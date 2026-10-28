"""Tests de modules/gemini.py — router por palabras clave y puente gemdev.

subprocess totalmente mockeado: sin navegador ni red real.
"""

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from modules.gemini import (
    GeminiBridge,
    _is_hollow_research,
    match_gemini_route,
)


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

    def test_acentos_y_raices(self):
        """Bug real: «investígame» (con tilde) no coincidía y caía a Google."""
        for t in ("investígame sobre el kernel 6.12",
                  "investigame lo de Hyprland",
                  "averigua el precio del dólar",
                  "indaga sobre Wayland",
                  "búscame información sobre el Ryzen 9000",
                  "buscame informacion de la nueva GPU",
                  "googlea precios de SSD",
                  "¿qué se sabe de la RTX 50?"):
            self.assertEqual(match_gemini_route(t)[0], "research", t)

    def test_no_confundir_informacion_con_investigacion(self):
        for t in ("abre google",
                  "muéstrame la información del sistema",
                  "información del disco",
                  "busca el archivo config.py"):
            self.assertIsNone(match_gemini_route(t), t)

    def test_texto_viaja_verbatim(self):
        _, q = match_gemini_route("investiga los últimos avances de fusión nuclear")
        self.assertEqual(q, "investiga los últimos avances de fusión nuclear")


def _proc(stdout: str) -> mock.Mock:
    p = mock.Mock()
    p.stdout = stdout
    p.stderr = ""
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

    @mock.patch("modules.gemini.subprocess.run")
    def test_not_signed_in_fail_loud(self, run):
        with tempfile.TemporaryDirectory() as tmp:
            run.return_value = _proc(json.dumps({
                "ok": False, "err": "NOT_SIGNED_IN",
                "msg": "Gemini Web no está autenticado",
            }))
            out = self._bridge(tmp).chat("investiga X", research=True)
            self.assertIn("gemdev login", out.lower())
            self.assertIn("no pude investigar", out.lower())

    @mock.patch("modules.gemini.subprocess.run")
    def test_research_hueca_tipo_jarvis_fail_loud(self, run):
        with tempfile.TemporaryDirectory() as tmp:
            art = Path(tmp) / "h.md"
            art.write_text("Te comento la situación, warcito.", encoding="utf-8")
            run.return_value = _proc(json.dumps({"ok": True, "f": str(art)}))
            out = self._bridge(tmp, min_research_chars=200).chat(
                "investiga Windows 12", research=True)
            self.assertIn("no pude investigar", out.lower())
            self.assertNotIn("te comento la situación", out.lower())

    @mock.patch("modules.gemini.subprocess.run")
    def test_research_sustancial_pasa(self, run):
        long = (
            "Según Reuters no existe un lanzamiento oficial de Windows 12 en 2026. "
            "Microsoft sigue en el ciclo de Windows 11 con actualizaciones anuales. "
            "La BBC y The Verge coinciden en que los rumores de Windows 12 fueron "
            "malinterpretaciones del programa Windows Next. En cifras, más del "
            "setenta por ciento del mercado de escritorio sigue en Once según "
            "StatCounter. Si aparece un sucesor, Microsoft lo anunciaría en un "
            "evento Build o Surface con fechas concretas, no por filtraciones "
            "sin fuentes. Eso es lo que hay hoy contrastado."
        )
        with tempfile.TemporaryDirectory() as tmp:
            art = Path(tmp) / "ok.md"
            art.write_text(long, encoding="utf-8")
            run.return_value = _proc(json.dumps({"ok": True, "f": str(art)}))
            out = self._bridge(tmp, min_research_chars=200).chat(
                "investiga Windows 12", research=True)
            self.assertIn("Windows", out)
            self.assertGreaterEqual(len(out), 200)


class TestHollowHelper(unittest.TestCase):
    def test_opener_corto_es_hueco(self):
        self.assertTrue(_is_hollow_research(
            "Te comento la situación, warcito.", 200))

    def test_texto_largo_no_es_hueco(self):
        text = ("Según Reuters " + ("dato concreto sobre el tema. " * 20))
        self.assertFalse(_is_hollow_research(text, 200))


if __name__ == "__main__":
    unittest.main()
