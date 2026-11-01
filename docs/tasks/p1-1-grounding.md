# P1-1 · Grounding del router (100 % local)

**Estado:** ✅ implementado y medido · Esfuerzo: 1 día · Depende de: P0
**Criterio:** las 8 frases de la sonda no ejecutan una acción incorrecta y no
dejan silencios; el corpus legítimo pasa de 0,90.

## Contexto

Plan completo en [plan-p1-grounding.md](../plan-p1-grounding.md). Dos decisiones
cambiaron el diseño a mitad de tarea:

1. **Groq sale de la ecuación** (petición del usuario): el router es 100 % local.
   Sin fallback cloud; si el local no puede anclar la acción, se responde con
   honestidad.
2. **La causa raíz era el contexto**: `OLLAMA_NUM_CTX=2048` truncaba el prompt
   (~1900 tokens) y el modelo perdía las instrucciones. Con 8192 el acierto pasó
   del 28 % al 88-94 %.

## Checklist

### 0. Modelo que existe
- [x] Router local-only: `GROQ_*` y `LLM_PRIORITY` eliminados de `config.py`,
      código y `.env` (claves comentadas, reversibles).
- [x] `OLLAMA_NUM_CTX=8192` (el prompt no cabe en 2048).
- [x] `OLLAMA_MODEL=qwen2.5:1.5b-instruct` (el 3b rinde peor y tarda el doble).
- [x] Temperatura 0 + `seed` fijo: el router es determinista, no creativo.

### 1. Módulo `modules/grounding.py`
- [x] `fold()` (minúsculas, sin acentos) y `Verdict(ok, reason)`.
- [x] `ACTION_HINTS`: evidencia mínima por acción (28 acciones, incluidas las
      lanes Gemini/terminal).
- [x] `ACTION_EXCLUDES`: «a qué hora abre/cierra…» no es `get_time`.
- [x] `PARAM_ENUMS` + `PARAM_ALIASES` (`free_space`→`disk`, `ram`→`memory`).
- [x] `check(action, params, text, known_actions)` → `Verdict` con motivo.

### 2. `LLMEngine`
- [x] Catálogo real inyectado desde `main`
      (`executor.action_map` + `confirm`/`cancel`).
- [x] Una sola llamada: el local propone, el grounding verifica (sin escalera).
- [x] `result["grounded"]` y `result["grounding_reason"]` en la salida y el log.
- [x] Historial: se registra **una** vez, el resultado aceptado.

### 3. `CommandExecutor`
- [x] `grounded=False` → frase honesta, sin ejecutar (y sin tocar `pending`).
- [x] Acción desconocida → «no sé hacer eso todavía».
- [x] Texto final vacío → «no te he entendido».

### 4. Prompt
- [x] Una línea: si no encaja en ninguna acción, `"action": null` y responder.
- [x] Reglas de desambiguación de archivos y `action: null` para charla.
- [x] Presupuesto: 8049 B renderizados de 8400 (test en verde).

### 5. Rutas deterministas que evitan el modelo
- [x] `modules/file_router.py`: «muéstramelo» → `reveal_last`, «ábrelo» →
      `open_last`, «abre el archivo ~/…» → `open_file`, «abre el segundo» →
      `open_last{index:2}`.
- [x] `modules/app_router.py` (nuevo): «abre/cierra `<app>`» y «pon `<app>` en
      pantalla» → `open_application`/`close_application`/`focus_window`.
- [x] `modules/media_router.py` (nuevo): «pausa/siguiente/reanuda/para la
      música» y «pon `<artista>` en Spotify» → `media_control`/`spotify_play`.

### 6. Tests
- [x] `tests/test_grounding.py` (casos medidos y falsos positivos).
- [x] `tests/test_llm_grounding.py` (anclaje, enum reparado, motor caído).
- [x] `tests/test_executor_guard.py` (no ejecutar sin grounding, sin silencios).
- [x] `tests/test_app_router.py`, `tests/test_media_router.py`,
      `tests/test_file_router.py` ampliado.
- [x] Suite completa: **262 tests** en verde.

### 7. Verificación
- [x] `bin/measure-router`: **32/32 (100 %)** en dos corridas consecutivas.
- [x] Latencia: **p50 1,6-1,8 s · p95 2,9-3,3 s · media 1,3-1,8 s** (antes 5,7 s
      con el contexto truncado).
- [x] `scripts/probe_grounding.py` (nuevo): 8 frases de la sonda original →
      3 acciones correctas, 5 bloqueadas con respuesta honesta, **0 silencios**.

### 8. Documentación
- [x] `CHANGELOG.md`, `AGENTS.md` (módulos, flujo y gotchas), este índice.
- [x] `docs/plan-p1-grounding.md` → resultados medidos.

## Pendiente (no bloquea P1)

- «tradúceme…» y «hazme un resumen…» se bloquean en vez de responderse como
  charla: falta una lane conversacional (Gemini talk) con evidencia.
- «estoy cansado» sigue tentando al modelo a proponer `shutdown` (el grounding
  lo bloquea siempre).
