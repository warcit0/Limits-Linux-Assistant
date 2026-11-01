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
    from modules.workspace_router import normalizar_orden
    plain = normalizar_orden(plain)
    if re.search(r"[;]|\b(y|luego|despues|pero|no|nunca)\b",plain):
        return None
    nivel = re.fullmatch(r"(?:(?:pon|ajusta|deja|establece|cambia) (?:el )?)?(volumen|brillo)\s+(?:a|al|en)\s+(\d{1,3})(?:\s*%| por ciento)?",plain)
    if nivel and 0 <= int(nivel[2]) <= 100:
        return {"intent":"system","action":"set_volume" if nivel[1] == "volumen" else "set_brightness",
                "params":{"level":int(nivel[2])},"response":"","confidence":1.0}
    relativo = re.fullmatch(r"(sube|baja|aumenta|reduce) (?:el )?volumen(?: en)? (\d{1,3})(?:\s*%| por ciento)?",plain)
    if relativo and 0 < int(relativo[2]) <= 100:
        signo = -1 if relativo[1] in {"baja","reduce"} else 1
        return {"intent":"system","action":"set_volume","params":{"level":signo*int(relativo[2]),"mode":"relative"},"response":"","confidence":1.0}
    if re.fullmatch(r"(?:dime |cual es |a cuanto esta )?(?:el )?volumen(?: actual)?",plain):
        return {"intent":"system","action":"get_volume","params":{},"response":"","confidence":1.0}

    # El reloj solo consume preguntas completas; nunca una subcadena de otra tarea.
    if not re.fullmatch(r"(?:que hora (?:es|son|tienes|tenemos)(?: ahora| hoy)?|(?:dime|dame) la hora|la hora|(?:que|en que) (?:dia|fecha)(?: de la semana)?(?: es| estamos| es hoy| estamos hoy)?|a que dia estamos|fecha de hoy|(?:dime|dame) (?:la fecha|el dia de la semana))",plain):
        return None

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
