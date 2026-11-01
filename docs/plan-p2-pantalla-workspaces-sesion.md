# Plan P2 — Ver la pantalla, moverse entre workspaces y recordar la sesión

**Estado:** propuesto · Esfuerzo: 4-5 días · Depende de: P0 y P1
**Objetivo:** que Limits deje de ser ciego y sin contexto: que pueda mirar la
pantalla, moverse por el escritorio por voz y acordarse de lo que ha pasado en la
sesión.

---

## 0. Resumen

Tres capacidades nuevas, cada una con su nivel de coste:

| Lane | Qué hace | Motor | Latencia objetivo |
|---|---|---|---|
| **A · Pantalla** | Leer, resumir y responder sobre lo que se ve | OCR local → VLM local → OpenCode (opt-in) | 2,5 s / 6 s / 15 s |
| **B · Workspaces** | «ve al 3», «manda esto al 2», «qué tengo abierto» | `hyprctl` determinista | < 150 ms |
| **C · Sesión** | «¿qué he hecho hoy?», «¿dónde lo dejamos?» | SQLite (ya existe) | < 100 ms |

**Regla que ordena todo:** primero lo determinista y barato (OCR, `hyprctl`,
SQL); el modelo local solo cuando hace falta *entender*; OpenCode solo cuando
hace falta *razonar o actuar* y el usuario lo autoriza.

### Medido hoy en esta máquina (no estimado)

| Dato | Valor |
|---|---|
| Captura con `grim` (1920×1080) | **57 ms**, PNG 246 KB |
| OCR con `tesseract --psm 6` (solo `eng`) | **1,8 s** |
| Idiomas OCR instalados | `afr`, `eng`, `osd` — **falta español** |
| VRAM (GTX 1650, 4 GB) | 2.393 MiB usados, **1.330 MiB libres** con el router cargado |
| Monitor / workspaces | 1 monitor 1920×1080; ws 1-4 + `special:music` y `special:communication` |
| OpenCode cloud (modelos gratis) | **429** `FreeUsageLimitError` |
| OpenCode cloud (modelos de pago) | **401** `api_key_expired` / `Insufficient account funds` |
| Inyección de teclado (`ydotool`/`wtype`) | **no instalado** |

Conclusión de las medidas: **la visión tiene que ser local para ser usable**. La
vía OpenCode está caída hoy (clave caducada y cuota gratuita agotada), así que
entra como escalón opcional, nunca como requisito.

---

## 1. Qué existe ya (inventario real)

- `take_screenshot` abre **flameshot** en modo GUI: sirve para capturar a mano,
  no para que el asistente *lea*.
- `hyprland_control(killactive|fullscreen)` y `focus_window(app)` tocan Hyprland,
  pero no hay nada de workspaces.
- `modules/memory.py` ya guarda `facts`, `notes` y `episodes` (turno, intención,
  ok) y `recent_turns(6)` alimenta el historial del LLM. **No hay consulta de
  sesión**: la memoria existe pero no se puede preguntar por ella.
- `modules/desktop_agent.py` (`desktop_task`) usa la API de OpenCode para pasos
  compuestos; hoy cae siempre al 3b local porque la API falla (401/429).
- Binarios disponibles: `grim`, `slurp`, `tesseract`, `magick`, `wl-copy`,
  `hyprctl`. No hay `ydotool` ni `wtype`.
- Grounding P1 ya bloquea acciones sin evidencia: cualquier acción nueva debe
  entrar en `ACTION_HINTS` con sus palabras.

---

## 2. Decisiones de diseño

**D1 · Tres escalones con presupuesto.** No todo va al modelo. «Lee la pantalla»
es OCR literal (barato y sin alucinación); «explícame qué está pasando» es VLM
local; «arréglame el error» es agente (OpenCode) y se confirma aparte.

**D2 · La captura es efímera.** El PNG vive en `/dev/shm/limits-screen` (tmpfs,
permisos 700), se borra en `finally` y **nunca** se persiste en `~/.limits` ni en
logs. El texto OCR solo se loguea a nivel DEBUG y se redacta con `redact()`.

**D3 · «Dictar» = narrar en voz alta.** Limits lee lo que hay en pantalla, no
escribe en tus apps. Escribir/dictar texto al campo enfocado requiere
`ydotool`/`wtype` y confirmación explícita: queda fuera de P2 (ver §7).

**D4 · Workspaces sin modelo.** Números, ordinales, «siguiente» y los especiales
se resuelven con un router determinista; el LLM solo para frases raras.

**D5 · Memoria de sesión sobre lo que ya hay.** Misma SQLite: `session_id` en
`episodes`, consultas SQL deterministas. Nada de resúmenes generados en v1 (un
resumen con LLM de lo que hiciste es donde un modelo pequeño miente).

---

## 3. Lane A — Pantalla

### 3.1 Flujo

```
"lee la pantalla"        → grim → recorte ventana activa → tesseract → narrar (literal)
"descríbeme la pantalla" → grim → VLM local → 2-3 frases
"qué error hay"          → OCR: busca líneas con error/fallo/exception →
                            si el OCR no basta → VLM → si es multi-paso → OpenCode
"busca 'puerto' en pantalla" → OCR → ¿aparece? ¿en qué línea/ventana?
"¿qué hay en la pantalla de música?" → grim del workspace/ventana de Spotify → VLM
```

### 3.2 Acciones nuevas

| Acción | Params | Qué responde |
|---|---|---|
| `screen_read` | `{region: active\|full}` | Narra el texto OCR (literal, máx ~60 s de voz) |
| `screen_describe` | `{region}` | Qué se ve: app, ventana, contenido principal |
| `screen_find` | `{text, region?}` | Si el texto está y en qué contexto |
| `screen_ask` | `{question, region?}` | Pregunta libre sobre la captura |
| `screen_windows` | `{}` | Inventario por workspace (`hyprctl clients`) |

`screen_read` y `screen_find` son **deterministas puros** (OCR); `describe` y
`ask` usan VLM; ninguna de las cinco envía nada a la red salvo que
`VISION_CLOUD=1` y el usuario lo confirme.

### 3.3 Implementación

- `modules/screen.py` — captura y OCR sin modelo:
  - `capture(region="active")`: `grim -g "$(hyprctl activewindow -j | geometría)"`
    o pantalla completa; devuelve ruta + tamaño.
  - `ocr(path, lang="spa+eng")`: `tesseract … --psm 6`; si falta `spa`, cae a
    `eng` y lo dice una vez en el log.
  - `clean_text()`: colapsa líneas, quita basura de iconos, limita a N caracteres
    para narración (el resto se resume por frases con `voice_utils`).
- `commands/screen.py` — handlers que devuelven `str` (lo que se habla).
- `modules/screen_router.py` — frases mecánicas antes del LLM: «lee la
  pantalla», «qué dice», «descríbeme la pantalla», «qué error hay», «busca X en
  pantalla», «qué tengo abierto».
- `prompts/system_prompt.txt` — 4 nombres de acción + 1 few-shot por lane
  (presupuesto: ver §6).

**VLM local (T1):** `VISION_MODEL=moondream:1.8b` (~1,8 GB, cabe en los 1,3 GB
libres solo si Ollama descarga el router). Alternativa de más calidad
`qwen2.5vl:3b` (~3,2 GB): **no cabe** junto al router en 4 GB, obliga a expulsar
y recargar (coste 1-2 s en el turno siguiente). Por eso: `keep_alive=0` tras cada
uso y resize a 1280 px de ancho antes de enviar.

**OpenCode (T2):** `opencode run --standalone -m $VISION_CLOUD_MODEL -f captura.png`
con timeout 90 s. Hoy devuelve 429/401 → fail-loud («no puedo consultar la nube:
revisa la clave de OpenCode»), sin reintentos en bucle. Requisito previo: (§9
tarea 2-1d) validar credenciales y modelo con visión.

### 3.4 Privacidad (reglas duras)

1. Captura en tmpfs, permisos 700, borrada siempre (también si el handler falla).
2. Nunca se guarda texto de pantalla en memoria persistente salvo que el usuario
   diga «recuerda lo que dice la pantalla» (y aun así pasa por `redact()`).
3. Cloud apagado por defecto (`VISION_CLOUD=false`); al activarlo, primera vez
   pide confirmación por voz y la recuerda solo para esa sesión.
4. El VLM **no inventa texto**: si la respuesta cita contenido literal, se
   contrasta con el OCR; si no está, se responde «no lo veo en pantalla».

### 3.5 Criterio de aceptación

- 10 frases de lectura sobre capturas reales: el texto narrado coincide con el
  OCR (sin inventar) y ninguna tarda más de 2,5 s p50.
- `screen_find` acierta presencia/ausencia en 10 casos (5 con el texto, 5 sin él).
- `describe`/`ask` responden en ≤ 6 s p50 con el VLM local.
- Ningún PNG sobrevive al turno (test que revisa el directorio temporal).

---

## 4. Lane B — Workspaces

### 4.1 Acciones nuevas

| Acción | Params | Ejemplo |
|---|---|---|
| `workspace_switch` | `{target: int\|str, monitor?}` | «ve al 3», «al especial de música» |
| `workspace_move` | `{target}` | «manda esto al 2» |
| `workspace_list` | `{}` | «qué tengo abierto» |
| `workspace_back` | `{}` | «vuelve al anterior» |

### 4.2 Router determinista (`modules/workspace_router.py`)

Frases: «workspace N», «escritorio N», «ve al N», «pásate al N», «el especial de
<música|comunicación>», «siguiente/anterior», «vuelve al anterior», «manda esto
al N», «qué tengo abierto».

- Números en palabra («tres» → 3) hasta 10.
- Historial de proceso para «anterior» (una entrada; se pierde al reiniciar).
- `special:*` solo si existe en `hyprctl workspaces -j`; si no, pedir aclaración.
- Multi-monitor: `monitor` opcional, validado contra `hyprctl monitors -j`.

### 4.3 Implementación

- `commands/workspaces.py`: `switch(target, monitor=None)`,
  `move_window(target)`, `list_open()`, `back()`.
  - `hyprctl dispatch workspace <id|name>` (para especiales: `workspace
    special:music`, que **no** los toglea: entra siempre)
  - `hyprctl dispatch movetoworkspace <id|name>` (mueve la ventana activa)
  - `hyprctl dispatch togglespecialworkspace <name>` solo para «abre/cierra el
    especial», nunca para «ve al especial»
  - `hyprctl workspaces -j` + `clients -j` para validar y listar.
- Nunca crear workspaces nuevos por error: si el número no existe y la frase no
  lo pide explícitamente («crea el 9»), se responde con los existentes.
- Grounding: `ACTION_HINTS["workspace_switch"]` = `workspace|escritorio|pantalla
  virtual`; `workspace_move` exige además «manda/mueve/envía».
- `workspace_list` responde resumido: «Workspace 3: virt-manager y foot.
  Workspace 2: foot. Especial de música: Spotify.»

### 4.4 Criterio de aceptación

- 12 frases (4 switch, 3 move, 3 especial/anterior, 2 list) → dispatch correcto.
- Cambio de workspace en < 150 ms (router determinista, sin LLM).
- Cero secuestros: «abre el workspace» sin número no cambia nada.

---

## 5. Lane C — Memoria de sesión

### 5.1 Qué se guarda

Se reutiliza `episodes` (ya registra `ts, role, text, intent, ok, meta`) y se
añade `session_id` (id de arranque del servicio) + `ms`. **No** se guarda
pantalla por defecto.

Dato importante: `main.run_pipeline` ya registra **todos** los turnos en el
`finally`, incluidas las rutas deterministas (hora, archivos, apps, música). La
materia prima existe desde el primer día; lo que falta es poder consultarla.

### 5.2 Acciones nuevas

| Acción | Params | Ejemplo |
|---|---|---|
| `session_summary` | `{hours?: int}` | «¿qué he hecho hoy?» |
| `session_last` | `{}` | «¿dónde lo dejamos?» |
| `session_clear` | `{}` | «olvida la sesión» (confirmación) |

### 5.3 Consultas (deterministas)

- `session_summary(horas=8)`: agrupa episodios `role=user` + `ok=1` por hora,
  responde en 3-6 frases: «A las 18:40 abriste Spotify. A las 18:52 buscaste
  config.py y lo abriste. A las 19:01 pausaste la música.»
- `session_last`: último turno con `ok=1` + el anterior si forman un par
  («estabas buscando el README y lo abriste»).
- `session_clear`: borra los episodios de la sesión actual (no los hechos).

### 5.4 Detalles

- `modules/session_router.py` para las frases mecánicas («qué he hecho»,
  «dónde lo dejamos», «resume la sesión», «olvida la sesión»).
- Retención: 7 días de episodios (ya hay tope de 5.000 filas); el resumen se
  calcula al vuelo, no se guarda.
- Privacidad: `redact()` en escritura (ya existe); el resumen no incluye el texto
  literal del usuario salvo que sea una orden ejecutada.

### 5.5 Criterio de aceptación

- Tras 5 turnos reales, «¿qué he hecho hoy?» enumera esos 5 en orden y en < 100 ms.
- «¿dónde lo dejamos?» devuelve la última acción ejecutada, no una invención.
- «olvida la sesión» pide confirmación y no toca los hechos guardados.

---

## 6. Prompt y presupuesto

Hoy el prompt renderizado son **8.049 B de 8.400**. Las acciones nuevas no caben
sin dieta:

- +5 nombres en el catálogo (~200 B) y +4 ejemplos cortos (~450 B) → **excede**.
- Estrategia: 8 de cada 10 frases nuevas se resuelven en routers deterministas
  (pantalla, workspaces, sesión), así que al prompt solo entran **los nombres de
  acción** y **un** ejemplo por lane; se compensa quitando ejemplos que ya tienen
  router (`file_router`, `app_router`, `media_router`).
- Test de presupuesto (`tests/test_corpus_ordenes.py`) sigue siendo la puerta:
  sin verde no se mergea.

---

## 7. Fuera de alcance (explícito)

- **Escribir/dictar texto en la app activa**: requiere `ydotool`/`wtype` (no
  instalados) y es inyección de entrada; si se hace, con confirmación y allowlist.
- **Clics o automatización de UI** (computer-use): solo tras P2 y con
  confirmación por acción.
- **Capturas continuas o vigilancia de pantalla**: no. Captura bajo demanda.
- **VLM en cada turno**: no. Solo cuando la acción lo pide.
- **Persistir imágenes** o historial visual: no.

---

## 8. Fases

| Fase | Contenido | Esfuerzo | Puerta de salida |
|---|---|---|---|
| **P2-1** | OCR + `screen_read`/`find`/`windows` + router + workspaces | 2 días | 10 lecturas sin inventar y 12 frases de workspace |
| **P2-2** | Memoria de sesión (SQL + router + 3 acciones) | 0,5 día | resumen real de 5 turnos < 100 ms |
| **P2-3** | VLM local (`moondream:1.8b`) para describir/preguntar | 1-2 días | ≤ 6 s p50 y VRAM estable |
| **P2-4** | Escalado OpenCode (opt-in) | 0,5 día | credenciales válidas + fail-loud |

Orden deliberado: primero lo que no depende de modelos (1 y 2), luego el VLM y
por último la nube. Si la VRAM no da para el VLM, P2-1 y P2-2 siguen siendo
útiles por sí solos.

---

## 9. Riesgos

| Riesgo | Mitigación |
|---|---|
| 4 GB de VRAM: el VLM expulsa al router (recarga 1-2 s) | VLM solo bajo petición, `keep_alive=0`, resize 1280 px, medir antes de fijar modelo |
| OCR sin español (`tesseract-data-spa` no instalado) | instalarlo en P2-1; mientras, fallback `eng` avisando en log |
| Texto OCR sucio (iconos, columnas) | `--psm 6` + limpieza + narración por frases; nunca “adivinar” |
| OpenCode caído (429/401 medido) | T0/T1 no dependen de la nube; fail-loud y tarea de validación previa |
| Privacidad (pantalla con secretos, tokens) | tmpfs + borrado + sin logs + `redact()` + cloud opt-in |
| Falsos positivos del router de workspaces | solo dispatch si el target existe; «abre el workspace» no hace nada |
| El resumen de sesión miente | SQL determinista, sin LLM; se listan acciones ejecutadas, no interpretaciones |
| Prompt por encima de 8.400 B | un ejemplo por lane; quitar ejemplos con router; test de presupuesto |

---

## 10. Tareas

- [P2-1 · Visión de pantalla](tasks/p2-1-vision-pantalla.md)
- [P2-2 · Workspaces](tasks/p2-2-workspaces.md)
- [P2-3 · Memoria de sesión](tasks/p2-3-memoria-sesion.md)
