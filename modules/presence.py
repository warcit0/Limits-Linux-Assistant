"""Estado visual local; nunca envía texto privado ni concede autorizaciones."""

import array
import fcntl
import json
import logging
import math
import os
import select
import socket
import stat
import struct
import threading
import time
import uuid
from collections import deque
from contextlib import contextmanager
from pathlib import Path

log = logging.getLogger("limits.presencia")
ETIQUETAS = {
    "oculto": "",
    "escuchando": "Te escucho",
    "pensando": "Pensando",
    "investigando": "Investigando",
    "ejecutando": "Trabajando",
    "confirmacion": "Esperando confirmación",
    "hablando": "Hablando",
    "interrumpido": "Detenido",
    "error": "No pude completarlo",
}


class Presencia:
    def __init__(self, ruta, ajustes=None):
        self.ruta = Path(ruta)
        self.ajustes = ajustes or {}
        self.lock = threading.RLock()
        self.fin = threading.Event()
        self.turno = ""
        self.base = "oculto"
        self.activo = False
        self.cancelado = False
        self.detener = None
        self.audio_id = None
        self.envolvente = deque(maxlen=600)
        self.audio_hasta = 0.0
        self.pausado = False
        self.secuencia = 0
        self.ultimo = {}
        self._huella = None
        self.clientes = {}
        self.hilo = None
        self.servidor = None
        self.cerrojo = None
        self.ocultar_en = None
        self._publicar()

    def iniciar(self):
        carpeta = self.ruta.parent
        carpeta.mkdir(mode=0o700, parents=True, exist_ok=True)
        st = carpeta.lstat()
        if (
            not stat.S_ISDIR(st.st_mode)
            or st.st_uid != os.getuid()
            or st.st_mode & 0o077
        ):
            raise PermissionError("La carpeta del widget debe ser privada (0700).")
        fd = os.open(
            str(self.ruta) + ".lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600
        )
        self.cerrojo = os.fdopen(fd, "w")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if self.ruta.exists() or self.ruta.is_symlink():
                st = self.ruta.lstat()
                if not stat.S_ISSOCK(st.st_mode) or st.st_uid != os.getuid():
                    raise PermissionError(
                        "El destino del widget no es un socket propio."
                    )
                self.ruta.unlink()
            self.servidor = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.servidor.bind(str(self.ruta))
            self.inodo = self.ruta.stat().st_ino
            os.chmod(self.ruta, 0o600)
            self.servidor.listen(4)
            self.servidor.setblocking(False)
            self.hilo = threading.Thread(
                target=self._bucle, daemon=True, name="limits-presencia"
            )
            self.hilo.start()
        except BaseException:
            if self.servidor:
                self.servidor.close()
            self.cerrojo.close()
            self.cerrojo = None
            raise
        return self

    def _publicar(self):
        ahora = time.monotonic()
        nivel = 0.0
        while not self.pausado and self.envolvente and self.envolvente[0][0] <= ahora:
            _, nivel = self.envolvente.popleft()
            self.nivel = nivel
        if self.audio_id and not self.pausado:
            nivel = (
                getattr(self, "nivel", 0.0) if ahora <= self.audio_hasta + 0.12 else 0.0
            )
        estado = (
            "hablando"
            if self.audio_id and not self.pausado and not self.cancelado
            else self.base
        )
        if self.ocultar_en is not None and ahora > self.ocultar_en:
            self.base = estado = "oculto"
            self.ocultar_en = None
        huella = (
            estado,
            self.base,
            round(nivel, 2),
            self.turno,
            bool(self.detener),
            self.pausado,
        )
        if huella == self._huella:
            return
        self._huella = huella
        self.secuencia += 1
        self.ultimo = {
            "v": 1,
            "seq": self.secuencia,
            "turno": self.turno,
            "estado": estado,
            "actividad": self.base,
            "etiqueta": ETIQUETAS[estado],
            "nivel": round(nivel, 2),
            "pausado": self.pausado,
            "detenible": bool(self.detener) and not self.cancelado,
            "tiempo": ahora,
            "ajustes": self.ajustes,
        }

    def comenzar(self, detener=None):
        with self.lock:
            self.turno = uuid.uuid4().hex
            self.base, self.activo, self.cancelado = "pensando", True, False
            self.detener = detener
            self.ocultar_en = None
            self.audio_id = None
            self.pausado = False
            self.envolvente.clear()
            self._publicar()
            return self.turno

    def fase(self, estado):
        if estado not in ETIQUETAS:
            return
        with self.lock:
            if self.activo and not self.cancelado:
                self.base = estado
                self._publicar()

    def escucha(self, escuchando):
        with self.lock:
            if not self.activo and not self.audio_id:
                if escuchando:
                    self.antes_escucha = self.base
                    self.base = "escuchando"
                elif self.base == "escuchando":
                    self.base = getattr(self, "antes_escucha", "oculto")
                self._publicar()

    def terminar(self, turno, estado="oculto"):
        with self.lock:
            if turno != self.turno:
                return
            self.activo = False
            self.base = "interrumpido" if self.cancelado else estado
            if self.base != "confirmacion":
                self.detener = None
            self.audio_id = None
            self.envolvente.clear()
            self.ocultar_en = (
                time.monotonic() + 1.5
                if self.base in {"error", "interrumpido"}
                else None
            )
            self._publicar()

    def detener_turno(self, turno):
        with self.lock:
            if turno != self.turno or not self.detener or self.cancelado:
                return False
            self.cancelado = True
            self.base = "interrumpido"
            self.audio_id = None
            self.envolvente.clear()
            self.ocultar_en = time.monotonic() + 1.5
            callback = self.detener
            self._publicar()
        threading.Thread(
            target=self._cancelar_seguro, args=(turno, callback), daemon=True
        ).start()
        return True

    def _cancelar_seguro(self, turno, callback):
        with self.lock:
            # Un clic retrasado no puede cancelar la petición siguiente.
            if turno != self.turno:
                return
            try:
                callback()
            except Exception:
                log.warning(
                    "No se pudo detener el turno desde el widget.", exc_info=True
                )

    def comenzar_audio(self):
        with self.lock:
            if self.cancelado:
                return None
            self.audio_id = uuid.uuid4().hex
            self.envolvente.clear()
            self.audio_hasta = time.monotonic()
            self.nivel = 0.0
            self._publicar()
            return self.audio_id

    def pcm(self, identificador, datos, tasa=22050):
        with self.lock:
            if not identificador or identificador != self.audio_id or self.cancelado:
                return
            muestras = array.array("h", datos[: len(datos) // 2 * 2])
            paso = max(1, int(tasa * 0.04))
            inicio = max(time.monotonic(), self.audio_hasta)
            for i in range(0, len(muestras), paso):
                tramo = muestras[i : i + paso]
                rms = math.sqrt(sum(float(x) * x for x in tramo) / len(tramo)) / 32768
                nivel = min(1.0, math.sqrt(rms) * 2.2)
                self.envolvente.append((inicio + i / tasa, nivel))
            self.audio_hasta = inicio + len(muestras) / tasa

    def terminar_audio(self, identificador):
        with self.lock:
            if identificador and identificador == self.audio_id:
                self.audio_id = None
                self.envolvente.clear()
                self._publicar()

    def pausar(self, valor):
        with self.lock:
            ahora = time.monotonic()
            if valor and not self.pausado:
                self.pausa_en = ahora
            elif not valor and self.pausado:
                delta = ahora - self.pausa_en
                self.envolvente = deque(
                    ((t + delta, n) for t, n in self.envolvente), maxlen=600
                )
                self.audio_hasta += delta
            self.pausado = valor
            self._publicar()

    def _bucle(self):
        while not self.fin.is_set():
            try:
                with self.lock:
                    self._publicar()
                    seq = self.secuencia
                    dato = (
                        json.dumps(self.ultimo, separators=(",", ":")) + "\n"
                    ).encode()
                legibles, _, _ = select.select(
                    [self.servidor, *self.clientes], [], [], 0.04
                )
                if self.servidor in legibles:
                    c, _ = self.servidor.accept()
                    uid = struct.unpack(
                        "3i", c.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12)
                    )[1]
                    if uid != os.getuid() or len(self.clientes) >= 4:
                        c.close()
                    else:
                        c.settimeout(0.01)
                        self.clientes[c] = {"seq": -1, "buffer": b""}
                        # Procesar una orden enviada antes de cerrar: el primer
                        # snapshot podría fallar con EPIPE y perder ese stop.
                        if select.select([c], [], [], 0)[0]:
                            legibles.append(c)
                    legibles.remove(self.servidor)
                for c, datos in list(self.clientes.items()):
                    try:
                        if c in legibles:
                            bloque = c.recv(1024)
                            if not bloque:
                                raise ConnectionError()
                            datos["buffer"] += bloque
                            if len(datos["buffer"]) > 2048:
                                raise ConnectionError()
                            while b"\n" in datos["buffer"]:
                                linea, datos["buffer"] = datos["buffer"].split(b"\n", 1)
                                try:
                                    mensaje = json.loads(linea)
                                    if (
                                        isinstance(mensaje, dict)
                                        and mensaje.get("cmd") == "stop"
                                    ):
                                        self.detener_turno(mensaje.get("turno"))
                                except (ValueError, TypeError):
                                    pass
                        if datos["seq"] != seq:
                            c.sendall(dato)
                            datos["seq"] = seq
                    except OSError:
                        c.close()
                        del self.clientes[c]
            except OSError:
                if not self.fin.is_set():
                    log.warning("Socket visual desconectado.")
                break

    def cerrar(self):
        self.fin.set()
        if self.hilo:
            self.hilo.join(1)
        for c in self.clientes:
            c.close()
        if self.servidor:
            self.servidor.close()
        if self.cerrojo:
            if self.ruta.exists() and self.ruta.stat().st_ino == self.inodo:
                self.ruta.unlink()
            self.cerrojo.close()
            self.cerrojo = None


_actual = None


def instalar(presencia):
    global _actual
    _actual = presencia


def obtener():
    return _actual


def fase(estado):
    if _actual:
        _actual.fase(estado)


def escucha(valor):
    if _actual:
        _actual.escucha(valor)


@contextmanager
def actividad(estado):
    bus = _actual
    anterior = bus.base if bus else None
    if bus:
        bus.fase(estado)
    try:
        yield
    finally:
        if bus and bus is _actual:
            bus.fase(anterior)
