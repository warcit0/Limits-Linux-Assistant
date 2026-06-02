"""Comandos de operaciones sobre archivos."""

import subprocess
import os
import shutil
from rich.console import Console

console = Console()


class FileCommands:
    def search_file(self, name: str, path: str = "~") -> str:
        """
        Busca un archivo por nombre.
        Usa 'fd' si está disponible (más rápido), o 'find' como fallback.
        Args:
            name: Nombre del archivo a buscar (puede incluir wildcards)
            path: Directorio base donde buscar (default: home)
        Returns:
            Texto con los primeros resultados
        """
        expanded = os.path.expanduser(path)

        try:
            if shutil.which("fd"):
                result = subprocess.run(
                    ["fd", "--max-results", "5", name, expanded],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
            else:
                result = subprocess.run(
                    ["find", expanded, "-name", f"*{name}*", "-maxdepth", "5"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )

            lines = result.stdout.strip().splitlines()[:5]
            if not lines:
                return f"No encontré archivos que coincidan con '{name}'."

            console.print("\n".join(lines))
            return f"Encontré {len(lines)} resultado(s) para '{name}'."

        except subprocess.TimeoutExpired:
            return "La búsqueda tardó demasiado. Intenta en un directorio más específico."
        except Exception as e:
            return f"Error al buscar: {e}"

    def open_file(self, path: str) -> None:
        """
        Abre un archivo con la aplicación por defecto del sistema (xdg-open).
        Args:
            path: Ruta al archivo
        """
        expanded = os.path.expanduser(path)
        if not os.path.exists(expanded):
            console.print(f"[yellow]Archivo no encontrado: {expanded}[/yellow]")
            return
        subprocess.Popen(
            ["xdg-open", expanded],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def list_directory(self, path: str = ".") -> str:
        """
        Lista el contenido de un directorio.
        Args:
            path: Directorio a listar (default: directorio actual)
        Returns:
            Texto con el contenido (máx 10 entradas)
        """
        expanded = os.path.expanduser(path)
        try:
            entries = os.listdir(expanded)
            dirs  = sorted([e for e in entries if os.path.isdir(os.path.join(expanded, e))])[:5]
            files = sorted([e for e in entries if os.path.isfile(os.path.join(expanded, e))])[:5]

            parts = []
            if dirs:
                parts.append(f"{len(dirs)} carpeta(s): {', '.join(dirs)}")
            if files:
                parts.append(f"{len(files)} archivo(s): {', '.join(files)}")

            return ". ".join(parts) if parts else "El directorio está vacío."
        except PermissionError:
            return "Sin permiso para acceder a ese directorio."
        except FileNotFoundError:
            return f"Directorio no encontrado: {path}"
