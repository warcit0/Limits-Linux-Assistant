# Tarea · Mejora 7: interlocutor y ejecución

Plan: [interlocutor](../plan-mejora-7-interlocutor.md).
Respaldo previo enviado a main: `8c0cfc1`.

- [x] Contrato conversacional, llamadas directas y encargos al ejecutor existente.
- [x] Roles locales independientes, con modelos instalados y sin respaldo cloud cotidiano.
- [x] Diálogo reciente, pregunta pendiente y recuerdos relevantes por sesión.
- [x] Política por capacidades, sin permisos por verbos en el modo nuevo.
- [x] Mantener validación técnica, alcance, confirmaciones, sandbox y recibos.
- [x] Cierres cotidianos del interlocutor y voz de intención durante encargos.
- [x] Preparar regresiones simuladas, sin ejecutarlas.
- [x] Revisión estática: AST de 11 archivos Python y diff sin errores. Servicio activo y listo el 2026-11-01 a las 16:23 CST.
- [ ] Aceptación funcional por voz y latencia: pendiente del usuario.

No contar una sintaxis válida o un servicio arrancado como aceptación funcional.

### Seguimiento del diagnóstico de los turnos reales

- [x] Entrega sin catálogo ni nuevas acciones; fallback a recibos sin reintento.
- [x] Citas por operación, distinción de lote directo y tarea abierta.
- [x] Foco sin lanzamiento implícito y un solo contrato conversacional observado.
- [x] Registro privado de métricas de inferencia para los turnos reales.
- [x] Regresiones simuladas adaptadas y preparadas, sin ejecutar.
- [ ] Aceptación funcional y latencia por el usuario; no correr pruebas.

### Simplificación tras los turnos reales

- [x] Retirar la cita literal obligatoria y sus rechazos por corregir el dictado.
- [x] Cierre directo de efectos concretos, sin nueva inferencia ni avances libres.
- [x] Compactar prompt/contexto y retirar objetivos antiguos reinyectados como activos.
- [x] Texto progresivo antes de finalizar audio; bloqueo conservado hasta el cierre.
- [x] Estados WS por turno y corrección de estados Android en Main.
- [x] Regresiones preparadas/adaptadas, NO ejecutadas.
- [x] Compilar APK debug con assembleDebug --offline, sin tests.
- [ ] Instalar APK Android actualizado en el teléfono; no se instaló automáticamente.
- [ ] Aceptación y tiempos mediante turnos reales del usuario, sin pruebas guiadas.
