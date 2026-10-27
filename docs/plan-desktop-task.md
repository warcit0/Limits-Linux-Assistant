# Lane compuesto `desktop_task`

Implementado: 2026-10-27. El clasificador strict **sigue estricto**; solo elige
`desktop_task` cuando la frase es multi-paso. El análisis lo hace un loop
aparte (`modules/desktop_agent.py`) sobre tools tipadas.

## Flujo

```
voz/texto
  ├─ match_desktop_task_route (keywords "y cópialo"/"y muévelo"/…)
  │     → desktop_task directo
  └─ LLM router (JSON) → action=desktop_task | search_and_open | …
         → DesktopAgent.run(goal) si desktop_task
              loop ≤ DESKTOP_AGENT_MAX_STEPS:
                Ollama/Qwen → {"tool","args"}
                FileCommands.* o propose_move/rename
              → texto para TTS
```

## Tools permitidas

| Tool | Efecto |
|---|---|
| search_file / search_and_open / open_file / reveal_file / copy_file / list_directory | Ejecutan ya |
| propose_move / propose_rename | Dejan `_pending_action` → confirm/cancel |
| ask_user / done | Terminan el turno |

Prohibido: shell libre, `rm`, paths inventados (el prompt del agent lo dice;
las tools validan existencia).

## Config

- Usa `OLLAMA_URL` / `OLLAMA_MODEL` / `OLLAMA_NUM_CTX` / `OLLAMA_KEEP_ALIVE`
- `DESKTOP_AGENT_MAX_STEPS` (default 6) en `.env`

## Seguridad

- Misma superficie que los handlers atómicos (sin `shell=True`)
- Move/rename atómicos también están en `DANGEROUS_ACTIONS`
- Overwrite rechazado en copy/move/rename
