# Validación de la mejora 1 · 2026-10-31

**Entrega completada y activada en este equipo:** `AGENT_ENABLED=true`.
El modo anterior está disponible mediante `false` y reinicio de `limits.service`.
La disponibilidad de cada proveedor externo se distingue de la aceptación del rol:
los principales conservan prioridad y los respaldos operativos completan el trabajo.

## Resultados comprobados

| Comprobación | Resultado |
|---|---|
| Suite Limits | 405 pruebas correctas en 6,491 s; referencia: 272. |
| Compilación y dependencias | Python compila; `pip check` correcto; LangGraph 1.2.19. |
| Selector local | 40/40; p50 682 ms. |
| Órdenes anteriores | 32/32 en router y 32/32 en pipeline por objetivos. |
| Router | p50 1705 ms / p95 3043 ms; referencia 1671/3045 ms. |
| Grounding | Ocho frases; cero silencios y propuestas sin evidencia bloqueadas. |
| Aceptación real | Analizar carpeta → explicar segunda opción → preparar y probar → confirmar y aplicar; nombres y contenido conservados. |
| Micrófono real | Interrupción durante la espera detectada; cancelación y liberación del dispositivo. Sin guardar audio. |
| Investigación Gemini | Sesión autenticada, respuesta completa con fechas y dos fuentes oficiales comprobadas; 86,26 s. |
| Servicio y reversión | Modo anterior y nuevo arrancan con servicio, gateway, autenticación y micrófono correctos. |
| Dependencia gemdev | 273 pruebas aprobadas; tres regresiones nuevas de espera del streaming. |

Los corpus son pequeños: estos resultados no garantizan acierto universal. Los
ensayos remotos usan exclusivamente datos sintéticos y carpetas temporales.
La suite de regresiones comprueba además concurrencia local/móvil, aislamiento
por sesión, invalidación de aprobaciones, reinicio, cancelación y descarte de
respuestas tardías. El dispositivo real se probó con la participación del usuario;
los límites de latencia de esa prueba incluyen su tiempo de reacción.

## Recorrido completo y evidencia

[aceptacion-completa.json](aceptacion-completa.json) conserva resultados y tiempos
por turno. La preparación ejecuta el script en una copia aislada con bwrap, sin
red ni acceso al HOME. La aprobación identifica script y datos probados; aplicar
verifica el resultado real. Preparación y aplicación se comunican directamente
desde la evidencia de herramientas: no dependen de una inferencia adicional que
pueda agotar su cuota después de haber terminado el trabajo.

[microfono-real.json](microfono-real.json) acredita la interrupción durante una
espera de prueba. La prueba no ejecutó comandos sobre archivos. Las regresiones
complementarias enlazan esa cancelación con la generación vigente y los
subprocesos; impiden ejecutar resultados tardíos del router compatible o del
agente compuesto. También se rechaza abrir un archivo si la tarea pedía solo copiar.

[gemini-fuentes.json](gemini-fuentes.json) conserva la investigación sintética y
su versión hablada. Se comprobaron los dos enlaces oficiales y sus fechas:
[publicación de GOV.UK](https://www.gov.uk/government/publications/ai-adoption-survey-2026/ai-adoption-survey-report-2026-executive-summary)
y [publicación de OpenAI](https://openai.com/index/updated-model-spec/).
La comprobación corresponde a esta muestra; la presencia de enlaces no demuestra
por sí sola la exactitud de cualquier respuesta futura.

El daemon de gemdev podía devolver una apertura durante una pausa del streaming.
Investigación utiliza por defecto el modo clásico (`GEMINI_RESEARCH_DAEMON=false`).
Además se corrigió la espera en la dependencia instalada
`/home/warcito/Work/WebAi-to-local-CLI-LLM/gemdev/core/gemini.py`: exige estabilidad
por tres ciclos sin carga y rechaza un timeout sin final confirmado. Sus pruebas
están en `tests/test_wait_response.py` del mismo repositorio. Se conservaron los
cambios previos del usuario en los selectores. Limits requiere dos URLs distintas
y una fecha, conserva el texto completo y comunica un fallo explícito si falta
esa evidencia. La salida web sigue siendo informativa, nunca ejecutable.

## Disponibilidad y prioridad

| Rol | Orden configurado | Evidencia actual |
|---|---|---|
| Cotidiano | Qwen local | Selector y órdenes conservados. |
| Análisis | Big Pickle OpenCode → NVIDIA Super → Bolt → Groq GPT-OSS 120B | Super y Bolt leyeron CSV y calcularon correctamente 100 − 40 − 15 = 45; Super conserva la alternativa en el recorrido completo. |
| Desarrollo | DeepSeek OpenCode → NVIDIA DeepSeek → Groq GPT-OSS 120B | Groq preparó, probó y aplicó scripts con verificación del contenido. |
| Investigación | Gemini mediante gemdev | Autenticación manual completada y prueba con fuentes aprobada. |

OpenCode mantiene prioridad fija, sin alternar roles. Sus modelos gratuitos no
estuvieron disponibles durante las pruebas (cuota/acceso); no se acredita su
calidad actual. NVIDIA DeepSeek no respondió con esperas de hasta 45 s. GLM no
respondió ni en 60 s, aunque su clave funcionó con Nemotron: permanece desactivado.
No se atribuyen estos fallos a saldo agotado sin evidencia.

Groq presentó HTTP 429 y algún rechazo de formato. El adaptador permite como
máximo una repetición de inferencia por `Retry-After` o `json_validate_failed`,
dentro del presupuesto y con cancelación. No repite herramientas. No se garantiza
servicio ilimitado en planes gratuitos. Los tiempos por turno incluyen selección,
inferencias, herramientas y, cuando corresponde, intentos fallidos de respaldo;
no equivalen a latencia aislada del modelo. No se dispone de facturación por
consulta de estos servicios; no se inventa un coste cero ilimitado.

## Activación y reproducción

`AGENT_ENABLED=true` está guardado en `.env` privado; las claves permanecen solo
allí y no aparecen en evidencias. El valor distribuido continúa siendo `false`.
Se comprobó salud con el modo anterior y con el nuevo tras reiniciar. La reversión
solo requiere cambiar ese indicador y reiniciar el servicio.

- Suite: `./limits-env/bin/python -m unittest discover -s tests -v`.
- Selector: `scripts/probe_objectives.py`; órdenes: `scripts/probe_pipeline.py`.
- Recorrido remoto con datos desechables: `scripts/probe_acceptance.py`.
- Ejecutar sondas locales secuencialmente para evitar medir contención artificial.

Los JSON anteriores (`nvidia.json`, `prioridad-proveedores.json`,
`nemotron-comparacion.json`, `groq-*.json`, `glm-disponibilidad.json`) se conservan
como historial; sus resultados no sustituyen la prioridad ni el estado actuales.

## Métricas del recorrido final

Consultas al coordinador por turno, incluyendo selección local; una consulta a
la cadena remota puede incluir varios candidatos fallidos antes del respaldo.

| Turno | Tiempo | Consultas de selección / especialista | Modelo que respondió |
|---|---:|---:|---|
| 1 · analisis | 14.57 s | 1 / 4 | nvidia/nemotron-3.5-super-vl-120b-a12b |
| 2 · analisis | 5.95 s | 1 / 1 | nvidia/nemotron-3.5-super-vl-120b-a12b |
| 3 · desarrollo | 28.67 s | 1 / 2 | openai/gpt-oss-120b |
| 4 · desarrollo | 0.03 s | 0 / 0 | Sin inferencia remota |

La generación correcta de un script con una única raíz autorizada desencadena
su prueba aislada y propuesta verificable sin pedir más inferencias. Si la prueba
falla, se conserva el error para corregirlo dentro del presupuesto. Las muestras
previas también detectaron código con escapes inválidos y agotamiento de cuota;
ninguna aplicó cambios a los originales tras fallar.
