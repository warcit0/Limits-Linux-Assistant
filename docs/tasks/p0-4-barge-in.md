# P0-4 · Barge-in (interrumpir al asistente)

**Estado:** implementado · Depende de: nada · Esfuerzo: 1 día
**Falta:** prueba con voz humana (el micro de este equipo no capta los altavoces).
**Habilita:** conversación natural. Sin esto, un asistente que se enrolla 20 s
te obliga a esperar: deja de ser una conversación y pasa a ser un mensaje de voz.

## Problema

```python
# modules/tts.py:100
aplay_proc.wait()          # bloquea el hilo del pipeline
```

El flujo es estrictamente secuencial: `escuchar → pensar → hablar → escuchar`.
Mientras habla **no hay micrófono**. No existe forma de decir «para», ni de
corregirle a mitad de frase.

En el gateway móvil pasa lo mismo: no hay mensaje de cancelación.

## Diseño

Cuatro piezas:

```text
pipeline ──► SpeechController.speak(text)
                 │
                 ├── hilo A: TTS (piper/ElevenLabs) ──┐
                 │                                     ├── stop_event
                 └── hilo B: VAD (webrtcvad) ──────────┘
                          voz sostenida > 350 ms
                                 │
                    stop_event.set() ──► aplay/piper terminate()  (< 50 ms)
                                 │
                                 ├── transcribir lo dicho
                                 ├── ¿es "para"/"cállate"? → ack y seguir
                                 ├── ¿es eco del TTS?      → descartar
                                 └── ¿es un comando?       → ejecutarlo
```

### Por qué VAD y no STT continuo durante la reproducción

- VAD (webrtcvad, ya es dependencia) cuesta ~1 % de CPU; Whisper en paralelo
  cuesta un núcleo y compite con el TTS.
- Solo transcribimos **después** de cortar, y únicamente el audio del usuario.

### El problema del eco

El micrófono oye los altavoces. Tres filtros acumulativos:

1. **Umbral temporal**: 350 ms de voz sostenida (`BARGEIN_MIN_MS`), no un golpe.
2. **Palabra clave o wake word**: si la transcripción contiene `para`, `cállate`,
   `stop` o la wake word, es interrupción segura.
3. **Similitud con lo hablado**: si la transcripción se parece > 0.75
   (`difflib.SequenceMatcher`) al texto que el TTS estaba diciendo, es eco →
   se descarta y no se ejecuta nada.

Si hay auriculares, el problema desaparece; sin ellos, los tres filtros bastan.

## Cambios por archivo

| Archivo | Cambio |
|---|---|
| `modules/tts.py` | `speak(text, stop_event=None)`: espera en bucle de 50 ms con `poll()`; al evento, `terminate()` de piper y aplay. Devuelve `"ok"`/`"interrupted"` |
| `modules/tts_elevenlabs.py` | Igual para `_play()` (mpv/aplay), respetando el `stop_event` |
| `modules/speech_controller.py` **(nuevo)** | Orquesta TTS en hilo + VAD en hilo + `stop_event`; expone `speak(text) -> str` y `stop()` |
| `modules/stt.py` | Separar `record_until_silence()` de `transcribe(audio)`; exponer `vad_wait(min_ms)` |
| `main.py` | Usa `SpeechController` en lugar de `tts.speak`; el bucle pasa a poder interrumpirse |
| `modules/gateway.py` | Mensaje `{"type":"stop"}` → `controller.stop()`; evento `{"type":"event","kind":"stopped"}` |
| `config.py` | `BARGEIN_ENABLED`, `BARGEIN_KEYWORDS`, `BARGEIN_MIN_MS` |
| `clients/android/…/WsClient.kt` | (opcional) botón «Para» que envía `stop` |
| `tests/test_bargein.py` **(nuevo)** | Corte < 500 ms con Popen falso, filtro de eco, palabras clave |

## Detalle técnico

```python
# modules/tts.py (esbozo)
while aplay_proc.poll() is None:
    if stop_event is not None and stop_event.is_set():
        _terminate(aplay_proc)
        _terminate(piper_proc)
        return "interrupted"
    time.sleep(0.05)
```

- `terminate()` y no `kill()`: deja que aplay cierre el dispositivo sin chasquido.
- Hay que cerrar también el `stdin` de piper, o queda zombi (ya se hace hoy).
- El `stop_event` es `threading.Event` compartido; se **limpia** al empezar cada
  turno (`clear()`), si no, todo turno posterior se cortaría al instante.

## Tareas

- [x] `TTSEngine.speak(text, stop_event=None)` no bloqueante + terminación limpia
- [x] Lo mismo en `ElevenLabsEngine._play()`
- [x] `modules/speech_controller.py` con hilos y `stop_event`
- [x] `stt.record_until_silence()` / `stt.transcribe()` reutilizados (el VAD del
      barge-in es propio: modo más sensible y ventana deslizante)
- [x] `main.py`: sustituir `tts.speak` por `speech_controller.speak` (+ encadenar
      `pending_text` cuando la interrupción es un comando)
- [x] Mensaje `stop` en el gateway + evento `stopped` (atendido sin esperar turno)
- [x] `config.py` + `.env.example` (`BARGEIN_*`)
- [x] Tests unitarios (Popen falso, eco, palabras clave, `clear()` entre turnos)
- [ ] **Prueba real:** respuesta larga, decir «para» a mitad
      — **pendiente de voz humana**: el micrófono de este equipo no capta los
      altavoces (RMS ambiente 89 vs pico 179), así que no se puede simular sin
      una persona hablando. El corte desde el móvil (`{"type":"stop"}`) sí está
      verificado E2E: fin en 0,64 s.
- [ ] **Prueba real:** 10 min hablando sin falsos cortes

## Criterios de aceptación

1. Mientras habla una respuesta de 20 s, decir «para» → silencio en **< 500 ms**.
2. El log muestra `tts interrupted after X.Xs` con `X < 0.5`.
3. 10 minutos de respuestas largas sin decir nada → **cero** interrupciones falsas.
4. Desde el móvil, `stop` corta la reproducción del PC.
5. Interrumpir no deja procesos `piper`/`aplay` huérfanos (`pgrep -a piper`).

## Riesgos

| Riesgo | Mitigación |
|---|---|
| Eco del altavoz dispara el corte | Tres filtros (tiempo, palabra clave, similitud) |
| `terminate()` deja el dispositivo de audio ocupado | Cerrar stdin de piper y esperar 100 ms antes del siguiente `speak` |
| El VAD consume CPU junto a Whisper | webrtcvad es barato; solo corre mientras hay TTS |
| El `stop_event` queda set y corta el turno siguiente | `clear()` al inicio de cada turno + test explícito |
| En el móvil, el audio del PC no se oye (no hay streaming) | Fuera de alcance: `stop` aquí cancela el TTS **del PC**; el audio remoto es F4 |

## No-objetivos

- Cancelar una investigación de Gemini a mitad (proceso externo): se puede añadir
  después matando el subproceso, pero no es requisito para conversar.
- Ducking (bajar volumen en vez de cortar) → mejora futura.
