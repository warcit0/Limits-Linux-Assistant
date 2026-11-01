"""Comandos para abrir y cerrar aplicaciones."""

import subprocess
import json
import psutil
import time
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
        "spotify":          ["spotify-launcher"],
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
            from modules.command_result import ResultadoComando
            from commands.system import SystemCommands
            limite = time.monotonic()+1.5
            while time.monotonic()<limite:
                try:
                    r = subprocess.run(["hyprctl", "-j", "clients"],capture_output=True,text=True,timeout=1,check=True)
                    if any(SystemCommands.coincide_clase(app, c) for c in json.loads(r.stdout)):
                        return ResultadoComando(f"{app} está abierto; he comprobado su ventana.",ok=True,verificado=True)
                except (OSError, ValueError, TypeError, subprocess.SubprocessError):
                    break
                time.sleep(.1)
            return ResultadoComando(f"He solicitado abrir {app}, pero no he comprobado su ventana.")
        except FileNotFoundError:
            console.print(f"[red]✗ Aplicación '{app}' no encontrada[/red]")
            from modules.command_result import ResultadoComando
            return ResultadoComando(f"No pude abrir {app}: no está instalado.",ok=False)

    def close_app(self, app: str) -> None:
        """Termina procesos o apaga aplicaciones de forma segura."""
        app_lower = app.lower()

        # Cierre seguro para Steam (evita corrupción de archivos)
        if app_lower == "steam":
            subprocess.run(["steam", "-shutdown"],timeout=3,check=True)
            from modules.command_result import ResultadoComando
            return ResultadoComando("He solicitado cerrar Steam; todavía no he comprobado su salida.",ok=True)

        target = self.PROCESS_ALIASES.get(app_lower, app_lower)
        killed = False
        terminados = []
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
                    terminados.append(proc)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        from modules.command_result import ResultadoComando
        if not killed:
            return ResultadoComando(f"No encontré {app} en ejecución; no he cerrado ninguna aplicación.",ok=False)
        _, vivos = psutil.wait_procs(terminados, timeout=2)
        if vivos:
            return ResultadoComando(f"He solicitado cerrar {app}; todavía hay procesos activos.",ok=True)
        return ResultadoComando(f"{app} está cerrado; sus procesos terminaron.",ok=True,verificado=True)

    def list_running(self) -> str:
        """Lista las primeras 10 apps corriendo (por nombre de proceso)."""
        try:
            resultado = subprocess.run(["hyprctl", "-j", "clients"], capture_output=True, text=True, timeout=3, check=True)
            clientes = json.loads(resultado.stdout)
            nombres = sorted({str(c.get("initialClass") or c.get("class") or "Aplicación") for c in clientes if c.get("mapped", True)})
            return "Aplicaciones con ventanas: " + ", ".join(nombres) if nombres else "No hay aplicaciones con ventanas visibles."
        except (OSError, ValueError, subprocess.SubprocessError):
            return "No pude consultar las ventanas de Hyprland; no puedo confirmar las aplicaciones visibles."
