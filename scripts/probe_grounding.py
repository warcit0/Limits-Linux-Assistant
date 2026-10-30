#!/usr/bin/env python3
"""Sonda de grounding: 8 frases que antes ejecutaban (o callaban) mal.

No ejecuta handlers: pasa cada frase por el router real (con el catálogo real)
y muestra qué acción propone, si el grounding la acepta y qué se diría.

Uso:
  ./limits-env/bin/python scripts/probe_grounding.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Frases de la sonda original (docs/plan-p1-grounding.md §Sonda real).
PHRASES = [
    "¿a qué hora abre el banco?",
    "ponme música relajante",
    "¿cuánto espacio libre me queda?",
    "estoy cansado",
    "¿qué canción suena?",
    "busca las llaves",
    "tradúceme buenos días al inglés",
    "hazme un resumen de la II Guerra Mundial",
]


def main() -> int:
    from config import Config
    from modules.app_router import match_app_route
    from modules.executor import CommandExecutor
    from modules.file_router import match_file_route
    from modules.llm import LLMEngine
    from modules.media_router import match_media_route

    config = Config()
    executor = CommandExecutor()
    known = frozenset(executor.action_map) | {"confirm", "cancel"}
    llm = LLMEngine(config, actions=known)

    print(f"modelo: {config.OLLAMA_MODEL} | {len(PHRASES)} frases")
    print("-" * 78)
    malos = 0
    routes = (match_file_route, match_app_route, match_media_route)
    for phrase in PHRASES:
        out = next((r for m in routes if (r := m(phrase))), None) or llm.process(phrase)
        action = out.get("action")
        grounded = out.get("grounded")
        reason = out.get("grounding_reason", "")
        response = (out.get("response") or "").strip()
        if grounded is False:
            verdict = f"BLOQUEADA ({reason})"
        elif action:
            verdict = f"ejecutaría {action}"
        else:
            verdict = "charla"
        # «Malo» = ejecutaría algo o respondería en silencio.
        if grounded is not False and not response:
            malos += 1
            verdict += " ⚠️ SILENCIO"
        print(f"{verdict:34} | responde: {response[:60]!r}")
        print(f"{'':34} | {phrase}")
    print("-" * 78)
    print(f"silencios: {malos}")
    return 1 if malos else 0


if __name__ == "__main__":
    raise SystemExit(main())
