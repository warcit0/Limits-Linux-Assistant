"""
DesktopAgent — lane compuesto para órdenes multi-paso de escritorio.

El clasificador strict emite action=desktop_task con params.goal.
Este módulo hace un loop corto sobre tools TIPADAS (FileCommands),
preferentemente vía Ollama/Qwen. Sin shell libre.

Contrato de cada paso del modelo (JSON único):
  {"tool":"search_file","args":{"name":"x","path":"~/Downloads"}}
  {"tool":"done","args":{"message":"Listo."}}
  {"tool":"ask_user","args":{"question":"¿Cuál de los dos?"}}
  {"tool":"propose_move","args":{"source":"...","destination":"..."}}
  {"tool":"propose_rename","args":{"path":"...","new_name":"..."}}

propose_move / propose_rename NO ejecutan: dejan pending en el executor
para el flujo confirm/cancel existente.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Callable

import requests
from rich.console import Console

console = Console()
log = logging.getLogger("limits.desktop_agent")

MAX_STEPS = 6

# Frases multi-paso de archivos → lane compuesto sin pasar por el clasificador
# (misma idea que match_gemini_route). "busca X y ábrelo" solo NO entra aquí:
# eso es search_and_open atómico.
_COMPOUND_FILE_MARKERS = (
    " y cópialo", " y copialo", " y cópiala", " y copiala",
    " y muévelo", " y muevelo", " y muévela", " y muevela",
    " y renómbralo", " y renombralo",
    " y luego copia", " y después copia",
    "búscale y copia", "buscale y copia",
    "busca y copia", "busca y mueve",
)


def match_desktop_task_route(text: str) -> str | None:
    """Si la frase es multi-paso de archivos, devuelve el goal verbatim."""
    low = (text or "").strip().lower()
    if not low:
        return None
    if any(m in low for m in _COMPOUND_FILE_MARKERS):
        return text.strip()
    return None


AGENT_SYSTEM = """\
Eres el planificador de escritorio de Limits (Linux). Resuelves UNA tarea
usando SOLO las tools listadas. Responde SIEMPRE con un único JSON:
{"tool":"...","args":{...}}

Tools:
- search_file {name, path?} — busca; path default ~
- search_and_open {name, path?} — busca y abre si hay 1 match
- open_file {path} — abre con xdg-open (ruta real de un paso anterior)
- reveal_file {path} o {name, search_path?} — muestra en Thunar
- copy_file {source, destination} — copia; falla si destino existe
- list_directory {path}
- propose_move {source, destination} — pide confirmación al usuario (no mueve aún)
- propose_rename {path, new_name} — pide confirmación (no renombra aún)
- ask_user {question} — si hay ambigüedad; termina el turno
- done {message} — tarea terminada; message se habla

Reglas:
1. NUNCA inventes rutas: usa solo paths devueltos por tools.
2. Si hay varios matches, ask_user o done listando opciones; no adivines.
3. Para mover/renombrar usa propose_*; nunca asumas confirmación.
4. Sin shell, sin markdown, sin texto fuera del JSON.
"""


def _extract_json(text: str) -> dict | None:
    if not text:
        return None
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    cleaned = re.sub(r"^```[a-zA-Z]*\s*", "", cleaned.strip())
    cleaned = re.sub(r"\s*```$", "", cleaned.strip()).strip()
    try:
        data = json.loads(cleaned)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{.*\}", cleaned, flags=re.S)
    if not m:
        return None
    try:
        data = json.loads(m.group())
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        return None


class DesktopAgent:
    """Loop tool-calling acotado sobre FileCommands."""

    def __init__(
        self,
        files=None,
        ollama_url: str = "http://localhost:11434",
        ollama_model: str = "qwen2.5-coder:7b",
        keep_alive: str = "30m",
        num_ctx: int = 2048,
        max_steps: int = MAX_STEPS,
        pending_setter: Callable[[str, dict, str], None] | None = None,
        llm_callable: Callable[[list[dict]], dict | None] | None = None,
    ):
        self.files = files
        self.ollama_url = ollama_url.rstrip("/")
        self.ollama_model = ollama_model
        self.keep_alive = keep_alive
        self.num_ctx = num_ctx
        self.max_steps = max_steps
        self._set_pending = pending_setter
        # Inyectable para tests (evita red)
        self._llm_callable = llm_callable
        self._tools: dict[str, Callable[..., str]] = {}
        if files is not None:
            self.bind_files(files)

    def bind_files(self, files) -> None:
        """Re-enlaza handlers tipados (CommandExecutor lo llama al arrancar)."""
        self.files = files
        self._tools = {
            "search_file": self.files.search_file,
            "search_and_open": self.files.search_and_open,
            "open_file": self.files.open_file,
            "reveal_file": self.files.reveal_file,
            "copy_file": self.files.copy_file,
            "list_directory": self.files.list_directory,
        }

    def run(self, goal: str) -> str:
        goal = (goal or "").strip()
        if not goal:
            return "¿Qué tarea de archivos quieres hacer?"

        messages: list[dict] = [
            {"role": "system", "content": AGENT_SYSTEM},
            {"role": "user", "content": f"Tarea: {goal}"},
        ]

        for step in range(self.max_steps):
            decision = self._plan(messages)
            if not decision:
                return "No pude planificar esa tarea. Intenta ser más específico."

            tool = str(decision.get("tool", "")).strip()
            args = decision.get("args") or {}
            if not isinstance(args, dict):
                args = {}

            console.print(f"[dim]desktop_task paso {step + 1}: {tool} {args}[/dim]")
            log.info("desktop_task step=%s tool=%s", step + 1, tool)

            if tool == "done":
                msg = str(args.get("message", "Listo.")).strip() or "Listo."
                return msg

            if tool == "ask_user":
                q = str(args.get("question", "¿Puedes aclarar?")).strip()
                return q or "¿Puedes aclarar?"

            if tool == "propose_move":
                return self._propose(
                    "move_file",
                    {"source": args.get("source", ""),
                     "destination": args.get("destination", "")},
                    "¿Confirmas el movimiento?",
                )

            if tool == "propose_rename":
                return self._propose(
                    "rename_file",
                    {"path": args.get("path", ""),
                     "new_name": args.get("new_name", "")},
                    "¿Confirmas el renombrado?",
                )

            handler = self._tools.get(tool)
            if not handler:
                observation = f"Tool desconocida: {tool}. Usa solo el catálogo."
            else:
                observation = self._call_tool(handler, args)

            messages.append({
                "role": "assistant",
                "content": json.dumps({"tool": tool, "args": args},
                                      ensure_ascii=False),
            })
            messages.append({
                "role": "user",
                "content": f"Resultado de {tool}: {observation}",
            })

        return "Se agotaron los pasos de la tarea. Reformúlala en partes más simples."

    def _propose(self, action: str, params: dict, prompt: str) -> str:
        if self._set_pending is None:
            return "No puedo pedir confirmación ahora."
        # Filtrar vacíos
        clean = {k: v for k, v in params.items() if v}
        if len(clean) < len(params) or not clean:
            return "Faltan rutas para esa operación."
        self._set_pending(action, clean, "Hecho.")
        src = clean.get("source") or clean.get("path") or "?"
        dst = clean.get("destination") or clean.get("new_name") or "?"
        return f"{prompt} De {src} a {dst}. Di confirmar o cancelar."

    def _call_tool(self, handler: Callable[..., Any], args: dict) -> str:
        import inspect
        sig = inspect.signature(handler)
        valid = {k: v for k, v in args.items() if k in sig.parameters}
        try:
            result = handler(**valid)
            if result is None:
                return "OK."
            return str(result)
        except TypeError as e:
            return f"Parámetros inválidos: {e}"
        except Exception as e:
            return f"Error: {e}"

    def _plan(self, messages: list[dict]) -> dict | None:
        if self._llm_callable is not None:
            return self._llm_callable(messages)
        return self._query_ollama(messages)

    def _query_ollama(self, messages: list[dict]) -> dict | None:
        try:
            payload = {
                "model": self.ollama_model,
                "messages": messages,
                "stream": False,
                "format": "json",
                "keep_alive": self.keep_alive,
                "options": {
                    "temperature": 0.1,
                    "num_predict": 250,
                    "num_ctx": self.num_ctx,
                },
            }
            response = requests.post(
                f"{self.ollama_url}/api/chat",
                json=payload,
                timeout=90,
            )
            if response.status_code != 200:
                console.print(f"[yellow]desktop_agent Ollama HTTP "
                              f"{response.status_code}[/yellow]")
                return None
            content = response.json()["message"]["content"]
            return _extract_json(content)
        except (requests.exceptions.RequestException, json.JSONDecodeError,
                KeyError) as e:
            console.print(f"[yellow]desktop_agent Ollama falló: {e}[/yellow]")
            return None
