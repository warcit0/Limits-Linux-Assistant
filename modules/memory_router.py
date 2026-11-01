"""Router determinista de memoria (P0-3).

«Recuerda que X es Y», «olvida X» y «¿qué sabes de mí?» son mecánicos: no
necesitan LLM y no deben poder alucinar. Si la frase no encaja, decide el LLM.

Trampa: «recuerda apagar la luz» no es un hecho («falta el *que*»). Se exige
`recuerda que …` para guardar; `apunta/anota` sí aceptan nota libre.
"""

from __future__ import annotations

import re

_REMEMBER_QUE = re.compile(
    r"^\s*(?:recuerda(?:me)?|acu[eé]rdate(?:\s+de)?)\s+que\s+(.+?)[\s.!?]*$",
    re.IGNORECASE)

_REMEMBER_FREE = re.compile(
    r"^\s*(?:apunta|anota|ten\s+presente)\s+(?:que\s+)?(.+?)[\s.!?]*$",
    re.IGNORECASE)

_FORGET = re.compile(
    r"^\s*(?:olvida(?:te)?(?:\s+de)?|borra(?:\s+de\s+tu\s+memoria)?|"
    r"quita\s+de\s+tu\s+memoria)\s+(.+?)[\s.!?]*$",
    re.IGNORECASE)

_KNOW_ALL = re.compile(
    r"^\s*¿?\s*(?:qu[eé]\s+sabes\s+de\s+m[ií]|qu[eé]\s+recuerdas|"
    r"qu[eé]\s+tienes\s+apuntado|qu[eé]\s+memoria\s+tienes|"
    r"mu[eé]strame\s+tu\s+memoria)\s*\??\s*$",
    re.IGNORECASE)

_KNOW_ABOUT = re.compile(
    r"^\s*¿?\s*qu[eé]\s+(?:sabes|recuerdas)\s+(?:de|sobre)\s+(.+?)\s*\??\s*$",
    re.IGNORECASE)

# «¿cuál es mi proyecto principal?» → consulta directa a la memoria.
_WHICH = re.compile(
    r"^\s*¿?\s*cu[aá]l(?:es)?\s+(?:es|son|era|eran)\s+(?:mi|mis)\s+(.+?)\s*\??\s*$",
    re.IGNORECASE)

# «X es Y» → hecho con clave; si no, nota libre.
_FACT = re.compile(r"^(.+?)\s+(?:es|son)\s+(.+)$", re.IGNORECASE)


def _route(action: str, params: dict, intent: str) -> dict:
    return {
        "intent": intent,
        "action": action,
        "params": params,
        "response": "",
        "confidence": 1.0,
    }


def match_memory_route(text: str) -> dict | None:
    """Devuelve un `parsed_result` de memoria, o None si no es una orden suya."""
    if not text or not text.strip():
        return None
    raw = text.strip()

    if _KNOW_ALL.match(raw):
        return _route("memory_list", {}, "memory_list")

    about = _KNOW_ABOUT.match(raw)
    if about:
        query = about.group(1).strip()
        if query.casefold() in ("mi", "mí"):
            return _route("memory_list", {}, "memory_list")
        return _route("memory_recall", {"query": query}, "memory_recall")

    which = _WHICH.match(raw)
    if which:
        return _route("memory_recall", {"query": which.group(1).strip()},
                      "memory_recall")

    forget = _FORGET.match(raw)
    if forget:
        return _route("forget", {"key": forget.group(1).strip()}, "memory_forget")

    remember = _REMEMBER_QUE.match(raw) or _REMEMBER_FREE.match(raw)
    if remember:
        content = remember.group(1).strip()
        fact = _FACT.match(content)
        if fact:
            return _route("remember",
                          {"key": fact.group(1).strip(),
                           "value": fact.group(2).strip()},
                          "memory_remember")
        return _route("remember", {"key": "", "value": content},
                      "memory_remember")

    return None
