"""
Gateway WebSocket — control remoto por voz desde Android (docs/plan-control-remoto-android.md).

Una sola responsabilidad: recibir texto del móvil y alimentarlo al MISMO pipeline
de Limits (LLM router → executor → voz). Cero lógica de intents aquí.

Seguridad:
  - Token de pairing autogenerado en ~/.limits/gateway_token (chmod 600).
    La app lo envía como "Authorization: Bearer <token>" en el upgrade del WS.
  - Sin token ⇒ close 4401. LAN-only por diseño.
Concurrencia:
  - El lock de turno vive en el pipeline compartido con la voz local
    (main.make_pipeline); el gateway pasa wait_timeout y traduce la espera
    agotada en {"err":"BUSY"}.
"""

import asyncio
import json
import logging
import mimetypes
import secrets
import socket
import threading
import time
from pathlib import Path

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect

log = logging.getLogger("limits.gateway")

PROTOCOL_VERSION = 1
TURN_WAIT_TIMEOUT = 20.0  # segundos que un comando remoto espera su turno


class RemoteBusy(Exception):
    """El asistente está atendiendo otro turno (voz local u otro remoto)."""


class TurnGate:
    """Lock de turno global compartido entre voz local y comandos remotos."""

    def __init__(self):
        self._lock = threading.Lock()

    def acquire(self, timeout: float | None = None) -> bool:
        if timeout is None:
            self._lock.acquire()
            return True
        return self._lock.acquire(timeout=timeout)

    def release(self):
        try:
            self._lock.release()
        except RuntimeError:
            pass


def lan_ip() -> str | None:
    """IP local en la LAN (truco UDP: no envía tráfico real)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return None
    finally:
        s.close()


def load_or_create_token(path: str | None = None) -> str:
    p = Path(path).expanduser() if path else Path.home() / ".limits" / "gateway_token"
    p.parent.mkdir(parents=True, exist_ok=True)
    if p.exists():
        token = p.read_text().strip()
        if token:
            return token
    token = secrets.token_hex(32)
    p.write_text(token)
    p.chmod(0o600)
    return token


def _msg(**fields) -> dict:
    base = {"v": PROTOCOL_VERSION}
    base.update(fields)
    return base


class GatewayServer:
    """WS /ws + zeroconf. Corre en un hilo daemon dentro del proceso principal."""

    def __init__(self, pipeline, host: str = "0.0.0.0", port: int = 8765,
                 mdns_name: str = "Limits", token_path: str | None = None,
                 app_version: str = "", speak_remote: bool = True):
        """
        Args:
            pipeline: callable(text: str, wait_timeout: float | None,
                               speak: bool = True) -> str.
                      Eleva RemoteBusy si no consigue turno a tiempo.
            speak_remote: si False, los turnos remotos NO hablan por los
                          altavoces del PC (modo silencioso en local).
        """
        self.pipeline = pipeline
        self.host = host
        self.port = port
        self.mdns_name = mdns_name
        self.speak_remote = speak_remote
        self.token = load_or_create_token(token_path)
        self.app_version = app_version
        self.app = FastAPI(title="Limits Gateway", docs_url=None, redoc_url=None,
                           openapi_url=None)
        self.app.websocket("/ws")(self._ws_endpoint)
        # Media efímero para casting de archivos locales (F2): URLs firmadas
        self._media: dict[str, tuple[Path, float]] = {}
        self._media_lock = threading.Lock()
        self.app.get("/media/{token}/{filename}")(self._serve_media)
        self._server: uvicorn.Server | None = None
        self._thread: threading.Thread | None = None
        self._zc = None
        self._zc_info = None

    # ── ciclo de vida ────────────────────────────────────────────────────────

    def start(self) -> dict:
        cfg = uvicorn.Config(self.app, host=self.host, port=self.port,
                             log_level="warning", lifespan="off",
                             ws_ping_interval=20.0, ws_ping_timeout=20.0)
        self._server = uvicorn.Server(cfg)
        self._thread = threading.Thread(
            target=self._server.run, name="limits-gateway", daemon=True)
        self._thread.start()
        self._register_mdns()
        info = {"host": self.host, "port": self.port, "ip": lan_ip(),
                "mdns": f"{self.mdns_name}._limits._tcp.local."}
        log.info("gateway arrancado: %s:%s", info["ip"], info["port"])
        return info

    def stop(self):
        self._unregister_mdns()
        if self._server:
            self._server.should_exit = True
        if self._thread:
            self._thread.join(timeout=3)
        self._server = None
        self._thread = None
        log.info("gateway detenido")

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    # ── mDNS ─────────────────────────────────────────────────────────────────

    def _register_mdns(self):
        try:
            from zeroconf import ServiceInfo, Zeroconf
            ip = lan_ip()
            if not ip:
                log.info("mDNS omitido: sin IP LAN detectable")
                return
            self._zc = Zeroconf()
            self._zc_info = ServiceInfo(
                "_limits._tcp.local.",
                f"{self.mdns_name}._limits._tcp.local.",
                addresses=[socket.inet_aton(ip)],
                port=self.port,
                properties={"v": str(PROTOCOL_VERSION)},
            )
            self._zc.register_service(self._zc_info)
            log.info("mDNS anunciado como %s (%s:%s)", self.mdns_name, ip, self.port)
        except Exception as e:  # mDNS es conveniencia, nunca crítico
            log.warning("mDNS no disponible: %s", e)
            self._zc = None
            self._zc_info = None

    def _unregister_mdns(self):
        try:
            if self._zc and self._zc_info:
                self._zc.unregister_service(self._zc_info)
            if self._zc:
                self._zc.close()
        except Exception:
            pass
        self._zc = None
        self._zc_info = None

    # ── media efímero (casting de archivos locales) ─────────────────────────

    MEDIA_TTL = 3600.0  # segundos que vive una URL de archivo local

    def make_media_url(self, file_path: str, ttl: float | None = None) -> str | None:
        """URL LAN temporal y firmada para que la TV descargue un archivo local."""
        try:
            p = Path(file_path).expanduser().resolve()
        except OSError:
            return None
        if not p.is_file():
            return None
        tok = secrets.token_urlsafe(12)
        with self._media_lock:
            self._purge_media_locked()
            self._media[tok] = (p, time.time() + (ttl or self.MEDIA_TTL))
        # Con bind 0.0.0.0 la TV necesita la IP LAN real; si el bind es una
        # IP concreta, esa misma (coherente con lo que realmente escucha).
        if self.host in ("0.0.0.0", "::"):
            ip = lan_ip() or "127.0.0.1"
        else:
            ip = self.host
        return f"http://{ip}:{self.port}/media/{tok}/{p.name}"

    def _purge_media_locked(self):
        now = time.time()
        dead = [t for t, (_, exp) in self._media.items() if exp <= now]
        for t in dead:
            del self._media[t]

    async def _serve_media(self, token: str, filename: str):
        from fastapi.responses import FileResponse, JSONResponse
        with self._media_lock:
            entry = self._media.get(token)
        if entry is None or time.time() > entry[1] \
                or entry[0].name != filename or not entry[0].is_file():
            return JSONResponse(status_code=404, content={"detail": "expirado"})
        ctype = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        return FileResponse(entry[0], filename=filename, media_type=ctype)

    # ── WebSocket ────────────────────────────────────────────────────────────

    async def _ws_endpoint(self, ws: WebSocket):
        auth = ws.headers.get("authorization", "")
        if auth != f"Bearer {self.token}":
            log.warning("conexión rechazada sin token válido")
            await ws.close(code=4401)
            return

        await ws.accept()
        await ws.send_json(_msg(type="welcome", version=self.app_version))
        log.info("cliente conectado")

        try:
            while True:
                try:
                    raw = await ws.receive_text()
                except WebSocketDisconnect:
                    break
                await self._handle_message(ws, raw)
        finally:
            log.info("cliente desconectado")

    async def _handle_message(self, ws: WebSocket, raw: str) -> None:
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            await ws.send_json(_msg(type="response", ok=False, err="BAD_JSON",
                                    msg="mensaje no es JSON válido"))
            return
        if not isinstance(msg, dict):
            await ws.send_json(_msg(type="response", ok=False, err="BAD_JSON",
                                    msg="mensaje no es objeto"))
            return
        if msg.get("v") != PROTOCOL_VERSION:
            await ws.send_json(_msg(
                type="response", ok=False, err="UNSUPPORTED_VERSION",
                msg=f"solo se habla v{PROTOCOL_VERSION}"))
            return

        mtype = msg.get("type")
        if mtype == "ping":
            await ws.send_json(_msg(type="pong"))
        elif mtype == "hello":
            await ws.send_json(_msg(type="welcome", version=self.app_version))
        elif mtype == "command":
            await self._run_command(ws, str(msg.get("text") or ""))
        else:
            await ws.send_json(_msg(type="response", ok=False,
                                    err="UNKNOWN_TYPE",
                                    msg=f"tipo desconocido: {mtype!r}"))

    async def _run_command(self, ws: WebSocket, text: str) -> None:
        text = text.strip()
        if not text:
            await ws.send_json(_msg(type="response", ok=False,
                                    err="EMPTY_TEXT", msg="comando vacío"))
            return

        await ws.send_json(_msg(type="event", kind="processing"))
        try:
            spoken = await asyncio.to_thread(
                self.pipeline, text, TURN_WAIT_TIMEOUT, self.speak_remote)
            await ws.send_json(_msg(type="response", ok=True, text=spoken))
        except RemoteBusy:
            await ws.send_json(_msg(
                type="response", ok=False, err="BUSY",
                msg="Estoy atendiendo otro comando. Repite en unos segundos."))
        except Exception:
            log.exception("turno remoto falló")
            await ws.send_json(_msg(
                type="response", ok=False, err="INTERNAL",
                msg="Error interno procesando el comando."))
