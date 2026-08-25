"""
Módulo STT — Speech to Text usando faster-whisper
Transcribe audio del micrófono a texto en tiempo real.
Corre 100% local, sin enviar audio a la nube.

Modelos disponibles (en orden de velocidad/precisión):
  tiny    → ~1GB RAM, muy rápido, menos preciso
  base    → ~1GB RAM, buena velocidad, aceptable precisión
  small   → ~2GB RAM, balance ideal                         ← RECOMENDADO
  medium  → ~5GB RAM, muy preciso, más lento
  large-v3→ ~10GB RAM, mejor precisión, requiere GPU
"""

import io
import numpy as np
import pyaudio
import wave
import webrtcvad
from faster_whisper import WhisperModel
from rich.console import Console

console = Console()


class STTEngine:
    def __init__(
        self,
        model_size: str = "small",
        language: str = "es",
        device: str = "cpu",
        input_device_index: int = None,
    ):
        """
        Args:
            model_size:          Tamaño del modelo Whisper (tiny/base/small/medium)
            language:            Código de idioma (es=español, en=inglés, None=autodetect)
            device:              'cpu' o 'cuda' si tienes GPU NVIDIA
            input_device_index:  Índice del micrófono. None = dispositivo default del sistema.
        """
        console.print(f"[cyan]Cargando modelo Whisper '{model_size}'...[/cyan]")

        self.model = WhisperModel(
            model_size,
            device=device,
            compute_type="int8",  # int8 = menos RAM, suficiente precisión
        )
        self.language = language
        self.input_device_index = input_device_index

        # Configuración de audio
        self.RATE = 16000          # Hz requerido por Whisper
        self.CHUNK = 480           # 30ms chunks (requerido por webrtcvad)
        self.FORMAT = pyaudio.paInt16
        self.CHANNELS = 1
        self.SILENCE_THRESHOLD = 30  # frames de silencio antes de cortar (30 × 30ms = 900ms)
        self.MAX_DURATION = 10       # segundos máximos de grabación
        self.NO_SPEECH_TIMEOUT = 5   # segundos sin detectar voz antes de abandonar

        # VAD (Voice Activity Detection) para detectar cuando hablas
        self.vad = webrtcvad.Vad(2)  # agresividad 0-3, 2 es buen balance

        self.audio = pyaudio.PyAudio()
        console.print("[green]✓ STT listo[/green]")

    def record_until_silence(self) -> bytes | None:
        """
        Graba audio desde el micrófono hasta detectar silencio.
        Returns: bytes del audio grabado en formato WAV, o None si no se detectó voz.
        """
        stream = self.audio.open(
            format=self.FORMAT,
            channels=self.CHANNELS,
            rate=self.RATE,
            input=True,
            input_device_index=self.input_device_index,
            frames_per_buffer=self.CHUNK,
        )

        frames = []
        silent_frames = 0
        speaking = False
        total_frames = 0
        no_speech_frames = 0
        max_frames = int(self.RATE / self.CHUNK * self.MAX_DURATION)
        no_speech_max = int(self.RATE / self.CHUNK * self.NO_SPEECH_TIMEOUT)

        console.print("[yellow]🎙️  Escuchando...[/yellow]")

        while total_frames < max_frames:
            data = stream.read(self.CHUNK, exception_on_overflow=False)
            frames.append(data)
            total_frames += 1

            try:
                is_speech = self.vad.is_speech(data, self.RATE)
            except Exception:
                is_speech = False

            if is_speech:
                speaking = True
                silent_frames = 0
                no_speech_frames = 0
            elif speaking:
                silent_frames += 1
                if silent_frames > self.SILENCE_THRESHOLD:
                    break
            else:
                # Aún no ha empezado a hablar
                no_speech_frames += 1
                if no_speech_frames > no_speech_max:
                    console.print("[dim]Sin voz detectada, cancelando.[/dim]")
                    stream.stop_stream()
                    stream.close()
                    return None

        stream.stop_stream()
        stream.close()

        if not speaking:
            return None

        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, "wb") as wf:
            wf.setnchannels(self.CHANNELS)
            wf.setsampwidth(self.audio.get_sample_size(self.FORMAT))
            wf.setframerate(self.RATE)
            wf.writeframes(b"".join(frames))

        return wav_buffer.getvalue()

    def transcribe(self, audio_bytes: bytes) -> str:
        """
        Transcribe audio WAV a texto.
        Args:
            audio_bytes: Audio en formato WAV como bytes
        Returns:
            Texto transcrito (puede ser vacío si no hay voz)
        """
        audio_buffer = io.BytesIO(audio_bytes)

        segments, info = self.model.transcribe(
            audio_buffer,
            language=self.language,
            beam_size=5,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=500),
            initial_prompt="Limits, Firefox, Chromium, Spotify, Discord, Slack, Obsidian, Thunar, Steam, VS Code, Code, Neovim, Ghostty, Docker, GitHub, Linux, Arch, CachyOS",
        )

        text = " ".join([segment.text for segment in segments]).strip()

        if text:
            console.print(f"[blue]📝 Transcrito:[/blue] {text}")

        return text

    def listen_and_transcribe(self) -> str:
        """Helper: graba y transcribe en un solo paso. Retorna '' si no hubo voz."""
        audio = self.record_until_silence()
        if audio is None:
            return ""
        return self.transcribe(audio)

    def cleanup(self):
        """Libera recursos de audio."""
        self.audio.terminate()
