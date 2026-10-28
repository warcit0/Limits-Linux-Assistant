"""Fuente única de verdad temporal para Limits.

El prompt se renderiza por turno con `{now}`: si el servicio lleva días vivo,
la hora debe ser la de ahora. Sin `locale` (el servicio no garantiza LANG).
"""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

_DIAS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
_MESES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
          "agosto", "septiembre", "octubre", "noviembre", "diciembre")


def _plain(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", str(text))
    return "".join(c for c in nfkd if not unicodedata.combining(c)).casefold()


def _now(tz: str | None = None, now: datetime | None = None) -> datetime:
    if now is not None:
        return now
    if tz:
        try:
            return datetime.now(ZoneInfo(tz))
        except Exception:
            pass  # zona inválida → local
    return datetime.now().astimezone()


def _offset(dt: datetime) -> str:
    total = int(dt.utcoffset().total_seconds()) if dt.utcoffset() else 0
    sign = "+" if total >= 0 else "-"
    hh, mm = divmod(abs(total) // 60, 60)
    return f"UTC{sign}{hh:02d}:{mm:02d}"


def now_line(tz: str | None = None, now: datetime | None = None) -> str:
    """'miércoles 28 de octubre de 2026, 16:55 (UTC-06:00)'."""
    dt = _now(tz, now)
    return (f"{_DIAS[dt.weekday()]} {dt.day} de {_MESES[dt.month - 1]} "
            f"de {dt.year}, {dt:%H:%M} ({_offset(dt)})")


def time_line(tz: str | None = None, now: datetime | None = None) -> str:
    dt = _now(tz, now)
    return f"Son las {dt:%H:%M}."


def date_line(tz: str | None = None, now: datetime | None = None) -> str:
    dt = _now(tz, now)
    return (f"Hoy es {_DIAS[dt.weekday()]} {dt.day} de "
            f"{_MESES[dt.month - 1]} de {dt.year}.")


def weekday_line(tz: str | None = None, now: datetime | None = None) -> str:
    return f"Hoy es {_DIAS[_now(tz, now).weekday()]}."


_UNIDADES = {
    "s": "seconds", "seg": "seconds", "segundo": "seconds", "segundos": "seconds",
    "m": "minutes", "min": "minutes", "minuto": "minutes", "minutos": "minutes",
    "h": "hours", "hora": "hours", "horas": "hours",
    "d": "days", "dia": "days", "dias": "days",
    "semana": "weeks", "semanas": "weeks",
}

_NUMEROS = {
    "un": 1, "una": 1, "uno": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5,
    "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10, "quince": 15,
    "veinte": 20, "treinta": 30, "media": 0.5, "medio": 0.5,
}


def parse_duration(text: str) -> timedelta | None:
    """
    '20 minutos' → 20 min · 'media hora' → 30 min · 'en 2 días' → 2 días.
    Devuelve None si no hay una duración reconocible. Lo usará P1 (recordatorios).
    """
    if not text:
        return None
    plain = _plain(text)
    match = re.search(
        r"(?:en\s+)?(\d+(?:[.,]\d+)?|" + "|".join(_NUMEROS) + r")\s*"
        r"(s|seg|segundos?|min|minutos?|h|horas?|d|dias?|semanas?)\b",
        plain)
    if not match:
        return None
    raw, unit = match.group(1).replace(",", "."), match.group(2)
    amount = float(raw) if raw[0].isdigit() else _NUMEROS[raw]
    field = _UNIDADES[unit]
    return timedelta(**{field: amount})
