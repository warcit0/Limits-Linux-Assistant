"""Tests del router determinista de apps (sin LLM)."""

import unittest

from modules.app_router import match_app_route


class TestAppRouter(unittest.TestCase):
    def test_abre_app_conocida(self):
        route = match_app_route("abre discord")
        self.assertEqual(route["action"], "open_application")
        self.assertEqual(route["params"]["app"], "discord")

    def test_cierra_app(self):
        self.assertEqual(match_app_route("cierra spotify")["action"],
                         "close_application")
        self.assertEqual(match_app_route("mata spotify")["params"]["app"], "spotify")

    def test_alias_coloquiales(self):
        self.assertEqual(match_app_route("abre el navegador")["params"]["app"],
                         "chromium")
        self.assertEqual(match_app_route("abre la terminal")["params"]["app"],
                         "ghostty")
        self.assertEqual(match_app_route("abre el editor")["params"]["app"], "code")

    def test_foco_en_pantalla(self):
        route = match_app_route("pon spotify en pantalla")
        self.assertEqual(route["action"], "focus_window")
        self.assertEqual(route["params"]["app"], "spotify")
        self.assertEqual(match_app_route("trae Discord al frente")["action"],
                         "focus_window")

    def test_no_secuestra_archivos_ni_compuestas(self):
        self.assertIsNone(match_app_route("abre el archivo README.md"))
        self.assertIsNone(match_app_route("abre la carpeta Descargas"))
        self.assertIsNone(match_app_route("abre spotify y pon música"))
        self.assertIsNone(match_app_route("busca config.py en Proyectos"))

    def test_app_desconocida_deja_paso_al_llm(self):
        self.assertIsNone(match_app_route("abre mi invento raro"))

    def test_no_confunde_poner_en_pantalla_una_cosa_cualquiera(self):
        self.assertIsNone(match_app_route("pon la música en pantalla"))


if __name__ == "__main__":
    unittest.main()
