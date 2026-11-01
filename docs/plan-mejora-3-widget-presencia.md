# Mejora 3 · Presencia animada de Limits

Estado: implementada y activada tras aprobación del usuario. Núcleo orgánico
elegido con mayor complejidad visual. Fecha: 2026-10-31.

Validación: [informe de Mejora 3](validaciones/mejora-3.md). La propuesta original
siguiente conserva el alcance acordado; las comprobaciones físicas limitadas se
detallan en el informe.

## Objetivo

Aparecer como widget sobre las aplicaciones, arriba a la derecha, al escuchar una
petición, pensar, ejecutar o hablar. Comunicar actividad real sin distraer ni
apropiarse del teclado. Reposo oculto por defecto; presencia mínima opcional.

## Opciones visuales

1. **Núcleo orgánico (recomendado):** esfera de 64–80 px con una forma interior
   que respira y se deforma. Pensamiento lento; voz reactiva a su energía. Da una
   identidad a Limits sin necesitar rostro ni animaciones pesadas.
2. **Cápsula de voz:** superficie de unos 220 × 64 px, nombre y barras. Mayor
   claridad para mostrar «Investigando» o «Esperando confirmación»; ocupa más ancho.
3. **Halo orbital:** anillo fino y centro luminoso, rotación lenta al pensar y
   pulsos de voz. Discreto y ligero; puede parecer un indicador de carga genérico.

Recomendación: núcleo con etiqueta breve debajo; expansión opcional al pasar el
ratón para ver estado y un control explícito «Detener». No usar caras ni una escena
3D en la primera versión. Colores sobrios adaptables al tema; los estados también
se distinguen mediante texto y movimiento, no solo por color.

## Integración propuesta

Quickshell/QML y Qt Quick, ya disponible en este equipo (0.3.2), con PanelWindow
Wayland. Anclaje arriba/derecha, margen configurable y respeto de la barra superior.
Sin reservar espacio de trabajo ni robar foco. Región de entrada limitada al widget:
los clics exteriores pasan a la aplicación. Selección de monitor configurable;
por defecto, monitor de la interacción al empezar y fijo durante ese turno.

Fuentes oficiales: https://quickshell.org/ y
https://quickshell.org/docs/v0.3.2/types/Quickshell/PanelWindow/.
La compatibilidad sobre fullscreen y las reglas concretas se validarán contra la
versión instalada; no se promete aparecer por encima de la pantalla de bloqueo.

Limits seguirá siendo un servicio independiente de la interfaz. Publicará un
contrato local de estado mediante socket Unix privado, con estado actual al
reconectar, id de turno, secuencia y marca temporal. Sin claves ni transcripciones
por defecto. El widget no leerá logs ni consultará periódicamente modelos.

Estados: oculto, escuchando, pensando, investigando, ejecutando, esperando
confirmación, hablando, interrumpido y error. Prioridad visual: error/confirmación,
luego habla, luego ejecución/investigación/pensamiento. Hablar e investigar pueden
coexistir internamente; el indicador secundario debe conservar esa distinción.

El movimiento de voz se calculará sobre el PCM del TTS y se alineará con su
reproducción, con suavizado y unas 20–30 actualizaciones por segundo; nunca se
volverá a abrir el micrófono para medirlo. Integrar Piper y ElevenLabs, sus
pausas, silencios, fallback y cancelación. Estar sintetizando no significa hablar.
El widget no podrá autorizar acciones sensibles; «Detener» reutilizará la
cancelación existente mediante un mensaje local autenticado por permisos Unix.

## Fases y aceptación

1. Elegir forma y comportamiento; aprobar este plan.
2. Prototipo de escritorio con estados simulados y retirada reversible.
3. Eventos reales del pipeline y conexión/reconexión; widget opcional por config.
4. Energía del audio, pausa/interrupción y fuentes local/Gemini/móvil.
5. Pruebas y activación: foco intacto, cambios de workspace, fullscreen, monitor y
   escala; sin widgets duplicados, eventos antiguos ni permanencia tras cancelar.

Medir latencia desde evento hasta pantalla, CPU/GPU y memoria en reposo y animando.
Objetivo inicial: transición de estado <150 ms en el equipo, 30 fps suficientes,
sin trabajo de animación cuando esté oculto. Ofrecer movimiento reducido y
opacidad/tamaño/margen configurables. El fallo o cierre del widget no debe
interrumpir Limits ni su voz. Si cae el servicio, dejar de mostrar actividad
vigente y comunicar desconexión brevemente.

## Límites

Primera entrega: presencia, estado y detener; sin historial, transcripciones,
chat completo, selección de modelos ni cambios del router. Respetar el periodo de
pruebas actual; no se consumirá OpenCode para elaborar esta propuesta. El usuario
ha indicado que esperará a las 7 para su reinicio de uso: es su previsión, no un
horario de cuota verificado ni una automatización solicitada.

## Dirección aprobada e implementación

El usuario eligió el núcleo orgánico y autorizó proceder, pidiendo una animación
más desarrollada. Dirección: membrana viva, filamentos de interferencia, centro
luminoso y partículas orbitales. Paleta: hielo `#66f0ff`, mineral `#066e7d`, ámbar
`#ff8c33`, fondo de etiqueta `#162127`, texto `#e5f4f5`. Inter para estados; toda
la expresividad se concentra en el núcleo, con etiquetas y controles sobrios.
No se añade decoración al resto del escritorio.

El render se hace mediante shader Qt Quick, no con una página web ni una escena
3D pesada. Tamaño inicial: 172 px para conservar detalle. Ritmo de 30 actualizaciones
por segundo, detenido cuando está oculto; movimiento reducido configurable.
La captura de energía utiliza el audio generado, sin otra escucha de micrófono.
