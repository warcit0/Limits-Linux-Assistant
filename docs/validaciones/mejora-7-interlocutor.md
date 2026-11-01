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
