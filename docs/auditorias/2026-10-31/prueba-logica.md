# Prueba conversacional · Fallos de lógica

31 de octubre de 2026, 17:06:45–17:10:18, Costa Rica. Análisis solicitado por el
usuario, sin cambios en código, configuración, servicio o memoria. Solo se crea
este informe. Referencia: episodios 623–642, 10 turnos del móvil; consulta SQLite
solo lectura, tarea conservada, logs y reproducción de funciones puras sin modelos
ni handlers reales.

## Resultado

Coincide con la experiencia comunicada: solo los dos últimos turnos tomaron rutas
operativas útiles. El resto de las peticiones no se cumplió. La última ruta busca
literalmente «música» en Spotify; tampoco distingue correctamente buscar de reanudar.
No hubo consultas a Gemini ni a OpenCode en esta conversación: los registros de
modelo corresponden a cotidiano local. La cuota de OpenCode no explica el fallo.

Las 451 pruebas anteriores y los corpus no acreditaban conversación funcional de
extremo a extremo. El corpus de órdenes usa expresiones canónicas; los escenarios
del selector no cubrían estas variantes ni comprobaban el resultado final de esta
secuencia. Mi conclusión de validación anterior fue insuficiente.

## Casos observados

| Episodios | Petición | Respuesta/comportamiento | Fallo |
|---|---|---|---|
| 625–626 | «bien livings primero muéveme al espacio de trabajo 3» | «ya te encuentras en tu espacio de trabajo 3» | Normalización no reconoce el prefijo; la autorización rebaja a lectura, sin herramientas de acción. Afirmación de éxito sin comprobación. |
| 627–628 | «quiero que abras code con la carpeta creador de videos» | «Estoy listo para abrir Code… ¿Necesitas ayuda con algo más?» | `abras` no satisface el patrón `abre…`; incluso una propuesta actuar acaba en leer. No resuelve ni abre el proyecto. |
| 629–630 | «Ábrelo Ábreme mi pantalla en el espacio de trabajo 3» | «Abriendo. No hay un archivo reciente» | `file_router` captura cualquier aparición de ábrelo y ejecuta `open_last`, ignorando el contexto de proyecto y workspace. El executor antepone un anuncio positivo al error. |
| 631–632 | «bien entonces abre el gestor de cotizaciones con code» | Vuelve a saludar y pregunta qué software | El prefijo residual `entonces` hace caer otra orden a lectura. No intenta resolver el proyecto por nombre. |
| 633–634 | Mover al workspace de Firefox y buscar vídeo en YouTube | Promete buscar, pregunta qué tipo de vídeo | No descompone la tarea ni consulta ventanas ni ejecuta la búsqueda. |
| 635–636 | Precisa el vídeo de perros | «estoy buscando… ¿Hay algo más…?» | Respuesta de progreso inventada, no existe búsqueda acreditada en los recibos conservados. |
| 637–638 | «Abre Spotify y Reproduce la música» | «No he realizado cambios… si concretamos el objetivo» | Se reconoce actuar, pero el agente finaliza sin herramientas. El objetivo ya era concreto: falta ejecutar pasos, no pedir otra descripción genérica. |
| 639–640 | «Abre Spotify» | Ruta nativa de abrir app | Funcionó según el usuario. El texto por sí solo no demuestra la ventana final. |
| 641–642 | «Reproduce la música» | Ruta `spotify_play(query="música")` | Funcionó según el usuario, pero busca en lugar de reanudar. El handler no comprueba el resultado final de `playerctl play`. |

## Causas confirmadas

1. **La capa de autorización destruye la intención de acción.**
   `modo_autorizado` depende de verbos y prefijos limitados. Se reprodujeron las
   frases exactas: las cuatro peticiones de workspace/proyecto y la orden de
   Firefox terminan en leer aunque se les proponga actuar. Esto no depende de que
   Qwen acierte o no. Al quedar en leer, el catálogo elimina las acciones y el agente
   solo puede conversar/consultar.

2. **La veracidad depende del modo ya mal clasificado.**
   `_finalizar` exige efectos solamente si modo=actuar. Si la primera capa rebaja
   una orden a leer, puede conservar «ya estás», «estoy buscando» y otros textos
   sin evidencia. La charla libre de Mejora 2 hace más visible este agujero. Los
   metadatos `ok=1` de varias respuestas agravan el problema: indican finalización
   de una respuesta, no cumplimiento del objetivo solicitado.

3. **El seguimiento se fuerza por una heurística demasiado amplia.**
   Si había pregunta abierta, la entrada es corta y `comando_compatible` no
   reconoce su prefijo, `contexto_ruta` fuerza referencia anterior. El formato de
   salida de Ollama convierte entonces `continuar` en `const:true`: el modelo no
   puede corregir la decisión. La tarea conservada acumula proyecto → Firefox →
   vídeo → Spotify, con recibos vacíos. Una pregunta genérica «¿algo más?» no debe
   vincular automáticamente el siguiente objetivo.

4. **Los pronombres se resuelven por palabra, no por referente.**
   La condición de `open_last` acepta ábrelo dentro de una oración más larga sin
   exigir una búsqueda de archivos previa. Se pierde el referente proyecto/app y
   se combina «Abriendo» con el error del handler.

5. **No hay obligación de completar el plan solicitado.**
   Una decisión final de texto puede cerrar una petición actuar sin usar ninguna
   herramienta. La advertencia final evita la mentira en Spotify compuesto, pero
   no provoca un intento de planificación válido. Hace falta controlar acciones
   pendientes, resultados por paso y una explicación específica ante fallos reales.

6. **Los proyectos por nombre carecen de una resolución suficiente.**
   No se observó intento de localizar las carpetas solicitadas. Sin ruta explícita,
   el agente no dispone de raíces observadas; no debe inventarlas ni leer todo HOME.
   Necesita resolver nombres dentro del catálogo y raíces configuradas autorizadas,
   y preguntar únicamente si falta el proyecto o hay varias coincidencias.

7. **La última orden musical usa una semántica incorrecta.**
   `Reproduce la música` cae en búsqueda de contenido; debería usar el contexto del
   reproductor para reanudar cuando hay una sesión preparada. Consultar reproducción
   y metadatos resulta necesario antes de asegurar que suena.

## Tiempos

Los turnos fallidos de proyectos, Firefox y Spotify compuesto duraron entre
13,4 y 18,2 s; abrir el último archivo fallido duró 5,4 s. Las rutas operativas
finales duraron 3,37 s y 7,26 s. Son tiempos totales del pipeline, incluido audio:
no equivalen a tiempo de silencio ni a primer PCM.

Los dos llamados locales de la mayoría de los turnos suman aproximadamente
3,7–8,9 s; el resto incluye procesamiento y reproducción. No hay marca suficiente
del primer PCM para todos estos turnos. No se atribuye esta demora a Gemini.

## Plan de reparación propuesto, pendiente de aprobación

1. **Intención y autorización coherentes.** Separar entender la orden de conceder
   capacidades. Sustituir el rebajado silencioso por un contrato de acciones
   explícitas y grounded respecto a la petición completa. Admitir cortesía,
   conjugaciones y dictado imperfecto sin convertir preguntas, negaciones ni
   recomendaciones en permisos. Mantener confirmación explícita y cortafuegos.
2. **Cumplimiento y veracidad obligatorios.** Para toda petición de acción, exigir
   pasos y resultados pertinentes antes de terminar. El generador conversacional
   no puede certificar efectos. Distinguir solicitado, ejecutado y comprobado con
   datos tipados; los metadatos deben reflejar cumplimiento, no solo texto generado.
3. **Contexto por significado.** Diferenciar aclaración de un parámetro, referencia
   a una opción y objetivo nuevo. Eliminar la obligación artificial de continuar
   por longitud; «¿algo más?» no mantiene una tarea operativa abierta. Ábrelo debe
   resolver proyecto/app/archivo según antecedentes y pedir aclaración si hay duda.
4. **Herramientas prácticas y composición.** Resolver proyectos por nombre dentro
   de raíces autorizadas, enfocar la app/identificar su workspace, buscar en el
   destino pedido y componer abrir Spotify + reanudar. Si un paso falla, identificarlo
   y conservar los ya completados sin repetir efectos ni hacer promesas vacías.
5. **Aceptación basada en esta secuencia.** Reproducir los diez turnos y variantes,
   primero con efectos simulados y aserciones del estado final, después con apps y
   workspaces reales restaurables. Comprobar ausencia de falsas afirmaciones,
   separación de objetivos y resultado de cada acción. Los negativos —explicación,
   negación, falta de destino, proyecto ambiguo— también deben pasar. No presentar
   otro 32/32 como prueba de capacidad conversacional completa.

Prioridad: reparar intención → cumplimiento/veracidad → contexto → herramientas;
no añadir otra capa de animación ni cambiar de modelo para tapar estos defectos.
Las respuestas fallidas de esta sesión permanecen intactas durante el análisis;
su exclusión del contexto reutilizable se incluiría en la reparación autorizada.

## Cierre de la reparación

Ver [validación de la reparación](../../validaciones/reparacion-logica-2026-10-31.md).
La lista de espacios activos no limita los destinos 1–10: el espacio 3 vacío es válido.
