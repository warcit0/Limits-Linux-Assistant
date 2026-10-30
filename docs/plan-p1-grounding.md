# P1 — Grounding: que la acción responda a la pregunta

**Estado:** en implementación · 2026-10-28
**Objetivo:** que Limits **entienda** lo que le pides, no solo que emita un JSON
válido. Hoy el cortafuegos garantiza *estructura* (tipos, params, confirmaciones),
pero no que la acción elegida tenga que ver con la frase del usuario.

## 1. Problema (medido, no teórico)

Sonda real sobre el pipeline (16 frases, sin ejecutar nada), con la configuración
de la máquina:

| Frase | Lo que hizo | Qué debería |
|---|---|---|
| «¿a qué hora abre el banco?» | `get_system_info {type:"time"}` | responder que no lo sabe / buscar |
| «ponme música relajante» | `media_play` (**no existe**) y decir «Trayendo Spotify» | `spotify_play` |
| «¿cuánto espacio libre me queda?» | `get_system_info {type:"free_space"}` (**enum inválido**) | `{type:"disk"}` |
| «estoy cansado» | sin `action` + `params:{app:"spotify"}` + «Trayendo Spotify» | respuesta conversacional |
| «¿qué canción suena?» | `web_search` | `get_current_song` |
| «busca las llaves» | sin `action` y sin respuesta | pedir aclaración |
| «tradúceme buenos días al inglés» | sin `action`, `response` vacía → **silencio** | responder o pedir aclaración |
| «hazme un resumen de la II Guerra Mundial» | `get_system_info` (inventado) | charla (`action: null`) |

Dos causas distintas:

1. **El router local (1.5b) alucina** acciones y parámetros. Es el motor primario
   por `LLM_PRIORITY=local`.
2. **`GROQ_MODEL=qwen/qwen3.6-27b` ya no existe** (404). El motor de calidad
   estaba caído y *todo* caía al 1.5b. Comprobado contra la API: los modelos
   disponibles hoy incluyen `qwen/qwen3.8-27b` y `openai/gpt-oss-20b/120b`.

Con `qwen/qwen3.8-27b` las mismas 8 frases problemáticas salen bien (8/8). Es
decir: **el modelo importa**, pero no se puede confiar solo en él.

## 2. Principio

> El modelo propone; el código **verifica contra el catálogo real y contra la
> frase**. Nunca se ejecuta una acción que no esté anclada en lo que dijo el
> usuario, y nunca se dice «hecho» si no se hizo.

Tres capas, todas deterministas y testeables sin red:

### Capa 1 · Catálogo real
`modules/grounding.py` recibe el `action_map` del ejecutor. Una acción que no
existe (`media_play`) se rechaza: **no se ejecuta y no se anuncia como hecha**.

### Capa 2 · Evidencia por dominio
Tabla `ACTION_HINTS` acción → palabras que deben aparecer en la frase
(`get_system_info` ← ram/memoria/disco/cpu…, `spotify_play` ← spotify,
`get_current_song` ← canción/suena…). Cada tabla tiene **exclusiones** para no
secuestrar preguntas ajenas:

- `get_time` con «a qué hora **abre/cierra/empieza**» → bloqueada (es un horario
  de terceros, no nuestro reloj).
- `search_file` exige «archivo/fichero/carpeta/extensión»: «busca las llaves» no
  es una búsqueda de archivos.

### Capa 3 · Enums de parámetros
`PARAM_ENUMS` valida valores cerrados (`get_system_info.type`, `get_time.detail`,
`media_control.action`, `set_volume.mode`, `web_search.engine`, `tv_control.action`)
con **alias** para los errores frecuentes (`free_space`→`disk`, `ram`→`memory`).

### Escalera de calidad (local → cloud)
Si el motor primario devuelve algo que **no** se sostiene, se reintenta **una vez**
con el secundario y se acepta solo lo que pase el filtro. El resultado rechazado
queda como último recurso: se responde con honestidad, no se ejecuta.

```
process(texto)
  ├─ motor primario ──► grounding ok ──► aceptar
  │                  └─ rechazado ──► probar secundario (1 vez)
  └─ si ninguno pasa ──► grounded=False → el executor NO ejecuta y lo dice
```

Coste: 0 llamadas extra en el caso normal; ~1 s extra solo cuando el barato falla.

## 3. Qué cambia en el turno

```
run_pipeline(texto)
  → rutas deterministas (hora, archivos, memoria)      # ya sin LLM
  → llm.process(texto)                                 # + grounding
      ├─ action fuera del catálogo        → grounded=False
      ├─ enum inválido y sin alias        → grounded=False
      ├─ dominio sin evidencia            → grounded=False
      └─ ok                               → grounded=True
  → executor.execute(dict)
      ├─ grounded=False → frase honesta + log; NO ejecuta
      ├─ action desconocida → «no sé hacer eso todavía» (nunca «hecho»)
      └─ texto vacío → «no te he entendido» (nunca silencio)
```

## 4. Criterio de aceptación

1. Las 8 frases de la tabla §1 **no ejecutan** una acción incorrecta: o aciertan
   o piden aclaración (nunca engañan).
2. El corpus de 25+ órdenes legítimas sigue ejecutando: `bin/measure-router`
   ≥ 0,90 y `unittest` en verde.
3. Cero silencios: toda entrada produce texto hablado.
4. Traza de por qué se bloqueó: `grounding: bloqueado (sin_evidencia) …`.

## 5. Fuera de alcance

- Reentrenar o afinar el modelo (regla del proyecto: código determinista).
- Embeddings o clasificadores: la tabla de dominios es explícita y revisable.
- Reparar acciones mal elegidas cambiando parámetros de otra acción: se bloquea y
  se pide aclaración; los remaps seguros (p. ej. «qué canción suena») van a
  `quick_routes` cuando se demuestre que merecen la pena.

## 6. Riesgos

| Riesgo | Mitigación |
|---|---|
| Falso bloqueo de una orden legítima | tabla revisada contra el corpus; un bloqueo se corrige con una palabra, no con un modelo |
| Tabla desactualizada al añadir acciones | por defecto **no** se restringe; solo las acciones listadas exigen evidencia |
| El modelo local cambia (versión nueva) | el grounding no depende del modelo: es la red de seguridad |
| Frases mecánicas que el modelo confunde | routers deterministas (`file`/`app`/`media`) antes del LLM |

## 7. Tareas

- [P1-1 · Grounding del router](tasks/p1-1-grounding.md)

## 8. Resultado medido (2026-10-28)

Router **100 % local** (`qwen2.5:1.5b-instruct`, `num_ctx=8192`, temperatura 0,
seed fija). Groq eliminado del código y del `.env`.

| Métrica | Antes | Ahora |
|---|---|---|
| Acierto del corpus (32 frases) | 9/32 (28,1 %) con ctx 2048 | **32/32 (100 %)** ×2 corridas |
| Latencia p50 | 5,7 s | **1,6-1,8 s** |
| Latencia p95 | 6,0 s | **2,9-3,3 s** |
| Silencios en la sonda | 1 («tradúceme…») | **0** |
| Acciones incorrectas ejecutadas | 5 de 8 | **0** |

La causa raíz de la mala precisión no era el modelo: `OLLAMA_NUM_CTX=2048`
truncaba el prompt (~1900 tokens) y el modelo perdía las instrucciones. Subirlo a
8192 movió el acierto de 28 % a 88-94 %; las rutas deterministas y los ajustes de
prompt lo llevaron a 100 %.

Vías del último corpus medido: 17 por LLM, 6 app_router, 5 file_router,
3 media_router y 1 por keyword (`desktop_task`).

Sonda (`scripts/probe_grounding.py`): 3 acciones correctas (`spotify_play`,
`get_system_info`, `get_current_song`), 5 bloqueadas con frase honesta
(horario ajeno, `shutdown` inventado, búsqueda sin nombre, `translate`
inexistente, resumen) y **0 silencios**.

Limitaciones conocidas: «tradúceme…» y «hazme un resumen…» acaban en «no estoy
seguro de haber entendido» (falta lane conversacional); «estoy cansado» tienta al
modelo a proponer `shutdown`, que el grounding bloquea siempre.
