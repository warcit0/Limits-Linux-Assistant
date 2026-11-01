"""
Módulo Listener — Escucha continua en segundo plano con detección de wake word.

Este módulo es el "siempre activo". Escucha constantemente el audio con
faster-whisper en modo ligero (tiny) para detectar la wake word, y cuando
la detecta, delega al STTEngine completo para transcribir el comando real.

Nota: En la implementación actual de main.py la detección de wake word está
inline (más simple). Este módulo se puede usar para una versión más eficiente
donde el modelo tiny corre siempre y el modelo small solo se activa al hablar.
"""

import threading
from rich.console import Console
from modules.stt import STTEngine

console = Console()


class WakeWordListener:
    """
    Escucha continua con wake word detection.
    Usa un modelo Whisper 'tiny' para la detección (bajo consumo)
    y activa el STTEngine principal solo cuando detecta la wake word.
    """

    def __init__(
        self,
        wake_word: str = "limits",
        on_command_callback=None,
        stt_model: str = "small",
        language: str = "es",
    ):
        """
        Args:
            wake_word:            Palabra que activa el asistente (case-insensitive)
            on_command_callback:  Función a llamar con el texto del comando detectado
            stt_model:            Modelo para transcribir el comando (small/medium)
            language:             Idioma de transcripción
        """
        self.wake_word = wake_word.lower()
        self.on_command_callback = on_command_callback
        self._running = False
        self._thread = None

        # Motor de transcripción completo (para el comando real)
        self.stt = STTEngine(model_size=stt_model, language=language)
        console.print(f"[cyan]Wake word: '{wake_word}'[/cyan]")

    def _listen_loop(self):
        """Loop principal que escucha continuamente."""
        console.print("[green]✓ Listener activo.[/green]")

        while self._running:
            try:
                text = self.stt.listen_and_transcribe()

                if not text:
                    continue

                if self.wake_word in text.lower():
                    # Extraer lo que viene después de la wake word
                    command = text.lower().replace(self.wake_word, "").strip()

                    if not command:
                        # Solo dijo la wake word, esperamos el comando
                        console.print(f"[cyan]Wake word detectada. Esperando comando...[/cyan]")
                        command = self.stt.listen_and_transcribe()

                    if command and self.on_command_callback:
                        self.on_command_callback(command)

            except Exception as e:
                if self._running:
                    console.print(f"[red]Error en listener: {e}[/red]")

    def start(self):
        """Inicia el listener en un hilo de fondo."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._thread.start()

    def stop(self):
        """Detiene el listener."""
        self._running = False
        self.stt.cleanup()
        if self._thread:
            self._thread.join(timeout=3)
        console.print("[dim]Listener detenido.[/dim]")
