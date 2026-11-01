# Agente general y memoria compartida

Se sustituyó el permiso basado en verbos por interpretación semántica y control
por herramientas. Las rutas mecánicas siguen como atajos. Qwen propone acciones
habituales; el coordinador valida la correspondencia con la petición, los tipos,
los destinos observados y la evidencia. Si la propuesta es parcial o inválida,
reinterpreta el objetivo y replantea. Las confirmaciones sensibles siguen vigentes.

El diálogo se conserva separado del objetivo. Los datos de estado necesitan
observaciones; no se usan respuestas inventadas como recuerdos o confirmación de
acciones. Las notas de memoria tampoco conceden permisos. «Solo local» se respeta
antes de enviar una consulta al proveedor remoto.

## Memoria

Bóveda propia: `/home/warcito/Documentos/Limits-Memoria`, registrada en Obsidian y
conectada a la misma SQLite. Preferencias expresas, decisiones, entorno, sesiones,
procedimientos comprobados y candidatos pendientes. Recuperación acotada por
relevancia, procedencia, versiones, caducidad y sincronización atómica.

Puedes editar el contenido de las notas y su título visible. Los archivos usan
identificadores estables; el índice Inicio muestra los títulos. Los conflictos se
conservan para revisar, sin sobrescribir la edición humana. Repetir explícitamente
un recuerdo resuelve su valor; las notas de conflicto incluyen instrucciones de
resolución manual. Las copias de notas gestionadas no se importan como recuerdos
nuevos. Los mensajes originales y respaldos privados se conservan como archivo,
fuera de la recuperación de los datos olvidados.

Aprender aquí significa guardar y recuperar hechos explícitos y procedimientos
con resultados verificados; no reentrenar pesos ni deducir preferencias de una
petición puntual. Los objetivos incompletos no se guardan como procedimientos
correctos. Inferencias y conflictos quedan fuera de los hechos confirmados.

## Validación y límites

- Última suite completa registrada: 502 pruebas correctas.
- Pruebas reales restaurables de volumen, disco y memoria: 5/5, sin micrófono.
- Diez escenarios con modelos reales y efectos simulados: 8 cierres confirmados;
  dos revisiones finales quedaron sin confirmar por cuota HTTP 429, aunque se
  recibieron los resultados de herramientas pedidos. Detalle local en
  `logs/probe_general_groq_runtime.json`.
- Qwen 1.5B solo no resultó suficiente como planificador general; se conserva para
  propuestas locales, sin permitir que su texto certifique efectos.
- Groq aplica límites gratuitos; no se acredita disponibilidad ilimitada ni
  comprensión universal. El usuario solicitó parar la repetición de pruebas.
- La voz progresiva y el widget se conservan; no se hizo una prueba manual nueva.

Referencias de los contratos utilizados:
[llamadas de herramientas de Ollama](https://github.com/ollama/ollama/blob/main/docs/capabilities/tool-calling.mdx),
[razonamiento de Groq](https://console.groq.com/docs/reasoning),
[límites de Groq](https://console.groq.com/docs/rate-limits),
[URI de Obsidian](https://obsidian.md/help/uri).
