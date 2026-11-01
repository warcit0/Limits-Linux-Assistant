"""Rutas deterministas de un solo dato: hora y fecha (P0-1).

No pasan por el LLM: son instantáneas y no pueden alucinar. El patrón es el
mismo que `file_router`: si la frase encaja, se responde; si no, decide el LLM.

Ojo con las trampas: «¿a qué hora abre el banco?» NO es la hora actual.
"""

from __future__ import annotations

import re
import unicodedata


def _plain(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", str(text))
    return "".join(c for c in nfkd if not unicodedata.combining(c)).casefold().strip()


_TIME = (
    re.compile(r"\b(que|la)\s+hora\s+(es|son|tienes|tenemos)\b"),
    re.compile(r"^(dime|dame)\s+la\s+hora\b"),
    re.compile(r"^la\s+hora\b"),
)

_WEEKDAY = re.compile(r"\bdia\s+de\s+la\s+semana\b")

_DATE = (
    re.compile(r"\b(que)\s+dia\s+(es|estamos)\b"),
    re.compile(r"\ba\s+que\s+(dia|estamos)\b"),
    re.compile(r"\bque\s+fecha\b"),
    re.compile(r"\bfecha\s+de\s+hoy\b"),
)

# Si aparece algo de esto, la pregunta es sobre un horario ajeno, no el nuestro.
_EXCLUDE = re.compile(r"\b(abre|abren|cierra|cierran|empieza|termina|sale|llega)\b")


def match_quick_route(text: str) -> dict | None:
    """Devuelve un `parsed_result` de `get_time`, o None."""
    if not text or not text.strip():
        return None
    plain = _plain(text).strip(" .!?¡¿,;:")

    detail = None
    if _WEEKDAY.search(plain):
        detail = "weekday"
    elif any(p.search(plain) for p in _DATE):
        detail = "date"
    elif any(p.search(plain) for p in _TIME):
        detail = "time"

    if detail is None or _EXCLUDE.search(plain):
        return None

    return {
        "intent": "get_time",
        "action": "get_time",
        "params": {"detail": detail},
        "response": "",
        "confidence": 1.0,
    }
