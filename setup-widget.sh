#!/bin/bash
# Instala la presencia visual sin modificar Hyprland ni el servicio de voz.
set -euo pipefail
PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if ! command -v qs >/dev/null; then
    echo 'Falta Quickshell. Instálalo antes de activar el widget.' >&2
    exit 1
fi
if [ ! -f "$PROJECT_DIR/ui/presence/nucleo.frag.qsb" ] || [ "$PROJECT_DIR/ui/presence/nucleo.frag" -nt "$PROJECT_DIR/ui/presence/nucleo.frag.qsb" ]; then
    /usr/lib/qt6/bin/qsb --glsl '100 es,120,150' --hlsl 50 --msl 12 \
        -o "$PROJECT_DIR/ui/presence/nucleo.frag.qsb" "$PROJECT_DIR/ui/presence/nucleo.frag"
fi
# El generador cita rutas para systemd; nunca las ejecuta mediante un shell.
"$PROJECT_DIR/limits-env/bin/python" - "$PROJECT_DIR" <<'PY'
import os
from pathlib import Path
import sys
raiz=Path(sys.argv[1])
def citar(valor):
    return '"'+str(valor).replace('\\','\\\\').replace('"','\\"').replace('%','%%')+'"'
unidad=Path.home()/'.config/systemd/user/limits-widget.service'
unidad.parent.mkdir(parents=True,exist_ok=True)
contenido='''[Unit]
Description=Presencia animada de Limits
After=graphical-session.target

[Service]
Type=simple
ExecStart=/usr/bin/qs -n --log-rules "quickshell.io.socket.warning=false" -p '''+citar(raiz/'ui/presence/shell.qml')+'''
Restart=on-failure
RestartSec=5
Environment=WAYLAND_DISPLAY='''+citar(os.environ.get('WAYLAND_DISPLAY','wayland-1'))+'''
Environment=XDG_RUNTIME_DIR=%t

[Install]
WantedBy=default.target
'''
if unidad.exists() and unidad.read_text()!=contenido:
    from datetime import datetime
    unidad.with_suffix('.service.bak-'+datetime.now().strftime('%Y%m%d%H%M%S')).write_bytes(unidad.read_bytes())
unidad.write_text(contenido)
PY
systemctl --user daemon-reload
systemctl --user enable --now limits-widget.service
echo 'Widget activado. PRESENCE_ENABLED=true en .env conecta la actividad de Limits.'
