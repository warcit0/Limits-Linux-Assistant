# Asistente por objetivos

La mejora 1 incorpora un coordinador local con LangGraph. Conserva las órdenes
rápidas y añade conversación, tareas con contexto y especialistas configurables.
El modo está activado en este equipo tras la aceptación. La configuración
distribuida conserva `false` como valor inicial; el pipeline anterior permite reversión.

## Configuración

`AGENT_ENABLED=true` selecciona la coordinación por objetivos; `false` vuelve al
modo anterior. Toda configuración se declara en `config.py` y se documenta en
`.env.example`. Tras cambiarla, reinicia `limits.service` si estaba activo.

| Variable | Uso |
|---|---|
| `AGENT_TASK_PATH` | Estado y artefactos privados; por defecto `~/.limits/tareas`. |
| `AGENT_REMOTE_PROVIDER` | `opencode_con_respaldo` por defecto; `opencode` desactiva el respaldo; `nvidia` selecciona explícitamente los modelos NVIDIA por rol. |
| `NVIDIA_API_KEY` | Credencial solo en `.env`, con permisos 600. |
| `NVIDIA_BASE_URL` | Endpoint compatible con OpenAI de NVIDIA. |
| `NVIDIA_DEVELOPMENT_MODEL` | Respaldo de DeepSeek de OpenCode: `deepseek-ai/deepseek-v4.1-flash`. |
| `NVIDIA_ANALYSIS_MODEL` | Respaldo de Big Pickle: `nvidia/nemotron-3.5-bolt-e4b`. |
| `NVIDIA_SUPER_API_KEY`, `NVIDIA_SUPER_MODEL`, `NVIDIA_BOLT_API_KEY` | Claves separadas y modelo Super; Bolt conserva respaldo con su propia clave. |
| `AGENT_SUPER_FALLBACK` | Añade Super antes de Bolt, únicamente en análisis. |
| `NVIDIA_GLM_API_KEY`, `NVIDIA_GLM_MODEL` | Clave propia y modelo GLM Flash; no sustituyen la clave NVIDIA existente. |
| `AGENT_GLM_FALLBACK` | Añade GLM a desarrollo; mantener false mientras no supere la prueba de disponibilidad. |
| `GROQ_API_KEY`, `GROQ_BASE_URL`, `GROQ_AGENT_MODEL` | Respaldo externo GPT-OSS 120B; credencial solo en `.env`. |
| `GROQ_MAX_TOKENS` | Tope por respuesta de Groq: 2048, independiente del de NVIDIA. |
| `AGENT_GROQ_FALLBACK` | Añade Groq al final de las dos cadenas de especialistas. |
| `NVIDIA_MAX_TOKENS` | Tope por respuesta, por defecto 4096. |
| `NVIDIA_THINKING_ENABLED` | Razonamiento interno activado como en el ejemplo proporcionado. Su contenido nunca se habla ni ejecuta. |
| `NVIDIA_MODEL_COOLDOWN` | Segundos antes de volver a intentar un modelo fallido, por defecto 60; respeta `Retry-After` hasta 600 s. |
| `AGENT_OPENCODE_BIN`, `AGENT_DEVELOPMENT_MODEL`, `AGENT_ANALYSIS_MODEL` | Ejecutable y modelos principales de desarrollo/análisis en OpenCode. |
| `AGENT_MAX_STEPS` | Máximo de herramientas por turno; por defecto 6. |
| `AGENT_TIMEOUT` | Presupuesto de consulta y ejecución por turno, antes del audio; por defecto 120 s. |
| `AGENT_CONTEXT_CHARS` | Presupuesto del contexto enviado al especialista; por defecto 12.000 caracteres. |
| `AGENT_VOICE_CHARS` | Longitud aproximada de la versión hablada; el texto completo se conserva como artefacto. |
| `GEMINI_RESEARCH_DAEMON` | `false` por defecto: espera completa mediante gemdev clásico; investigación exige dos enlaces distintos y fechas. |
| `AGENT_APPROVAL_TTL` | Vigencia de una propuesta pendiente; por defecto 300 s. |

Qwen utiliza el Ollama ya configurado. La investigación utiliza el puente gemdev
existente y requiere `GEMINI_ENABLED=true` y una sesión autenticada. La selección
explícita de Qwen o Gemini prevalece sobre la propuesta del selector. DeepSeek
selecciona el rol de desarrollo, que mantiene OpenCode como principal y NVIDIA DeepSeek como respaldo. «Solo local» o «sin internet» mantienen la tarea en Ollama.

## Funcionamiento

Las órdenes inequívocas de hora, memoria explícita, archivos, apps y música
conservan sus rutas rápidas. Preguntas sobre cómo ejecutar una orden, negaciones
y objetivos compuestos pasan al coordinador.
Las órdenes operativas ya existentes que necesitan el router anterior conservan
su contrato y executor, con historial separado por sesión. La tarea compuesta de
búsqueda y copia de archivos existente conserva su lane acotado.

Qwen selecciona un rol y modo de trabajo. El selector utiliza también hechos
comprobables del contexto: una ruta local solicitada y las referencias a una
tarea anterior. El coordinador limita el permiso de modificar según la petición
del usuario; el modelo no puede concedérselo por sí mismo.

El ciclo decide un paso, valida su herramienta y parámetros, observa el resultado
y continúa. Las peticiones sobre archivos o estado del equipo requieren datos
observados antes de aceptar una conclusión. Las consultas generales no necesitan
acceso al disco.

Cada sesión mantiene objetivo, observaciones, resultados, artefactos y recibos de
operaciones. «Explícame la segunda opción» puede continuar la tarea. Las tareas
se guardan en JSON privado y se recuperan tras reiniciar, conservando los recibos;
las aprobaciones y trabajos activos se invalidan al recuperar el proceso.

La memoria de tareas está separada de los hechos personales explícitos de SQLite.
El coordinador no convierte sus inferencias en recuerdos personales.

## Especialistas

- **Cotidiano / Qwen:** conversación, explicaciones y herramientas comunes.
- **Desarrollo / DeepSeek OpenCode:** principal `opencode/deepseek-v4.1-flash-free`;
  respaldo NVIDIA `deepseek-ai/deepseek-v4.1-flash` si falla o se agota la cuota.
- **Análisis / Big Pickle OpenCode:** principal `opencode/big-pickle`; respaldo
  NVIDIA `nvidia/nemotron-3.5-bolt-e4b` si falla.
- **Investigación / gemdev:** información actualizada. Su respuesta es informativa
  y nunca se convierte en herramientas o comandos ejecutables.

La aclaración del usuario sustituye la configuración inicial incorrecta que
alternaba ambos modelos NVIDIA. Las parejas tienen prioridad fija y disponibilidad
independiente. Un principal que responde no consume el respaldo. Después de un
fallo se enfría el proveedor afectado y se consulta exclusivamente el respaldo de
su rol. Al caducar el enfriamiento vuelve a probarse el principal. Cada candidato
se consulta una vez dentro del presupuesto del turno. Si todos los candidatos fallan, se conserva
el estado y se comunica el fallo; no se cruza al modelo del otro rol.

`DESKTOP_AGENT_PROVIDER=opencode` y `DESKTOP_AGENT_FALLBACK=nvidia` mantienen
DeepSeek OpenCode primero en las tareas compuestas de archivos. Si falla, utilizan
NVIDIA DeepSeek; Nemotron queda reservado al respaldo de Big Pickle.

OpenCode CLI V2 tiene las herramientas nativas denegadas. Las propuestas de todos
los modelos pasan por el catálogo y los límites de Limits. La salida interna de
razonamiento de los modelos no se habla ni ejecuta. Ningún cambio de proveedor ejecuta
herramientas por sí mismo. Los datos facilitados a los especialistas se procesan
en servidores remotos; «solo local» conserva la tarea en Ollama.

Con Groq habilitado, las prioridades son:

- Desarrollo: OpenCode DeepSeek → NVIDIA DeepSeek → Groq GPT-OSS 120B.
- Análisis: OpenCode Big Pickle → NVIDIA Nemotron Super (si está habilitado) → Bolt → Groq GPT-OSS 120B.

GLM queda preparado como alternativa opcional para desarrollo; habilitarlo lo
coloca antes de NVIDIA DeepSeek. No se intercambian Nemotron y DeepSeek entre
roles. `DESKTOP_AGENT_FALLBACK=nvidia` conserva su nombre y utiliza la misma
lista de respaldos de desarrollo, incluyendo Groq si está habilitado.

Groq usa JSON completo, sin streaming, y el mismo verificador local de decisiones.
Sus límites gratuitos pueden provocar HTTP 429. Se respeta `Retry-After` cuando
cabe dentro del turno; como máximo se repite una petición de inferencia, también
ante un rechazo explícito de formato JSON. La repetición nunca ejecuta herramientas
ni amplía el presupuesto. Un error o una cancelación no autorizan efectos nuevos.
No se enviará una orden cotidiana a Groq: el selector y router siguen siendo locales.

## Archivos, scripts y aprobaciones

El usuario indica la ruta o una carpeta conocida. Las herramientas consultan ese
alcance y las rutas observadas; no aceptan una ruta inventada por el modelo ni
amplían el alcance mediante enlaces simbólicos. Si falta una carpeta, se pregunta.

Un script Python se guarda como artefacto privado de la tarea. `probar_script`
utiliza bwrap con una copia temporal de los datos: sin red ni HOME del usuario,
runtime de solo lectura y límites de CPU, memoria, procesos, tiempo y tamaño.
El script trabaja sobre `/datos`. La prueba rechaza árboles con archivos privados,
enlaces o más de 200 entradas y 5 MB de archivos. Una carpeta de trabajo por sí sola no se
considera aislamiento. Si bwrap falta, no se ejecuta el script.

Aplicarlo a los originales requiere una propuesta concreta y «confirmar». La
aprobación identifica tarea, revisión, código y contenido de los datos probados;
si cambian, debe probarse de nuevo. Tras aplicar y verificar un script se comunica
el resultado directamente; no se necesita otra inferencia para confirmar el efecto. Los efectos iniciados se registran antes de
ejecutar: una operación interrumpida no se repite automáticamente. Un script
fallido puede dejar cambios parciales dentro de su carpeta autorizada; requiere
inspección y no se presenta como una ejecución satisfactoria.

## Voz y móvil

El pipeline conserva el bloqueo compartido durante respuesta y audio. El origen
Gemini llega al selector de voz. Las respuestas largas se conservan completas en
un artefacto y se ofrece una versión breve para hablar. El gateway puede entregar
los artefactos por sus URLs firmadas existentes.

Cada conexión móvil tiene una sesión diferente de la local. Las propuestas no se
comparten entre sesiones. La desconexión cancela su tarea; reconectar crea una
sesión nueva. No se promete continuidad de sesión móvil tras reconectar.

`stop` y las palabras de corte se atienden sin esperar al bloqueo. Cancelan la
inferencia, los subprocesos, la voz y los turnos de esa sesión que estaban en cola.
Las respuestas tardías se descartan. Con micrófono y barge-in habilitados se
reutiliza la escucha VAD durante la consulta del modelo; se libera el micrófono
antes de hablar. Una orden que interrumpe se conserva como siguiente turno.

## Verificación y estado de entrega

La suite incorpora casos de continuidad, separación de sesiones, grounding,
aprobaciones caducadas, cancelación, resultados tardíos, voz, gateway real y
ejecución de scripts en bwrap. Las pruebas automáticas usan dobles de proveedores
y datos temporales; la sonda del selector consulta Ollama sin ejecutar acciones:

```bash
./limits-env/bin/python -m unittest discover -s tests -v
./limits-env/bin/python scripts/probe_objectives.py --min-accuracy 0.90
./limits-env/bin/python scripts/probe_pipeline.py
./bin/measure-router --min-accuracy 1.0
```

Resultados de la entrega en [la validación de la mejora 1](validaciones/mejora-1/informe.md):
405 pruebas automáticas, 40/40 escenarios del selector, 32/32 órdenes conservadas,
recorrido real de análisis/script/aprobación/aplicación, Gemini con fuentes y
cancelación con el micrófono del equipo. OpenCode conserva prioridad; Super, Bolt y
Groq tienen pruebas reales satisfactorias. GLM permanece desactivado y NVIDIA
DeepSeek no ha respondido en las comprobaciones; los respaldos permiten trabajar.

## Conversación fluida (Mejora 2)

Qwen conversa con un prompt independiente y salida natural cuando no necesita
herramientas. Conserva preguntas y alternativas recientes; las respuestas cortas
pueden continuar ese tema. Tras una pregunta hay 10 segundos para responder por
voz sin repetir Limits (`DIALOGUE_FOLLOWUP_SECONDS`, 0 desactiva). Las operaciones
sensibles siguen requiriendo su aprobación concreta y vigente.

Las órdenes de workspaces existentes tienen ruta directa, normalizan variantes de
transcripción y verifican el destino real. Mover esta ventana requiere decirlo
expresamente. No se crean espacios y los especiales todavía no están soportados.
Sin capacidad visual, Limits lo explica y ofrece consultar ventanas de aplicaciones.

Gemini emite avances provisionales por frases mientras genera; el final conserva
texto y fuentes completos. La cola de voz local Piper evita esperas adicionales de
un proveedor de voz y mantiene una única escucha y reproducción. Si cambia una
frase ya hablada o falla la validación final, comunica la corrección. Las fuentes y
fechas se revisan al final; su presencia no garantiza la exactitud de cada afirmación.
El audio ya emitido no se vuelve a leer por cambios de formato.

`GEMINI_STREAMING=true` requiere el CLI gemdev con eventos v1 y su navegador
persistente. Para volver manualmente al modo clásico, desactivar esa opción y
liberar antes el perfil del navegador persistente. No hay fallback automático al
protocolo antiguo. `AGENT_CONVERSATION_MODEL` permite cambiar únicamente el modelo
de conversación/trabajo local; vacío conserva `OLLAMA_MODEL`, incluido su contexto.

Las trazas temporales correlacionan turno, sesión y tiempos hasta el primer PCM;
el texto privado permanece en DEBUG. La suite aísla memoria y tareas por prueba.
Informe de aceptación: [Mejora 2](validaciones/mejora-2.md).
