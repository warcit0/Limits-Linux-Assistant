# AGENTS.md — Contexto de Trabajo para Agentes y Desarrolladores

Guía técnica de referencia para trabajar en el código de **Limits** (asistente de voz
para Linux). Léela completa antes de modificar nada.

## 1. Qué es

Asistente de voz terminal-first para CachyOS + Hyprland (Wayland).
Pipeline por turno: **STT local → LLM dual → Executor con cortafuegos → TTS local**.

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

# Checklist pre-commit / pre-release (sin Groq en el router)
./limits-env/bin/python -m py_compile main.py config.py version.py \
    modules/*.py commands/*.py
./limits-env/bin/python -m unittest discover -s tests -v
./bin/measure-router --min-accuracy 0.90   # requiere Ollama; fuerza local

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
| `modules/llm.py` | Groq (prioritario) → Ollama (fallback). Historial de 6 mensajes. Devuelve dict validado o intent `unknown`. Renderiza `{now}` por turno |
| `modules/stt.py` | PyAudio + webrtcvad (corte: 900ms silencio / máx 10s) + faster-whisper int8 |
| `modules/tts.py` | piper-tts → pipe → aplay 22050Hz S16LE; fallback espeak-ng. `speak()` devuelve `ok|interrupted`; `pause_all`/`resume_all` (SIGSTOP/SIGCONT) |
| `modules/speech_controller.py` | Barge-in: VAD mientras habla, pausa/reanuda si es eco, palabras clave («para») y `pending_text` para encadenar |
| `modules/executor.py` | `action_map` action→handler, cortafuegos de tipos/params, flujo confirm/cancel con estado |
| `modules/clock.py` | Fuente única de verdad temporal: `now_line`/`time_line`/`date_line`/`weekday_line`/`parse_duration` (sin `locale`) |
| `modules/quick_routes.py` | Rutas deterministas de un dato (hora/fecha) **antes** del LLM; excluye horarios ajenos («a qué hora abre…») |
| `modules/memory.py` | Hechos/notas/episodios en SQLite (`~/.limits/memory.db`, WAL + FTS5, 600). Singleton `get_store()`; si falla, `enabled=False` y todo sigue |
| `modules/memory_router.py` | «recuerda que…», «olvida…», «qué sabes de mí», «cuál es mi X» sin LLM |
| `modules/file_router.py` | Ruta determinista de «lista/abre la carpeta X» antes del LLM |
| `modules/desktop_agent.py` | Lane `desktop_task`: OpenCode Flash agent + fallback Ollama 3b; path guard |
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
  → quick_routes (hora/fecha) · memory_router (recuerda/olvida) · file_router   # sin LLM
  → llm.process(text)            # dict {intent, action, params, response, confidence} o unknown
  → executor.execute(parsed)     # string para hablar
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
- Agent: OpenCode `OPENCODE_AGENT_MODEL` (default deepseek-v4.1-flash-free);
  fallback Ollama `DESKTOP_AGENT_MODEL` (3b). Router intents = `OLLAMA_MODEL` (1.5b).
- Sin Groq ni Big Pickle. Paths locales van al cloud si provider=opencode.
- Path guard: open/copy solo con rutas observadas en el turno.
- Docs: `docs/plan-desktop-task-calidad.md`. Tipar apps: `docs/plan-redactar-apps.md`.

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

- Groq es prioritario SI hay `GROQ_API_KEY`; Ollama solo actúa como fallback o motor
  único sin key. El chequeo de arranque `_check_ollama` es informativo, no bloqueante.
- La wake word se filtra sobre la transcripción completa; `WAKE_WORD=Limits` añade
  variaciones "límites/limites" automáticamente en `main.py`.
- `focus_window` consulta `hyprctl clients -j` antes de enfocar; si no existe la
  ventana, abre la app vía `APP_MAP`.
- `hyprctl`/`wpctl`/`playerctl` requieren sesión gráfica activa; bajo systemd user
  service el script ya exporta `WAYLAND_DISPLAY` y `XDG_RUNTIME_DIR`.
- Los modelos de Whisper se descargan on-demand de HF en el primer arranque.
- En este equipo el micro **no capta los altavoces** (RMS ambiente ~89, pico
  ~179): no hay autocorte hoy, pero con altavoces audibles el eco se detecta y
  se reanuda. Cada detección cuesta ~1,5 s de pausa: con altavoces, auriculares
  o `module-echo-cancel` de PipeWire.
- `qwen3.6-27b` (Groq) **omite `confidence`** con frecuencia: `LLMEngine.process`
  la normaliza a 0.9 (`DEFAULT_CONFIDENCE`) y el executor ejecuta si falta (no
  bloquear: rompía órdenes legítimas como «cuánta RAM tengo»). El grounding real
  (¿la acción responde a la pregunta?) es P1; mientras tanto puede elegir una
  action válida pero equivocada.
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
