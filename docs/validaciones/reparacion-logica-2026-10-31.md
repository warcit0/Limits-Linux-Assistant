# Reparación de la conversación fallida

## Cambios

Se reconocen órdenes con cortesía, «quiero que abras» y variantes de dictado.
Los proyectos se resuelven por nombre dentro de PROJECT_ROOTS, con comprobación
de ambigüedad. Las tareas cotidianas compuestas tienen pasos vinculados a la
petición y resultados por paso; una respuesta de texto no acredita su ejecución.
«Ábrelo» conserva el referente de proyecto o aplicación y deja de abrir un archivo
reciente ajeno. Una pregunta genérica no une objetivos distintos automáticamente.

Code OSS se reconoce por su clase real. El foco se verifica por dirección de
ventana. Los espacios numéricos 1–10 son destinos válidos aunque estén vacíos;
0 equivale a 10. La afirmación anterior de que el espacio 3 no existía era errónea:
la lista de workspaces materializados no es el catálogo de destinos disponibles.
Spotify se abre en special:music; se verifica su visibilidad en los monitores.
Reanudar música consulta el estado del reproductor, sin buscar literalmente «música».
Los errores no llevan un anuncio positivo como «Abriendo» delante.

## Evidencia

- Suite completa: 465 pruebas correctas, 8,2 segundos.
- Selector local de objetivos: 40/40.
- Pipeline del corpus: 32/32, sin efectos reales.
- Router local: 32/32; sonda de grounding: ocho frases, cero silencios y
  propuestas sin evidencia bloqueadas.
- Compilación completa y revisión de cambios sin errores; cero secretos detectados
  en archivos modificados. Salud: servicio, gateway, autenticación y micrófono correctos;
  widget activo.
- Secuencia original: diez casos aceptados en ventanas reales, sin micrófono ni
  proveedores remotos, con memoria y tareas aisladas. Informe local detallado:
  `logs/probe_operations_last.json`.
- Se comprobó el cambio al espacio 3, apertura de ambos proyectos, referente de
  «ábrelo», foco en Firefox y apertura de Spotify en su espacio especial.
- YouTube: se comprobó el envío de la URL de búsqueda al navegador; no se acredita
  carga de página ni reproducción de vídeo. La respuesta dice «he enviado».
- Spotify no tenía reproducción disponible. Las dos peticiones de reproducir
  terminaron preguntando por canción o artista; no se acredita reproducción.
- Operaciones de esa pasada: 0,015–1,382 segundos sin audio. No comparar directamente
  con los tiempos antiguos, que incluían TTS. Un proyecto ya estaba abierto; no son
  mediciones de arranque en frío.
- Se restauraron foco y espacio originales, se cerraron ventanas temporales y se
  restauró el servicio. Firefox usa una ventana nueva solo en la prueba para que
  pueda cerrarse; el producto conserva la apertura de pestaña.

## Memoria

Se marcaron como no fiables seis respuestas antiguas de la sesión fallida para
excluirlas del contexto. No se eliminaron episodios ni hechos. Se hizo respaldo
SQLite privado con permisos 0600 antes del cambio; una séptima respuesta ya estaba
marcada como fallida.

## Límites

Los planes cotidianos cubren las variantes implementadas y probadas; no acreditan
comprensión universal de órdenes arbitrarias. Se mantienen grounding, parámetros
acotados, confirmaciones sensibles y aislamiento de contenido externo. La voz
progresiva y Gemini no se modificaron ni se validaron con micrófono en este cierre.
