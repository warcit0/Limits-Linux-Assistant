"""
Comandos personalizados — Extiende Limits con tus propias acciones.

Cómo agregar un comando nuevo:
  1. Agrega un método a la clase CustomCommands
  2. Regístralo en modules/executor.py → action_map
  3. Agrega un ejemplo en prompts/system_prompt.txt

Ejemplo de comando personalizado:
  def abrir_proyecto_trabajo(self) -> None:
      subprocess.Popen(["ghostty", "-e", "bash", "-c", "cd ~/Work && nvim ."])
"""

import subprocess
from rich.console import Console

console = Console()


class CustomCommands:
    """
    Comandos personalizados del usuario.
    Agrega aquí cualquier acción específica de tu flujo de trabajo.
    """

    # ──────────────────────────────────────────────────────────────────────────
    # Ejemplo (descomenta y adapta):
    # ──────────────────────────────────────────────────────────────────────────

    # def abrir_proyecto_trabajo(self) -> None:
    #     """Abre el directorio de trabajo en Ghostty + nvim."""
    #     subprocess.Popen(
    #         ["ghostty", "-e", "bash", "-c", "cd ~/Work && nvim ."],
    #         start_new_session=True,
    #     )

    # def modo_focus(self) -> str:
    #     """Activa modo focus: silencia notificaciones y cierra distracciones."""
    #     subprocess.run(["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", "0%"])
    #     return "Modo focus activado."

    pass
