# Mejora 8 · Registro de implementación y revisión

Fecha: 2026-11-01, America/Costa_Rica. Base: `8b13f0e`.
Plan: [agente único](../plan-mejora-8-agente-unico.md).
Tarea: [checklist](../tasks/mejora-8-agente-unico.md).

## Cambios realizados

- Un modelo cotidiano fijado al abrir turno en AGENT_CONVERSATION_MODEL. El ciclo
  continúa con ese modelo tras consultas o efectos no finales. No utiliza el 1.5B
  como segundo ejecutor, ni encargo reformulado, ni inferencia de presentación.
- Retirados task/goal y helpers de presentación. Eliminado agent_executor.txt tras
  revisar que no quedan consumidores ejecutables. Campo encargo conservado solo
  para compatibilidad de lectura de estados anteriores.
- Atajos completos existentes restaurados; operaciones no disponibles pasan completas
  al modelo. Se conserva exclusión de peticiones compuestas/ambiguas en atajos.
- Lote final cierra desde recibos; lote no final continúa. Chat sin recibos tiene
  tipo_cierre=conversacion, no se registra como operación realizada. No se implementa
  un juez lingüístico que detecte toda afirmación falsa en texto.
- Límites configurables de seis decisiones y 30 segundos cotidianos, junto al límite
  existente de herramientas. Investigación/desarrollo/análisis conservan su presupuesto
  especializado. Sin expansión del presupuesto por fases o respaldos.
- Lectura HTTP de Ollama separada del consumidor mediante cola acotada; cancelación
  y plazo se comprueban mientras espera el primer byte. El lector no ejecuta herramientas
  ni cambia tareas. El socket puede permanecer hasta su timeout antes de cerrar;
  no se garantiza terminación inmediata del cálculo del servidor.
- Aprobación de lote sensible antes de cualquier efecto del lote, revisión/fecha/hash
  y datos de scripts revalidados al confirmar. Propuestas mixtas tienen artefacto
  privado revisable. Fallo para el resto; no revierte efectos previos automáticamente.
- Aviso único «Estoy con ello» tras 2,5 segundos, mediante el mismo FlujoVoz y dueño
  del micrófono. Temporizador cancelado/unido al entregar y en finally; progreso
  serializado con eventos Gemini. Texto temprano, lock y finalización WS conservados.
- Referencias de aclaración como datos anteriores; no conceden alcance ni permisos.
  No se modifican SQLite ni bóveda; no se cambian modelos, OAuth ni claves.

## Revisión realizada, sin pruebas

- Lectura de ramas de decisión, proveedor, ejecución, aprobación, persistencia y voz.
- Búsqueda de consumidores de prompt_ejecutor, presentar_resultados y
  devolucion_ejecutor: sin consumidores ejecutables restantes.
- AST de 10 archivos Python modificados, sin importar módulos del proyecto.
- git diff --check sin incidencias.
- Adaptados escenarios simulados de continuidad con el mismo proveedor, encargo
  antiguo rechazado, atajo sin inferencia, lote sensible sin efectos previos y cierre
  conversacional separado. Ajustados dobles HTTP por la lectura cancelable.
- **NO se ejecutaron tests, probes, inferencias de aceptación ni pruebas de voz.**
  No hay porcentajes de acierto ni tiempos nuevos de respuesta medidos.

## Límites que permanecen explícitos

La elección de herramienta y la cobertura siguen dependiendo del modelo. Qwen puede
clasificar una orden como chat o proponer una acción ajena; tipos y recibos no prueban
comprensión. No se anuncia ese problema como eliminado por el cambio arquitectónico.

El plazo se comprueba antes/después de herramientas: un handler síncrono ya iniciado
puede tardar hasta su timeout propio en devolver el control. No se desprenden efectos
con un hilo para liberar el turno dejando acciones antiguas en ejecución.

Después de una aprobación de lote no final se entregan recibos como parcial; no hay
replanificación automática de lo no aprobado. Una nueva petición puede continuar.
El APK previo necesita instalación en el teléfono para sus cambios de estados; esta
implementación no cambia Kotlin ni instala automáticamente una aplicación.

## Respaldo, servicio y publicación

Respaldo privado de configuración, permiso 0600:
`~/.limits/respaldos/agente-unico-20261101-175854/env-anterior`.
No se publica su contenido. No se modifica .env.

Antes de cargar la nueva versión, systemd mostró servicio failed, Result=timeout y
ExecMainStatus=9. Journal: parada a las 19:01:09 CST y SIGKILL a las 19:01:19 tras
TimeoutStopSec=10 s. No hay evidencia de que ese proceso estuviera usando este cambio;
no se atribuye el incidente a la versión nueva ni se afirma una causa adicional.

Servicio arrancado y después reiniciado con la versión final. Estado: active/running,
ExecMainStatus=0. Último arranque: 2026-11-01 21:33:32 CST; «Limits listo» a las
21:33:38 CST. Banner: asistente cotidiano qwen2.5:3b-instruct (local).
No se enviaron consultas al modelo para comprobarlo.

Publicación: implementación `fb7adf3`, push SSH a origin/main completado
(`8b13f0e..fb7adf3`). Este cierre documental se publica después en main.
Aceptación funcional: **pendiente del uso libre del usuario**.
