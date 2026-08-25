"""Comandos para abrir y cerrar aplicaciones."""

import subprocess
import psutil
from rich.console import Console

console = Console()


class AppCommands:
    APP_MAP = {
        "firefox":          ["firefox"],
        "chromium":         ["chromium"],
        "ghostty":          ["ghostty"],
        "code":             ["code"],
        "vscode":           ["code"],
        "steam":            ["steam"],
        "spotify":          ["spotify"],
        "discord":          ["discord"],
        "slack":            ["slack"],
        "obsidian":         ["obsidian"],
        "github":           ["chromium", "--profile-directory=Default", "--app-id=mjoklplbddabcmpepnokjaffbmgbkkgg"],
        "antigravity":      ["code", "/home/warcito/.gemini/antigravity"],
        "thunar":           ["thunar"],
        "nvim":             ["ghostty", "-e", "nvim"],
        "neovim":           ["ghostty", "-e", "nvim"],
        "lazygit":          ["ghostty", "-e", "lazygit"],
        "htop":             ["ghostty", "-e", "htop"],
        "bruno":            ["bruno"],
        "tableplus":        ["tableplus"],
        "figma-linux":      ["figma-linux"],
        "gnome-calculator": ["gnome-calculator"],
        "flameshot":        ["flameshot", "gui"],
        "obs":              ["obs"],
    }

    # Nombres coloquiales → nombre real del proceso en el sistema
    PROCESS_ALIASES = {
        "vscode":             "code",
        "vs code":            "code",
        "visual studio code": "code",
        "editor":             "code",
        "terminal":           "ghostty",
        "neovim":             "nvim",
    }

    def open_app(self, app: str, args: list = None) -> None:
        """Abre una aplicación. args=None corrige el bug de mutable default."""
        args = args or []
        cmd = self.APP_MAP.get(app.lower(), [app]) + args
        try:
            subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            console.print(f"[green]✓ Abriendo {app}[/green]")
        except FileNotFoundError:
            console.print(f"[red]✗ Aplicación '{app}' no encontrada[/red]")

    def close_app(self, app: str) -> None:
        """Termina procesos o apaga aplicaciones de forma segura."""
        app_lower = app.lower()

        # Cierre seguro para Steam (evita corrupción de archivos)
        if app_lower == "steam":
            subprocess.run(["steam", "-shutdown"])
            console.print("[green]✓ Apagando Steam correctamente[/green]")
            return

        target = self.PROCESS_ALIASES.get(app_lower, app_lower)
        killed = False
        for proc in psutil.process_iter(["pid", "name"]):
            try:
                name = (proc.info["name"] or "").lower()
                # Match exacto o por prefijo con separador; evita falsos
                # positivos como matar "qrcode-gen" al pedir cerrar "code"
                if (
                    name == target
                    or name.startswith(target + "-")
                    or name.startswith(target + ".")
                ):
                    proc.terminate()
                    killed = True
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        if not killed:
            console.print(f"[yellow]'{app}' no estaba corriendo[/yellow]")

    def list_running(self) -> str:
        """Lista las primeras 10 apps corriendo (por nombre de proceso)."""
        apps = set()
        for proc in psutil.process_iter(["name"]):
            try:
                apps.add(proc.info["name"])
            except psutil.NoSuchProcess:
                pass
        top = sorted(apps)[:10]
        return ", ".join(top)
