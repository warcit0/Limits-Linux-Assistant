# Segunda conversación: diagnóstico y propuesta de cambio

## Evidencia nueva

Conversación móvil de 19:36–19:39 del 31 de octubre de 2026, Costa Rica,
episodios 643–660. Lectura de SQLite, log de modelos, tarea persistida y código;
reproducción de clasificadores puros, sin ejecutar comandos del usuario.
No se modificó servicio, configuración de Obsidian, notas ni memoria del usuario.

Nueve turnos: saludo, siete órdenes y una corrección. Solo «bien Abre Spotify»
registra herramientas, con ventana y foco verificados. Los otros ocho turnos no
registran herramientas; seis figuran como correctos, incluyendo saludo y varias
respuestas inventadas. Mediana de duración total: 18,118 segundos, incluyendo voz.
Este recuento no confunde respuestas conversacionales válidas con cumplimiento.

| Entrada | Comportamiento | Causa reproducida |
|---|---|---|
| «I living to primero que nada Abre Spotify y ponme algo de música puede ser bachata» | Afirma haber preparado una lista y deduce que bachata es una preferencia | El filtro léxico rebaja a leer incluso si el clasificador propone actuar; no hay plan. La guardia de veracidad no cubre «he preparado». |
| «bien Abre Spotify» | Ejecuta y verifica Spotify en special:music | Coincide con el plan cotidiano implementado. |
| «Busca en Spotify bachata y Pon algo» | Termina sin un paso válido | No existe plan; spotify_play no se ofrece en el catálogo general del trabajador. |
| «Dale Play a la música» | Inventa Yesterday/The Sound of Silence y volumen 75 % | La autorización rebaja a leer. El trabajador puede finalizar sin observación musical; la veracidad solo identifica ciertas frases de acción, no datos de estado inventados. |
| «no no está sonando ninguna canción…» | Recomienda reiniciar el dispositivo | No consulta el estado, y el contexto anterior no se conserva como diálogo general. |
| «Dale Play a la música de Spotify» | Inventa otra canción y volumen | Mismo fallo, sin herramientas. |
| «al espacio de trabajo uno» | Saludo y preguntas genéricas | Elipsis fuera del patrón; modo lectura y sin plan. |
| «muéveme al espacio de trabajo donde está virto manager» | Termina sin paso válido | Se autoriza actuar, pero el plan solo reconoce algunas apps fijas y no resuelve el nombre contra ventanas/aplicaciones reales. |

## Problemas de arquitectura

1. `modo_autorizado` sigue usando `es_orden` como permiso léxico. Entender intención
   y autorizar una herramienta están mezclados. Una formulación natural no debería
   perder todas las herramientas porque no empieza por un verbo conocido.
2. `operational.py` ejecuta frases reconocidas, pero no es un planificador semántico.
   La reparación anterior mejoró los ejemplos conocidos; no demostró generalización.
3. `task_tools.py` no ofrece búsqueda/reproducción Spotify al trabajador general.
   Las operaciones nuevas solo aparecen si un patrón ya construyó el plan exacto.
4. `_finalizar` permite datos del equipo sin evidencia en modo lectura. Ampliar una
   expresión regular de frases prohibidas no resolverá esta categoría de fallo.
5. Diálogo, objetivo activo y memoria duradera son estados distintos. Ahora una
   tarea nueva puede perder contexto conversacional útil; la continuación depende
   principalmente de referencias léxicas, incluso tras consultar al clasificador.
6. La memoria de hechos y episodios alimenta el LLM antiguo (`llm.py`), pero no se
   recupera para los prompts del orquestador nuevo. Registrar episodios no equivale
   a que el agente los consulte o aprenda de ellos.
7. El modelo cotidiano no produjo pasos útiles en estas formulaciones. Falta una
   prueba comparativa antes de atribuir todo a su tamaño: recibió permisos,
   herramientas y contexto insuficientes. No se acredita que otro modelo aislado
   resuelva estos problemas de arquitectura.

## Plan propuesto, pendiente de aprobación

### 1. Sustituir el permiso por palabras por comprensión semántica

- Conservar rutas deterministas solo como atajo para órdenes completas inequívocas;
  su ausencia pasa al agente, nunca implica «solo conversar».
- El intérprete devuelve intención, objetivo, entidades, referencia y pasos. Tolera
  cortesía, ruido de dictado y elipsis; conserva transcripción original y no modifica
  nombres/rutas de manera irreversible.
- El control determinista se aplica a cada herramienta: tipos, alcance, negaciones,
  acción solicitada y confirmaciones sensibles. No ejecutar instrucciones externas
  ni otorgar permisos por notas recuperadas.
- Separar historial de diálogo reciente del objetivo operativo. Corregir «no está
  sonando» obliga a revisar la observación pertinente y actualizar el objetivo.

### 2. Catálogo operativo real y recuperación de fallos

- Ofrecer al planificador herramientas generales acotadas de aplicaciones/ventanas,
  proyectos, música y navegador, con parámetros estructurados y ejemplos mínimos.
- Consultar catálogo real/ventanas para resolver apps; proponer coincidencias si
  «virto manager» es ambiguo, sin inventar una app ni restringirse a cuatro nombres.
- Spotify distingue buscar contenido, elegir/reproducir y reanudar. En caso de
  selección ambigua, dar opciones concretas; no pedir otra descripción genérica.
- Ejecutar-observar-replanificar con límites. Un resultado fallido permite elegir
  otro paso permitido, no terminar inmediatamente con texto genérico.
- Toda afirmación sobre canción, volumen, ventanas o archivos requiere observación.
  Respuestas de estado se apoyan en resultados estructurados, no en frases libres
  filtradas por regex. Finalización requiere cobertura del objetivo del turno.

### 3. Evaluar Qwen y escalar cuando no avance

- Probar las entradas nuevas y variaciones inéditas con herramientas simuladas,
  comprobando plan, llamada, parámetros, estado y respuesta, no solo nombre de ruta.
- Comparar el modelo cotidiano actual con los proveedores ya configurados usando
  los mismos casos y medir acierto y latencia. Las pruebas remotas se presupuestan
  y se identifican; no convertir cada saludo en una consulta remota.
- Escalar razonamiento si no produce un paso válido, repite un fallo o la tarea
  requiere planificación compleja; conservar objetivo y evidencia al transferir.
- Ningún modelo podrá declarar cumplido un efecto que el sistema no verificó.

### 4. Memoria compartida SQLite + Obsidian

Crear `/home/warcito/Documentos/Limits-Memoria` como bóveda propia registrada en
Obsidian, independiente de las notas existentes. Estructura propuesta:

- `Inicio.md`: índice y explicación de cómo corregir/olvidar información.
- `Preferencias/`: preferencias expresas del usuario.
- `Entorno/`: proyectos, alias y procedimientos comprobados; estados transitorios
  como canción/volumen llevan caducidad y no se convierten en hechos permanentes.
- `Decisiones/`: acuerdos y decisiones con fecha y origen.
- `Sesiones/`: resúmenes breves, acciones verificadas, errores y pendientes.
- `Aprendizajes/`: correcciones explícitas y procedimientos comprobados.
- `Pendientes-de-validar/`: inferencias que aún no son hechos fiables.

SQLite conserva identificadores, índice FTS, versiones, procedencia, ámbito,
conflictos, caducidad y cola de sincronización. Markdown es la representación
editable visible en Obsidian. Escritura transaccional + cola de exportación
idempotente para no perder recuerdos si falla la exportación. Ediciones humanas
se importan con validación de versión y conflictos; no sobrescribirlas silenciosamente.

Recuperar pocos recuerdos relevantes al empezar cada turno y pasarlos al
orquestador. Mostrar origen/fecha/estado al resolver discrepancias; no cargar toda
la bóveda. Herramientas acotadas para recordar, buscar, corregir y olvidar.

Aprendizaje significa registrar y recuperar información, no reentrenar el modelo.
Guardar automáticamente resultados observados, resúmenes y correcciones explícitas.
Una petición puntual de bachata no demuestra un género favorito. Inferencias quedan
como candidatas; hechos personales inferidos requieren confirmación. No archivar
secretos ni convertir salidas inventadas del asistente en hechos. Las notas son
contexto, no autorizaciones ejecutables. Olvidar debe retirar el dato de SQLite,
Markdown, índice y contexto derivado, sin resucitarlo desde una copia antigua.

### 5. Validación y salida del cambio

- Convertir ambas conversaciones en regresiones y añadir paráfrasis no usadas al
  implementar. Aceptar correcciones de dictado, negaciones y elipsis sin ejecutar
  la acción contraria ni saltarse confirmaciones.
- Pruebas de recuperación/corrección/olvido tras reiniciar; edición desde Obsidian,
  escrituras simultáneas, conflictos, redacción de secretos y fallos de exportación.
- Limpiar de contexto las nuevas afirmaciones falsas con respaldo reversible;
  conservar conversaciones y hechos del usuario.
- Repetir aceptación restaurable en escritorio real y verificar cada efecto.
  No usar los casos conocidos ni el total de unit tests como prueba de comprensión
  general. Publicar fallos y límites además de aciertos y latencia.
- Reiniciar servicio tras implementar y verificar gateway, autenticación y widget.
