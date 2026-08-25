"""
Módulo de control multimedia avanzado.
- Reproducción específica en Spotify (URI nativa) y YouTube (mpv + yt-dlp)
- Letras de la canción actual vía lyrics.ovh
"""

import subprocess
import urllib.request
import urllib.parse
import json
import re
from rich.console import Console

console = Console()


class MediaCommands:

    def get_current_song(self) -> str:
        """Devuelve el artista y título de la canción que está sonando."""
        try:
            result = subprocess.run(
                ["playerctl", "metadata", "--format", "{{artist}} - {{title}}"],
                capture_output=True, text=True, timeout=3
            )
            song = result.stdout.strip()
            if not song or song == " - ":
                return "No hay ninguna canción reproduciéndose ahora mismo."
            return f"Ahora está sonando {song}."
        except Exception:
            return "No pude obtener la canción actual."

    def spotify_play(self, query: str) -> str:
        """
        Busca y reproduce una canción/artista específico en Spotify.
        Usa el esquema URI de Spotify para abrir directamente la búsqueda en la app.
        """
        encoded = urllib.parse.quote(query)
        uri = f"spotify:search:{encoded}"
        console.print(f"[green]🎵 Buscando en Spotify: {query}[/green]")
        try:
            subprocess.Popen(
                ["xdg-open", uri],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            return f"Buscando {query} en Spotify."
        except Exception as e:
            console.print(f"[red]Error al abrir Spotify: {e}[/red]")
            return "No pude abrir Spotify."

    def youtube_play(self, query: str, audio_only: bool = False) -> str:
        """
        Reproduce un video/audio de YouTube directamente con mpv + yt-dlp.
        audio_only=True para reproducir solo el audio (ideal para música).
        """
        console.print(f"[green]▶  Reproduciendo en YouTube: {query}[/green]")
        try:
            cmd = [
                "mpv",
                f"ytdl://ytsearch1:{query}",
                "--no-terminal",
                "--really-quiet",
            ]
            if audio_only:
                cmd += ["--no-video", "--audio-display=no"]

            subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            return f"Reproduciendo {query} desde YouTube."
        except FileNotFoundError:
            return "mpv no está instalado. Instálalo con: sudo pacman -S mpv yt-dlp"
        except Exception as e:
            return f"No pude reproducir: {e}"

    def get_lyrics(self) -> str:
        """
        Obtiene la letra de la canción que está sonando actualmente en Spotify.
        Usa playerctl para el metadato y lyrics.ovh para la letra.
        Lee en voz alta los primeros ~4 versos.
        """
        try:
            # Obtener artista y título actuales
            result = subprocess.run(
                ["playerctl", "metadata", "--format", "{{artist}}|||{{title}}"],
                capture_output=True, text=True, timeout=3
            )
            if result.returncode != 0 or "|||" not in result.stdout:
                return "No hay ninguna canción reproduciéndose ahora mismo."

            parts = result.stdout.strip().split("|||")
            artist = parts[0].strip()
            title = parts[1].strip()

            # Limpiar el título de cosas como "(feat. ...)", "- Remastered", etc.
            title_clean = re.sub(r'\s*[\(\[].*?[\)\]]', '', title).strip()
            title_clean = re.sub(r'\s*-\s*(Remaster|Live|Radio|Official).*', '', title_clean, flags=re.IGNORECASE).strip()

            console.print(f"[green]🎵 Buscando letra: {artist} - {title_clean}[/green]")

            url = f"https://api.lyrics.ovh/v1/{urllib.parse.quote(artist)}/{urllib.parse.quote(title_clean)}"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            response = urllib.request.urlopen(req, timeout=5)
            data = json.loads(response.read().decode("utf-8"))
            lyrics = data.get("lyrics", "")

            if not lyrics:
                return f"No encontré la letra de {title_clean}."

            # Limpiar saltos de línea y tomar los primeros 4-5 versos
            lines = [l.strip() for l in lyrics.splitlines() if l.strip()]
            preview = ". ".join(lines[:5])
            if len(preview) > 400:
                preview = preview[:400].rsplit(".", 1)[0] + "..."

            return f"{title_clean} de {artist}. {preview}"

        except urllib.error.HTTPError:
            return "No encontré la letra de esa canción."
        except Exception as e:
            console.print(f"[red]Error al obtener letra: {e}[/red]")
            return "No pude obtener la letra en este momento."
