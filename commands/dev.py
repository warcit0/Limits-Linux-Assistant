"""
Comandos de desarrollo: git, docker, terminal, proyectos.

SEGURIDAD: run_command usa una allowlist de comandos seguros.
Comandos destructivos (rm, sudo, etc.) nunca se ejecutan directamente.
"""

import subprocess
import os
from rich.console import Console

console = Console()

# Allowlist de comandos de terminal seguros (sin parámetros destructivos).
# NOTA: sin "curl" (exfiltración de datos) ni "cat" (lectura de archivos
# privados que se leerían en voz alta). El match exige límite de palabra.
SAFE_COMMANDS = {
    "git status",
    "git log",
    "git diff",
    "git branch",
    "git fetch",
    "docker ps",
    "docker images",
    "docker stats",
    "docker logs",
    "ls",
    "pwd",
    "df -h",
    "free -h",
    "top",
    "htop",
    "ping",
    "echo",
    "whoami",
    "uname",
    "uptime",
}


class DevCommands:
    def run_command(self, command: str, show_output: bool = False) -> str:
        """
        Ejecuta un comando de terminal dentro de la allowlist de comandos seguros.
        Args:
            command:     Comando a ejecutar (debe comenzar con un prefijo seguro)
            show_output: Si True, abre una terminal mostrando la salida
        Returns:
            Output del comando como string (primeras 5 líneas)
        """
        # Verificar que el comando es seguro (límite de palabra: evita que
        # "catalog..." matchee "ca...", o que "git statusx" matchee "git status")
        cmd_lower = command.strip().lower()
        is_safe = any(
            cmd_lower == safe or cmd_lower.startswith(safe + " ")
            for safe in SAFE_COMMANDS
        )

        if not is_safe:
            console.print(f"[red]⚠️  Comando bloqueado por seguridad: '{command}'[/red]")
            return "Ese comando no está permitido por razones de seguridad."

        if show_output:
            # Abrir en terminal visible para que el usuario vea la salida
            subprocess.Popen(
                ["ghostty", "-e", "bash", "-c", f"{command}; read -p 'Presiona Enter para cerrar'"],
                start_new_session=True,
            )
            return ""
        else:
            try:
                result = subprocess.run(
                    command.split(),
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                lines = result.stdout.strip().splitlines()[:5]
                return " | ".join(lines) if lines else result.stderr.strip()[:100]
            except subprocess.TimeoutExpired:
                return "El comando tardó demasiado."
            except Exception as e:
                return f"Error: {e}"

    def git_status(self) -> str:
        """Muestra el estado de git en el directorio actual."""
        try:
            result = subprocess.run(
                ["git", "status", "--short"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            output = result.stdout.strip()
            if not output:
                return "El repositorio está limpio, sin cambios."
            lines = output.splitlines()
            return f"{len(lines)} archivo(s) modificado(s)."
        except Exception:
            return "No estás en un repositorio git."

    def docker_status(self) -> str:
        """Muestra el estado de los contenedores Docker."""
        try:
            result = subprocess.run(
                ["docker", "ps", "--format", "{{.Names}}: {{.Status}}"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            output = result.stdout.strip()
            if not output:
                return "No hay contenedores corriendo."
            lines = output.splitlines()[:3]
            return f"{len(lines)} contenedor(es) activo(s): " + ", ".join(
                line.split(":")[0] for line in lines
            )
        except FileNotFoundError:
            return "Docker no está instalado."
        except Exception as e:
            return f"Error al consultar Docker: {e}"

    def _resolve_project(self, path: str) -> str | None:
        """
        Acepta ruta, ~/ruta o solo el nombre del proyecto ("limits").
        Tolera mayúsculas/acentos y busca en las carpetas de proyectos.
        """
        from commands.files import _resolve_existing

        direct = _resolve_existing(path)
        if direct and os.path.isdir(direct):
            return direct
        for root in ("~/Proyectos", "~/Work", "~/Projects", "~/Trabajo",
                     "~/Repos", "~/Documentos", "~/Escritorio"):
            base = _resolve_existing(root)
            if not base or not os.path.isdir(base):
                continue
            found = _resolve_existing(os.path.join(base, path))
            if found and os.path.isdir(found):
                return found
        return None

    def open_project(self, path: str, editor: str = "nvim") -> str | None:
        """Abre un directorio de proyecto en el editor elegido (code o nvim)."""
        expanded = self._resolve_project(path)
        if not expanded:
            from commands.files import _suggest
            console.print(f"[yellow]Directorio no encontrado: {path}[/yellow]")
            return f"No encontré el proyecto {path}.{_suggest(path)}"

        if editor == "code":
            subprocess.Popen(["code", expanded], start_new_session=True)
        else:
            subprocess.Popen(
                ["ghostty", "-e", "bash", "-c", f"cd '{expanded}' && nvim ."],
                start_new_session=True,
            )
        return None
