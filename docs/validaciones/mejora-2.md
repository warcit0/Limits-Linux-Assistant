# Mejora 2 · Validación del 31 de octubre de 2026

Implementación autorizada con «proceed». Se completaron los cambios y las pruebas
automáticas. El usuario pidió continuar sin prueba manual de micrófono: esa
aceptación sigue pendiente y no se considera superada.

## Resultado

- Workspaces existentes: ruta directa para workspace/work space/world space,
  cortesía y números; cambio comprobado por Hyprland. Movimiento de ventana solo
  explícito y comprobado por identificador. Vuelta al anterior y listado agrupado.
- La prueba real cambió de espacio en 20 ms y restauró el original. No se crean
  espacios para probar. Especiales y creación siguen fuera del alcance inicial.
- Una acción antigua no acredita un turno nuevo. Una solicitud sin verificación
  no se presenta como resultado comprobado. No se inventa visión de pantalla.
- Aplicaciones abiertas se obtienen de ventanas de Hyprland. Qwen conversa con
  texto natural, mantiene preguntas abiertas y ofrece continuaciones concretas.
  Las acciones conservan grounding, catálogo y confirmaciones vigentes.
- Gemini entrega eventos mientras genera; la voz usa frases provisionales y Piper
  local, con una cola y una escucha. Fuentes, fechas y respuesta completa se
  conservan al final. Cancelación local/móvil invalida generación y audio tardíos.

## Evidencia y tiempos

La prueba real de voz sin micrófono midió acuse con primer PCM en **1,385 s**,
primer contenido con PCM en **24,238 s** y final de Gemini en **29,207 s**. El
contenido comenzó a hablarse antes de terminar Gemini; desde recibir la primera
frase hasta PCM transcurrieron **1,564 s**. Son muestras individuales, no p50/p95.
El tiempo de lectura completa depende de la extensión y no equivale a silencio.

Esa ejecución detectó una repetición por serialización del DOM: el final quitaba
espacios entre nodos y parecía una revisión. Se corrigió después; no se usa esa
medición de audio para acreditar ausencia de duplicación. La corrección tiene
regresión específica y una nueva consulta real de Gemini: **5 fragmentos, 157
palabras, sin revisión ni duplicación**, comparados con el texto final. Las
revisiones reales de contenido siguen produciendo un aviso y una corrección.

- [Medición PCM real](mejora-2/audio-real.json).
- [Nueva comprobación de fragmentos](mejora-2/fragmentos.json).
- [Conversación y continuación con aplicaciones reales](mejora-2/dialogo.json).
- [Aislamiento de memoria](mejora-2/aislamiento.json).

## Comprobaciones automáticas

- Suite Limits: **437 pruebas correctas** (7,618 s).
- Selector de especialistas: **40/40** escenarios.
- Pipeline compartido: **32/32** órdenes, handlers simulados sin efectos reales.
- Compilación de módulos, comandos y scripts correcta; dependencias compatibles.
- gemdev: **276 pruebas correctas**. También se comprobó el tipado del motor
  modificado; no se declara limpio todo el tipado de ese proyecto.
- Regresiones: permisos y confirmaciones, cortesía y workspaces, comprobación del
  address de ventana, ausencia de visión, fechas de publicación de hoy, texto
  parcial, fuentes tardías, error tras fragmentos, cambios de formato y contenido,
  cancelación y progreso por WebSocket con y sin voz local, seguimiento de opciones.

- [Router local](mejora-2/router-32.json): **32/32 (100 %)**, p50 1.537 ms,
  p95 3.034 ms; incluye rutas deterministas.
- [Sonda grounding](mejora-2/grounding.txt): 8 frases, cero silencios y acciones
  sin evidencia bloqueadas.
- [Servicio reiniciado](mejora-2/salud.txt): activo, puerto, autenticación y audio
  disponibles, **4/4**. La disponibilidad de audio no prueba barge-in acústico.
- [Conversación mediante WebSocket](mejora-2/servicio.json): explicación real de
  CSV con el coordinador activo. Sus 2 episodios de prueba se pusieron en cuarentena con respaldo.

El corpus del selector y el del pipeline también se conservan en esta carpeta.

## Memoria y límites

La suite usa memoria en RAM y carpetas temporales por prueba. Se comprobó que no
alteraba los episodios y hechos reales. Con respaldo SQLite privado previo, se
pusieron **468 episodios sintéticos inequívocos en cuarentena** y se excluyeron del
contexto **3 respuestas falsas conocidas**. Los hechos personales se conservaron.
El respaldo y los textos privados permanecen fuera del repositorio.

No se añadió visión ni se completaron todos los especiales de P2-2. La presencia
de fuentes y fechas no garantiza cada afirmación de Gemini; los avances se anuncian
como provisionales. El protocolo progresivo requiere el gemdev actualizado en
`/home/warcito/Work/WebAi-to-local-CLI-LLM`. `GEMINI_STREAMING=false` ofrece vuelta
manual al modo clásico, liberando antes el perfil persistente; no hay conmutación
automática entre protocolos. No se alteraron las prioridades de proveedores.

Pendiente únicamente de aceptación manual: hablar por el micrófono, decir «para»
y valorar la naturalidad durante una conversación real. Las pruebas automáticas
no sustituyen esa comprobación acústica.
