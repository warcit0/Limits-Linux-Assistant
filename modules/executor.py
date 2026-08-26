"""
Módulo Executor — Ejecuta acciones reales en el sistema operativo.
Mapea los intents del LLM a funciones Python concretas via subprocess.

SEGURIDAD:
  - Los comandos destructivos requieren confirmación verbal explícita.
  - El estado de confirmación pendiente se guarda entre turnos.
"""

import psutil
from rich.console import Console
from commands.apps import AppCommands
from commands.system import SystemCommands
from commands.web import WebCommands
from commands.dev import DevCommands
from commands.files import FileCommands
from commands.custom import CustomCommands
from commands.media import MediaCommands
from commands.tv import TVCommands

console = Console()


class CommandExecutor:
    def __init__(self):
        self.apps    = AppCommands()
        self.system  = SystemCommands()
        self.web     = WebCommands()
        self.dev     = DevCommands()
        self.files   = FileCommands()
        self.custom  = CustomCommands()
        self.media   = MediaCommands()
        self.tv      = TVCommands()
        self.gemini  = None  # lo asigna main.py si GEMINI_ENABLED (GeminiBridge)

        # Mapeo action → handler
        self.action_map = {
            # Apps
            "open_application":     self.apps.open_app,
            "close_application":    self.apps.close_app,
            "list_running_apps":    self.apps.list_running,
            # Sistema
            "set_volume":           self.system.set_volume,
            "get_volume":           self.system.get_volume,
            "set_brightness":       self.system.set_brightness,
            "lock_screen":          self.system.lock_screen,
            "shutdown":             self.system.shutdown,
            "reboot":               self.system.reboot,
            "get_system_info":      self.system.get_info,
            "take_screenshot":      self.system.screenshot,
            "media_control":        self.system.media_control,
            "hyprland_control":     self.system.hyprland_control,
            "focus_window":         self.system.focus_window,
            # Multimedia avanzado
            "spotify_play":         self.media.spotify_play,
            "youtube_play":         self.media.youtube_play,
            "get_lyrics":           self.media.get_lyrics,
            "get_current_song":     self.media.get_current_song,
            "get_current_media":    self.media.get_current_song,  # alias
            "get_song":             self.media.get_current_song,  # alias
            "current_song":         self.media.get_current_song,  # alias
            # TV / casting
            "tv_cast":              self.tv.tv_cast,
            "tv_control":           self.tv.tv_control,
            "list_tvs":             self.tv.list_tvs,
            # Cerebro conversacional (salida solo a voz; jamás ejecuta nada)
            "gemini_talk":          self._gemini_talk,
            "gemini_research":      self._gemini_research,
            # Web
            "web_search":           self.web.search,
            "open_url":             self.web.open_url,
            # Dev
            "run_terminal_command": self.dev.run_command,
            "git_status":           self.dev.git_status,
            "docker_status":        self.dev.docker_status,
            "open_project":         self.dev.open_project,
            # Archivos
            "search_file":          self.files.search_file,
            "open_file":            self.files.open_file,
            "list_directory":       self.files.list_directory,
            # Error
            "speak_error":          self._noop,
        }

        # Acciones que siempre requieren confirmación
        self.DANGEROUS_ACTIONS = {"shutdown", "reboot"}

        # Estado de confirmación pendiente
        self._pending_action: dict | None = None

    # ──────────────────────────────────────────────────────────────────────────
    # Interfaz pública
    # ──────────────────────────────────────────────────────────────────────────

    def execute(self, parsed_result: dict) -> str:
        """
        Ejecuta la acción indicada por el LLM.
        Maneja el flujo de confirmación con estado.
        Returns: Texto de respuesta para sintetizar en voz.
        """
        # ── Cortafuegos de tipos: el LLM puede alucinar la estructura ─────────
        action     = parsed_result.get("action", "speak_error")
        params     = parsed_result.get("params", {})
        response   = parsed_result.get("response", "Hecho.")
        try:
            confidence = float(parsed_result.get("confidence", 1.0))
        except (TypeError, ValueError):
            confidence = 1.0
        if not isinstance(params, dict):
            params = {}
        if not isinstance(response, str):
            response = "Hecho."
        requires_confirmation = bool(params.pop("requires_confirmation", False))

        # ── ¿Hay una confirmación pendiente? ──────────────────────────────────
        if self._pending_action is not None:
            pending = self._pending_action
            self._pending_action = None

            # Solo los intents dedicados (enseñados en el system prompt) deciden
            if action == "confirm":
                console.print("[green]✓ Confirmación recibida, ejecutando...[/green]")
                return self._run(pending["action"], pending["params"], pending["response"])

            if action == "cancel":
                return "Acción cancelada."

            # Cualquier otro comando cancela lo pendiente y se procesa normal
            console.print("[yellow]Había una acción pendiente; se canceló.[/yellow]")

        # ── Confianza baja ────────────────────────────────────────────────────
        if confidence < 0.5:
            return "No estoy seguro de lo que quieres hacer. ¿Puedes ser más específico?"

        # ── Acción peligrosa o requiere confirmación ──────────────────────────
        if action in self.DANGEROUS_ACTIONS or requires_confirmation:
            self._pending_action = {"action": action, "params": params, "response": response}
            return f"⚠️  Este comando es sensible. Di 'confirmar' para ejecutarlo o 'cancelar' para no."

        return self._run(action, params, response)

    # ──────────────────────────────────────────────────────────────────────────
    # Internos
    # ──────────────────────────────────────────────────────────────────────────

    def _run(self, action: str, params: dict, default_response: str) -> str:
        """Resuelve y ejecuta un handler del action_map."""
        handler = self.action_map.get(action)

        if handler:
            try:
                import inspect
                sig = inspect.signature(handler)
                # Filtrar kwargs extra para proteger contra alucinaciones del LLM
                valid_params = {k: v for k, v in params.items() if k in sig.parameters}
                
                result = handler(**valid_params)
                if result and isinstance(result, str) and result != default_response:
                    return f"{default_response} {result}"
                return default_response
            except TypeError as e:
                console.print(f"[red]Error en parámetros de '{action}': {e}[/red]")
                return "Ocurrió un error al ejecutar ese comando."
            except Exception as e:
                console.print(f"[red]Error ejecutando '{action}': {e}[/red]")
                return "No pude completar esa acción."
        else:
            console.print(f"[yellow]Acción no implementada: '{action}'[/yellow]")
            return default_response

    def _noop(self, **kwargs) -> None:
        pass

    # ── Cerebro conversacional ───────────────────────────────────────────────

    def _gemini_talk(self, query: str) -> str:
        return self._gemini(query, research=False)

    def _gemini_research(self, query: str) -> str:
        return self._gemini(query, research=True)

    def _gemini(self, query: str, research: bool) -> str:
        if not self.gemini:
            return "El cerebro conversacional está desactivado."
        return self.gemini.chat(query, research=research)
