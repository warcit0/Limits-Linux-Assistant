"""Eventos de texto y audio progresivo con cancelación y memoria acotada."""

import json
import logging
import os
import queue
import re
import signal
import subprocess
import tempfile
import threading
import time

from modules.agent_providers import Cancelado, ErrorProveedor
from modules.voice_utils import clean_for_voice

log = logging.getLogger("limits.streaming")


def proceso_eventos(argumentos, callback, cancelar, timeout):
    """Lee NDJSON sin bloquear la cancelación; el daemon conserva su navegador."""
    eventos = queue.Queue(maxsize=64)
    cerrado = threading.Event()
    with tempfile.TemporaryFile() as errores:
        proceso = subprocess.Popen(
            argumentos,
            stdout=subprocess.PIPE,
            stderr=errores,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
        fin = time.monotonic() + timeout

        def leer():
            try:
                while linea := proceso.stdout.readline(131073):
                    if len(linea) > 131072:
                        raise ValueError("Evento demasiado largo")
                    while not cerrado.is_set():
                        try:
                            eventos.put(linea, timeout=0.05)
                            break
                        except queue.Full:
                            pass
            finally:
                try:
                    eventos.put(None, timeout=1)
                except queue.Full:
                    pass

        hilo = threading.Thread(target=leer, daemon=True)
        hilo.start()
        final = None
        cantidad = 0
        try:
            while True:
                if cancelar is not None and cancelar.is_set():
                    raise Cancelado("Tarea cancelada.")
                if time.monotonic() > fin:
                    raise ErrorProveedor("Gemini tardó demasiado en responder.")
                try:
                    linea = eventos.get(timeout=0.05)
                except queue.Empty:
                    if not hilo.is_alive():
                        break
                    continue
                if linea is None:
                    break
                cantidad += len(linea)
                if cantidad > 2_000_000:
                    raise ErrorProveedor("El flujo de Gemini superó su límite.")
                try:
                    evento = json.loads(linea)
                except (ValueError, UnicodeError):
                    continue
                if not isinstance(evento, dict):
                    continue
                if evento.get("v") != 1:
                    if evento.get("ok") is False and isinstance(evento.get("err"), str):
                        final = evento
                    continue
                if evento.get("type") == "final":
                    final = evento
                elif evento.get("type") == "error":
                    final = {"ok": False, "err": evento.get("code", "EMPTY")}
                callback(evento)
            if not final:
                raise ErrorProveedor(
                    "Gemini terminó sin confirmar una respuesta completa."
                )
            return subprocess.CompletedProcess(
                argumentos, proceso.wait(timeout=1), json.dumps(final), ""
            )
        finally:
            cerrado.set()
            if proceso.poll() is None:
                os.killpg(proceso.pid, signal.SIGINT)
                try:
                    proceso.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    os.killpg(proceso.pid, signal.SIGKILL)
                    proceso.wait()
            proceso.stdout.close()
            hilo.join(timeout=2)


class FrasesProgresivas:
    """Publica solo prefijos completos; no repite frases ni habla código/URLs."""

    def __init__(self, emitir):
        self.emitir = emitir
        self.emitido = ""
        self.ultimo = ""
        self.revisado = False

    def recibir(self, texto, final=False):
        if not isinstance(texto, str) or self.revisado:
            return
        texto = re.sub(r"```.*?(?:```|$)", "", texto, flags=re.S)
        texto = re.sub(r"(?m)^[^.\n:?!]{1,60}\n(?:\+\s*\d+\s*\n)?(?=\n)", "", texto)
        texto = re.sub(r"https?://\S+", "", texto)
        texto = re.sub(r"\b(?:Fuentes|Referencias)(?: consultadas)?\s*:\s*", "", texto)
        texto = re.sub(r"\s+", " ", clean_for_voice(texto)).strip()
        # El DOM puede retirar espacios entre nodos al cerrar la generación.
        # Comparar letras/puntuación conserva las revisiones de contenido y evita
        # confundir esa serialización con una corrección de hechos.
        emitido = re.sub(r"\s", "", self.emitido)
        compacto = re.sub(r"\s", "", texto)
        if emitido and not compacto.startswith(emitido):
            self.revisado = True
            self.ultimo = texto
            return
        self.ultimo = texto
        inicio = 0
        if emitido:
            inicio = list(re.finditer(r"\S", texto))[len(emitido) - 1].end()
        resto = texto[inicio:]
        limites = list(re.finditer(r"[.!?](?:\s|$)|\n\n", resto))
        if not limites and not final:
            return
        corte = len(resto) if final else limites[-1].end()
        bloque = resto[:corte]
        if not final and re.fullmatch(
            r"Publicaci[oó]n\s*:\s*[\d./-]+[.!]?\s*", bloque, re.I
        ):
            return
        # Un bloque de código abierto se retiene entero hasta el final y se omite.
        inicio_codigo = bloque.find("```")
        if inicio_codigo >= 0:
            corte = inicio_codigo
            bloque = bloque[:corte]
        self.emitido = texto[:inicio + corte]
        bloque = re.sub(r"https?://\S+", "", bloque)
        bloque = clean_for_voice(bloque)
        if bloque.strip() and not re.fullmatch(
            r"(?:Fuentes|Referencias)\s*:?\s*", bloque, re.I
        ):
            self.emitir(bloque.strip())


class FlujoVoz:
    """Una voz y un oyente durante generación, esperas y reproducción."""

    def __init__(self, speech, cancelar, vigente):
        self.speech = speech
        self.cancelar = cancelar
        self.vigente = vigente
        self.cola = queue.Queue(maxsize=32)
        self.fin = threading.Event()
        self.error = None
        self.actual = ""
        self.inicio = time.monotonic()
        self.primer_audio = None
        self.metricas = []
        speech.finalizar_espera()
        speech._stop_event.clear()
        speech.pending_text = ""

        class Parada:
            def is_set(_):
                return self.fin.is_set() or speech._stop_event.is_set() or not vigente()

        self.parada = Parada()

        def reproducir():
            try:
                while not self.parada.is_set():
                    try:
                        entrada = self.cola.get(timeout=0.05)
                    except queue.Empty:
                        continue
                    if entrada is None:
                        break
                    texto, recibido, tipo = entrada
                    if self.parada.is_set():
                        break
                    self.actual = texto
                    motor = getattr(speech.voice, "piper", speech.voice)
                    metrica = {
                        "tipo": tipo,
                        "recibido_s": round(recibido - self.inicio, 3),
                        "sintesis_s": round(time.monotonic() - self.inicio, 3),
                    }
                    anterior = getattr(motor, "on_audio_start", None)

                    def audio_iniciado():
                        ahora = time.monotonic()
                        if self.primer_audio is None:
                            self.primer_audio = ahora
                        metrica["pcm_s"] = round(ahora - self.inicio, 3)
                        metrica["latencia_desde_frase_s"] = round(ahora - recibido, 3)
                        log.info(
                            "voz flujo tipo=%s pcm_s=%.3f latencia_frase_s=%.3f",
                            tipo,
                            ahora - self.inicio,
                            ahora - recibido,
                        )

                    motor.on_audio_start = audio_iniciado
                    try:
                        resultado = motor.speak(
                            texto, source="gemini", stop_event=self.parada
                        )
                    finally:
                        motor.on_audio_start = anterior
                        self.metricas.append(metrica)
                    if resultado == "error":
                        raise RuntimeError(
                            "El motor de voz no pudo reproducir el fragmento."
                        )
                    if resultado == "interrupted":
                        cancelar()
                        break
            except BaseException as e:
                self.error = e
                cancelar()

        self.hilo = threading.Thread(target=reproducir, daemon=True)
        self.hilo.start()

        def escuchar():
            from modules.speech_controller import classify_interruption

            texto = speech._listen(self.hilo, lambda: self.actual)
            if texto and vigente() and not self.fin.is_set():
                if (
                    classify_interruption(texto, self.actual, speech.keywords)
                    == "command"
                ):
                    speech.pending_text = texto
                if classify_interruption(texto, self.actual, speech.keywords) != "echo":
                    cancelar()

        self.oyente = None
        if speech.enabled:
            self.oyente = threading.Thread(target=escuchar, daemon=True)
            self.oyente.start()

    def decir(self, texto, tipo="contenido"):
        while not self.parada.is_set():
            try:
                self.cola.put(
                    (texto, time.monotonic(), tipo) if texto is not None else None,
                    timeout=0.05,
                )
                return
            except queue.Full:
                continue

    def cerrar(self):
        self.decir(None)
        limite = time.monotonic() + 180
        while self.hilo.is_alive() and time.monotonic() < limite:
            self.hilo.join(0.05)
        if self.hilo.is_alive():
            self.fin.set()
            self.cancelar()
            self.hilo.join(5)
        if self.oyente:
            self.oyente.join(15)
        if self.hilo.is_alive() or (self.oyente and self.oyente.is_alive()):
            raise RuntimeError("El flujo no liberó el audio o el micrófono.")
        if self.error:
            raise RuntimeError("Falló el audio progresivo.") from self.error

    def descartar_pendientes(self):
        while True:
            try:
                self.cola.get_nowait()
            except queue.Empty:
                return
