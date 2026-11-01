# Plan de implementación: voz natural con ElevenLabs

> Estado: **IMPLEMENTADO (F1–F3)** — motor, router y utilidades en producción
> con 23 tests mockeados en verde. Pendiente: smoke test con audio real, que
> requiere regenerar la API key actual con el permiso `text_to_speech` activado
> (la key inicial se creó sin él; solo lista voces).
> Alcance: sustituir/mejorar la voz de respuesta de Limits usando ElevenLabs,
> **sin depender del CLI de Gemini** (esa integración queda EN PAUSA mientras
> `hermes-web-clis/gemdev` estabiliza — ver `docs/integracion-gemini.md`).
> Cuando el puente Gemini llegue, su salida usará esta misma capa de voz
> automáticamente (`mode=gemini`, reservado desde ya en el diseño).

---

## 1. Objetivo y decisiones de diseño

Hoy Limits habla con Piper (local, rápido, calidad "robot amable") o espeak-ng
(fallback feo). ElevenLabs da voces naturales en español con latencia aceptable
(~0.3–1 s por frase corta vía red). La idea: **voz dual por economía de cuota** —
la API key es la gratuita (~10k caracteres/mes), así que cada carácter cuenta:

- **Piper para respuestas cortas operativas** ("Volumen al 70 %", "Abriendo
  Firefox", confirmaciones): son la mayoría de los turnos, no valen gastar cuota y
  ahí la velocidad local gana.
- **ElevenLabs para respuestas largas o desarrolladas** donde la entonación importa:
  letras de canciones, resumenes web extensos y, sobre todo, las futuras respuestas
  conversacionales/de investigación del puente Gemini.

### Decisiones clave

1. **Motor nuevo junto al existente, no reemplazo.** Piper sigue siendo default y
   fallback permanente: si ElevenLabs falla (red, cuota, key inválida), la respuesta
   se habla igual con Piper. El asistente jamás se queda mudo.
2. **Enrutado por origen Y longitud** (`ELEVENLABS_MODE`):
   - `auto` (propuesto tras validar) → decide por umbral de longitud
     (`ELEVENLABS_MIN_CHARS`, default 200): lo corto del día a día va a Piper, lo
     largo/desarrollado a ElevenLabs. Funciona HOY sin Gemini: letras y resúmenes
     web largos ya suenan naturales.
   - `gemini` → solo la salida etiquetada del futuro cerebro conversacional va a
     ElevenLabs (independiente de longitud); hoy equivale a `off`.
   - `off` (default seguro si falta API key) → comportamiento actual.
   - No existe modo "todo por ElevenLabs": derrocharía la cuota gratis en "Hecho."
3. **Tope por turno** (`ELEVENLABS_MAX_TURN_CHARS`, default 1200): una respuesta
   gigante nunca devora la cuota mensual; el resto se sigue hablando con Piper.
4. **Cero dependencias Python nuevas**: `requests` ya está en `requirements.txt`;
   reproducción con `mpv` (dependencia de sistema ya documentada para multimedia),
   fallback `ffplay`.
5. **Cache agresiva de frases** → ahorra cuota: frases repetidas (saludos, errores,
   letras consultadas dos veces...) no gastan créditos dos veces.
6. **Privacidad honesta**: con ElevenLabs activo, el TEXTO de esas respuestas largas
   sale a sus servidores (no lo dictado: eso sigue en Groq/Ollama/Whisper). Opt-in
   claro en README/doc; `off` sigue siendo el default seguro.

### Por qué esto NO depende de Gemini

El TTS solo recibe texto y lo habla. Construir el motor, el router de voz, la cache,
el manejo de errores y las utilidades de limpieza de texto es útil hoy mismo (toda la
voz de Limits mejora) y deja el terreno listo: cuando el puente Gemini se implemente,
su salida larga y conversacional sonará natural sin tocar nada del TTS.

---

## 2. Contrato técnico de ElevenLabs (verificado contra su API pública)

```http
POST https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}?output_format=mp3_44100_128
Headers:
    xi-api-key: <ELEVENLABS_API_KEY>
    Content-Type: application/json
Body:
{
  "text": "<texto>",
  "model_id": "eleven_turbo_v2_5",
  "voice_settings": {
    "stability": 0.5,
    "similarity_boost": 0.75,
    "style": 0.0,
    "use_speaker_boost": true
  }
}
Response 200: audio/mpeg (binario, streaming-friendly)
```

- Modelos recomendados para español: `eleven_turbo_v2_5` (balance velocidad/calidad,
  default propuesto) y `eleven_multilingual_v2` (máxima calidad, más lento).
  `eleven_flash_v2_5` si algún día se busca mínima latencia.
- Límite por petición: 5.000 caracteres (nosotros enviaremos frases muy cortas;
  guard defensivo igualmente).
- Cuota free: ~10.000 créditos/mes (~10 min de audio). Con respuestas de ≤100 palabras
  y cache, rinde para cientos de turnos.
- Endpoints auxiliares útiles: `GET /v1/voices` (listar voces),
  `GET /v1/user/subscription` (cuota restante → aviso hablado al 80%, fase 4).

Errores HTTP relevantes: 401 (key inválida), 404 (voice_id mal), 422 (texto vacío/
inválido), 429 (rate limit/cuota agotada). Todos mapean a fallback Piper + log.

---

## 3. Arquitectura propuesta

```
run_pipeline(respuesta)
      │
      ▼
┌───────────────────────┐  1) ¿mode/off?  2) ¿src="gemini"?  3) ¿len ≥ MIN_CHARS?
│  VoiceRouter (nuevo)  │───────────────────────────┬─────────────────────┐
│  .speak(text, src)    │                           │                     │
└───────────────────────┘              corto / off / fallo      largo (o gemini)
                                                       ▼                     ▼
                                    ┌────────────────────┐   ┌──────────────────────┐
                                    │ TTSEngine (actual) │   │ ElevenLabsEngine     │
                                    │ piper → espeak     │◄──│ cache → POST → mpv/  │
                                    │ (instantáneo)      │   │ mpv/ffplay           │
                                    └────────────────────┘   └──────────────────────┘
```

### Matriz de enrutado

| Tipo de respuesta | Ejemplo | Motor |
|---|---|---|
| Confirmación operativa corta | "Volumen al 70 %.", "Abriendo Spotify.", "Hecho." | **Piper** |
| Respuesta media del sistema con datos | "Encontré 5 resultados para config.py." | Piper (< umbral) |
| Respuesta larga/desarrollada | Letras de una canción, resumen web ≥ umbral | **ElevenLabs** |
| Futuro: salida del puente Gemini | charla/investigación conversacional | **ElevenLabs** (siempre, por tag `src`) |
| Cualquier respuesta > MAX_TURN_CHARS | texto enorme | ElevenLabs hasta el tope + resto en Piper |
| Fallo de red / cuota agotada / key inválida | — | **Piper** (fallback automático, sin crash) |

- `VoiceRouter` implementa exactamente la interfaz que `main.py` ya usa
  (`router.speak(text)`), por lo que `run_pipeline` no cambia de firma: solo cambia
  qué objeto se construye en `main()`.
- Etiqueta de origen (`src="system"` hoy; `"gemini"` reservado) permite forzar el
  canal natural para el futuro cerebro conversacional sin tocar el router.

---

## 4. Configuración nueva (.env → config.py)

```bash
# ─── VOZ NATURAL (ElevenLabs — solo respuestas largas, cuota free) ──────
ELEVENLABS_ENABLED=false            # master switch (true requiere API key)
ELEVENLABS_API_KEY=                 # nunca commitear (ya cubierto por .gitignore)
ELEVENLABS_MODE=auto                # auto | gemini | off   (auto = por longitud)
ELEVENLABS_MIN_CHARS=200            # umbral: >= esto va a ElevenLabs en modo auto
ELEVENLABS_MAX_TURN_CHARS=1200      # tope por turno (protege la cuota mensual)
ELEVENLABS_VOICE_ID=                # p.ej. voz masculina ES; ver F0
ELEVENLABS_MODEL=eleven_turbo_v2_5
ELEVENLABS_STABILITY=0.5
ELEVENLABS_SIMILARITY=0.75
ELEVENLABS_CACHE=true               # cache de audio por frase (ahorra cuota)
```

Reglas: `config.py` único lector; defaults seguros (`enabled=false`); validación
temprana: enabled sin key ⇒ warning en arranque y motor desactivado (no crash).
`.env.example` gana el bloque correspondiente comentado como opt-in.

---

## 5. Plan por fases

### F0 — Prerrequisitos manuales (una vez, ~15 min)
- [ ] Crear cuenta en elevenlabs.io (plan Starter recomendado si convence: más cuota).
- [ ] Elegir voz: probar en la web voces hispanas (p. ej. catálogo es_ES/es_MX);
      copiar su `voice_id` (o listarlas con `GET /v1/voices`).
- [ ] Smoke test con curl del endpoint (§2) para validar key/voz/model antes de tocar
      código.
- [ ] Decidir `MODE` inicial (`auto` recomendado: letras/resúmenes largos ya suenan
      naturales desde el día uno sin gastar cuota en confirmaciones).

### F1 — Motor ElevenLabs (`modules/tts_elevenlabs.py`, nuevo)
- [ ] Clase `ElevenLabsEngine(enabled, api_key, voice_id, model, stability,
      similarity, cache_dir, speed_fallback)` con método `speak(text)` compatible.
- [ ] Descarga: `requests.post(..., stream=True, timeout=(5, 30))` → archivo temporal
      `.mp3` en `$XDG_CACHE_HOME/limits-tts/`; nunca `shell=True`.
- [ ] Reproducción: `subprocess.run(["mpv", "--no-video", "--terminal=no",
      "--really-quiet", tmp])`; fallback `ffplay -nodisp -autoexit`; limpieza del
      temporal en `finally`.
- [ ] Cache por contenido: clave `sha256(model|voice|settings|texto)` → hit = skip
      descarga (piper-level latency en repetidos). Evicción LRU simple si >50 MB.
- [ ] Guardas: vacío ⇒ no-op; texto > `ELEVENLABS_MAX_TURN_CHARS` ⇒ hablar por API
      la primera porción (corte en límite de frase) y el resto directamente con
      Piper, nunca cortado a mitad de frase ni devorando la cuota.
- [ ] Errores → excepción propia `TTSUnavailable`; NUNCA silencio total.
- [ ] Log DEBUG de duración/bytes; INFO solo éxitos; la key JAMÁS se loguea.

### F2 — Router de voz + cableado
- [ ] `modules/tts.py` o módulo nuevo `voice_router.py`: clase `VoiceRouter`
      con `.speak(text, source="system")`; decide motor según matriz §3:
      mode/disponibilidad → tag de origen → umbral de longitud;
      try ElevenLabs → except → piper/espeak actual.
- [ ] `main.py`: construir `VoiceRouter` en lugar de `TTSEngine` directo (misma
      interfaz; `--text` y modo voz intactos).
- [ ] `config.py`: variables §4 + coacciones de tipos.
- [ ] `.env.example`: bloque nuevo marcado opt-in.
- [ ] README: sección de configuración + nota de privacidad.

### F3 — Calidad de voz compartida (terreno común con el futuro Gemini)
- [ ] `modules/voice_utils.py`: limpieza markdown→hablado (fences, `**`, cabeceras,
      URLs→frases), truncado inteligente por límite de frase. Lo usará TODO el TTS y
      mañana el puente Gemini tal cual.
- [ ] Helper `speak_then_block(router, ack_text, slow_fn)` para acuses de recibo
      previos a operaciones lentas (patrón que el puente Gemini reutilizará).
- [ ] Tests unitarios: cache hit/miss, truncado, mapeo de errores HTTP (mockeando
      `requests`), fallback a piper ante fallo ElevenLabs, router según mode.
      Mockear también subprocess de reproducción.

### F4 — Extras (opcional, tras validar en uso real)
- [ ] Aviso hablado al 80% de cuota (consulta `/v1/user/subscription` 1×/día).
- [ ] Streaming chunked real (reproducir mientras llega el audio) para bajar latencia
      percibida en respuestas largas.
- [ ] Comando de voz "cambia a tu voz normal/temporal" (toggle runtime piper↔11labs).

---

## 6. Archivos tocados (resumen)

| Archivo | Cambio |
|---|---|
| `modules/tts_elevenlabs.py` | **NUEVO** — motor ElevenLabs |
| `modules/voice_utils.py` | **NUEVO** — limpieza/truncado de texto para voz |
| `main.py` | construir `VoiceRouter` (≈6 líneas) |
| `config.py` | 8 variables nuevas |
| `requirements.txt` | **SIN CAMBIOS** (requests ya está) |
| `.env.example`, `README.md`, `CHANGELOG.md` | documentación |

Sin cambios en: executor, llm, stt, prompts, comandos. Riesgo de regresión mínimo
y confinado a la capa de salida de audio.

## 7. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| Cuota free agotada a mitad de uso | Fallback automático a Piper + aviso una vez (no cada turno) |
| Latencia de red empeora la UX | Cache; modelo turbo; solo las respuestas largas pasan por red (lo corto es Piper local instantáneo); F4 streaming; piper siempre disponible |
| Key filtrada por accidente | Solo `.env` (gitignored); jamás en logs; ejemplo usa placeholder |
| Proveedor caído / cambio de API | Motor aislado tras interfaz; tests con mocks detectan contrato roto |
| Privacidad (texto sale a 11labs) | Opt-in explícito, default `off`; doc clara de QUÉ sale y qué no |

## 8. Criterio de done (F1–F3)

- `py_compile` completo + suite de tests nueva en verde.
- Smoke test manual en modo `auto`: una confirmación corta ("abre firefox" →
  "Abriendo Firefox.") suena con Piper; una respuesta larga (p. ej. `dime la letra`
  de una canción) suena con ElevenLabs; desconectar red ⇒ todo sigue hablándose
  (Piper) sin crash.
- Con cache caliente, repetir la misma letra/resumen no genera segunda petición HTTP
  (verificable en log DEBUG).
