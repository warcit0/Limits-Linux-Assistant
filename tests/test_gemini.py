"""Tests de modules/gemini.py — router por palabras clave y puente gemdev.

subprocess totalmente mockeado: sin navegador ni red real.
"""

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from modules.gemini import GeminiBridge, match_gemini_route


class TestRouterPalabrasClave(unittest.TestCase):
    def test_investiga_va_a_research(self):
        self.assertEqual(match_gemini_route("investiga qué pasó con X")[0], "research")

    def test_infomame_y_variantes(self):
        for t in ("infórmame del clima", "informame sobre IA",
                  "infórmate de las noticias"):
            self.assertEqual(match_gemini_route(t)[0], "research", t)

    def test_busca_compuesto_si_pero_solo_no(self):
        self.assertEqual(match_gemini_route("busca en internet gatos")[0], "research")
        self.assertEqual(match_gemini_route("búscame en la web el precio")[0], "research")
        # "busca" sola NO es investigación web
        self.assertIsNone(match_gemini_route("busca el archivo config.py"))

    def test_gemini_prefijo_es_talk(self):
        mode, _ = match_gemini_route("gemini, cuéntame un chiste")
        self.assertEqual(mode, "talk")
        mode, _ = match_gemini_route("pregúntale a gemini quién es Tesla")
        self.assertEqual(mode, "talk")

    def test_comandos_normales_no_rutean(self):
        for t in ("abre firefox", "volumen al 80", "qué RAM estoy usando",
                  "pon cumbia en spotify", ""):
            self.assertIsNone(match_gemini_route(t), t)

    def test_texto_viaja_verbatim(self):
        _, q = match_gemini_route("investiga los últimos avances de fusión nuclear")
        self.assertEqual(q, "investiga los últimos avances de fusión nuclear")


def _proc(stdout: str) -> mock.Mock:
    p = mock.Mock()
    p.stdout = stdout
    p.returncode = 0
    return p


class TestGeminiBridge(unittest.TestCase):
    def _bridge(self, tmp, **kw):
        return GeminiBridge(gemini_bin="gemdev-fake", timeout_s=60,
                            session_file=str(Path(tmp) / "sess.json"), **kw)

    def test_available_comprueba_binario(self):
        b = self._bridge("/tmp")
        self.assertFalse(b.available())
        b2 = GeminiBridge(gemini_bin="/bin/true")
        self.assertTrue(b2.available())

    @mock.patch("modules.gemini.subprocess.run")
    def test_turno_exitoso_lee_artefacto(self, run):
        with tempfile.TemporaryDirectory() as tmp:
            art = Path(tmp) / "out.md"
            art.write_text("Hola **mundo**, todo *bien*.", encoding="utf-8")
            pointer = json.dumps({"ok": True, "f": str(art),
                                  "url": "https://x", "elapsed": 6.0})
            run.return_value = _proc(f"[gemdev] 1 ventana(s)\n{pointer}\n")

            out = self._bridge(tmp).chat("hola")
            self.assertEqual(out, "Hola mundo, todo bien.")
            cmd = run.call_args.args[0]
            self.assertIn("-t", cmd)
            self.assertIn("--json", cmd)
            # siempre pasa -c de sesión
            self.assertIn("-c", cmd)

    @mock.patch("modules.gemini.subprocess.run")
    def test_research_inserta_modo_investigacion(self, run):
        with tempfile.TemporaryDirectory() as tmp:
            art = Path(tmp) / "o.md"
            art.write_text("Según Reuters…", encoding="utf-8")
            run.return_value = _proc(json.dumps(
                {"ok": True, "f": str(art)}))
            self._bridge(tmp).chat("novedades de cohetes", research=True)
            prompt = run.call_args.args[0][-1]
            self.assertIn("MODO INVESTIGACIÓN", prompt)

    @mock.patch("modules.gemini.subprocess.run")
    def test_error_locked_da_frase_amable(self, run):
        with tempfile.TemporaryDirectory() as tmp:
            run.return_value = _proc(json.dumps(
                {"ok": False, "err": "LOCKED", "msg": "busy"}))
            out = self._bridge(tmp).chat("hola")
            self.assertIn("ocupado", out.lower())

    @mock.patch("modules.gemini.subprocess.run")
    def test_timeout_devuelve_frase(self, run):
        run.side_effect = subprocess.TimeoutExpired(cmd="x", timeout=90)
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIn("tardó demasiado", self._bridge(tmp).chat("hola"))

    @mock.patch("modules.gemini.subprocess.run")
    def test_salida_basura_devuelve_inesperado(self, run):
        run.return_value = _proc("no hay json aquí")
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIn("inesperado", self._bridge(tmp).chat("hola").lower())

    @mock.patch("modules.gemini.subprocess.run")
    def test_respuesta_vacia_avisa(self, run):
        with tempfile.TemporaryDirectory() as tmp:
            art = Path(tmp) / "v.md"
            art.write_text("", encoding="utf-8")
            run.return_value = _proc(json.dumps({"ok": True, "f": str(art)}))
            self.assertIn("vacía", self._bridge(tmp).chat("hola"))


if __name__ == "__main__":
    unittest.main()
