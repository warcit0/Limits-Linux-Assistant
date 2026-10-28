"""Barge-in (P0-4): interrumpir al asistente mientras habla.

Mientras el TTS reproduce, un hilo escucha con VAD. Si hay voz sostenida
(`BARGEIN_MIN_MS`, no un golpe), se corta el audio y se transcribe lo dicho:

  - «para» / «cállate» / «stop»  → se corta y no se hace nada más
  - eco de los altavoces         → se descarta (no se ejecuta)
  - cualquier otra frase         → se guarda en `pending_text` y el bucle la
                                    procesa como el siguiente turno

El `stop_event` se limpia al empezar cada `speak()`: si no, todo turno
posterior se cortaría al instante.
"""

from __future__ import annotations

import io
import os
import re
import threading
import time
import unicodedata
import wave
from collections import deque

from rich.console import Console

console = Console()


def _plain(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", str(text))
    return "".join(c for c in nfkd if not unicodedata.combining(c)).casefold().strip()


def looks_like_echo(heard: str, spoken: str, threshold: float = 0.75) -> bool:
    """True si lo oído está compuesto casi solo por palabras del TTS.

    Exige ≥2 palabras: un «para» suelto del usuario no puede confundirse con
    eco, y una frase de ≥3 palabras del propio TTS sí se detecta.
    """
    heard_words = set(re.findall(r"\w+", _plain(heard)))
    if len(heard_words) < 2:
        return False
    spoken_words = set(re.findall(r"\w+", _plain(spoken)))
    if not heard_words:
        return True
    return len(heard_words & spoken_words) / len(heard_words) >= threshold


def classify_interruption(heard: str, spoken: str, keywords=(),
                          echo_threshold: float = 0.75) -> str:
    """Devuelve "stop", "echo" o "command".

    El eco se comprueba ANTES que las palabras clave: el propio TTS puede
    decir «para ver si…» y eso no es una orden del usuario.
    """
    plain = _plain(heard)
    if not plain:
        return "echo"
    if looks_like_echo(heard, spoken, echo_threshold):
        return "echo"
    words = set(re.findall(r"\w+", plain))
    for keyword in keywords:
        key = _plain(keyword).strip()
        if not key:
            continue
        if key in words or (len(key) > 3 and key in plain):
            return "stop"
    if len(words) < 2:
        return "echo"
    return "command"


class SpeechController:
    def __init__(self, voice, stt=None, enabled: bool = True,
                 keywords=(), min_ms: int = 350,
                 echo_threshold: float = 0.75,
                 silence_ms: int = 600, max_utterance_s: float = 6.0):
        self.voice = voice
        self.stt = stt
        self.enabled = bool(enabled) and stt is not None
        self.keywords = tuple(keywords)
        self.min_ms = max(90, int(min_ms))
        self.echo_threshold = echo_threshold
        self.silence_ms = max(180, int(silence_ms))
        self.max_utterance_s = max_utterance_s
        self._stop_event = threading.Event()
        self.pending_text = ""
        self.last_result = "ok"

    # ── API ─────────────────────────────────────────────────────────────────
    def speak(self, text: str, source: str = "system") -> str:
        """Habla y escucha a la vez. Devuelve "ok" o "interrupted"."""
        self.pending_text = ""
        self._stop_event.clear()

        if not self.enabled:
            self.last_result = self.voice.speak(
                text, source, stop_event=self._stop_event) or "ok"
            return self.last_result

        box: dict = {}
        debug = __debug__ and bool(os.getenv("LIMITS_BARGEIN_DEBUG"))

        def _tts():
            try:
                box["r"] = self.voice.speak(text, source,
                                            stop_event=self._stop_event)
            except Exception:
                if debug:
                    import traceback
                    console.print(traceback.format_exc())
                box["r"] = "error"

        thread = threading.Thread(target=_tts, daemon=True)
        thread.start()
        heard = self._listen(thread, text)
        # La pausa/reanudación alarga la reproducción: espera de verdad a que
        # termine, no un tiempo fijo que puede quedarse corto.
        deadline = time.monotonic() + 120
        while thread.is_alive() and time.monotonic() < deadline:
            thread.join(timeout=0.2)
        if debug:
            console.print(f"[dim]bargein: tts={box.get('r')!r} "
                          f"oyó={heard!r}[/dim]")
        self.last_result = box.get("r", "error")

        if not heard:
            return self.last_result

        verdict = classify_interruption(heard, text, self.keywords,
                                        self.echo_threshold)
        if verdict == "stop":
            console.print("[yellow]✋ Interrumpido: no hago nada más.[/yellow]")
            return "interrupted"
        if verdict == "command":
            self.pending_text = heard
            console.print(f"[cyan]↪ Sigo con lo que dijiste:[/cyan] {heard}")
            return "interrupted"
        console.print("[dim](eco del altavoz descartado)[/dim]")
        return "interrupted"

    def stop(self) -> None:
        """Corta el TTS en curso (p. ej. mensaje `stop` del móvil)."""
        self._stop_event.set()

    # ── Audio ───────────────────────────────────────────────────────────────
    def _listen(self, tts_thread: threading.Thread, spoken: str) -> str:
        if self.stt is None:
            return ""
        import pyaudio  # noqa: F401  (valida que el backend existe)

        debug = __debug__ and bool(os.getenv("LIMITS_BARGEIN_DEBUG"))
        stt = self.stt
        need = max(1, int(round(self.min_ms / 30.0)))
        # VAD propio más sensible que el del STT: buscamos una interjección
        # corta («para»), no una frase completa.
        try:
            import webrtcvad
            vad = webrtcvad.Vad(int(os.getenv("LIMITS_BARGEIN_VAD_MODE", "1")))
        except Exception:
            vad = stt.vad
        # Ventana deslizante: ~1/4 de tramas con voz basta. Exigir 12 seguidas
        # hacía inalcanzable un «para» corto (los micros baratos dan rachas 4-6).
        trigger_at = max(2, need // 4)
        from modules.tts import pause_all, resume_all

        stream = None
        try:
            stream = stt.audio.open(
                format=stt.FORMAT,
                channels=stt.CHANNELS,
                rate=stt.RATE,
                input=True,
                input_device_index=stt.input_device_index,
                frames_per_buffer=stt.CHUNK,
            )
            # Se sigue escuchando DESPUÉS de un eco: si no, una tos al empezar
            # dejaría el resto de la respuesta sin barge-in.
            next_guard = 0.4
            while tts_thread.is_alive():
                window: deque[bool] = deque(maxlen=need)
                pre_roll: deque[bytes] = deque(maxlen=need + 10)
                started = time.monotonic()
                guard_s = next_guard
                next_guard = 0.4
                triggered = False

                while tts_thread.is_alive():
                    try:
                        data = stream.read(stt.CHUNK, exception_on_overflow=False)
                    except Exception:
                        if debug:
                            console.print("[dim]bargein: micro falló[/dim]")
                        return ""
                    pre_roll.append(data)
                    # Ignora el «pop» de aplay al abrir el dispositivo.
                    if time.monotonic() - started < guard_s:
                        continue
                    try:
                        is_speech = vad.is_speech(data, stt.RATE)
                    except Exception:
                        is_speech = False
                    window.append(is_speech)
                    if sum(window) >= trigger_at:
                        triggered = True
                        break

                if not triggered:
                    if debug:
                        console.print("[dim]bargein: sin voz (fin del TTS)[/dim]")
                    return ""

                pause_all()
                frames = list(pre_roll)
                silent = 0
                total = 0
                max_frames = int(stt.RATE / stt.CHUNK * self.max_utterance_s)
                silence_limit = int(self.silence_ms / 30.0)
                while total < max_frames:
                    try:
                        data = stream.read(stt.CHUNK, exception_on_overflow=False)
                    except Exception:
                        break
                    frames.append(data)
                    total += 1
                    try:
                        is_speech = stt.vad.is_speech(data, stt.RATE)
                    except Exception:
                        is_speech = False
                    silent = 0 if is_speech else silent + 1
                    if silent > silence_limit:
                        break

                try:
                    heard = stt.transcribe(self._wav(stt, frames))
                except Exception:
                    # Nunca dejar el TTS pausado para siempre por un fallo del STT.
                    if debug:
                        console.print("[dim]bargein: falló la transcripción[/dim]")
                    resume_all()
                    continue
                if debug:
                    console.print(f"[dim]bargein oyó: {heard!r} "
                                  f"(eco={looks_like_echo(heard, spoken)})[/dim]")
                if not heard.strip() or looks_like_echo(heard, spoken):
                    resume_all()
                    # Enfriamiento: evita el bucle pausa/reanuda si los
                    # altavoces se oyen a través del micro.
                    next_guard = 1.2
                    continue
                self._stop_event.set()
                return heard
            return ""
        finally:
            if stream is not None:
                try:
                    stream.stop_stream()
                    stream.close()
                except Exception:
                    pass

    @staticmethod
    def _wav(stt, frames: list[bytes]) -> bytes:
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wf:
            wf.setnchannels(stt.CHANNELS)
            wf.setsampwidth(stt.audio.get_sample_size(stt.FORMAT))
            wf.setframerate(stt.RATE)
            wf.writeframes(b"".join(frames))
        return buffer.getvalue()
