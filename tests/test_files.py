"""Tests de commands/files.py — sin xdg-open/thunar reales (mock Popen)."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from commands.files import FileCommands


class TestFileCommands(unittest.TestCase):
    def setUp(self):
        self.fc = FileCommands()
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "docs").mkdir()
        (self.root / "docs" / "informe.pdf").write_text("pdf")
        (self.root / "docs" / "notas.txt").write_text("txt")
        (self.root / "otro.txt").write_text("x")

    def tearDown(self):
        self.tmp.cleanup()

    def test_search_file_incluye_rutas(self):
        out = self.fc.search_file("informe", path=str(self.root))
        self.assertIn("informe.pdf", out)
        self.assertIn("1 resultado", out)

    def test_search_file_sin_match(self):
        out = self.fc.search_file("zzz_no_existe", path=str(self.root))
        self.assertIn("No encontré", out)

    def test_search_and_open_unico(self):
        with mock.patch.object(self.fc, "open_file",
                               return_value="Abriendo mock.") as opener:
            out = self.fc.search_and_open("informe.pdf", path=str(self.root))
        self.assertIn("Abrí", out)
        opener.assert_called_once()
        self.assertTrue(opener.call_args[0][0].endswith("informe.pdf"))

    def test_search_and_open_multiples(self):
        # "txt" matchea notas.txt y otro.txt
        with mock.patch.object(self.fc, "open_file") as opener:
            out = self.fc.search_and_open("txt", path=str(self.root))
        self.assertIn("coincidencias", out)
        opener.assert_not_called()

    def test_open_file(self):
        target = str(self.root / "otro.txt")
        with mock.patch("commands.files.subprocess.Popen") as popen:
            # Popen mockeado rompe subprocess.run; open_file solo usa Popen
            out = self.fc.open_file(target)
        self.assertIn("Abriendo", out)
        popen.assert_called_once()

    def test_open_file_inexistente(self):
        out = self.fc.open_file(str(self.root / "nope.txt"))
        self.assertIn("No encontré", out)

    def test_reveal_file_path(self):
        target = str(self.root / "docs" / "informe.pdf")
        with mock.patch("commands.files.shutil.which",
                        return_value="/usr/bin/thunar"), \
             mock.patch("commands.files.subprocess.Popen") as popen:
            out = self.fc.reveal_file(path=target)
        self.assertIn("Mostrando", out)
        popen.assert_called_once()
        self.assertEqual(popen.call_args[0][0][0], "thunar")

    def test_copy_file(self):
        src = str(self.root / "otro.txt")
        dst = str(self.root / "copia.txt")
        out = self.fc.copy_file(src, dst)
        self.assertIn("Copié", out)
        self.assertTrue(Path(dst).is_file())

    def test_copy_file_no_overwrite(self):
        src = str(self.root / "otro.txt")
        dst = str(self.root / "docs" / "notas.txt")
        out = self.fc.copy_file(src, dst)
        self.assertIn("ya existe", out)

    def test_move_file(self):
        src = str(self.root / "otro.txt")
        dst = str(self.root / "docs" / "movido.txt")
        out = self.fc.move_file(src, dst)
        self.assertIn("Moví", out)
        self.assertFalse(Path(src).exists())
        self.assertTrue(Path(dst).is_file())

    def test_rename_file(self):
        src = str(self.root / "otro.txt")
        out = self.fc.rename_file(src, "renombrado.txt")
        self.assertIn("Renombré", out)
        self.assertTrue((self.root / "renombrado.txt").is_file())

    def test_rename_rechaza_separador(self):
        src = str(self.root / "otro.txt")
        out = self.fc.rename_file(src, "subdir/x.txt")
        self.assertIn("no es válido", out)


class TestExecutorFileDanger(unittest.TestCase):
    def test_move_pide_confirmacion(self):
        from modules.executor import CommandExecutor
        ex = CommandExecutor()
        msg = ex.execute({
            "action": "move_file",
            "params": {"source": "~/a", "destination": "~/b"},
            "response": "ok",
            "confidence": 0.99,
        })
        self.assertIn("confirmar", msg.lower())
        self.assertIsNotNone(ex._pending_action)
        self.assertEqual(ex._pending_action["action"], "move_file")


if __name__ == "__main__":
    unittest.main()
