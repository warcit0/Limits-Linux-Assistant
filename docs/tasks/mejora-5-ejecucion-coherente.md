# Mejora 5 · Ejecución y conversación coherentes

Estado: **planificado; pendiente de aprobación para implementar**.
Fecha: 2026-10-31.
Plan: [plan-mejora-5-ejecucion-coherente.md](../plan-mejora-5-ejecucion-coherente.md).

## Objetivo

Sustituir el recorrido cotidiano de decisiones redundantes por un agente con
herramientas verificables, objetivos completos y respuesta natural. Reparar el
contrato general; no añadir excepciones para frases individuales.

## Entregables y orden

- [ ] F1. Inventariar capacidades expuestas y definir contrato uniforme de resultados.
- [ ] F1. Adaptar handlers; None/fallo no significa solicitud exitosa. Verificar efectos.
- [ ] F2. Definir e implementar transición de autorización conservando límites y pruebas negativas.
- [ ] F2. Implementar ciclo único, objetivos compuestos y recibos vinculados a resultados.
- [ ] F2. Retirar propuesta local y jueces redundantes del nuevo recorrido cotidiano.
- [ ] F2. Separar fallo de proveedor, error de herramienta y delegación por complejidad.
- [ ] F3. Resolver entidades observadas y contexto pertinente; preguntar ante ambigüedad real.
- [ ] F4. Unificar presentación de respuestas, errores y aclaraciones sin estructuras internas.
- [ ] F4. Cancelar sin perder recibos ni repetir efectos; mantener voz/bloqueos compartidos.
- [ ] F5. Conservar trazas acotadas por turno, con duraciones y motivos sin secretos.
- [ ] F5. Validar los ocho escenarios del plan sin red y realizar una suite completa.
- [ ] F5. Una aceptación real de hasta seis turnos / veinte inferencias / tres minutos de proveedor.
- [ ] F5. Publicar resultados y pendientes; activar, reiniciar y comprobar servicio una vez.
- [ ] F5. Actualizar AGENTS, changelog y este índice; documentar reversión.

## Criterios de aceptación

- Consultas reciben datos pertinentes y no ejecutan mutaciones.
- Cada parte de una orden compuesta tiene resultado o pendiente explícito.
- Ningún destino inventado llega a un efecto; ninguna ausencia de respuesta acredita éxito.
- Ventanas y especiales se resuelven contra estado real; ambigüedades reciben una pregunta concreta.
- Ninguna salida de voz contiene diccionarios, direcciones internas o listas técnicas crudas.
- Cancelación/cuota/fallo posterior conservan efectos comprobados sin repetirlos.
- Confirmaciones, path guard, sandbox, privacidad y aislamiento Gemini siguen vigentes.
- Órdenes sencillas no activan cadenas de jueces ni escalados sin motivo registrado.
- Se publica número de inferencias y latencia por etapa, sin ocultar escenarios fallidos.

## Presupuesto y restricciones

Sin comparativas de modelos, sin pruebas manuales de micrófono y sin nuevas pruebas
reales tras agotar el presupuesto. Repetir comprobaciones solo por cambios o fallos
concretos. Preservar cambios existentes y memoria; sin commit ni release solicitado.

## Registro de trabajo

- 2026-10-31: plan y tarea creados a petición del usuario. Código y configuración sin cambios.
- Implementación: pendiente de aprobación.
- Validación: no iniciada.
- Activación: no iniciada.
