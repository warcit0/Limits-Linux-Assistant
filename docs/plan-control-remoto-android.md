# Plan: Control remoto por voz desde Android ("modo Jarvis en casa")

> Estado: **Diseño listo pendiente de aprobación e implementación**.
> Origen: adaptación del prompt "Asistente IA Personal Jarvis" (app Android +
> servidor PC) a la arquitectura existente de Limits.
> Principio rector: **no se rehace nada que Limits ya hace bien** — el teléfono es
> una puerta de entrada más al MISMO pipeline (como `--text` o `--once`), y cada
> capacidad nueva (casting a TV) nace como comando del executor, aprovechable por
> voz en el PC Y desde el móvil sin duplicar lógica.

---

## 1. Qué se adapta del prompt original (y qué no)

| El prompt original decía... | Adaptación a Limits | Por qué |
|---|---|---|
| Servidor FastAPI nuevo con router de intents propio | **Gateway WebSocket embebido en Limits** que alimenta `run_pipeline()` | Limits ya ES el backend: Groq/Ollama + Executor + cortafuegos. Un segundo router sería otra fuente de verdad |
| NLU con reglas + hook a LLM | **Nada que hacer**: ya existe el router LLM con system prompt versionado | Reimplementar intents en regex sería un paso atrás |
| STT en servidor (implícito) | STT **en el móvil** (SpeechRecognizer de Google) enviando texto | Gratis, rápido, offline-friendly; el texto entra al mismo pipeline |
| Wake word Porcupine en la app | Igual, con alternativa **openWakeWord** (sin cuenta Picovoice) | Decisión en F4 |
| pychromecast para TV | Nuevo módulo `commands/tv.py` registrado en el `action_map` | Así el casting sale GRATIS también por voz en el PC ("pasame esto a la tele") |
| Mini HTTP server para archivos locales | Endpoint `/media/` del propio gateway (FastAPI ya está ahí) | Un solo proceso, token obligatorio |
| mDNS/zeroconf para descubrimiento | Igual (`zeroconf`) anunciando `_limits._tcp` | La app no configura IPs |
| Respuesta textual a la app | El resultado de `executor.execute()` ya ES ese texto | Se devuelve por WS y además se habla por los altavoces del PC (comportamiento configurable) |
| UI orbe HUD | Se conserva tal cual la dirección de arte (§6) | Es buena y no choca con nada |

Lo único genuinamente nuevo en Python: gateway WS + zeroconf + módulo de casting.
Todo lo demás es cablear.

## 2. Arquitectura resultante

```
[App Android]                         [PC — Limits (proceso único)]
 wake word (on-device)                ┌────────────────────────────────────┐
   │                                  │ main.py                            │
   ▼                                  │  ├─ loop voz local (actual)        │
 SpeechRecognizer                     │  ├─ VoiceRouter piper/ElevenLabs   │
   │ texto                            │  ├─ LLMEngine Groq→Ollama          │
   ▼                                  │  ├─ CommandExecutor                │
 WebSocket ──WiFi LAN──► :8765 ──────►│  │   └─ action_map (+ tv.py NUEVO) │
 (token pairing)                      │  └─ GatewayServer (NUEVO, hilo)    │
                                      │       ├─ WS /ws      ← texto       │
 [Smart TV]◄──Chromecast──────────────┤       ├─ GET /media/<tok>/<file>   │
                                      │       └─ zeroconf _limits._tcp     │
                                      └────────────────────────────────────┘
```

Decisiones estructurales:

- **Un solo proceso**: el gateway corre en un hilo (uvicorn) dentro de
  `limits.service`, compartiendo directamente `llm`, `executor` y `router` de voz.
  Sin IPC ni segunda configuración. Alternativa descartada: servicio aparte con
  cola — complejidad sin beneficio en un asistente personal de 1 usuario.
- **Concurrencia = 1 por diseño**: un lock global serializa turnos (voz local y
  móvil compiten amablemente; el segundo espera o recibe "ocupado"). Es un
  asistente, no un API multiusuario.
- **El pipeline no cambia de forma**: `run_pipeline(user_input)` gana un valor de
  retorno estructurado (ya devuelve el texto hablado; solo hay que capturarlo y
  añadir metadatos) para mandarlo por WS.

## 3. Protocolo WebSocket (versionado desde el día uno)

```jsonc
// app → servidor
{"v": 1, "type": "hello",    "device": "pixel7"}
{"v": 1, "type": "command",  "text": "pon lofi en la tele"}
{"v": 1, "type": "ping"}

// servidor → app
{"v": 1, "type": "welcome",  "version": "1.0.0-prealpha", "queue": false}
{"v": 1, "type": "response", "ok": true,  "text": "Reproduciendo en Living Room.",
                             "intent": "tv_cast", "elapsed_ms": 4200}
{"v": 1, "type": "response", "ok": false, "err": "BUSY", "msg": "Estoy atendiendo otro comando."}
{"v": 1, "type": "pong"}
{"v": 1, "type": "event",    "kind": "speaking_started|speaking_finished"}  // F5+: para animar el orbe
```

Reglas: campos desconocidos se ignoran (compatibilidad hacia adelante); `v`
desconocido → error descriptivo; toda respuesta lleva `v`.

## 4. Seguridad (LAN-only, pero no confiado)

1. **Token de emparejamiento**: generado al primer arranque del gateway
   (`~/.limits/gateway_token`, 32 bytes hex). La app lo introduce UNA vez (o escanea
   QR que el PC muestra por consola); viaja como header `Authorization: Bearer` en
   el upgrade de WS. Sin token ⇒ close 4401.
2. **Bind a la LAN**: escuchar en `0.0.0.0:8765` solo si `GATEWAY_ENABLED=true`;
   nota de firewall en el README (`ufw allow 8765/tcp` o el equivalente de
   CachyOS). Jamás expuesto a internet; sin TLS por ser LAN doméstica + token
   (documentado como decisión consciente; TLS local con CA propia = overkill F1).
3. **El texto del móvil entra EXACTAMENTE igual que la voz local**: pasa por el
   mismo LLM router y cortafuegos del executor. Cero superficie nueva de ejecución.
4. **`/media/`**: rutas generadas por el servidor (nunca path traversal), URLs
   firmadas con expiración corta, token requerido.

## 5. Parte servidor — cambios en Limits

### Archivos nuevos/modificados

| Archivo | Rol |
|---|---|
| `modules/gateway.py` | **NUEVO** — `GatewayServer`: uvicorn en hilo daemon, WS `/ws`, auth por token, zeroconf register/unregister, mini file-server `/media/`, lock de turno |
| `commands/tv.py` | **NUEVO** — `TVCommands`: descubrir chromecasts, listar TVs, castear URL o archivo local, controlar reproducción (play/pause/volumen/stop vía pychromecast) |
| `commands/media.py` | helper `current_media_url()` via `playerctl metadata xesam:url` (para "castea lo que estoy viendo") |
| `main.py` | arranque/parada del gateway tras inicializar módulos (≈15 líneas) |
| `config.py` | variables §5.1 |
| `prompts/system_prompt.txt` | intents `tv_cast` + few-shots |
| `requirements.txt` | `fastapi`, `uvicorn`, `zeroconf`, `pychromecast` |

### 5.1 Configuración nueva (.env)

```bash
# ─── GATEWAY MOVIL (control remoto por voz) ──────────────────────────────
GATEWAY_ENABLED=false          # opt-in; requiere regenerar token al activar
GATEWAY_PORT=8765
# Token: se autogenera en ~/.limits/gateway_token si no existe (NO va en .env)
GATEWAY_SPEAK_LOCAL=true       # ¿el PC sigue hablando las respuestas mientras
                               # se controla desde el móvil?
GATEWAY_MDNS_NAME=Limits       # nombre anunciado por mDNS

# ─── TV / CASTING ─────────────────────────────────────────────────────────
TV_FRIENDLY_NAME=              # vacío = primera TV encontrada
TV_HTTP_MEDIA_PORT=8766        # puerto para servir archivos locales a la TV
```

### 5.2 Nuevos comandos del executor (benefician TAMBIÉN a la voz local)

| action | params | hace |
|---|---|---|
| `tv_cast` | `query` o `source="current"` | resuelve URL (web actual via `xesam:url`, o búsqueda YouTube→URL directa) y castea |
| `tv_control` | `action: play/pause/stop/volume_up/...` | control de reproducción |
| `list_tvs` | — | "Encontré Living Room y Dormitorio." |

Few-shots en el system prompt: *"pasame esto a la tele"* → `tv_cast{source:"current"}`;
*"pon lofi en la TV del living"* → `tv_cast{query:"lofi", target:"Living Room"}`.

### 5.3 Flujo interno de un comando remoto

```
WS message(text) → lock acquire (timeout 20s; si no: BUSY)
  → run_pipeline(text)            # idéntico a voz local
      → llm.process → executor.execute → router.speak(respuesta)  [si speak_local]
  → WS response {ok, text, intent}
  → lock release
```

Nota: `run_pipeline` ya loguea y habla; el gateway solo captura el retorno. Si el
executor devolvió error hablado, `ok:false` con ese texto.

## 6. Parte Android — spec heredada del prompt (se conserva)

Stack: Kotlin + Jetpack Compose, Porcupine u openWakeWord (decisión F4),
`SpeechRecognizer` nativo, OkHttp WebSocket, Foreground Service.

Estructura propuesta dentro de ESTE repo (monorepo personal):

```
clients/android/
├── app/src/main/java/dev/limits/jarvis/
│   ├── net/        (WsClient,Discovery[mDNS nsd],Pairing)
│   ├── voice/      (WakeWordService,SpeechToText)
│   ├── ui/         (Orbe,Estado,Historial,Pantalla principal)
│   └── data/       (Settings datastore,LogStore)
└── README.md       (build instructions)
```

Funcionalidad mínima por fase: ver §8. Dirección de arte: se adopta íntegra la del
prompt original (paleta `#0A0E14`/cyan `#00E5FF`/violeta procesando, orbe con
Canvas+Animatable, JetBrains Mono para logs, haptic feedback al detectar wake word,
una sola pantalla sin nav bar). Detalle fino conservado: el orbe en violeta +
anillo giratorio mientras `type:"response"` no llega (estado "procesando"), y el
evento `speaking_started` del protocolo permite sincronizar una animación sutil
mientras el PC habla.

## 7. Interacción con lo ya construido en Limits

- **Voz dual**: respuestas largas dichas desde el PC siguen usando ElevenLabs;
  el móvil solo recibe el texto. Si algún día se quiere TTS en el propio móvil
  (Android TTS engine), es un flag del cliente, cero cambios en el protocolo.
- **Puente Gemini (en pausa)**: cuando llegue, sus respuestas conversacionales ya
  saldrán por WS automáticamente porque pasan por `run_pipeline`. Nada que hacer.
- **Privacidad**: el dictado del móvil usa el STT de Google del teléfono (igual que
  hoy usa el teclado GBoard); el texto viaja cifrado por la LAN local hasta el PC.
  Alternativa full-local (enviar audio crudo a Whisper del PC) queda anotada como
  variante futura opt-in por latencia/ancho de banda.

## 8. Plan de implementación por fases

**F1 — Gateway en Limits (solo Python, ~1 sesión)**
- [ ] `GatewayServer` con WS + token + ping/pong + lock de turno
- [ ] `run_pipeline` devuelve `(texto_hablado, meta)` sin romper llamadas actuales
- [ ] zeroconf announce; tests mockeando websocket y lock
- [ ] Done: con `websocat`/script de prueba, un mensaje `command` produce la misma
      acción y respuesta que teclearlo en `--text`

**F2 — Casting a TV (solo Python, independiente del móvil)**
- [ ] `commands/tv.py`: discover/list/cast/control + HTTP media server con token
- [ ] Registro en action_map + DANGEROUS no aplica + 3 few-shots
- [ ] Done: por voz en el PC: "qué TVs hay", "castea lo que estoy viendo",
      "pausa la tele" funcionan end-to-end

**F3 — App Android esqueleto**
- [ ] Proyecto Compose + pantalla única con estado conexión + botón "hablar"
      (sin wake word) + historial estilo terminal
- [ ] Descubrimiento mDNS + pairing manual del token (campo de texto; QR en F6)
- [ ] Done: desde el móvil: "abre spotify" abre Spotify en el PC y el orbe muestra
      la respuesta

**F4 — Voz completa en el móvil**
- [ ] SpeechRecognizer → reemplaza botón; luego wake word (Porcupine u
      openWakeWord, decidir según licencia/free tier) + Foreground Service
- [ ] Whitelist batería MIUI/Samsung documentada en README del cliente
- [ ] Done: "Limits, pausa la tele" desde el sofá sin tocar el móvil

**F5 — Pulido bidireccional**
- [ ] Eventos `speaking_*` para animar el orbe; reconexión automática robusta
      (backoff exponencial); modo `GATEWAY_SPEAK_LOCAL=false`
- [ ] Done: red WiFi cae y vuelve → la app se reengancha sola sin tocar nada

**F6 — HUD final**
- [ ] Orbe reactivo a amplitud (escuchando), violeta girando (procesando),
      destello cyan (confirmación); tipografías; QR de emparejamiento
- [ ] Done: la app parece nave, no formulario

## 9. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| MIUI/Samsung matan el Foreground Service | Whitelist de batería guiada en el README; reconnect automático tolerante |
| Dos turnos simultáneos (voz PC + móvil) | Lock global con timeout → `BUSY` claro; nunca intercalar salidas |
| `xesam:url` vacío según reproductor | Fallbacks: último archivo mpv (`--input-ipc`), luego pedir query explícita |
| TV no Android/Chromecast (webOS/Tizen) | Fase F2 documenta detección; DLNA vía `pydlnadsm`/UPnP como extensión posterior, no bloqueante |
| Dependencias nuevas pesadas (pychromecast, fastapi) | Todas opt-in detrás de `GATEWAY_ENABLED`; import lazy para no penalizar arranque normal |
| Token filtrado en backups del teléfono | Regenerable borrando `~/.limits/gateway_token`; revocación = regenerar + reemparejar |

## 10. Referencias

- Pipeline y reglas: `AGENTS.md` (§4 flujo, §5 seguridad — aplican íntegras al gateway)
- Voz dual: `docs/plan-elevenlabs-tts.md`
- Gemini en pausa: `docs/integracion-gemini.md`
- Prompt original del usuario (dirección de arte y stack Android): sección §6 de este doc
