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
./limits-env/bin/python main.py --text

# Verificar sintaxis de todos los módulos (equivalente a lint mínimo actual)
./limits-env/bin/python -m py_compile main.py config.py version.py \
    modules/*.py commands/*.py

# Probar el executor sin tocar el sistema (mockear handlers en action_map)
./limits-env/bin/python -c "
from modules.executor import CommandExecutor
e = CommandExecutor()
e.action_map['shutdown'] = lambda: 'mock'
print(e.execute({'action':'shutdown','params':{},'response':'x','confidence':0.99}))
"

# Tras cambiar código o .env, si el servicio está activo:
systemctl --user restart limits.service
```

No hay suite de tests ni CI todavía (pendiente, ver CHANGELOG). Antes de cada commit:
`py_compile` de todo + prueba manual en modo texto.

## 3. Estructura y responsabilidades

| Ruta | Responsabilidad única |
|---|---|
| `main.py` | Orquestador: argparse (`--text`, `--once`), SIGTERM graceful, wake word inline, loop |
| `config.py` | Único punto que lee `.env`. Añade aquí toda variable nueva |
| `version.py` | Metadatos de versión. Única fuente de verdad para versionar |
| `modules/llm.py` | Groq (prioritario) → Ollama (fallback). Historial de 6 mensajes. Devuelve dict validado o intent `unknown` |
| `modules/stt.py` | PyAudio + webrtcvad (corte: 900ms silencio / máx 10s) + faster-whisper int8 |
| `modules/tts.py` | piper-tts → pipe → aplay 22050Hz S16LE; fallback espeak-ng |
| `modules/executor.py` | `action_map` action→handler, cortafuegos de tipos/params, flujo confirm/cancel con estado |
| `modules/listener.py` | ⚠️ NO USADO — versión threaded futura del wake word |
| `commands/apps.py` | Abrir/cerrar apps (`APP_MAP`, `PROCESS_ALIASES`) |
| `commands/system.py` | Volumen/brillo/lock/info/shutdown/hyprland (`WINDOW_CLASS_MAP`) |
| `commands/web.py` | Búsquedas (raspa DDG Lite para resumen hablado) y URLs |
| `commands/dev.py` | Terminal con allowlist, git/docker status, abrir proyectos |
| `commands/files.py` | fd/find, xdg-open, listar directorios |
| `commands/media.py` | Spotify URI, YouTube mpv+yt-dlp, letras lyrics.ovh, canción actual |
| `commands/custom.py` | Plantilla vacía para comandos del usuario |
| `prompts/system_prompt.txt` | System prompt few-shot. `{username}` se sustituye desde env |
| `docs/` | Documentación de diseño de integraciones planificadas |
| `setup-service.sh` | Instala `~/.config/systemd/user/limits.service` |

## 4. Flujo de datos de un turno

```
main.run_pipeline(user_input)
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
```

## 5. Reglas críticas de seguridad (NO romper)

1. **Nunca `shell=True`** ni construir comandos con f-strings usando datos del LLM.
   Siempre listas de argumentos en `subprocess`.
2. **Allowlist en `dev.py`:** match exacto o con límite de palabra (`cmd == safe or
   cmd.startswith(safe + " ")`). No añadir `curl`, `cat`, `sudo`, `rm` ni anything
   que pueda leer archivos privados o hacer red arbitraria.
3. **Confirmaciones explícitas:** `shutdown`/`reboot` viven en
   `DANGEROUS_ACTIONS`. La decisión SOLA viene del intent `confirm`/`cancel`
   (enseñado en el system prompt). Jamás inferir de substrings ("sí", "ok") dentro
   de respuestas libres.
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

### Integración Gemini conversacional (EN PAUSA)
- **Decisión 2026-08-25:** pausada mientras el CLI `gemdev` de
  `~/Work/hermes-web-clis` estabiliza (repo en desarrollo activo). El diseño
  congelado vive en `docs/integracion-gemini.md`; NO implementarlo sin despausar.
- Regla dura cuando se retome: la salida de Gemini va SOLO a TTS/log, jamás al
  `action_map` ni al executor (bloquea prompt injection desde contenido web).
  Serán actions nuevas (`gemini_talk`/`gemini_research`) delegando en un
  `GeminiBridge` por subprocess.

### Control remoto desde Android (planeado → diseño listo)
- Diseño en `docs/plan-control-remoto-android.md`: gateway WebSocket embebido en
  Limits (hilo, mismo proceso) que alimenta `run_pipeline` tal cual; app Android
  en `clients/android/`; casting a TV como comandos nuevos (`commands/tv.py`)
  aprovechables también por voz local.
- Reglas duras cuando se implemente: el texto del móvil pasa por el MISMO router
  LLM + executor (cero superficie nueva); token de pairing obligatorio; lock
  global serializa turnos voz-local vs móvil (nunca intercalar salidas).

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
- Python objetivo: 3.11+ (el entorno usa 3.14). Sintaxis moderna permitida
  (`int | None`).

## 8. Release checklist

1. Actualizar `__version__`/`STATUS` en `version.py`.
2. Nueva entrada arriba en `CHANGELOG.md` (formato Keep a Changelog).
3. Badge de versión del README acorde.
4. `py_compile` completo + smoke test `--text` de los intents tocados.
5. Commit estilo conventional (español): `feat:`, `fix:`, `docs:`...
