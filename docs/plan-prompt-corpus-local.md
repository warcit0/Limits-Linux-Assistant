# Plan 4 — Prompt slim + corpus (sin Groq)

**Estado:** implementado (2026-10-27)  
**Objetivo:** mantener el router local preciso al crecer el catálogo, sin volver al prompt de 9KB que estrangulaba el modelo.

## Problema

- Cada action nueva compite por atención del 1.5b/3b.
- `measure-router` existe pero no está en el flujo habitual pre-commit.
- Follow-ups (“muéstramelo”) y paths acotados aún débiles en few-shots (depende del plan 1).

## Alcance

### 4.1 Disciplina del prompt

- Regla: 1 action nueva → 1 few-shot máximo; si el prompt supera ~6KB, fusionar/retirar ejemplos de baja frecuencia (TV, gemini) a doc completa.
- Mantener reglas 6–8 (archivo vs web, desktop_task, follow-ups) visibles arriba del ruido.

### 4.2 Corpus vivo

- Extender `tests/corpus_ordenes.json` con follow-ups y “busca en Proyectos/…”.
- `./bin/measure-router` con `LLM_PRIORITY=local` (única vía).
- Umbral: fallar CI local / pre-commit manual si accuracy < 90% en el corpus.

### 4.3 Checklist en AGENTS.md

```bash
./limits-env/bin/python -m py_compile main.py config.py modules/*.py commands/*.py
./limits-env/bin/python -m unittest discover -s tests -v
./bin/measure-router   # requiere Ollama arriba
```

## Criterio de hecho

- Corpus ≥ 25 frases; accuracy local documentada en `logs/measure_router_last.json`.
- AGENTS.md lista el checklist; un contribuidor puede reproducir sin Groq.

## Orden

1. Ampliar corpus (tras plan 1)  
2. Umbral + nota en AGENTS  
3. Dieta puntual del prompt si measure baja  
