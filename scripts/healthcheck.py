#!/usr/bin/env python3
"""Chequeo de salud de Limits: servicio, gateway, autenticación y micrófono.

Uso:  bin/limits-health [--port 8765] [--token ~/.limits/gateway_token]
Sale 0 si el servicio y el gateway responden; 1 si algo crítico falla.
El micrófono es un aviso (no falla) porque depende de la sesión gráfica.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path

OK, BAD, WARN = "✓", "✗", "⚠"


def _check_service() -> tuple[bool, str]:
    try:
        r = subprocess.run(
            ["systemctl", "--user", "is-active", "limits.service"],
            capture_output=True, text=True, timeout=5)
    except Exception as e:  # noqa: BLE001
        return False, f"no pude ejecutar systemctl: {e}"
    active = r.stdout.strip()
    enabled = subprocess.run(
        ["systemctl", "--user", "is-enabled", "limits.service"],
        capture_output=True, text=True, timeout=5).stdout.strip()
    if active != "active":
        return False, f"servicio {active or 'desconocido'} (enabled={enabled or '?'})"
    return True, f"servicio activo (enabled={enabled or '?'})"


def _check_port(port: int) -> tuple[bool, str]:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=2):
            return True, f"puerto {port} escuchando"
    except OSError as e:
        return False, f"puerto {port} cerrado ({e})"


def _check_ws(port: int, token_path: Path) -> tuple[bool, str]:
    if not token_path.is_file():
        return False, f"sin token en {token_path}"
    token = token_path.read_text(encoding="utf-8").strip()
    try:
        from websockets.sync.client import connect
    except ImportError:
        return False, "websockets no instalado en este intérprete"
    try:
        with connect(f"ws://127.0.0.1:{port}/ws",
                     additional_headers={"Authorization": f"Bearer {token}"},
                     open_timeout=3, close_timeout=2) as ws:
            msg = json.loads(ws.recv(timeout=5))
        if msg.get("type") == "welcome":
            return True, f"handshake ok (v{msg.get('v')})"
        return False, f"respuesta inesperada: {msg}"
    except Exception as e:  # noqa: BLE001
        return False, f"handshake falló: {e}"


def _check_mic() -> tuple[bool | None, str]:
    """True/False y detalle; None si no hay herramientas para comprobarlo."""
    if shutil.which("pactl"):
        r = subprocess.run(["pactl", "info"], capture_output=True, text=True,
                           timeout=5)
        if r.returncode != 0:
            return False, "pactl falla (¿PipeWire/PulseAudio caído?)"
        src = [ln.split(":", 1)[1].strip() for ln in r.stdout.splitlines()
               if ln.startswith("Default Source:")]
        return True, f"audio ok (fuente: {src[0] if src else '?'})"
    if shutil.which("arecord"):
        r = subprocess.run(["arecord", "-l"], capture_output=True, text=True,
                           timeout=5)
        if r.returncode == 0 and "card" in r.stdout.lower():
            return True, "dispositivo de captura presente (ALSA)"
        return False, "sin dispositivos de captura ALSA"
    return None, "sin pactl ni arecord: no puedo comprobar el micrófono"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int,
                        default=int(os.getenv("GATEWAY_PORT", "8765")))
    parser.add_argument("--token", default=None)
    args = parser.parse_args()

    token_path = Path(args.token or
                      os.getenv("GATEWAY_TOKEN_PATH") or
                      "~/.limits/gateway_token").expanduser()

    checks = [
        ("Servicio", _check_service()),
        ("Gateway", _check_port(args.port)),
        ("Auth", _check_ws(args.port, token_path)),
    ]
    critical_ok = True
    for name, (ok, detail) in checks:
        print(f"{OK if ok else BAD} {name}: {detail}")
        critical_ok = critical_ok and ok

    mic_ok, mic_detail = _check_mic()
    if mic_ok is None:
        print(f"{WARN} Micrófono: {mic_detail}")
    else:
        print(f"{OK if mic_ok else WARN} Micrófono: {mic_detail}")

    return 0 if critical_ok else 1


if __name__ == "__main__":
    sys.exit(main())
