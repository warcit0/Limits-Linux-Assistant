"""
DesktopAgent — lane compuesto para órdenes multi-paso de escritorio.

El clasificador strict emite action=desktop_task con params.goal.
Loop corto sobre tools TIPADAS (FileCommands). Sin shell libre.

Motor preferido: OpenCode API (deepseek-v4.1-flash-free).
Fallback: Ollama local (p.ej. qwen2.5:3b-instruct).
Groq / Big Pickle: fuera de alcance.

Contrato de cada paso del modelo (JSON único):
  {"tool":"search_file","args":{"name":"x","path":"~/Downloads"}}
  {"tool":"done","args":{"message":"Listo."}}
  {"tool":"ask_user","args":{"question":"¿Cuál de los dos?"}}
  {"tool":"propose_move","args":{"source":"...","destination":"..."}}
  {"tool":"propose_rename","args":{"path":"...","new_name":"..."}}

propose_move / propose_rename NO ejecutan: dejan pending en el executor.
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Callable

import requests
from rich.console import Console

console = Console()
log = logging.getLogger("limits.desktop_agent")

MAX_STEPS = 6

_COMPOUND_FILE_MARKERS = (
    " y cópialo", " y copialo", " y cópiala", " y copiala",
    " y muévelo", " y muevelo", " y muévela", " y muevela",
    " y renómbralo", " y renombralo",
    " y luego copia", " y después copia",
    "búscale y copia", "buscale y copia",
    "busca y copia", "busca y mueve",
)

# Tools que exigen que path/source ya hayan salido de una observación
_PATH_GUARDED = {
    "open_file": ("path",),
    "reveal_file": ("path",),
    "copy_file": ("source",),
}


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
- search_file {name, path?} — busca; path default raíces configuradas
- search_and_open {name, path?} — busca y abre si hay 1 match
- open_file {path} — abre con xdg-open (ruta real de un paso anterior)
- open_last {index?} — abre el N-ésimo de la última búsqueda (1=primero)
- reveal_file {path} o {name, search_path?} — muestra en Thunar
- reveal_last {index?} — revela el N-ésimo de la última búsqueda
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


def _normalize_opencode_model(model: str) -> str:
    """API espera id sin prefijo 'opencode/' (p.ej. deepseek-v4.1-flash-free)."""
    m = (model or "").strip()
    if m.startswith("opencode/"):
        return m.split("/", 1)[1]
    return m


def load_opencode_api_key(explicit: str = "") -> str:
    """Key desde env o ~/.local/share/opencode/auth.json (provider opencode)."""
    if explicit and explicit.strip():
        return explicit.strip()
    env = os.getenv("OPENCODE_API_KEY", "").strip()
    if env:
        return env
    auth_path = Path.home() / ".local/share/opencode" / "auth.json"
    try:
        data = json.loads(auth_path.read_text(encoding="utf-8"))
        block = data.get("opencode") if isinstance(data, dict) else None
        if isinstance(block, dict):
            key = block.get("key") or block.get("apiKey") or ""
            if isinstance(key, str) and key.strip():
                return key.strip()
    except (OSError, json.JSONDecodeError, TypeError):
        pass
    return ""


class DesktopAgent:
    """Loop tool-calling acotado sobre FileCommands."""

    def __init__(
        self,
        files=None,
        ollama_url: str = "http://localhost:11434",
        ollama_model: str = "qwen2.5:3b-instruct",
        keep_alive: str = "30m",
        num_ctx: int = 2048,
        max_steps: int = MAX_STEPS,
        pending_setter: Callable[[str, dict, str], None] | None = None,
        llm_callable: Callable[[list[dict]], dict | None] | None = None,
        provider: str = "opencode",
        opencode_api_key: str = "",
        opencode_base_url: str = "https://opencode.ai/inference/openai/v1",
        opencode_model: str = "opencode/deepseek-v4.1-flash-free",
        fallback: str = "ollama",
        request_timeout_s: float = 60.0,
    ):
        self.files = files
        self.ollama_url = ollama_url.rstrip("/")
        self.ollama_model = ollama_model
        self.keep_alive = keep_alive
        self.num_ctx = num_ctx
        self.max_steps = max_steps
        self._set_pending = pending_setter
        self._llm_callable = llm_callable
        self.provider = (provider or "opencode").strip().lower()
        self.opencode_api_key = load_opencode_api_key(opencode_api_key)
        self.opencode_base_url = opencode_base_url.rstrip("/")
        self.opencode_model = opencode_model
        self.fallback = (fallback or "ollama").strip().lower()
        self.request_timeout_s = request_timeout_s
        self._tools: dict[str, Callable[..., str]] = {}
        self._observed_paths: set[str] = set()
        self._opencode_failed = False  # evita martillar API cada paso tras fallo
        if files is not None:
            self.bind_files(files)

    def bind_files(self, files) -> None:
        """Re-enlaza handlers tipados (CommandExecutor lo llama al arrancar)."""
        self.files = files
        self._tools = {
            "search_file": self.files.search_file,
            "search_and_open": self.files.search_and_open,
            "open_file": self.files.open_file,
            "open_last": self.files.open_last,
            "reveal_file": self.files.reveal_file,
            "reveal_last": self.files.reveal_last,
            "copy_file": self.files.copy_file,
            "list_directory": self.files.list_directory,
        }

    def run(self, goal: str) -> str:
        goal = (goal or "").strip()
        if not goal:
            return "¿Qué tarea de archivos quieres hacer?"

        self._observed_paths = set()
        self._opencode_failed = False
        messages: list[dict] = [
            {"role": "system", "content": AGENT_SYSTEM},
            {"role": "user", "content": f"Tarea: {goal}"},
        ]

        for step in range(self.max_steps):
            decision = self._plan(messages)
            if not decision:
                return "No pude completar la tarea de archivos ahora."

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

            blocked = self._path_guard(tool, args)
            if blocked:
                observation = blocked
            else:
                handler = self._tools.get(tool)
                if not handler:
                    observation = f"Tool desconocida: {tool}. Usa solo el catálogo."
                else:
                    observation = self._call_tool(handler, args)
                    self._ingest_observations(tool)

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

    def _ingest_observations(self, tool: str) -> None:
        """Acumula paths reales tras tools de búsqueda/listado."""
        if self.files is None:
            return
        for p in getattr(self.files, "last_matches", []) or []:
            self._observed_paths.add(os.path.expanduser(str(p)))
        opened = getattr(self.files, "last_opened", None)
        if opened:
            self._observed_paths.add(os.path.expanduser(str(opened)))

    def _path_guard(self, tool: str, args: dict) -> str | None:
        """Bloquea open/copy/reveal con paths no observados en este turno."""
        keys = _PATH_GUARDED.get(tool)
        if not keys:
            return None
        # Primera tool del turno puede ser open con path absoluto si ya
        # venía en el goal — aún así exigimos observación previa (search).
        for key in keys:
            raw = args.get(key)
            if not raw or not str(raw).strip():
                # reveal_file puede ir por name; open_file vacío → open_last
                if tool == "reveal_file" and args.get("name"):
                    continue
                if tool == "open_file" and not str(raw or "").strip():
                    continue
                continue
            expanded = os.path.expanduser(str(raw).strip())
            if expanded not in self._observed_paths:
                # Permitir si es el único last_match exacto recién buscado
                matches = list(getattr(self.files, "last_matches", []) or [])
                matches_exp = {os.path.expanduser(m) for m in matches}
                if expanded not in matches_exp:
                    log.warning("desktop_task path guard blocked %s %s", tool, key)
                    return (
                        f"Ruta no observada en este turno: {raw}. "
                        "Primero search_file / search_and_open y usa un path "
                        "devuelto, o open_last/reveal_last."
                    )
                self._observed_paths.add(expanded)
        return None

    def _propose(self, action: str, params: dict, prompt: str) -> str:
        if self._set_pending is None:
            return "No puedo pedir confirmación ahora."
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

        # 1) OpenCode
        if self.provider == "opencode" and not self._opencode_failed:
            if not self.opencode_api_key:
                console.print("[yellow]desktop_agent: sin OPENCODE_API_KEY; "
                              "fallback[/yellow]")
                self._opencode_failed = True
            else:
                result = self._query_opencode(messages)
                if result is not None:
                    return result
                self._opencode_failed = True
                console.print("[yellow]desktop_agent OpenCode falló; "
                              f"fallback={self.fallback}[/yellow]")
                log.warning("opencode agent failed; falling back to %s",
                            self.fallback)

        # 2) Ollama (provider=ollama o fallback)
        if self.provider == "ollama" or self.fallback == "ollama":
            return self._query_ollama(messages)
        return None

    def _query_opencode(self, messages: list[dict]) -> dict | None:
        url = f"{self.opencode_base_url}/chat/completions"
        model = _normalize_opencode_model(self.opencode_model)
        headers = {
            "Authorization": f"Bearer {self.opencode_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "messages": messages,
            "temperature": 0.1,
            "max_tokens": 400,
        }
        for attempt in (1, 2):
            try:
                response = requests.post(
                    url, headers=headers, json=payload,
                    timeout=self.request_timeout_s,
                )
                if response.status_code in (401, 403, 429):
                    console.print(f"[yellow]desktop_agent OpenCode HTTP "
                                  f"{response.status_code}[/yellow]")
                    log.warning("opencode HTTP %s", response.status_code)
                    return None
                if response.status_code != 200:
                    console.print(f"[yellow]desktop_agent OpenCode HTTP "
                                  f"{response.status_code} intento {attempt}"
                                  f"[/yellow]")
                    continue
                data = response.json()
                content = (
                    data.get("choices", [{}])[0]
                    .get("message", {})
                    .get("content")
                    or ""
                )
                parsed = _extract_json(content)
                if parsed is not None:
                    return parsed
                console.print(f"[yellow]desktop_agent OpenCode sin JSON "
                              f"útil (intento {attempt})[/yellow]")
            except (requests.exceptions.RequestException, json.JSONDecodeError,
                    KeyError, IndexError, TypeError) as e:
                console.print(f"[yellow]desktop_agent OpenCode error: "
                              f"{type(e).__name__}[/yellow]")
                log.warning("opencode error: %s", e)
        return None

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
