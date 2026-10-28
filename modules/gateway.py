"""
Gateway WebSocket — control remoto por voz desde Android (docs/plan-control-remoto-android.md).

Una sola responsabilidad: recibir texto del móvil y alimentarlo al MISMO pipeline
de Limits (LLM router → executor → voz). Cero lógica de intents aquí.

Seguridad:
  - Token de pairing autogenerado en ~/.limits/gateway_token (chmod 600).
    La app lo envía como "Authorization: Bearer <token>" en el upgrade del WS.
  - Emparejamiento sin teclear: `print_pairing()` muestra un QR con
    limits://pair?h=IP&p=PORT&t=TOKEN; la app lo escanea una vez.
  - Sin token ⇒ close 4401 (tras accept, para que el cliente pueda mostrar
    el motivo; antes daba 403 opaco). LAN-only por diseño.
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
import shutil
import socket
import subprocess
import threading
import time
import unicodedata
from pathlib import Path
from urllib.parse import quote, urlencode

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
            # Re-aplicar 600: el archivo pudo crearse con otro umask o copiarse
            try:
                p.chmod(0o600)
            except OSError:
                pass
            return token
    token = secrets.token_hex(32)
    p.write_text(token)
    p.chmod(0o600)
    return token


def regenerate_token(path: str | None = None) -> str:
    """Revoca el token actual y crea uno nuevo (re-emparejar la app)."""
    p = Path(path).expanduser() if path else Path.home() / ".limits" / "gateway_token"
    p.parent.mkdir(parents=True, exist_ok=True)
    token = secrets.token_hex(32)
    p.write_text(token)
    p.chmod(0o600)
    return token


# ── Emparejamiento por QR (sin teclear 64 caracteres en el móvil) ─────────────

PAIR_SCHEME = "limits://pair"


def pairing_uri(host: str, port: int, token: str) -> str:
    """URI que la app Android entiende: limits://pair?h=IP&p=PORT&t=TOKEN."""
    query = urlencode({"v": PROTOCOL_VERSION, "h": host, "p": port, "t": token})
    return f"{PAIR_SCHEME}?{query}"


def render_qr(text: str) -> str | None:
    """QR en ASCII/ANSI UTF-8 vía `qrencode`; None si no está instalado."""
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


def write_qr_png(text: str, path) -> bool:
    """Guarda un QR PNG grande (más fácil de escanear que la terminal).

    Devuelve True si se escribió. No falla si `qrencode` no está instalado.
    """
    from pathlib import Path as _Path

    binary = shutil.which("qrencode")
    if not binary:
        return False
    target = _Path(path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        proc = subprocess.run(
            [binary, "-t", "PNG", "-s", "10", "-m", "2", "-o", str(target), text],
            capture_output=True, text=True, timeout=10, check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return False
    return proc.returncode == 0 and target.is_file()


def print_pairing(port: int, token: str, host: str | None = None,
                  out=print) -> str:
    """Imprime el QR + datos para emparejar la app. Devuelve la URI."""
    ip = host or lan_ip() or "127.0.0.1"
    uri = pairing_uri(ip, port, token)
    qr = render_qr(uri)
    out("")
    out("┌─ Emparejar la app Android ─────────────────────────────────────")
    out(f"│ PC:    {ip}:{port}     red local (sin internet)")
    out(f"│ Token: {token}")
    out("│")
    out("│ App Limits → botón «Escanear QR» (arriba a la derecha), o escanea")
    out("│ con la cámara del móvil (abre la app directamente).")
    out("│ ¿No lo lee? Genera un PNG grande:  limits-qr --png --open")
    if qr:
        out("│")
        for line in qr.rstrip("\n").splitlines():
            out(f"│ {line}")
    else:
        out("│ (instala `qrencode` para ver el QR en la terminal)")
    out("└────────────────────────────────────────────────────────────────")
    out("")
    return uri


def _msg(**fields) -> dict:
    base = {"v": PROTOCOL_VERSION}
    base.update(fields)
    return base


def _fold(text: str) -> str:
    """Minúsculas y sin acentos, para comparar palabras habladas."""
    nfkd = unicodedata.normalize("NFKD", str(text))
    return "".join(c for c in nfkd if not unicodedata.combining(c)).casefold()


def _is_stop(raw: str, stop_words=()) -> bool:
    """True si el mensaje debe cortar el TTS YA, sin esperar al turno.

    Cubre dos casos:
      - `{"type":"stop"}` (botón/evento explícito de la app).
      - `{"type":"command","text":"para"}`: el micrófono del móvil usa el
        reconocedor de Android, así que «para» llega como **texto**. Si se
        encolara como un turno normal esperaría a que el PC acabe de hablar
        (justo lo contrario de interrumpir).

    Solo se acepta una **palabra suelta** del conjunto: «para la música» sigue
    siendo un comando normal.
    """
    try:
        msg = json.loads(raw)
    except Exception:
        return False
    if not isinstance(msg, dict):
        return False
    if msg.get("type") == "stop":
        return True
    if msg.get("type") != "command":
        return False
    words = _fold(msg.get("text") or "").split()
    return len(words) == 1 and words[0].strip(".,!¡?¿") in stop_words


class GatewayServer:
    """WS /ws + zeroconf. Corre en un hilo daemon dentro del proceso principal."""

    def __init__(self, pipeline, host: str = "0.0.0.0", port: int = 8765,
                 mdns_name: str = "Limits", token_path: str | None = None,
                 app_version: str = "", speak_remote: bool = True,
                 speak_fn=None, stop_fn=None, stop_words=()):
        """
        Args:
            pipeline: callable(text: str, wait_timeout: float | None,
                               speak: bool = True) -> str.
                      Eleva RemoteBusy si no consigue turno a tiempo.
            speak_remote: si False, los turnos remotos NO hablan por los
                          altavoces del PC (modo silencioso en local).
            speak_fn: callable(text) que reproduce la voz (tts.speak). Si se
                      pasa, el gateway habla él mismo DESPUÉS de enviar el
                      texto: la app recibe la respuesta al instante y el orbe
                      anima `speaking_started/finished` mientras suena.
            stop_fn: callable() que corta el TTS en curso (barge-in desde el
                     móvil: mensaje {"type":"stop"} o un comando con una sola
                     palabra de `stop_words`, p. ej. «para» dictado al micro).
        """
        self.pipeline = pipeline
        self.host = host
        self.port = port
        self.mdns_name = mdns_name
        self.speak_remote = speak_remote
        self.speak_fn = speak_fn
        self.stop_fn = stop_fn
        # Palabras sueltas que cortan aunque lleguen como texto (micro del móvil).
        self.stop_words = frozenset(_fold(w).strip() for w in stop_words if w)
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

    # ── pairing ──────────────────────────────────────────────────────────────

    def pairing_uri(self, host: str | None = None) -> str:
        """URI limits://pair?... con la IP LAN real (no 0.0.0.0)."""
        if host:
            ip = host
        elif self.host in ("0.0.0.0", "::"):
            ip = lan_ip() or "127.0.0.1"
        else:
            ip = self.host
        return pairing_uri(ip, self.port, self.token)

    def print_pairing(self, out=print) -> str:
        """QR + token en la terminal para emparejar el móvil sin teclear."""
        if self.host in ("0.0.0.0", "::"):
            ip = lan_ip() or "127.0.0.1"
        else:
            ip = self.host
        return print_pairing(self.port, self.token, host=ip, out=out)

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

    async def _ws_endpoint(self, ws: WebSocket):        # accept() primero: si rechazáramos antes del upgrade, uvicorn responde
        # HTTP 403 y la app no puede distinguir "token malo" de "sin red".
        # Con 4401 el cliente muestra el motivo y ofrece re-emparejar.
        await ws.accept()
        auth = ws.headers.get("authorization", "")
        if auth != f"Bearer {self.token}":
            log.warning("conexión rechazada sin token válido")
            try:
                await ws.send_json(_msg(
                    type="error", err="UNAUTHORIZED",
                    msg="token inválido: escanea el QR del PC (⚙ → Escanear)"))
            except Exception:
                pass
            await ws.close(code=4401, reason="unauthorized")
            return

        await ws.send_json(_msg(type="welcome", version=self.app_version))
        log.info("cliente conectado")

        try:
            pending: set[asyncio.Task] = set()
            while True:
                try:
                    raw = await ws.receive_text()
                except WebSocketDisconnect:
                    break
                # `stop` (barge-in desde el móvil) se atiende YA: si esperara a
                # que termine el turno en curso, no cortaría nada.
                if _is_stop(raw, self.stop_words):
                    await self._handle_stop(ws)
                    continue
                task = asyncio.create_task(self._handle_message(ws, raw))
                pending.add(task)
                task.add_done_callback(pending.discard)
        finally:
            for task in list(pending):
                task.cancel()
            log.info("cliente desconectado")

    async def _handle_stop(self, ws) -> None:
        """Corta el TTS en curso sin tocar el turno (ni el lock) en marcha."""
        if self.stop_fn is not None:
            try:
                await asyncio.to_thread(self.stop_fn)
            except Exception:
                log.warning("stop_fn falló", exc_info=True)
        await ws.send_json(_msg(type="event", kind="stopped"))

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
        elif mtype == "stop":
            await self._handle_stop(ws)
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
            # Si el gateway tiene speak_fn, el pipeline NO habla: se responde
            # primero (texto instantáneo en la app) y se reproduce después,
            # emitiendo speaking_started/finished para animar el orbe.
            inline_speak = self.speak_remote and self.speak_fn is None
            spoken = await asyncio.to_thread(
                self.pipeline, text, TURN_WAIT_TIMEOUT, inline_speak)
            await ws.send_json(_msg(type="response", ok=True, text=spoken))

            if self.speak_remote and self.speak_fn is not None:
                await ws.send_json(_msg(type="event", kind="speaking_started"))
                try:
                    await asyncio.to_thread(self.speak_fn, spoken)
                except Exception:
                    log.warning("TTS remoto falló; la respuesta ya se envió",
                                exc_info=True)
                finally:
                    await ws.send_json(_msg(type="event", kind="speaking_finished"))
        except RemoteBusy:
            await ws.send_json(_msg(
                type="response", ok=False, err="BUSY",
                msg="Estoy atendiendo otro comando. Repite en unos segundos."))
        except Exception:
            log.exception("turno remoto falló")
            await ws.send_json(_msg(
                type="response", ok=False, err="INTERNAL",
                msg="Error interno procesando el comando."))
