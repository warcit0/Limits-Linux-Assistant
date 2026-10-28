"""Tests de commands/files.py — memoria last_*, excludes, focus mockeado."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from commands.files import FileCommands


class TestFileCommands(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "docs").mkdir()
        (self.root / "docs" / "informe.pdf").write_text("pdf")
        (self.root / "docs" / "notas.txt").write_text("txt")
        (self.root / "otro.txt").write_text("x")
        # basura que debe excluirse
        venv = self.root / "limits-env" / "lib"
        venv.mkdir(parents=True)
        (venv / "config.py").write_text("skip")
        self.fc = FileCommands(
            search_roots=str(self.root),
            search_excludes="limits-env,node_modules,.git",
            focus_delay_s=0.0,
            focus_retries=1,
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_search_file_incluye_rutas_y_memoria(self):
        out = self.fc.search_file("informe", path=str(self.root))
        self.assertIn("informe.pdf", out)
        self.assertTrue(self.fc.last_matches)
        self.assertTrue(self.fc.last_matches[0].endswith("informe.pdf"))

    def test_search_excluye_limits_env(self):
        out = self.fc.search_file("config.py", path=str(self.root))
        self.assertIn("No encontré", out)
        self.assertEqual(self.fc.last_matches, [])

    def test_search_and_open_unico(self):
        # No mockear subprocess.Popen a nivel módulo: rompe fd vía run().
        with mock.patch.object(self.fc, "open_file",
                               return_value="Abrí mock. En pantalla.") as opener:
            out = self.fc.search_and_open("informe.pdf", path=str(self.root))
        self.assertIn("Abrí", out)
        opener.assert_called_once()
        self.assertTrue(opener.call_args[0][0].endswith("informe.pdf"))

    def test_search_and_open_multiples(self):
        with mock.patch.object(self.fc, "open_file") as opener:
            out = self.fc.search_and_open("txt", path=str(self.root))
        self.assertIn("coincidencias", out)
        opener.assert_not_called()
        self.assertGreaterEqual(len(self.fc.last_matches), 2)

    def test_open_last_tras_busqueda(self):
        self.fc.search_file("informe", path=str(self.root))
        real_popen = __import__("subprocess").Popen

        def popen_guard(args, **kwargs):
            if args and args[0] in ("xdg-open", "thunar"):
                return mock.Mock()
            return real_popen(args, **kwargs)

        with mock.patch.object(self.fc, "_focus_opened_path", return_value=False), \
             mock.patch("commands.files.subprocess.Popen", side_effect=popen_guard):
            out = self.fc.open_last(index=1)
        self.assertIn("Abrí", out)
        self.assertIn("otro escritorio", out)

    def test_reveal_last(self):
        self.fc.search_file("informe", path=str(self.root))
        real_popen = __import__("subprocess").Popen

        def popen_guard(args, **kwargs):
            if args and args[0] in ("xdg-open", "thunar"):
                return mock.Mock()
            return real_popen(args, **kwargs)

        with mock.patch.object(self.fc, "_focus_opened_path", return_value=True), \
             mock.patch("commands.files.shutil.which", return_value="/usr/bin/thunar"), \
             mock.patch("commands.files.subprocess.Popen", side_effect=popen_guard) as popen:
            out = self.fc.reveal_last()
        self.assertIn("Mostrando", out)
        self.assertIn("En pantalla", out)
        self.assertTrue(popen.called)

    def test_open_last_sin_memoria(self):
        out = self.fc.open_last()
        self.assertIn("No hay un archivo reciente", out)

    def test_open_last_indice_fuera(self):
        self.fc.search_file("informe", path=str(self.root))
        out = self.fc.open_last(index=9)
        self.assertIn("Solo tengo", out)

    def test_copy_file(self):
        src = str(self.root / "otro.txt")
        dst = str(self.root / "copia.txt")
        out = self.fc.copy_file(src, dst)
        self.assertIn("Copié", out)
        self.assertTrue(Path(dst).is_file())

    def test_move_pide_confirmacion_en_executor(self):
        from modules.executor import CommandExecutor
        ex = CommandExecutor()
        msg = ex.execute({
            "action": "move_file",
            "params": {"source": "~/a", "destination": "~/b"},
            "response": "ok",
            "confidence": 0.99,
        })
        self.assertIn("confirmar", msg.lower())
        self.assertEqual(ex._pending_action["action"], "move_file")

    def test_focus_client_por_titulo(self):
        clients = [
            {"address": "0x1", "class": "Code", "title": "readme.md - Limits",
             "workspace": {"id": 2}},
            {"address": "0x2", "class": "thunar", "title": "informe.pdf",
             "workspace": {"id": 3}},
        ]
        with mock.patch("commands.files.subprocess.run") as run:
            run.return_value = mock.Mock(
                returncode=0, stdout=json.dumps(clients),
            )
            found = FileCommands._find_client(["informe.pdf"], ["thunar"])
        self.assertEqual(found["address"], "0x2")

    def test_focus_client_mueve_workspace(self):
        client = {
            "address": "0xabc", "class": "thunar", "title": "x",
            "workspace": {"id": 9},
        }
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            return mock.Mock(returncode=0, stdout="{}")

        with mock.patch("commands.files.subprocess.run", side_effect=fake_run):
            ok = FileCommands._focus_client(client, workspace_id=1)
        self.assertTrue(ok)
        joined = [" ".join(map(str, c)) for c in calls]
        self.assertTrue(any("movetoworkspacesilent" in j for j in joined))
        self.assertTrue(any("focuswindow" in j and "0xabc" in j for j in joined))

    def test_configure_files_en_executor(self):
        from modules.executor import CommandExecutor
        ex = CommandExecutor()
        ex.configure_files(search_roots=str(self.root),
                           search_excludes="limits-env")
        self.assertIn("open_last", ex.action_map)
        self.assertIn("reveal_last", ex.action_map)
        out = ex.files.search_file("informe")
        self.assertIn("informe", out)


class TestResolucionDeRutas(unittest.TestCase):
    """Bug real: "lista los proyectos de la carpeta work" → no existía 'work'.

    Las rutas del asistente deben resolverse contra $HOME y tolerando
    mayúsculas/acentos, porque el LLM (y la voz) no respetan la caja.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        (self.home / "Work" / "Proyectos" / "Limits").mkdir(parents=True)
        (self.home / "Work" / "Limits").mkdir(parents=True)
        (self.home / "Work" / "Limits" / "README.md").write_text("x")
        (self.home / "Descargas").mkdir()
        (self.home / "Documentos").mkdir()
        (self.home / ".config").mkdir()
        self._env = mock.patch.dict(os.environ, {"HOME": str(self.home)})
        self._env.start()
        self.fc = FileCommands(search_roots=str(self.home), focus_delay_s=0.0,
                              focus_retries=1)

    def tearDown(self):
        self._env.stop()
        self.tmp.cleanup()

    def test_relativa_se_resuelve_contra_home(self):
        from commands.files import _expand
        self.assertEqual(_expand("work"), str(self.home / "work"))

    def test_list_directory_tolera_mayusculas(self):
        out = self.fc.list_directory("work")
        self.assertIn("Proyectos", out)
        self.assertIn("Limits", out)

    def test_list_directory_tolera_acentos_y_anidamiento(self):
        # "documentos" sin tilde debe caer en ~/Documentos
        self.assertIn("vacío", self.fc.list_directory("documentos"))
        out = self.fc.list_directory("work/limits")
        self.assertIn("README.md", out)

    def test_list_directory_sugiere_si_no_existe(self):
        out = self.fc.list_directory("Descarga")
        self.assertIn("No encontré", out)
        self.assertIn("Descargas", out)   # sugerencia, no invención

    def test_list_directory_oculta_dotfiles(self):
        out = self.fc.list_directory("~")
        self.assertNotIn(".config", out)

    def test_copy_resuelve_destino_con_caja(self):
        src = str(self.home / "Work" / "Limits" / "README.md")
        out = self.fc.copy_file(src, "~/descargas/readme-copia.md")
        self.assertIn("Copié", out)
        self.assertTrue((self.home / "Descargas" / "readme-copia.md").is_file())

    def test_open_file_resuelve_caja(self):
        with mock.patch.object(self.fc, "_focus_opened_path", return_value=False), \
                mock.patch("commands.files.subprocess.Popen") as popen:
            out = self.fc.open_file("~/work/limits/readme.md")
        self.assertIn("Abrí", out)
        self.assertIn("README.md", out)
        self.assertTrue(popen.called)

    def test_search_file_acepta_carpeta_con_caja_distinta(self):
        out = self.fc.search_file("README", path="~/work/limits")
        self.assertIn("README.md", out)


if __name__ == "__main__":
    unittest.main()
