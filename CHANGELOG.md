# Changelog

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/).
Versionado semántico simplificado; mientras dure el estado prealpha pueden haber
cambios rompientes en cualquier release.

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
- Suite de tests automatizada y CI.
- Activación del listener threaded (`modules/listener.py`) o wake word dedicada
  (openWakeWord/Porcupine).
