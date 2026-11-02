# Autorización, dependencias y cierre

Fecha: 2026-11-01. Cambios posteriores a `dbe5590`.

## Evidencia que motivó el cambio

- Mover Firefox al espacio 4 produjo un recibo verificado. Qwen emitió
  complete=false, continuó, delegó a análisis y el turno terminó cancelado,
  ocultando el movimiento real.
- Abrir Spotify y reproducir produjo una búsqueda genérica incorrecta y una
  operación media_control. El validador añadía verify después de calcular la
  autorización: la huella dejaba de coincidir y rechazaba el lote sin efectos.
- Abrir un proyecto recibió HTTP 500 de Ollama antes de obtener salida. No hay
  evidencia suficiente para atribuir el fallo a memoria, gramática o parámetros.
- El cierre de Spotify quedó sin verificar tras dos segundos de espera de procesos.

## Cambios

1. Normalización canónica de parámetros antes de autorización, aprobación y
   recibos. El ejecutor rechaza cambios posteriores en vez de extender permisos.
2. pending declara trabajo posterior al lote; command con complete=false sin
   pendientes se corrige antes de ejecutar. Los lotes finales entregan recibos
   directamente. No se cierra por el mero éxito de una de varias acciones.
3. depends_on permite requisitos entre pasos con parámetros ya conocidos. Los
   índices deben apuntar hacia atrás. Se prepara y valida TODO antes del primer
   efecto; cada dependiente exige recibos comprobados de sus requisitos. También
   se aplica a lotes aprobados. No habilita referencias a datos futuros.
4. Delegación con encargo y motivo explícitos; después de resultados solo se
   permite un encargo de la lista de pendientes. El especialista recibe ese
   encargo, conservando el objetivo original como contexto de autorización.
5. Cancelación conserva resultados de efectos previos y registra origen. Un corte
   posterior de audio no cambia a cancelada una tarea ya finalizada sin actividad.
6. La apertura rápida de apps habilita el contrato interno antes de filtrar el
   catálogo. El modelo mantiene la capacidad por nombre.
7. Cerrar apps conserva un único envío y espera hasta cuatro segundos; consulta
   ventanas además de procesos. Si quedan procesos o ventanas no afirma salida
   completa. No fuerza kill ni repite la orden. La espera atiende cancelación.
8. Ollama registra en diagnóstico privado fase, estado HTTP, clase/código y
   duración al fallar; mide primer token y tamaños. No almacena cuerpos de error
   ni añade reintentos de inferencia o efectos.

## Revisión y límites

- Revisados contratos, huellas, preparación del lote, revalidación al confirmar,
  bloqueo de dependientes, recibos y entrega de cancelaciones.
- Regresiones simuladas preparadas en tests/test_conversation.py: permiso de
  reproducción, dependencias cumplidas/inciertas, cancelación durante un handler,
  delegación ajena a pendientes, complete inconsistente y apertura por atajo.
- Por instrucción del usuario NO se ejecutan tests, probes, modelos ni acciones
  de aceptación. Solo revisión estática/sintaxis y comprobación de arranque.
- Sintaxis AST y compilación en memoria de diez archivos Python correctas, sin
  importar ni ejecutar módulos del proyecto; git diff --check sin errores.
- Servicio reiniciado a las 22:35:05 CST: active/running, ExecMainStatus=0;
  registrados STT listo y Limits listo. Esto acredita arranque, no funcionamiento
  de órdenes ni comprensión por voz.
- pending, dependencias y encargo son decisiones del modelo. Su contrato evita
  incoherencias estructurales, pero no demuestra que haya comprendido todo lo pedido.
- No se cambian modelo, contexto ni presupuesto. No hay una nueva medición de
  latencia ni validación funcional por voz. El HTTP 500 queda mejor instrumentado;
  su causa interna continúa pendiente de observar si vuelve a ocurrir.
- Respaldo privado previo: ~/.limits/respaldos/ciclo-20261101-222443/codigo-previo.tar.
  No contiene memoria, .env ni aprobaciones activas. Revertir código no debe
  restaurar autorizaciones ni borrar memoria personal.
