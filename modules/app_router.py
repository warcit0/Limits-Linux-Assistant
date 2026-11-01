"""Router determinista de aplicaciones (sin LLM).

«abre discord», «cierra spotify», «pon spotify en pantalla» son mecánicas: el
modelo solo aporta variación (a veces elegía `focus_window` para abrir, o
`media_control` para enfocar). Aquí se resuelven contra el catálogo real de
apps en ~0 ms; si la frase no encaja, devuelve None y decide el LLM.

Reglas duras:
- Sin ` y ` (frases compuestas → desktop_task o el LLM).
- Sin verbos de búsqueda/archivo: «abre el archivo X» no es una app.
- La app debe existir en `AppCommands.APP_MAP` (o en sus alias).
"""

from __future__ import annotations

import re
import unicodedata


def _plain(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", str(text))
    return "".join(c for c in nfkd if not unicodedata.combining(c)).casefold().strip()


# Alias coloquiales que no viven en APP_MAP (los de proceso están en apps.py).
_EXTRA_ALIASES = {
    "navegador": "chromium",
    "browser": "chromium",
    "explorador": "thunar",
    "archivos": "thunar",
    "explorador de archivos": "thunar",
    "gestor de archivos": "thunar",
}

# «abre X» / «cierra X» / «mata X»
_OPEN_CLOSE = re.compile(
    r"^(?P<verb>abre|abreme|abrir|lanza|ejecuta|cierra|cerrar|mata)\s+"
    r"(?:la\s+|el\s+|los\s+|las\s+)?"
    r"(?:app|aplicacion|aplicación|programa\s+)?"
    r"(?P<app>.+)$"
)

# «pon X en pantalla» / «trae X al frente»
_FOCUS = re.compile(
    r"^(?P<verb>pon|ponme|muestra|muestrame|trae|traeme|enfoca|enfocame)\s+"
    r"(?:la\s+|el\s+)?"
    r"(?P<app>.+?)\s+"
    r"(?:en\s+(?:(?:mi|la)\s+)?pantalla|en\s+primer\s+plano|al\s+frente)$"
)

# Palabras que significan archivo/carpeta: eso lo decide `file_router`/LLM.
_NOT_APP = re.compile(r"\b(archivo|fichero|carpeta|directorio|proyecto|busca)\b")

_CLOSE_VERBS = frozenset({"cierra", "cerrar", "mata"})


def _catalog() -> dict[str, str]:
    """Nombre coloquial → nombre real, sin depender de estado global."""
    from commands.apps import AppCommands

    disponibles = AppCommands.disponibles()
    table = {k.casefold(): k for k in disponibles}
    for alias, real in AppCommands.PROCESS_ALIASES.items():
        table[alias.casefold()] = real
    table.update(_EXTRA_ALIASES)
    gestor = AppCommands.predeterminada('inode/directory',('thunar','nautilus','dolphin','pcmanfm'))
    for alias in ('archivos','explorador','explorador de archivos','gestor de archivos'):
        if gestor:
            table[alias] = gestor
        else:
            table.pop(alias,None)
    return {alias:real for alias,real in table.items() if real in disponibles}


def resolver_aplicacion(nombre):
    """Alias exactos del catálogo real, compartidos por router y permisos."""
    return _catalog().get(_plain(nombre).strip(' .!?¡¿\"'))


def match_app_route(text: str) -> dict | None:
    """Devuelve un `parsed_result` de open/close/focus, o None."""
    if not text or not text.strip():
        return None
    plain = _plain(text).strip(" .!?¡¿,;:")
    if not plain or " y " in plain:
        return None

    table = _catalog()

    match = _FOCUS.search(plain)
    if match:
        app = table.get(match.group("app").strip())
        if app:
            return {
                "intent": "focus_window",
                "action": "focus_window",
                "params": {"app": app},
                "response": f"Trayendo {app}.",
                "confidence": 1.0,
            }
        return None

    match = _OPEN_CLOSE.search(plain)
    if not match:
        return None
    app = table.get(match.group("app").strip())
    if _NOT_APP.search(plain) and not app:
        return None
    if not app:
        return None
    if match.group("verb") in _CLOSE_VERBS:
        return {
            "intent": "app_close",
            "action": "close_application",
            "params": {"app": app},
            "response": f"Cerrando {app}.",
            "confidence": 1.0,
        }
    return {
        "intent": "app_open",
        "action": "open_application",
        "params": {"app": app, "args": []},
        "response": f"Abriendo {app}.",
        "confidence": 1.0,
    }
