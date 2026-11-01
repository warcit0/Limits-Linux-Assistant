"""Elección de reproductor MPRIS y control multimedia.

Bug real (2026-10-28): «reanuda la reproducción de spotify» desde el móvil
respondía «reanudando» pero no sonaba nada. Con Spotify + Firefox abiertos,
`playerctl` a secas controlaba la PRIMERA entrada MPRIS (una pestaña de
WhatsApp Web en Firefox) y el handler no comprobaba el resultado.
"""

import unittest
from unittest.mock import patch

from commands import media as media_mod
from commands.media import pick_player
from commands.system import SystemCommands


class FakeProc:
    def __init__(self, stdout="", stderr="", returncode=0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


def playerctl_fake(players, statuses=None, action_rc=0, action_err=""):
    """Devuelve un subprocess.run falso para playerctl."""
    statuses = statuses or {}

    def run(cmd, **kwargs):
        if cmd[:2] == ["playerctl", "-l"]:
            return FakeProc(stdout="\n".join(players) + "\n")
        if "status" in cmd:
            name = cmd[cmd.index("--player") + 1]
            return FakeProc(stdout=statuses.get(name, "Paused"))
        # acción sobre un reproductor
        return FakeProc(stderr=action_err, returncode=action_rc)

    return run


class TestPickPlayer(unittest.TestCase):
    def test_prefer_spotify_entre_varios(self):
        run = playerctl_fake(["firefox.instance_1_59", "spotify"])
        with patch.object(media_mod.subprocess, "run", side_effect=run):
            self.assertEqual(pick_player("spotify"), "spotify")

    def test_prefer_inexistente_devuelve_none(self):
        run = playerctl_fake(["firefox.instance_1_59"])
        with patch.object(media_mod.subprocess, "run", side_effect=run):
            self.assertIsNone(pick_player("spotify"))

    def test_sin_preferencia_gana_el_que_suena(self):
        run = playerctl_fake(
            ["firefox.instance_1_59", "spotify"],
            statuses={"firefox.instance_1_59": "Playing", "spotify": "Paused"},
        )
        with patch.object(media_mod.subprocess, "run", side_effect=run):
            self.assertEqual(pick_player(), "firefox.instance_1_59")

    def test_sin_nada_sonando_prefiere_spotify(self):
        run = playerctl_fake(["firefox.instance_1_59", "spotify"])
        with patch.object(media_mod.subprocess, "run", side_effect=run):
            self.assertEqual(pick_player(), "spotify")

    def test_sin_reproductores(self):
        run = playerctl_fake([])
        with patch.object(media_mod.subprocess, "run", side_effect=run):
            self.assertIsNone(pick_player())


class TestMediaControl(unittest.TestCase):
    def setUp(self):
        self.sys = SystemCommands.__new__(SystemCommands)  # sin __init__

    def test_play_en_spotify_usa_el_player_explicito(self):
        calls = []
        run = playerctl_fake(["firefox.instance_1_59", "spotify"])

        def spy(cmd, **kwargs):
            calls.append(cmd)
            return run(cmd, **kwargs)

        with patch.object(media_mod.subprocess, "run", side_effect=spy), \
                patch("commands.system.subprocess.run", side_effect=spy), \
                patch("commands.system.console"):
            out = self.sys.media_control("play", "spotify")

        self.assertEqual(out, "")
        self.assertIn(["playerctl", "--player", "spotify", "play"], calls)
        self.assertNotIn(["playerctl", "play"], calls)

    def test_spotify_cerrado_no_dice_que_reanudo(self):
        run = playerctl_fake(["firefox.instance_1_59"])
        with patch.object(media_mod.subprocess, "run", side_effect=run), \
                patch("commands.system.subprocess.run", side_effect=run):
            out = self.sys.media_control("play", "spotify")
        self.assertIn("No encuentro spotify", out)

    def test_error_de_playerctl_se_reporta(self):
        run = playerctl_fake(["spotify"], action_rc=1,
                             action_err="No player could handle this command")
        with patch.object(media_mod.subprocess, "run", side_effect=run), \
                patch("commands.system.subprocess.run", side_effect=run), \
                patch("commands.system.console"):
            out = self.sys.media_control("play", "spotify")
        self.assertIn("No pude play", out)
        self.assertIn("No player could handle", out)

    def test_accion_invalida_cae_en_play_pause(self):
        calls = []
        run = playerctl_fake(["spotify"])

        def spy(cmd, **kwargs):
            calls.append(cmd)
            return run(cmd, **kwargs)

        with patch.object(media_mod.subprocess, "run", side_effect=spy), \
                patch("commands.system.subprocess.run", side_effect=spy), \
                patch("commands.system.console"):
            self.sys.media_control("borrar_todo", None)

        self.assertIn(["playerctl", "--player", "spotify", "play-pause"], calls)


if __name__ == "__main__":
    unittest.main()
