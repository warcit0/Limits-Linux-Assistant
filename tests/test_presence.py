"""Contrato visual, aislamiento de turnos y audio medido sin micrófono."""

import array
import json
import socket
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from modules import presence


class TestPresencia(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.bus = presence.Presencia(
            Path(self.tmp.name) / "privado" / "presence.sock"
        ).iniciar()
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(self.bus.cerrar)

    def conectar(self):
        c = socket.socket(socket.AF_UNIX)
        c.settimeout(1)
        c.connect(str(self.bus.ruta))
        self.addCleanup(c.close)
        return c, c.makefile("rb")

    def esperar(self, lector, predicado):
        for _ in range(20):
            dato = json.loads(lector.readline())
            if predicado(dato):
                return dato
        self.fail("No llegó el estado esperado")

    def test_reconexion_recibe_estado_sin_texto_privado(self):
        turno = self.bus.comenzar(lambda: None)
        self.bus.fase("investigando")
        c, f = self.conectar()
        self.addCleanup(f.close)
        d = self.esperar(f, lambda x: x["estado"] == "investigando")
        self.assertEqual(d["turno"], turno)
        self.assertNotIn("texto", d)
        self.assertEqual(self.bus.ruta.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.bus.ruta.parent.stat().st_mode & 0o777, 0o700)

    def test_stop_solo_para_el_turno_actual_una_vez(self):
        fin = threading.Event()
        viejo = self.bus.comenzar(lambda: self.fail("Se canceló un turno antiguo"))
        turno = self.bus.comenzar(fin.set)
        c, f = self.conectar()
        self.addCleanup(f.close)
        self.esperar(f, lambda x: x["turno"] == turno)
        c.sendall((json.dumps({"cmd": "confirm", "turno": turno}) + "\n").encode())
        c.sendall((json.dumps({"cmd": "stop", "turno": viejo}) + "\n").encode())
        self.assertFalse(fin.wait(0.08))
        c.sendall((json.dumps({"cmd": "stop", "turno": turno}) + "\n").encode())
        self.assertTrue(fin.wait(1))
        self.assertFalse(self.bus.detener_turno(turno))
        self.assertEqual(self.bus.base, "interrumpido")

    def test_stop_no_se_pierde_si_el_cliente_cierra_tras_enviarlo(self):
        fin = threading.Event()
        turno = self.bus.comenzar(fin.set)
        with socket.socket(socket.AF_UNIX) as c:
            c.connect(str(self.bus.ruta))
            c.sendall((json.dumps({"cmd": "stop", "turno": turno}) + "\n").encode())
        self.assertTrue(fin.wait(1))

    def test_callback_tardio_no_cancela_un_turno_nuevo(self):
        viejo = self.bus.comenzar()
        self.bus.comenzar()
        callback = mock.Mock()
        self.bus._cancelar_seguro(viejo, callback)
        callback.assert_not_called()

    def test_instancia_duplicada_no_borra_el_socket(self):
        otra = presence.Presencia(self.bus.ruta)
        with self.assertRaises(BlockingIOError):
            otra.iniciar()
        self.assertTrue(self.bus.ruta.exists())
        c, f = self.conectar()
        self.addCleanup(f.close)
        self.assertEqual(json.loads(f.readline())["estado"], "oculto")

    def test_no_sigue_en_audio_tras_cancelar_o_recibir_audio_antiguo(self):
        turno = self.bus.comenzar(lambda: None)
        a = self.bus.comenzar_audio()
        self.bus.pcm(a, array.array("h", [16000] * 882).tobytes())
        self.bus._publicar()
        self.assertGreater(self.bus.ultimo["nivel"], 0)
        self.bus.detener_turno(turno)
        self.bus.comenzar(lambda: None)
        self.bus.pcm(a, array.array("h", [32000] * 882).tobytes())
        self.bus.terminar_audio(a)
        self.assertEqual(self.bus.ultimo["estado"], "pensando")
        self.assertEqual(len(self.bus.envolvente), 0)

    def test_silencio_pause_y_actividad_durante_voz(self):
        self.bus.comenzar()
        self.bus.fase("investigando")
        a = self.bus.comenzar_audio()
        self.bus.pcm(a, b"\0\0" * 882)
        self.bus._publicar()
        self.assertEqual(self.bus.ultimo["nivel"], 0)
        self.assertEqual(self.bus.ultimo["estado"], "hablando")
        self.assertEqual(self.bus.ultimo["actividad"], "investigando")
        self.bus.pausar(True)
        self.assertTrue(self.bus.ultimo["pausado"])
        self.assertNotEqual(self.bus.ultimo["estado"], "hablando")
        self.bus.pausar(False)
        self.bus.terminar_audio(a)
        self.assertEqual(self.bus.ultimo["estado"], "investigando")

    def test_confirmacion_y_escucha_no_ocultan_un_turno_remoto(self):
        turno = self.bus.comenzar()
        self.bus.fase("investigando")
        self.bus.escucha(True)
        self.assertEqual(self.bus.base, "investigando")
        self.bus.terminar(turno, "confirmacion")
        self.bus.escucha(True)
        self.assertEqual(self.bus.base, "escuchando")
        self.bus.escucha(False)
        self.assertEqual(self.bus.base, "confirmacion")

    def test_cliente_lento_no_bloquea_la_generacion(self):
        c, f = self.conectar()
        self.addCleanup(f.close)
        t = time.monotonic()
        for _ in range(1000):
            self.bus.fase("pensando")
        self.assertLess(time.monotonic() - t, 0.5)


class TestPipelineVisual(unittest.TestCase):
    def test_pipeline_entrega_audio_y_vuelve_a_reposo(self):
        from main import make_pipeline
        from modules.gateway import TurnGate

        bus = presence.Presencia("/no-se-abre-socket")
        presencia_anterior = presence.obtener()
        presence.instalar(bus)
        self.addCleanup(presence.instalar, presencia_anterior)
        executor = mock.Mock()
        executor._pending_action = None
        executor.execute.return_value = "Son las tres."
        voz = mock.Mock()
        with mock.patch("modules.memory.get_store"):
            p = make_pipeline(mock.Mock(), executor, voz, TurnGate())
            self.assertEqual(p("qué hora es"), "Son las tres.")
        self.assertEqual(bus.base, "oculto")
        self.assertFalse(bus.activo)

    def test_interrupcion_de_voz_publica_el_corte_y_descarta_aprobaciones(self):
        from main import make_pipeline
        from modules.gateway import TurnGate

        bus = presence.Presencia("/no-se-abre-socket")
        anterior = presence.obtener()
        presence.instalar(bus)
        self.addCleanup(presence.instalar, anterior)
        executor = mock.Mock()
        executor._pending_action = {"action": "shutdown"}
        executor.execute.return_value = "¿Confirmas?"
        voz = mock.Mock()
        voz.speak.return_value = "interrupted"
        with mock.patch("modules.memory.get_store"):
            make_pipeline(mock.Mock(), executor, voz, TurnGate())("qué hora es")
        self.assertEqual(bus.base, "interrumpido")
        executor.cancel_pending.assert_called()

    def test_detener_mientras_router_espera_no_ejecuta_al_regresar(self):
        from main import make_pipeline
        from modules.gateway import TurnGate

        bus = presence.Presencia("/no-se-abre-socket")
        anterior = presence.obtener()
        presence.instalar(bus)
        self.addCleanup(presence.instalar, anterior)
        executor = mock.Mock()
        executor._pending_action = None
        llm = mock.Mock()

        def procesar(texto):
            self.assertTrue(bus.detener_turno(bus.turno))
            return {"action": "shutdown", "params": {}}

        llm.process.side_effect = procesar
        with mock.patch("modules.memory.get_store"):
            p = make_pipeline(llm, executor, mock.Mock(), TurnGate())
            r = p("una petición para el modelo", speak=False)
        self.assertEqual(r, "Tarea cancelada.")
        executor.execute.assert_not_called()


class TestMotoresVisuales(unittest.TestCase):
    def setUp(self):
        anterior = presence.obtener()
        self.addCleanup(presence.instalar, anterior)
        presence.instalar(presence.Presencia("/no-se-abre-socket"))

    def test_elevenlabs_decodifica_audio_sin_llamar_a_la_api(self):
        from modules.tts_elevenlabs import ElevenLabsEngine, TTSUnavailable

        motor = ElevenLabsEngine.__new__(ElevenLabsEngine)
        with (
            mock.patch("shutil.which", return_value="/bin/ffmpeg"),
            mock.patch(
                "modules.audio_meter.reproducir_archivo", return_value="ok"
            ) as reproducir,
        ):
            self.assertEqual(motor._play(Path("/audio-en-cache.mp3"), 20), "ok")
            reproducir.assert_called_once_with(Path("/audio-en-cache.mp3"), None)
        with (
            mock.patch("shutil.which", return_value="/bin/ffmpeg"),
            mock.patch("modules.audio_meter.reproducir_archivo", return_value="error"),
        ):
            with self.assertRaises(TTSUnavailable):
                motor._play(Path("/audio-en-cache.mp3"), 20)

    def test_espeak_usa_archivo_temporal_privado_y_reproduccion_medida(self):
        from modules.tts import TTSEngine

        motor = TTSEngine.__new__(TTSEngine)
        proceso = mock.Mock(returncode=0, stdin=None)
        proceso.poll.return_value = 0

        def reproducir(ruta, event, **kwargs):
            self.assertEqual(Path(ruta).stat().st_mode & 0o777, 0o600)
            return "ok"

        with (
            mock.patch("shutil.which", return_value="/bin/ffmpeg"),
            mock.patch("modules.tts.subprocess.Popen", return_value=proceso),
            mock.patch(
                "modules.audio_meter.reproducir_archivo", side_effect=reproducir
            ),
        ):
            self.assertEqual(motor._speak_espeak("Prueba de voz"), "ok")
