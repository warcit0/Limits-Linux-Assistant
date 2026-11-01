#!/usr/bin/env python3
"""Muestra el QR/token para emparejar la app Android SIN arrancar Limits.

Uso:
    ./bin/limits-qr              # QR con el token actual
    ./bin/limits-qr --rotate     # revoca el token y muestra el nuevo
    ./bin/limits-qr --port 8765  # puerto explícito (default: GATEWAY_PORT)

No inicia el gateway, ni el micrófono, ni carga Whisper: solo lee config y
el token (~/.limits/gateway_token).
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description="QR de emparejamiento de Limits")
    parser.add_argument("--port", type=int, default=None,
                        help="Puerto del gateway (default: GATEWAY_PORT de .env)")
    parser.add_argument("--rotate", action="store_true",
                        help="Revoca el token actual y genera uno nuevo")
    parser.add_argument("--no-qr", action="store_true",
                        help="Solo imprime URI y token (sin QR)")
    parser.add_argument("--png", nargs="?", const="", default=None, metavar="RUTA",
                        help="Guarda el QR como PNG grande "
                             "(default: ~/.limits/pair-qr.png)")
    parser.add_argument("--open", action="store_true",
                        help="Abre el PNG con el visor del sistema (implica --png)")
    args = parser.parse_args()

    from config import Config
    from modules.gateway import (
        lan_ip,
        load_or_create_token,
        pairing_uri,
        print_pairing,
        regenerate_token,
        write_qr_png,
    )

    cfg = Config()
    token_path = cfg.GATEWAY_TOKEN_PATH or None
    port = args.port or cfg.GATEWAY_PORT

    if args.rotate:
        token = regenerate_token(token_path)
        print("Token revocado. Re-empareja la app con este QR.")
    else:
        token = load_or_create_token(token_path)

    if not cfg.GATEWAY_ENABLED:
        print("⚠  GATEWAY_ENABLED=false: este QR solo sirve si activas el "
              "gateway en .env y reinicias Limits.")

    uri = pairing_uri(lan_ip() or "127.0.0.1", port, token)

    # QR grande en PNG: la terminal (medio bloque) falla más al escanear.
    if args.png is not None or args.open:
        target = (Path(args.png).expanduser() if args.png
                  else Path.home() / ".limits" / "pair-qr.png")
        if write_qr_png(uri, target):
            print(f"PNG:   {target}")
            if args.open:
                subprocess.run(["xdg-open", str(target)], check=False,
                               stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL)
        else:
            print("⚠  no pude generar el PNG (¿falta qrencode?)")

    if args.no_qr:
        print(uri)
        return 0
    print_pairing(port, token, out=print)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
