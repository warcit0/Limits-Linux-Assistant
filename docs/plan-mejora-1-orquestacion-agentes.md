# Mejora 1: asistente por objetivos y especialistas

Estado: implementación experimental; verificación externa parcial. Actualizado: 2026-10-31.
La propuesta original se conserva debajo como referencia. La decisión posterior
aclarada por el usuario mantiene OpenCode DeepSeek y Big Pickle como principales.
NVIDIA DeepSeek respalda únicamente al primero y NVIDIA Nemotron únicamente al
segundo, sin alternancia entre roles.
La configuración vigente está en [la guía operativa](asistente-por-objetivos.md) y
la evidencia en [el informe](validaciones/mejora-1/informe.md). Los apartados que
proponían comparar Big Pickle y DeepSeek gratuitos han quedado sustituidos por
esta decisión de respaldo específico por rol.

Tarea de implementación: [Mejora 1 · Asistente por objetivos y especialistas](tasks/mejora-1-asistente-por-objetivos.md).

## Resultado esperado

Limits podrá conversar, analizar información, recomendar, ejecutar tareas de varios
pasos y explicar el resultado. Cada tarea conservará su objetivo y sus resultados
para admitir aclaraciones y continuaciones. El usuario no necesitará nombrar el
modelo que debe atenderla, aunque podrá hacerlo explícitamente.

Ejemplo de aceptación: «Revisa esta carpeta y recomienda cómo organizarla» debe
producir una recomendación basada en archivos observados. «Prepara un script para
esa organización» debe conservar el contexto, generar un archivo y probarlo sobre
una copia temporal. Una posterior autorización debe referirse a ese plan concreto.

## Diagnóstico del código actual

- `main.make_pipeline` elige rutas mediante una sucesión de detectores y termina
  después de cada respuesta. Algunas rutas de palabras clave preceden a las rutas
  deterministas de órdenes simples.
- `LLMEngine.process` propone una acción del catálogo. Su historial guarda órdenes
  y respuestas JSON; no representa el estado completo de una tarea.
- `DesktopAgent.run` ya implementa un ciclo acotado de decisión, herramienta y
  observación. Su catálogo se limita a archivos y el estado se reinicia por llamada.
- El verificador actual comprueba la relación entre una acción y la frase inicial.
  Las acciones intermedias de una tarea necesitan además contexto del objetivo,
  resultados observados y alcance autorizado.
- La integración OpenCode actual llama directamente al proveedor de inferencia;
  usar un modelo de OpenCode y utilizar su agente con herramientas son integraciones
  diferentes. El CLI instalado permite sesiones y salida JSON.

## Arquitectura recomendada

Mantener Python y usar LangGraph como biblioteca local de coordinación. Su papel
será gestionar estado, transiciones, pausas y reanudaciones. Los modelos decidirán
los pasos dentro de los límites de cada tarea. Se reutilizarán comandos, voz,
gateway y memoria explícita existentes.

Flujo propuesto:

1. Resolver una orden inequívoca mediante las rutas rápidas existentes.
2. Para el resto, interpretar objetivo, contexto, necesidad de actualidad y alcance.
3. Decidir si responder, aclarar, usar herramientas o delegar a un especialista.
4. Ejecutar un paso, observar su resultado y verificar el avance.
5. Continuar, solicitar una decisión del usuario o entregar el resultado.

Las rutas rápidas solo deben aceptar peticiones completas que puedan resolver;
no deben capturar una parte de una pregunta, negación o tarea compuesta.

Un único coordinador conserva la tarea. Los especialistas se activan cuando son
necesarios; no se consultan los cuatro modelos en cada turno. Qwen realiza el
enrutamiento habitual y las tareas pequeñas. Una tarea compleja delega también
su planificación al especialista, evitando que el modelo pequeño tenga que
resolverla primero para poder delegar.

| Rol | Proveedor inicial | Trabajo |
|---|---|---|
| Asistente cotidiano | Qwen local | Conversación sencilla, explicaciones breves y uso acotado de herramientas comunes. |
| Desarrollo y tareas complejas | DeepSeek mediante OpenCode | Planificación extensa, creación de scripts, pruebas y tareas con varias dependencias. |
| Análisis de información local | Big Pickle mediante OpenCode, candidato | Examinar datos y archivos del alcance indicado, comparar y recomendar; herramientas de lectura. |
| Investigación actualizada | Gemini mediante gemdev | Noticias, documentación vigente e investigación con fuentes y fechas. |

Los roles y los modelos serán configurables por separado. Big Pickle se mantendrá
para análisis si las pruebas justifican su calidad y coste frente a DeepSeek.
El Qwen 1.5B actual debe evaluarse para conversación y herramientas; sus buenos
resultados como clasificador no demuestran capacidad de razonamiento general.

Big Pickle procesa en servidores del proveedor, aunque los archivos analizados
sean locales. Si se solicita procesamiento enteramente local, se usará Ollama
con capacidades ajustadas al equipo. No se enviará todo un directorio o historial
por defecto: cada especialista recibe solamente la información necesaria.

## Estado, herramientas y continuidad

- Estado por sesión y tarea: objetivo, restricciones, decisiones del usuario,
  pasos completados, observaciones relevantes, artefactos y siguiente paso.
- La memoria temporal de la tarea es distinta de los hechos personales explícitos
  guardados en SQLite. No convertir inferencias del agente en recuerdos personales.
- Los especialistas reciben un resumen compacto y referencias a artefactos. Las
  respuestas largas se conservan completas y se prepara una versión breve para voz.
- Las herramientas devuelven estado, datos y evidencia de éxito o error. El agente
  debe comprobar el resultado antes de declarar una operación completada.
- Presupuestos configurables de pasos, tiempo y contexto, con una escalada acotada
  cuando falle el modelo local. Un proveedor caído no genera reintentos indefinidos
  ni activa automáticamente un modelo de pago.
- Continuaciones como «explícalo», «haz la segunda opción» y «procede» se resuelven
  contra la tarea vigente. Las autorizaciones se vinculan al plan y su versión;
  cambiar de objetivo invalida la aprobación pendiente. No se decide por encontrar
  una palabra afirmativa dentro del texto libre.
- Las acciones ordinarias ya solicitadas no requieren una pregunta por cada paso.
  Pedir una recomendación no autoriza a aplicar cambios en el equipo.
- Reanudar una tarea no debe repetir efectos ya ejecutados. Guardar resultados y
  comprobar el estado real antes de reintentar una operación con efectos.

La interpretación será más flexible. La ejecución seguirá comprobando tipos,
catálogo, alcance y confirmaciones. Para tareas compuestas, el verificador añadirá
la evidencia de los pasos anteriores; no se desactivará globalmente el grounding.

OpenCode tendrá perfiles por tarea: análisis con lectura y desarrollo en una
carpeta de trabajo delimitada. Los scripts se prepararán y probarán en un entorno
aislado con entradas de prueba; una carpeta por sí sola no constituye aislamiento.
Aplicarlos a archivos reales requerirá el alcance solicitado y las confirmaciones
que correspondan. No se ampliará indiscriminadamente la terminal existente.

Gemini seguirá siendo una fuente informativa: su contenido no se convertirá en
acciones ejecutables. En esta entrega no se añadirá una cadena automática que
ejecute instrucciones obtenidas de páginas web.

## Comparación de orquestadores

| Alternativa | Evaluación para Limits |
|---|---|
| Python con coordinación propia | Viable y sin nueva biblioteca; obliga a mantener persistencia, pausas y recuperación propias. |
| Python + LangGraph | Recomendación: permite mezclar rutas deterministas con decisiones de modelos y conservar el estado entre turnos. Validar primero compatibilidad con Python 3.14. |
| n8n | Adecuado para futuras automatizaciones e integraciones externas. Incorporarlo al núcleo de voz añade otra aplicación y puentes con el código actual. |

n8n sí admite agentes que seleccionan herramientas. La recomendación de reservarlo
para integraciones se basa en la arquitectura de Limits, que ya dispone en Python
de audio, interrupciones, comandos y gateway; no en una supuesta incapacidad de n8n.

## Implementación propuesta, después de la aprobación

1. **Validar proveedores y establecer referencia.** Comprobar una interacción
   real de Qwen, OpenCode y gemdev; comparar DeepSeek y Big Pickle con un conjunto
   pequeño y reproducible de análisis. Verificar el protocolo de la versión local
   de OpenCode y las dependencias de LangGraph. El catálogo local ya lista ambos
   modelos, pero eso no prueba que la inferencia funcione. La documentación actual
   exige OpenCode para los modelos gratuitos: integrar su interfaz admitida,
   inicialmente CLI con salida JSON y sesiones, antes de considerar un servidor
   persistente. Si hay un bloqueo de acceso, documentarlo sin cambiar de plan de pago.
2. **Introducir estado de tareas y adaptadores.** Añadir el coordinador, contratos
   de resultado y adaptadores de proveedores detrás de una opción de configuración.
   Mantener la firma del pipeline compartido y un modo anterior para reversión.
3. **Evolucionar Qwen y el enrutamiento.** Separar los prompts de selección de rol,
   conversación y herramientas. Conservar las órdenes rápidas y probar negaciones,
   preguntas y objetivos compuestos. Añadir aclaración y escalada cuando corresponda.
4. **Generalizar el ciclo de trabajo.** Reutilizar el patrón de `DesktopAgent` para
   observar, actuar y verificar. Conectar los perfiles de análisis y desarrollo
   de OpenCode; incorporar las herramientas mínimas de lectura y creación de
   artefactos necesarias para los casos de aceptación. Gemini entrega investigación
   con fuentes y una respuesta completa separada de su versión hablada.
5. **Completar continuidad y voz.** Retomar una tarea después de una aclaración o
   aprobación, conservar el origen de las respuestas y admitir cancelación de
   tareas largas. Mantener un único dueño del turno y del audio; detener el trabajo
   debe invalidar resultados tardíos. Conservar las tres correcciones anteriores.
6. **Verificar y activar.** Ejecutar la suite, el corpus actual y los casos nuevos;
   medir tiempos y llamadas por rol. Activar el nuevo modo cuando cumpla los criterios
   y actualizar AGENTS.md y documentación para reflejar la arquitectura aprobada.

Zonas de cambio previstas: `main.py`, `modules/llm.py`, `modules/desktop_agent.py`,
`modules/gemini.py`, la interfaz de herramientas del executor y el verificador,
`config.py`, prompts y pruebas. Nuevos módulos pequeños para coordinación,
estado de tareas y adaptadores. La ubicación exacta se decidirá al implementar.

## Criterios de aceptación

- El corpus existente de 32 órdenes mantiene su resultado de referencia; las rutas
  rápidas no añaden llamadas al modelo. Medir latencia en el mismo equipo.
- Suite actual completa y regresiones específicas de memoria entre hilos,
  serialización del audio local/móvil y cancelación de confirmaciones antiguas.
- Al menos 40 escenarios nuevos: conversación, selección de especialista, análisis
  con evidencia, tareas de varios pasos, scripts, investigación, continuación,
  negaciones, ambigüedad, cancelación y errores del proveedor.
- Una tarea de análisis produce conclusiones sobre datos realmente consultados;
  una tarea de código entrega un archivo y evidencia de sus pruebas.
- «Analiza» y «recomienda» no provocan cambios. Una aprobación caducada o de otra
  tarea no autoriza acciones. Una reanudación no duplica una operación.
- La caída de un servicio se comunica con claridad y conserva el trabajo recuperable.
- Las pruebas automáticas usan dobles de proveedores; las comprobaciones reales
  son pocas y separadas para no depender de la red en toda la suite.

La mejora no incluye los otros hallazgos aplazados de la auditoría, visión de
pantalla, gestión general de escritorios ni despliegue de n8n. Tampoco incorpora
todos los comandos posibles: la capacidad se amplía mediante herramientas concretas.

## Fuentes consultadas

- [LangGraph: coordinación con estado y pasos deterministas o dirigidos por modelos](https://docs.langchain.com/oss/python/langgraph/overview).
- [LangGraph: persistencia y reanudación](https://docs.langchain.com/oss/python/langgraph/persistence).
- [OpenCode: modelos, acceso gratuito y condiciones de procesamiento](https://opencode.ai/v2/docs/console/models/).
- [n8n: agente con herramientas e integraciones](https://docs.n8n.io/integrations/builtin/cluster-nodes/root-nodes/n8n-nodes-langchain.agent/tools-agent).
- [Ollama: ciclo de llamadas a herramientas](https://docs.ollama.com/capabilities/tool-calling).

Comprobación local: lectura del pipeline, router y agente de archivos; ayuda de
`opencode` y listado de modelos. No se han ejecutado inferencias de validación ni
cambiado el código como parte de la preparación de este plan.
