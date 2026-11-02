# Task · Mejora 8: asistente cotidiano único

Plan: [diseño detallado](../plan-mejora-8-agente-unico.md).
Fecha: 2026-11-01. Estado: **implementada, activa y publicada; aceptación funcional pendiente**.
Base: `8b13f0e`. Sustituye el recorrido cotidiano de mejora 7 cuando se implemente;
no declara la versión anterior aceptada. Activación registrada en el informe.

## Restricciones obligatorias

- No ejecutar tests, probes, inferencias de aceptación ni pruebas manuales guiadas.
- Revisión estática/sintaxis y arranque permitidos; uso real por cuenta del usuario.
- Un modelo cotidiano; no añadir clasificador, juez o narrador separado.
- No reglas nuevas por frases; no reducir protección técnica para ocultar errores.
- No cambiar modelos ni instalar dependencias en esta mejora.
- Preservar memoria, especialistas, sandbox, aprobaciones, recibos y voz interrumpible.
- No guardar secretos ni adjuntos del usuario en commits. No PR: main según permiso existente.

## A. Preparación y decisiones

- [x] Contrastar arquitectura con código y último turno fallido.
- [x] Documentar garantías técnicas y límites semánticos del modelo.
- [x] Crear plan detallado con alcance, contratos, fases, aceptación y reversión.
- [x] Obtener aprobación de implementación mediante el siguiente proceed.
- [x] Registrar HEAD/estado del árbol antes de modificar; conservar trabajo ajeno.
- [x] Respaldar configuración privada y registrar solo ruta/fecha, nunca contenido secreto.
- [x] Inventariar consumidores de fases, `encargo`, `devolucion_ejecutor` y presentación.

Salida de fase: contrato entendido y base reversible, sin activación parcial.

## B. Contrato y modelo único

- [x] Retirar `task`/`goal` del esquema conversacional y sus instrucciones.
- [x] Mantener command/chat/clarify/delegate con tipos y parámetros reales.
- [x] Resolver AGENT_CONVERSATION_MODEL una vez para todas las decisiones cotidianas.
- [x] Mantener OLLAMA_MODEL para modos históricos, sin alternancia en conversacional.
- [x] Conservar petición original completa e inmutable en cada decisión/delegación.
- [x] Unificar prompt cotidiano; retirar prompt ejecutor solo si no tiene consumidores.
- [x] Eliminar fases conversación→ejecutor→presentación del recorrido activo.
- [x] Eliminar selección de modelo basada en banderas de presentación.
- [x] Registrar modelo efectivo y métricas reales, sin inferirlos del rol.

Salida de fase: no existe salto cotidiano entre 3B y 1.5B ni objetivo reformulado.

## C. Ciclo de herramientas y resultados

- [x] Habilitar atajos completos existentes en conversacional mediante el mismo executor.
- [x] Asegurar que un match parcial no ejecuta ni fragmenta una petición compuesta.
- [x] Mantener hasta seis operaciones independientes por lote, ejecución secuencial.
- [x] Prevalidar lote completo antes del primer efecto y revalidar cada destino al ejecutar.
- [x] Pausar lote sensible antes de mutar; vincular aprobación a revisión exacta.
- [x] Continuar complete=false con observaciones y el mismo modelo, incluso tras efectos.
- [x] Cerrar complete=true desde recibos, sin inferencia de presentación.
- [x] Parar lote ante fallo e informar efectos previos y pasos sin ejecutar.
- [x] Separar conversación contestada de operación completada en estado/consumidores.
- [x] No acreditar éxito operativo con texto libre o None.
- [x] Conservar recibos tras cancelación tardía y evitar repetición de efectos inciertos.
- [x] Admitir consulta negativa verificada como cierre sin efecto cuando corresponda.
- [x] Conservar política por capacidad, rutas observadas, tipos/enums y sandbox.
- [x] Mantener delegación especializada y aislamiento de salida Gemini.

Salida de fase: una herramienta puede alimentar el siguiente paso sin otro agente;
un recibo demuestra el efecto, no la comprensión universal de la petición.

## D. Contexto, límites y cancelación

- [x] Reutilizar diálogo breve y recuerdos confirmados sin objetivos antiguos activos.
- [x] Mantener referencias de aclaraciones con procedencia y revalidación al actuar.
- [x] Preservar petición/recibos/aprobaciones al acotar contexto; no cortar JSON.
- [x] Reutilizar límite de herramientas y añadir límites faltantes de decisiones/plazo.
- [x] Aplicar deadline monótono común a inferencias, corrección y herramientas.
- [x] Máximo una corrección de formato; error de servidor no dispara otra cadena.
- [x] No repetir lecturas inútiles ni efectos anteriores dentro del turno.
- [x] Invalidar propuestas al cambiar tarea, cancelar, caducar o reiniciar.
- [x] Descartar resultados tardíos; comprobar todos los caminos de salida.

Salida de fase: un fallo termina de forma explícita dentro de un presupuesto acotado.

## E. Voz y entrega

- [x] Reutilizar SpeechController y cola única para un aviso de espera a los 2,5 s.
- [x] Cancelar aviso si llega respuesta/audio, cancelación o cierre antes del umbral.
- [x] Emitir progreso solo desde estado real; no hablar JSON o intenciones como hechos.
- [x] Mantener conversación natural sin pregunta automática después de cada orden.
- [x] Conservar texto temprano, ids WS y turn_finished en cierres y excepciones.
- [x] Mantener lock hasta cerrar audio/escucha; no crear segundo reproductor/micrófono.
- [x] Verificar por revisión de código que eventos antiguos no afectan turnos nuevos.
- [x] Documentar que el APK previo necesita instalación; no asumir móvil actualizado.

Salida de fase: la espera tiene señal honesta y no introduce carreras de audio.

## F. Revisión y retirada de código

- [x] Revisar imports/referencias antes de retirar helpers/ramas sin consumidores.
- [x] Conservar módulos históricos necesarios para otros modos y especialistas.
- [x] Adaptar escenarios con dobles de conversación, lotes, cancelación y gateway.
- [x] Dejar esos tests preparados y explícitamente NO ejecutados.
- [x] Revisar prompt/esquema/contratos, todos los cierres y presupuesto compartido.
- [x] Revisar falso chat inicial como límite abierto, sin anunciar detección infalible.
- [x] Comprobar sintaxis de archivos cambiados sin importar ni ejecutar el asistente.
- [x] Ejecutar git diff --check y revisar diff acotado.
- [x] Documentar líneas retiradas/añadidas y justificar nuevos componentes si los hay.
- [x] Actualizar AGENTS, CHANGELOG y referencias vigentes sin borrar historia útil.
- [x] Crear informe de implementación/validación con comandos realmente realizados.

Salida de fase: revisión técnica trazable; ninguna casilla equivale a prueba funcional.

## G. Activación y entrega, después de aprobación

- [x] Revisar staged explícito; excluir .env, logs, modelos y .codex-attachments.
- [x] Registrar commit de implementación y respaldo anterior.
- [x] Activar conjunto completo; servicio encontrado failed por timeout de parada. Arranque y reinicio final registrados en el informe.
- [x] Verificar estado y mensaje de listo mediante logs filtrados, sin consulta al modelo.
- [x] Push SSH directo a main completado: implementación fb7adf3, desde 8b13f0e.
- [x] Entregar archivos cambiados, límites pendientes y procedimiento de reversión.
- [x] Confirmar que memoria/bóveda permanecen intactas y no se restauran aprobaciones.

Salida de fase: implementación activa, si se autorizó; servicio iniciado no significa
que el modelo haya superado aceptación por voz.

## H. Aceptación funcional pendiente del uso libre

- [ ] Revisar conversaciones reales que el usuario señale, sin generar pruebas propias.
- [ ] Separar éxito de atajos y de decisiones de Qwen.
- [ ] Comprobar ausencia de segundo modelo/narrador en trazas cotidianas reales.
- [ ] Registrar acciones omitidas/no solicitadas, cierres falsos y errores técnicos.
- [ ] Medir tiempos por etapa de turnos reales, sin prometer objetivos no alcanzados.
- [ ] Si persisten errores semánticos, presentar evidencia para decidir modelo adecuado.
- [ ] Obtener aceptación del usuario; mantener pendiente hasta que realmente ocurra.

## Registro de esta tarea

2026-11-01: plan aprobado e implementación realizada. Revisión AST de 10 archivos,
sin imports ni pruebas ejecutadas. Modelo y memoria personal conservados. Respaldo
privado: ~/.limits/respaldos/agente-unico-20261101-175854/env-anterior.
Detalles, límites y activación: [informe](../validaciones/mejora-8-agente-unico.md).
La aceptación por voz permanece pendiente.
