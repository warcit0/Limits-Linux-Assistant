"""Router determinista de música (sin LLM).

«pausa la música», «siguiente», «ponme música relajante» son las órdenes más
repetidas del asistente y no necesitan un modelo de 1,5B para acertar. Aquí se
resuelven en ~0 ms contra `commands/media.py`.

Si la frase no encaja (o es compuesta: «pon música y baja el volumen»), devuelve
None y decide el LLM. Nunca inventamos una query.
"""

from __future__ import annotations

import re
import unicodedata


def _plain(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", str(text))
    return "".join(c for c in nfkd if not unicodedata.combining(c)).casefold().strip()


# Frases que NO son del lane de música aunque contengan «música»/«spotify».
_EXCLUDE = re.compile(
    r"\b(en pantalla|al frente|volumen|brillo|cancion actual|que cancion|"
    r"letra|tele|tv|chromecast)\b"
)

# Control de reproducción: frases cortas y cerradas.
_CONTROL = (
    (re.compile(r"^(pausa|pausar|pausala|pon pausa)(\s+(la\s+)?"
                r"(musica|cancion|spotify))?$"), "pause"),
    (re.compile(r"^(reanuda|reanudar|continua|continua la|sigue|dale)"
                r"(\s+(la\s+)?(musica|cancion|spotify|reproduccion(?: de spotify)?))?$"), "play"),
    (re.compile(r"^(siguiente|next|otra)(\s+(cancion|tema))?$"), "next"),
    (re.compile(r"^(anterior|previous|previa)(\s+(cancion|tema))?$"), "previous"),
    (re.compile(r"^(para|deten|detiene|stop)(\s+(la\s+)?"
                r"(musica|cancion|spotify))?$"), "stop"),
)

_CONTROL_SAYS = {
    "pause": "Pausando.",
    "play": "Reanudando.",
    "next": "Siguiente.",
    "previous": "Anterior.",
    "stop": "Parando la música.",
}

# «pon (a) X en spotify» / «ponme música relajante» / «reproduce X».
# Se aplica al texto ORIGINAL para conservar mayúsculas y acentos en la query.
_PLAY = re.compile(
    r"^\s*(pon|ponme|ponle|reproduce|reproduceme|escucha|quiero\s+escuchar)"
    r"\s+(?P<q>.+?)\s*[.!?¡¿]*$",
    re.IGNORECASE,
)
_SPOTIFY_TAIL = re.compile(r"\s+en\s+spotify\s*$", re.IGNORECASE)
_YOUTUBE_TAIL = re.compile(r"\s+en\s+youtube\s*$", re.IGNORECASE)
_ARTICLE = re.compile(r"^(a|al|el|la|los|las)\s+", re.IGNORECASE)


def _play(query: str, platform: str) -> dict:
    intent = "spotify_play" if platform == "spotify" else "youtube_play"
    return {
        "intent": intent,
        "action": intent,
        "params": {"query": query},
        "response": f"Buscando {query}.",
        "confidence": 1.0,
    }


def match_media_route(text: str) -> dict | None:
    """Devuelve un `parsed_result` de música, o None."""
    if not text or not text.strip():
        return None
    plain = _plain(text).strip(" .!?¡¿,;:")
    if not plain or " y " in plain or _EXCLUDE.search(plain):
        return None

    if re.fullmatch(r"(?:reproduce|reproducir) (?:la )?musica", plain):
        return {"intent":"media_control", "action":"media_control", "params":{"action":"play", "verify":True}, "response":"", "confidence":1.0}

    for pattern, action in _CONTROL:
        if pattern.search(plain):
            return {
                "intent": "media_control",
                "action": "media_control",
                "params": {"action": action},
                # Nunca vacío: `media_control` devuelve None y el executor
                # necesita texto o responde «no te he entendido».
                "response": _CONTROL_SAYS[action],
                "confidence": 1.0,
            }

    match = _PLAY.search(text)
    if not match:
        return None

    query = match.group("q").strip().strip(" .!?¡¿,;:")
    platform = "spotify"
    if _YOUTUBE_TAIL.search(query):
        platform, query = "youtube", _YOUTUBE_TAIL.sub("", query)
    elif _SPOTIFY_TAIL.search(query):
        query = _SPOTIFY_TAIL.sub("", query)
    elif not re.search(r"\b(musica|spotify|cancion|tema|artista|album)\b",
                       _plain(query)):
        # «pon la mesa» no es música: que decida el LLM.
        return None

    query = _ARTICLE.sub("", query).strip()
    if not query:
        return None
    return _play(query, platform)
