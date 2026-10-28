# Lane compuesto `desktop_task`

Implementado (F1): 2026-10-27 — loop tipado con Ollama.  
**Objetivo actual:** Agent vía OpenCode Flash + fallback Ollama 3b — ver [`plan-desktop-task-calidad.md`](plan-desktop-task-calidad.md).

El clasificador strict **sigue estricto**; solo elige `desktop_task` en frases multi-paso (o bypass por keywords). El análisis lo hace un loop aparte (`modules/desktop_agent.py`) sobre tools tipadas — **no** afloja el router global.

## Arquitectura objetivo (sin Groq)

```
voz/texto
  ├─ match_desktop_task_route (keywords "y cópialo"/"y muévelo"/…)
  │     → desktop_task directo
  └─ LLM router Ollama 1.5b → action=desktop_task | search_and_open | …
         → DesktopAgent.run(goal)
              loop ≤ DESKTOP_AGENT_MAX_STEPS:
                1) OpenCode deepseek-v4.1-flash-free → {"tool","args"}
                2) fallback Ollama 3b si falla
                FileCommands.* o propose_move/rename
              → texto para TTS
```

| Rol | Motor |
|---|---|
| Intents atómicos | Ollama `qwen2.5:1.5b-instruct` |
| Agent multi-paso | OpenCode `opencode/deepseek-v4.1-flash-free` |
| Fallback Agent | Ollama `qwen2.5:3b-instruct` |
| Research/charla | Gemini (`gemdev`) |

**No usar:** Groq, Big Pickle (stealth rotatorio), segundo modelo 7b residente en la 1650 4 GB.

## Tools permitidas

| Tool | Efecto |
|---|---|
| search_file / search_and_open / open_file / reveal_file / copy_file / list_directory | Ejecutan ya |
| propose_move / propose_rename | Dejan `_pending_action` → confirm/cancel |
| ask_user / done | Terminan el turno |

Prohibido: shell libre, `rm`, paths no observados en el turno.

## Config (objetivo)

| Variable | Rol |
|---|---|
| `OLLAMA_MODEL` | Router (1.5b) |
| `DESKTOP_AGENT_PROVIDER` | `opencode` \| `ollama` |
| `OPENCODE_API_KEY` / `OPENCODE_BASE_URL` / `OPENCODE_AGENT_MODEL` | Agent cloud |
| `DESKTOP_AGENT_MODEL` | Fallback Ollama (3b) |
| `DESKTOP_AGENT_FALLBACK` | `ollama` \| `off` |
| `DESKTOP_AGENT_MAX_STEPS` | default 6 |

Implementado plan 2: Agent usa OpenCode por defecto; Ollama 3b como fallback
(`DESKTOP_AGENT_MODEL`). El router de intents sigue en `OLLAMA_MODEL` (1.5b).

## Seguridad / privacidad

- Misma superficie tipada (sin `shell=True`).
- Move/rename → confirmación verbal.
- Overwrite rechazado en copy/move/rename.
- Con provider OpenCode: **rutas locales viajan a la API**; no enviar contenidos de archivo.
- Preferir Flash free pineado; documentar cupo free y fallback obligatorio.
