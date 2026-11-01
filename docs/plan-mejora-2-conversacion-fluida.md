# Mejora 2 · Conversación fluida, voz progresiva y acciones comprobadas

Estado: implementada tras aprobación del usuario. Validación automática y pruebas
reales sin micrófono: [informe](validaciones/mejora-2.md). La aceptación manual de
micrófono queda aplazada por petición del usuario.

Los hallazgos siguientes describen el estado previo a esta mejora.

## Hallazgos de la conversación

1. **Cambio de workspace ficticio.** Se registraron «muéveme al work Space 2» y
   «perfecto muéveme al World space 1». La primera recibió una respuesta
   contradictoria: negaba cambios y aseguraba que el objetivo se había alcanzado.
   La segunda aseguró encontrarse en el destino. No existe una herramienta de
   workspaces: `hyprland_control` solo implementa cerrar ventana y fullscreen.
   La tarea P2-2 continúa propuesta. Separar “work space” contribuye al problema,
   pero normalizar la transcripción por sí solo no implementa esa capacidad.
   Además, `modo_autorizado` no reconoce el prefijo conversacional «perfecto»;
   puede clasificar una orden como lectura y omitir la comprobación de efectos.
   `_finalizar` antepone una advertencia, pero conserva la afirmación falsa.

2. **Visión inventada.** Ante una pregunta sobre la pantalla, el asistente afirmó
   observar a un usuario y detalles del sistema, música y aplicaciones. No dispone
   de una herramienta de visión en el catálogo actual. Consultar procesos no
   demuestra lo que aparece en pantalla. Esa respuesta debe indicar la capacidad
   ausente y ofrecer solo observaciones que realmente pueda consultar.

3. **Aplicaciones poco útiles.** La respuesta enumeró procesos internos como
   SD-PAM, MainThread y Socket Process. `list_running` devuelve los diez primeros
   nombres de procesos ordenados alfabéticamente; no enumera aplicaciones visibles.

4. **Silencio de Gemini.** El log registra comienzo del puente a las 14:24:51 y
   artefacto recibido a las 14:26:00: unos 69 segundos. gemdev informa 65,1 segundos
   de espera; la selección local anterior costó 2,442 segundos. No hay una marca
   del primer audio que permita atribuir exactamente cada segundo restante.
   El puente acumula stdout hasta terminar; el modo clásico exige tres ciclos de
   estabilidad y una relectura (aproximadamente once segundos tras el último
   crecimiento en el caso estable). Esta espera evita aceptar aperturas incompletas,
   pero no debería impedir hablar antes de la validación final.

5. **Actualidad insuficiente.** La petición era noticias de autos «de hoy» y el
   resumen hablado describió movimientos de octubre. Incluir dos URLs y un año
   no demuestra que una noticia se haya publicado hoy. Hay que distinguir fecha
   del hecho, fecha de publicación y fecha de consulta, o reconocer que no se halló
   información de ese día.

6. **Diálogo débil.** Hubo saludo genérico, una repetición literal del usuario y
   ausencia de propuestas contextuales de continuación. Cada mensaje termina
   como una consulta independiente. No hay un contrato explícito de conversación
   que mantenga una pregunta abierta y una breve oportunidad de responder por voz.

7. **Higiene de contexto y observabilidad.** Existen respuestas simuladas en la
   base real de episodios. El test del gateway ya contiene un intento de aislamiento
   mediante singleton temporal: hay que comprobar su ciclo de vida y el resto de
   la suite antes de atribuir la fuga a un test concreto. Esas entradas podrían
   contaminar el historial; no se ha demostrado que causaran estas alucinaciones.
   Los episodios analizados tampoco guardan resultado `ok` ni correlación de
   sesión/turno útil para reconstruir herramientas y primer audio.

Las 405 pruebas anteriores validaban componentes y algunos recorridos, pero no
estos casos reales. No acreditaban una experiencia conversacional suficientemente
fluida ni ausencia general de afirmaciones falsas de acciones o percepción.

## Plan propuesto

### A. Veracidad y control de workspaces

- Declarar capacidades disponibles en el contexto. Una petición no soportada
  produce una explicación honesta y una alternativa, nunca una ejecución inventada.
- Separar resultados: solicitado, ejecutado y comprobado. Un resultado sin evidencia
  no puede conservar frases de éxito ni confirmaciones de percepción inventadas.
  Verificar la acción correspondiente, no la existencia de cualquier efecto anterior.
- Implementar el alcance necesario de P2-2: consultar, cambiar y volver al workspace;
  mover una ventana solo cuando se solicite explícitamente esa operación.
- Normalizar workspace/work space/espacio de trabajo/escritorio. Aceptar variantes
  de reconocimiento como “world space” únicamente dentro de órdenes inequívocas
  con destino, sin sustituciones globales. Tratar prefijos como “perfecto” como
  cortesía cuando existe después una orden explícita; no convertir un agradecimiento
  aislado en autorización.
- Consultar los workspaces existentes; no crear nuevos sin petición explícita.
  Tras cambiar, leer el workspace activo; tras mover una ventana, comprobar su
  identificador y destino. Un retorno exitoso de `hyprctl` por sí solo no basta.
- Para aplicaciones abiertas, consultar clientes de Hyprland, agrupar ventanas
  por aplicación y separar expresamente aplicaciones visibles de procesos internos.

### B. Gemini con voz progresiva

- Ampliar gemdev con eventos incrementales versionados: estado, fragmento, fuentes,
  final y error. Su motor ya produce eventos Delta, pero el CLI consumido por Limits
  devuelve el resultado final; hace falta un contrato incremental real entre ambos.
- Mantener un navegador preparado cuando sea posible y corregir el final prematuro
  del motor persistente antes de volver a usarlo. El modo clásico queda como respaldo.
  No volver a interpretar una pausa de generación como respuesta completa.
- Canalizar fragmentos por frases o párrafos estables. Deduplicar, detectar revisiones
  del texto y evitar pronunciar fences, URLs partidas o aperturas repetidas.
- Dar una confirmación breve del trabajo aceptado y comunicar estados reales útiles
  durante las esperas; no fabricar avances ni repetir relleno por temporizador.
- Una única cola de audio y un único dueño de la captura del micrófono. Generación,
  preparación del siguiente fragmento y reproducción pueden solaparse; dos voces o
  dos escuchas nunca. Conservar la exclusión de turnos local/móvil y la cancelación.
- Distinguir avance provisional de conclusión contrastada. Si las fuentes llegan
  al final, avisar que el avance es provisional; si falla la validación, comunicarlo
  o corregirlo. No anunciar “verificado” antes de disponer de la evidencia final.
- Conservar texto, fuentes y fechas completos al finalizar, aunque ya se hayan leído
  fragmentos. No repetir la respuesta entera al final. Gemini nunca produce acciones
  ejecutables ni autorizaciones.
- Medir por separado recepción de petición, primer estado, primer texto, primer
  audio, fin de Gemini y fin del audio. Metas iniciales: acuse local en ≤2 s tras
  aceptar el texto y primer fragmento hablado en ≤2 s desde recibir una frase
  utilizable de Gemini. Medir p50/p95; no prometer una primera generación externa
  que el proveedor todavía no ha producido.

### C. Conversación más participativa

- Respuestas cálidas y desarrolladas cuando aporten valor; órdenes simples siguen
  siendo breves. Evitar saludos de presentación en cada turno y repetición literal.
- Contexto de diálogo: tema, pregunta abierta, alternativas ofrecidas y siguiente
  paso propuesto, separado de hechos personales y de aprobaciones destructivas.
- Hacer una pregunta contextual cuando abra una continuación útil: después de
  noticias de autos, por ejemplo, ofrecer eléctricos o lanzamientos y precios.
  Evitar el “¿algo más?” fijo tras cada orden.
- Tras una pregunta del asistente, permitir un periodo breve y configurable para
  contestar sin repetir la wake word; después volver al estado de reposo.
  Integrarlo con móvil, barge-in y cancelación sin capturas simultáneas.
- Respuestas como “la segunda”, “sí, compáralos” o “mejor los eléctricos” continúan
  el diálogo vigente. No convertir un sí conversacional en una aprobación de
  operaciones sensibles ajenas a esa pregunta.

### D. Memoria limpia y aceptación real

- Aislar memoria, tareas y logs de las pruebas mediante dependencias temporales
  por prueba, incluyendo fallos y teardown. Comprobar que la suite no cambia los
  episodios reales. Evitar que el registro de episodios mezcle conversaciones.
- Preparar un respaldo y una selección revisable de entradas sintéticas inequívocas
  y afirmaciones de capacidades no verificadas; excluirlas del contexto reutilizable
  sin borrar hechos personales ni conversaciones reales indiscriminadamente.
- Registrar identificador de turno y sesión, herramienta, resultado, verificación,
  modelo, tiempos y cancelación; mantener texto privado en DEBUG y no guardar claves.
- Añadir casos exactos de esta conversación a las regresiones: work space/world
  space, prefijo “perfecto”, pantalla no disponible, listado útil de apps, noticias
  de hoy, streaming parcial, fuentes tardías, error tras un fragmento, revisión del
  texto, cancelación de voz y móvil, y conversación de seguimiento.
- Aceptación manual: pedir noticias, escuchar mientras Gemini sigue generando,
  interrumpirlo, continuar con otra pregunta y cambiar realmente de workspace.
  Comprobar estado real, ningún audio tardío o duplicado y memoria de pruebas aislada.

## Orden y límites

Antes de ejecutar nuevas pruebas, aplicar el aislamiento descrito en D.
Desarrollar A → B → C y cerrar D con aceptación real, añadiendo regresiones de
cada bloque durante su desarrollo.
La honestidad y las acciones reales tienen prioridad sobre añadir más frases.
No se incorpora visión de pantalla ni otras tareas P2 por este plan; se comunica
que esa capacidad todavía no existe. La creación explícita de workspaces nuevos
puede permanecer fuera de este bloque inicial. No se cambia la prioridad de modelos.

La implementación fue autorizada mediante «proceed». Se mantiene el ciclo
plan → revisión → proceder para mejoras nuevas.
