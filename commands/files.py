"""Comandos de operaciones sobre archivos."""

from __future__ import annotations

import difflib
import json
import os
import shutil
import subprocess
import time
import unicodedata
from pathlib import Path

from rich.console import Console

console = Console()

_MAX_SEARCH = 5

# Excludes por defecto (fd --exclude / find -prune)
_DEFAULT_EXCLUDES = (
    ".git",
    "node_modules",
    "__pycache__",
    "limits-env",
    "site-packages",
    ".venv",
    "venv",
    ".cache",
    "Cache",
)

# Clases Hyprland típicas tras xdg-open / thunar
_EXT_CLASSES: dict[str, tuple[str, ...]] = {
    ".pdf": ("org.gnome.Evince", "evince", "okular", "firefox", "chromium",
             "google-chrome", "Chromium", "Firefox"),
    ".png": ("imv", "feh", "org.gnome.eog", "eog", "gimp"),
    ".jpg": ("imv", "feh", "org.gnome.eog", "eog", "gimp"),
    ".jpeg": ("imv", "feh", "org.gnome.eog", "eog", "gimp"),
    ".webp": ("imv", "feh", "org.gnome.eog", "eog"),
    ".mp4": ("mpv", "vlc", "org.gnome.Totem"),
    ".mkv": ("mpv", "vlc"),
    ".py": ("Code", "code", "code-oss", "cursor", "Cursor", "dev.zed.Zed"),
    ".md": ("Code", "code", "obsidian", "Obsidian", "cursor", "Cursor"),
    ".txt": ("Code", "code", "mousepad", "org.gnome.TextEditor", "nvim", "ghostty"),
    ".json": ("Code", "code", "cursor", "Cursor"),
}


def _expand(path: str) -> str:
    """
    Expande ~ y $VARS. Las rutas relativas se resuelven contra $HOME, no
    contra el cwd del servicio: para un asistente de voz "work" significa
    ~/work, no ./work dentro del repo de Limits.
    """
    raw = os.path.expandvars(os.path.expanduser((path or "").strip() or "~"))
    if not os.path.isabs(raw):
        raw = os.path.join(os.path.expanduser("~"), raw)
    return os.path.normpath(raw)


def _norm(text: str) -> str:
    """Pliega mayúsculas y acentos: 'Descárgas' → 'descargas'."""
    nfkd = unicodedata.normalize("NFKD", str(text))
    return "".join(c for c in nfkd if not unicodedata.combining(c)).casefold().strip()


def _match_child(parent: str, name: str) -> str | None:
    """Hijo de `parent` que coincide con `name` ignorando caja y acentos."""
    exact = os.path.join(parent, name)
    if os.path.lexists(exact):
        return exact
    try:
        entries = os.listdir(parent)
    except OSError:
        return None
    folded = name.casefold()
    for entry in entries:
        if entry.casefold() == folded:
            return os.path.join(parent, entry)
    wanted = _norm(name)
    for entry in sorted(entries):
        if _norm(entry) == wanted:
            return os.path.join(parent, entry)
    return None


def _resolve_existing(path: str) -> str | None:
    """
    Ruta real o None. Recorre componente a componente tolerando mayúsculas y
    acentos: 'work/proyectos' → '~/Work/Proyectos'.
    """
    expanded = _expand(path)
    current = os.sep
    for part in Path(expanded).parts[1:]:
        found = _match_child(current, part)
        if found is None:
            return None
        current = found
    return current


def _resolve_target(path: str) -> str:
    """
    Ruta de destino: resuelve la carpeta padre (tolerante a caja/acentos) y
    conserva el nombre final tal cual, porque puede no existir todavía.
    """
    expanded = _expand(path)
    parent = os.path.dirname(expanded)
    real_parent = _resolve_existing(parent)
    return os.path.join(real_parent or parent, os.path.basename(expanded))


def _suggest(path: str) -> str:
    """Sugerencia corta cuando no se encuentra la ruta pedida."""
    expanded = _expand(path)
    parent = os.path.dirname(expanded)
    real_parent = _resolve_existing(parent)
    if not real_parent:
        return ""
    try:
        entries = sorted(os.listdir(real_parent))
    except OSError:
        return ""
    wanted = os.path.basename(expanded)
    close = difflib.get_close_matches(
        _norm(wanted), [_norm(e) for e in entries], n=3, cutoff=0.6)
    if not close:
        return ""
    names = [e for n in close for e in entries if _norm(e) == n][:3]
    pretty = ", ".join(
        _speakable_path(os.path.join(real_parent, n)) for n in names)
    return f" ¿Quisiste decir {pretty}?"


def _speakable_path(path: str) -> str:
    """Acorta paths bajo $HOME para voz."""
    home = os.path.expanduser("~")
    if path.startswith(home + os.sep):
        return "~" + path[len(home):]
    return path


def _parse_roots(raw: str | None) -> list[str]:
    """FILE_SEARCH_ROOT: rutas separadas por ':' (estilo PATH)."""
    if not raw or not str(raw).strip():
        return [os.path.expanduser("~")]
    roots = []
    for part in str(raw).split(":"):
        part = part.strip()
        if not part:
            continue
        expanded = os.path.expanduser(part)
        if os.path.isdir(expanded):
            roots.append(expanded)
    return roots or [os.path.expanduser("~")]


def _parse_excludes(raw: str | None) -> list[str]:
    if raw is None or str(raw).strip() == "":
        return list(_DEFAULT_EXCLUDES)
    return [x.strip() for x in str(raw).split(",") if x.strip()]


class FileCommands:
    def __init__(
        self,
        search_roots: str | None = None,
        search_excludes: str | None = None,
        focus_delay_s: float = 0.55,
        focus_retries: int = 4,
    ):
        self.search_roots = _parse_roots(search_roots)
        self.search_excludes = _parse_excludes(search_excludes)
        self.focus_delay_s = focus_delay_s
        self.focus_retries = focus_retries
        # Memoria entre turnos (follow-ups: muéstramelo / ábrelo / el 2º)
        self.last_matches: list[str] = []
        self.last_opened: str | None = None

    def _default_path_arg(self, path: str | None) -> str | None:
        """None/'~'/'' → buscar en search_roots; otra ruta → esa sola."""
        if path is None or not str(path).strip() or str(path).strip() in ("~", "~/"):
            return None
        return str(path).strip()

    def _roots_for(self, path: str | None) -> list[str]:
        specific = self._default_path_arg(path)
        if specific is None:
            return list(self.search_roots)
        resolved = _resolve_existing(specific)
        return [resolved] if resolved and os.path.isdir(resolved) else []

    def _find_matches(self, name: str, path: str | None = None) -> list[str]:
        """Busca por nombre; hasta _MAX_SEARCH rutas absolutas."""
        roots = self._roots_for(path)
        if not roots:
            return []

        found: list[str] = []
        try:
            for root in roots:
                if len(found) >= _MAX_SEARCH:
                    break
                need = _MAX_SEARCH - len(found)
                batch = self._search_one_root(name, root, need)
                for p in batch:
                    if p not in found:
                        found.append(p)
                        if len(found) >= _MAX_SEARCH:
                            break
            return found
        except subprocess.TimeoutExpired:
            raise
        except Exception:
            return found

    def _search_one_root(self, name: str, root: str, limit: int) -> list[str]:
        if shutil.which("fd"):
            cmd = ["fd", "-F", "--max-results", str(limit)]
            for ex in self.search_excludes:
                cmd.extend(["--exclude", ex])
            cmd.extend([name, root])
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=10,
            )
        else:
            # find: ( -name ex1 -o -name ex2 ) -prune -o -iname *name* -print
            cmd = ["find", root]
            if self.search_excludes:
                cmd.append("(")
                for i, ex in enumerate(self.search_excludes):
                    if i:
                        cmd.append("-o")
                    cmd.extend(["-name", ex])
                cmd.extend([")", "-prune", "-o"])
            cmd.extend(["-iname", f"*{name}*", "-print"])
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=10,
            )
        lines = [ln.strip() for ln in result.stdout.splitlines() if ln.strip()]
        # find no limita; recortar y filtrar basura residual
        out = []
        for ln in lines:
            if any(f"/{ex}/" in ln or ln.endswith(f"/{ex}") for ex in self.search_excludes):
                continue
            out.append(ln)
            if len(out) >= limit:
                break
        return out

    def _remember_matches(self, matches: list[str]) -> None:
        self.last_matches = list(matches[:_MAX_SEARCH])

    def _resolve_index(self, index: int | str | None) -> int | None:
        if index is None or index == "":
            return 1
        try:
            i = int(index)
        except (TypeError, ValueError):
            return None
        return i if i >= 1 else None

    # ── búsqueda / apertura ─────────────────────────────────────────────────

    def search_file(self, name: str, path: str = "~") -> str:
        """Busca un archivo por nombre (fd/find). Guarda last_matches."""
        if not name or not str(name).strip():
            return "¿Qué archivo busco?"

        try:
            lines = self._find_matches(name, path)
        except subprocess.TimeoutExpired:
            return "La búsqueda tardó demasiado. Intenta en un directorio más específico."
        except Exception as e:
            return f"Error al buscar: {e}"

        self._remember_matches(lines)
        if not lines:
            return f"No encontré archivos que coincidan con '{name}'."

        console.print("\n".join(lines))
        spoken = ", ".join(_speakable_path(p) for p in lines)
        hint = " Di muéstramelo o ábrelo." if len(lines) == 1 else " Di el número o muéstrame el primero."
        return (f"Encontré {len(lines)} resultado(s) para '{name}': {spoken}.{hint}")

    def search_and_open(self, name: str, path: str = "~") -> str:
        """Busca y abre si hay un único match. Si hay varios, lista sin abrir."""
        if not name or not str(name).strip():
            return "¿Qué archivo abro?"

        try:
            lines = self._find_matches(name, path)
        except subprocess.TimeoutExpired:
            return "La búsqueda tardó demasiado."
        except Exception as e:
            return f"Error al buscar: {e}"

        self._remember_matches(lines)
        if not lines:
            return f"No encontré '{name}'."

        if len(lines) == 1:
            return self.open_file(lines[0])

        spoken = "; ".join(
            f"{i + 1}: {_speakable_path(p)}" for i, p in enumerate(lines)
        )
        console.print("\n".join(lines))
        return (f"Hay {len(lines)} coincidencias. Di el número o muéstrame el primero. {spoken}.")

    def open_file(self, path: str = "", index: int | str | None = None) -> str:
        """
        Abre con xdg-open y intenta foco Hyprland.
        path vacío → usa last_matches[index] (1-based) o last_opened.
        """
        target = (path or "").strip()
        if not target:
            return self.open_last(index=index)

        expanded = _resolve_existing(target)
        if not expanded:
            console.print(f"[yellow]Archivo no encontrado: {_expand(target)}[/yellow]")
            return f"No encontré {_speakable_path(_expand(target))}.{_suggest(target)}"

        subprocess.Popen(
            ["xdg-open", expanded],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        self.last_opened = expanded
        if expanded not in self.last_matches:
            self.last_matches = [expanded] + [m for m in self.last_matches if m != expanded]
            self.last_matches = self.last_matches[:_MAX_SEARCH]

        focused = self._focus_opened_path(expanded)
        base = f"Abrí {_speakable_path(expanded)}."
        if focused:
            return base + " En pantalla."
        return base + " Si no lo ves, mira otro escritorio."

    def open_last(self, index: int | str | None = 1) -> str:
        """Abre el N-ésimo de last_matches (1 = primero). Follow-up: ábrelo."""
        i = self._resolve_index(index)
        if i is None:
            return "No entendí el número."
        if not self.last_matches:
            if self.last_opened and os.path.exists(self.last_opened):
                return self.open_file(self.last_opened)
            return "No hay un archivo reciente. Busca algo primero."
        if i > len(self.last_matches):
            return f"Solo tengo {len(self.last_matches)} resultado(s)."
        return self.open_file(self.last_matches[i - 1])

    def reveal_file(self, path: str = "", name: str = "",
                    search_path: str = "~",
                    index: int | str | None = None) -> str:
        """Muestra en Thunar; path/name vacíos → reveal_last."""
        if (not path or not str(path).strip()) and (not name or not str(name).strip()):
            return self.reveal_last(index=index)

        target = ""
        if path and str(path).strip():
            target = _expand(path)
        elif name and str(name).strip():
            try:
                matches = self._find_matches(name, search_path)
            except subprocess.TimeoutExpired:
                return "La búsqueda tardó demasiado."
            self._remember_matches(matches)
            if not matches:
                return f"No encontré '{name}'."
            if len(matches) > 1:
                spoken = ", ".join(_speakable_path(p) for p in matches)
                return (f"Hay {len(matches)} coincidencias; di cuál revelar: "
                        f"{spoken}.")
            target = matches[0]

        return self._reveal_path(target)

    def reveal_last(self, index: int | str | None = 1) -> str:
        """Revela en explorador el N-ésimo match. Follow-up: muéstramelo."""
        i = self._resolve_index(index)
        if i is None:
            return "No entendí el número."
        if not self.last_matches:
            if self.last_opened and os.path.exists(self.last_opened):
                return self._reveal_path(self.last_opened)
            return "No hay un archivo reciente. Busca algo primero."
        if i > len(self.last_matches):
            return f"Solo tengo {len(self.last_matches)} resultado(s)."
        return self._reveal_path(self.last_matches[i - 1])

    def _reveal_path(self, target: str) -> str:
        if not target:
            return "¿Qué archivo o carpeta muestro?"
        expanded = _resolve_existing(target)
        if not expanded:
            return f"No existe {_speakable_path(_expand(target))}.{_suggest(target)}"

        parent = expanded if os.path.isdir(expanded) else str(Path(expanded).parent)
        used_thunar = False
        if shutil.which("thunar") and os.path.isfile(expanded):
            subprocess.Popen(
                ["thunar", expanded],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            used_thunar = True
        else:
            subprocess.Popen(
                ["xdg-open", parent],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )

        self.last_opened = expanded
        if expanded not in self.last_matches:
            self.last_matches = [expanded] + [
                m for m in self.last_matches if m != expanded
            ]
            self.last_matches = self.last_matches[:_MAX_SEARCH]

        prefer = ("thunar", "Thunar", "org.xfce.thunar") if used_thunar else None
        focused = self._focus_opened_path(
            expanded, prefer_classes=prefer, title_hints=(Path(expanded).name, Path(parent).name),
        )
        base = f"Mostrando {_speakable_path(expanded)} en el explorador."
        if focused:
            return base + " En pantalla."
        return base + " Si no lo ves, mira otro escritorio."

    def copy_file(self, source: str, destination: str) -> str:
        """Copia; falla si el destino ya existe."""
        src = _resolve_existing(source)
        dst = _resolve_target(destination)
        if not src:
            return (f"Origen no encontrado: "
                    f"{_speakable_path(_expand(source))}.{_suggest(source)}")
        if os.path.exists(dst):
            return (f"El destino {_speakable_path(dst)} ya existe. "
                    "Elige otro nombre o bórralo antes.")
        try:
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
        """Mueve. Requiere confirmación vía executor."""
        src = _resolve_existing(source)
        dst = _resolve_target(destination)
        if not src:
            return (f"Origen no encontrado: "
                    f"{_speakable_path(_expand(source))}.{_suggest(source)}")
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
        """Renombra (misma carpeta). Confirmación vía executor."""
        src = _resolve_existing(path)
        if not src:
            return f"No encontré {_speakable_path(_expand(path))}.{_suggest(path)}"
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

    def list_directory(self, path: str = "~") -> str:
        """Lista el contenido de un directorio (máx 8 carpetas + 6 archivos)."""
        expanded = _resolve_existing(path)
        if not expanded:
            return (f"No encontré la carpeta "
                    f"{_speakable_path(_expand(path))}.{_suggest(path)}")
        try:
            entries = [e for e in os.listdir(expanded) if not e.startswith(".")]
            dirs = sorted(
                [e for e in entries if os.path.isdir(os.path.join(expanded, e))]
            )
            files = sorted(
                [e for e in entries if os.path.isfile(os.path.join(expanded, e))]
            )
            parts = []
            if dirs:
                shown = ", ".join(dirs[:8])
                extra = f" y {len(dirs) - 8} más" if len(dirs) > 8 else ""
                parts.append(f"{len(dirs)} carpeta(s): {shown}{extra}")
            if files:
                shown = ", ".join(files[:6])
                extra = f" y {len(files) - 6} más" if len(files) > 6 else ""
                parts.append(f"{len(files)} archivo(s): {shown}{extra}")
            return ". ".join(parts) if parts else "El directorio está vacío."
        except PermissionError:
            return "Sin permiso para acceder a ese directorio."
        except FileNotFoundError:
            return f"Directorio no encontrado: {path}"

    # ── Hyprland focus ──────────────────────────────────────────────────────

    def _focus_opened_path(
        self,
        path: str,
        prefer_classes: tuple[str, ...] | None = None,
        title_hints: tuple[str, ...] | None = None,
    ) -> bool:
        """Intenta traer al workspace activo la ventana que abrió el archivo."""
        if not shutil.which("hyprctl"):
            return False

        basename = Path(path).name
        hints = list(title_hints or ())
        if basename not in hints:
            hints.insert(0, basename)
        classes = list(prefer_classes or ())
        classes.extend(_EXT_CLASSES.get(Path(path).suffix.lower(), ()))
        # Viewers comunes al final
        classes.extend(("thunar", "Thunar", "Code", "code", "firefox", "chromium",
                        "org.gnome.Evince", "mpv", "imv"))

        active_ws = self._active_workspace_id()
        deadline_steps = max(1, self.focus_retries)
        time.sleep(self.focus_delay_s)

        for _ in range(deadline_steps):
            client = self._find_client(hints, classes)
            if client:
                return self._focus_client(client, active_ws)
            time.sleep(0.35)
        return False

    @staticmethod
    def _active_workspace_id() -> int | None:
        try:
            r = subprocess.run(
                ["hyprctl", "activeworkspace", "-j"],
                capture_output=True, text=True, timeout=2, check=False,
            )
            if r.returncode != 0:
                return None
            data = json.loads(r.stdout)
            return int(data.get("id")) if isinstance(data, dict) else None
        except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError, TypeError, ValueError):
            return None

    @staticmethod
    def _find_client(
        title_hints: list[str],
        classes: list[str],
    ) -> dict | None:
        try:
            r = subprocess.run(
                ["hyprctl", "clients", "-j"],
                capture_output=True, text=True, timeout=3, check=False,
            )
            if r.returncode != 0:
                return None
            clients = json.loads(r.stdout)
            if not isinstance(clients, list):
                return None
        except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError):
            return None

        hints_l = [h.lower() for h in title_hints if h]
        classes_l = [c.lower() for c in classes if c]

        # 1) título contiene hint (más preciso para el archivo)
        for c in clients:
            if not isinstance(c, dict):
                continue
            title = str(c.get("title", "")).lower()
            if any(h in title for h in hints_l):
                return c

        # 2) clase preferida (última ventana de ese tipo — menos preciso)
        for cls in classes_l:
            for c in reversed(clients):
                if not isinstance(c, dict):
                    continue
                if str(c.get("class", "")).lower() == cls:
                    return c
        return None

    @staticmethod
    def _focus_client(client: dict, workspace_id: int | None) -> bool:
        addr = client.get("address")
        if not addr:
            return False
        try:
            if workspace_id is not None:
                ws = client.get("workspace") or {}
                cur = ws.get("id") if isinstance(ws, dict) else None
                if cur != workspace_id:
                    subprocess.run(
                        ["hyprctl", "dispatch", "movetoworkspacesilent",
                         f"{workspace_id},address:{addr}"],
                        capture_output=True, text=True, timeout=2, check=False,
                    )
            subprocess.run(
                ["hyprctl", "dispatch", "focuswindow", f"address:{addr}"],
                capture_output=True, text=True, timeout=2, check=False,
            )
            console.print(f"[green]✓ Foco en {client.get('class')} "
                          f"({client.get('title', '')[:40]})[/green]")
            return True
        except (subprocess.TimeoutExpired, OSError):
            return False
