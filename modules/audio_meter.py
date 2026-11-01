"""Reproduce PCM local y mide solo la voz generada, sin abrir el micrófono."""

import os
import select
import subprocess
import threading
import time


def reproducir_pcm(productor, stop_event=None, on_audio_start=None):
    from modules import presence
    from modules.tts import _register, _terminate, _unregister, wait_with_stop

    bus = presence.obtener()
    identificador = None
    reproductor = None
    hilo = None
    errores = []
    try:
        limite = time.monotonic() + 30
        primero = b""
        while time.monotonic() < limite:
            if stop_event is not None and stop_event.is_set():
                return "interrupted"
            if select.select([productor.stdout], [], [], 0.05)[0]:
                primero = os.read(productor.stdout.fileno(), 1764)
                break
        if not primero:
            return "error"
        reproductor = subprocess.Popen(
            ["aplay", "-r", "22050", "-f", "S16_LE", "-t", "raw", "-"],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        _register(reproductor)
        if bus:
            identificador = bus.comenzar_audio()

        def alimentar():
            try:
                bloque = primero
                inicial = True
                while bloque:
                    reproductor.stdin.write(bloque)
                    reproductor.stdin.flush()
                    if inicial and on_audio_start:
                        on_audio_start()
                    inicial = False
                    if bus:
                        bus.pcm(identificador, bloque)
                    bloque = productor.stdout.read(1764)
            except (BrokenPipeError, OSError):
                errores.append(True)
            finally:
                try:
                    reproductor.stdin.close()
                except OSError:
                    pass

        hilo = threading.Thread(target=alimentar, daemon=True)
        hilo.start()
        if wait_with_stop(reproductor, stop_event):
            return "interrupted"
        productor.wait(timeout=10)
        return (
            "ok"
            if not errores and productor.returncode == 0 and reproductor.returncode == 0
            else "error"
        )
    finally:
        if reproductor:
            if reproductor.poll() is None:
                _terminate(reproductor)
            _unregister(reproductor)
        if productor.poll() is None:
            _terminate(productor)
        if hilo:
            hilo.join(2)
        if bus:
            bus.terminar_audio(identificador)


def reproducir_archivo(ruta, stop_event=None, on_audio_start=None):
    from modules.tts import _register, _terminate, _unregister

    proceso = subprocess.Popen(
        [
            "ffmpeg",
            "-nostdin",
            "-loglevel",
            "error",
            "-i",
            str(ruta),
            "-f",
            "s16le",
            "-ar",
            "22050",
            "-ac",
            "1",
            "pipe:1",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    _register(proceso)
    try:
        return reproducir_pcm(proceso, stop_event, on_audio_start)
    finally:
        if proceso.poll() is None:
            _terminate(proceso)
        _unregister(proceso)
        proceso.stdout.close()
