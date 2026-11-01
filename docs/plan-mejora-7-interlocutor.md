# Mejora 7 · Interlocutor y ejecución por capacidades

Autorizada el 2026-11-01. Respaldo previo en main: `8c0cfc1`.

## Objetivo y recorrido

El interlocutor mantiene diálogo, intención y preguntas pendientes. Decide si responde,
llama una herramienta concreta o encarga un objetivo cotidiano completo a Qwen.
El despachador consume JSON; no traduce otra vez el lenguaje del usuario.

Voz/texto → interlocutor → llamada directa o Qwen ejecutor → recibos → interlocutor → voz.

Se conserva UN ciclo en coherent_agent y Orquestador._ejecutar. conversation.py contiene
contratos y preparación de contexto, sin otro bucle. Los modelos no ejecutan comandos
por producir texto. Cada operación atraviesa validación técnica y ejecución registrada.

## Roles y contexto

- `AGENT_MODE=conversacional` activa el recorrido nuevo. local/legacy permiten reversión.
- Interlocutor: AGENT_CONVERSATION_MODEL. Instalación inicial: Qwen 2.5 3B ya disponible.
- Ejecutor cotidiano: OLLAMA_MODEL, Qwen 2.5 1.5B. Solo interviene en encargos abiertos.
- Desarrollo/análisis conservan proveedores y respaldos anteriores. Investigación usa
  Gemini y su salida exclusivamente informativa. Nunca constituye una instrucción ejecutable.
- Diálogo reciente de la misma sesión, hasta diez entradas y 30 minutos de inactividad;
  la pregunta y resultados anteriores se presentan como históricos. No heredar ventanas,
  autorizaciones o recibos de otra tarea. Una aclaración conserva las raíces ya delimitadas.
- Recuperar hasta dos recuerdos confirmados desde la SQLite/bóveda existentes.
  Olvidar invalida contexto; las inferencias no se guardan como hechos personales.

## Decisiones y efectos

El interlocutor usa command/chat/clarify del contrato existente o task/delegate. Un
encargo transmite objetivo y restricciones a Qwen junto con la petición original.
La intención hablada se entrega por SpeechController/FlujoVoz bajo el mismo bloqueo.
Los JSON completos se validan antes de hablar: no se reproducen tokens de JSON incompleto.

Se retira la comprobación léxica de operación/destino en este modo. La intención queda
a cargo del interlocutor y del ejecutor, con el riesgo de errores semánticos del modelo.
La política comprueba capacidades/efectos, no maneras de pedirlas. Se conservan firmas,
tipos, enums, catálogo instalado, observación de destinos, path guard y recibos sin repetición.

- Efectos cotidianos acotados: ejecución sin otra inferencia de autorización.
- Apagar/reiniciar, mover/renombrar, envío de contenido a TV y aplicación de scripts:
  propuesta explícita antes del efecto. Copiar rechaza destinos existentes; no concede
  una capacidad de sobrescritura.
- Scripts: sandbox, prueba de copia, huellas y aprobación vigente. Terminal arbitraria
  y capacidades sin política quedan fuera del recorrido.
- Memoria personal mantiene el reconocimiento explícito de guardar/olvidar.
- Aprobaciones, cancelación y entrega de resultados comprobados de scripts conservan
  su salida directa. No depender de una nueva inferencia para comunicar un efecto sensible.
- Gemini conserva voz progresiva y artefacto completo directamente; su contenido no
  vuelve a un ciclo con herramientas. Esta es una excepción deliberada al cierre conversacional.

El interlocutor redacta los cierres cotidianos a partir de recibos, incluyendo errores
e incertidumbre. Su prosa no demuestra cobertura semántica universal. No hay juez extra
ni garantía de que un 3B interprete correctamente cualquier petición.

## Límites y validación

No se descargaron modelos ni se entrenaron pesos. El 3B se eligió por estar instalado;
calidad y latencia reales quedan pendientes de la prueba libre del usuario. Puede aumentar
la latencia: una acción concreta requiere decisión y respuesta; un encargo añade Qwen.
Las intenciones habladas cubren trabajo prolongado, no prometen éxito ni ocultan esperas.

Por indicación vigente NO ejecutar tests, probes, inferencias de aceptación ni acciones
sobre el escritorio. Se preparan regresiones simuladas para revisión futura. Únicamente
revisión estática, AST, diff y arranque del servicio. No marcar aceptación funcional.

Revertir el recorrido: AGENT_MODE=local en .env y reiniciar. No restaurar aprobaciones
ni memoria. Para volver a código anterior que desconoce campos nuevos, apartar el estado
temporal de tareas con el servicio parado; conservar SQLite y la bóveda.
