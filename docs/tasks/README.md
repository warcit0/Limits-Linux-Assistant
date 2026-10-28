# Tareas P0 — Fundamentos Jarvis

Índice y estado de las cuatro tareas de [P0](../plan-p0-fundamentos.md).
Marca la casilla de la tarea **solo** cuando su documento esté entero en verde.

| Orden | Tarea | Esfuerzo | Estado | Criterio de cierre |
|---|---|---|---|---|
| 1 | [P0-2 · Arranque automático](p0-2-arranque-automatico.md) | 30 min | 🟡 implementado (falta prueba de reinicio) | Reboot sin terminal → servicio activo y móvil conecta |
| 2 | [P0-1 · Reloj y fecha](p0-1-reloj-fecha.md) | 3-4 h | ✅ implementado y verificado | «¿Qué hora es?» en < 50 ms sin LLM, hora correcta 24 h después |
| 3 | [P0-3 · Memoria persistente](p0-3-memoria.md) | 1-1,5 días | ✅ implementado (v1) y verificado | «Recuerda que…» sobrevive a un reinicio y se puede olvidar |
| 4 | [P0-4 · Barge-in](p0-4-barge-in.md) | 1 día | 🟡 implementado (falta prueba con voz real) | «Para» corta en < 500 ms, 0 falsos positivos en 10 min |

## Convenciones

- Cada tarea termina con: tests en verde (`203+`), `CHANGELOG.md` actualizado y
  este índice marcado.
- Los cambios de prompt deben respetar el presupuesto: **≤ 8400 B** renderizado
  (7800 base + hasta 600 B de memoria; test en `tests/test_corpus_ordenes.py`).
- Toda variable nueva se declara **solo** en `config.py`, nunca con `os.getenv`
  disperso.
- Al cerrar P0 completo: actualizar `AGENTS.md` (tabla de módulos) y
  `docs/plan-p0-fundamentos.md` a **implementado**.

## Fuera de alcance de P0

- Recordatorios, calendario y proactividad → **P1** (se apoyan en P0-1 y P0-3).
- Wake word local (openWakeWord/Porcupine) y visión de pantalla → **P2**.
- Export a Obsidian → fase 2 de P0-3.
- Postgres / sincronización multi-dispositivo → descartado, ver decisión en el
  plan maestro.
