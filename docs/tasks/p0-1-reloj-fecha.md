# P0-1 · Reloj y fecha

**Estado:** propuesto · Depende de: nada · Esfuerzo: 3-4 h
**Habilita:** recordatorios, «en 20 minutos», saludos por franja horaria,
respuestas con fecha («¿cuándo es el examen?»), proactividad (P1).

## Problema

No existe `datetime` en ningún módulo. El prompt no sabe qué día es, así que:

- «¿qué hora es?» no tiene respuesta fiable;
- «avísame en 20 minutos» es imposible de calcular;
- «¿qué toca hoy?» carece de ancla temporal.

## Diseño

Tres piezas, de dentro hacia fuera:

1. **`modules/clock.py`** — fuente única de verdad temporal.
2. **`{now}` en el prompt** — renderizado **por turno**, no al arrancar.
3. **Ruta rápida determinista** — «¿qué hora es?» sin LLM (0 ms, exacta).

```
"¿qué hora es?" ──► quick_routes ──► get_time ──► "Son las 15:42."
cualquier turno ──► prompt con {now} reemplazado ──► el LLM ya sabe la fecha
```

## Cambios por archivo

| Archivo | Cambio |
|---|---|
| `modules/clock.py` **(nuevo)** | `now_line(tz=None)` → `"miércoles 28 de octubre de 2026, 15:42 (UTC-06:00)"`; `time_line()`, `date_line()`; `parse_duration("20 minutos")` → `timedelta` (lo usará P1) |
| `config.py` | `TIMEZONE` (default `""` = local) |
| `prompts/system_prompt.txt` | Cabecera: `Ahora: {now}.` |
| `modules/llm.py` | `_render_system_prompt()` reemplaza `{now}` al construir los mensajes (Groq y Ollama) |
| `commands/system.py` | `get_time(detail="all")` con `detail: time\|date\|weekday\|all` |
| `modules/executor.py` | `action_map["get_time"] = self.system.get_time` |
| `modules/quick_routes.py` **(nuevo)** | `match_quick_route(text)` → `get_time` para «qué hora es», «qué día es», «a qué estamos» |
| `main.py` | Engancha `quick_routes` antes del LLM (junto a `file_router`) |
| `tests/test_clock.py` **(nuevo)** | Formato, zona, duraciones |
| `tests/test_quick_routes.py` **(nuevo)** | Frases que sí y que no |
| `tests/test_corpus_ordenes.py` | Presupuesto del prompt renderizado (subir tope a 7800 B con `{now}`) |

## Detalle técnico

```python
# modules/clock.py (esbozo)
_DIAS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
_MESES = ("enero", "febrero", ...)

def now_line(tz: str | None = None, now: datetime | None = None) -> str:
    dt = now or (datetime.now(ZoneInfo(tz)) if tz else datetime.now().astimezone())
    return (f"{_DIAS[dt.weekday()]} {dt.day} de {_MESES[dt.month - 1]} de {dt.year}, "
            f"{dt:%H:%M} ({dt:%Z%z})")
```

- `now=` inyectable para tests sin congelar el reloj.
- Sin `locale`: los nombres van en tablas (el servicio no garantiza `LANG`).
- `{now}` se sustituye **en cada turno**: si el servicio lleva 3 días vivo, la
  hora debe ser la de ahora, no la del arranque.

```python
# modules/llm.py
def _render_system_prompt(self) -> str:
    now = now_line(self.config.TIMEZONE or None)
    return self.system_prompt.replace("{now}", now)
```

> Ojo: `self.system_prompt` se sigue cargando una vez; lo que cambia es el
> reemplazo. No recargar el archivo por turno.

## Tareas

- [x] `modules/clock.py` con tablas en español, `tz` opcional y `now` inyectable
- [x] `config.TIMEZONE` + `.env.example`
- [x] `{now}` en la cabecera del prompt
- [x] `_render_system_prompt()` usado en **ambas** ramas (Groq y Ollama)
- [x] `get_time(detail)` en `commands/system.py` + `action_map`
- [x] Línea en el catálogo del prompt: `get_time {detail:time|date|all}`
- [x] `modules/quick_routes.py` + enganche en `main.py`
- [x] Tests de reloj, rutas y presupuesto de prompt
- [x] `CHANGELOG.md` + fila en `AGENTS.md` (tabla de módulos)

## Criterios de aceptación

1. `get_time()` devuelve la hora real con zona y día en español.
2. «¿qué hora es?» responde en < 50 ms **sin llamar al LLM** (verificable en log:
   no aparece `turno procesado`).
3. El prompt renderizado contiene la hora actual y ningún `{now}` literal.
4. Tras 24 h de servicio, la hora del prompt sigue siendo la correcta.

## No-objetivos

- Calendario (Google/CalDAV) → P1.
- Recordatorios → P1 (aquí solo se deja `parse_duration` listo).
