# P0 — Fundamentos Jarvis

**Estado:** implementado · 2026-10-28 (P0-1 ✅, P0-2 🟡 falta prueba de reinicio, P0-3 ✅, P0-4 🟡 falta prueba con voz)
**Objetivo:** cerrar las cuatro carencias que impiden que Limits se sienta un
asistente y no un ejecutor de comandos: **saber la hora**, **estar siempre
arrancado**, **acordarse de ti** y **poder interrumpirlo**.

Estas cuatro no son estética: son las que habilitan todo lo demás (recordatorios,
proactividad, contexto, personalidad). Sin ellas, cualquier fase posterior se
construye sobre arena.

---

## 1. Por qué P0

| Condición Jarvis | Dolor real hoy |
|---|---|
| Contexto temporal | No hay `datetime` en el código: no puede decir la hora ni calcular «en 20 minutos» |
| Disponibilidad | `limits.service` está `active` pero **`disabled`**: tras reiniciar el PC no existe |
| Memoria | `HISTORY_SIZE = 6` en RAM; al reiniciar el servicio se olvida de todo y nunca recuerda nada tuyo |
| Invocación natural | `aplay_proc.wait()` bloquea el turno: si se enrolla hablando no puedes callarlo |

---

## 2. Orden de ejecución

| # | Tarea | Depende de | Esfuerzo | Doc |
|---|---|---|---|---|
| 1 | Arranque automático | — | 30 min | [tasks/p0-2-arranque-automatico.md](tasks/p0-2-arranque-automatico.md) |
| 2 | Reloj y fecha | — | 3-4 h | [tasks/p0-1-reloj-fecha.md](tasks/p0-1-reloj-fecha.md) |
| 3 | Memoria persistente | 2 (usa `{now}` para fechar hechos) | 1-1,5 días | [tasks/p0-3-memoria.md](tasks/p0-3-memoria.md) |
| 4 | Barge-in («para») | — | 1 día | [tasks/p0-4-barge-in.md](tasks/p0-4-barge-in.md) |

Se puede paralelizar 1+2 y luego 3+4. **No** empezar por 4 sin 1-3: interrumpir
a un asistente que no recuerda nada aporta poco.

---

## 3. Arquitectura resultante

```
voz / texto / móvil
      │
      ▼
┌───────────────────────────────────────────────┐
│ pipeline (main.make_pipeline)                 │
│                                               │
│  quick_routes ──► hora/fecha (0 ms, sin LLM)  │
│  file_router  ──► archivos (0 ms, sin LLM)    │
│  memory_router ─► "recuerda que…" / "olvida"  │
│  gemini / desktop_task / LLM router           │
└───────────────┬───────────────────────────────┘
                │ prompt renderizado por turno
                ▼
        {username} {machine_map} {now} {memory}
                │
                ▼
          executor (47 acciones)
                │
                ▼
        SpeechController ── TTS interrumpible
                │
                ▼
        ~/.limits/memory.db  (SQLite WAL + FTS5)
```

Claves de diseño:

- El prompt deja de ser un archivo estático: se **renderiza por turno** con
  `{now}` y `{memory}` (coste ~0, sin recargar el archivo).
- La memoria no entra entera: entra un **bloque acotado** (≤ 600 B) con los
  hechos más relevantes. El resto se consulta bajo demanda.
- Las rutas mecánicas (hora, archivos, memoria explícita) **no pasan por el LLM**:
  deterministas, instantáneas y sin alucinación.

---

## 4. Decisión de almacenamiento

### Comparativa

| Opción | A favor | En contra | Veredicto |
|---|---|---|---|
| **SQLite** (`~/.limits/memory.db`) | Cero ops, transaccional, FTS5, un archivo, `cp` como backup, `chmod 600` | Sin acceso concurrente multi-máquina | ✅ **Elegida** |
| **PostgreSQL** | Concurrencia, extensiones (pgvector), acceso remoto | Daemon + auth + migraciones + backups para **1 usuario y 1 máquina**; no aporta nada al problema real (recuperar poco y bueno) | ❌ Sobredimensionado |
| **Obsidian (vault)** | Legible y editable por ti, sync gratis en el móvil, backlinks | Sin transacciones ni updates atómicos; parsear markdown es frágil; el agente reescribiría tus notas; conflictos con Obsidian Sync | ⚠️ Solo como **export/import**, nunca fuente de verdad |

### Decisión

1. **SQLite es la fuente de verdad.** Ruta `~/.limits/memory.db`, `journal_mode=WAL`,
   `chmod 600`.
2. **Obsidian es una vista.** Fase 2: `scripts/export_memory.py` regenera
   `~/.limits/exports/memoria.md` (o `MEMORY_EXPORT_PATH` apuntando a tu vault).
   Unidireccional: el agente escribe, tú lees. La importación desde notas queda
   fuera de alcance hasta que exista una necesidad real.
3. **Si algún día hace falta Postgres** será por multi-dispositivo, y entonces el
   problema a resolver será sincronización (CRDT o servidor), no el motor.

### Esquema propuesto (v1)

```sql
-- Hechos declarativos sobre el usuario y su entorno
CREATE TABLE facts (
    id          INTEGER PRIMARY KEY,
    key         TEXT NOT NULL UNIQUE,   -- normalizada: "proyecto_principal"
    value       TEXT NOT NULL,
    tags        TEXT DEFAULT '',        -- csv: "proyecto,trabajo"
    source      TEXT DEFAULT 'user',    -- user | inferred
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    last_used_at TEXT
);
CREATE VIRTUAL TABLE facts_fts USING fts5(key, value, tags, content='facts',
                                          content_rowid='id');

-- Turnos para continuidad y recuperación episódica
CREATE TABLE episodes (
    id      INTEGER PRIMARY KEY,
    ts      TEXT NOT NULL,
    role    TEXT NOT NULL,              -- user | assistant
    text    TEXT NOT NULL,
    intent  TEXT,
    ok      INTEGER,                    -- 1/0/NULL
    meta    TEXT                        -- json libre
);

-- Historial de cambios de un hecho (auditoría y "¿por qué sabe esto?")
CREATE TABLE fact_history (
    id      INTEGER PRIMARY KEY,
    fact_id INTEGER NOT NULL REFERENCES facts(id),
    old_value TEXT,
    new_value TEXT,
    ts      TEXT NOT NULL
);
```

Presupuesto de contexto, no de almacenamiento:

| Bloque | Tope | Contenido |
|---|---|---|
| `{memory}` en prompt | 600 B | Hasta 8 hechos, priorizando `tags` relevantes y `last_used_at` reciente |
| Historial de diálogo | 6 mensajes | Igual que hoy, pero persistido |
| Recuperación bajo demanda | 5 resultados | FTS5 por la frase del usuario |

---

## 5. Configuración nueva

| Variable | Default | Uso |
|---|---|---|
| `TIMEZONE` | sistema | Zona para `{now}`; vacío = local |
| `MEMORY_ENABLED` | `true` | Activa SQLite |
| `MEMORY_PATH` | `~/.limits/memory.db` | Ruta de la base |
| `MEMORY_CONTEXT_BYTES` | `600` | Presupuesto del bloque `{memory}` |
| `MEMORY_EXPORT_PATH` | `~/.limits/exports/memoria.md` | Export (fase 2) |
| `BARGEIN_ENABLED` | `true` | Interrupción por voz |
| `BARGEIN_KEYWORDS` | `para,cállate,stop` | Palabras que cortan el TTS |
| `BARGEIN_MIN_MS` | `350` | Voz sostenida necesaria para cortar |

Todas se leen **solo** en `config.py` (regla del repo).

---

## 6. Criterio de aceptación global

Escenario único, reproducible de principio a fin:

1. Reinicio el PC y **no abro ninguna terminal**.
2. Digo: «Limits, ¿qué hora es?» → responde la hora real en < 1 s.
3. Digo: «Limits, recuerda que mi proyecto principal es Limits».
4. Reinicio el servicio (`limits-service restart`).
5. Digo: «Limits, ¿qué sabes de mí?» → menciona el proyecto principal.
6. Mientras termina de hablar, digo «para» → se calla en < 500 ms.

Los cuatro puntos son el `Done` de P0. Cada tarea tiene además su propio
criterio verificable en su documento.

---

## 7. Riesgos

| Riesgo | Mitigación |
|---|---|
| `loginctl enable-linger` arranca el servicio antes de que PipeWire tenga dispositivo de audio | Arrancar el servicio con reintento de micrófono; documentar que el audio puede tardar unos segundos tras el login; validar en un reinicio real |
| La memoria se llena de ruido y contamina el prompt | Solo se guarda lo explícito («recuerda que…»); bloque acotado a 600 B; comando para olvidar |
| Barge-in se auto-dispara con el propio TTS | Umbral de voz sostenida + palabras clave + prueba de 10 min hablando sin interrupciones falsas |
| SQLite bloqueado por dos procesos (servicio + CLI) | WAL + `timeout=5` en la conexión; una conexión por proceso |
| El prompt crece y el router local se degrada | Presupuesto medido en test (`≤ 7800 B` renderizado) |

---

## 8. Índice de tareas

- [x] [P0-1 · Reloj y fecha](tasks/p0-1-reloj-fecha.md) — implementado y verificado E2E
- [x] [P0-2 · Arranque automático](tasks/p0-2-arranque-automatico.md) — implementado (falta prueba de reinicio físico)
- [x] [P0-3 · Memoria persistente](tasks/p0-3-memoria.md) — implementado (v1) y verificado entre reinicios
- [ ] [P0-4 · Barge-in](tasks/p0-4-barge-in.md) — implementado; falta prueba con voz humana

Al cerrar las cuatro: actualizar `CHANGELOG.md`, `AGENTS.md` (tabla de módulos)
y `docs/plan-p0-fundamentos.md` (marcar estado **implementado**).
