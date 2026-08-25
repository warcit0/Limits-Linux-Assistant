"""Comandos de control del sistema operativo."""

import json
import subprocess
import psutil
from rich.console import Console
from commands.apps import AppCommands

console = Console()


class SystemCommands:
    """
    SEGURIDAD: Todos los comandos usan listas de argumentos (NO shell=True con f-strings)
    para prevenir inyección de comandos si el LLM genera parámetros maliciosos.
    """

    def set_volume(self, level: int, mode: str = "absolute") -> None:
        """Establece el volumen del sistema via WirePlumber (wpctl)."""
        if mode == "relative":
            # Ajuste relativo: admite negativos (-10 baja 10%)
            level = int(level)
            sign = "+" if level >= 0 else ""
            subprocess.run(
                ["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", f"{sign}{level}%"],
                check=True,
            )
        else:
            level = max(0, min(100, int(level)))
            subprocess.run(
                ["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", f"{level}%"],
                check=True,
            )

    def get_volume(self) -> str:
        """Obtiene el volumen actual."""
        result = subprocess.run(
            ["wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@"],
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()

    def set_brightness(self, level: int) -> None:
        """Ajusta el brillo de la pantalla via brightnessctl."""
        level = max(0, min(100, int(level)))
        subprocess.run(["brightnessctl", "set", f"{level}%"], check=True)

    def lock_screen(self) -> None:
        """Bloquea la pantalla con hyprlock."""
        subprocess.Popen(["hyprlock"], start_new_session=True)

    def screenshot(self) -> None:
        """Captura de pantalla con flameshot."""
        subprocess.Popen(
            ["flameshot", "gui"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def media_control(self, action: str) -> None:
        """Controla la reproducción multimedia (Spotify, navegadores) via playerctl."""
        valid_actions = {"play": "play", "pause": "pause", "play-pause": "play-pause", "next": "next", "previous": "previous", "stop": "stop"}
        cmd = valid_actions.get(action, "play-pause")
        subprocess.run(["playerctl", cmd], check=False)

    def hyprland_control(self, action: str) -> None:
        """Controles directos del gestor de ventanas Hyprland."""
        if action == "killactive":
            subprocess.run(["hyprctl", "dispatch", "killactive"], check=False)
        elif action == "fullscreen":
            subprocess.run(["hyprctl", "dispatch", "fullscreen"], check=False)

    # Mapa de nombres de voz a clases reales de ventana en Hyprland
    WINDOW_CLASS_MAP = {
        "spotify":      "Spotify",
        "discord":      "discord",
        "chromium":     "chromium",
        "github":       "chrome-mjoklplbddabcmpepnokjaffbmgbkkgg-Default",
        "firefox":      "firefox",
        "code":         "code",
        "vscode":       "code",
        "antigravity":  "antigravity",
        "ghostty":      "com.mitchellh.ghostty",
        "terminal":     "com.mitchellh.ghostty",
        "steam":        "steam",
        "obs":          "com.obsproject.Studio",
        "obsidian":     "obsidian",
        "thunar":       "thunar",
    }

    def focus_window(self, app: str) -> str:
        """Trae al frente una ventana específica por nombre de app usando hyprctl.
        Si la ventana no existe, abre la aplicación."""
        window_class = self.WINDOW_CLASS_MAP.get(app.lower(), app)

        if self._window_exists(window_class):
            subprocess.run(
                ["hyprctl", "dispatch", "focuswindow", f"class:{window_class}"],
                capture_output=True, text=True, check=False
            )
            console.print(f"[green]✓ Foco en ventana: {window_class}[/green]")
            return ""

        # Si no está abierta, abrirla (el response default "Aquí tienes X" sigue siendo válido)
        console.print(f"[yellow]Ventana no encontrada, abriendo {app}...[/yellow]")
        AppCommands().open_app(app)
        return ""

    @staticmethod
    def _window_exists(window_class: str) -> bool:
        """Consulta las ventanas activas de Hyprland y busca la clase (case-insensitive)."""
        try:
            result = subprocess.run(
                ["hyprctl", "clients", "-j"],
                capture_output=True, text=True, timeout=3, check=False
            )
            clients = json.loads(result.stdout) if result.returncode == 0 else []
            return any(
                str(c.get("class", "")).lower() == window_class.lower()
                for c in clients if isinstance(c, dict)
            )
        except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError):
            return False

    def get_info(self, type: str = "all") -> str:
        """Retorna información del sistema en texto para sintetizar."""
        if type == "memory":
            mem = psutil.virtual_memory()
            used_gb = mem.used / (1024 ** 3)
            total_gb = mem.total / (1024 ** 3)
            return f"Usas {used_gb:.1f} GB de {total_gb:.1f} GB, al {mem.percent} por ciento."
        elif type == "cpu":
            cpu = psutil.cpu_percent(interval=1)
            return f"CPU al {cpu} por ciento."
        elif type == "disk":
            disk = psutil.disk_usage("/")
            free_gb = disk.free / (1024 ** 3)
            return f"Tienes {free_gb:.1f} gigabytes libres en disco."
        else:
            mem = psutil.virtual_memory()
            cpu = psutil.cpu_percent(interval=0.5)
            return f"CPU al {cpu} por ciento. RAM al {mem.percent} por ciento."

    def shutdown(self) -> None:
        """Apaga el sistema. Solo ejecutar tras confirmación."""
        subprocess.run(["shutdown", "now"])

    def reboot(self) -> None:
        """Reinicia el sistema. Solo ejecutar tras confirmación."""
        subprocess.run(["reboot"])
