"""Tests de la capa de voz dual (voice_utils + VoiceRouter + ElevenLabs).

Sin red ni audio real: subprocess y requests van mockeados.
Ejecutar: ./limits-env/bin/python -m unittest discover -s tests -v
"""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from modules.tts import VoiceRouter
from modules.tts_elevenlabs import TTSUnavailable, ElevenLabsEngine
from modules.voice_utils import clean_for_voice, split_for_voice


# ── Utilidades de texto ──────────────────────────────────────────────────────

class TestCleanForVoice(unittest.TestCase):
    def test_quita_fences_y_negritas(self):
        t = "Hola ```python\nprint('x')\n``` mundo **importante** fin"
        out = clean_for_voice(t)
        self.assertNotIn("```", out)
        self.assertNotIn("**", out)
        self.assertIn("importante", out)

    def test_convierte_links_y_urls(self):
        out = clean_for_voice("mira [esto](https://x.com/a) y https://elpais.com/articulo")
        self.assertNotIn("https://", out)
        self.assertIn("esto", out)
        self.assertIn("enlace a elpais.com", out)

    def test_quita_cabeceras_y_bullets(self):
        out = clean_for_voice("# Título\n- punto uno\n* punto dos")
        self.assertNotIn("#", out)
        self.assertNotIn("- punto", out)
        self.assertIn("punto uno", out)

    def test_vacio(self):
        self.assertEqual(clean_for_voice(""), "")
        self.assertEqual(clean_for_voice(None), "")


class TestSplitForVoice(unittest.TestCase):
    def test_corto_sin_division(self):
        first, rest = split_for_voice("Hola mundo.", 100)
        self.assertEqual(first, "Hola mundo.")
        self.assertEqual(rest, "")

    def test_corta_en_limite_de_frase(self):
        t = "Primera frase corta. " + "B " * 30 + ". Última frase final."
        # límite que cae dentro de la segunda frase
        limit = len("Primera frase corta. ") + 10
        first, rest = split_for_voice(t, limit)
        self.assertTrue(first.endswith("."))
        self.assertTrue(len(first) <= limit or "B" not in first.split(".")[1][:1])
        self.assertTrue(rest)

    def test_frase_gigante_corte_duro(self):
        t = "palabra " * 300  # sin puntos
        first, rest = split_for_voice(t, 50)
        self.assertLessEqual(len(first), 60)
        self.assertTrue(rest)

    def test_limite_invalido(self):
        first, rest = split_for_voice("hola", 0)
        self.assertEqual(first, "hola")


# ── Router ───────────────────────────────────────────────────────────────────

class FakeEngine:
    def __init__(self, name):
        self.name = name
        self.spoken = []

    def speak(self, text):
        self.spoken.append(text)


class FailEngine(FakeEngine):
    def speak(self, text):
        raise RuntimeError("boom")


LONG = "Esta es una respuesta larga y desarrollada. " * 8   # > 200 chars limpios
SHORT = "Abriendo Firefox."


class TestVoiceRouter(unittest.TestCase):
    def _router(self, mode="auto", eleven=None, **kw):
        piper = FakeEngine("piper")
        r = VoiceRouter(piper=piper, eleven=eleven, mode=mode,
                        min_chars=kw.pop("min_chars", 50),
                        max_turn_chars=kw.pop("max_turn_chars", 1200))
        return r, piper

    def test_mode_off_siempre_piper(self):
        r, piper = self._router(mode="off", eleven=FakeEngine("e"))
        r.speak(LONG)
        r.speak(SHORT)
        self.assertEqual(len(piper.spoken), 2)

    def test_auto_corto_va_a_piper(self):
        e = FakeEngine("eleven")
        r, piper = self._router(mode="auto", eleven=e)
        r.speak(SHORT)
        self.assertEqual(len(piper.spoken), 1)
        self.assertEqual(e.spoken, [])

    def test_auto_largo_va_a_eleven(self):
        e = FakeEngine("eleven")
        r, piper = self._router(mode="auto", eleven=e)
        r.speak(LONG)
        self.assertEqual(piper.spoken, [])
        self.assertEqual(len(e.spoken), 1)

    def test_gemini_mode_filtra_por_origen(self):
        e = FakeEngine("eleven")
        r, piper = self._router(mode="gemini", eleven=e)
        r.speak(SHORT, source="system")
        self.assertEqual(len(piper.spoken), 1)
        r.speak(SHORT, source="gemini")
        self.assertEqual(len(e.spoken), 1)

    def test_fallback_si_eleven_falla(self):
        e = FailEngine("eleven")
        r, piper = self._router(mode="auto", eleven=e)
        r.speak(LONG)  # no debe lanzar
        self.assertTrue(piper.spoken)  # Piper habló en su lugar

    def test_tope_por_turno_divide(self):
        e = FakeEngine("eleven")
        r, piper = self._router(mode="auto", eleven=e, max_turn_chars=80)
        r.speak(LONG)
        self.assertEqual(len(e.spoken), 1)
        self.assertLessEqual(len(e.spoken[0]), 100)
        self.assertTrue(piper.spoken)  # el resto salió por Piper

    def test_texto_vacio_no_habla_nadie(self):
        e = FakeEngine("eleven")
        r, piper = self._router(mode="auto", eleven=e)
        r.speak("")
        r.speak("   ")
        self.assertEqual(piper.spoken, [])
        self.assertEqual(e.spoken, [])


# ── Motor ElevenLabs (HTTP mockeado) ────────────────────────────────────────

def _resp(status=200, content=b"AUDIO" * 40, ctype="audio/mpeg"):
    m = mock.Mock()
    m.status_code = status
    m.headers = {"content-type": ctype}
    m.content = content
    return m


class TestElevenLabsEngine(unittest.TestCase):
    def _engine(self, tmp, use_cache=True):
        return ElevenLabsEngine(
            api_key="sk_test", voice_id="vid123",
            cache_dir=str(tmp), use_cache=use_cache,
        )

    @mock.patch("modules.tts_elevenlabs.subprocess.run")
    def test_sintetiza_y_reproduce_mpv(self, run):
        with tempfile.TemporaryDirectory() as tmp:
            eng = self._engine(tmp)
            with mock.patch.object(eng._session, "post", return_value=_resp()):
                eng.speak("Frase de prueba suficientemente larga para hablar. " * 3)
            run.assert_called_once()
            self.assertIn("mpv", run.call_args.args[0])

    @mock.patch("modules.tts_elevenlabs.subprocess.run")
    def test_cache_evita_segunda_peticion(self, run):
        with tempfile.TemporaryDirectory() as tmp:
            eng = self._engine(tmp)
            with mock.patch.object(eng._session, "post",
                                   return_value=_resp()) as post:
                eng.speak("Repetido repetido repetido repetido. " * 4)
                eng.speak("Repetido repetido repetido repetido. " * 4)
            self.assertEqual(post.call_count, 1)

    @mock.patch("modules.tts_elevenlabs.subprocess.run")
    def test_fallback_reproductor_ffplay(self, run):
        run.side_effect = [FileNotFoundError, None]
        with tempfile.TemporaryDirectory() as tmp:
            eng = self._engine(tmp, use_cache=False)
            with mock.patch.object(eng._session, "post", return_value=_resp()):
                eng.speak("Probando reproductor alternativo. " * 5)
            self.assertEqual(run.call_count, 2)
            self.assertIn("ffplay", run.call_args.args[0])

    def test_errores_http_elevan_ttsunavailable(self):
        with tempfile.TemporaryDirectory() as tmp:
            eng = self._engine(tmp)
            for status in (401, 402, 429, 500):
                with mock.patch.object(eng._session, "post",
                                       return_value=_resp(status=status)):
                    with self.assertRaises(TTSUnavailable):
                        eng.speak("Texto cualquiera largo. " * 5)

    def test_respuesta_sin_audio_eleva(self):
        with tempfile.TemporaryDirectory() as tmp:
            eng = self._engine(tmp)
            with mock.patch.object(
                    eng._session, "post",
                    return_value=_resp(ctype="application/json")):
                with self.assertRaises(TTSUnavailable):
                    eng.speak("Texto cualquiera largo. " * 5)

    def test_red_caida_eleva(self):
        import requests as _rq
        with tempfile.TemporaryDirectory() as tmp:
            eng = self._engine(tmp)
            with mock.patch.object(eng._session, "post",
                                   side_effect=_rq.ConnectionError("down")):
                with self.assertRaises(TTSUnavailable):
                    eng.speak("Texto cualquiera largo. " * 5)

    def test_vacio_es_noop(self):
        with tempfile.TemporaryDirectory() as tmp:
            eng = self._engine(tmp)
            with mock.patch.object(eng._session, "post") as post:
                eng.speak("")
                eng.speak("   ")
                post.assert_not_called()

    def test_constructor_valida_argumentos(self):
        with self.assertRaises(ValueError):
            ElevenLabsEngine(api_key="", voice_id="x")
        with self.assertRaises(ValueError):
            ElevenLabsEngine(api_key="k", voice_id="")


if __name__ == "__main__":
    unittest.main()
