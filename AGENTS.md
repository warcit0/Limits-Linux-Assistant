# AGENTS.md — Contexto de Trabajo para Agentes y Desarrolladores

Guía técnica de referencia para trabajar en el código de **Limits** (asistente de voz
para Linux). Léela completa antes de modificar nada.

## 1. Qué es

Asistente de voz terminal-first para CachyOS + Hyprland (Wayland).
Pipeline por turno: **STT local → rutas deterministas → LLM local (Ollama) →
Executor con cortafuegos → TTS local**.

Modo experimental opt-in: `AGENT_ENABLED=true` conserva las rutas rápidas y
coordina objetivos con LangGraph, estado por sesión y especialistas. La instalación
actual lo tiene activado; el valor predeterminado distribuido sigue siendo `false`
para permitir instalaciones conservadoras y reversión explícita. Diseño y
estado: `docs/asistente-por-objetivos.md`, tarea
`docs/tasks/mejora-1-asistente-por-objetivos.md`.

- **Identidad del producto:** "Limits" (no usar nombres antiguos como Carmen/Luna).
- **Versión:** gestionada SOLO en `version.py` (`__version__`, `STATUS`). Actualmente
  `1.0.0-prealpha` / `unstable`: el formato de intents puede cambiar sin aviso.
- **Idioma:** todo el contenido orientado al usuario (respuestas de voz, prompts,
  docs) va en español; identificadores y comentarios de código en español también.

## 2. Comandos de desarrollo

```bash
# Ejecutar en modo texto (no requiere micrófono — la forma principal de probar)
limits --text            # equivalente a ./limits-env/bin/python main.py --text

# Lanzador global: bin/limits (symlink en ~/.local/bin). Flags: --text/--once/
# --takeover (para el service de fondo automáticamente para evitar conflicto
# de micrófono/puerto 8765). Control del servicio: limits-service start|stop|
# restart|status|logs

# Checklist pre-commit / pre-release (router 100 % local, sin Groq)
./limits-env/bin/python -m py_compile main.py config.py version.py \
    modules/*.py commands/*.py scripts/*.py
./limits-env/bin/python -m unittest discover -s tests -v
./bin/measure-router --min-accuracy 0.90        # requiere Ollama
./limits-env/bin/python scripts/probe_grounding.py   # 8 frases, sin ejecutar

# Tras cambiar código o .env, si el servicio está activo:
systemctl --user restart limits.service
```

Prompt slim: `prompts/system_prompt.txt` ≤ ~6KB en crudo; renderizado ≤ 8400 B
(incluye hasta 600 B de `{memory}`). 1 action nueva → ≤1 few-shot.
Corpus: `tests/corpus_ordenes.json` (≥25). Resultado: `logs/measure_router_last.json`.
Docs: `docs/plan-prompt-corpus-local.md`.

## 3. Estructura y responsabilidades

| Ruta | Responsabilidad única |
|---|---|
| `main.py` | Orquestador: argparse (`--text`, `--once`), SIGTERM graceful, wake word inline, loop |
| `config.py` | Único punto que lee `.env`. Añade aquí toda variable nueva |
| `version.py` | Metadatos de versión. Única fuente de verdad para versionar |
| `modules/llm.py` | Router **100 % local** (Ollama, `qwen2.5:1.5b-instruct`, ctx 8192). Historial de 6 mensajes. Devuelve dict validado por `grounding` o intent `unknown`. Renderiza `{now}` por turno |
| `modules/stt.py` | PyAudio + webrtcvad (corte: 900ms silencio / máx 10s) + faster-whisper int8 |
| `modules/tts.py` | piper-tts → pipe → aplay 22050Hz S16LE; fallback espeak-ng. `speak()` devuelve `ok|interrupted`; `pause_all`/`resume_all` (SIGSTOP/SIGCONT) |
| `modules/speech_controller.py` | Barge-in: VAD mientras habla, pausa/reanuda si es eco, palabras clave («para») y `pending_text` para encadenar |
| `modules/executor.py` | `action_map` action→handler, cortafuegos de tipos/params, flujo confirm/cancel con estado |
| `modules/clock.py` | Fuente única de verdad temporal: `now_line`/`time_line`/`date_line`/`weekday_line`/`parse_duration` (sin `locale`) |
| `modules/quick_routes.py` | Rutas deterministas de un dato (hora/fecha) **antes** del LLM; excluye horarios ajenos («a qué hora abre…») |
| `modules/memory.py` | Hechos/notas/episodios en SQLite (`~/.limits/memory.db`, WAL + FTS5, 600). Singleton `get_store()`; si falla, `enabled=False` y todo sigue |
| `modules/memory_router.py` | «recuerda que…», «olvida…», «qué sabes de mí», «cuál es mi X» sin LLM |
| `modules/file_router.py` | Ruta determinista de archivos: «lista la carpeta X», «muéstramelo», «ábrelo», «abre el archivo ~/…», «abre el segundo» |
| `modules/app_router.py` | Ruta determinista de apps: «abre/cierra `<app>`», «pon `<app>` en pantalla» (catálogo real de `APP_MAP`) |
| `modules/media_router.py` | Ruta determinista de música: «pausa/siguiente/reanuda/para la música», «pon `<artista>` en Spotify» |
| `modules/grounding.py` | Verificador determinista P1: catálogo real, evidencia por dominio, enums con alias. `grounded=False` → no se ejecuta |
| `modules/desktop_agent.py` | Lane `desktop_task`: OpenCode DeepSeek con respaldo NVIDIA DeepSeek; path guard |
| `modules/orchestrator.py` | Modo por objetivos: ciclo LangGraph, roles, continuidad, autorizaciones y cancelación |
| `modules/agent_providers.py` | Ollama, OpenCode CLI V2 y NVIDIA SSE; respaldos independientes por rol |
| `modules/task_state.py` | Estado privado y atómico por sesión, recibos y artefactos; separado de los recuerdos personales |
| `modules/task_tools.py` | Herramientas internas del coordinador: alcance observado, scripts bwrap y resultados con evidencia |
| `modules/gateway.py` | Gateway WebSocket móvil (`GATEWAY_ENABLED`): token pairing, lock de turno vía pipeline compartido, media firmada para casting |
| `modules/listener.py` | ⚠️ NO USADO — versión threaded futura del wake word |
| `commands/apps.py` | Abrir/cerrar apps (`APP_MAP`, `PROCESS_ALIASES`) |
| `commands/system.py` | Volumen/brillo/lock/info/shutdown/hyprland (`WINDOW_CLASS_MAP`) |
| `commands/web.py` | Búsquedas (raspa DDG Lite para resumen hablado) y URLs |
| `commands/dev.py` | Terminal con allowlist, git/docker status, abrir proyectos |
| `commands/files.py` | fd/find + excludes, search_and_open, reveal/open_last, foco Hyprland, copy/move/rename |
| `commands/media.py` | Spotify URI, YouTube mpv+yt-dlp, letras lyrics.ovh, canción actual |
| `commands/tv.py` | Casting a Chromecast/Android TV: discover/list, cast (current/query), control |
| `commands/custom.py` | Plantilla vacía para comandos del usuario |
| `prompts/system_prompt.txt` | System prompt few-shot. `{username}` se sustituye desde env |
| `tests/` | Suite unittest (voz, gateway, TV, files, desktop_agent, corpus) |
| `tests/corpus_ordenes.json` | Frases → action esperada; medir con `./bin/measure-router` |
| `docs/` | Diseño de integraciones; `catalogo-ordenes-audit.md`, `plan-desktop-task.md` |
| `docs/track-redactar-apps.md` | APLAZADO — tipar/redactar en apps (adapters UI), no mezclar con el router |
| `setup-service.sh` | Instala/actualiza `~/.config/systemd/user/limits.service` (idempotente: enable + linger) |
| `scripts/healthcheck.py` · `bin/limits-health` | Salud: servicio, puerto, handshake WS autenticado y micrófono. Sale 1 si falla algo crítico |
| `bin/limits-qr` | QR de emparejamiento del móvil (`--rotate` revoca el token); no arranca Limits |

## 4. Flujo de datos de un turno

```
main.run_pipeline(user_input)
  → quick_routes · memory_router · file_router · app_router · media_router  # sin LLM
  → llm.process(text)            # propone {intent, action, params, response} + grounding
  → executor.execute(parsed)     # string para hablar (rechaza grounded=False)
      ├── params.pop("requires_confirmation")
      ├── si hay _pending_action: solo intents "confirm"/"cancel" deciden;
      │   cualquier otro comando cancela lo pendiente y se procesa normal
      ├── confidence < 0.5 → pedir clarificación
      ├── acción peligrosa → guardar en _pending_action y pedir confirmación
      └── _run(): filtra params por inspect.signature(handler), ejecuta,
          devuelve "{response} {resultado}" si el handler devolvió algo útil
  → tts.speak(respuesta)
  → memoria: episodio user/assistant + `{memory}` refrescado en el próximo turno
```

## 5. Reglas críticas de seguridad (NO romper)

1. **Nunca `shell=True`** ni construir comandos con f-strings usando datos del LLM.
   Siempre listas de argumentos en `subprocess`.
2. **Allowlist en `dev.py`:** match exacto o con límite de palabra (`cmd == safe or
   cmd.startswith(safe + " ")`). No añadir `curl`, `cat`, `sudo`, `rm` ni anything
   que pueda leer archivos privados o hacer red arbitraria.
3. **Confirmaciones explícitas:** `shutdown`/`reboot`/`move_file`/`rename_file`
   viven en `DANGEROUS_ACTIONS`. El agent compuesto usa `propose_move`/
   `propose_rename` (mismo pending). La decisión SOLA viene del intent
   `confirm`/`cancel`. Jamás inferir de substrings ("sí", "ok") en texto libre.
4. **Cortafuegos de tipos:** el LLM alucina estructuras. `execute()` coacciona tipos
   (`params` debe ser dict, `confidence` float, etc.) y `_run()` filtra kwargs contra
   la firma real del handler. Cualquier handler nuevo hereda esta protección gratis.
5. **Privacidad:** no subir el nivel de log de INPUT/RESPONSE por encima de DEBUG
   (`main.run_pipeline`). `.env`, modelos y logs están gitignored.

## 6. Cómo extender

### Añadir un comando nuevo (3 pasos obligatorios)
1. Método en la clase adecuada de `commands/` (o `custom.py`). Docstring breve en español.
2. Entrada en `action_map` (`modules/executor.py`). Si es destructiva → añadirla a
   `DANGEROUS_ACTIONS`.
3. Al menos un ejemplo few-shot JSON en `prompts/system_prompt.txt`
   (intent nuevo → añadirlo también a la lista enum del prompt).

### Convenciones de handlers
- Devolver `str` con info útil (se lee en voz alta tras el response default); `None`
  o `""` = solo el response default.
- Validar/clampear parámetros numéricos dentro del handler (ver `set_volume`,
  `set_brightness`).
- Operaciones largas → `subprocess.Popen(..., start_new_session=True)` +
  `stdout/stderr=DEVNULL`; síncronas → siempre `timeout=`.

### Cambiar el comportamiento del LLM
- Los ejemplos del system prompt son la API real: el executor solo conoce las actions
  registradas. Mantener ejemplos y `action_map` sincronizados.
- Si añades un campo al JSON de respuesta, valida su tipo en `execute()` igual que
  los existentes.
- `HISTORY_SIZE` (6) controla cuántos turnos se conservan Y se envían.

### Memoria persistente (P0-3)
- `get_store()` es un singleton perezoso: no crear conexiones por turno y no
  tocar disco al importar (el CLI y el servicio conviven por WAL).
- Solo se guarda lo **explícito** del usuario (router determinista); extraer
  hechos con LLM queda para v2 y siempre con confirmación.
- `{memory}` se renderiza por turno (≤600 B) y las notas se muestran sin hash.
- Acciones: `remember`, `forget`, `memory_list`, `memory_recall`, `memory_stats`.
- La redacción de secretos ocurre en escritura (`redact()`), no al leer.

### Barge-in (P0-4)
- `SpeechController` envuelve al `VoiceRouter`: no llamar `tts.speak` directamente
  desde `main` (rompe la interrupción).
- Flujo: VAD (ventana deslizante, ~1/4 de tramas) → `pause_all()` → transcribir →
  eco/ruido → `resume_all()`; comando → `stop_event` + `pending_text`.
- El eco se comprueba **antes** de las palabras clave, pero una interjección de
  1-2 palabras nunca se considera eco (si no, «para» no cortaría nunca).
- `_terminate` manda SIGCONT antes de SIGTERM: un proceso pausado no atiende
  SIGTERM hasta reanudarse.
- Desde el móvil hay dos vías de corte, ambas sin esperar al turno: `{"type":
  "stop"}` y un `command` de **una sola palabra** de `BARGEIN_KEYWORDS` (el
  micro de la app usa el reconocedor de Android y manda texto). Frases como
  «para la música» no cuentan: son comandos.
- Traza: `LIMITS_BARGEIN_DEBUG=1` (y `LIMITS_BARGEIN_VAD_MODE`, 0-3).

### Lane compuesto desktop_task
- Frases multi-paso → `desktop_task` + `params.goal` verbatim (o keywords).
- Agent: `DESKTOP_AGENT_PROVIDER=opencode` mantiene DeepSeek de OpenCode como
  principal. `DESKTOP_AGENT_FALLBACK=nvidia` usa NVIDIA DeepSeek si falla (incluida
  cuota agotada). Nunca usa Nemotron como respaldo de desarrollo. Router: Ollama 1.5b.
- Los fragmentos enviados a NVIDIA u OpenCode se procesan en servidores remotos.
- Path guard: open/copy solo con rutas observadas en el turno.
- Docs: `docs/plan-desktop-task-calidad.md`. Tipar apps: `docs/plan-redactar-apps.md`.

### Coordinación por objetivos (mejora 1, experimental)
- Configuración y reversión en `config.py`: `AGENT_ENABLED=false` mantiene el
  pipeline anterior; los modelos por rol y límites se configuran por separado.
- Prioridad aclarada por el usuario (2026-10-31): desarrollo usa DeepSeek de
  OpenCode y solo ante fallo NVIDIA `deepseek-ai/deepseek-v4.1-flash`; análisis
  usa Big Pickle de OpenCode y solo ante fallo `nvidia/nemotron-3.5-bolt-e4b`.
  `AGENT_REMOTE_PROVIDER=opencode_con_respaldo` aplica estas parejas independientes.
  No alternar por consulta ni cruzar respaldos entre roles. Tras el enfriamiento
  se vuelve a intentar el principal. Cancelar nunca dispara respaldo.
  Clave solo en `.env`, nunca en logs; presupuesto compartido entre intentos.
- Respaldos adicionales autorizados: `AGENT_GROQ_FALLBACK=true` añade GPT-OSS
  120B como último respaldo de ambos roles, manteniendo OpenCode primero.
  `AGENT_GLM_FALLBACK=true` añade GLM Flash antes de NVIDIA DeepSeek en desarrollo;
  mantenerlo desactivado si no responde. Cada uno tiene su propia clave en `.env`.
  Groq recibe JSON sin streaming; usa hasta una repetición de inferencia por
  `Retry-After` o formato inválido, dentro del presupuesto y sin repetir efectos.
  El router de órdenes sigue 100 % local: esto no restaura Groq en `modules/llm.py`.
- `AGENT_SUPER_FALLBACK=true` añade Nemotron Super antes de Bolt, únicamente
  para análisis: Big Pickle → Super → Bolt → Groq si está habilitado.
  Super y Bolt usan `NVIDIA_SUPER_API_KEY` y `NVIDIA_BOLT_API_KEY`; la clave
  NVIDIA original y la de GLM permanecen separadas. Desarrollo no usa Nemotron.
- OpenCode CLI V2 usa perfiles con herramientas nativas denegadas. Las
  herramientas internas de `task_tools.py` pertenecen al catálogo del coordinador;
  no añaden intents al prompt ni acciones al `action_map` del router anterior.
- No desactivar el grounding: las operaciones heredadas mantienen la validación
  de firma, catálogo y objetivo; los archivos requieren alcance y observación.
- Scripts: bwrap real, sin red/HOME, copia temporal para pruebas y aplicación
  de la versión probada solo tras confirmar la propuesta vigente. No sustituirlo
  por una carpeta de trabajo sin aislamiento ni ampliar la terminal existente.
- Las aprobaciones identifican tarea, revisión, código y datos probados. Se
  invalidan al cambiar de objetivo, cancelar, caducar o reiniciar. Los recibos
  impiden repetir automáticamente efectos iniciados o completados.
- Tras probar un script en modo preparar, presentar la propuesta verificable sin
  otra inferencia; los originales siguen intactos hasta confirmar.
- Tras aplicar y verificar un script, comunicar el resultado de la herramienta
  directamente, sin otra inferencia que pueda fallar por cuota y ocultar el efecto.
- Estado temporal en `AGENT_TASK_PATH`; nunca convertir inferencias en hechos
  personales. Mantener completo el artefacto de respuestas largas y breve el audio.
- La sesión móvil es por conexión, separada de la local; desconectar cancela la
  tarea. Reconectar no recupera esa sesión automáticamente.
- `SpeechController` sigue siendo dueño de la voz y escucha también durante
  consultas en este modo. El móvil cancela sin esperar al bloqueo. Descartar
  resultados tardíos y conservar el bloqueo hasta terminar la entrega y el audio.
- Investigación usa `GEMINI_RESEARCH_DAEMON=false` por defecto (espera completa
  de gemdev), exige dos URLs distintas y fechas y conserva el documento completo.
- Gemini sigue siendo información para voz/artefactos; jamás alimenta herramientas
  ejecutables. No realizar cambios automáticos a partir de instrucciones de la web.
- Verificación adicional: `scripts/probe_objectives.py` (40 casos, sin ejecutar
  herramientas). Evidencias y pendientes: `docs/validaciones/mejora-1/informe.md`.

### Integración Gemini conversacional (F1 implementada)
- **Despausada 2026-08-25**: `modules/gemini.py` implementa el puente por
  subprocess al CLI `gemdev` (ruta en `GEMINI_BIN`; repo actual del usuario:
  `~/Work/WebAi-to-local-CLI-LLM`). Router determinista por palabras clave en
  `make_pipeline`: "investiga/infórmame/googlea/busca en internet/novedades…"
  → research; frases que empiezan por "gemini" o "pregúntale a gemini" → talk;
  además intents `gemini_talk`/`gemini_research` enseñados en el prompt para
  casos sin palabra clave. Memoria de conversación vía `-c GEMINI_SESSION`.
- Regla dura VIGENTE: la salida de Gemini va SOLO a TTS/log, jamás al
  `action_map` ni al executor (bloquea prompt injection desde contenido web).
- Research fail-loud: si `NOT_SIGNED_IN`, artefacto vacío o respuesta hueca
  (&lt; `GEMINI_MIN_RESEARCH_CHARS`, default 200) → frase explícita (pide
  `gemdev login`); nunca openers Jarvis vacíos. Ver
  `docs/plan-gemini-research-calidad.md`.
- Contrato: `chat -t N --json -c FILE` → puntero JSON en última línea stdout,
  texto en archivo `f`. Siempre pasar `-t`.

### Control remoto desde Android (F1–F2 implementados, app pendiente)
- Diseño en `docs/plan-control-remoto-android.md`. Implementado: gateway
  WebSocket embebido en Limits (`modules/gateway.py`, opt-in `GATEWAY_ENABLED`)
  que alimenta el pipeline compartido, y casting a TV como comandos nativos
  (`commands/tv.py`, usables también por voz local).
- Reglas duras (vigentes para la app Android cuando se construya): el texto del
  móvil pasa por el MISMO router LLM + executor (cero superficie nueva); token
  de pairing obligatorio (`~/.limits/gateway_token`, chmod 600); el lock de turno
  vive en `main.make_pipeline` y serializa voz local vs móvil (nunca intercalar
  salidas); archivos locales solo por URLs firmadas del gateway.
- **Emparejamiento sin teclear (2026-10-28):** el gateway imprime un QR
  (`GATEWAY_SHOW_QR=true`, requiere `qrencode`) con
  `limits://pair?h=IP&p=PORT&t=TOKEN`. La app lo escanea (⚙ → Escanear QR) o lo
  abre con la cámara del móvil (deep link `limits://pair`). Reimprimir/rotar:
  `./bin/limits-qr [--rotate]`. El rechazo de auth es `close 4401` **tras**
  `accept()`: si se cierra antes del upgrade uvicorn responde 403 y el cliente
  no puede distinguir token malo de red caída.

### Voz natural ElevenLabs (implementada)
- Voz dual por economía de cuota: Piper para respuestas cortas del sistema,
  ElevenLabs (API free) para respuestas largas donde importa la entonación (y
  para el futuro puente Gemini). Router `VoiceRouter` (`modules/tts.py`) por
  modo (`auto|gemini|off`), umbral de longitud, tope por turno, cache de frases
  y fallback automático a Piper ante cualquier fallo. Opt-in vía `.env`.
- Módulos: `modules/tts_elevenlabs.py` (motor), `modules/voice_utils.py`
  (limpieza markdown→hablado + cortes por frase), tests en `tests/test_voice.py`.
- Regla dura: la salida de ElevenLabs es solo audio hablado; jamás se parsea ni
  alimenta al executor. La API key vive SOLO en `.env`, nunca en código/logs.
- Las utilidades de voz son compartidas: cuando el puente Gemini se retome, su
  salida etiquetada `source="gemini"` pasa por la misma capa sin cambios.

## 7. Gotchas conocidos

- **El router es 100 % local** (decisión 2026-10-28): Groq se eliminó del código,
  de `config.py` y del `.env` (claves comentadas). No hay fallback cloud.
- **`OLLAMA_NUM_CTX=2048` trunca el prompt** (~1900 tokens): el modelo pierde las
  instrucciones y el acierto cae al 28 %. Con `8192` sube a 88-94 % y, con las
  rutas deterministas y el prompt actual, a 100 % del corpus (p50 ~1,6 s). No
  bajarlo sin volver a medir con `./bin/measure-router`.
- El 3b no mejora al 1.5b: da 81 % y tarda el doble (4,2 s p50). Por eso el
  router usa `qwen2.5:1.5b-instruct`; el 3b queda solo como fallback del
  `desktop_agent`.
- `LLMEngine` llama una sola vez (temperatura 0 + seed fija): si el grounding no
  puede anclar la propuesta, se pregunta al usuario en vez de reintentar en
  silencio.
- La wake word se filtra sobre la transcripción completa; `WAKE_WORD=Limits` añade
  variaciones "límites/limites" automáticamente en `main.py`.
- `focus_window` consulta `hyprctl clients -j` antes de enfocar; si no existe la
  ventana, informa del fallo sin abrir aplicaciones. El modo conversacional usa
  únicamente `enfocar_ventana` con dirección observada.
- `hyprctl`/`wpctl`/`playerctl` requieren sesión gráfica activa; bajo systemd user
  service el script ya exporta `WAYLAND_DISPLAY` y `XDG_RUNTIME_DIR`.
- Los modelos de Whisper se descargan on-demand de HF en el primer arranque.
- En este equipo el micro **no capta los altavoces** (RMS ambiente ~89, pico
  ~179): no hay autocorte hoy, pero con altavoces audibles el eco se detecta y
  se reanuda. Cada detección cuesta ~1,5 s de pausa: con altavoces, auriculares
  o `module-echo-cancel` de PipeWire.
- El modelo **omite `confidence`** con frecuencia: `LLMEngine.process` la
  normaliza a 0.9 (`DEFAULT_CONFIDENCE`) y el executor ejecuta si falta (no
  bloquear: rompía órdenes legítimas como «cuánta RAM tengo»). Quien decide de
  verdad es el grounding, no la confianza que se declara.
- El grounding **bloquea de más antes que ejecutar de más**: una frase legítima
  que acaba en «no estoy seguro de haber entendido» se arregla con una ruta
  determinista o una palabra en `ACTION_HINTS`, nunca aflojando el verificador.
- `scripts/probe_grounding.py` reproduce la sonda de 8 frases que originó P1
  (sin ejecutar handlers) y `scripts/measure_router.py` mide el corpus real con
  las mismas rutas que `main.run_pipeline`.
- `{now}` y `{username}`/`{machine_map}` se sustituyen en momentos distintos:
  usuario y mapa al cargar el prompt, `{now}` en cada turno
  (`_render_system_prompt`). No congelar la hora al arrancar.
- Python objetivo: 3.11+ (el entorno usa 3.14). Sintaxis moderna permitida
  (`int | None`).

## 8. Release checklist

1. Actualizar `__version__`/`STATUS` en `version.py`.
2. Nueva entrada arriba en `CHANGELOG.md` (formato Keep a Changelog).
3. Badge de versión del README acorde.
4. `py_compile` completo + smoke test `--text` de los intents tocados.
5. Commit estilo conventional (español): `feat:`, `fix:`, `docs:`...

## 9. Mejora 2 · Conversación progresiva (2026-10-31)

- `modules/workspace_router.py` precede al LLM: work space/world space/espacio de
  trabajo con destino inequívoco. `commands/workspaces.py` cambia entre espacios
  existentes y comprueba estado; mover ventana es explícito y verifica su address.
  Especiales y creación siguen pendientes. `list_running` consulta clientes Hyprland.
- `modules/streaming.py`: protocolo gemdev v1 `status/delta/final/error`, límites de
  tamaño, cancelación del grupo de procesos, frases estables y cola única. Requiere
  el gemdev actualizado en `~/Work/WebAi-to-local-CLI-LLM`; `GEMINI_STREAMING=false`
  permite uso clásico manual, sin conmutación automática entre protocolos.
- Avances Gemini son provisionales hasta validación. Solo voz/texto, nunca acciones.
  Si revisa o falla, corregir explícitamente. No volver a leer el final ya emitido.
  Piper reproduce los avances para evitar otra dependencia de red; una captura de
  micrófono y un reproductor por turno, bloqueo local/móvil hasta terminar audio.
- `prompts/agent_chat.txt` permite conversación libre de Qwen en modo lectura sin
  herramientas; ese texto jamás se interpreta como JSON de ejecución. Las acciones
  siguen el catálogo, grounding, permisos y confirmaciones. La pregunta abierta
  vive en la tarea; no es un hecho personal. `DIALOGUE_FOLLOWUP_SECONDS` (10) abre
  una breve respuesta sin wake word; un sí conversacional no aprueba operaciones.
- `tests/test_000_aislamiento.py` aísla memoria/tareas/logs durante cada prueba.
  `modules/memory_hygiene.py` respalda antes de poner episodios sintéticos en
  cuarentena; no borrar hechos ni conversaciones reales. No guardar secretos en
  informes. `scripts/probe_conversation.py --live` usa tareas temporales, audio real
  sin micrófono y restaura el workspace original y el servicio en `finally`.
- Validación y límites: `docs/validaciones/mejora-2.md`. La nueva interrupción por
  micrófono no se validó manualmente: el usuario pidió pruebas automáticas.

## 10. Presencia visual (Mejora 3)

- `modules/presence.py`: socket Unix privado en `$XDG_RUNTIME_DIR/limits`, 0700/0600,
  estado y energía PCM, secuencia e id de turno; nunca texto, claves ni acciones.
  Solo acepta `stop` ligado al turno actual. El widget no concede aprobaciones.
- `ui/presence/Presence.qml` + shader `nucleo.frag`: Quickshell, capa overlay,
  sin foco ni exclusión; captura clics solo en la etiqueta/control. Render a 30 Hz,
  detenido cuando está oculto; reconexión y snapshot. Servicio independiente.
- `modules/audio_meter.py` comparte la reproducción PCM de Piper y el decodificado
  local de ElevenLabs/espeak mediante ffmpeg cuando la presencia está habilitada.
  No medir el micrófono ni reproducir dos salidas. Pausa y cancelación deben vaciar
  energía y rechazar audio antiguo. Mantener métricas `on_audio_start` después de PCM.
- Instalar con `./setup-widget.sh`, activar `PRESENCE_ENABLED=true` y reiniciar
  Limits. Detener la UI con `systemctl --user stop limits-widget.service` no debe
  afectar al asistente. Configuración centralizada en `config.py`.
- Regenerar `nucleo.frag.qsb` con `/usr/lib/qt6/bin/qsb --glsl '100 es,120,150'
  --hlsl 50 --msl 12 -o ui/presence/nucleo.frag.qsb ui/presence/nucleo.frag`.
- Vista de diseño: `qs -p ui/presence/preview.qml`; no conectarla a sesiones reales.
  Aceptación optativa sin micrófono ni modelos: `scripts/probe_presence.py --live`;
  detiene/restaura servicio y usa memoria y artefactos desechables.

### Reparación conversacional (2026-10-31)
- `modules/operational.py` compila órdenes cotidianas en pasos vinculados al texto;
  `operation_intent.py` distingue órdenes, consultas y referencias explícitas.
- Resolver proyectos solo dentro de `PROJECT_ROOTS`; ante ambigüedad o búsqueda
  incompleta no seleccionar una coincidencia. No confundir enviar una petición con verificar su efecto.
- Hyprland materializa espacios al usarlos: 1–10 son destinos válidos aunque no
  aparezcan en `workspaces`; tecla 0 equivale a 10. Los especiales tienen semántica propia.
- Aceptación: `scripts/probe_operations.py --live` reproduce diez turnos sin voz,
  aísla memoria/tareas y restaura ventanas/foco/servicio; abre ventanas reales.

## 11. Agente general y memoria compartida (2026-10-31)

- `AGENT_SEMANTIC=true`: fuera de atajos inequívocos, interpretar significado,
  seleccionar capacidades/contratos reales, ejecutar y revisar evidencia. El
  formato de intérprete añade objetivos, observación, síntesis y selección de
  herramientas; no depender de un verbo inicial ni de ejemplos de frases.
- El modo general no pasa por el router heredado para órdenes no reconocidas.
  `general_agent.py` controla estados; `capability_tools.py` descubre herramientas,
  ventanas y proyectos reales. Registrar una nueva capacidad en su familia y
  describir parámetros/prerrequisitos; no añadir otro patrón de lenguaje por defecto.
- Cada efecto requiere autorización semántica vinculada a usuario, revisión,
  acción y parámetros. `task_tools.huella_autorizacion` solo lo genera el
  coordinador. La prueba sustituye únicamente la dependencia léxica de dominio de
  `grounding.check`; catálogo, enums, exclusiones, tipos, rutas y confirmaciones
  siguen obligatorios. Datos externos o memorias no conceden permisos.
- Verificar cobertura por resultados, no contar llamadas como objetivos cumplidos.
  Consulta negativa verificada es una respuesta válida; no acredita un efecto
  positivo solicitado. La síntesis se revisa contra datos antes de presentarse.
- No preguntar prematuramente si un catálogo o consulta disponible puede resolver
  el dato. No permitir que una respuesta de texto cierre una operación sin herramientas.
- `AGENT_COGNITIVE_PROVIDER=groq` configura el rol cotidiano flexible con GPT-OSS;
  Qwen queda disponible para modo local y compatibilidad. Respaldos de análisis y
  desarrollo conservan sus parejas anteriores. No interpretar que el Qwen 1.5B
  basta para planificar porque pase el corpus antiguo. «Solo local/sin internet»
  obliga a Ollama ANTES de enviar la primera clasificación y evita escalado cloud.
- `KNOWLEDGE_ENABLED` y `KNOWLEDGE_VAULT` integran la MISMA SQLite con la bóveda
  propia ~/Documentos/Limits-Memoria. knowledge.py: FTS, procedencia, versiones,
  caducidad, cola dirty, bloqueo entre procesos y exportación atómica. Markdown es
  editable; conflictos e inferencias quedan pendientes y fuera de recuperación.
- Hechos explícitos se espejan por triggers. Recordar procedimientos solo tras
  resultados comprobados; las notas históricas no prueban el estado actual.
  Redactar secretos antes de escribir. Olvidar mantiene tombstones, retira derivados
  y cambia época global para invalidar contexto en otras sesiones. Los candidatos
  del modelo no se convierten automáticamente en hechos personales.
- Las pruebas se aíslan de la bóveda real mediante test_000_aislamiento.py. Probes
  heredados fuerzan modo anterior. `probe_general_agent.py` usa modelos reales y
  efectos simulados; `probe_general_live.py --live` usa volumen/sistema y memoria
  temporal, restaura volumen y servicio. Respetar cuota al medir; publicar fallos.


## 12. Ejecución coherente (mejora 5)

- `AGENT_COHERENT=true` junto con AGENT_SEMANTIC usa coherent_agent.py: una
  decisión puede proponer hasta cuatro pasos independientes, vinculados a citas
  del usuario. Sin propuesta Qwen, clasificador inicial ni jueces de cierre.
- Un plan marcado finaliza solo cierra directamente cuando TODOS sus pasos tienen
  recibos verificados y resúmenes aptos para voz. El modelo interpreta la cobertura;
  no es una garantía determinista de haber descompuesto bien cualquier petición.
- La autorización semántica se conserva para efectos no demostrables por controles
  directos acotados. Los atajos verifican dominio, negaciones, parámetros y catálogo;
  no aceptar una cita o id de objetivo como permiso suficiente. Mantener grounding,
  path guard, confirmaciones y sandbox. Lecturas y mutaciones no comparten permisos.
- Contrato común en command_result.py: completado, fallido, sin_verificar; None no
  acredita éxito. Handlers antiguos de efectos sin prueba quedan sin verificar.
- consultar_escritorio observa foco, especiales y ventanas; workspace numérico
  filtra y genera resumen. cerrar_ventana exige dirección observada; ocultar_especial
  exige especial observado y verifica el estado actual antes de usar el toggle.
- Recibos se guardan antes de comprobar una cancelación tardía. No repetir un efecto
  intentado sin observarlo. Persistir traza privada acotada por turno sin textos ni
  parámetros: inferencias, duración, herramientas, corrección y cierre.
- Catálogo cotidiano breve, ampliable por consultar_capacidades; no añadir patrones
  de frases. Presentación compartida evita estructuras internas y conserva resultados
  de consultas y acciones de un mismo turno.
- El usuario pidió únicamente tests automáticos: no ejecutar más probes de modelos
  ni pedirle una prueba manual guiada. Él probará libremente por voz.
- Plan/tarea: docs/plan-mejora-5-ejecucion-coherente.md y
  docs/tasks/mejora-5-ejecucion-coherente.md. No confundir aceptación automática con
  funcionamiento por voz validado por el usuario.

## 13. Recorrido cotidiano local (vigente, 2026-11-01)

- `AGENT_MODE=local` prevalece sobre flags históricos y fuerza Ollama para el uso
  cotidiano. Se reutilizan coherent_agent y Orquestador._ejecutar; no añadir otro ciclo.
  `legacy` mantiene el recorrido anterior. No usar respaldo remoto para órdenes locales.
- Contrato común para rutas rápidas y Qwen: intent (`command|chat|clarify`),
  operations (`[{action,params}]`, hasta seis independientes), complete y response.
  Las rutas completas se compilan sin inferencia; el resto llega COMPLETO a Qwen.
  No dividir la petición en cláusulas para decidir qué debe atender el modelo.
- Los esquemas de parámetros derivan de las firmas/contratos reales. El catálogo
  local no cambia por patrones de frases ni por haber observado una entidad.
  Los prerrequisitos se comprueban en validación antes de ejecutar. Consultar escritorio
  es la observación cotidiana de ventanas, foco y especiales. Las familias se descubren
  con consultar_capacidades; especialistas solo para desarrollo/análisis/investigación.
- Un lote se valida entero antes del primer efecto. No incluir un efecto que dependa
  de una observación aún no realizada. El ejecutor vuelve a validar cada operación.
  Mantener grounding estructural/exclusiones, permisos locales independientes, path guard,
  catálogo real, confirmaciones explícitas, sandbox y recibos contra repetición.
- Local_permissions verifica operación/destino en la petición original. Los atajos
  completos conceden permiso solo a su operación exacta compilada. Ni citas, confianza,
  recuerdos ni resultados externos autorizan cambios. Ante falta de evidencia, aclarar.
- El cierre usa recibos de los handlers: completado, fallido o sin_verificar. `complete`
  indica cobertura interpretada por Qwen, no prueba que haya comprendido todo. Un lote
  final entrega resultados directamente; solo se marca terminado con todos sus recibos
  comprobados. No añadir jueces ni otra inferencia para anunciar un resultado.
- Qwen recibe resultados del turno y la petición actual como último mensaje. El diálogo
  anterior se incluye solo con referencia explícita, acotado al último intercambio.
  Recuerdos personales disponibles por herramientas; no inyectar episodios automáticamente.
  El reproductor explícito conserva su referencia por sesión cinco minutos/generación.
- installed_apps abre ids .desktop observados con huella vigente. Spotify MCP stdio/PKCE
  permanece preparado y DESACTIVADO hasta Client ID/OAuth (`SPOTIFY_MCP_ENABLED=false`).
  No cambiar modelo ni atribuir entrenamiento de pesos a cambios de contexto/prompts.
- Diagnóstico opt-in `AGENT_QWEN_DIAGNOSTICS`: salidas-qwen.jsonl privado por turno,
  redacción de secretos, máximo 128 KiB, nunca textos ni parámetros en INFO.
- Restricción vigente: NO ejecutar tests, probes, consultas de aceptación a modelos ni
  pruebas manuales guiadas. Solo revisión estática/sintaxis y estado/arranque del servicio.
  No anunciar aceptación funcional ni tests superados. Reversión en el respaldo privado;
  no restaurar aprobaciones ni borrar memoria/bóveda. Los módulos legacy con consumidores
  se conservan para reversión y especialistas; no borrar código a ciegas.

- Catálogo de apps local: disponibles por PATH y parámetros app con enum derivado.
  Alias de explorador usan asociación XDG inode/directory; no imponer Thunar.
  Coincidencias aproximadas solo sugieren: no autorizan abrir otra app automáticamente.
- Una orden de cambio no termina mediante consultas preparatorias ni chat. Abrir un
  editor vacío no cumple abrir un proyecto. No convertir complete en prueba de cobertura.
- Multimedia espera disponibilidad/capacidad MPRIS, permite cancelación antes del envío,
  manda UN efecto y observa estado/identidad de pista después. No repetir ni cambiar
  reproductor/transporte por incertidumbre. Si no hay contenido/control, explicarlo.

## 14. Interlocutor y ejecución (vigente, 2026-11-01)

- El modo conversacional autorizado sustituye el recorrido de sección 13 al activarse:
  AGENT_MODE=conversacional fuerza agent/semantic/coherent y proveedores cotidianos locales.
  Interlocutor en AGENT_CONVERSATION_MODEL, ejecutor en OLLAMA_MODEL. Inicialmente 3B/1.5B
  ya instalados; no atribuir entrenamiento ni calidad demostrada a esa selección.
- Interlocutor primero en cada petición: chat/clarify, herramientas directas command o
  encargo task. Dispatch por JSON sin traducción intermedia. Un único ciclo en coherent_agent;
  conversation.py son contratos/contexto. Qwen recibe encargo y petición original completa.
- Acciones concretas entregan recibos directamente. Tareas abiertas pueden devolver
  informes al interlocutor para explicar. Historial breve y dos recuerdos confirmados.
  No heredar permisos ni destinos observados; reobservar antes de actuar. Olvido limpia contexto.
- En este modo local_permissions.autorizar_capacidad sustituye los permisos léxicos y
  grounding no reinterpreta el lenguaje. Conserva firmas, tipos, enums, catálogo, rutas,
  destinos observados, política de efectos, sandbox, confirmaciones y recibos. Los modelos
  deciden intención; no anunciar comprensión universal ni seguridad basada solo en prompts.
- Nuevas capacidades requieren declarar su política de efectos, no ejemplos de frases.
  Memoria explícita conserva su control específico. No terminal libre. Copiar rechaza
  destinos existentes; enviar contenido a TV requiere aprobación. Acciones cotidianas
  acotadas pueden ejecutarse sin juez adicional.
- Los textos de intención de command/task/delegate no se reproducen. Confirmaciones,
  efectos sensibles aprobados y Gemini conservan entrega directa; investigación jamás
  vuelve como instrucciones a un ciclo ejecutable. Una charla afirmativa no aprueba cambios.
- Plan/tarea: docs/plan-mejora-7-interlocutor.md y docs/tasks/mejora-7-interlocutor.md.
  Mantener la restricción de NO ejecutar pruebas/probes/inferencias de aceptación.
  Solo revisión estática/sintaxis y estado/arranque; aceptación por voz pendiente del usuario.

### Simplificación vigente (2026-11-01)

- Retirada la cita literal de las operaciones conversacionales: Qwen devuelve
  action/params. El coordinador conserva la petición original en el plan; no
  exigir al modelo copiar ni mantener errores del dictado. No nuevos jueces ni
  patrones léxicos. Firmas, tipos, enums, catálogo, destinos observados, sandbox,
  confirmaciones y recibos contra repetición siguen vigentes.
- Tras efectos concretos del interlocutor, entregar resúmenes reales directamente,
  sin inferencia de cierre ni voz libre anterior al efecto. Las tareas abiertas
  conservan el ejecutor; sus informes y lotes finales pueden pasar a una sola
  presentación sin herramientas, con fallback a recibos y sin reintento.
- Historial conversacional limitado a seis mensajes registrados, 350 caracteres
  por campo y dos recuerdos confirmados. No reinyectar el objetivo, pregunta o
  recibos anteriores como trabajo pendiente. La petición actual prevalece; las
  referencias se interpretan con el diálogo. No hay garantía de comprensión universal.
- Prompt compacto y catálogo sin firmas duplicadas; esquemas conservan parámetros.
  Petición completa enviada una sola vez. Sin timestamp cambiante innecesario.
  Métricas privadas de carga/evaluación/generación y cache si Ollama la informa;
  no asumir que ausencia de la métrica significa cero. No cambiar modelos/contexto.
- Confirmo/adelante sin aprobación vigente son conversación. Nunca reutilizar una
  aprobación vieja ni convertir una afirmación conversacional en autorización sensible.
- Foco por dirección observada sin apertura implícita. Gemini sigue solo voz/datos.
- Texto final del flujo progresivo se envía antes de esperar su audio. Reservar
  audio_entregado antes del callback para evitar otro reproductor. Mantener el lock
  hasta cerrar voz/escucha. Eventos de audio y turn_finished con id de turno en WS.
- Android aplica estados en Main e ignora cierres de otros turnos. Este código
  requiere instalar el APK compilado; no afirmar que el móvil fue actualizado por editarlo.
- NO ejecutar tests, probes ni inferencias de aceptación. Solo sintaxis/revisión
  estática y estado/arranque; el usuario comprueba libremente por voz.
