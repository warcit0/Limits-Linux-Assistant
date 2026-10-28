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
import signal
import threading
import time
from rich.console import Console

console = Console()


def _terminate(proc: subprocess.Popen | None) -> None:
    """Corta un proceso de audio sin dejar zombis ni chasquidos.

    Si está pausado (SIGSTOP por el barge-in), primero se reanuda: un proceso
    detenido no atiende SIGTERM hasta recibir SIGCONT.
    """
    if proc is None:
        return
    try:
        if proc.stdin is not None and not proc.stdin.closed:
            try:
                proc.stdin.close()
            except Exception:
                pass
        try:
            proc.send_signal(signal.SIGCONT)
        except Exception:
            pass
        proc.terminate()
        proc.wait(timeout=0.5)
    except Exception:
        try:
            proc.send_signal(signal.SIGCONT)
        except Exception:
            pass
        try:
            proc.kill()
        except Exception:
            pass


# Procesos de audio vivos: permiten "pausar" el TTS para decidir si lo que
# oye el micro es eco (se reanuda) o el usuario (se corta). Sin esto, el
# asistente se cortaría a sí mismo en cada frase.
_ACTIVE_PROCS: set = set()
_ACTIVE_LOCK = threading.Lock()


def _register(proc) -> None:
    with _ACTIVE_LOCK:
        _ACTIVE_PROCS.add(proc)


def _unregister(proc) -> None:
    with _ACTIVE_LOCK:
        _ACTIVE_PROCS.discard(proc)


def pause_all() -> None:
    """Silencia el TTS al instante (SIGSTOP) sin perder la posición."""
    with _ACTIVE_LOCK:
        for proc in list(_ACTIVE_PROCS):
            try:
                if proc.poll() is None:
                    proc.send_signal(signal.SIGSTOP)
            except Exception:
                pass


def resume_all() -> None:
    with _ACTIVE_LOCK:
        for proc in list(_ACTIVE_PROCS):
            try:
                if proc.poll() is None:
                    proc.send_signal(signal.SIGCONT)
            except Exception:
                pass


def wait_with_stop(proc: subprocess.Popen, stop_event=None,
                   timeout: float | None = None) -> bool:
    """Espera a `proc`. Devuelve True si `stop_event` pidió cortar.

    Bucle de 50 ms (no `wait()` bloqueante): es lo que permite que «para»
    corte en < 500 ms sin matar el proceso a lo bruto.
    """
    deadline = time.monotonic() + timeout if timeout else None
    while proc.poll() is None:
        if stop_event is not None and stop_event.is_set():
            _terminate(proc)
            return True
        if deadline is not None and time.monotonic() > deadline:
            _terminate(proc)
            return False
        time.sleep(0.05)
    return False


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

    def speak(self, text: str, source: str = "system", stop_event=None) -> str:
        """Habla `text`. Devuelve "ok" | "interrupted" | "error".

        `source` se acepta por compatibilidad con `VoiceRouter` (Piper ignora
        si la respuesta viene de Gemini o del sistema).
        """
        if not text or not text.strip():
            return "ok"

        console.print(f"[magenta]🔊 Limits:[/magenta] {text}")

        if os.path.exists(self.voice_model):
            return self._speak_piper(text, stop_event)
        return self._speak_espeak(text, stop_event)

    def _speak_piper(self, text: str, stop_event=None) -> str:
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
            _register(piper_proc)
            _register(aplay_proc)

            try:
                piper_proc.stdin.write(text.encode("utf-8"))
                piper_proc.stdin.close()
            except BrokenPipeError:
                pass  # aplay murió antes de leer todo; se limpia abajo

            try:
                interrupted = wait_with_stop(aplay_proc, stop_event)

                if interrupted:
                    _terminate(piper_proc)
                    console.print("[yellow]⏹ TTS interrumpido.[/yellow]")
                    return "interrupted"

                # Reap del proceso piper para evitar zombies
                try:
                    piper_proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    piper_proc.kill()
                    piper_proc.wait()
                return "ok"
            finally:
                _unregister(aplay_proc)
                _unregister(piper_proc)

        except FileNotFoundError:
            console.print("[yellow]piper no encontrado, usando espeak-ng...[/yellow]")
            return self._speak_espeak(text, stop_event)
        except Exception as e:
            console.print(f"[red]Error en TTS: {e}[/red]")
            return "error"

    def _speak_espeak(self, text: str, stop_event=None) -> str:
        """Fallback con espeak-ng (baja calidad pero siempre disponible)."""
        try:
            proc = subprocess.Popen(
                ["espeak-ng", "-v", "es", "-s", "150", text],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            console.print("[red]⚠️  espeak-ng tampoco disponible. Sin audio.[/red]")
            return "error"
        _register(proc)
        try:
            if wait_with_stop(proc, stop_event):
                return "interrupted"
            return "ok"
        finally:
            _unregister(proc)


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

    def speak(self, text: str, source: str = "system", stop_event=None) -> str:
        if not text or not text.strip():
            return "ok"

        engine = self._pick(text, source)
        if engine is not self.eleven:
            return self.piper.speak(text, stop_event=stop_event) or "ok"

        from modules.voice_utils import clean_for_voice, split_for_voice
        first, rest = split_for_voice(
            clean_for_voice(text), self.max_turn_chars)
        try:
            result = self.eleven.speak(first, stop_event=stop_event)
        except Exception as e:
            console.print(f"[yellow]ElevenLabs no disponible ({e}); "
                          f"usando Piper.[/yellow]")
            result = self.piper.speak(first, stop_event=stop_event)
        if result == "interrupted":
            return "interrupted"
        # El tope por turno protege la cuota; el resto sale con la voz local.
        if rest:
            return self.piper.speak(rest, stop_event=stop_event) or "ok"
        return result or "ok"

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
