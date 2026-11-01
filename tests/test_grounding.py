"""Grounding determinista (P1): la acción debe responder a la frase.

Casos sacados de la sonda real del 2026-10-28 (ver docs/plan-p1-grounding.md).
"""

import unittest

from modules.grounding import check, fold

# Catálogo reducido a lo que usa cada caso (el real lo inyecta main).
KNOWN = {"get_system_info", "get_time", "set_volume", "spotify_play",
         "media_control", "web_search", "search_file", "open_application",
         "get_current_song", "take_screenshot", "lock_screen", "shutdown"}


class TestNormalizacion(unittest.TestCase):
    def test_fold(self):
        self.assertEqual(fold("¿A qué HORA  abre?"), "¿a que hora abre?")
        self.assertEqual(fold("Canción"), "cancion")


class TestBloqueos(unittest.TestCase):
    """Los fallos medidos: hoy engañan al usuario; deben bloquearse."""

    def test_horario_ajeno_no_es_la_hora(self):
        v = check("get_system_info", {"type": "time"},
                  "¿a qué hora abre el banco?", KNOWN)
        self.assertFalse(v.ok)
        self.assertIn(v.reason, {"sin_evidencia", "fuera_de_dominio"})

    def test_horario_ajeno_tampoco_es_get_time(self):
        v = check("get_time", {"detail": "time"},
                  "¿a qué hora abre el banco?", KNOWN)
        self.assertFalse(v.ok)
        self.assertEqual(v.reason, "fuera_de_dominio")

    def test_accion_inventada(self):
        v = check("media_play", {"type": "relaxing_music"},
                  "ponme música relajante", KNOWN)
        self.assertFalse(v.ok)
        self.assertEqual(v.reason, "accion_desconocida")

    def test_accion_sin_nombre_con_params(self):
        # «estoy cansado» → action ausente + params {app: spotify}
        v = check(None, {"app": "spotify"}, "estoy cansado", KNOWN)
        self.assertFalse(v.ok)
        self.assertEqual(v.reason, "accion_sin_nombre")

    def test_dominio_equivocado(self):
        v = check("web_search", {"query": "qué canción suena"},
                  "¿qué canción suena?", KNOWN)
        self.assertFalse(v.ok)
        self.assertEqual(v.reason, "sin_evidencia")

    def test_parametro_fuera_de_enum(self):
        v = check("media_control", {"action": "rebobinar"},
                  "rebobina la canción", KNOWN)
        self.assertFalse(v.ok)
        self.assertTrue(v.reason.startswith("param_invalido"))


class TestReparaciones(unittest.TestCase):
    def test_free_space_es_disk(self):
        v = check("get_system_info", {"type": "free_space"},
                  "¿cuánto espacio libre me queda?", KNOWN)
        self.assertTrue(v.ok)
        self.assertEqual(v.params["type"], "disk")

    def test_ram_es_memory(self):
        v = check("get_system_info", {"type": "RAM"},
                  "¿cuánta RAM tengo?", KNOWN)
        self.assertTrue(v.ok)
        self.assertEqual(v.params["type"], "memory")

    def test_toggle_es_play_pause(self):
        v = check("media_control", {"action": "toggle"},
                  "pausa la música", KNOWN)
        self.assertTrue(v.ok)
        self.assertEqual(v.params["action"], "play-pause")


class TestClasesDeCharla(unittest.TestCase):
    def test_charla_sin_params_pasa(self):
        for texto in ("¿qué es la fotosíntesis?", "busca las llaves",
                      "tradúceme buenos días al inglés"):
            with self.subTest(texto=texto):
                v = check(None, {}, texto, KNOWN)
                self.assertTrue(v.ok)
                self.assertEqual(v.reason, "chat")


class TestSinFalsosPositivos(unittest.TestCase):
    """Órdenes legítimas del corpus: no pueden bloquearse."""

    CASOS = [
        ("sube el volumen al 70", "set_volume", {"level": 70, "mode": "absolute"}),
        ("¿cuánta RAM tengo?", "get_system_info", {"type": "memory"}),
        ("¿qué hora es?", "get_time", {"detail": "time"}),
        ("¿qué día es hoy?", "get_time", {"detail": "date"}),
        ("pon a Michael Jackson en Spotify", "spotify_play",
         {"query": "Michael Jackson"}),
        ("pausa la música", "media_control", {"action": "pause"}),
        ("¿qué canción suena?", "get_current_song", {}),
        ("busca el archivo config.py", "search_file", {"name": "config.py"}),
        ("abre el navegador", "open_application", {"app": "chromium"}),
        ("haz una captura de pantalla", "take_screenshot", {}),
        ("bloquea la pantalla", "lock_screen", {}),
        ("busca gatos en google", "web_search", {"query": "gatos",
                                                 "engine": "google"}),
    ]

    def test_no_bloquea_ordenes_validas(self):
        for texto, action, params in self.CASOS:
            with self.subTest(texto=texto):
                v = check(action, params, texto, KNOWN)
                self.assertTrue(v.ok, f"{action} bloqueada: {v.reason}")


if __name__ == "__main__":
    unittest.main()
