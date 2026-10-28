#!/usr/bin/env python3
"""Sirve el APK de la app Android por LAN para descargarlo desde el móvil.

- Página de descarga simple (un botón) + QR de la URL en la terminal.
- Solo expone el APK indicado: no hay listado de directorios ni rutas libres.
- Soporta Range (reanudar descarga) y Content-Disposition de attachment.

Uso:
    ./bin/share-apk                     # último APK debug, puerto 9090
    ./bin/share-apk --port 8766
    ./bin/share-apk --apk ruta/a/app.apk
"""

from __future__ import annotations

import argparse
import hashlib
import html
import mimetypes
import os
import re
import socket
import sys
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_APK = ROOT / "clients/android/app/build/outputs/apk/debug/app-debug.apk"
APK_NAME = "limits-android.apk"
APK_MIME = "application/vnd.android.package-archive"


def lan_ip() -> str:
    """IP de la LAN (truco UDP: no envía tráfico real)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def render_qr(text: str) -> str | None:
    """QR en ANSI UTF-8 con qrencode (si está instalado)."""
    import shutil
    import subprocess

    binary = shutil.which("qrencode")
    if not binary:
        return None
    try:
        proc = subprocess.run(
            [binary, "-t", "ANSIUTF8", "-m", "1", "-o", "-", text],
            capture_output=True, text=True, timeout=5, check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    return proc.stdout if proc.returncode == 0 and proc.stdout.strip() else None


def _human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} GB"


def build_page(apk: Path, url: str, digest: str) -> str:
    """Página de descarga (HTML plano, legible en móvil y escritorio)."""
    name = html.escape(apk.name)
    size = _human_size(apk.stat().st_size)
    stamp = datetime.fromtimestamp(apk.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
    return f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Limits — descargar app</title>
<style>
  :root {{ color-scheme: dark; }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; min-height: 100vh; display: grid; place-items: center;
    padding: 24px; background: #0a0e14; color: #e8eaf0;
    font: 16px/1.5 ui-sans-serif, system-ui, -apple-system, sans-serif;
  }}
  main {{ width: 100%; max-width: 420px; }}
  .eyebrow {{
    font: 11px/1 ui-monospace, SFMono-Regular, monospace; letter-spacing: .18em;
    text-transform: uppercase; color: #00e5ff; opacity: .75; margin-bottom: 10px;
  }}
  h1 {{ margin: 0 0 6px; font-size: 30px; letter-spacing: -.02em; }}
  p.sub {{ margin: 0 0 28px; color: #e8eaf0a8; font-size: 14px; }}
  a.btn {{
    display: flex; align-items: center; justify-content: center; gap: 10px;
    min-height: 56px; border-radius: 14px; text-decoration: none;
    background: #00e5ff; color: #04141a; font-weight: 650; font-size: 17px;
    transition: transform .12s ease, filter .12s ease;
  }}
  a.btn:active {{ transform: scale(.98); filter: brightness(.94); }}
  dl {{
    margin: 26px 0 0; padding-top: 18px; border-top: 1px solid #e8eaf01f;
    display: grid; grid-template-columns: auto 1fr; gap: 8px 16px;
    font: 12px/1.4 ui-monospace, SFMono-Regular, monospace;
  }}
  dt {{ color: #e8eaf066; }}
  dd {{ margin: 0; text-align: right; overflow-wrap: anywhere; }}
  .note {{
    margin-top: 22px; padding: 12px 14px; border-radius: 10px;
    background: #00e5ff0f; border: 1px solid #00e5ff26; font-size: 12.5px;
    color: #e8eaf0b8;
  }}
  .note b {{ color: #00e5ff; font-weight: 600; }}
</style>
</head>
<body>
<main>
  <div class="eyebrow">Limits · LAN</div>
  <h1>App Android</h1>
  <p class="sub">Descarga el APK en este dispositivo. Misma red, sin cables.</p>

  <a class="btn" href="/{APK_NAME}" download>Descargar APK · {size}</a>

  <dl>
    <dt>archivo</dt><dd>{name}</dd>
    <dt>compilado</dt><dd>{stamp}</dd>
    <dt>sha256</dt><dd>{digest[:16]}…</dd>
  </dl>

  <div class="note">
    Instálalo desde el aviso de descarga o en
    <b>Ajustes → Apps → Acceso especial → Instalar apps desconocidas</b>.
    Si Chrome pregunta, elige «Descargar de todos modos».
  </div>
</main>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    apk: Path = DEFAULT_APK
    page_html: str = ""
    digest: str = ""
    url: str = ""

    # La página se regenera cuando cambia el APK (recompilar no obliga a
    # reiniciar el servidor para ver el tamaño/hash correctos).
    _cache_key: tuple[int, int] | None = None

    @classmethod
    def _page(cls) -> str:
        st = cls.apk.stat()
        key = (st.st_mtime_ns, st.st_size)
        if cls._cache_key != key:
            cls.digest = hashlib.sha256(cls.apk.read_bytes()).hexdigest()
            cls.page_html = build_page(cls.apk, cls.url, cls.digest)
            cls._cache_key = key
        return cls.page_html

    server_version = "limits-share/1.0"

    def log_message(self, fmt, *args):  # noqa: A003 - firma de la stdlib
        sys.stderr.write(
            f"{self.log_date_time_string()} {self.address_string()} "
            f"{fmt % args}\n")

    # ── rutas ────────────────────────────────────────────────────────────────

    def do_HEAD(self):
        self._dispatch(head_only=True)

    def do_GET(self):
        self._dispatch(head_only=False)

    def _dispatch(self, head_only: bool):
        path = self.path.split("?", 1)[0].rstrip("/") or "/"
        if path in ("/", "/index.html"):
            body = self._page().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            if not head_only:
                self.wfile.write(body)
            return
        if path in (f"/{APK_NAME}", "/app-debug.apk", f"/{self.apk.name}"):
            self._serve_apk(head_only)
            return
        if path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            if not head_only:
                self.wfile.write(b"ok")
            return
        self.send_error(404, "no encontrado")

    def _serve_apk(self, head_only: bool):
        total = self.apk.stat().st_size
        start, end = 0, total - 1

        rng = self.headers.get("Range", "")
        m = re.match(r"bytes=(\d*)-(\d*)$", rng.strip()) if rng else None
        partial = False
        if m:
            s, e = m.group(1), m.group(2)
            if s:
                start = int(s)
                end = int(e) if e else total - 1
            elif e:  # sufijo: últimos N bytes
                start = max(0, total - int(e))
            if start > end or start >= total:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{total}")
                self.end_headers()
                return
            end = min(end, total - 1)
            partial = True

        length = end - start + 1
        self.send_response(206 if partial else 200)
        self.send_header("Content-Type", APK_MIME)
        self.send_header("Content-Disposition",
                         f'attachment; filename="{APK_NAME}"')
        self.send_header("Content-Length", str(length))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Cache-Control", "no-store")
        if partial:
            self.send_header("Content-Range", f"bytes {start}-{end}/{total}")
        self.end_headers()
        if head_only:
            return

        with self.apk.open("rb") as fh:
            fh.seek(start)
            remaining = length
            while remaining > 0:
                chunk = fh.read(min(64 * 1024, remaining))
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError):
                    return
                remaining -= len(chunk)


def main() -> int:
    parser = argparse.ArgumentParser(description="Sirve el APK de Limits por LAN")
    parser.add_argument("--apk", default=str(DEFAULT_APK),
                        help="Ruta del APK (default: build debug)")
    parser.add_argument("--port", type=int, default=9090,
                        help="Puerto (default 9090, ya permitido en ufw)")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--no-qr", action="store_true")
    args = parser.parse_args()

    apk = Path(os.path.expanduser(args.apk)).resolve()
    if not apk.is_file():
        print(f"No existe el APK: {apk}")
        print("Compílalo: cd clients/android && ./gradlew :app:assembleDebug")
        return 1

    digest = hashlib.sha256(apk.read_bytes()).hexdigest()
    ip = lan_ip()
    url = f"http://{ip}:{args.port}/"

    Handler.apk = apk
    Handler.url = url
    Handler.digest = digest
    Handler._page()  # precalcula hash + página al arrancar

    try:
        httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    except OSError as e:
        print(f"No pude abrir {args.host}:{args.port} → {e}")
        print("Prueba otro puerto con --port (y ábrelo en ufw).")
        return 1

    print()
    print("┌─ APK por la red local ─────────────────────────────────────────")
    print(f"│ URL:   {url}")
    print(f"│ APK:   {apk.name} ({_human_size(apk.stat().st_size)})")
    print(f"│ sha256 {digest[:32]}…")
    print("│")
    print("│ Abre esa URL en el móvil, o escanea el QR:")
    if not args.no_qr:
        qr = render_qr(url)
        if qr:
            for line in qr.rstrip("\n").splitlines():
                print(f"│ {line}")
        else:
            print("│ (instala `qrencode` para ver el QR)")
    print("│")
    print("│ Ctrl+C para detener el servidor.")
    print("└────────────────────────────────────────────────────────────────")
    print()
    sys.stdout.flush()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor detenido.")
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
