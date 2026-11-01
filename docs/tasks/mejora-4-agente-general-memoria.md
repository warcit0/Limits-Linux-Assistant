# Agente general y memoria compartida

Autorizado por el usuario: 2026-10-31. No resolver mediante más frases especiales.
Objetivo: interpretación semántica, catálogo general, recuperación ante fallos,
evidencia por turno, diálogo independiente del objetivo, SQLite + Obsidian.

Restricciones: mantener confirmaciones, grounding, sandbox de scripts, cancelación,
separación Gemini/acciones, privacidad y cambios anteriores. Sin prueba manual de micro.

Estado inicial: dos conversaciones fallidas auditadas; segunda con una orden
operativa de siete. El permiso léxico elimina herramientas y el agente nuevo no
recupera memoria. La bóveda nueva irá en ~/Documentos/Limits-Memoria.

Pendientes: implementar, pruebas generales/negativas/memoria, aceptación local y
comparación de proveedores con presupuesto acotado, registro de bóveda, reinicio y salud.

## Avance de implementación (sin desplegar todavía)

- Nuevos modules/general_agent.py, capability_tools.py, knowledge.py y prompts
  agent_semantic_router/worker. Opt-in config AGENT_SEMANTIC, KNOWLEDGE_ENABLED;
  .env todavía NO activado. Rutas legacy intactas para reversión.
- Selección semántica de objetivos y herramientas top-k, descubrimiento por
  capacidades, contratos de tipos derivados, llamadas nativas Ollama y esquemas
  específicos por herramienta para NVIDIA/Groq. Diálogo separado del objetivo.
- Autorización semántica ligada a objetivo/revisión/acción/parámetros antes de
  efectos; mantiene firmas/enums/exclusiones/pathguard y confirmaciones. Evidencia
  semántica reemplaza solo la dependencia léxica de dominio, no los demás límites.
- Verificador separado de cobertura usa recibos realmente verificados. No contar
  herramientas como objetivos: una herramienta puede cubrir varios resultados.
  Síntesis analítica permite texto solo tras revisión contra evidencia.
- Memoria mismo SQLite, FTS, procedencia/revisión/caducidad, dirty queue,
  sincronización Markdown, conflictos, borrados/época global para invalidar contexto,
  candidatos sin consolidar. Protección de enlaces/redacción de secretos.
- Bóveda creada y registrada en ~/Documentos/Limits-Memoria. Respaldo SQLite y
  registro de Obsidian privado en ~/.limits/respaldos. URI de Inicio enviada a Obsidian.
- SystemCommands volumen/brillo verifican valor posterior; get_current_song
  distingue pausado de sonando; workspaces especiales observados se verifican.
- Suite previa completa 487 OK (antes de las últimas pequeñas revisiones).
- Aceptación real scripts/probe_general_live.py --live pasó 5/5 con Groq: ajuste
  volumen, disco, recordar/recuperar/olvidar en memoria aislada; volumen restaurado.
  Informe logs/probe_general_live_last.json, pasada /tmp/limits-general-live-final.log.
- Modelo Qwen 1.5/3b no es suficiente como planificador general en comparación;
  últimas pruebas locales aún finalizando. Cerebro configurable Groq separado de
  parejas originales desarrollo/análisis. Free tier 8k TPM/modelo causó 429 en
  pruebas rápidas. Reintentos semánticos no esperan largos Retry-After: pasan al
  siguiente modelo. Cotidiano usa 120B→20B, sin fallback local silencioso; «solo
  local/sin internet» fuerza local ANTES de inferencia y no escala a cloud.
- Probes nuevos: probe_general_agent.py (modelo real + handlers simulados) y
  probe_general_live.py (restaurable). Comparación rápida previa dio fallos de cuota
  y finalización por conteo, corregida por verificación semántica. NO reportar 10/10
  sin leer el informe final. Prueba de 20B actual en /tmp/limits-general-20b.log.

Pendiente: terminar diagnóstico/calibración de proveedores con cuotas, añadir pruebas
negativas de autorización/cobertura/privacidad y olvido entre sesiones; pruebas
amplias/realistas y documentación final; activar flags .env (respaldo privado),
excluir nuevas respuestas falsas de episodios 646/652/654/656/658 con respaldo
conservando mensajes; comprobar Obsidian, suite/corpus legacy, reinicio/salud y
escaneo privado de secretos. No commit ni release solicitado.

## Cierre solicitado tras reducir pruebas

El usuario señaló exceso de pruebas. Se detuvieron comprobaciones adicionales de
modelos; no seguir consumiendo cuota para mejorar una cifra de aceptación.

Implementación activada en .env: AGENT_SEMANTIC=true, KNOWLEDGE_ENABLED=true,
AGENT_COGNITIVE_PROVIDER=groq, respaldo GPT-OSS 20B, propuestas locales Qwen
habilitadas por defecto. Desarrollo/análisis mantienen sus proveedores previos.
Qwen propone operaciones sin ejecutarlas; autorización, parámetros y evidencia se
comprueban antes de presentarlas como realizadas. Los errores se replantean y los
planes parciales se reinterpretan. El historial conserva respuestas reales, no
las promesas de Qwen. Normalización de argumentos por contrato (command/action,
component/type, value/level) sin añadir patrones de frases.

Última suite completa registrada: 502 pruebas correctas. Pruebas específicas de
memoria posteriores correctas. Aceptación real de volumen/disco/recordar/recuperar/
olvidar: 5/5 con memoria temporal y volumen restaurado. Comparación funcional del
runtime: 8/10 cierres confirmados; en los otros dos se obtuvieron los resultados de
herramientas solicitados, pero la revisión final falló por HTTP 429. No afirmar
10/10 ni comprensión universal. Las cuotas gratuitas siguen siendo una limitación
externa; se conservan resultados verificados cuando falla una inferencia posterior.

Bóveda registrada en ~/Documentos/Limits-Memoria. Índice navegable por títulos,
notas editables, conflictos pendientes, redacción de secretos, tombstones y época
global para evitar recuperar datos olvidados. Se excluyeron del contexto cinco
respuestas falsas de la segunda conversación, con respaldo previo y sin borrar
los mensajes originales. No guardar procedimientos incompletos como aprendidos.

No commit ni release. No prueba manual de micrófono. Cambios anteriores conservados.
