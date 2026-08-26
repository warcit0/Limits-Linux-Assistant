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
                "[dim]   Para descargar la voz, mira el Quick Start del README.[/dim]"
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
            import shutil
            import sys
            # Orden: 1) piper del propio venv (motor TTS real), 2) "piper-tts"
            # en PATH, 3) "piper" en PATH — OJO: en Arch /usr/bin/piper es la
            # utilidad de ratones, por eso el venv tiene prioridad absoluta.
            from pathlib import Path
            candidates = [
                str(Path(sys.executable).parent / "piper"),
                shutil.which("piper-tts"),
                shutil.which("piper"),
            ]
            binary = next(
                (c for c in candidates if c and Path(c).exists() and os.access(c, os.X_OK)),
                None,
            )
            if binary is None:
                raise FileNotFoundError("binario piper-tts no encontrado")
            console.print(f"[dim]TTS motor: {binary}[/dim]")
            piper_cmd = [
                binary,
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

            try:
                piper_proc.stdin.write(text.encode("utf-8"))
                piper_proc.stdin.close()
            except BrokenPipeError:
                pass  # aplay murió antes de leer todo; se limpia abajo

            aplay_proc.wait()

            # Reap del proceso piper para evitar zombies
            try:
                piper_proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                piper_proc.kill()
                piper_proc.wait()

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


class VoiceRouter:
    """Elige el motor de voz por respuesta (ver docs/plan-elevenlabs-tts.md).

    Matriz:
      - mode "off" o sin ElevenLabs  → Piper (comportamiento clásico)
      - mode "gemini"               → solo respuestas etiquetadas source="gemini"
      - mode "auto"                 → largo (>= min_chars) a ElevenLabs, resto Piper

    NUNCA falla: cualquier problema del motor natural cae a Piper. Respuestas que
    exceden max_turn_chars se hablan en dos tramos sin cortar frases (primera vía
    API para proteger la cuota, resto vía Piper).
    """

    def __init__(self, piper: TTSEngine, eleven=None,
                 mode: str = "off", min_chars: int = 200,
                 max_turn_chars: int = 1200):
        self.piper = piper
        self.eleven = eleven
        self.mode = mode if mode in ("auto", "gemini", "off") else "off"
        self.min_chars = max(0, min_chars)
        self.max_turn_chars = max(40, max_turn_chars)

    def speak(self, text: str, source: str = "system") -> None:
        if not text or not text.strip():
            return

        engine = self._pick(text, source)
        if engine is not self.eleven:
            self.piper.speak(text)
            return

        from modules.voice_utils import clean_for_voice, split_for_voice
        first, rest = split_for_voice(
            clean_for_voice(text), self.max_turn_chars)
        try:
            self.eleven.speak(first)
        except Exception as e:
            console.print(f"[yellow]ElevenLabs no disponible ({e}); "
                          f"usando Piper.[/yellow]")
            self.piper.speak(first)
        # El tope por turno protege la cuota; el resto sale con la voz local.
        if rest:
            self.piper.speak(rest)

    def _pick(self, text: str, source: str = "system"):
        """Devuelve el motor elegido según modo, origen y longitud."""
        if self.mode == "off" or self.eleven is None:
            return self.piper
        if self.mode == "gemini":
            return self.eleven if source == "gemini" else self.piper
        # mode auto: umbral de longitud sobre el texto limpio
        from modules.voice_utils import clean_for_voice
        return (
            self.eleven
            if len(clean_for_voice(text)) >= self.min_chars
            else self.piper
        )
