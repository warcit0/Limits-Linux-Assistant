"""Utilidades compartidas de preparación de texto para síntesis de voz.

Las usan todos los motores TTS (Piper hoy, ElevenLabs mañana el puente Gemini).
Objetivo: que lo hablado suene natural aunque la fuente tenga markdown, URLs
o sea más larga que el tope por turno.
"""

import re

# Pre-compiladas (se llaman en cada turno)
_FENCE_PAIR = re.compile(r"```[ \t]*[a-zA-Z0-9_+-]*[ \t]*\n?(.*?)```", re.DOTALL)
_FENCE_LONE = re.compile(r"```+")
_INLINE_CODE = re.compile(r"`([^`]*)`")
_BOLD_ITALIC = re.compile(r"\*\*([^*]+)\*\*|\*([^*]+)\*|__([^_]+)__|_([^_]+)_")
_HEADER = re.compile(r"^#{1,6}\s+", re.MULTILINE)
_LINK = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_URL = re.compile(r"https?://([A-Za-z0-9.-]+)[^\s)]*")
_BULLET = re.compile(r"^[\-\*•]\s+", re.MULTILINE)
_MULTISPACE = re.compile(r"[ \t]+")
_MULTINEWLINE = re.compile(r"\n{3,}")


def clean_for_voice(text: str) -> str:
    """Convierte texto 'de pantalla' (markdown, URLs) en texto hablado."""
    if not text:
        return ""
    out = _FENCE_PAIR.sub(r"\1", text)                 # conserva el contenido
    out = _FENCE_LONE.sub("", out)                     # fences sin pareja
    out = _INLINE_CODE.sub(r"\1", out)
    out = _BOLD_ITALIC.sub(lambda m: next(g for g in m.groups() if g), out)
    out = _HEADER.sub("", out)
    out = _LINK.sub(r"\1", out)
    # URL → "enlace a dominio" (leer una URL cruda en voz alta es insufrible)
    out = _URL.sub(lambda m: f" enlace a {m.group(1)} ", out)
    out = _BULLET.sub("", out)
    out = _MULTISPACE.sub(" ", out)
    out = _MULTINEWLINE.sub("\n\n", out)
    return out.strip()


_SENTENCE_END = re.compile(r"[.!?…]+[\s\n]+|\n+")


def split_for_voice(text: str, max_chars: int) -> tuple[str, str]:
    """Divide texto en dos partes sin cortar frases por la mitad.

    Returns:
        (primera, resto): primera cabe en max_chars cortando en el límite de
        frase más cercano; si una sola frase excede max_chars, corte duro en el
        último espacio antes del límite. resto es "" si no hace falta dividir.
    """
    text = text.strip()
    if max_chars <= 0 or len(text) <= max_chars:
        return text, ""

    # Último límite de frase dentro del límite
    best = 0
    for m in _SENTENCE_END.finditer(text, 0, max_chars):
        best = m.end()

    cut = best
    if cut == 0:
        # Frase gigante: corte duro en el último espacio antes del límite
        cut = text.rfind(" ", 0, max_chars)
        if cut <= 0:
            cut = max_chars

    return text[:cut].strip(), text[cut:].strip()
