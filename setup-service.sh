#!/bin/bash
# Instala/actualiza Limits como servicio de usuario y lo deja arrancando solo.
# Idempotente: se puede ejecutar tantas veces como haga falta.
set -euo pipefail

SERVICE_FILE="$HOME/.config/systemd/user/limits.service"
PROJECT_DIR="${PROJECT_DIR:-$HOME/Proyectos/Limits}"

if [ ! -x "$PROJECT_DIR/limits-env/bin/python" ]; then
    echo "✗ No encuentro $PROJECT_DIR/limits-env/bin/python" >&2
    exit 1
fi

mkdir -p "$HOME/.config/systemd/user"

echo "Creando unidad systemd..."
cat > "$SERVICE_FILE" << EOF
[Unit]
Description=Limits Linux Assistant
After=network.target sound.target pipewire.service wireplumber.service
# Sin límite de reintentos: si el micrófono aún no existe, reintenta hasta que
# PipeWire publique el dispositivo.
StartLimitIntervalSec=0

[Service]
Type=simple
WorkingDirectory=$PROJECT_DIR
ExecStart=$PROJECT_DIR/limits-env/bin/python main.py
Restart=always
RestartSec=10
Environment=DISPLAY=:0
Environment=WAYLAND_DISPLAY=wayland-1
Environment=XDG_RUNTIME_DIR=/run/user/%U
Environment=PIPEWIRE_RUNTIME_DIR=/run/user/%U

[Install]
WantedBy=default.target
EOF

echo "Recargando systemd..."
systemctl --user daemon-reload

echo "Activando al inicio de sesión..."
systemctl --user enable limits.service

# Sin linger, el servicio solo existe DESPUÉS de iniciar sesión gráfica.
echo "Activando linger (arranque sin iniciar sesión)..."
loginctl enable-linger "$USER"

echo "Arrancando..."
systemctl --user restart limits.service

echo ""
echo "✅ Limits instalado y arrancando solo."
echo "   Estado:   systemctl --user status limits.service"
echo "   Logs:     journalctl --user -u limits.service -f"
echo "   Salud:    $PROJECT_DIR/bin/limits-health"
echo "   Deshacer: systemctl --user disable --now limits.service && loginctl disable-linger $USER"
