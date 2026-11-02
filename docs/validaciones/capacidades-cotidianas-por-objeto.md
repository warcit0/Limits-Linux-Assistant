# Capacidades cotidianas por objeto · 2026-11-01

Aplicación autorizada tras revisar los cuatro turnos móviles posteriores al cambio
PTT. Base: 624f603. Sin pruebas, probes, inferencias ni operaciones de aceptación.

## Problemas observados

- Cambiar al workspace 4: 0,118 s, completado por ruta rápida.
- Abrir Code con un proyecto: editor vacío, consulta innecesaria del escritorio y
  fallo de la segunda inferencia al agotarse el presupuesto de 30 s.
- Dictado recibido «sera code…»: apertura de Code; intención original incierta.
- Mover Firefox al workspace 2: dirección inventada y destino incorrecto, repetidos
  tras corregir; 23,488 s sin efectos. Inferencias individuales de 11–15 s.

## Cambio aplicado

- En modo conversacional, enfocar/cerrar/mover_ventana reciben aplicación o título
  exacto; origen opcional permite distinguir ventanas por workspace. Resolverlas
  y revalidarlas es responsabilidad de la herramienta, antes de cualquier efecto
  del lote. No hay coincidencia aproximada ni selección de la primera ventana.
- Abrir aplicaciones recibe nombre, consulta el catálogo instalado y conserva
  huella. Las coincidencias aproximadas o múltiples requieren aclaración.
  open_application permanece en los atajos completos y en el recorrido anterior;
  el catálogo del modelo conversacional usa abrir_aplicacion.
- Abrir proyectos recibe nombre o la ruta elegida para desambiguar, busca dentro
  de PROJECT_ROOTS y conserva la ruta exacta hasta la apertura. Búsquedas
  incompletas no seleccionan una coincidencia. No abre un editor vacío como fallback.
- Todas las preparaciones preceden al primer efecto: una ambigüedad posterior
  impide ejecutar efectos anteriores del mismo lote. Observaciones de varios
  objetos se conservan. La ejecución revalida catálogo, ventana o proyecto.
- Una elección pendiente se comunica directamente y viaja al siguiente turno como
  referencia informativa. Se reobserva; no hereda permisos ni efectos pendientes.
- La recuperación muestra la propuesta fallida y su motivo. Repetir la misma
  propuesta sin nuevos resultados se detiene; una observación nueva permite
  revalidarla. Recibos y restricciones contra repetir efectos siguen vigentes.
- JSON compacto, campos de contrato ordenados, familias en el prefijo estable y
  datos/resúmenes idénticos sin duplicar. Sin cambios de modelo, contexto o plazo.
- Prompt: aclarar operaciones contrarias en dictado dudoso y conservar el objeto
  completo. Es una instrucción al modelo, no una garantía de comprensión.
- Observaciones internas de preparación no se convierten en frases de voz. Las
  consultas explícitas conservan sus resultados. Traza acotada resolver_objeto
  permite distinguir preparación de inferencia y ejecución sin registrar parámetros.

## Validación y límites

Revisión estática, análisis de sintaxis AST y git diff --check. Se prepararon seis
regresiones simuladas en tests/test_conversation.py, sin ejecutarlas: movimiento
por nombre, origen, ambigüedad de lote sin efectos, apertura por ruta exacta,
recuperación con propuesta y observaciones de dos aplicaciones.

Servicio activo/running, ExecMainStatus=0, STT listo, Limits listo y entrada F9
confirmados al activar el cambio; socket PTT con permisos 0600. El acierto semántico,
la voz y el ahorro de latencia quedan pendientes del uso libre del usuario. El
reconocimiento Android sigue enviando su texto; no se cambia el APK ni se afirma
haber corregido su transcripción.
