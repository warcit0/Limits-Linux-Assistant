"""Grounding determinista (P1): ¿la acción elegida responde a la frase?

El modelo propone un intent; este módulo **verifica** que sea cierto antes de
que el executor toque nada. Tres comprobaciones, todas sin red y testeables:

1. **Catálogo**: la acción debe existir en el `action_map` real.
2. **Evidencia por dominio**: la frase debe contener alguna palabra del dominio
   de la acción (`get_system_info` ← ram/disco/cpu…). Con exclusiones para no
   secuestrar preguntas ajenas («¿a qué hora abre el banco?» no es `get_time`).
3. **Enums**: parámetros cerrados validados y, cuando el error es típico,
   reparados por alias (`free_space` → `disk`).

Regla de oro: si no se puede demostrar que la acción encaja, **no se ejecuta**.
El executor responde con honestidad en vez de inventarse un «hecho».
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

# Acciones que no tocan nada: solo hablan. `None`/"" = el modelo no eligió acción.
CHAT_ACTIONS = frozenset({"", "none", "null", "unknown", "speak_error", "chat"})

# Acción → palabras que deben aparecer en la frase (regex, sin acentos).
# Solo se listan las acciones donde una elección equivocada es plausible o
# dañina; el resto no se restringe para no bloquear órdenes legítimas.
ACTION_HINTS: dict[str, tuple[str, ...]] = {
    "get_system_info": (
        r"ram", r"memoria", r"procesador", r"cpu", r"\bgpu\b", r"grafica",
        r"disco", r"espacio", r"almacenamiento", r"hardware", r"temperatura",
        r"bateria", r"kernel", r"sistema",
    ),
    "get_time": (
        r"\bhora\b", r"que hora", r"\bfecha\b", r"que dia", r"\bsemana\b",
        r"\blunes\b", r"\bmartes\b", r"\bmiercoles\b", r"\bjueves\b",
        r"\bviernes\b", r"\bsabado\b", r"\bdomingo\b",
    ),
    "set_volume": (r"volumen",),
    "get_volume": (r"volumen",),
    "set_brightness": (r"brillo",),
    "take_screenshot": (r"captura", r"screenshot", r"pantallazo"),
    "media_control": (
        r"pausa", r"reanuda", r"siguiente", r"anterior", r"reproduce",
        r"reproducir", r"para la musica", r"deten", r"\bstop\b", r"\bplay\b",
    ),
    "get_lyrics": (r"\bletra",),
    "get_current_song": (
        r"cancion", r"suena", r"sonando", r"reproduciendo", r"\btema\b",
        r"\bmusica\b",
    ),
    "spotify_play": (r"spotify", r"\bmusica\b", r"cancion", r"ponme"),
    "youtube_play": (r"youtube", r"video"),
    "web_search": (r"busca", r"buscar", r"buscame", r"google", r"internet",
                   r"\bweb\b", r"en la red"),
    "search_file": (r"archivo", r"fichero", r"carpeta", r"directorio",
                    r"extension", r"\.\w{1,5}\b"),
    "search_and_open": (r"archivo", r"fichero", r"carpeta", r"directorio",
                        r"extension", r"\.\w{1,5}\b"),
    "open_file": (r"archivo", r"fichero"),
    "list_directory": (r"carpeta", r"directorio", r"listame"),
    "copy_file": (r"copia", r"copiar"),
    "move_file": (r"mueve", r"mover"),
    "rename_file": (r"renombra", r"renombrar"),
    "git_status": (r"\bgit\b",),
    "docker_status": (r"docker",),
    "open_project": (r"proyecto",),
    "list_running": (r"abiertas", r"corriendo", r"ejecutando", r"procesos"),
    "lock_screen": (r"bloquea", r"bloquear", r"cierra la sesion"),
    "shutdown": (r"apaga", r"apagar"),
    "reboot": (r"reinicia", r"reiniciar"),
    "tv_cast": (r"\btele\b", r"\btv\b", r"chromecast", r"castea"),
    "tv_control": (r"\btele\b", r"\btv\b", r"chromecast"),
    "list_tvs": (r"\btele\b", r"\btv\b", r"chromecast"),
    "run_terminal_command": (r"ejecuta", r"terminal", r"comando", r"\bshell\b"),
    # Lane Gemini: research abre el CLI y gasta cuota; exige señal de
    # investigación. `gemini_talk` es charla y no se restringe.
    "gemini_research": (
        r"investiga", r"investigacion", r"informe", r"novedades",
        r"busca en internet", r"en la web", r"que se sabe", r"documenta",
    ),
}

# Frases que se parecen al dominio pero no lo son: se bloquean aunque la
# evidencia esté presente («¿a qué hora abre el banco?» contiene «hora»).
ACTION_EXCLUDES: dict[str, tuple[str, ...]] = {
    "get_time": (
        r"a que hora (abre|abren|cierra|cierran|empieza|empiezan|sale|salen|"
        r"llega|llegan|termina|terminan)",
        r"horario",
    ),
    "get_system_info": (r"a que hora",),
    "get_current_song": (r"que cancion (me )?recomiendas",),
}

# Parámetros con valores cerrados (los que el LLM más suele inventar).
PARAM_ENUMS: dict[str, dict[str, tuple[str, ...]]] = {
    "get_system_info": {"type": ("memory", "cpu", "disk", "all")},
    "get_time": {"detail": ("time", "date", "weekday", "all")},
    "media_control": {"action": ("play", "pause", "play-pause", "next",
                                 "previous", "stop")},
    "set_volume": {"mode": ("absolute", "relative")},
    "web_search": {"engine": ("google", "duckduckgo", "youtube", "github")},
    "tv_control": {"action": ("play", "pause", "stop", "next", "previous",
                              "volume_up", "volume_down")},
}

# Errores típicos del modelo → valor válido del enum.
PARAM_ALIASES: dict[tuple[str, str], dict[str, str]] = {
    ("get_system_info", "type"): {
        "free_space": "disk", "espacio": "disk", "disco": "disk",
        "ram": "memory", "memoria": "memory", "free": "disk",
        "procesador": "cpu", "gpu": "all", "bateria": "all",
        "time": "all", "hora": "all",
    },
    ("get_time", "detail"): {"hora": "time", "fecha": "date", "dia": "date"},
    ("media_control", "action"): {
        "resume": "play", "reanudar": "play", "pausar": "pause",
        "siguiente": "next", "anterior": "previous", "detener": "stop",
        "play_pause": "play-pause", "toggle": "play-pause",
    },
    ("set_volume", "mode"): {"absoluto": "absolute", "relativo": "relative"},
    ("web_search", "engine"): {
        "ddg": "duckduckgo", "duck": "duckduckgo", "yt": "youtube",
        "gh": "github",
    },
}


def fold(text: str) -> str:
    """Minúsculas, sin acentos y con espacios simples."""
    nfkd = unicodedata.normalize("NFKD", str(text))
    plain = "".join(c for c in nfkd if not unicodedata.combining(c)).casefold()
    return re.sub(r"\s+", " ", plain).strip()


@dataclass
class Verdict:
    """Resultado del grounding; `params` puede venir reparado por alias."""

    ok: bool
    reason: str = ""
    action: str = ""
    params: dict = field(default_factory=dict)


def check(action, params, text: str, known_actions=None) -> Verdict:
    """Decide si `action` responde a `text`.

    Args:
        known_actions: nombres reales del `action_map`. `None` desactiva la
                       comprobación de catálogo (tests unitarios del resto).
    """
    action = "" if action is None else str(action)
    params = dict(params) if isinstance(params, dict) else {}
    folded = fold(text)

    # ── Charla: no ejecuta nada, pero tampoco puede traer params de acción ──
    if action in CHAT_ACTIONS or action == "unknown":
        if params:
            # «estoy cansado» → params {app: spotify} y «Trayendo Spotify»:
            # el modelo se quedó a mitad de una acción. Mejor preguntar.
            return Verdict(False, "accion_sin_nombre", action, params)
        return Verdict(True, "chat", action, params)

    if known_actions is not None and action not in known_actions:
        return Verdict(False, "accion_desconocida", action, params)

    # ── Enums (con reparación por alias) ────────────────────────────────────
    for key, allowed in PARAM_ENUMS.get(action, {}).items():
        if key not in params:
            continue
        raw = fold(params[key]).replace(" ", "_")
        if not raw:
            params.pop(key, None)
            continue
        by_value = {fold(v).replace(" ", "_"): v for v in allowed}
        if raw in by_value:
            params[key] = by_value[raw]
            continue
        alias = PARAM_ALIASES.get((action, key), {}).get(raw)
        if alias:
            params[key] = alias
            continue
        return Verdict(False, f"param_invalido:{key}", action, params)

    # ── Dominio: exclusiones primero, luego evidencia ───────────────────────
    for bad in ACTION_EXCLUDES.get(action, ()):
        if re.search(bad, folded):
            return Verdict(False, "fuera_de_dominio", action, params)

    hints = ACTION_HINTS.get(action)
    if hints and not any(re.search(h, folded) for h in hints):
        return Verdict(False, "sin_evidencia", action, params)

    return Verdict(True, "ok", action, params)
