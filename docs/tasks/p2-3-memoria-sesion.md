# P2-3 · Memoria de sesión

**Estado:** propuesto · Esfuerzo: 0,5 día · Depende de: P0-3 (memoria), P1
**Criterio:** tras varios turnos reales, «¿qué he hecho hoy?» enumera esas
acciones (no invenciones) en < 100 ms, y «¿dónde lo dejamos?» devuelve la última
acción ejecutada.

Plan completo en [plan-p2-pantalla-workspaces-sesion.md](../plan-p2-pantalla-workspaces-sesion.md).

## Contexto

`modules/memory.py` ya guarda `facts`, `notes` y `episodes` (ts, role, text,
intent, ok, meta) con tope de 5.000 filas, pero:

- `main.run_pipeline` ya llama a `log_turn` en su `finally` para **todos** los
  turnos, también los que resuelven los routers deterministas;
- no hay `session_id`: no se puede separar «esta sesión» de «la semana pasada»;
- no hay consultas por acción ejecutada (solo `recent_turns`, que alimenta al LLM);
- `memory_stats` cuenta filas, no cuenta qué ha pasado.

## Checklist

### 1. Esquema
- [ ] `episodes`: columnas nuevas `session_id TEXT` y `ms INTEGER`
      (migración idempotente con `PRAGMA table_info`).
- [ ] `session_id` = timestamp de arranque del proceso + pid (se pasa desde
      `main` a `get_store()` o vía `MemoryStore.start_session()`).
- [ ] Índice `episodes_session (session_id, ts)`.

### 2. Consultas
- [ ] `session_actions(limit=20)`: turnos `role=user` con `ok=1` de la sesión,
      con intención y hora.
- [ ] `session_summary(hours=8)`: agrupa por bloques de ~10 min y devuelve 3-6
      frases en español («A las 18:40 abriste Spotify…»).
- [ ] `session_last()`: último turno ejecutado + el anterior si forman pareja.
- [ ] `session_clear()`: borra episodios de la sesión actual (no toca `facts`).

### 3. Acciones y router
- [ ] `action_map`: `session_summary`, `session_last`, `session_clear`
      (`session_clear` pide confirmación con el flujo `_pending_action`).
- [ ] `modules/session_router.py`: «qué he hecho hoy», «qué hice antes»,
      «dónde lo dejamos», «resume la sesión», «olvida la sesión».
- [ ] No secuestros: «recuerda que…» sigue siendo `remember` (memory_router).

### 4. Privacidad
- [ ] `redact()` en escritura (ya existe) y ninguna captura de pantalla en
      `episodes` salvo orden explícita de recordarla.
- [ ] Retención: 7 días además del tope de filas.
- [ ] El resumen no repite el texto literal del usuario salvo que sea una orden.

### 5. Tests
- [ ] `tests/test_session.py`: migración de esquema, resumen con episodios
      sembrados, `last`, `clear` (y que `facts` sobrevive).
- [ ] `tests/test_session_router.py`: frases válidas y no secuestros.
- [ ] Test de rendimiento: 500 episodios → resumen < 100 ms.

### 6. Verificación E2E
- [ ] 5 turnos reales mezclados (música, archivo, workspace, pantalla) →
      «¿qué he hecho hoy?» los enumera en orden.
- [ ] «¿dónde lo dejamos?» tras reiniciar el servicio: si la sesión es nueva, lo
      dice («no tengo nada de esta sesión»), no inventa.

## Fuera de alcance

- Resúmenes generados por LLM (donde un modelo pequeño confabula): v1 es SQL.
- Sincronizar sesión entre dispositivos o export a Obsidian (fase 2 de P0-3).
