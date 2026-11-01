"""Tests del router determinista de música (sin LLM)."""

import unittest

from modules.media_router import match_media_route


class TestMediaRouter(unittest.TestCase):
    def test_control_sin_llm(self):
        self.assertEqual(match_media_route("pausa la música")["params"]["action"],
                         "pause")
        self.assertEqual(match_media_route("siguiente")["params"]["action"], "next")
        self.assertEqual(match_media_route("reanuda la música")["params"]["action"],
                         "play")
        self.assertEqual(match_media_route("para la música")["params"]["action"],
                         "stop")

    def test_toda_ruta_trae_texto(self):
        """Nunca vacío: el executor respondería «no te he entendido»."""
        for phrase in ("pausa la música", "siguiente", "reanuda", "para la música",
                       "ponme música relajante", "pon lofi en youtube"):
            route = match_media_route(phrase)
            self.assertTrue(route["response"].strip(), phrase)

    def test_pon_artista_en_spotify(self):
        route = match_media_route("pon a Michael Jackson en Spotify")
        self.assertEqual(route["action"], "spotify_play")
        self.assertEqual(route["params"]["query"], "Michael Jackson")

    def test_ponme_musica_de_genero(self):
        route = match_media_route("ponme música relajante")
        self.assertEqual(route["action"], "spotify_play")
        self.assertEqual(route["params"]["query"], "música relajante")

    def test_youtube(self):
        route = match_media_route("pon lofi en youtube")
        self.assertEqual(route["action"], "youtube_play")
        self.assertEqual(route["params"]["query"], "lofi")

    def test_no_secuestra_otras_ordenes(self):
        self.assertIsNone(match_media_route("pon el volumen al 70"))
        self.assertIsNone(match_media_route("pon spotify en pantalla"))
        self.assertIsNone(match_media_route("pon la mesa"))
        self.assertIsNone(match_media_route("pon música y baja el volumen"))
        self.assertIsNone(match_media_route("¿qué canción suena?"))

    def test_no_controla_barrido_de_palabras(self):
        """«pausa» dentro de una frase larga no es una orden de pausa."""
        self.assertIsNone(match_media_route("pausa el vídeo de la reunión"))


if __name__ == "__main__":
    unittest.main()
