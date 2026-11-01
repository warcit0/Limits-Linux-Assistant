# Mejora 1 · Asistente por objetivos y especialistas

**Estado:** completada, verificada y activada (2026-10-31). Limitaciones de disponibilidad de proveedores documentadas en el informe.
**Dependencias:** comandos y grounding actuales; correcciones de memoria entre
hilos, bloqueo de audio y confirmaciones antiguas conservadas.
**Plan:** [Orquestación por objetivos y especialistas](../plan-mejora-1-orquestacion-agentes.md).

## Objetivo y criterio de cierre

Limits entiende un objetivo, responde o elige el especialista adecuado, consulta
herramientas, verifica resultados y conserva el contexto para continuar la tarea.
Puede analizar y recomendar sin ejecutar cambios, preparar scripts probados y
aplicar un plan concreto cuando tenga la autorización correspondiente.

La tarea se cierra cuando estén completos los seis bloques, la suite pase, el
corpus actual conserve sus 32/32 aciertos y se validen al menos 40 escenarios
nuevos. Cada bloque debe dejar evidencia de su resultado antes de marcarse.

## Alcance y decisiones

| Componente | Responsabilidad |
|---|---|
| Python + LangGraph | Coordinar estado, pasos, pausas y reanudaciones; reutilizar voz, gateway y comandos. |
| Qwen local | Conversación sencilla, tareas comunes y selección inicial de especialista. |
| Desarrollo | OpenCode DeepSeek → NVIDIA DeepSeek → Groq GPT-OSS 120B. |
| Análisis | OpenCode Big Pickle → NVIDIA Super → Bolt → Groq GPT-OSS 120B. |
| Gemini mediante gemdev | Investigación actualizada con fuentes y fechas; salida informativa. |

La aclaración del usuario (2026-10-31) mantiene los principales de OpenCode;
NVIDIA se usa solo si falla el principal correspondiente, por ejemplo por cuota
agotada. No hay alternancia entre desarrollo y análisis. Los fragmentos
proporcionados a estos especialistas se procesan en servidores remotos. Una petición de procesamiento
enteramente local utiliza Ollama, con sus capacidades y limitaciones comprobadas.

Fuera de alcance: otros hallazgos aplazados de la auditoría, visión de pantalla,
gestión de escritorios, despliegue de n8n y ejecución automática de instrucciones
procedentes de páginas web. No se consultan todos los especialistas en cada turno.

## Checklist de implementación

### 1. Validación de proveedores y referencia inicial

- [x] Registrar la referencia actual de suite, corpus y latencias en el mismo equipo.
- [x] Probar Qwen con conversación, selección de rol y herramientas sencillas.
- [x] Verificar compatibilidad de LangGraph con el entorno Python 3.14 y registrar
      la dependencia y versión elegidas en el archivo de dependencias del proyecto.
- [x] Validar el contrato del OpenCode instalado: CLI, salida JSON, selección de
      modelo, sesiones, errores, timeout y cancelación.
- [x] Ejecutar una comprobación real de los dos modelos NVIDIA y gemdev. Distinguir
      un modelo listado de un proveedor que realmente responde.
- [x] Comprobar acceso de principales y validar respaldos operativos por rol con casos pequeños:
      calidad de conclusiones, evidencia utilizada, latencia y límites observados.
      OpenCode y NVIDIA DeepSeek no se presentan como disponibles cuando falla su acceso.
- [x] Documentar la selección por rol y los fallos de acceso sin activar un modelo
      de pago como sustitución automática.

**Entregable:** referencia reproducible y matriz de proveedores verificados. Si
falla un proveedor, continuar el trabajo independiente con dobles de prueba,
manteniendo pendiente su validación real y sin presentarlo como disponible.
Con la incorporación de respaldos solicitada por el usuario, el cierre funcional
del rol exige una cadena real que complete la aceptación; no exige recuperar
la cuota de un servicio externo ni acredita calidad de un candidato inaccesible.

### 2. Estado de tareas, coordinación y adaptadores

- [x] Definir contratos de entrada, decisión y resultado: sesión/tarea, objetivo,
      restricciones, especialista, observaciones, artefactos y estado de ejecución.
- [x] Implementar el coordinador con estados de trabajo, espera de aclaración o
      aprobación, finalización, cancelación y error recuperable.
- [x] Conservar el contexto entre turnos y persistir lo necesario para recuperar
      tareas sin convertir inferencias del agente en recuerdos personales.
- [x] Crear adaptadores de Ollama, NVIDIA, OpenCode opcional y gemdev con errores y resultados
      normalizados; conservar texto completo y origen de cada respuesta.
- [x] Añadir selección de modo anterior/nuevo y presupuestos de pasos, tiempo y
      contexto; declarar toda variable nueva solamente en `config.py`.
- [x] Preservar el contrato de `make_pipeline`, incluido el callback de respuesta
      bajo el bloqueo compartido, para voz local y móvil.
- [x] Enviar a cada especialista solo el contexto y las herramientas necesarios;
      conservar resultados extensos como artefactos con referencias.

**Entregable:** una tarea puede conservarse y retomarse usando proveedores simulados,
y el modo anterior sigue disponible para reversión.

### 3. Qwen conversacional y enrutamiento por objetivos

- [x] Separar los prompts y contratos de selección de rol, conversación y uso de
      herramientas; validar sus salidas y acotar su tamaño.
- [x] Permitir responder, pedir aclaración, usar herramientas o delegar según el
      objetivo, contexto, complejidad y necesidad de información reciente.
- [x] Respetar la elección explícita del modelo por el usuario cuando esté disponible.
- [x] Mantener las rutas rápidas sin llamadas adicionales al modelo; deben reconocer
      órdenes completas y evitar capturar preguntas, negaciones o tareas compuestas.
- [x] Delegar también la planificación compleja al especialista. Una salida inválida
      de Qwen conduce a una aclaración o escalada acotada, nunca a ejecución directa.
- [x] Mantener el presupuesto del prompt existente y definir límites separados para
      los nuevos prompts, sin reducir el contexto del router sin volver a medirlo.

**Entregable:** Limits distingue conversación, ejecución, análisis e investigación
sin exigir que el usuario nombre un modelo o una acción del catálogo.

### 4. Especialistas y ciclo de ejecución verificada

- [x] Generalizar el patrón de `DesktopAgent`: decidir un paso, ejecutar una
      herramienta, observar el resultado y continuar o responder.
- [x] Normalizar resultados de herramientas con estado, datos y evidencia, adaptando
      los handlers existentes sin romper sus consumidores actuales.
- [x] Extender el grounding para comprobar objetivo, alcance y evidencia de pasos
      anteriores; mantener validación de tipos, catálogo y parámetros.
- [x] Conectar los especialistas NVIDIA con JSON validado, prioridad OpenCode primero y
      respaldo NVIDIA independiente por rol, sin alternancia.
- [x] Incorporar las herramientas mínimas para consultar archivos observados y
      producir los artefactos requeridos por los casos de aceptación.
- [x] Implementar preparación y pruebas de scripts en un entorno realmente aislado
      con datos de prueba; documentar y comprobar sus límites antes de ejecutarlos.
- [x] Aplicar cambios sobre archivos reales solo dentro del alcance autorizado y
      con las confirmaciones correspondientes; no ampliar la terminal sin límites.
- [x] Comprobar el resultado antes de declarar una tarea completada. Registrar
      efectos y verificar el estado real antes de reintentar para evitar duplicados.
- [x] Mantener Gemini como salida informativa con fuentes y fechas; conservar su
      artefacto completo y preparar una respuesta hablada breve por separado.
- [x] Acotar pasos y reintentos; comunicar fallos conservando el trabajo recuperable.

**Entregable:** análisis sustentado en archivos consultados, scripts entregados con
evidencia de pruebas e investigación documentada, sin mezclar información con órdenes.

### 5. Continuidad, autorizaciones, cancelación y voz

- [x] Resolver «explícalo», «la segunda opción» y «procede» contra la tarea vigente;
      aclarar referencias ambiguas en vez de seleccionar un plan arbitrario.
- [x] Vincular cada aprobación a sesión, tarea, plan y versión; invalidarla al cambiar
      de objetivo. Resolver confirmación/cancelación mediante decisiones explícitas,
      nunca buscando palabras afirmativas dentro del texto libre.
- [x] Distinguir una recomendación de una orden de aplicar cambios; ejecutar los
      pasos ordinarios ya solicitados sin preguntar de nuevo por cada uno.
- [x] Cancelar tareas largas y sus subprocesos cuando corresponda; descartar resultados
      tardíos y no reanudar automáticamente una operación cancelada.
- [x] Mantener un único dueño del turno y del audio, con interrupción móvil accesible
      sin esperar al bloqueo; conservar el origen para la selección de voz.
- [x] Verificar que ni sesiones distintas ni conversaciones con Gemini recuperan
      autorizaciones antiguas o mezclan el contexto de las tareas.
- [x] Conservar las regresiones de SQLite entre hilos, voces simultáneas y confirmaciones.

**Entregable:** una tarea puede aclararse, aprobarse, continuarse o cancelarse por
texto, voz local y móvil sin solapamientos ni acciones pendientes inesperadas.

### 6. Pruebas, activación y documentación

- [x] Añadir al menos 40 escenarios con expectativas de comportamiento observables:

  | Familia | Mínimo | Comportamiento comprobado |
  |---|---:|---|
  | Conversación y tareas comunes | 6 | Explicar y actuar con herramientas apropiadas. |
  | Selección de rol | 6 | Elegir especialista; respetar órdenes rápidas, negaciones y ambigüedad. |
  | Análisis | 6 | Conclusiones apoyadas en evidencia, sin modificar los datos analizados. |
  | Scripts y ejecución compuesta | 6 | Artefacto, pruebas y comprobación del resultado. |
  | Investigación | 4 | Información actualizada con fuentes y errores explícitos. |
  | Continuidad y autorizaciones | 8 | Retomar, aclarar, cancelar e invalidar aprobaciones antiguas. |
  | Fallos y recuperación | 4 | Proveedores caídos, límites y prevención de efectos duplicados. |

- [x] Usar dobles de proveedores en la suite automática y separar las comprobaciones
      reales, pequeñas y reproducibles, que necesitan servicios externos.
- [x] Ejecutar compilación y suite completa; referencia previa: 272 pruebas aprobadas,
      que debe volver a comprobarse durante la implementación.
- [x] Medir el corpus existente: 32/32 aciertos, sin llamadas adicionales en rutas
      rápidas, y registrar p50/p95 frente a la referencia del primer bloque.
- [x] Ejecutar la sonda de grounding y pruebas de texto de los comportamientos nuevos.
- [x] Validar el recorrido completo de aceptación descrito debajo y las regresiones
      de memoria, voz y confirmaciones, incluyendo concurrencia local/móvil.
- [x] Registrar tiempos, llamadas y límites por rol; no activar un rol que no haya
      superado sus casos de aceptación o presentarlo como disponible si falló su acceso.
- [x] Verificar reversión al modo anterior y activar el nuevo modo tras cumplir los criterios.
- [x] Actualizar `AGENTS.md`, documentación de configuración y `CHANGELOG.md` para
      reflejar lo implementado; documentar los respaldos NVIDIA
      y la nueva coordinación sin conservar reglas contradictorias sobre esos cambios.
- [x] Reiniciar `limits.service` si estaba activo y comprobar el funcionamiento final.
- [x] Añadir evidencias, marcar este documento y actualizar el índice solo al completar
      todos los bloques; registrar cualquier pendiente como pendiente.

**Entregable:** implementación verificada, activación reversible y documentación coherente.

## Recorrido de aceptación de extremo a extremo

1. «Revisa esta carpeta y recomienda cómo organizarla»: consultar archivos reales
   del alcance indicado y ofrecer una propuesta; ningún archivo se modifica.
2. «Explícame la segunda opción»: conservar contexto y explicar la alternativa correcta.
3. «Prepara un script para esa opción»: entregar un archivo y comprobarlo con una
   copia temporal, sin aplicar cambios sobre los originales.
4. «Procede con esa propuesta»: resolver el plan vigente y su autorización, ejecutar
   dentro del alcance aprobado y comprobar el resultado real.
5. Repetir con cancelación, cambio de objetivo y caída del proveedor: no ejecutar
   aprobaciones obsoletas, no duplicar efectos y comunicar el trabajo pendiente.

## Zonas de cambio y evidencia

Zonas previstas: `main.py`, `config.py`, `modules/llm.py`, `modules/desktop_agent.py`,
`modules/gemini.py`, interfaces del executor y grounding, prompts y tests. Añadir
módulos pequeños para coordinación, estado y adaptadores; su división definitiva
se decide al implementar. Reutilizar `SpeechController` para la salida hablada.

Registrar aquí, durante la ejecución, los archivos de evidencia de cada bloque y
las decisiones justificadas. No guardar credenciales, contenido privado ni logs
completos de conversaciones en los documentos del proyecto.

| Bloque | Evidencia | Estado |
|---|---|---|
| 1 · Proveedores y referencia | [Informe](../validaciones/mejora-1/informe.md) | Acceso comprobado; respaldos operativos validados |
| 2 · Coordinación y estado | `modules/task_state.py`, `modules/orchestrator.py`, suite | Implementado y probado |
| 3 · Qwen y enrutamiento | Corpus de 40 rutas y 32 órdenes | Implementado y medido |
| 4 · Especialistas y ejecución | `tests/test_objectives.py`, `tests/test_nvidia.py`, informe | Aceptación completa con respaldos operativos |
| 5 · Continuidad y voz | Suite: sesiones, cancelación, gateway y sandbox | Suite y micrófono real verificados |
| 6 · Validación y activación | [Informe](../validaciones/mejora-1/informe.md) | 405 pruebas; modo activo y reversible |

Cierre: recorrido real de recomendación → explicación de alternativa → script probado
→ aprobación → aplicación verificada completado; Gemini autenticado con dos fuentes
oficiales comprobadas; micrófono real con cancelación durante la espera verificado.
El servicio queda activo con `AGENT_ENABLED=true`; reversión mediante `false` y reinicio.
Los fallos de acceso de OpenCode, NVIDIA DeepSeek y GLM se documentan como límites
externos: no se atribuyen a saldo agotado sin evidencia ni se ocultan como éxitos.
