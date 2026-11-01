# Mejora 5 · Ejecución y conversación coherentes

Fecha: 2026-10-31. Estado: propuesta pendiente de aprobación para implementar.
Tarea: [mejora-5-ejecucion-coherente.md](tasks/mejora-5-ejecucion-coherente.md).

## Problema y evidencia

La conversación de 21:08–21:11 expone fallos del recorrido completo, pese a las
pruebas anteriores de componentes. Fuente: logs/limits.log, episodios 661–676
de SQLite y estado persistido de la sesión móvil. No copiar secretos ni títulos
privados al informe.

- Consultar el workspace produjo cinco consultas al modelo cotidiano y escalado
  a análisis; terminó cancelado. No se conserva toda la traza de herramientas.
- Reproducir música y ajustar volumen produjo siete consultas cotidianas y cinco
  al especialista; terminó cancelado. Los efectos no pueden reconstruirse con
  certeza a partir de la evidencia conservada.
- Cerrar la ventana especial propuso `special_window`, inexistente. El handler
  devolvió None y el adaptador lo convirtió en solicitud aceptada. El historial
  repitió el recibo; esto no demuestra dos ejecuciones del efecto.
- Una aclaración concatenó datos internos de ventanas y los incorporó al diálogo.
- El código descarta consultar_ventanas al redactar resultados, aunque puede ser
  la respuesta principal. Es un defecto demostrado; su participación exacta en
  la consulta fallida no está demostrada por la traza conservada.

## Resultado esperado

Un agente mantiene el objetivo y decide el siguiente paso con herramientas reales.
El ejecutor valida el alcance y comprueba los efectos. La respuesta comunica datos
observados, resultados parciales o una aclaración concreta. Las órdenes compuestas
conservan todos sus objetivos. Una cuota agotada no oculta efectos ya realizados.

## Arquitectura propuesta

Petición + contexto pertinente → agente único → herramientas → evidencia →
respuesta o siguiente paso justificado.

1. Conservar atajos completos e inequívocos. El resto entra directamente al agente
   cotidiano; retirar de ese recorrido la propuesta previa del router Qwen, la
   clasificación redundante y los jueces de preguntas y cobertura por defecto.
   Qwen sigue disponible en compatibilidad y modo explícitamente local.
2. El agente recibe el objetivo completo, diálogo breve, capacidades y observaciones
   pertinentes. Puede consultar, actuar, responder o pedir una aclaración. No necesita
   ejecutar una herramienta de relleno para poder preguntar.
3. Mantener un plan explícito de resultados solicitados y vínculos con recibos.
   Los objetivos rutinarios se cierran mediante postcondiciones de herramientas.
   Una síntesis compleja puede necesitar revisión adicional, pero no cada operación.
4. Separar comprensión semántica de permisos: el agente propone acciones vinculadas
   al objetivo; el ejecutor conserva catálogo, tipos, exclusiones, rutas observadas,
   confirmaciones y recibos. La migración de la autorización semántica debe estar
   documentada y probada antes de retirar su juez actual. Un identificador de
   objetivo aportado por el modelo, por sí solo, no concede autorización.
5. Resolver entidades reales antes de mutar: aplicación, ventana, workspace normal
   o especial. No aceptar nombres inventados como destinos. Consultar foco y especial
   visible cuando haga falta; distinguir ocultar un especial de cerrar su aplicación.
6. Conservar parejas de proveedores por rol. Un error de transporte activa su
   respaldo; una dificultad real de razonamiento puede delegarse con contexto.
   Una respuesta vacía o un contrato incorrecto no convierte una tarea en análisis.

LangGraph puede mantenerse como controlador de estados; sustituirlo por n8n no
resuelve los contratos defectuosos ni las decisiones redundantes.

## Fases de implementación

### 1. Contratos de ejecución

Auditar handlers expuestos por task_tools y normalizar su resultado: estado
`completado|fallido|pendiente|sin_verificar`, datos estructurados, evidencia,
motivo de fallo y resumen apto para voz. Separar aceptación de una solicitud de
comprobación del efecto. None significa ausencia de evidencia, nunca éxito.

Empezar por adaptar todos los handlers accesibles al agente, no solo Spotify.
Cada capacidad declara parámetros, alcance, prerrequisitos, efecto y forma de
verificación. Las capacidades sin verificación deben comunicar esa limitación.
Archivos principales: commands/*, command_result.py, task_tools.py y capability_tools.py.

### 2. Ciclo único y objetivos compuestos

Reestructurar main.py, orchestrator.py, general_agent.py, task_state.py y prompts.
Mantener por objetivo su estado, recibos y pendientes. Evitar descartar partes de
una petición al aceptar la primera acción propuesta. Conservar historial de pasos
y no repetir efectos completados o inciertos sin observar su estado primero.

Mantener una separación explícita entre el objetivo del usuario y datos externos.
Gemini continúa sin producir acciones ejecutables. Conservar sandbox y aprobación
de scripts. No ampliar la terminal existente.

### 3. Entidades y contexto

Obtener estado actual del escritorio bajo demanda con identidad estable y fecha
de observación. Resolver referencias del diálogo contra ese estado; volver a
comprobar antes de una mutación cuando la observación pueda haber caducado.
Si persiste una ambigüedad, ofrecer solo las opciones pertinentes.

Memoria SQLite/Obsidian aporta preferencias e historia; no acredita estado actual
ni permisos. No modificar la arquitectura de memoria en esta tarea. Evitar que
resultados técnicos o respuestas fallidas entren como contexto conversacional útil.

### 4. Respuesta, cancelación y recuperación

Construir una presentación única para respuesta normal, aclaración, error y
cancelación. Nunca concatenar repr/JSON de herramientas ni leer rutas de artefactos
como sustituto de una explicación. Una consulta puede usar cualquier observación
relevante, aunque la herramienta suela ser preparatoria.

Mantener SpeechController como único dueño del audio y el bloqueo hasta finalizar
la entrega. Avances breves solo cuando hay espera real; nunca inventar progreso.
Tras cancelar, detener audio y ejecución y conservar los recibos; la interfaz puede
mostrar lo completado sin reanudar voz no solicitada.

Una corrección de parámetros por fallo recuperable y como máximo una delegación
justificada por tarea cotidiana. No reiniciar todo el objetivo tras un fallo.
Los reintentos de proveedor comparten presupuesto y no repiten efectos.

### 5. Observabilidad, aceptación y activación

Registrar id de turno, etapa, duración, proveedor, número de inferencias, herramienta,
estado del resultado, motivo de recuperación/cancelación y pendientes. No elevar
texto de usuario/respuesta sobre DEBUG ni guardar secretos. Conservar una traza
acotada por turno para que una tarea posterior no borre la evidencia del fallo.

Objetivo de eficiencia: órdenes simples no rápidas usan normalmente una inferencia
para elegir acción y hasta otra para redactar; las compuestas crecen por dependencias
reales, no por jueces repetidos. Medir tiempos por etapa; aspiración de respuesta
simple menor de cinco segundos con proveedor disponible, no garantía de red.

## Validación acotada

Primero pruebas sin red con respuestas grabadas/simuladas a través del pipeline,
incluyendo gateway y presentación. Casos obligatorios:

1. Consulta de ventanas del workspace, con respuesta útil y sin mutaciones.
2. Dos acciones en un turno; informar cada resultado, incluido fallo parcial.
3. Referencia a especial visible; distinción entre ocultar y cerrar, ambigüedad real.
4. Destino inventado y handler sin resultado: rechazo/sin verificar, jamás éxito.
5. Negación, consulta y datos externos no autorizan efectos.
6. Cancelación después de un efecto, cuota agotada y reconexión: sin duplicación.
7. Confirmación caducada, rutas no observadas y scripts conservan sus protecciones.
8. Conversación con referencia al turno anterior y memoria pertinente, sin datos crudos.

Ejecutar una vez la suite pertinente y una suite completa antes de activar. Repetir
solo pruebas afectadas por un cambio o fallo concreto. No comparar modelos.

Después de pasar las pruebas sin red: una sesión de aceptación de hasta seis turnos
con modelos reales, máximo veinte inferencias y tres minutos acumulados de proveedor.
Parar al primer bloqueo de cuota; informar el pendiente en vez de repetir. Efectos
reales reversibles, memoria temporal y restauración en finally. Sin micrófono manual.
No declarar aceptación completa si faltan escenarios por presupuesto.

## Activación y reversión

Introducir un selector temporal centralizado en config.py para comparar recorridos
sin ejecutar ambos. Mantener configuración y estado previo respaldados. Activar
tras aceptación, reiniciar servicio y comprobar su estado una vez. Si hay regresión,
volver al recorrido previo sin borrar memoria ni recibos; informar sus limitaciones.
La reversión no reutiliza aprobaciones pendientes. Actualizar AGENTS, documentación
y changelog; no hacer commit ni release sin solicitud.

## Fuera de alcance

Nuevos proveedores, comparativas de modelos, cambios del widget, nueva memoria,
automatización arbitraria de interfaces, aprendizaje automático de permisos y
garantías de controlar cualquier aplicación sin una capacidad disponible.

## Cierre

Todos los criterios funcionales aprobados, límites y fallos publicados, ausencia de
éxitos inventados/datos crudos/efectos duplicados y evidencia por turno. Una suite
verde sola no acredita que la experiencia conversacional esté resuelta.
