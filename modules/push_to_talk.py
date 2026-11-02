"""Control local de pulsar para hablar; no abre dispositivos de audio."""
import fcntl
import os
from pathlib import Path
import select
import socket
import time


class PushToTalk:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(self.path.parent, 0o700)
        self.lock = open(self.path.with_suffix('.lock'), 'w')
        fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        self.path.unlink(missing_ok=True)
        self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        self.socket.bind(str(self.path))
        os.chmod(self.path, 0o600)
        self.pulsada = False

    def _recibir(self, timeout=0):
        if select.select([self.socket], [], [], timeout)[0]:
            return self.socket.recv(64)
        return None

    def esperar(self, detener):
        # Descartar pulsaciones durante tareas anteriores, nunca encolarlas.
        while self._recibir() is not None:
            pass
        while not detener():
            if self._recibir(.2) == b'press':
                self.expirada = False
                self.pulsada = True
                self.limite = time.monotonic() + 30
                return True
        return False

    def sostenida(self):
        mensaje = self._recibir()
        while mensaje is not None:
            if mensaje == b'release':
                self.pulsada = False
            mensaje = self._recibir()
        if time.monotonic() >= self.limite:
            self.expirada = True
            self.pulsada = False
        return self.pulsada

    def cerrar(self):
        self.socket.close()
        self.path.unlink(missing_ok=True)
        self.lock.close()
