"""Router determinista para órdenes de archivos con carpeta explícita.

Por qué existe: el LLM inventa rutas aunque el prompt traiga el mapa del
equipo ("/Proyectos", "work", "~/Documentos/work"). Estas frases son
mecánicas y no necesitan modelo:

    "lista los proyectos de la carpeta work"  → list_directory("work")
    "qué hay en descargas"                    → list_directory("descargas")
    "muéstrame la carpeta work"               → reveal_file("work")

La ruta extraída se valida contra el disco (con tolerancia a mayúsculas y
acentos). Si no resuelve, el router devuelve None y decide el LLM: así nunca
inventamos un destino.
"""

from __future__ import annotations

import re
import unicodedata

from commands.files import _resolve_existing

# Verbos de listado (normalizados: sin acentos, minúsculas)
_LIST = re.compile(
    r"\b(lista|listame|listar|listado|ensename|muestrame el contenido|"
    r"muestra el contenido|que hay|que contiene|contenido de|"
    r"cuantos archivos|cuantas carpetas)\b"
)

# Verbos de "abrir el explorador en..."
_REVEAL = re.compile(r"\b(muestrame|muestra|ensename|abre el explorador en)\b")

# Marcadores de ruta, del más específico al más genérico
_MARKERS = (
    re.compile(r"\b(?:de|del|en)\s+la\s+carpeta\s+de\s+(?P<path>.+)$"),
    re.compile(r"\b(?:de|del|en)\s+la\s+carpeta\s+(?!de\s)(?P<path>.+)$"),
    re.compile(r"\b(?:de|del|en)\s+el\s+directorio\s+(?P<path>.+)$"),
    re.compile(r"\b(?:contenido|archivos|cosas)\s+de\s+(?P<path>.+)$"),
    re.compile(r"\bcarpeta\s+(?!de\s)(?P<path>.+)$"),
    re.compile(r"\b(?:de|del|en)\s+(?P<path>[~/].+)$"),
    re.compile(r"\b(?:de|del|en)\s+(?P<path>.+)$"),
)

_TRAILING = " .!?¡¿,;:"


def _plain(text: str) -> str:
    """Minúsculas y sin acentos, para comparar verbos."""
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).casefold()


def _clean(raw: str) -> str:
    path = raw.strip().strip("\"'").strip(_TRAILING)
    # "mi carpeta work" / "mi work" → "work"
    path = re.sub(r"^mi\s+(carpeta\s+|directorio\s+)?", "", path)
    return path.strip().strip(_TRAILING)


def _extract_paths(normalized: str):
    """Candidatos de ruta, del marcador más específico al más genérico."""
    for pattern in _MARKERS:
        match = pattern.search(normalized)
        if not match:
            continue
        path = _clean(match.group("path"))
        if path:
            yield path


def match_file_route(text: str) -> dict | None:
    """
    Devuelve el `parsed_result` del executor, o None si la frase no es una
    orden de archivos con carpeta explícita y resoluble.
    """
    if not text or not text.strip():
        return None
    normalized = _plain(text)

    is_list = bool(_LIST.search(normalized))
    # "muéstrame el informe de descargas" NO es revelar la carpeta: exigimos
    # que el objeto sea explícitamente una carpeta/explorador.
    is_reveal = bool(_REVEAL.search(normalized)) and any(
        w in normalized for w in ("carpeta", "directorio", "explorador"))
    is_projects = bool(re.search(
        r"\b(que|mis|cuantos|todos los)\s+proyectos\b", normalized))
    if not (is_list or is_reveal or is_projects):
        return None

    resolved = None
    for candidate in _extract_paths(normalized):
        resolved = _resolve_existing(candidate)
        if resolved:
            break

    # "¿qué proyectos tengo?" / "lista mis proyectos" → ~/Proyectos
    if not resolved and is_projects:
        resolved = _resolve_existing("~/Proyectos")

    if not resolved:
        return None

    # "muéstrame el contenido de X" es listado aunque lleve "muéstrame"
    if (is_list or is_projects) and "contenido" in normalized:
        is_reveal = False

    if is_reveal and not (is_list or is_projects):
        return {
            "intent": "reveal_file",
            "action": "reveal_file",
            "params": {"path": resolved},
            "response": "Mostrando la carpeta.",
            "confidence": 1.0,
        }
    if not (is_list or is_projects):
        return None

    # Las herramientas hablan mejor de rutas cortas (~/Work)
    return {
        "intent": "list_directory",
        "action": "list_directory",
        "params": {"path": resolved},
        "response": "Mirando la carpeta.",
        "confidence": 1.0,
    }
