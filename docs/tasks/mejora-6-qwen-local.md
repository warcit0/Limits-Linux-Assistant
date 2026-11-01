# Task — Mejora 6: asistente cotidiano local

Estado: implementada y activada; aceptación funcional pendiente. [Plan](../plan-mejora-6-qwen-local.md).

- [x] Diagnosticar sesión real y acordar arquitectura con el usuario.
- [x] Crear snapshot local previo a la refactorización sin credenciales en el árbol.
- [x] Confirmar publicación SSH: `codex/respaldo-pre-qwen-2026-10-31`, commit `891d18aabfbcfcce898bad12aadaa0d2e9ad5256`.
- [x] Redactar plan, alcance, fases, aceptación y reversión.
- [x] Recibir aprobación de implementación.
- [x] Conservar configuración privada y versiones para reversión.
- [x] Unificar entrada: router inequívoco y Qwen como ruta cotidiana.
- [x] Preparar contexto selectivo, herramientas y decisiones de Qwen.
- [x] Resolver destinos observados y verificar resultados con permisos locales.
- [x] Preparar MCP Spotify propio, OAuth PKCE y control local compatible.
- [ ] Conectar cuenta Spotify y validar API: falta Client ID; el usuario pidió dejarlo preparado.
- [x] Delimitar delegación a especialistas y mantener conversación/voz.
- [x] Retirar probe_coherent sin consumidores y preparar casos automáticos consolidados sin ejecutarlos.
- [ ] Retirar coordinadores legacy después de aceptación, conservando reversión mientras tanto.
- [x] Preparar aceptación; no ejecutar pruebas sin nueva autorización.
- [x] Activar recorrido local autorizado: limits.service activo/running, ExecMainStatus=0.
- [x] Documentar reversión privada y límites de aceptación.
- [ ] Recoger evaluación libre del usuario; no se declara funcionamiento por voz validado.

No confundir plan escrito con implementación, ni pruebas simuladas con funcionamiento real validado.

[Entrega y límites](../validaciones/mejora-6-qwen-local.md). [Spotify MCP](../spotify-mcp.md).

## Corrección tras uso real — 2026-11-01

- [x] Sustituir el contrato de planes de Qwen por decisiones simples de cuatro campos.
- [x] Reducir contexto y descubrir especialistas aparte de las tareas cotidianas.
- [x] Separar errores internos de mensajes públicos manteniendo evidencia de los efectos.
- [x] Actualizar casos automáticos sin ejecutarlos.
- [x] Reiniciar con esta corrección: servicio active/running, ExecMainStatus=0. Aceptación real pendiente del usuario.

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


Actualización 2026-11-01: sustituido el recorrido cotidiano por contrato común de
operaciones para rutas rápidas y Qwen. Retirados cola de cláusulas, filtros del
catálogo por frases y cierre por patrones. Esquemas reales, validación previa del
lote, contexto del turno y cierre con recibos. Estado funcional pendiente de uso
libre por voz; no se ejecutaron tests/probes. Detalles vigentes en AGENTS.md §13
y docs/validaciones/mejora-6-qwen-local.md (última actualización).
