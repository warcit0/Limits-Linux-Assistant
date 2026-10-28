"""Tests de resolución de proyectos por nombre (open_project sin rutas)."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from commands.dev import DevCommands


class TestResolveProject(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        (self.home / "Proyectos" / "Limits").mkdir(parents=True)
        (self.home / "Work" / "WebAi-to-local-CLI-LLM").mkdir(parents=True)
        self._env = mock.patch.dict(os.environ, {"HOME": str(self.home)})
        self._env.start()
        self.dev = DevCommands()

    def tearDown(self):
        self._env.stop()
        self.tmp.cleanup()

    def test_nombre_solo(self):
        self.assertEqual(self.dev._resolve_project("limits"),
                         str(self.home / "Proyectos" / "Limits"))

    def test_nombre_en_otra_raiz_y_con_caja(self):
        self.assertEqual(self.dev._resolve_project("webai-to-local-cli-llm"),
                         str(self.home / "Work" / "WebAi-to-local-CLI-LLM"))

    def test_ruta_completa(self):
        self.assertEqual(self.dev._resolve_project("~/work/webai-to-local-cli-llm"),
                         str(self.home / "Work" / "WebAi-to-local-CLI-LLM"))

    def test_inexistente(self):
        self.assertIsNone(self.dev._resolve_project("no-existe"))

    def test_open_project_avisa_sin_lanzar_proceso(self):
        with mock.patch("commands.dev.subprocess.Popen") as popen:
            out = self.dev.open_project("no-existe")
        self.assertIn("No encontré", out)
        self.assertFalse(popen.called)

    def test_open_project_lanza_editor(self):
        with mock.patch("commands.dev.subprocess.Popen") as popen:
            out = self.dev.open_project("limits", editor="code")
        self.assertIsNone(out)
        self.assertEqual(popen.call_args.args[0][0], "code")


if __name__ == "__main__":
    unittest.main()
