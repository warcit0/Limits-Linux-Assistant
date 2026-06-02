"""
Módulo TTS — Text to Speech usando piper-tts
Sintetiza respuestas de texto en voz natural en español.
Corre 100% local, sin latencia de red.

Voces disponibles en español:
  es_ES-davefx-medium  → voz masculina, España
  es_MX-ald-medium     → voz masculina, México
  es_ES-sharvard-high  → voz femenina, España
"""

import subprocess
import os
from rich.console import Console

console = Console()


class TTSEngine:
    def __init__(self, voice_model: str = None, voice_speed: float = 1.0, speaker: int = None):
        self.voice_model = voice_model or os.path.expanduser(
            "~/.local/share/piper/es_ES-davefx-medium.onnx"
        )
        self.voice_speed = voice_speed
        self.speaker = speaker
        self._verify_voice()

    def _verify_voice(self):
        if not os.path.exists(self.voice_model):
            console.print(f"[yellow]⚠️  Voz piper no encontrada: {self.voice_model}[/yellow]")
            console.print("[yellow]   Usando espeak-ng como fallback temporal.[/yellow]")
            console.print(
                "[dim]   Para descargar la voz, ejecuta: limits-linux-setup.sh[/dim]"
            )
        else:
            console.print("[green]✓ TTS listo[/green]")

    def speak(self, text: str) -> None:
        if not text or not text.strip():
            return

        console.print(f"[magenta]🔊 Limits:[/magenta] {text}")

        if os.path.exists(self.voice_model):
            self._speak_piper(text)
        else:
            self._speak_espeak(text)

    def _speak_piper(self, text: str) -> None:
        """Síntesis de voz con piper-tts (calidad alta, local)."""
        try:
            piper_cmd = [
                "piper-tts",
                "--model", self.voice_model,
                "--output-raw",
                "--length-scale", str(1.0 / self.voice_speed),
            ]
            if self.speaker is not None:
                piper_cmd.extend(["--speaker", str(self.speaker)])
                
            aplay_cmd = ["aplay", "-r", "22050", "-f", "S16_LE", "-t", "raw", "-"]

            piper_proc = subprocess.Popen(
                piper_cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
            aplay_proc = subprocess.Popen(
                aplay_cmd,
                stdin=piper_proc.stdout,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            piper_proc.stdin.write(text.encode("utf-8"))
            piper_proc.stdin.close()
            aplay_proc.wait()

        except FileNotFoundError:
            console.print("[yellow]piper no encontrado, usando espeak-ng...[/yellow]")
            self._speak_espeak(text)
        except Exception as e:
            console.print(f"[red]Error en TTS: {e}[/red]")

    def _speak_espeak(self, text: str) -> None:
        """Fallback con espeak-ng (baja calidad pero siempre disponible)."""
        try:
            subprocess.run(
                ["espeak-ng", "-v", "es", "-s", "150", text],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            console.print("[red]⚠️  espeak-ng tampoco disponible. Sin audio.[/red]")
