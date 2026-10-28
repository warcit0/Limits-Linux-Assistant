"""Tests del router determinista de archivos (sin LLM)."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from modules.file_router import match_file_route


class TestFileRouter(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        (self.home / "Work" / "Proyectos" / "Limits").mkdir(parents=True)
        (self.home / "Work" / "Treecodes").mkdir()
        (self.home / "Proyectos" / "Nolimitz").mkdir(parents=True)
        (self.home / "Descargas").mkdir()
        (self.home / "Música").mkdir()
        (self.home / "Documentos").mkdir()
        self._env = mock.patch.dict(os.environ, {"HOME": str(self.home)})
        self._env.start()

    def tearDown(self):
        self._env.stop()
        self.tmp.cleanup()

    def _path(self, text):
        route = match_file_route(text)
        return None if route is None else route["params"]["path"]

    def test_caso_real_carpeta_work(self):
        route = match_file_route("lista los proyectos de la carpeta work")
        self.assertIsNotNone(route)
        self.assertEqual(route["action"], "list_directory")
        self.assertEqual(route["params"]["path"], str(self.home / "Work"))

    def test_carpeta_con_caja_y_acentos(self):
        self.assertEqual(self._path("qué hay en descargas"),
                         str(self.home / "Descargas"))
        self.assertEqual(self._path("lista la carpeta musica"),
                         str(self.home / "Música"))
        self.assertEqual(self._path("muéstrame el contenido de la carpeta DE work"),
                         str(self.home / "Work"))

    def test_ruta_absoluta_y_anidada(self):
        self.assertEqual(self._path("lista el contenido de ~/work/proyectos"),
                         str(self.home / "Work" / "Proyectos"))

    def test_reveal_solo_si_es_mostrar_carpeta(self):
        route = match_file_route("muéstrame la carpeta work")
        self.assertEqual(route["action"], "reveal_file")
        self.assertEqual(route["params"]["path"], str(self.home / "Work"))

    def test_no_secuestra_otras_ordenes(self):
        for frase in (
            "lista los procesos",
            "lista las apps abiertas",
            "busca el informe de la carpeta work",
            "muéstrame el informe de descargas",
            "abre spotify",
            "pausa la música",
            "qué hora es",
        ):
            self.assertIsNone(match_file_route(frase), frase)

    def test_ruta_inexistente_deja_paso_al_llm(self):
        self.assertIsNone(match_file_route("lista los proyectos de la carpeta inventada"))

    def test_proyectos_sin_ruta_explicita(self):
        route = match_file_route("¿qué proyectos tengo?")
        self.assertEqual(route["params"]["path"], str(self.home / "Proyectos"))
        self.assertEqual(match_file_route("lista todos los proyectos")["action"],
                         "list_directory")

    def test_ejecuta_de_verdad_listando(self):
        from modules.executor import CommandExecutor
        route = match_file_route("lista los proyectos de la carpeta work")
        out = CommandExecutor().execute(route)
        self.assertIn("Proyectos", out)
        self.assertIn("Treecodes", out)


if __name__ == "__main__":
    unittest.main()
