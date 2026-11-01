# Changelog

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/).
Versionado semántico simplificado; mientras dure el estado prealpha pueden haber
cambios rompientes en cualquier release.

## [Unreleased]

- Catálogo instalado y asociación XDG para abrir apps; sugerencias aproximadas sin
  ejecución implícita, protección de cobertura de órdenes/proyectos y control MPRIS
  con disponibilidad, cancelación, envío único y verificación posterior.


- Recorrido local unificado: rutas rápidas y Qwen compilan operaciones al mismo
  ejecutor; lotes independientes, contratos de parámetros reales, contexto por turno
  y cierre por recibos. Retirados segmentación y filtros/cierres por frases del ciclo
  local. Revisión estática únicamente, sin aceptación funcional.


- Recibos de memoria confirmados tras commit/borrado; referencias de archivos rápidos
  se convierten a destinos observados y pasan por el mismo control de rutas.

### Cambiado — Mejora 6
- Selector AGENT_MODE=local: Qwen atiende el escritorio cotidiano sin Groq ni jueces por paso; especialistas por capacidad y permisos locales por operación/destino.
- Contexto acotado sin duplicar contratos, consulta de aplicaciones instaladas y verificación de foco antes de cerrar ventanas.
- MCP Spotify stdio con OAuth PKCE, preparado y desactivado hasta conectar la cuenta.
- Aceptación preparada sin ejecutar tests ni consultas de prueba por petición del usuario.


### Corregido
- Ciclo cotidiano único con planes acotados, resultados verificables, recibos ante cancelación y respuestas sin estructuras internas.
- Resolución observada de ventanas y especiales; resultados vacíos dejan de considerarse solicitudes exitosas.
- Catálogo por capacidades y cierre directo de planes comprobados, conservando confirmaciones, grounding y sandbox.
 — 2026-10-31

### Added
- Agente general opt-in: interpretación por significado, contratos reales,
  revisión de autorización/cobertura, recuperación y diálogo separado del objetivo.
- Bóveda editable en Obsidian conectada a SQLite: recuperación relevante,
  procedimientos verificados, conflictos, caducidad, sincronización y olvido.

### Fixed
- Verificación posterior de volumen/brillo, estado musical pausado y espacios
  especiales; los conflictos de memoria tampoco se presentan como hechos en rutas clásicas.
- Conversación operativa: planes por pasos para proyectos, foco, YouTube y Spotify;
  referencias explícitas y resultados comprobados por turno. Se reconocen Code OSS
  y destinos numéricos vacíos; no se certifican búsquedas ni reproducción sin evidencia.
- Workspaces: órdenes con «work space», «World space» y prefijos de cortesía se
  ejecutan y comprueban contra Hyprland. Un efecto anterior no acredita un turno
  nuevo; las solicitudes sin comprobación se comunican como tales. Se reconoce la
  ausencia de visión y las aplicaciones se consultan por ventanas reales.
- Aislamiento por prueba de memoria, tareas y logs; cuarentena respaldada de
  episodios sintéticos inequívocos y exclusión de respuestas fallidas del contexto.
- Preparación de scripts: la prueba satisfactoria produce una propuesta concreta sin
  depender de otra inferencia; cancelaciones del router compatible impiden efectos tardíos.
- El agente compuesto rechaza aperturas no solicitadas durante una búsqueda y copia.
- Investigación Gemini: espera completa, URLs visibles y fechas obligatorias; respuestas
  incompletas no se presentan como verificadas. Integración activada tras aceptación.

### Added
- **Presencia animada nativa:** núcleo orgánico con membrana, filamentos y partículas
  mediante shader de Quickshell. Widget arriba/derecha, sin foco, con estado real,
  energía PCM de Piper/ElevenLabs/espeak, pausa y botón Detener ligado al turno.
  Socket privado, reconexión, movimiento reducido y servicio independiente opt-in.
- Voz progresiva de Gemini: eventos del CLI gemdev, navegador persistente,
  frases provisionales deduplicadas, validación final de fuentes/fechas y cola
  única de audio con cancelación local/móvil. Telemetría hasta primer PCM.
- Conversación natural local con preguntas contextuales, continuidad de opciones
  y ventana configurable para responder sin repetir «Limits».
- **Respaldos GLM/Groq opcionales:** credenciales separadas; GLM Flash para
  desarrollo y GPT-OSS 120B de Groq como último respaldo de los especialistas.
  OpenCode conserva prioridad. Groq usa JSON sin streaming, límite de salida
  propio y una repetición acotada por `Retry-After` o formato rechazado.
  La aplicación verificada de scripts se comunica sin otra llamada al modelo.
- **Nemotron Super y Bolt:** claves independientes y cadena de análisis
  Big Pickle → Super → Bolt → Groq, conservando prioridad fija por rol.
- **Asistente por objetivos (experimental, opt-in):** coordinador LangGraph con
  estado privado por sesión, selección de Qwen/NVIDIA/gemdev, herramientas
  verificadas y continuidad entre turnos. Scripts probados con bwrap sobre copias
  y aplicación vinculada al plan aprobado. Cancelación de consultas, procesos y
  turnos en cola; versión hablada y artefacto completo separados. Activación
  mediante `AGENT_ENABLED`; documentación en `docs/asistente-por-objetivos.md`.
  Respaldos independientes: OpenCode DeepSeek → NVIDIA DeepSeek y
  OpenCode Big Pickle → NVIDIA Nemotron, con prioridad fija, enfriamiento y
  presupuesto compartido por intento. El lane compuesto conserva OpenCode
  DeepSeek primero y NVIDIA DeepSeek como respaldo. La autenticación de gemdev y la
  aceptación externa pendiente se detallan en el informe de validación.
- **Grounding del router (P1):** `modules/grounding.py` verifica cada intent
  contra el catálogo real (`action_map`), el dominio de la frase y los enums de
  parámetros (con alias: `free_space`→`disk`). Si no puede anclarlo, devuelve
  `grounded=False` y `CommandExecutor` **no ejecuta**: responde con honestidad en
  vez de inventarse un «hecho». Cobertura: `tests/test_grounding.py`,
  `tests/test_llm_grounding.py`, `tests/test_executor_guard.py`.
- **Rutas deterministas de apps y música:** `modules/app_router.py` resuelve
  «abre/cierra `<app>`» y «pon `<app>` en pantalla» contra `APP_MAP`;
  `modules/media_router.py` resuelve «pausa/siguiente/reanuda/para la música» y
  «pon `<artista>` en Spotify/YouTube». Sin modelo, en ~0 ms.
- **Seguimientos de archivos sin LLM:** «muéstramelo» → `reveal_last`, «ábrelo» →
  `open_last`, «abre el archivo ~/…» → `open_file`, «abre el segundo» →
  `open_last{index:2}` (`modules/file_router.py`).
- **Sonda de grounding:** `scripts/probe_grounding.py` reproduce las 8 frases que
  originaron P1 sin ejecutar handlers (0 acciones incorrectas, 0 silencios).

### Changed
- **Router 100 % local:** Groq sale de la ecuación. Eliminado de `modules/llm.py`,
  `config.py`, `main.py`, `.env` (claves comentadas) y del `.env.example`.
  Sin fallback cloud: la latencia y la privacidad mandan.
- **`OLLAMA_NUM_CTX=8192`:** con 2048 el prompt (~1900 tokens) se truncaba y el
  modelo perdía las instrucciones: 28 % de acierto. Con 8192, acierto del 88-94 %
  y p50 de 2,5 s; con las rutas deterministas y el prompt ajustado, **32/32
  (100 %)** y **p50 1,6 s**.
- **Router determinista:** temperatura 0 y `seed` fija (deja de ser creativo).
- El prompt gana reglas de desambiguación de archivos y `action: null` para
  charla; presupuesto renderizado 8049 B de 8400.
- `bin/measure-router` mide el pipeline real (rutas deterministas + grounding) y
  una acción bloqueada cuenta como fallo. Sin `--allow-cloud`.

### Fixed
- El executor devolvía «hecho» con acciones inexistentes (`media_play`,
  `translate`) o con `params` en charla («estoy cansado» → «Trayendo Spotify»).
  Ahora: acción desconocida → «no lo sé hacer todavía»; grounding fallido →
  «no estoy seguro de haber entendido».
- Silencio cuando el modelo devolvía `response` vacía: ahora hay frase de
  respaldo.
- `confirm`/`cancel` ya no se bloquean como acción desconocida (no viven en
  `action_map`, los resuelve `execute()`).

### Documented
- `docs/plan-p1-grounding.md` (resultados medidos), `docs/tasks/p1-1-grounding.md`,
  `AGENTS.md` (módulos, flujo y gotchas de contexto) y README/INICIO sin Groq.

## [Unreleased] — 2026-10-28

Base para que Limits deje de ser un ejecutor de comandos y empiece a comportarse
como asistente (plan: `docs/plan-p0-fundamentos.md`).

### Added
- **Memoria persistente (P0-3):** `modules/memory.py` guarda hechos («recuerda
  que X es Y»), notas libres y episodios en SQLite (`~/.limits/memory.db`, WAL +
  FTS5, permisos 600). El prompt recibe un bloque `{memory}` (≤ 600 B) y el
  historial se hidrata al arrancar, así que Limits recuerda entre reinicios.
- **Router de memoria (P0-3):** «recuerda que…», «olvida…», «¿qué sabes de
  mí?» y «¿cuál es mi X?» se resuelven sin LLM (`modules/memory_router.py`).
- **Privacidad de la memoria:** tokens con pinta de secreto (`gsk_`, `sk-`,
  `ghp_`, `Bearer`, hex largos) se guardan como `[redactado]`.
- **Barge-in (P0-4):** `modules/speech_controller.py` habla y escucha a la vez.
  Voz sostenida → el TTS se **pausa** (SIGSTOP), se transcribe lo dicho y:
  «para/cállate/stop/basta» corta sin ejecutar nada; un eco del altavoz se
  descarta y se **reanuda**; cualquier otra frase se encadena como siguiente
  turno (`pending_text`). El TTS deja de bloquear (`wait_with_stop`, poll 50 ms).
- **Corte desde el móvil:** mensaje `{"type":"stop"}` en el gateway, atendido
  sin esperar al turno en curso, con evento `stopped`. Verificado: respuesta de
  25 s cortada a los 0,64 s.
- **«Para» dictado al micrófono del móvil:** la app transcribe con el
  reconocedor de Android y envía **texto**, así que un comando de una sola
  palabra de `BARGEIN_KEYWORDS` («para», «basta», «cállate»…) corta igual que
  `stop`, sin pasar por el pipeline ni esperar al turno. «Para la música» sigue
  siendo un comando normal. Medido: corte en 0,51 s.
- **Reloj y fecha (P0-1):** `modules/clock.py` como fuente única de verdad
  temporal (tablas en español, `TIMEZONE` opcional, `now` inyectable en tests) y
  `get_time(detail)` en `commands/system.py` con su entrada en `action_map`.
- **Rutas deterministas de un solo dato (P0-1):** `modules/quick_routes.py`
  responde «¿qué hora es?» y «¿qué día es hoy?» sin LLM, en ~0 ms, y no
  secuestra preguntas sobre horarios ajenos («¿a qué hora abre el banco?»).
- **Arranque automático (P0-2):** la unidad de systemd reintenta sin límite
  (`Restart=always`, `StartLimitIntervalSec=0`), arranca tras `pipewire`/
  `wireplumber` y sobrevive a reinicios sin sesión abierta (`enable-linger`).
- **Salud del asistente (P0-2):** `bin/limits-health` comprueba servicio,
  puerto, handshake autenticado del móvil y micrófono; sale 1 si algo crítico
  falla.

### Changed
- El TTS ya no bloquea el turno: `speak()` devuelve `ok|interrupted` y se puede
  cortar desde el móvil o por voz sin matar el proceso a lo bruto.
- El system prompt se renderiza **por turno**: `{now}` trae la hora real aunque
  el servicio lleve días vivo (antes cualquier fecha se habría congelado al
  arrancar).
- `setup-service.sh` es idempotente: regenera la unidad, recarga systemd,
  habilita el autostart y activa linger, todo en una pasada.

### Fixed
- `limits.service` aparecía `disabled` sin que `limits-service` lo hiciera;
  `stop` ahora está documentado como «parar, no desactivar» (`INICIO.md`).
- El log del turno imprimía `confidence=0.00` cuando el modelo omitía el campo
  mientras el executor ejecutaba igualmente; ahora `LLMEngine.process` normaliza
  el valor (0.9) y log y ejecutor coinciden.
- El executor devolvía respuestas con espacio inicial (`" Son las 16:55."`)
  cuando el handler no tenía `response` por defecto.

## [1.0.0-prealpha] — 2026-08-25

Primera versión etiquetada. Estado: **unstable**.

### Added
- Control multimedia avanzado (`commands/media.py`): reproducción directa en Spotify
  (URI nativa), YouTube vía `mpv` + `yt-dlp` con modo solo-audio, letras de la canción
  actual vía lyrics.ovh y consulta de la pista en reproducción (`playerctl`).
- Foco de ventanas Hyprland por clase real (`focus_window` + `WINDOW_CLASS_MAP`),
  verificando existencia via `hyprctl clients -j` y abriendo la app si no existe.
- Intents dedicados `confirm` / `cancel` para el flujo de acciones peligrosas,
  enseñados en el system prompt con regla anti-ambigüedad.
- Documentación completa: README renovado, `AGENTS.md` (guía de trabajo),
  `CHANGELOG.md`, `LICENSE` (MIT) y plantilla `.env.example`.
- Versionado centralizado en `version.py` mostrado en el banner.

### Fixed
- `open_project` en el `action_map` era una lambda que referenciaba una variable
  inexistente (`NameError` garantizado al invocarse); ahora es binding directo.
- El volumen relativo ignoraba valores negativos (el clamp 0–100 se aplicaba antes
  de saber el modo): "baja el volumen 10" no bajaba nada.
- La confirmación de acciones peligrosas se infería de substrings de la respuesta
  libre del LLM (cualquier frase con "sí"/"si" confirmaba); ahora solo deciden los
  intents dedicados, y un comando no relacionado cancela lo pendiente y se ejecuta.
- Allowlist de terminal: eliminados `curl` y `cat` (lectura/exfiltración de archivos
  privados por voz) y el match exigía límite de palabra (`catalog`, `git statusx`
  colaban antes).
- `close_app` mataba procesos por substring del nombre (cerrar "code" podía matar
  procesos tipo "qrcode-gen"); ahora match exacto/prefijo con separador más aliases
  (`vscode→code`, `terminal→ghostty`).
- Proceso piper sin reap tras `aplay` (zombies potenciales); ahora se espera con
  timeout y kill, y se tolera `BrokenPipeError`.
- Respuestas malformadas del LLM (`params` no-dict, `confidence` no numérico, JSON
  no-objeto) podían tumbar el bucle principal; ahora se coaccionan tipos y el JSON
  no-objeto dispara fallback al otro motor.
- Privacidad: lo dictado se registra a nivel DEBUG; en INFO solo metadatos del turno.
- Identidad unificada a "Limits" (README, INICIO, initial_prompt de Whisper que aún
  decía "Luna", referencia a script inexistente en tts.py).
- Docstring de `llm.py` documentaba prioridad inversa a la real (Groq es prioritario).

### Changed
- `requirements.txt` pineado a versiones exactas reproducibles.
- Dependencias de sistema documentadas completas (añadidos `mpv`, `yt-dlp`).
- README e INICIO alineados con la voz por defecto real (`davefx`).

### Security
- Endurecimiento general descrito en Fixed (allowlist, confirmaciones, tipos).

## [Unreleased]

### Added
- Emparejamiento del móvil **por QR**: el gateway imprime un QR con
  `limits://pair?h=IP&p=PORT&t=TOKEN` (`GATEWAY_SHOW_QR`, requiere `qrencode`) y
  la app Android lo escanea (⚙ → «Escanear QR del PC») o lo abre con la cámara
  del móvil (deep link). Nuevo `./bin/limits-qr [--rotate]` para reimprimir o
  revocar el token sin arrancar Limits. Fin del tecleo del token de 64 hex.
- `regenerate_token()` en `modules/gateway.py`; `load_or_create_token` re-aplica
  `chmod 600` si el archivo ya existía con permisos laxos.
- Plan 4: prompt slim (~5.9KB), corpus ≥25, `measure-router --min-accuracy 0.90`
  (fuerza Ollama local). Checklist en AGENTS.md. Docs:
  `docs/plan-prompt-corpus-local.md`.
- Plan 3 Gemini research: logging del puente, fail-loud si `NOT_SIGNED_IN`/
  respuesta hueca (&lt; `GEMINI_MIN_RESEARCH_CHARS` o opener Jarvis vacío),
  RESEARCH_MARK más estricto. Docs: `docs/plan-gemini-research-calidad.md`.
- Plan 2: Agent `desktop_task` vía OpenCode (`deepseek-v4.1-flash-free`) con
  fallback Ollama 3b, path guard y sin Groq/Big Pickle. Docs:
  `docs/plan-desktop-task-calidad.md`.
- Plan 1 archivos: memoria `last_matches` + `open_last`/`reveal_last` (“muéstramelo”,
  “ábrelo”, “el segundo”); foco Hyprland tras abrir (`movetoworkspacesilent` +
  `focuswindow`); `FILE_SEARCH_ROOT` / excludes (evita venvs). Docs:
  `docs/plan-focus-y-muestramelo.md`.
- Órdenes de archivos atómicas: `search_and_open`, `reveal_file`, `copy_file`,
  `move_file`, `rename_file`; `search_file` ahora habla rutas. Move/rename en
  `DANGEROUS_ACTIONS`. Few-shots locales en el system prompt (anti-confusión
  con `web_search`).
- Lane compuesto `desktop_task` (`modules/desktop_agent.py`): loop de tools
  tipadas + Ollama/Qwen sin aflojar el router global. Docs:
  `docs/plan-desktop-task.md`, auditoría `docs/catalogo-ordenes-audit.md`.
  Tipar/redactar en apps aplazado: `docs/track-redactar-apps.md`.
- Corpus `tests/corpus_ordenes.json` + `./bin/measure-router` (precisión/latencia).
- Voz dual: Piper para respuestas cortas del sistema y ElevenLabs (API gratuita)
  para respuestas largas donde importa la entonación — letras, resúmenes web y el
  futuro cerebro conversacional. Incluye router por longitud/origen
  (`VoiceRouter`), tope por turno, cache de audio local, limpieza markdown→hablado
  (`modules/voice_utils.py`) y fallback automático a Piper. Opt-in via `.env`;
  diseño y contrato en `docs/plan-elevenlabs-tts.md`.
- Primera suite de tests automatizada (`tests/`): 23 casos de la capa de voz con
  HTTP/audio mockeados.
- Gateway móvil (F1): WebSocket embebido (`modules/gateway.py`, opt-in
  `GATEWAY_ENABLED`) que recibe texto de un cliente Android y lo alimenta al
  pipeline compartido — mismo LLM router, executor y voz que la local. Token de
  pairing autogenerado (chmod 600), protocolo JSON versionado, zeroconf para
  descubrimiento y lock de turno global (`TurnGate` en `main.make_pipeline`)
  que serializa voz local vs remota sin intercalar salidas.
- Casting a TV (F2): `commands/tv.py` con `tv_cast` (lo que suena ahora vía
  playerctl, búsqueda YouTube vía yt-dlp o URL directa), `tv_control`
  (play/pause/stop/volumen) y `list_tvs`. Usables por voz en el PC Y por el
  gateway. Archivos locales servidos por URLs firmadas con expiración del
  endpoint `/media/`.
- Tests del gateway/pipeline compartido (16) y de TV (13): servidor uvicorn real
  en puerto efímero con clientes websocket; total 52 casos.
- App Android esqueleto (F3): Kotlin + Jetpack Compose, una sola pantalla HUD
  (orbe animado, historial monoespaciado), descubrimiento mDNS del gateway,
  token de pairing manual, reconocimiento de voz nativo y reconexión automática.
  Compila sin Android Studio (SDK cmdline-tools + Gradle); instrucciones en
  `clients/android/README.md`.

- Comandos globales de shell: `limits` (lanzador con guard anti-conflicto contra
  el servicio de fondo y flag `--takeover`) y `limits-service` (atajos systemd).
  El gateway ahora degrada con gracia si el puerto 8765 está ocupado.
- Fix de voz: `/usr/bin/piper` en Arch es el gestor de ratones, no el TTS —
  resolución ordenada del binario real (venv primero); piper-tts pineado.
- Fix de rendimiento: modelo Groq retirado (404 silencioso) causaba fallback a
  Ollama local en CPU en cada turno (~20s). Ahora `GROQ_MODEL` configurable;
  benchmarked qwen3.6-27b a ~1s.
- **Mapa del equipo en el system prompt** (`modules/machine_map.py`): rutas
  reales de `~` y de las carpetas de proyectos (máx. 700 B, con las carpetas
  importantes protegidas del recorte). El prompt renderizado queda en ~7 KB y
  su test mide el texto ya sustituido, no el archivo en crudo.
- `list_directory` ya no se corta en 5+5 entradas: 8 carpetas + 6 archivos, con
  «y N más», ignora dotfiles y explica qué carpeta no encontró.

### Fixed
- **App Android no conectaba aunque ambos estuvieran activos.** Cuatro causas
  reales: (a) el cliente no intentaba nada con el token vacío; (b) el server
  cerraba *antes* del upgrade → HTTP 403 opaco en vez de `4401`; (c) una IP
  manual sin puerto se ignoraba en silencio y caía a mDNS; (d) `WsClient` moría
  para siempre si el loop de reconexión terminaba (`loopJob != null`). Ahora el
  rechazo llega como `4401` con mensaje accionable, el puerto vacío usa 8765, el
  botón grande pasa a «Escanear QR» cuando no hay token, y el loop se relanza.
- **«Investígame» caía a Google en vez de investigar con Gemini.** Dos causas:
  (a) el router comparaba palabras clave sin normalizar acentos, así que
  «investígame», «búscame información» o «averigua» no coincidían y el LLM
  elegía `web_search`; ahora normaliza (NFD, sin diacríticos) y usa raíces
  (`investig`, `averigu`, `indag`, `googlea`…), con tests de falsos positivos
  («información del sistema», «abre google»); (b) **bug en gemdev**:
  `PLACEHOLDERS` no incluía «Buscando en la Web», así que la investigación se
  daba por terminada a los ~8 s con solo esa frase. Añadidos los estados de
  búsqueda (`buscando/searching/consultando`) → ahora espera la respuesta real
  (verificado E2E: 773–861 chars con fuentes en 13–20 s).
- **«Muéstrame Spotify en pantalla» no hacía nada (o cambiaba de canción).**
  Faltaba el mapeo en el prompt: el router mandaba «pon/muéstrame/trae X en
  pantalla» a `media_control` — incluso `action:"next"`. Añadido el few-shot de
  `focus_window` y la regla 10 de desambiguación (pantalla/al frente →
  `focus_window`; play/pausa/siguiente → `media_control`), con dieta del prompt
  para no pasar de 6 KB. 4 frases nuevas en `tests/corpus_ordenes.json`.
  Verificado E2E por el gateway contra una ventana en `special:music`.
- **«Reanuda Spotify» respondía pero no sonaba nada.** Con varios reproductores
  MPRIS abiertos (Spotify + Firefox + integración del navegador), `playerctl` a
  secas controlaba la *primera* entrada — una pestaña de WhatsApp Web. Además
  `media_control` no miraba el código de salida, así que la respuesta del LLM
  («reanudando») se decía igual. Ahora `media_control` acepta `player` opcional,
  elige el reproductor correcto (`pick_player`: el pedido → el que suena →
  Spotify), reporta el fallo real y el prompt enseña `{action, player}`.
  Tests: `tests/test_media_control.py` (9 casos, incluido el bug original).
- **La app no mostraba el escaneo QR** si ya había un token guardado: estaba
  solo en ⚙. Ahora hay un botón «Escanear QR» fijo en la cabecera y el parser
  de `limits://pair` tolera variantes; si falla, la app muestra lo que leyó.
- **Respuesta instantánea y orbe que habla (F5).** El gateway llamaba al
  pipeline con la voz activada y no respondía hasta terminar de hablar: en
  investigaciones de 20-60 s la app parecía colgada. Ahora responde primero,
  reproduce después vía `speak_fn` (`tts.speak`) y emite
  `speaking_started/finished`; el orbe se queda encendido y el estado dice
  «Hablando…». Un fallo de TTS ya no rompe el turno.
- **QR de emparejamiento**: `limits-qr --png [--open]` genera un PNG grande
  (la terminal con medio bloque fallaba al escanear en pantallas pequeñas).
- **Descarga del APK por LAN**: `scripts/share_apk.py` regenera la página cuando
  cambia el APK (tamaño/hash correctos sin reiniciar el servidor).
- **«lista los proyectos de la carpeta work» no encontraba nada.** Dos bugs
  deterministas: las rutas relativas se resolvían contra el cwd del servicio
  (no contra `$HOME`) y no había tolerancia a mayúsculas/acentos. Ahora
  `_expand` resuelve contra `$HOME` y el nuevo `_resolve_existing` recorre la
  ruta componente a componente (`work` → `~/Work`, `descárgas` →
  `~/Descargas`); si no existe, la respuesta sugiere la carpeta parecida en vez
  de inventarla. Aplica a listar, abrir, revelar, copiar, mover y renombrar.
- **El LLM inventaba rutas** (`/Proyectos`, `work`) aunque el prompt lleve el
  mapa del equipo. Nuevo router determinista (`modules/file_router.py`): «lista
  … carpeta X», «qué hay en X», «muéstrame la carpeta X» y «qué proyectos
  tengo» se resuelven sin modelo, validando contra el disco (0.00 s).
- **`open_project` solo aceptaba rutas**: ahora entiende el nombre del proyecto
  («abre el proyecto limits») y lo busca en `~/Proyectos`, `~/Work`,
  `~/Projects`, `~/Repos` y compañía, tolerando caja y acentos.

### Planned
- App Android del control remoto (F3–F6): Kotlin/Compose, wake word, orbe HUD.
  El lado servidor ya está listo y esperando.

- Integración del cerebro conversacional Gemini Web — EN PAUSA mientras el CLI
  `gemdev` (hermes-web-clis) estabiliza. Diseño completo congelado en
  `docs/integracion-gemini.md`; su salida usará ElevenLabs cuando llegue.

- Ampliar la suite de tests al resto del sistema (executor, llm) y CI.
- Activación del listener threaded (`modules/listener.py`) o wake word dedicada
  (openWakeWord/Porcupine).
