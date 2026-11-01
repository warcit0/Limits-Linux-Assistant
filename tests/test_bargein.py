"""Tests de barge-in: corte del TTS, filtros de eco y palabras clave."""

import threading
import time
import unittest

from modules.speech_controller import (
    SpeechController,
    classify_interruption,
    looks_like_echo,
)
from modules.tts import wait_with_stop


class FakeProc:
    def __init__(self, frames_alive: int | None = None):
        self.frames_alive = frames_alive
        self.terminated = False
        self.stdin = None

    def poll(self):
        if self.frames_alive is None:
            return None
        if self.frames_alive <= 0:
            return 0
        self.frames_alive -= 1
        return None

    def terminate(self):
        self.terminated = True

    def wait(self, timeout=None):
        return 0

    def kill(self):
        self.terminated = True


class TestWaitWithStop(unittest.TestCase):
    def test_corta_al_pedir_stop(self):
        proc = FakeProc(frames_alive=None)
        event = threading.Event()
        threading.Timer(0.05, event.set).start()
        start = time.monotonic()
        self.assertTrue(wait_with_stop(proc, event))
        self.assertLess(time.monotonic() - start, 0.5)
        self.assertTrue(proc.terminated)

    def test_termina_solo(self):
        proc = FakeProc(frames_alive=3)
        self.assertFalse(wait_with_stop(proc, threading.Event()))
        self.assertFalse(proc.terminated)

    def test_timeout_corta(self):
        proc = FakeProc(frames_alive=None)
        start = time.monotonic()
        self.assertFalse(wait_with_stop(proc, threading.Event(), timeout=0.2))
        self.assertLess(time.monotonic() - start, 1.0)
        self.assertTrue(proc.terminated)

    def test_sin_evento_no_falla(self):
        self.assertFalse(wait_with_stop(FakeProc(frames_alive=1), None))


class TestFiltros(unittest.TestCase):
    SPOKEN = ("El proyecto principal de Limits es un asistente de voz local "
              "que corre en CachyOS con Hyprland y no envía audio a la nube.")

    def test_palabras_clave_cortan(self):
        for frase in ("para", "Para.", "cállate ya", "callate", "stop",
                      "basta por favor"):
            self.assertEqual(
                classify_interruption(frase, self.SPOKEN,
                                      ["para", "cállate", "callate", "stop", "basta"]),
                "stop", frase)

    def test_eco_se_descarta(self):
        eco = "el proyecto principal de limits es un asistente de voz local"
        self.assertEqual(classify_interruption(
            eco, self.SPOKEN, ["para"]), "echo")

    def test_comando_se_ejecuta(self):
        self.assertEqual(classify_interruption(
            "abre spotify", self.SPOKEN, ["para"]), "command")

    def test_silencio_es_eco(self):
        self.assertEqual(classify_interruption("", self.SPOKEN), "echo")

    def test_looks_like_echo(self):
        self.assertTrue(looks_like_echo(
            "el proyecto principal es limits",
            "el proyecto principal es limits y corre local"))
        self.assertFalse(looks_like_echo("abre spotify",
                                         "el proyecto es un asistente"))
        # Una sola palabra nunca es eco: «para» debe poder cortar.
        self.assertFalse(looks_like_echo("para", "para ver si funciona"))

    def test_clave_en_el_propio_texto_sigue_cortando(self):
        spoken = "Esta frase dice para que veas el problema del eco."
        self.assertEqual(classify_interruption("para", spoken, ["para"]), "stop")
        # Copia larga del TTS: es eco aunque contenga la palabra clave.
        self.assertEqual(classify_interruption(
            "esta frase dice para que veas el problema del eco",
            spoken, ["para"]), "echo")


class FakeVoice:
    def __init__(self, result="ok"):
        self.result = result
        self.calls = []
        self.stop_sets = []

    def speak(self, text, source="system", stop_event=None):
        self.calls.append((text, source))
        self.stop_sets.append(stop_event.is_set() if stop_event else None)
        return self.result


class TestSpeechController(unittest.TestCase):
    def test_sin_stt_delega_en_la_voz(self):
        voice = FakeVoice("ok")
        ctrl = SpeechController(voice, stt=None, enabled=True)
        self.assertFalse(ctrl.enabled)
        self.assertEqual(ctrl.speak("hola"), "ok")
        self.assertEqual(voice.calls, [("hola", "system")])

    def test_stop_se_limpia_en_el_siguiente_turno(self):
        voice = FakeVoice("ok")
        ctrl = SpeechController(voice, stt=None)
        ctrl.stop()
        self.assertTrue(ctrl._stop_event.is_set())
        ctrl.speak("hola")
        self.assertFalse(ctrl._stop_event.is_set())
        self.assertEqual(voice.stop_sets, [False])

    def test_pending_text_se_resetea(self):
        voice = FakeVoice("ok")
        ctrl = SpeechController(voice, stt=None)
        ctrl.pending_text = "basura vieja"
        ctrl.speak("hola")
        self.assertEqual(ctrl.pending_text, "")

    def test_clasificacion_de_eco_no_encadena(self):
        self.assertEqual(classify_interruption(
            "el proyecto principal es limits",
            "el proyecto principal es limits y corre local"), "echo")


if __name__ == "__main__":
    unittest.main()
