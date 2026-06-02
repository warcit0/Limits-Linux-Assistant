#!/bin/bash
# Setup script to configure Limits Linux as a systemd user service

set -e

SERVICE_FILE="$HOME/.config/systemd/user/limits.service"
PROJECT_DIR="$HOME/Proyectos/Limits"

mkdir -p "$HOME/.config/systemd/user"

echo "Creating systemd service file..."
cat > "$SERVICE_FILE" << EOF
[Unit]
Description=Limits Linux Assistant
After=network.target sound.target

[Service]
Type=simple
WorkingDirectory=$PROJECT_DIR
ExecStart=$PROJECT_DIR/limits-env/bin/python main.py
Restart=on-failure
RestartSec=5
StartLimitBurst=3
Environment=DISPLAY=:0
Environment=WAYLAND_DISPLAY=wayland-1
Environment=XDG_RUNTIME_DIR=/run/user/%U
Environment=PIPEWIRE_RUNTIME_DIR=/run/user/%U

[Install]
WantedBy=default.target
EOF

echo "Reloading systemd daemon..."
systemctl --user daemon-reload

echo "Enabling and starting Limits service..."
systemctl --user enable --now limits.service

echo ""
echo "✅ Limits systemd service installed and started!"
echo "You can check the status with: systemctl --user status limits.service"
echo "You can view logs with: journalctl --user -u limits.service -f"
