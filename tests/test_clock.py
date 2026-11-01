"""Tests de modules/clock.py — formato, zona y duraciones."""

import unittest
from datetime import datetime, timedelta, timezone

from modules.clock import (
    date_line,
    now_line,
    parse_duration,
    time_line,
    weekday_line,
)


class TestClock(unittest.TestCase):
    def setUp(self):
        # Miércoles 28 de octubre de 2026, 16:05 UTC-6
        self.dt = datetime(2026, 10, 28, 16, 5, tzinfo=timezone(timedelta(hours=-6)))

    def test_now_line(self):
        self.assertEqual(
            now_line(now=self.dt),
            "miércoles 28 de octubre de 2026, 16:05 (UTC-06:00)")

    def test_time_line(self):
        self.assertEqual(time_line(now=self.dt), "Son las 16:05.")

    def test_date_line(self):
        self.assertEqual(date_line(now=self.dt),
                         "Hoy es miércoles 28 de octubre de 2026.")

    def test_weekday_line(self):
        self.assertEqual(weekday_line(now=self.dt), "Hoy es miércoles.")

    def test_zona_horaria_valida(self):
        linea = now_line(tz="Europe/Madrid", now=None)
        self.assertRegex(linea, r"^\w+ \d{1,2} de \w+ de \d{4}, \d{2}:\d{2} \(UTC[+-]\d{2}:\d{2}\)$")

    def test_zona_invalida_no_revienta(self):
        self.assertIn("de", now_line(tz="No/Existe"))

    def test_now_line_sin_zona_usa_local(self):
        self.assertRegex(now_line(), r"\(UTC[+-]\d{2}:\d{2}\)")


class TestDuration(unittest.TestCase):
    def test_minutos_horas_dias(self):
        self.assertEqual(parse_duration("en 20 minutos"), timedelta(minutes=20))
        self.assertEqual(parse_duration("2 horas"), timedelta(hours=2))
        self.assertEqual(parse_duration("1 dia"), timedelta(days=1))
        self.assertEqual(parse_duration("30 segundos"), timedelta(seconds=30))

    def test_palabras(self):
        self.assertEqual(parse_duration("media hora"), timedelta(minutes=30))
        self.assertEqual(parse_duration("una hora"), timedelta(hours=1))
        self.assertEqual(parse_duration("un minuto"), timedelta(minutes=1))

    def test_sin_duracion(self):
        for frase in ("mañana", "el martes", "cuando llueva", ""):
            self.assertIsNone(parse_duration(frase), frase)


class TestPromptNow(unittest.TestCase):
    """El prompt NO puede congelar la hora al arrancar."""

    def setUp(self):
        from modules.memory import MemoryStore, set_store
        self.store = MemoryStore(":memory:")
        set_store(self.store)

    def tearDown(self):
        from modules.memory import set_store
        set_store(None)
        self.store.close()

    def test_now_se_renderiza_por_turno(self):
        from types import SimpleNamespace
        from modules.llm import LLMEngine

        engine = object.__new__(LLMEngine)
        engine.system_prompt = "Usuario: {username}. Ahora: {now}."
        engine.config = SimpleNamespace(TIMEZONE="", MEMORY_CONTEXT_BYTES=600)

        first = engine._render_system_prompt()
        self.assertNotIn("{now}", first)
        self.assertRegex(first, r"Ahora: \w+ \d{1,2} de \w+ de \d{4}, \d{2}:\d{2}")


if __name__ == "__main__":
    unittest.main()
