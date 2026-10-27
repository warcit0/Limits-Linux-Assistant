"""Comandos de operaciones sobre archivos."""

import os
import shutil
import subprocess
from pathlib import Path

from rich.console import Console

console = Console()

# Máximo de resultados de búsqueda que se hablan / listan
_MAX_SEARCH = 5


def _expand(path: str) -> str:
    return os.path.expanduser(path.strip()) if path else os.path.expanduser("~")


def _speakable_path(path: str) -> str:
    """Acorta paths bajo $HOME para voz."""
    home = os.path.expanduser("~")
    if path.startswith(home + os.sep):
        return "~" + path[len(home):]
    return path


class FileCommands:
    def _find_matches(self, name: str, path: str = "~") -> list[str]:
        """Busca por nombre; devuelve hasta _MAX_SEARCH rutas absolutas."""
        expanded = _expand(path)
        if not os.path.isdir(expanded):
            return []

        try:
            if shutil.which("fd"):
                # -F: literal (evita que "informe.pdf" sea regex)
                result = subprocess.run(
                    ["fd", "-F", "--max-results", str(_MAX_SEARCH),
                     name, expanded],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
            else:
                result = subprocess.run(
                    ["find", expanded, "-iname", f"*{name}*",
                     "-maxdepth", "6"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
            lines = [ln.strip() for ln in result.stdout.splitlines() if ln.strip()]
            return lines[:_MAX_SEARCH]
        except subprocess.TimeoutExpired:
            raise
        except Exception:
            return []

    def search_file(self, name: str, path: str = "~") -> str:
        """
        Busca un archivo por nombre.
        Usa 'fd' si está disponible (más rápido), o 'find' como fallback.
        Args:
            name: Nombre del archivo a buscar (puede incluir wildcards)
            path: Directorio base donde buscar (default: home)
        Returns:
            Texto con rutas hablables (para el siguiente turno / open_file)
        """
        if not name or not str(name).strip():
            return "¿Qué archivo busco?"

        try:
            lines = self._find_matches(name, path)
        except subprocess.TimeoutExpired:
            return "La búsqueda tardó demasiado. Intenta en un directorio más específico."
        except Exception as e:
            return f"Error al buscar: {e}"

        if not lines:
            return f"No encontré archivos que coincidan con '{name}'."

        console.print("\n".join(lines))
        spoken = ", ".join(_speakable_path(p) for p in lines)
        return (f"Encontré {len(lines)} resultado(s) para '{name}': {spoken}.")

    def search_and_open(self, name: str, path: str = "~") -> str:
        """
        Busca y abre si hay un único match. Si hay varios, lista sin abrir.
        """
        if not name or not str(name).strip():
            return "¿Qué archivo abro?"

        try:
            lines = self._find_matches(name, path)
        except subprocess.TimeoutExpired:
            return "La búsqueda tardó demasiado."
        except Exception as e:
            return f"Error al buscar: {e}"

        if not lines:
            return f"No encontré '{name}'."

        if len(lines) == 1:
            self.open_file(lines[0])
            return f"Abrí {_speakable_path(lines[0])}."

        spoken = "; ".join(
            f"{i + 1}: {_speakable_path(p)}" for i, p in enumerate(lines)
        )
        console.print("\n".join(lines))
        return (f"Hay {len(lines)} coincidencias. Di el número o la ruta. {spoken}.")

    def open_file(self, path: str) -> str:
        """
        Abre un archivo con la aplicación por defecto del sistema (xdg-open).
        Args:
            path: Ruta al archivo
        """
        expanded = _expand(path)
        if not os.path.exists(expanded):
            console.print(f"[yellow]Archivo no encontrado: {expanded}[/yellow]")
            return f"No encontré {_speakable_path(expanded)}."
        subprocess.Popen(
            ["xdg-open", expanded],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        return f"Abriendo {_speakable_path(expanded)}."

    def reveal_file(self, path: str = "", name: str = "",
                    search_path: str = "~") -> str:
        """
        Muestra el archivo en el explorador (Thunar).
        Si path está vacío y hay name, busca primero (1 match → revelar).
        """
        target = ""
        if path and str(path).strip():
            target = _expand(path)
        elif name and str(name).strip():
            try:
                matches = self._find_matches(name, search_path)
            except subprocess.TimeoutExpired:
                return "La búsqueda tardó demasiado."
            if not matches:
                return f"No encontré '{name}'."
            if len(matches) > 1:
                spoken = ", ".join(_speakable_path(p) for p in matches)
                return (f"Hay {len(matches)} coincidencias; di cuál revelar: "
                        f"{spoken}.")
            target = matches[0]
        else:
            return "¿Qué archivo o carpeta muestro?"

        if not os.path.exists(target):
            return f"No existe {_speakable_path(target)}."

        parent = target if os.path.isdir(target) else str(Path(target).parent)

        # Thunar selecciona el archivo si se le pasa la ruta completa
        if shutil.which("thunar") and os.path.isfile(target):
            subprocess.Popen(
                ["thunar", target],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        else:
            subprocess.Popen(
                ["xdg-open", parent],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        return f"Mostrando {_speakable_path(target)} en el explorador."

    def copy_file(self, source: str, destination: str) -> str:
        """
        Copia un archivo o directorio. Falla si el destino ya existe
        (evita overwrite silencioso; el lane compuesto puede pedir otra ruta).
        """
        src = _expand(source)
        dst = _expand(destination)
        if not os.path.exists(src):
            return f"Origen no encontrado: {_speakable_path(src)}."
        if os.path.exists(dst):
            return (f"El destino {_speakable_path(dst)} ya existe. "
                    "Elige otro nombre o bórralo antes.")
        try:
            # Si destination es un directorio existente... ya cubierto por exists.
            # Si destination es "carpeta/" y la carpeta existe → exists.
            # Si destination es una carpeta y queremos copiar DENTRO:
            if os.path.isdir(dst):
                return f"El destino {_speakable_path(dst)} ya existe."
            parent = str(Path(dst).parent)
            if not os.path.isdir(parent):
                return f"No existe la carpeta destino {_speakable_path(parent)}."
            if os.path.isdir(src):
                shutil.copytree(src, dst)
            else:
                shutil.copy2(src, dst)
            return f"Copié {_speakable_path(src)} a {_speakable_path(dst)}."
        except Exception as e:
            return f"No pude copiar: {e}"

    def move_file(self, source: str, destination: str) -> str:
        """Mueve un archivo o directorio. Requiere confirmación vía executor."""
        src = _expand(source)
        dst = _expand(destination)
        if not os.path.exists(src):
            return f"Origen no encontrado: {_speakable_path(src)}."
        if os.path.exists(dst):
            return (f"El destino {_speakable_path(dst)} ya existe. "
                    "No sobrescribo.")
        parent = str(Path(dst).parent)
        if not os.path.isdir(parent):
            return f"No existe la carpeta destino {_speakable_path(parent)}."
        try:
            shutil.move(src, dst)
            return f"Moví {_speakable_path(src)} a {_speakable_path(dst)}."
        except Exception as e:
            return f"No pude mover: {e}"

    def rename_file(self, path: str, new_name: str) -> str:
        """Renombra un archivo (solo el nombre, misma carpeta). Confirmación vía executor."""
        src = _expand(path)
        if not os.path.exists(src):
            return f"No encontré {_speakable_path(src)}."
        new_name = (new_name or "").strip()
        if not new_name or os.sep in new_name or new_name in (".", ".."):
            return "El nuevo nombre no es válido."
        dst = str(Path(src).parent / new_name)
        if os.path.exists(dst):
            return f"Ya existe {_speakable_path(dst)}. No sobrescribo."
        try:
            os.rename(src, dst)
            return f"Renombré a {new_name}."
        except Exception as e:
            return f"No pude renombrar: {e}"

    def list_directory(self, path: str = ".") -> str:
        """
        Lista el contenido de un directorio.
        Args:
            path: Directorio a listar (default: directorio actual)
        Returns:
            Texto con el contenido (máx 10 entradas)
        """
        expanded = _expand(path)
        try:
            entries = os.listdir(expanded)
            dirs = sorted(
                [e for e in entries if os.path.isdir(os.path.join(expanded, e))]
            )[:5]
            files = sorted(
                [e for e in entries if os.path.isfile(os.path.join(expanded, e))]
            )[:5]

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
