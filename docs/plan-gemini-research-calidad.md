# Plan 3 — Calidad Gemini research (puente, no routing)

**Estado:** implementado (2026-10-27)  
**Doc base:** [`integracion-gemini.md`](integracion-gemini.md)  
**Hallazgo 2026-10-27:** *“investiga…”* → routing OK pero salida hueca (33 chars) o `NOT_SIGNED_IN`.  
**Causa raíz repro:** `gemdev` devolvió `NOT_SIGNED_IN` (sesión caducada). Antes, respuestas Jarvis vacías pasaban a TTS; ahora fail-loud.

## Problema

- Bypass por keyword funciona (no pasa por Ollama intents).
- Respuestas cortas/vacías o genéricas → mala UX; el usuario cree que “Gemini no investiga”.

## Hipótesis a verificar (en orden)

1. `gemdev` devolvió error / ok=false y el bridge degradó mal.
2. Archivo `f` vacío o parcial; leemos mal el puntero JSON.
3. `PREAMBLE` + timeout demasiado agresivo; sesión `-c` corrupta.
4. TTS/`clean_for_voice` / `max_voice_chars` recortan de más.
5. Cuota/sesión web de Gemini sin login fresco.

## Alcance

### 3.1 Observabilidad

- Log DEBUG: exit code, última línea JSON, path `f`, `len(texto)`, primeros 200 chars (nunca API keys).
- Si `ok=false` o texto < N chars → TTS: “No pude investigar ahora” + motivo corto, no frase Jarvis vacía.

### 3.2 Smoke reproducible

```bash
# Fuera de Limits
gemdev chat -t 60 --json -c ~/.limits/gemini_session.json "investiga X"
# Dentro
limits --text   # misma frase; contrastar chars y log
```

- Añadir test de bridge con fixture de stdout/archivo `f` corto vs largo (ya hay mocks; extender casos de degradación).

### 3.3 Contrato de voz

- Research: mínimo razonable (~80–120 palabras) o mensaje de fallo explícito.
- No mezclar salida Gemini con `action_map` (regla dura vigente).

## Fuera de alcance

- Sustituir Gemini por Ollama para research web (Ollama no tiene el mismo acceso web vía gemdev).
- Aflojar el router de intents.

## Criterio de hecho

- Frase “investiga …” en `--text` → log research + respuesta ≥ ~200 chars útiles **o** error hablado explícito.
- Cero falsos “Te comento la situación…” sin contenido.

## Hecho

1. Logging INFO/DEBUG: rc, ok, err, `f`, chars, preview  
2. Repro: `NOT_SIGNED_IN` confirmado → mensaje pide `gemdev login`  
3. Fail-loud research: `GEMINI_MIN_RESEARCH_CHARS` + detección de openers huecos  
4. Tests de degradación en `tests/test_gemini.py`  
5. `RESEARCH_MARK` exige ≥120 palabras / hechos; preamble no limita research  

**Acción de usuario:** `gemdev login` cuando la sesión caduque.
