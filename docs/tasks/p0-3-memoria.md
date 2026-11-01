# P0-3 · Memoria persistente

**Estado:** implementado (v1) · Depende de: P0-1 (`{now}` para fechar hechos) · Esfuerzo: 1-1,5 días
**Habilita:** continuidad entre reinicios, preferencias, «¿qué sabes de mí?»,
base de la proactividad (recordar rutinas) y de la personalización.

## Problema

```python
HISTORY_SIZE = 6
self.conversation_history: list[dict] = []   # en RAM
```

- Al reiniciar el servicio, Limits olvida la conversación y **nunca** ha sabido
  nada de ti.
- No hay forma de decirle «recuerda que mi proyecto principal es Limits».
- El `{machine_map}` aporta rutas, no preferencias ni hechos.

## Decisión de almacenamiento

**SQLite** en `~/.limits/memory.db` (WAL + FTS5). Postgres no aporta nada a un
usuario único y Obsidian no es transaccional. El razonamiento completo está en
[`../plan-p0-fundamentos.md`](../plan-p0-fundamentos.md#4-decisión-de-almacenamiento).

## Diseño

```text
turno ──► memory.log_turn(role, text)          (episodios)
       ──► prompt {memory}  ◄── facts_block(600 B)
       ──► "recuerda que X es Y" ──► memory.remember("x", "Y")
       ──► "¿qué sabes de mí?"  ──► memory.facts_block() hablado
```

### Dos tipos de memoria

| Tipo | Cuándo | Clave | Recuperación |
|---|---|---|---|
| **Hecho** (`X es Y`) | «recuerda que mi proyecto principal es Limits» | `mi_proyecto_principal` (normalizada) | Upsert; entra en `{memory}` por relevancia/recencia |
| **Nota** (frase libre) | «recuerda que el wifi se cae los martes» | `nota:<hash>` | FTS5 por la consulta del usuario |

### Esquema (v1)

```sql
PRAGMA user_version = 1;

CREATE TABLE facts (
    id           INTEGER PRIMARY KEY,
    key          TEXT NOT NULL UNIQUE,
    value        TEXT NOT NULL,
    tags         TEXT DEFAULT '',
    source       TEXT DEFAULT 'user',      -- user | inferred
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    last_used_at TEXT
);
CREATE VIRTUAL TABLE facts_fts USING fts5(
    key, value, tags,
    content='facts', content_rowid='id',
    tokenize="unicode61 remove_diacritics 2"
);

CREATE TABLE episodes (
    id INTEGER PRIMARY KEY, ts TEXT NOT NULL, role TEXT NOT NULL,
    text TEXT NOT NULL, intent TEXT, ok INTEGER, meta TEXT
);

CREATE TABLE fact_history (
    id INTEGER PRIMARY KEY, fact_id INTEGER REFERENCES facts(id),
    old_value TEXT, new_value TEXT, ts TEXT NOT NULL
);
```

`remove_diacritics 2` es lo que hace que «música» encuentre «musica» — la misma
lección del bug de `~/Work`.

## API (`modules/memory.py`)

```python
class MemoryStore:
    def __init__(self, path: str, enabled: bool = True): ...
    def remember(self, key: str, value: str, tags: str = "") -> str
    def forget(self, key: str) -> bool
    def recall(self, query: str, limit: int = 5) -> list[dict]
    def facts_block(self, max_bytes: int = 600) -> str
    def log_turn(self, role: str, text: str, intent: str | None = None,
                 ok: bool | None = None, meta: dict | None = None) -> None
    def recent_turns(self, n: int = 6) -> list[dict]   # hidratar historial
    def stats(self) -> dict
    def close(self) -> None
```

Reglas de implementación:

- `PRAGMA journal_mode=WAL`, `timeout=5`, `chmod 600` al crear.
- **Degradación limpia**: si SQLite falla, `MemoryStore` queda `enabled=False`
  y Limits sigue funcionando como hoy. Nunca tumbar el asistente por la memoria.
- **Redacción en escritura**: regex para `gsk_`, `sk-`, `ghp_`, `Bearer …`,
  hex de 64 → `[redactado]`.
- Una conexión por proceso; el CLI y el servicio pueden coexistir por WAL.

## Integración

| Archivo | Cambio |
|---|---|
| `modules/memory.py` **(nuevo)** | `MemoryStore` completo |
| `modules/memory_router.py` **(nuevo)** | `match_memory_route(text)` → `remember` / `forget` / `what_do_you_know` |
| `config.py` | `MEMORY_ENABLED`, `MEMORY_PATH`, `MEMORY_CONTEXT_BYTES`, `MEMORY_EXPORT_PATH` |
| `prompts/system_prompt.txt` | Sección `## LO QUE SABES DEL USUARIO\n{memory}` + regla «no inventes hechos» |
| `modules/llm.py` | `_render_system_prompt()` sustituye también `{memory}`; hidrata historial con `recent_turns(6)`; `log_turn` en cada turno |
| `modules/executor.py` | Acciones `remember {key, value}`, `forget {key}`, `memory_stats {}` |
| `main.py` | Engancha `memory_router` antes del LLM; inyecta `MemoryStore` en LLM y executor |
| `tests/test_memory.py` **(nuevo)** | CRUD, FTS, presupuesto, persistencia, redacción |
| `tests/test_memory_router.py` **(nuevo)** | Frases válidas y señuelos |

### Router determinista (sin LLM)

| Frase | Acción |
|---|---|
| «recuerda que **mi proyecto principal es Limits**» | `remember("mi_proyecto_principal", "Limits")` |
| «recuerda que **el wifi se cae los martes**» | nota libre |
| «olvida **el wifi**» | `forget` + confirmación hablada |
| «¿qué sabes de mí?» / «¿qué recuerdas?» | lista acotada |

Extracción del hecho: si el texto tras «recuerda que» casa con `(.+?) es (.+)`,
se parte en clave/valor; si no, nota. La clave se normaliza (`mi `, `el `, `la `
fuera, espacios → `_`, sin acentos).

## Presupuesto de contexto

| Bloque | Tope | Prioridad |
|---|---|---|
| `{memory}` | 600 B | Hechos con `last_used_at` reciente y `tags` que casen con el turno |
| Notas | 3 máx. en el bloque | El resto, solo bajo demanda por FTS |

Si el bloque se pasa, se recortan primero las notas y luego los hechos más
antiguos. **Nunca** truncar a mitad de palabra.

## Fases

1. **v1 (este plan):** esquema, API, hechos/notas explícitos, `{memory}`,
   hidratación del historial, acciones y router.
2. **v2 (fase 2):** export a Obsidian (`scripts/export_memory.py` →
   `MEMORY_EXPORT_PATH`, unidireccional), resumen nocturno de episodios a hechos.
3. **v3 (fase 3):** recuperación semántica (`sqlite-vec` + embeddings locales) si
   FTS5 se queda corto. No antes.

## Tareas

- [x] `modules/memory.py` (esquema, WAL, redacción, degradación limpia)
- [x] `config.py` + `.env.example`
- [x] Sección `{memory}` en el prompt + regla antiinvención
- [x] `_render_system_prompt()` con `{memory}` en cada turno
- [x] Hidratar `conversation_history` al arrancar y persistir cada turno
- [x] `modules/memory_router.py` + enganche en `main.py`
- [x] Acciones `remember` / `forget` / `memory_stats` en `executor` + catálogo del prompt
      (más `memory_list` y `memory_recall` para consultas)
- [x] Tests (CRUD, FTS con acentos, presupuesto, persistencia, redacción, DB corrupta)
- [x] Test de prompt renderizado ≤ 8400 B (7800 base + 600 de memoria)
- [x] `CHANGELOG.md`, `AGENTS.md`, este doc marcado como implementado

## Criterios de aceptación

1. «recuerda que mi proyecto principal es Limits» → fila en `facts` y respuesta
   confirmando.
2. `limits-service restart` y «¿qué sabes de mí?» → lo menciona.
3. «olvida mi proyecto principal» → deja de aparecer en el prompt.
4. `ls -l ~/.limits/memory.db` → `600`.
5. Escribir «recuerda que mi token es gsk_abc…» → se guarda `[redactado]`.
6. Con la DB borrada o corrupta, Limits arranca y responde igual (sin memoria).

## Riesgos

| Riesgo | Mitigación |
|---|---|
| Memoria basura que contamina el prompt | Solo se guarda lo explícito; bloque de 600 B; `forget` |
| Hechos contradictorios («proyecto principal es X» y «…es Y») | Upsert por clave + `fact_history`; gana el último y se avisa |
| Fuga de secretos al log/DB | Redacción en escritura + test dedicado |
| FTS5 no disponible en el Python del venv | `sqlite3` de la stdlib lo trae; si faltara, `recall` cae a `LIKE` |

## No-objetivos

- Extracción automática de hechos con el LLM (v2, y siempre con confirmación).
- Sincronización multi-dispositivo.
- Sustituir `{machine_map}`: son complementarios (rutas vs. hechos).
