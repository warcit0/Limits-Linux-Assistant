# Entrada por F9 y teléfono

Configuración local: `LOCAL_INPUT_MODE=ptt`. Mantener F9 mientras se habla y soltar
para enviar. No se necesita wake word. Mientras está ocupado, volver a pulsar
cuando termine; no se encolan pulsaciones. A los 30 segundos sin soltar se descarta
la captura. El teléfono mantiene sus órdenes y cancelación sin wake word.

Hyprland carga `~/.config/hypr/limits-ptt.conf` desde su configuración principal:

```ini
bind = , F9, exec, /home/warcito/Proyectos/Limits/bin/limits-ptt press
bindr = , F9, exec, /home/warcito/Proyectos/Limits/bin/limits-ptt release
```

Para volver a escucha ambiental: `LOCAL_INPUT_MODE=wakeword` y reiniciar Limits.
La reproducción móvil permanece aislada del micrófono local en ambos modos.

Validación: revisión estática y sintaxis, recarga de Hyprland sin errores, arranque
del servicio. No se ejecutan tests, inferencias ni pruebas de micrófono; aceptación
de voz pendiente del uso libre del usuario.
