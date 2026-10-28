"""
Módulo Executor — Ejecuta acciones reales en el sistema operativo.
Mapea los intents del LLM a funciones Python concretas via subprocess.

SEGURIDAD:
  - Los comandos destructivos requieren confirmación verbal explícita.
  - El estado de confirmación pendiente se guarda entre turnos.
"""

from rich.console import Console
from commands.apps import AppCommands
from commands.system import SystemCommands
from commands.web import WebCommands
from commands.dev import DevCommands
from commands.files import FileCommands
from commands.custom import CustomCommands
from commands.media import MediaCommands
from commands.tv import TVCommands
from modules.desktop_agent import DesktopAgent

console = Console()


class CommandExecutor:
    def __init__(self, desktop_agent: DesktopAgent | None = None):
        self.apps    = AppCommands()
        self.system  = SystemCommands()
        self.web     = WebCommands()
        self.dev     = DevCommands()
        # FileCommands se reconfigura desde main via configure_files() si hay Config
        self.files   = FileCommands()
        self.custom  = CustomCommands()
        self.media   = MediaCommands()
        self.tv      = TVCommands()
        self.gemini  = None  # lo asigna main.py si GEMINI_ENABLED (GeminiBridge)

        # Estado de confirmación pendiente (antes del agent: propose_* lo usa)
        self._pending_action: dict | None = None

        # Lane compuesto (tools tipadas + Qwen). main.py puede inyectar uno
        # configurado; si no, se crea con defaults de Ollama.
        self.desktop_agent = desktop_agent or DesktopAgent(
            files=self.files,
            pending_setter=self._set_pending,
        )
        self.desktop_agent.bind_files(self.files)
        self.desktop_agent._set_pending = self._set_pending

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
            "get_time":             self.system.get_time,
            # Memoria persistente (P0-3)
            "remember":             self._remember,
            "forget":               self._forget,
            "memory_list":          self._memory_list,
            "memory_recall":        self._memory_recall,
            "memory_stats":         self._memory_stats,
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
            "search_and_open":      self.files.search_and_open,
            "open_file":            self.files.open_file,
            "open_last":            self.files.open_last,
            "reveal_file":          self.files.reveal_file,
            "reveal_last":          self.files.reveal_last,
            "copy_file":            self.files.copy_file,
            "move_file":            self.files.move_file,
            "rename_file":          self.files.rename_file,
            "list_directory":       self.files.list_directory,
            # Lane compuesto (multi-paso tipado)
            "desktop_task":         self._desktop_task,
            # Error
            "speak_error":          self._noop,
        }

        # Acciones que siempre requieren confirmación
        self.DANGEROUS_ACTIONS = {"shutdown", "reboot", "move_file", "rename_file"}

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
            raw_conf = parsed_result.get("confidence")
            # OJO: qwen3.6-27b omite `confidence` a menudo. Bloquear cuando
            # falta rompía órdenes legítimas («cuánta RAM tengo»), así que se
            # ejecuta. `LLMEngine.process` normaliza el valor (0.9) para que
            # el log y este cortafuegos coincidan. El grounding real es P1.
            confidence = 1.0 if raw_conf is None else float(raw_conf)
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
    # Memoria persistente (P0-3)
    # ──────────────────────────────────────────────────────────────────────────

    def _remember(self, key: str = "", value: str = "", tags: str = "") -> str:
        """Guarda un hecho («X es Y») o una nota libre (sin clave)."""
        from modules.memory import get_store
        return get_store().remember(str(key), str(value), str(tags))

    def _forget(self, key: str = "") -> str:
        from modules.memory import get_store
        if not str(key).strip():
            return "¿Qué quieres que olvide?"
        if get_store().forget(str(key)):
            return f"Olvidado: {key}."
        return f"No tenía nada guardado sobre {key}."

    def _memory_list(self) -> str:
        from modules.memory import get_store
        store = get_store()
        if not store.enabled:
            return "La memoria está desactivada."
        facts = store.list_facts(8)
        if not facts:
            return "Todavía no sé nada de ti."
        return "Sé que " + "; ".join(self._format_fact(f) for f in facts) + "."

    def _memory_recall(self, query: str = "") -> str:
        from modules.memory import get_store
        rows = get_store().recall(str(query))
        if not rows:
            return f"No tengo nada guardado sobre {query}."
        return "; ".join(self._format_fact(r) for r in rows)

    @staticmethod
    def _format_fact(row: dict) -> str:
        """Las notas (clave autogenerada) se dicen por su texto, sin hash."""
        key = row["key"]
        if key.startswith("nota_"):
            return row["value"]
        return f"{key.replace('_', ' ')}: {row['value']}"

    def _memory_stats(self) -> str:
        from modules.memory import get_store
        stats = get_store().stats()
        if not stats.get("enabled"):
            return "La memoria está desactivada."
        return f"Tengo {stats['facts']} hechos y {stats['episodes']} turnos guardados."

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
                    return " ".join(p for p in (default_response, result) if p)
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

    def configure_files(self, search_roots: str | None = None,
                        search_excludes: str | None = None,
                        focus_delay_s: float = 0.55) -> None:
        """Aplica FILE_SEARCH_* desde Config y re-enlaza el desktop_agent."""
        self.files = FileCommands(
            search_roots=search_roots,
            search_excludes=search_excludes,
            focus_delay_s=focus_delay_s,
        )
        # Re-bind action_map handlers (apuntaban al FileCommands viejo)
        self.action_map["search_file"] = self.files.search_file
        self.action_map["search_and_open"] = self.files.search_and_open
        self.action_map["open_file"] = self.files.open_file
        self.action_map["open_last"] = self.files.open_last
        self.action_map["reveal_file"] = self.files.reveal_file
        self.action_map["reveal_last"] = self.files.reveal_last
        self.action_map["copy_file"] = self.files.copy_file
        self.action_map["move_file"] = self.files.move_file
        self.action_map["rename_file"] = self.files.rename_file
        self.action_map["list_directory"] = self.files.list_directory
        self.desktop_agent.bind_files(self.files)

    def _set_pending(self, action: str, params: dict, response: str) -> None:
        """Usado por DesktopAgent.propose_* para el flujo confirm/cancel."""
        self._pending_action = {
            "action": action,
            "params": params,
            "response": response,
        }

    def _desktop_task(self, goal: str) -> str:
        """Lane compuesto: loop de tools tipadas (sin shell)."""
        return self.desktop_agent.run(goal)

    # ── Cerebro conversacional ───────────────────────────────────────────────

    def _gemini_talk(self, query: str) -> str:
        return self._gemini(query, research=False)

    def _gemini_research(self, query: str) -> str:
        return self._gemini(query, research=True)

    def _gemini(self, query: str, research: bool) -> str:
        if not self.gemini:
            return "El cerebro conversacional está desactivado."
        return self.gemini.chat(query, research=research)
