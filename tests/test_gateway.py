"""Tests del gateway WebSocket y del pipeline compartido.

Levantan el servidor REAL de uvicorn en 127.0.0.1 (puerto efímero) con mDNS
desactivado; sin LLM/TTS reales (pipelines falsos).
Ejecutar: ./limits-env/bin/python -m unittest discover -s tests
"""

import json
import socket
import tempfile
import time
import unittest
from pathlib import Path

from websockets.exceptions import InvalidStatus
from websockets.sync.client import connect as ws_connect

from modules.gateway import (
    GatewayServer,
    RemoteBusy,
    TurnGate,
    load_or_create_token,
)


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class Harness:
    """Arranca/para un GatewayServer real sin mDNS ni efectos externos."""

    def __init__(self, pipeline, token_path=None):
        self.port = _free_port()
        self.srv = GatewayServer(
            pipeline=pipeline, host="127.0.0.1", port=self.port,
            mdns_name="TestLimits", token_path=token_path,
            app_version="test", speak_remote=True)

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


def ok_pipeline(text, wait_timeout=None, speak=True):
    return f"ok:{text}"


def busy_pipeline(text, wait_timeout=None, speak=True):
    if wait_timeout is not None:
        raise RemoteBusy()
    return "no debería pasar"


def _recv(ws):
    return json.loads(ws.recv(timeout=5))


class TestGatewayAuth(unittest.TestCase):
    def test_rechaza_sin_token(self):
        with Harness(ok_pipeline) as h:
            with self.assertRaises(InvalidStatus):
                h.client()  # sin header authorization

    def test_rechaza_token_incorrecto(self):
        with Harness(ok_pipeline) as h:
            with self.assertRaises(InvalidStatus):
                h.client(token="incorrecto")

    def test_token_se_genera_y_reutiliza(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = str(Path(tmp) / "gw_token")
            t1 = load_or_create_token(p)
            t2 = load_or_create_token(p)
            self.assertEqual(t1, t2)
            self.assertGreaterEqual(len(t1), 32)
            self.assertEqual(Path(p).stat().st_mode & 0o777, 0o600)


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


if __name__ == "__main__":
    unittest.main()
