"""Mapa compacto del equipo para el system prompt.

El LLM no conoce el disco: si le pides "la carpeta work" inventa `work`,
`~/work` o `~/Documentos/work`. Este mapa le da las rutas REALES (con sus
mayúsculas) de un vistazo, sin escanear el disco entero ni llamar a tools.

Se genera una vez al arrancar: es un snapshot barato (solo listdir de dos
niveles) y acotado por presupuesto de caracteres.
"""

from __future__ import annotations

import os
from pathlib import Path

# Ruido que no aporta nada al asistente
_SKIP = {
    "snap", "node_modules", "__pycache__", "venv", ".venv", "limits-env",
    "site-packages", ".git", ".cache", "Cache", ".local", ".config",
}

# Carpetas cuyos hijos sí importan (proyectos, documentos, descargas)
_EXPAND = (
    "Proyectos", "Projects", "Work", "Trabajo", "Repos", "repo",
    "Documentos", "Documents", "Escritorio", "Desktop",
)

_DEFAULT_BUDGET = 700


def _dirs(path: Path) -> list[str]:
    try:
        names = os.listdir(path)
    except OSError:
        return []
    out = []
    for name in names:
        if name.startswith(".") or name in _SKIP:
            continue
        if os.path.isdir(os.path.join(path, name)):
            out.append(name)
    return sorted(out, key=str.casefold)


def build_machine_map(home: str | os.PathLike | None = None,
                      top_max: int = 18,
                      child_max: int = 8,
                      budget: int = _DEFAULT_BUDGET) -> str:
    """
    Devuelve algo como::

        ~/: Descargas, Documentos, Escritorio, Proyectos, Work
        ~/Proyectos: ClipsYoser, Limits, Nolimitz
        ~/Work: Docs, Treecodes, WebAi-to-local-CLI-LLM

    Nunca lanza: si no puede leer algo, simplemente lo omite.
    """
    base = Path(home or os.path.expanduser("~"))
    top = _dirs(base)
    if not top:
        return ""

    # Las carpetas de proyectos/documentos van SIEMPRE delante: son las que
    # el asistente necesita conocer y el corte por presupuesto no debe tirarlas.
    wanted = {e.casefold() for e in _EXPAND}
    important = [n for n in top if n.casefold() in wanted]
    ordered = important + [n for n in top if n not in important]

    shown = ordered[:top_max]
    more = f" (+{len(ordered) - top_max})" if len(ordered) > top_max else ""
    lines = [f"~/: {', '.join(shown)}{more}"]

    for name in ordered[:top_max]:
        # Comparación sin acentos ni caja para aceptar "documentos"/"Documents"
        if name.casefold() not in {e.casefold() for e in _EXPAND}:
            continue
        children = _dirs(base / name)
        if not children:
            continue
        shown = children[:child_max]
        more = f" (+{len(children) - child_max})" if len(children) > child_max else ""
        lines.append(f"~/{name}: {', '.join(shown)}{more}")

    out = "\n".join(lines)
    if len(out) > budget:
        out = out[: budget - 1].rstrip(", ") + "…"
    return out
