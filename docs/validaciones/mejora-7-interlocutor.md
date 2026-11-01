# Entrega · Interlocutor y ejecución por capacidades

Fecha: 2026-11-01. Respaldo previo publicado en main: `8c0cfc1`.

Implementación en el ciclo existente: interlocutor primero, llamadas directas o
encargo a Qwen y retorno de recibos para redactar el cierre cotidiano. Diálogo
reciente, pregunta pendiente y recuperación de memoria confirmada. Sin otra
interpretación léxica de permisos en el recorrido conversacional.

Configuración activa: AGENT_MODE=conversacional; interlocutor
qwen2.5:3b-instruct; ejecutor qwen2.5:1.5b-instruct. Modelos ya instalados.
No se descargaron modelos ni se entrenaron pesos. Respaldo privado del .env
anterior en ~/.limits/respaldos/interlocutor-20261101-132543, modo 0600.

Comprobaciones realizadas:
- Revisión estática de contratos, flujo de roles, parámetros, cancelación y voz.
- AST correcto en 11 archivos Python modificados/nuevos.
- git diff --check sin errores.
- Servicio reiniciado: 2026-11-01 16:23:02 CST, active/running, ExecMainStatus=0.
- Registro de arranque: modelos separados y «Limits listo». No se publica el
  registro completo porque contiene información privada de emparejamiento.

No se ejecutaron tests, probes, inferencias de aceptación ni acciones en el
escritorio. Se prepararon regresiones con proveedores simulados, SIN EJECUTAR.
No hay medición de latencia ni aceptación funcional por voz. El 3B puede seguir
fallando en comprensión o redacción; separar funciones no garantiza calidad.

Aprobaciones y resultados sensibles conservan entrega directa; Gemini conserva
streaming y documento sin volver como instrucciones al ciclo ejecutable. Copiar
rechaza destinos existentes; no se habilita sobrescritura. Las herramientas
acotadas y las confirmaciones siguen vigentes.

Reversión sin restaurar código ni aprobaciones: AGENT_MODE=local y reiniciar
limits.service. Mantener intactas SQLite y la bóveda.

## Corrección del fallo de arranque de inferencia

Los cuatro turnos reales de las 16:29–16:30 fallaron antes de obtener salida
de Qwen. El registro de Ollama identifica repeticiones excesivas en la gramática
JSON, seguidas de SIGSEGV y HTTP 500. El esquema nuevo incluía maxLength
500/4000: se retiraron del esquema enviado; los límites siguen comprobándose
en decidir_interlocutor. Se conserva la salida estructurada y su validación.
Los errores HTTP del proveedor local tienen ahora una clase y mensaje propios,
y registran solo el estado HTTP, sin cuerpos ni datos privados.

Revisión de sintaxis AST y diff; no se ejecutaron tests ni inferencias. Los
registros de esos turnos no muestran un error independiente de TTS. Esto no
acredita que el audio sea audible ni sustituye la aceptación funcional.

## Diagnóstico y corrección de ejecución/entrega

Evidencia de dos turnos reales del usuario, sin inferencias de prueba:
- Workspace: 20,221 s primera inferencia, 4,181 s corrección, 4,075 s
  herramientas y 4,839 s replanteamiento: 33,410 s ciclo, 44,776 s turno.
  Inventó una dirección de ventana y luego focus_window de una calculadora no
  solicitada. El fallback del handler abrió la aplicación.
- Cerrar calculadora/abrir editor: efectos verificados al primer lote. Repitió
  el lote en otras dos inferencias (6,414 y 5,247 s), bloqueadas por recibos.
  Ciclo 18,367 s, turno 23,516 s. La respuesta parcial no describía el éxito real.

Cambios: fase resultado sin catálogo ni operaciones ejecutables, una sola
explicación y fallback a recibos sin reintento; esquema compacto para reducir
entrada. Después de consultas preparatorias aún puede planificar; task mantiene
el ciclo del ejecutor hasta entregar el lote final o informe. El interlocutor
puede anticipar el lote tras validar todos los pasos. No se añade otro modelo,
juez semántico, patrón de frases ni inferencia inicial.

Los contratos conversacionales exigen una cita literal por operación y el prompt
distingue opciones del catálogo de objetivos pedidos. Esto permite revisar
la procedencia pero NO demuestra que cualquier efecto sea pertinente. La
comprensión sigue dependiendo de Qwen; una cita auténtica puede acompañar una
interpretación equivocada. El foco se limita a ventanas observadas y jamás
lanza una aplicación implícitamente.

Regresiones simuladas actualizadas/preparadas para cierre, efectos inciertos,
citas inventadas y foco ausente. NO EJECUTADAS. Verificación permitida: AST,
diff y estado/arranque. No hay cifras de rendimiento posteriores al cambio.
Los próximos turnos reales registrarán carga, evaluación de entrada y generación
de Ollama en el diagnóstico privado para separar sus costes.

Revisión tras aplicar el cambio: AST correcto en 8 archivos Python modificados
y git diff --check limpio. Servicio reiniciado el 2026-11-01 a las 16:46:49 CST:
active/running, ExecMainStatus=0. Esto verifica el arranque, no la comprensión,
el audio ni la latencia de una inferencia. No se ejecutó ningún test/probe/modelo.

## Simplificación del recorrido

Diagnóstico posterior basado en turnos reales: el requisito de copiar la cita
rechazó una intención reconocida al corregirse el dictado; dos inferencias de
16,659 y 4,936 s. Un cambio de workspace comprobado terminó pidiendo confirmar
la misma acción. Al solicitar un proyecto, el modelo arrastró un workspace anterior.
En ese turno, 18,158 s evaluando entrada, 1,551 s generando y 0,072 s cargando:
optimizar keep_alive no aborda su coste dominante. No se atribuye todo el tiempo
restante al modelo: el turno también espera la entrega y el audio.

Se retiraron cita obligatoria y voz libre de intención. Efectos directos entregan
sus recibos sin narración adicional. Prompt y catálogo más breves, sin duplicar
firmas, petición ni objetivos/preguntas/recibos de turnos anteriores como pendientes.
Se conserva diálogo breve como referencia; no se promete interpretar bien cada caso.
La métrica de tokens de caché se recoge únicamente si el servidor la suministra.

Gemini mantiene streaming: se publica el texto final antes de esperar el audio,
reservándolo para el flujo para impedir duplicación. Se conserva el bloqueo hasta
liberar voz/escucha. WS anuncia audio/cierre con id de turno; Android actualiza los
estados en Main y discrimina turnos. Fuente Android modificada: APK debug compilado sin tests, NO instalado en el
teléfono. El backend conserva compatibilidad mediante eventos aditivos.

Regresiones adaptadas para no exigir inferencias de cierre ni citas, conservar
confirmaciones y comprobar el evento de fin. NO EJECUTADAS. No se corrieron
pruebas, inferencias ni voz. Se compiló assembleDebug --offline correctamente
en 12 segundos; no ejecuta tests. La latencia posterior del asistente no está medida.

Verificación estática: AST correcto en 9 archivos Python modificados y diff sin
errores de formato. Prompt interlocutor 4574 → 2577 bytes en crudo; sin medición
de tokens ni latencia. APK en clients/android/app/build/outputs/apk/debug/app-debug.apk.
El archivo compilado está fuera del versionado; requiere instalación en el teléfono.

Servicio reiniciado 2026-11-01 17:45:35 CST: active/running, ExecMainStatus=0
y mensaje de arranque «Limits listo». Solo verifica arranque; sin aceptación
funcional ni medición posterior de respuesta.
