"""Tests de modules/quick_routes.py — hora/fecha sin LLM."""

import unittest

from modules.quick_routes import match_quick_route


class TestQuickRoutes(unittest.TestCase):
    def _detail(self, text):
        route = match_quick_route(text)
        return None if route is None else route["params"]["detail"]

    def test_hora(self):
        for frase in ("¿qué hora es?", "qué hora son", "dime la hora",
                      "la hora", "¿qué hora tienes?"):
            self.assertEqual(self._detail(frase), "time", frase)

    def test_fecha(self):
        for frase in ("¿qué día es hoy?", "¿a qué día estamos?",
                      "¿qué fecha es hoy?", "a qué estamos"):
            self.assertEqual(self._detail(frase), "date", frase)

    def test_dia_de_la_semana(self):
        self.assertEqual(self._detail("¿qué día de la semana es?"), "weekday")

    def test_no_secuestra_horarios_ajenos(self):
        for frase in ("¿a qué hora abre el banco?",
                      "¿a qué hora cierra la tienda?",
                      "¿a qué hora sale el tren?",
                      "pon una alarma a las 7"):
            self.assertIsNone(match_quick_route(frase), frase)

    def test_no_secuestra_otras_ordenes(self):
        for frase in ("abre spotify", "lista la carpeta work", "pausa la música",
                      "investiga sobre la hora dorada"):
            self.assertIsNone(match_quick_route(frase), frase)

    def test_ejecuta_y_devuelve_texto(self):
        from modules.executor import CommandExecutor
        route = match_quick_route("¿qué hora es?")
        out = CommandExecutor().execute(route)
        self.assertRegex(out, r"^Son las \d{2}:\d{2}\.$")


if __name__ == "__main__":
    unittest.main()
