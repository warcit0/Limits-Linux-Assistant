# Mejora 6 — Entrega y límites de aceptación

Fecha: 2026-10-31. Implementación autorizada por «proceed».

## Cambios

- `AGENT_MODE=local` selecciona router rápido + ciclo existente con Qwen/Ollama.
  Obliga a semantic/coherent activos y deshabilita propuestas duplicadas y Groq
  cotidiano, aunque queden variables históricas en `.env`.
- Se reutiliza coherent_agent; no se añadió un coordinador alternativo. General,
  operational y el recorrido legacy se conservan solo para reversión y consumidores
  existentes. No se declara terminada su retirada hasta aceptación real.
- Plan, permisos locales por operación/destino, observaciones y recibos. No hay
  juez adicional de autorización por paso en este modo. No desaparecen validación
  de tipos/enums, restricciones de archivos, confirmaciones ni sandbox.
- Herramientas de aplicaciones instaladas y cierre de ventanas observadas; se
  vuelve a comprobar el foco al cerrar «lo que estoy viendo». Los cierres rápidos
  de apps conocidas conservan el handler previo; no se reescribió todo el executor.
- Contexto reciente acotado, contratos sin duplicación y salida de 800 tokens para
  el rol cotidiano. La cota de bytes es conservadora, no un tokenizador exacto.
- Atajos completos para volumen/brillo y variantes de workspace; las peticiones
  compuestas pasan completas a Qwen. Los permisos siguen siendo acotados: un modelo
  que proponga un efecto sin operación/destino demostrables recibirá una negativa
  y deberá aclarar. No se promete comprensión universal del Qwen 1,5B.
- Spotify MCP propio, OAuth PKCE y documentación preparados. Desactivado por falta
  de Client ID; el usuario pidió dejarlo preparado.

## Limpieza

Retirado `scripts/probe_coherent.py`: sonda reciente sin consumidores ni referencias
fuera de sí misma, sustituida por casos automáticos consolidados. Recuperable en
el snapshot `891d18aabfbcfcce898bad12aadaa0d2e9ad5256`. El resto de scripts conserva
consumidores documentados, instalación, salud o evidencia histórica; no se borra.
Los scripts no se ejecutan por estar presentes; su tamaño previo era ~264 KB.

## Validación y pendientes

No se ejecutaron tests, probes, inferencias de aceptación, pruebas de audio/micrófono ni acciones
de escritorio. Revisión estática de sintaxis con ast.parse, sin importar módulos de
la aplicación, y revisión de diferencias. Los casos `tests/test_local_mode.py` quedan
preparados, sin resultados atribuidos. No se declara suite en verde ni calidad por
voz validada. Conexión Spotify, ambigüedades y rendimiento real siguen pendientes.

Activar el servicio implica cargar el código, no demuestra que el modelo comprenda
cada petición. Registrar su estado tras reinicio separadamente de la aceptación.

## Reversión

Respaldo de código previo por SSH: rama `codex/respaldo-pre-qwen-2026-10-31`, commit
`891d18aabfbcfcce898bad12aadaa0d2e9ad5256`. El snapshot es una raíz independiente
para no arrastrar credenciales antiguas. No representa una versión estable validada.

La configuración previa y versiones están en la carpeta privada
`~/.limits/respaldos/mejora-6-20261031-220225/`, permisos 0700/0600. No subirla a Git.
Para volver solo al recorrido anterior: `AGENT_MODE=legacy` y restaurar los valores
previos de modo/proveedor, luego reiniciar el servicio. Para recuperar todo el código,
usar el snapshot en una copia de trabajo conservando las modificaciones actuales,
configuración, dependencias y versión de gemdev registradas; no resetear a ciegas
ni restaurar encima de SQLite/bóveda. Revertir código no deshace acciones ya realizadas.

## Activación

Servicio reiniciado el 2026-10-31 a las 22:06 (Costa Rica): active/running y
ExecMainStatus=0. `.env`: AGENT_MODE=local, proveedor cotidiano Ollama, propuestas
duplicadas desactivadas y Spotify MCP=false. Modelo instalado conservado:
qwen2.5:1.5b-instruct, contexto 8192. No se enviaron frases de prueba.

Al recuperar todo el snapshot antiguo, su dataclass no conoce los campos nuevos
de estado: conservar en privado y apartar la carpeta de estado temporal de tareas
antes de cargar código antiguo. No borrar memoria.db ni la bóveda; no reutilizar
aprobaciones ni trabajos activos. El cambio a legacy usando el código actual no
requiere esa migración de estado.

## Corrección tras primer uso

Los turnos móviles de las 22:07 fallaron antes del router/Qwen por un NameError:
la normalización de cortesía usaba re.sub sin importar re en main.py. Se añadió
el import y se reinició el servicio. El chequeo sintáctico previo no detectaba
nombres sin definir; no acreditaba ejecución funcional. Sin tests ni probes.

## Corrección del contrato cotidiano — 2026-11-01

Los turnos reales 707–716 mostraron cuatro fallos de interpretación sin ninguna
herramienta ejecutada. Qwen producía texto de cierre o intentaba delegar; el sistema
leía literalmente el rechazo del coordinador. Los dos turnos que tomaron atajos sí
obtuvieron resultados. Cambiar de proveedor conservando el contrato complejo no
había resuelto el recorrido cotidiano.

Corrección:

- Ollama cotidiano usa un objeto plano de cuatro campos: tipo, accion, parametros,
  texto; tres decisiones: herramienta, respuesta o pregunta. Una herramienta cada vez.
  Se mantiene generación JSON y se validan catálogo, firma, tipos, permisos y destino
  antes de ejecutar. No se exige al modelo generar planes, citas, IDs de evidencia,
  finaliza o pendientes. El adaptador no concede permisos: solo alimenta el mismo ciclo.
- Contexto para Qwen: petición original, diálogo breve, recuerdos pertinentes,
  resultados y corrección de la última decisión. Se retiran los planes internos,
  estados del coordinador, IDs y contratos duplicados. Salida cotidiana: 500 tokens.
- Los especialistas no aparecen como salida inicial del contrato. Se descubren por
  consultar_capacidades categoria especialistas; después se exponen llamadas por rol.
  Se conserva el límite de delegación para capacidades complejas y solo local.
- Apps conocidas pueden abrirse con open_application usando solo app y APP_MAP;
  las demás se descubren por .desktop. No se admiten argumentos arbitrarios.
- Errores de contrato y alcance tienen presentación pública separada. Los resultados
  ya comprobados se conservan y la salida nunca transforma errores en éxito. Las
  trazas anotan tipo de decisión y nombre de herramienta disponible, sin parámetros.
- Atajos de workspace aceptan destino completo sin verbo y la variación de dictado
  «muévete el espacio…»; no consumen un número aislado ni una orden compuesta.

Casos automáticos actualizados/preparados en test_local_mode.py, SIN ejecutar.
Revisión de sintaxis y diferencias únicamente. No se hicieron inferencias, probes
ni pruebas de voz. El arranque se registra aparte; no demuestra comprensión real.

Corrección cargada: servicio reiniciado, active/running y ExecMainStatus=0.
Sin consultas de aceptación; estos datos acreditan arranque, no comprensión por voz.

### Revisión del recorrido directo · 2026-11-01

La conversación del usuario posterior a las 11:21 mostró nueve peticiones sin
herramientas, tres atajos correctos y un intento multimedia fallido en Firefox.
Se sustituyó el adaptador local a planes por comandos intent/action/params/response
ejecutados directamente por el ejecutor protegido en el ciclo existente. Se
conservan presupuesto, recibos, permisos, aprobación y cierre basado en resultados.
El referente multimedia explícito tiene alcance de sesión, caducidad de cinco
minutos e invalidación por cancelación. Se reutiliza en atajos y decisiones locales.
Se actualizaron fixtures existentes al contrato nuevo, sin ejecutarlos. Revisión
de sintaxis por AST y diff sin errores de espacios; sin tests, probes ni consultas
a modelos. La eficacia con voz y la cobertura de órdenes siguen pendientes.

### Diagnóstico de salidas y encadenadas · 2026-11-01

Los episodios 751–774 mostraron seis decisiones repetidas por petición: cerrar
ventana, cambiar workspace, abrir una app no conocida y ajustar volumen. Los
recibos evitaron repetir efectos, pero el ciclo consumía todas sus inferencias.
En «detén la música y volumen al 60» solo se completó volumen. La mención de
Firefox para cerrarlo también sustituyó incorrectamente el referente multimedia.

Cambios: diagnóstico opt-in de salida original de Qwen antes del parseo, resultado
y rechazo; archivos privados redactados y acotados por turno. Cola conservadora
de cláusulas con y/e/además/también/luego/después; petición completa conservada,
cláusula pendiente visible y permiso vinculado a esa cláusula. Los efectos
verificados avanzan la cola. Consultas preparatorias no completan una orden.
Corte anticipado de repeticiones y errores para evitar seis decisiones iguales.
Referencia multimedia solo por intención multimedia; cerrar un navegador no lo
selecciona como reproductor. Atajos de enfoque aceptan «en mi/la pantalla», y el
router musical excluye esos destinos. Controles musicales piden verificación.
Catálogo local incluye enfoque, web y YouTube que antes requerían descubrimiento.

Validación: AST en once archivos y diff sin errores de espacios. Se ajustaron
fixtures y se prepararon casos de segmentación/citas/permisos sin ejecutarlos.
No hubo tests, probes ni consultas de prueba a modelos. No existe salida original
recuperable de los turnos anteriores; el diagnóstico captura los próximos turnos
reales. Pendiente comprobar la selección de Qwen y las encadenadas por uso real.

### Corrección de los cinco fallos observados · 2026-11-01

La sesión de episodios 775–794 completó cinco de diez peticiones; una quedó parcial
y cuatro mal resueltas. La orden de cambiar al espacio 2 y abrir Firefox sí tuvo
dos recibos verificados. Las salidas originales mostraron JSON válido con selección
incorrecta (address inventado, motor Google en lugar de YouTube y catálogo instalado
en lugar de aplicaciones abiertas). La petición de reanudar Spotify fue capturada
por el atajo musical, sin inferencia. La separación de «y vamos al espacio…» falló
por no compartir el reconocedor que sí aceptaba la orden aislada.

Se reutilizan los reconocedores puros de espacios y rutas rápidas al separar. El
catálogo local aplica prerrequisitos de observación a ventanas, especiales, apps,
proyectos y contenido Spotify. No ofrece cierre de ventanas para una operación
dirigida al espacio especial. Las preguntas interrogativas son lectura y las
consultas de estado actual excluyen la búsqueda instalada. El escritorio devuelve
un resumen hablado de apps abiertas y especiales visibles, además de datos reales.

Las búsquedas ligan engine al destino explícito antes de autorizar; cualquier ajuste
queda en salidas-qwen.jsonl y el permiso valida de nuevo la plataforma. El handler
web devuelve un recibo específico del envío, conservando sin_verificar porque no
observa la carga de la URL. El router multimedia separa música/reproducción genérica
con reproductor de una búsqueda de contenido. Las consultas idénticas no se repiten
salvo tras un efecto verificado intermedio. Se rechazan afirmaciones de cambio
sustentadas únicamente por consultas. No se cambió de modelo ni de coordinador.

Validación estática: AST de ocho archivos y diff sin errores de espacios. Casos
automáticos preparados, sin ejecutar. No hubo tests, probes ni peticiones de
prueba a modelos. La comprensión y recuperación efectivas siguen pendientes del
uso real y se analizarán con el diagnóstico privado ya activo.

### Operación, objeto y cierre con recibos · 2026-11-01

Los episodios 795–824 mostraron dos acciones correctas (abrir Firefox y enviar
búsqueda YouTube), con repetición innecesaria del envío; consultas del escritorio
con filtros inventados y repetición; proyectos tratados como apps; movimiento de
Code sustituido por cambio de escritorio; y selección de Code para el explorador.
Además main atribuía verificación a media_control solo por recibir verify=true,
contradiciendo los recibos sin comprobar del handler.

Se preservan ahora los recibos tipados. Los alias de apps se comparten entre router,
normalización y permisos, incluyendo los nombres cotidianos del gestor de archivos.
El catálogo local distingue el objeto solicitado: espacios especiales, proyectos
y movimiento de ventanas ofrecen su observación y operación correspondientes.
mover_ventana usa dirección observada, revalida clase/existencia, detecta ambigüedad
en permisos y verifica la ubicación por dirección sin cambiar de escritorio. No
se añadió shell ni se ampliaron permisos de archivos.

La consulta de escritorio vincula su filtro a la cláusula actual; actual se resuelve
con datos del turno. Las consultas de estado se presentan directamente al obtener
su resumen. Los efectos enviados sin comprobar se comunican una vez, conservan
la incertidumbre y permiten atender otras cláusulas; no se repiten ni se convierten
en éxitos verificados. La apertura de un proyecto requiere búsqueda y ruta observada;
no se sustituye por iniciar el editor vacío.

Revisión estática: AST de ocho archivos y diff sin errores de espacios. Preparados
casos automáticos de ámbito, movimiento frente a cambio, proyectos, alias y cierre;
no ejecutados. Sin tests, probes ni peticiones de prueba a modelos por la restricción
vigente. La comprensión real de Qwen y el uso de voz permanecen pendientes del usuario.


### Sustitución del recorrido cotidiano · 2026-11-01

El recorrido directo anterior queda sustituido por un contrato común de operaciones.
Los parches históricos documentados arriba no describen la arquitectura vigente.

- Las rutas rápidas compilan una operación al mismo ejecutor protegido que Qwen;
  no usan una entrega alternativa en main. Qwen interpreta la petición completa y
  devuelve hasta seis operaciones independientes, complete y response.
- No hay cola de cláusulas ni cierre por patrones. El catálogo mantiene sus contratos;
  permisos, tipos, observaciones, rutas y recibos se comprueban antes del lote y de
  cada efecto. Las dependencias observación→efecto requieren decisiones sucesivas.
- Los esquemas de argumentos proceden de las firmas reales; cerrar apps conocidas
  dispone del mismo close_application que el atajo. Una ventana concreta conserva
  su contrato de dirección observada. La consulta del escritorio evita duplicar
  la observación cotidiana de ventanas.
- La petición actual va al final del mensaje. No se inyectan recuerdos ni órdenes
  anteriores automáticamente; referencias explícitas admiten el último intercambio.
- Un lote final comunica los recibos sin nueva inferencia; los fallos/resultados sin
  comprobar permanecen parciales. complete es interpretación de cobertura, no una
  garantía determinista de que Qwen haya descompuesto correctamente toda petición.
- Los módulos heredados con consumidores se conservan para legacy/especialistas.
  No se ha entrenado ni sustituido Qwen, ni habilitado respaldos cotidianos remotos.

Se actualizaron los contratos preparados en tests/test_local_mode.py SIN ejecutarlos.
Se revisó la sintaxis con AST, sin importar módulos, y el formato del diff. No se ha
validado el funcionamiento por voz ni medido la precisión del nuevo contrato.
El respaldo previo está en ~/.limits/respaldos/simplificacion-20261101-122258.

Las operaciones de memoria devuelven recibos tipados después del commit/borrado.
Los seguimientos de archivos compilan la ruta del resultado observado en la sesión;
no conceden HOME o / como alcance implícito y conservan el bloqueo de ejecutables.


### Revisión del uso libre · 2026-11-01 (episodios 845–878)

La combinación cambiar espacio + abrir Firefox produjo ambos recibos verificados.
Persistían tres cierres incorrectos: abrir Code vacío por un proyecto y dos consultas
como sustituto del movimiento. El alias de archivos apuntaba a Thunar ausente; la
asociación observada es org.gnome.Nautilus.desktop y hay Nautilus/Dolphin instalados.
Qwen propuso literalmente facebook/dolby; no hay prueba de que esos nombres deban
sustituirse automáticamente. La orden de Spotify llegó con MPRIS sin control disponible;
las órdenes posteriores se enviaron sin comprobación suficiente, incluido next.

Cambios: catálogo y enum de apps disponibles; alias basado en XDG; sugerencias sin
permiso automático; proyecto independiente del orden editor/objeto; bloqueo de cierre
por lecturas/texto para cambios; variantes del router de espacios; espera de capacidades
MPRIS cancelable, una sola emisión y observación posterior de estado/pista.

Los contratos preparados en los tests se actualizaron SIN ejecutarlos. Solo se permite
revisión estática, sintaxis y arranque del servicio. Spotify no tiene MCP habilitado ni
se garantiza reproducción si el cliente no ofrece control/contenido. No se probaron
modelos, aplicaciones ni audio. Respaldo privado: ruta registrada en
/tmp/limits-respaldo-revision (archivos anteriores, sin claves ni memoria de usuario).
