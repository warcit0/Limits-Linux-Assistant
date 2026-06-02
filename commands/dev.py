"""
Comandos de desarrollo: git, docker, terminal, proyectos.

SEGURIDAD: run_command usa una allowlist de comandos seguros.
Comandos destructivos (rm, sudo, etc.) nunca se ejecutan directamente.
"""

import subprocess
import os
from rich.console import Console

console = Console()

# Allowlist de comandos de terminal seguros (sin parámetros destructivos)
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
    "curl",
    "cat",
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
        # Verificar que el comando es seguro
        cmd_lower = command.strip().lower()
        is_safe = any(cmd_lower.startswith(safe) for safe in SAFE_COMMANDS)

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

    def open_project(self, path: str, editor: str = "nvim") -> None:
        """Abre un directorio de proyecto en el editor elegido (code o nvim)."""
        expanded = os.path.expanduser(path)
        if not os.path.isdir(expanded):
            console.print(f"[yellow]Directorio no encontrado: {expanded}[/yellow]")
            return
            
        if editor == "code":
            subprocess.Popen(["code", expanded], start_new_session=True)
        else:
            subprocess.Popen(
                ["ghostty", "-e", "bash", "-c", f"cd '{expanded}' && nvim ."],
                start_new_session=True,
            )
