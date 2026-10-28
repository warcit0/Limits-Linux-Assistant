"""Cortafuegos del executor: confianza baja no ejecuta.

Decisión de producto (2026-10-28): si el modelo OMITE `confidence` se ejecuta
(antes se bloqueó y rompía órdenes legítimas como «cuánta RAM tengo», porque
qwen3.6-27b omite el campo a menudo). `LLMEngine.process` normaliza el valor a
`DEFAULT_CONFIDENCE` para que el log no diga 0.00 mientras se ejecuta.
El grounding de verdad (¿la acción responde a la pregunta?) es P1.
"""

import unittest

from modules.executor import CommandExecutor
from modules.llm import DEFAULT_CONFIDENCE, _normalize_confidence


class TestConfianza(unittest.TestCase):
    def setUp(self):
        self.ex = CommandExecutor()

    def test_sin_confidence_ejecuta(self):
        out = self.ex.execute({
            "intent": "get_time",
            "action": "get_time",
            "params": {"detail": "time"},
            "response": "",
        })
        self.assertRegex(out, r"^Son las \d{2}:\d{2}\.$")

    def test_confidence_baja_no_ejecuta(self):
        out = self.ex.execute({
            "intent": "system_info", "action": "get_system_info",
            "params": {"type": "cpu"}, "response": "Hecho.", "confidence": 0.0,
        })
        self.assertIn("No estoy seguro", out)

    def test_confidence_alta_ejecuta(self):
        out = self.ex.execute({
            "intent": "get_time", "action": "get_time",
            "params": {"detail": "time"}, "response": "", "confidence": 0.95,
        })
        self.assertRegex(out, r"^Son las \d{2}:\d{2}\.$")

    def test_confidence_como_texto(self):
        out = self.ex.execute({
            "intent": "get_time", "action": "get_time",
            "params": {"detail": "time"}, "response": "", "confidence": "0.9",
        })
        self.assertIn("Son las", out)

    def test_confidence_basura_no_revienta(self):
        out = self.ex.execute({
            "intent": "get_time", "action": "get_time",
            "params": {"detail": "time"}, "response": "", "confidence": "alta",
        })
        self.assertIn("Son las", out)


class TestNormalizacion(unittest.TestCase):
    def test_inyecta_default_si_falta(self):
        parsed = _normalize_confidence({"intent": "x"})
        self.assertEqual(parsed["confidence"], DEFAULT_CONFIDENCE)
        self.assertIsInstance(parsed["confidence"], float)

    def test_convierte_texto(self):
        self.assertEqual(_normalize_confidence({"confidence": "0.7"})["confidence"], 0.7)

    def test_basura_usa_default(self):
        self.assertEqual(_normalize_confidence({"confidence": "alta"})["confidence"],
                         DEFAULT_CONFIDENCE)

    def test_respeta_valor_bajo(self):
        self.assertEqual(_normalize_confidence({"confidence": 0.1})["confidence"], 0.1)


if __name__ == "__main__":
    unittest.main()
