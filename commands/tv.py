"""
Comandos de casting a TV vía Chromecast/Android TV (pychromecast).

Nacen como comandos del executor: funcionan por voz en el PC Y desde el móvil
por el gateway, sin lógica duplicada (docs/plan-control-remoto-android.md §5.2).

Seguridad: solo se castea lo que el pipeline resuelve; archivos locales salen
por el endpoint firmado del gateway (nunca rutas crudas al aire).
"""

import os
import subprocess

from rich.console import Console

console = Console()

# Apps de receptor que usamos según el contenido
APP_DEFAULT_MEDIA = "default_media_receiver"


class TVCommands:

    def __init__(self, media_url_factory=None, discovery_timeout: float = 5.0):
        """
        Args:
            media_url_factory: callable(ruta_local) -> http://LAN/...
                Lo provee el gateway cuando está activo. Si es None, los
                archivos locales devuelven mensaje de ayuda en vez de fallar.
        """
        self.media_url_factory = media_url_factory
        self.discovery_timeout = discovery_timeout
        self._last_tv_name: str | None = None

    # ── Handlers registrados en el action_map ────────────────────────────────

    def list_tvs(self) -> str:
        """Lista las TVs/receptores Chromecast visibles en la red."""
        names = [c.device.friendly_name for c in self._discover()]
        if not names:
            return ("No encontré televisores con Chromecast en la red. "
                    "Verifica que estén encendidos y en el mismo WiFi.")
        return "Televisores encontrados: " + ", ".join(names)

    def tv_cast(self, query: str = "", source: str = "", target: str = "") -> str:
        """
        Castea un video a la TV.
        - source="current": lo que suena/se ve ahora en el PC (playerctl).
        - query="texto": busca en YouTube (yt-dlp) o URL directa si ya es http(s).
        - target: nombre parcial de la TV (vacío = primera encontrada).
        """
        try:
            url, title = self._resolve(query.strip(), source.strip().lower())
        except ValueError as e:
            console.print(f"[yellow]{e}[/yellow]")
            return str(e)

        cast = self._pick(target)
        if cast is None:
            return "No encontré ninguna TV disponible para enviar el video."

        name = getattr(cast.device, "friendly_name", "TV")
        try:
            from pychromecast.quick_play import quick_play
            quick_play(cast, APP_DEFAULT_MEDIA, {"url": url, "title": title})
            self._last_tv_name = name
            console.print(f"[green]✓ Cast a {name}: {title}[/green]")
            return f"Reproduciendo {title} en {name}."
        except Exception as e:
            console.print(f"[red]Error al castear: {e}[/red]")
            return f"No pude enviar el video a {name}."

    def tv_control(self, action: str = "pause") -> str:
        """Controla la reproducción en la última TV usada (o la primera hallada)."""
        valid = {"play", "pause", "stop", "rewind",
                 "volume_up", "volume_down", "volume_mute"}
        action = (action or "").strip().lower()
        if action not in valid:
            return f"Acción de TV no soportada: {action}."

        cast = self._pick_by_name(self._last_tv_name or "")
        if cast is None:
            return "No tengo una TV conectada todavía. Pide primero un cast."

        name = getattr(cast.device, "friendly_name", "TV")
        try:
            mc = cast.media_controller
            if action == "play":
                mc.play()
            elif action == "pause":
                mc.pause()
            elif action == "stop":
                mc.stop()
            elif action == "rewind":
                mc.rewind()
            elif action == "volume_up":
                cast.set_volume(min(1.0, cast.status.volume_level + 0.1))
            elif action == "volume_down":
                cast.set_volume(max(0.0, cast.status.volume_level - 0.1))
            elif action == "volume_mute":
                cast.set_volume_muted(not cast.status.volume_muted)
            return f"Hecho en {name}."
        except Exception as e:
            console.print(f"[red]Error controlando {name}: {e}[/red]")
            return f"No pude controlar {name}."

    # ── Internos ─────────────────────────────────────────────────────────────

    def _discover(self):
        """Devuelve receptores conectados y listos (.wait() aplicado)."""
        import pychromecast
        casts, browser = pychromecast.get_listed_chromecasts(
            discovery_timeout=self.discovery_timeout)
        ready = []
        for c in casts:
            try:
                c.wait(timeout=self.discovery_timeout)
                ready.append(c)
            except Exception:
                continue
        try:
            browser.stop_discovery()
        except Exception:
            pass
        return ready

    def _pick(self, target: str = ""):
        target = (target or "").strip().lower()
        casts = self._discover()
        if not casts:
            return None
        if target:
            for c in casts:
                if target in c.device.friendly_name.lower():
                    return c
        return casts[0]

    def _pick_by_name(self, name: str = ""):
        return self._pick(name)

    def _resolve(self, query: str, source: str) -> tuple[str, str]:
        """Devuelve (url_streamable, título) o ValueError con mensaje hablado."""
        if source in ("current", "actual", "ahora", "viendo", "esto"):
            url = self._current_media_url()
            if not url:
                raise ValueError(
                    "No detecto nada reproduciéndose ahora mismo.")
            return url, self._current_title() or "lo que estabas viendo"

        if query.startswith(("http://", "https://")):
            return query, query.split("//")[-1][:60]

        if not query:
            raise ValueError("¿Qué quieres enviar a la tele?")

        url = self._youtube_stream_url(query)
        if not url:
            raise ValueError(f"No encontré '{query}' en YouTube.")
        return url, query

    @staticmethod
    def _current_media_url() -> str | None:
        try:
            r = subprocess.run(
                ["playerctl", "metadata", "xesam:url"],
                capture_output=True, text=True, timeout=3, check=False)
            out = r.stdout.strip()
            return out if out.startswith(("http://", "https://")) else None
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return None

    @staticmethod
    def _current_title() -> str | None:
        try:
            r = subprocess.run(
                ["playerctl", "metadata", "--format", "{{title}}"],
                capture_output=True, text=True, timeout=3, check=False)
            return r.stdout.strip() or None
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return None

    @staticmethod
    def _youtube_stream_url(query: str) -> str | None:
        try:
            r = subprocess.run(
                ["yt-dlp", "-f", "best[ext=mp4]/best", "--no-playlist",
                 "--get-url", f"ytsearch1:{query}"],
                capture_output=True, text=True, timeout=25, check=False)
            lines = [l for l in r.stdout.splitlines() if l.startswith("http")]
            return lines[0] if lines else None
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return None


def resolve_local_file(path: str, media_url_factory) -> str | None:
    """Convierte una ruta local en URL servible por la TV (o None si imposible)."""
    expanded = os.path.expanduser(path)
    if not os.path.isfile(expanded):
        return None
    if media_url_factory is None:
        return None
    return media_url_factory(expanded)
