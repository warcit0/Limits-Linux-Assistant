"""Grounding en `LLMEngine.process` (P1) con el router 100 % local.

Sin red: el motor de Ollama se sustituye por respuestas guionizadas.
"""

import unittest
from types import SimpleNamespace

from modules.llm import LLMEngine


class FakeLLM(LLMEngine):
    def __init__(self, answers=()):
        self.config = SimpleNamespace(OLLAMA_MODEL="fake")
        self.system_prompt = ""
        self.conversation_history = []
        self._history_loaded = True
        self.known_actions = {"get_time", "spotify_play", "get_system_info",
                              "media_control"}
        self.calls = 0
        self._cola = list(answers)

    def _query_ollama(self, user_text):
        self.calls += 1
        return self._cola.pop(0) if self._cola else None


def _r(action, params=None, response="Hecho."):
    return {"intent": "x", "action": action, "params": params or {},
            "response": response, "confidence": 0.9}


class TestGrounding(unittest.TestCase):
    def test_anclada_pasa(self):
        llm = FakeLLM([_r("get_time", {"detail": "time"})])
        out = llm.process("¿qué hora es?")
        self.assertTrue(out["grounded"])
        self.assertEqual(out["action"], "get_time")
        self.assertEqual(llm.calls, 1)

    def test_accion_inventada_se_bloquea(self):
        llm = FakeLLM([_r("media_play", {"type": "relaxing"})])
        out = llm.process("ponme música relajante")
        self.assertFalse(out["grounded"])
        self.assertEqual(out["grounding_reason"], "accion_desconocida")
        self.assertEqual(llm.calls, 1)

    def test_repara_enum(self):
        llm = FakeLLM([_r("get_system_info", {"type": "free_space"})])
        out = llm.process("¿cuánto espacio libre me queda?")
        self.assertTrue(out["grounded"])
        self.assertEqual(out["params"]["type"], "disk")

    def test_horario_ajeno_se_bloquea(self):
        llm = FakeLLM([_r("get_system_info", {"type": "time"})])
        out = llm.process("¿a qué hora abre el banco?")
        self.assertFalse(out["grounded"])

    def test_charla_sin_action(self):
        llm = FakeLLM([_r(None, {}, "Canberra.")])
        out = llm.process("¿cuál es la capital de Australia?")
        self.assertTrue(out["grounded"])
        self.assertEqual(out["grounding_reason"], "chat")

    def test_motor_caido_no_revienta(self):
        llm = FakeLLM([])
        out = llm.process("hola")
        self.assertEqual(out["intent"], "unknown")
        self.assertTrue(out["grounded"])

    def test_historial_se_registra_una_vez(self):
        llm = FakeLLM([_r("get_time", {"detail": "time"})])
        llm.process("¿qué hora es?")
        self.assertEqual(len(llm.conversation_history), 2)


if __name__ == "__main__":
    unittest.main()
