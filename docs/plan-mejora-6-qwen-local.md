# Mejora 6 — Qwen como asistente cotidiano local

Estado: implementación aprobada por «proceed» y activada en modo local. Aceptación funcional pendiente; ver docs/validaciones/mejora-6-qwen-local.md.

## Objetivo y contrato

Usuario → router determinista → Qwen local cuando no haya coincidencia completa → herramientas verificables → respuesta. El escritorio básico debe funcionar sin proveedores remotos. Spotify requiere su servicio de red, pero no un modelo remoto para interpretar órdenes.

El router conserva velocidad, variaciones habituales y comprobación de efectos. Solo consume peticiones completas e inequívocas; negaciones, referencias ambiguas y órdenes parcialmente reconocidas pasan completas a Qwen, sin efectos previos. Qwen también recibe conversación libre: no hace falta otro clasificador que determine previamente si es un comando.

Qwen observa, resuelve referencias, decide y encadena herramientas. La complejidad se determina por capacidades necesarias, no por cantidad de pasos ni por palabras desconocidas. No se escala automáticamente un fallo de herramienta, una aplicación desconocida ni una frase distinta.

## Fase 0 — Respaldo y base recuperable

Snapshot de código anterior al replanteamiento: rama `codex/respaldo-pre-qwen-2026-10-31`, commit `891d18aabfbcfcce898bad12aadaa0d2e9ad5256`. Sin historial antiguo para no arrastrar credenciales encontradas en un documento versionado. No constituye una versión estable validada.

El respaldo Git no incluye `.env`, credenciales, SQLite, bóveda, modelos, entorno Python, logs ni el repositorio externo gemdev. Antes de implementar, conservar localmente una copia privada de la configuración y registrar versiones de dependencias y gemdev, sin subir secretos. No restablecer ramas ni borrar memoria para revertir: recuperar código y configuración compatible conservando datos actuales.

## Fase 1 — Un único recorrido cotidiano

Modificar `main.py`, `modules/orchestrator.py`, `modules/agent_providers.py` y `config.py`. Sustituir el recorrido cotidiano remoto por Qwen/Ollama. Reutilizar executor, resultados, cancelación y estado; evitar añadir un cuarto coordinador paralelo a general_agent/coherent_agent/operational.

Conservar temporalmente el recorrido previo únicamente como reversión explícita, nunca como fallback oculto. Tras aceptación, retirar los caminos sustituidos y sus configuraciones. Un selector central de modo evita combinaciones contradictorias de flags. Especialistas conservan sus parejas actuales, fuera del camino cotidiano.

Criterio: una petición básica que no encaje en un atajo llega a Qwen, incluso si todos los proveedores remotos están indisponibles. Si Ollama falla, informar del fallo local sin enviar la conversación a la nube.

## Fase 2 — Contexto y preparación de Qwen

Preparar instrucciones y ejemplos diversos; esto no es ajuste de pesos. Empezar con el Qwen instalado, sin asumir que 1,5B basta ni cambiar modelos silenciosamente. Una evaluación posterior con consentimiento determinará si hace falta mayor tamaño; el corpus de comandos antiguo no demuestra capacidad de agente.

Contexto fijo breve: identidad, política de acciones, esquema de decisiones y catálogo por familias. Contexto dinámico: petición íntegra, objetivo pendiente, referencias recientes y memoria pertinente. Observaciones del escritorio y herramientas adicionales se consultan cuando hacen falta; nunca enviar todo el historial, bóveda o catálogo completo por defecto.

Mantener la ventana actual de 8192 inicialmente; medir tamaño de entrada y reservar salida sin truncar instrucciones. Si no cabe, reducir observaciones/historial antiguo conservando solicitud, permisos y resultados pendientes. No atribuir al prompt cambios automáticos de caché o de capacidad.

Decisión estructurada: responder, consultar, actuar, pedir aclaración o delegar con motivo. Normalmente una decisión para acciones simples; pasos dependientes esperan la observación anterior. Límites configurables de tiempo y pasos, una reparación de formato como máximo y detección de bucles. Un efecto incierto se observa antes de cualquier reintento.

## Fase 3 — Herramientas generales y destinos observados

Reutilizar `capability_tools.py`, `task_tools.py`, `command_result.py` y handlers. Resolver aplicaciones desde entradas instaladas y ventanas reales, proyectos desde PROJECT_ROOTS, espacios normales 1–10 y especiales con su semántica propia. APP_MAP queda como alias, no como universo de aplicaciones posibles.

Las referencias «esto», «la otra», «lo que veo» necesitan entidades observadas y vigencia por turno. Varios candidatos plausibles → pregunta concreta. Actualizar observación antes de cerrar/mover una ventana cuyo estado pudo cambiar.

Resultados comunes: completado, fallido, sin verificar, con evidencia y resumen hablado. Aperturas esperan de forma acotada la ventana/proceso apropiado; solicitud enviada no implica éxito. Los errores conservan causa útil sin exponer secretos.

La autorización se valida localmente contra la petición, capacidades, parámetros y alcance. No introducir un juez remoto por paso. Diseñar explícitamente cómo expresar permisos para órdenes compuestas: una cita o confianza del modelo no basta. Mantener tipos, catálogo de herramientas, grounding no léxico, rutas observadas, confirmaciones peligrosas y sandbox. Si el alcance no puede establecerse, aclarar; nunca abrir shell arbitrario.

## Fase 4 — Spotify mediante MCP

Seleccionar servidor durante implementación tras revisar su documentación vigente: mantenimiento, licencia, OAuth, permisos, transporte y operaciones realmente disponibles. No se ha seleccionado ni instalado ninguno; las herramientas del chat no se transfieren a Limits.

Adaptador acotado: búsqueda, biblioteca, reproducción actual, dispositivos y control, según soporte real. Validar requisitos de cuenta, restricciones de reproducción y permisos antes de prometer una operación. Credenciales locales fuera de Git; timeout, cancelación y manejo de renovación OAuth. Allowlist de herramientas y esquemas, sin ejecutar instrucciones contenidas en metadatos musicales.

Conservar control local MPRIS para operaciones compatibles cuando MCP falle. No convertir un fallo de Spotify en una delegación a un modelo remoto. Verificar reproducción/dispositivo; cambios de biblioteca o playlists solo por petición explícita.

## Fase 5 — Especialistas y conversación

Qwen deriva desarrollo de código/scripts a DeepSeek, análisis extenso a Big Pickle y actualidad/investigación a Gemini. Conservar respaldos por rol, presupuesto y cancelación. «Solo local» prohíbe envío remoto. Gemini permanece informativo: sus respuestas nunca son órdenes ejecutables.

Conversación natural sin fingir efectos: responder saludos, aclarar ambigüedad y ofrecer un siguiente paso cuando sea útil, sin preguntar sistemáticamente tras cada orden. Voz progresiva, SpeechController, gateway y widget conservan su ciclo y bloqueo. Una sola fuente de voz; stop cancela trabajo y resultados tardíos.

## Fase 6 — Migración, limpieza y aceptación

Inventariar imports, lanzadores, servicios, documentación y pruebas antes de retirar scripts. Eliminar solo utilidades sustituidas o reproducciones temporales sin consumidores; documentar sustituto y commit recuperable. No borrar modelos, entornos, memoria, servicios ni scripts de salud/instalación por parecer voluminosos. Los scripts actuales ocupan aproximadamente 264 KB: no hay evidencia de saturación por su tamaño.

Preferir una suite automática consolidada a nuevos scripts probe por mejora. No ejecutar tests, probes, modelos ni pruebas de voz durante la preparación de este plan. La restricción vigente de no correr tests se mantiene hasta autorización explícita; preparar casos no equivale a ejecutarlos. El usuario prueba libremente por voz, sin prueba manual guiada obligatoria.

Casos de aceptación a preparar: equivalencia de variaciones; negación y orden compuesta sin ejecución parcial del router; cierre de ventana activa; app instalada fuera de APP_MAP; referencia ambigua; proyecto observado; fallo remoto sin impacto local; error de herramienta sin repetición de efecto; Spotify sin dispositivo/autorización; cancelar y confirmar con revisión vigente; aislamiento de sesiones y memoria.

Criterios: cero éxito declarado sin evidencia para efectos; cero envío remoto cotidiano; cero repetición automática de efectos inciertos; preservación de negaciones/confirmaciones. Medir tiempo hasta primer audio, inferencias y resultado real cuando se autorice; no fijar promesas de latencia sin medición. Tests con modelos simulados acreditan contratos, no comprensión real de Qwen. La aceptación por voz permanece pendiente hasta valoración del usuario.

## Entrega y reversión

Implementar por fases con cambios acotados, explicar qué cambia y no marcar estable solo por tests. Antes de activar, documentar selector nuevo, configuración previa y procedimiento de recuperación. Revertir código no revierte automáticamente efectos ni datos de memoria. El usuario autorizó implementar con «proceed». La restricción de no ejecutar pruebas permanece vigente.
