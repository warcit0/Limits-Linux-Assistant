# Tareas — Fundamentos Jarvis

Índice y estado de las tareas por fase. Marca la casilla de una tarea **solo**
cuando su documento esté entero en verde.

## Mejora 1 — Asistente por objetivos y especialistas

| Orden | Tarea | Estado | Criterio de cierre |
|---|---|---|---|
| 1 | [Mejora 1 · Orquestación por objetivos](mejora-1-asistente-por-objetivos.md) | ✅ completada, verificada y activada | Seis bloques completos, suite en verde, corpus 32/32 y ≥ 40 escenarios nuevos validados |

Plan: [plan-mejora-1-orquestacion-agentes.md](../plan-mejora-1-orquestacion-agentes.md).

## Mejora 2 — Conversación fluida

[Plan y alcance](../plan-mejora-2-conversacion-fluida.md) implementados;
[validación automática](../validaciones/mejora-2.md). Prueba manual de micrófono
aplazada por petición del usuario, sin marcarla como superada.

## Mejora 3 — Presencia animada

[Plan](../plan-mejora-3-widget-presencia.md) implementado y activado, núcleo orgánico
con shader. [Aceptación automática y límites](../validaciones/mejora-3.md): voz real,
interrupción local, foco y consumo; sin prueba manual de micrófono ni varios monitores.

## Mejora 5 — Ejecución y conversación coherentes

[Plan de implementación](../plan-mejora-5-ejecucion-coherente.md) y
[tarea](mejora-5-ejecucion-coherente.md): implementados y activados; evaluación real con fallos.
La mejora 6 propone sustituir el recorrido cotidiano remoto.
Corrige el recorrido cotidiano tras los fallos de conversación de la mejora 4.
Validación acotada, sin comparativas de modelos.

## P2 — Pantalla, workspaces y sesión

| Orden | Tarea | Esfuerzo | Estado | Criterio de cierre |
|---|---|---|---|---|
| 1 | [P2-1 · Visión de pantalla](p2-1-vision-pantalla.md) | 2-3 días | 📋 propuesto | Leer sin inventar ≤ 2,5 s p50; describir ≤ 6 s; 0 capturas persistidas |
| 2 | [P2-2 · Workspaces por voz](p2-2-workspaces.md) | 1 día | 🟡 parcial: numéricos existentes y verificación | 12 frases correctas en < 150 ms, sin crear workspaces por error |
| 3 | [P2-3 · Memoria de sesión](p2-3-memoria-sesion.md) | 0,5 día | 📋 propuesto | «¿qué he hecho hoy?» real en < 100 ms |

Plan: [plan-p2-pantalla-workspaces-sesion.md](../plan-p2-pantalla-workspaces-sesion.md).

## P1 — Grounding (router 100 % local)

| Orden | Tarea | Esfuerzo | Estado | Criterio de cierre |
|---|---|---|---|---|
| 1 | [P1-1 · Grounding del router](p1-1-grounding.md) | 1 día | ✅ implementado y medido | 0 acciones incorrectas en la sonda, 0 silencios y corpus ≥ 0,90 (medido: 32/32) |

## P0 — Fundamentos

| Orden | Tarea | Esfuerzo | Estado | Criterio de cierre |
|---|---|---|---|---|
| 1 | [P0-2 · Arranque automático](p0-2-arranque-automatico.md) | 30 min | 🟡 implementado (falta prueba de reinicio) | Reboot sin terminal → servicio activo y móvil conecta |
| 2 | [P0-1 · Reloj y fecha](p0-1-reloj-fecha.md) | 3-4 h | ✅ implementado y verificado | «¿Qué hora es?» en < 50 ms sin LLM, hora correcta 24 h después |
| 3 | [P0-3 · Memoria persistente](p0-3-memoria.md) | 1-1,5 días | ✅ implementado (v1) y verificado | «Recuerda que…» sobrevive a un reinicio y se puede olvidar |
| 4 | [P0-4 · Barge-in](p0-4-barge-in.md) | 1 día | ✅ implementado y verificado con voz | «Para» corta en < 500 ms, 0 falsos positivos en 10 min |

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

## Mejora 6 — Qwen como asistente cotidiano local

[Plan](../plan-mejora-6-qwen-local.md) y [tarea](mejora-6-qwen-local.md):
implementados con aceptación funcional pendiente. Sustituyen la dirección cotidiana remota de
la mejora 5, implementada y activada pero con fallos en la evaluación real del usuario.
No ejecutar pruebas sin nueva autorización. Véase la tarea para estado de activación y pendientes de Spotify.


## Mejora 7 — Interlocutor y ejecución por capacidades

[Plan](../plan-mejora-7-interlocutor.md) y [tarea](mejora-7-interlocutor.md).
Implementación autorizada; revisión estática y activación, aceptación por voz pendiente.
