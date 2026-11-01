"""Tests del gateway WebSocket y del pipeline compartido.

Levantan el servidor REAL de uvicorn en 127.0.0.1 (puerto efímero) con mDNS
desactivado; sin LLM/TTS reales (pipelines falsos).
Ejecutar: ./limits-env/bin/python -m unittest discover -s tests
"""

import json
import socket
import tempfile
import time
import threading
import unittest
from unittest import mock
from pathlib import Path

from websockets.exceptions import ConnectionClosed
from websockets.sync.client import connect as ws_connect

from modules.gateway import (
    GatewayServer,
    RemoteBusy,
    TurnGate,
    load_or_create_token,
    pairing_uri,
    regenerate_token,
)


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class Harness:
    """Arranca/para un GatewayServer real sin mDNS ni efectos externos."""

    def __init__(self, pipeline, token_path=None, speak_remote=True, speak_fn=None,
                 stop_fn=None, stop_words=()):
        self.port = _free_port()
        self.srv = GatewayServer(
            pipeline=pipeline, host="127.0.0.1", port=self.port,
            mdns_name="TestLimits", token_path=token_path,
            app_version="test", speak_remote=speak_remote,
            speak_fn=speak_fn, stop_fn=stop_fn, stop_words=stop_words)

    def __enter__(self):
        self.srv._register_mdns = lambda: None  # jamás anunciar en la LAN real
        self.srv.start()
        deadline = time.time() + 5
        while time.time() < deadline:
            try:
                probe = socket.create_connection(("127.0.0.1", self.port), 0.2)
                probe.close()
                return self
            except OSError:
                time.sleep(0.05)
        raise RuntimeError("gateway no arrancó")

    def __exit__(self, *a):
        self.srv.stop()

    def client(self, token=None, extra=None):
        headers = dict(extra or {})
        if token is not None:
            headers["authorization"] = f"Bearer {token}"
        return ws_connect(f"ws://127.0.0.1:{self.port}/ws",
                          additional_headers=headers)


def ok_pipeline(text, wait_timeout=None, speak=True, on_response=None):
    respuesta = f"ok:{text}"
    if on_response is not None:
        on_response(respuesta)
    return respuesta


def busy_pipeline(text, wait_timeout=None, speak=True):
    if wait_timeout is not None:
        raise RemoteBusy()
    return "no debería pasar"


def _recv(ws):
    # Las pruebas anteriores al evento aditivo de cierre siguen leyendo el
    # siguiente mensaje útil; el cierre se comprueba explícitamente aparte.
    while True:
        mensaje = json.loads(ws.recv(timeout=5))
        if mensaje.get('kind') != 'turn_finished':
            return mensaje


class TestGatewayAuth(unittest.TestCase):
    def _rechazo(self, h, token=None):
        """Sin token válido: el server acepta, manda el error y cierra 4401."""
        with h.client(token=token) as ws:
            first = _recv(ws)
            self.assertEqual(first["err"], "UNAUTHORIZED")
            with self.assertRaises(ConnectionClosed) as ctx:
                ws.recv(timeout=5)
            self.assertEqual(ctx.exception.rcvd.code, 4401)

    def test_rechaza_sin_token(self):
        with Harness(ok_pipeline) as h:
            self._rechazo(h)

    def test_rechaza_token_incorrecto(self):
        with Harness(ok_pipeline) as h:
            self._rechazo(h, token="incorrecto")

    def test_token_se_genera_y_reutiliza(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = str(Path(tmp) / "gw_token")
            t1 = load_or_create_token(p)
            t2 = load_or_create_token(p)
            self.assertEqual(t1, t2)
            self.assertGreaterEqual(len(t1), 32)
            self.assertEqual(Path(p).stat().st_mode & 0o777, 0o600)

    def test_chmod_se_reaplica_a_token_existente(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "gw_token"
            p.write_text("a" * 64)
            p.chmod(0o644)
            load_or_create_token(str(p))
            self.assertEqual(p.stat().st_mode & 0o777, 0o600)

    def test_regenerate_invalida_el_anterior(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = str(Path(tmp) / "gw_token")
            old = load_or_create_token(p)
            new = regenerate_token(p)
            self.assertNotEqual(old, new)
            self.assertEqual(load_or_create_token(p), new)


class TestPairing(unittest.TestCase):
    def test_uri_contiene_host_puerto_y_token(self):
        uri = pairing_uri("192.168.1.101", 8765, "deadbeef")
        self.assertTrue(uri.startswith("limits://pair?"))
        self.assertIn("h=192.168.1.101", uri)
        self.assertIn("p=8765", uri)
        self.assertIn("t=deadbeef", uri)

    def test_servidor_expone_uri_con_ip_lan(self):
        with Harness(ok_pipeline) as h:
            uri = h.srv.pairing_uri(host="10.0.0.5")
            self.assertIn("h=10.0.0.5", uri)
            self.assertIn(f"t={h.srv.token}", uri)


class TestGatewayProtocol(unittest.TestCase):
    def setUp(self):
        self.h = Harness(ok_pipeline).__enter__()
        self.ws = self.h.client(token=self.h.srv.token)
        welcome = _recv(self.ws)
        self.assertEqual(welcome["type"], "welcome")
        self.assertEqual(welcome["v"], 1)

    def tearDown(self):
        self.ws.close()
        self.h.__exit__()

    def test_ping_pong(self):
        self.ws.send(json.dumps({"v": 1, "type": "ping"}))
        self.assertEqual(_recv(self.ws)["type"], "pong")

    def test_hello_responde_welcome(self):
        self.ws.send(json.dumps({"v": 1, "type": "hello", "device": "test"}))
        self.assertEqual(_recv(self.ws)["type"], "welcome")

    def test_comando_fluye_por_el_pipeline(self):
        self.ws.send(json.dumps({"v": 1, "type": "command", "text": "qué RAM hay"}))
        ev = _recv(self.ws)
        self.assertEqual((ev["type"], ev["kind"]), ("event", "processing"))
        r = _recv(self.ws)
        self.assertTrue(r["ok"])
        self.assertEqual(r["text"], "ok:qué RAM hay")

    def test_comando_vacio_da_error(self):
        self.ws.send(json.dumps({"v": 1, "type": "command", "text": "   "}))
        r = _recv(self.ws)
        self.assertEqual((r["ok"], r["err"]), (False, "EMPTY_TEXT"))

    def test_busy_cuando_no_hay_turno(self):
        self.h.srv.pipeline = busy_pipeline  # parche en caliente
        self.ws.send(json.dumps({"v": 1, "type": "command", "text": "hola"}))
        ev = _recv(self.ws)  # processing llega igual
        self.assertEqual(ev["kind"], "processing")
        r = _recv(self.ws)
        self.assertEqual(r["err"], "BUSY")

    def test_json_invalido(self):
        self.ws.send("esto-no-es-json{{{")
        r = _recv(self.ws)
        self.assertEqual(r["err"], "BAD_JSON")

    def test_tipo_desconocido(self):
        self.ws.send(json.dumps({"v": 1, "type": "voltear", "x": 1}))
        r = _recv(self.ws)
        self.assertEqual(r["err"], "UNKNOWN_TYPE")

    def test_version_incorrecta(self):
        self.ws.send(json.dumps({"v": 99, "type": "ping"}))
        r = _recv(self.ws)
        self.assertEqual(r["err"], "UNSUPPORTED_VERSION")

    def test_stop_sin_handler_responde_stopped(self):
        self.ws.send(json.dumps({"v": 1, "type": "stop"}))
        ev = _recv(self.ws)
        self.assertEqual((ev["type"], ev["kind"]), ("event", "stopped"))


class TestGatewayStop(unittest.TestCase):
    """Barge-in desde el móvil: `stop` corta el TTS del PC."""

    def test_stop_llama_al_controlador(self):
        called = []
        h = Harness(ok_pipeline, stop_fn=lambda: called.append(True)).__enter__()
        ws = h.client(token=h.srv.token)
        _recv(ws)  # welcome
        try:
            ws.send(json.dumps({"v": 1, "type": "stop"}))
            ev = _recv(ws)
            self.assertEqual((ev["type"], ev["kind"]), ("event", "stopped"))
            self.assertEqual(called, [True])
        finally:
            ws.close()
            h.__exit__()

    def test_para_dictado_corta_sin_pasar_por_el_pipeline(self):
        """El micro del móvil manda texto: «para» debe cortar, no encolarse."""
        called, turnos = [], []
        h = Harness(lambda *a, **k: turnos.append(a) or "no debería",
                    stop_fn=lambda: called.append(True),
                    stop_words=["para", "cállate", "basta"]).__enter__()
        ws = h.client(token=h.srv.token)
        _recv(ws)  # welcome
        try:
            # Con acento, puntuación y mayúsculas: el reconocedor no es limpio.
            ws.send(json.dumps({"v": 1, "type": "command", "text": "¡Para!"}))
            ev = _recv(ws)
            self.assertEqual((ev["type"], ev["kind"]), ("event", "stopped"))
            self.assertEqual(called, [True])
            self.assertEqual(turnos, [])
        finally:
            ws.close()
            h.__exit__()

    def test_frase_con_para_sigue_siendo_comando(self):
        """«para la música» NO es una interrupción: es un comando normal."""
        turnos, called = [], []
        h = Harness(lambda text, *a, **k: turnos.append(text) or "hecho",
                    stop_fn=lambda: called.append(True),
                    stop_words=["para"]).__enter__()
        ws = h.client(token=h.srv.token)
        _recv(ws)  # welcome
        try:
            ws.send(json.dumps({"v": 1, "type": "command",
                                "text": "para la música"}))
            r = _recv(ws)
            while r.get("type") == "event":  # primero llega `processing`
                r = _recv(ws)
            self.assertEqual(r["type"], "response")
            self.assertEqual(called, [])
            self.assertEqual(turnos, ["para la música"])
        finally:
            ws.close()
            h.__exit__()


class TestGatewaySpeaking(unittest.TestCase):
    """F5: la respuesta llega ANTES de hablar y la app recibe eventos de voz."""

    def test_respuesta_antes_de_speaking_y_pipeline_sin_voz(self):
        llamadas, dicho = [], []

        def pipe(text, wait_timeout=None, speak=True, on_response=None):
            llamadas.append(speak)
            return ok_pipeline(text, wait_timeout, speak, on_response)

        h = Harness(pipe, speak_remote=True, speak_fn=dicho.append).__enter__()
        try:
            ws = h.client(token=h.srv.token)
            _recv(ws)  # welcome
            ws.send(json.dumps({"v": 1, "type": "command", "text": "hola"}))
            self.assertEqual(_recv(ws)["kind"], "processing")
            r = _recv(ws)
            self.assertEqual((r["type"], r["text"]), ("response", "ok:hola"))
            self.assertEqual(_recv(ws)["kind"], "speaking_started")
            self.assertEqual(_recv(ws)["kind"], "speaking_finished")
            cierre = json.loads(ws.recv(timeout=5))
            self.assertEqual(cierre['kind'],'turn_finished')
            self.assertEqual(cierre['turno'],r['turno'])
            self.assertEqual(llamadas, [False])      # el pipeline no habla
            self.assertEqual(dicho, ["ok:hola"])     # habla el gateway
            ws.close()
        finally:
            h.__exit__()

    def test_speak_remote_false_no_habla_ni_emite(self):
        dicho = []
        h = Harness(ok_pipeline, speak_remote=False,
                    speak_fn=dicho.append).__enter__()
        try:
            ws = h.client(token=h.srv.token)
            _recv(ws)
            ws.send(json.dumps({"v": 1, "type": "command", "text": "hola"}))
            self.assertEqual(_recv(ws)["kind"], "processing")
            self.assertEqual(_recv(ws)["text"], "ok:hola")
            with self.assertRaises(TimeoutError):
                ws.recv(timeout=0.7)                 # sin eventos de voz
            self.assertEqual(dicho, [])
            ws.close()
        finally:
            h.__exit__()

    def test_fallo_de_tts_no_rompe_el_turno(self):
        def boom(_text):
            raise RuntimeError("sin audio")

        h = Harness(ok_pipeline, speak_remote=True, speak_fn=boom).__enter__()
        try:
            ws = h.client(token=h.srv.token)
            _recv(ws)
            ws.send(json.dumps({"v": 1, "type": "command", "text": "hola"}))
            self.assertEqual(_recv(ws)["kind"], "processing")
            self.assertEqual(_recv(ws)["text"], "ok:hola")
            self.assertEqual(_recv(ws)["kind"], "speaking_started")
            self.assertEqual(_recv(ws)["kind"], "speaking_finished")
            ws.send(json.dumps({"v": 1, "type": "ping"}))  # turno sigue vivo
            self.assertEqual(_recv(ws)["type"], "pong")
            ws.close()
        finally:
            h.__exit__()


class TestTurnGate(unittest.TestCase):
    def test_timeout_devuelve_false_sin_bloquear(self):
        g = TurnGate()
        self.assertTrue(g.acquire())
        try:
            self.assertFalse(g.acquire(timeout=0.05))
        finally:
            g.release()
        self.assertTrue(g.acquire(timeout=0.05))  # liberado → disponible

    def test_release_doble_no_explota(self):
        g = TurnGate()
        g.acquire()
        g.release()
        g.release()  # idempotente ante errores


# ── Pipeline compartido (make_pipeline) ──────────────────────────────────────

from main import make_pipeline  # noqa: E402

# Aislamiento: el pipeline real registra episodios en memoria. Sin esto, los
# tests escribirían en ~/.limits/memory.db del usuario.
from modules.memory import MemoryStore, set_store  # noqa: E402

_test_memory = MemoryStore(":memory:")
set_store(_test_memory)


def tearDownModule():
    set_store(None)
    _test_memory.close()


class FakeLLM:
    def process(self, t):
        return {"intent": "test", "action": "noop", "params": {},
                "response": t, "confidence": 1.0}


class FakeExecutor:
    def execute(self, parsed):
        return f"resp:{parsed['response']}"


class FakeTTS:
    def __init__(self):
        self.spoken = []

    def speak(self, text, source="system"):
        self.spoken.append(text)


class TestMakePipeline(unittest.TestCase):
    def _pipeline(self):
        gate = TurnGate()
        tts = FakeTTS()
        pipe = make_pipeline(FakeLLM(), FakeExecutor(), tts, gate)
        return pipe, tts, gate

    def test_flujo_completo_y_habla(self):
        pipe, tts, _ = self._pipeline()
        out = pipe("hola")
        self.assertEqual(out, "resp:hola")
        self.assertEqual(tts.spoken, ["resp:hola"])

    def test_speak_false_no_habla(self):
        pipe, tts, _ = self._pipeline()
        out = pipe("hola", speak=False)
        self.assertEqual(out, "resp:hola")
        self.assertEqual(tts.spoken, [])

    def test_remotebusy_si_lock_ocupado(self):
        pipe, _, gate = self._pipeline()
        gate.acquire()  # otro turno en curso
        try:
            with self.assertRaises(RemoteBusy):
                pipe("hola", wait_timeout=0.05)
        finally:
            gate.release()

    def test_callback_fallido_libera_el_turno(self):
        pipe, _, gate = self._pipeline()
        with self.assertRaisesRegex(RuntimeError, "desconectado"):
            pipe("hola", speak=False,
                 on_response=mock.Mock(side_effect=RuntimeError("desconectado")))
        self.assertTrue(gate.acquire(0))
        gate.release()

    def test_gemini_cancela_pendiente_incluso_si_falla(self):
        from modules.executor import CommandExecutor

        for frase in ("gemini hola", "investiga las estrellas"):
            for falla in (False, True):
                with self.subTest(frase=frase, falla=falla):
                    ejecutor = CommandExecutor()
                    apagado = mock.Mock(return_value="apagado simulado")
                    ejecutor.action_map["shutdown"] = apagado
                    ejecutor.execute({"action": "shutdown", "params": {}})
                    gemini = mock.Mock()
                    gemini.chat.return_value = "respuesta simulada"
                    if falla:
                        gemini.chat.side_effect = RuntimeError("sin conexión")
                    pipeline = make_pipeline(FakeLLM(), ejecutor, FakeTTS(),
                                             TurnGate(), gemini=gemini)
                    if falla:
                        with self.assertRaises(RuntimeError):
                            pipeline(frase, speak=False)
                    else:
                        pipeline(frase, speak=False)
                    self.assertIsNone(ejecutor._pending_action)
                    ejecutor.execute({"intent": "confirm", "action": "confirm",
                                      "confidence": 1.0, "grounded": True})
                    apagado.assert_not_called()

    def test_rechazo_grounding_cancela_pendiente(self):
        from modules.executor import CommandExecutor

        ejecutor = CommandExecutor()
        apagado = mock.Mock()
        ejecutor.action_map["shutdown"] = apagado
        ejecutor.execute({"action": "shutdown", "params": {}})
        ejecutor.execute({"action": "get_time", "grounded": False})
        ejecutor.execute({"intent": "confirm", "action": "confirm"})
        self.assertIsNone(ejecutor._pending_action)
        apagado.assert_not_called()

    def test_confirmacion_inmediata_conserva_funcionamiento(self):
        from modules.executor import CommandExecutor

        ejecutor = CommandExecutor()
        apagado = mock.Mock(return_value="apagado simulado")
        ejecutor.action_map["shutdown"] = apagado
        ejecutor.execute({"action": "shutdown", "params": {}})
        ejecutor.execute({"intent": "confirm", "action": "confirm"})
        apagado.assert_called_once_with()


class TestVozRemotaSerializada(unittest.TestCase):
    def test_memoria_local_y_movil_persisten_en_la_misma_base(self):
        from modules.executor import CommandExecutor

        with tempfile.TemporaryDirectory() as temporal:
            ruta = Path(temporal) / "memoria.db"
            memoria = MemoryStore(ruta)
            try:
                with mock.patch("modules.memory.get_store", return_value=memoria):
                    pipeline = make_pipeline(FakeLLM(), CommandExecutor(),
                                             FakeTTS(), TurnGate())
                    pipeline("recuerda que mi proyecto es Limits", speak=False)
                    with Harness(pipeline, token_path=str(Path(temporal) / "token"),
                                 speak_remote=False) as servidor:
                        with servidor.client(servidor.srv.token) as movil:
                            _recv(movil)
                            movil.send(json.dumps({"v": 1, "type": "command",
                                                   "text": "recuerda que mi color es azul"}))
                            self.assertEqual(_recv(movil)["kind"], "processing")
                            respuesta = _recv(movil)
                            self.assertIn("Anotado", respuesta["text"])
                    self.assertEqual(memoria.recall("color")[0]["value"], "azul")
                    self.assertEqual(memoria.stats()["episodes"], 4)
            finally:
                memoria.close()
            reabierta = MemoryStore(ruta)
            try:
                self.assertEqual(reabierta.stats()["facts"], 2)
                self.assertEqual(reabierta.stats()["episodes"], 4)
            finally:
                reabierta.close()

    def test_dos_clientes_y_voz_local_comparten_bloqueo_hasta_stop(self):
        bloqueo = TurnGate()
        hablando = threading.Event()
        terminar = threading.Event()
        procesados = []

        class Modelo(FakeLLM):
            def process(self, texto):
                procesados.append(texto)
                return super().process(texto)

        def hablar(texto):
            if texto == "resp:hola":
                hablando.set()
                if not terminar.wait(5):
                    raise RuntimeError("la prueba no interrumpió la voz")

        pipeline = make_pipeline(Modelo(), FakeExecutor(), FakeTTS(), bloqueo)
        with tempfile.TemporaryDirectory() as temporal:
            with Harness(pipeline, token_path=str(Path(temporal) / "token"),
                         speak_fn=hablar, stop_fn=terminar.set) as servidor:
                with servidor.client(servidor.srv.token) as primero, \
                        servidor.client(servidor.srv.token) as segundo:
                    _recv(primero)
                    _recv(segundo)
                    try:
                        primero.send(json.dumps({"v": 1, "type": "command", "text": "hola"}))
                        self.assertEqual(_recv(primero)["kind"], "processing")
                        self.assertEqual(_recv(primero)["text"], "resp:hola")
                        self.assertEqual(_recv(primero)["kind"], "speaking_started")
                        self.assertTrue(hablando.wait(2))
                        with self.assertRaises(RemoteBusy):
                            pipeline("voz local", wait_timeout=0.02)
                        segundo.send(json.dumps({"v": 1, "type": "command", "text": "saludos"}))
                        self.assertEqual(_recv(segundo)["kind"], "processing")
                        self.assertEqual(procesados, ["hola"])

                        # Stop se recibe mientras el trabajador conserva el turno.
                        primero.send(json.dumps({"v": 1, "type": "stop"}))
                        eventos = {_recv(primero)["kind"], _recv(primero)["kind"]}
                        self.assertEqual(eventos, {"stopped", "speaking_finished"})
                        self.assertEqual(_recv(segundo)["text"], "resp:saludos")
                        self.assertEqual(_recv(segundo)["kind"], "speaking_started")
                        self.assertEqual(_recv(segundo)["kind"], "speaking_finished")
                        self.assertEqual(procesados, ["hola", "saludos"])
                    finally:
                        terminar.set()
                self.assertTrue(bloqueo.acquire(2))
                bloqueo.release()


if __name__ == "__main__":
    unittest.main()
