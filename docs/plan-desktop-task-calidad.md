# Plan 2 — Agent `desktop_task` vía OpenCode (sin Groq, sin dual-VRAM)

**Estado:** implementado (2026-10-27) — OpenCode primario + fallback Ollama 3b  
**Doc base:** [`plan-desktop-task.md`](plan-desktop-task.md)  
**Hardware:** GTX 1650 4 GB — no cabe un segundo modelo Ollama residente.

## Decisión de diseño (fijada)

| Rol | Motor | Modelo |
|---|---|---|
| Router de intents (atómico, 1 JSON) | Ollama local | `qwen2.5:1.5b-instruct` (rápido, VRAM ~1.4 GB) |
| Agent compuesto (`desktop_task`) | **OpenCode API** | `opencode/deepseek-v4.1-flash-free` (pineado) |
| Fallback del Agent | Ollama | `qwen2.5:3b-instruct` si falla red/cuota/auth |
| Investigación / charla | Gemini (`gemdev`) | sin cambios |

- **Groq:** fuera de la ecuación (router y agent).
- **Big Pickle:** no usar — stealth que rota de backend; no reproducible.
- **No** cargar 1.5b + 7b a la vez. El Agent cloud no toca VRAM.

```
órdenes simples     → Ollama 1.5b
desktop_task        → OpenCode deepseek-v4.1-flash-free
                     └ fallback → Ollama 3b
investiga/infórmame → Gemini
```

## Problema que resuelve

- El 1.5b como planificador de tools inventa paths / hace `done` prematuro.
- Swap local 1.5b↔7b en 4 GB es lento e inestable.
- OpenCode Flash da calidad tipo “Groq agent” sin pelear GPU; la latencia extra solo en multi-paso (poco frecuente).

## Alcance

### 2.1 Cliente OpenCode en `DesktopAgent`

- Endpoint OpenAI-compatible: `https://opencode.ai/inference/openai/v1/chat/completions`
- Auth: API key OpenCode (Zen/console) en `.env` — **nunca** en logs/git.
- Modelo default: `opencode/deepseek-v4.1-flash-free` (ID exacto según `opencode models`).
- `format`/prompt: mismo contrato JSON `{"tool","args"}` que hoy; temperatura baja; extracción defensiva (`_extract_json`).
- Timeout por paso + reintento único ante vacío/HTML/error HTTP.

Variables nuevas (propuesta):

| Env | Default | Uso |
|---|---|---|
| `DESKTOP_AGENT_PROVIDER` | `opencode` | `opencode` \| `ollama` |
| `OPENCODE_API_KEY` | *(vacío)* | Bearer |
| `OPENCODE_BASE_URL` | `https://opencode.ai/inference/openai/v1` | override |
| `OPENCODE_AGENT_MODEL` | `opencode/deepseek-v4.1-flash-free` | pineado |
| `DESKTOP_AGENT_FALLBACK` | `ollama` | `ollama` \| `off` |
| `DESKTOP_AGENT_MODEL` | `qwen2.5:3b-instruct` | solo fallback Ollama |
| `DESKTOP_AGENT_MAX_STEPS` | `6` | sin cambio |

Router sigue en `OLLAMA_MODEL` (1.5b). No reintroducir Groq.

### 2.2 Cadena de fallback

1. Si `DESKTOP_AGENT_PROVIDER=opencode` y hay key → OpenCode.  
2. Fallo de red / 401 / 429 / JSON inválido tras reintento → log WARN + Ollama 3b si fallback activo.  
3. Si ambos fallan → TTS: “No pude completar la tarea de archivos ahora.”

### 2.3 Contrato del loop (igual de estricto)

- Paths absolutos solo desde observaciones de tools.
- N>1 matches → `ask_user`; no abrir/copiar a ciegas.
- Guard en código: `open`/`copy`/`reveal` solo si path ∈ set observado en el turno.
- `propose_move` / `propose_rename` → pending confirm/cancel (sin ejecutar en el loop).
- Tope de pasos + mensaje claro.

### 2.4 Privacidad y cuota

- El Agent cloud **ve rutas locales** (nombres de archivo). Documentar en README/AGENTS.
- Preferir Flash free (zero-retention según docs OpenCode) sobre Big Pickle (puede usarse para entrenar).
- Free tier “por tiempo limitado”: el fallback 3b no es opcional en producción casera.
- No enviar contenidos de archivo (solo paths + resultados cortos de tools).

### 2.5 Corpus E2E y benchmark

- `tests/corpus_desktop_task.json` + mocks HTTP OpenCode (sin red en CI).
- Smoke opcional: `LIMITS_E2E_OPENCODE=1` → 1 goal real; registrar p50 ms/paso en este doc.
- Criterio previo a merge: p50/paso Agent &lt; ~5 s en red normal; si no, documentar y valorar `provider=ollama` 3b por defecto.

### 2.6 Docs / limpieza Groq en este lane

- Actualizar [`plan-desktop-task.md`](plan-desktop-task.md), `.env.example`, `AGENTS.md`.
- `DesktopAgent._query_ollama` queda como fallback; añadir `_query_opencode`.
- No usar `opencode run` CLI dentro de Limits (proceso pesado); solo HTTP.

## Fuera de alcance

- Sustituir el router 1.5b por OpenCode (mata latencia de órdenes simples).
- Big Pickle / modelos stealth.
- Reintroducir Groq.
- Tipar en apps (plan 5).

## Criterio de hecho

- `desktop_task` con OpenCode Flash: ≥4/5 goals del corpus E2E (mock + 1 smoke manual).
- Sin key / sin red → fallback 3b o mensaje de fallo explícito (no cuelgue).
- Router `measure-router` local ≥90% (sin OpenCode en el hot path).
- Cero path inventado ejecutado (guard).
- VRAM: durante Agent, GPU sigue con ~1.5b o libre; no carga 7b.

## Orden de implementación

1. Env + cliente OpenCode en `modules/desktop_agent.py` + tests HTTP mock  
2. Cadena fallback Ollama 3b  
3. Guard de paths observados  
4. Smoke latencia real; anotar números abajo  
5. Actualizar `.env.example` / AGENTS / plan-desktop-task.md  

## Benchmark (smoke 2026-10-27)

| Motor | Pasos | p50 ms/paso | Notas |
|---|---|---|---|
| OpenCode deepseek-v4.1-flash-free | 1 | ~236 ms hasta 429 | HTTP **429** rate-limit en smoke; fallback obligatorio |
| Ollama 3b fallback | loop corto | ver smoke local | Usado cuando OpenCode falla (401/429/red) |
| Ollama 1.5b (solo referencia; no target Agent) | — | — | Solo router de intents |
