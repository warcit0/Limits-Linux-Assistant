"""Módulo LLM — router local de intents (Ollama).

Decisión 2026-10-28: el router es **100 % local**. Groq salió del camino
crítico: añadía latencia variable (20-30 s en free tier), dependía de la red y
su modelo configurado llegó a no existir, con lo que cada turno fallaba en
silencio y caía al motor pequeño.

El modelo propone; `modules/grounding.py` verifica la propuesta contra el
catálogo real de acciones y contra la frase del usuario antes de que el
executor toque nada.
"""

import json

import requests
from rich.console import Console

from config import Config

console = Console()

# Número de mensajes de historial a conservar Y enviar al LLM (deben ser iguales)
HISTORY_SIZE = 6

# Confianza asumida cuando el modelo omite el campo (pasa a menudo). No es 1.0
# para no mentir en el log, ni <0.5 para no bloquear órdenes legítimas.
DEFAULT_CONFIDENCE = 0.9


def _normalize_confidence(result: dict) -> dict:
    """Deja `confidence` como float y con valor cuando el modelo lo omite.

    El executor ejecuta si falta (default 1.0) para no romper órdenes
    legítimas; normalizar aquí evita que el log diga 0.00 y ejecute.
    """
    raw = result.get("confidence")
    try:
        result["confidence"] = DEFAULT_CONFIDENCE if raw is None else float(raw)
    except (TypeError, ValueError):
        result["confidence"] = DEFAULT_CONFIDENCE
    return result


class LLMEngine:
    def __init__(self, config: Config, actions=None):
        self.config = config
        self.system_prompt = self._load_system_prompt()
        self.conversation_history: list[dict] = []
        self._history_loaded = False
        # Catálogo real del executor (P1): el modelo no puede inventar acciones.
        self.known_actions = frozenset(actions) if actions else None
        self._check_ollama()

    def _load_system_prompt(self) -> str:
        """Carga el system prompt desde archivo e inyecta variables de entorno."""
        import os
        try:
            with open("prompts/system_prompt.txt", "r", encoding="utf-8") as f:
                prompt = f.read()
            prompt = prompt.replace("{username}", os.getenv("USER", "usuario"))
            try:
                from modules.machine_map import build_machine_map
                prompt = prompt.replace("{machine_map}", build_machine_map())
            except Exception:
                prompt = prompt.replace("{machine_map}", "")
            return prompt
        except FileNotFoundError:
            console.print("[red]⚠️  prompts/system_prompt.txt no encontrado[/red]")
            return "Eres Limits, un asistente de Linux. Responde SIEMPRE en JSON válido."

    def _render_system_prompt(self) -> str:
        """
        Sustituye lo que cambia por turno. `{now}` NO puede congelarse al
        arrancar: un servicio de tres días daría la hora de hace tres días.
        `{memory}` sale de SQLite y cambia cuando el usuario recuerda/olvida.
        """
        try:
            from modules.clock import now_line
            now = now_line(self.config.TIMEZONE or None)
        except Exception:
            now = ""
        try:
            from modules.memory import get_store
            limit = getattr(self.config, "MEMORY_CONTEXT_BYTES", 600)
            memory = get_store().facts_block(limit)
        except Exception:
            memory = ""
        return (self.system_prompt
                .replace("{now}", now)
                .replace("{memory}", memory or "(nada todavía)"))

    def _hydrate_history(self) -> None:
        """Al primer turno, recupera la conversación de antes del reinicio."""
        if self._history_loaded:
            return
        self._history_loaded = True
        try:
            from modules.memory import get_store
            for turn in get_store().recent_turns(HISTORY_SIZE):
                self.conversation_history.append(
                    {"role": turn["role"], "content": turn["text"]})
        except Exception:
            pass

    def _check_ollama(self):
        """Verifica que Ollama esté corriendo y el modelo esté disponible."""
        try:
            response = requests.get(
                f"{self.config.OLLAMA_URL}/api/tags",
                timeout=3,
            )
            if response.status_code == 200:
                models = [m["name"] for m in response.json().get("models", [])]
                target = self.config.OLLAMA_MODEL
                # Match exacto o por prefijo (ej. "qwen2.5-coder:7b" == "qwen2.5-coder:7b")
                available = any(m == target or m.startswith(target.split(":")[0] + ":") for m in models)

                if available:
                    console.print(f"[green]✓ Ollama listo con {target}[/green]")
                else:
                    console.print(f"[yellow]⚠️  Modelo '{target}' no encontrado en Ollama.[/yellow]")
                    console.print(f"[yellow]   Modelos disponibles: {', '.join(models)}[/yellow]")
                    console.print(f"[yellow]   Ejecuta: ollama pull {target}[/yellow]")
        except requests.exceptions.ConnectionError:
            console.print("[red]⚠️  Ollama no responde: el router no puede funcionar.[/red]")
            console.print("[yellow]   Para iniciar: sudo systemctl start ollama[/yellow]")

    def _query_ollama(self, user_text: str) -> dict | None:
        """Consulta al LLM local via Ollama."""
        try:
            payload = {
                "model": self.config.OLLAMA_MODEL,
                "messages": [
                    {"role": "system", "content": self._render_system_prompt()},
                    *self.conversation_history,
                    {"role": "user", "content": user_text},
                ],
                "stream": False,
                "format": "json",
                "keep_alive": self.config.OLLAMA_KEEP_ALIVE,
                "options": {
                    "temperature": 0.0,
                    "seed": 42,
                    "num_predict": 200,
                    "num_ctx": self.config.OLLAMA_NUM_CTX,
                },
            }

            response = requests.post(
                f"{self.config.OLLAMA_URL}/api/chat",
                json=payload,
                timeout=90,
            )

            if response.status_code == 200:
                content = response.json()["message"]["content"]
                return json.loads(content)

            console.print(f"[yellow]Ollama respondió {response.status_code}[/yellow]")

        except (requests.exceptions.RequestException, json.JSONDecodeError, KeyError) as e:
            console.print(f"[yellow]Ollama falló: {e}[/yellow]")
        return None

    @staticmethod
    def _extract_json(text: str) -> dict | None:
        """Extrae un objeto JSON de una respuesta LLM imperfecta.

        Tolera bloques <think> residuales, fences markdown y texto alrededor;
        devuelve None si no hay JSON parseable."""
        import re
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
        if m:
            try:
                data = json.loads(m.group())
                return data if isinstance(data, dict) else None
            except json.JSONDecodeError:
                return None
        return None

    def process(self, user_text: str) -> dict:
        """Devuelve el intent validado y **anclado** a la frase (P1).

        Si el modelo propone una acción que no existe, un parámetro inválido o
        un dominio que no aparece en la frase, el resultado sale con
        `grounded=False`: el executor no lo ejecutará y responderá con
        honestidad en vez de inventarse un «hecho».
        """
        console.print(f"[dim]Procesando: '{user_text}'[/dim]")
        self._hydrate_history()

        result = self._query_ollama(user_text)
        if not isinstance(result, dict):
            return {
                "intent": "unknown",
                "action": "speak_error",
                "params": {},
                "response": "No pude procesar ese comando. ¿Puedes repetirlo?",
                "confidence": 0.0,
                "grounded": True,
                "grounding_reason": "sin_respuesta",
            }

        _normalize_confidence(result)

        from modules.grounding import check as _ground
        verdict = _ground(result.get("action"), result.get("params"),
                          user_text, self.known_actions)
        result["params"] = verdict.params
        result["grounded"] = verdict.ok
        result["grounding_reason"] = verdict.reason
        if not verdict.ok:
            console.print(f"[yellow]grounding: '{result.get('action')}' "
                          f"rechazada ({verdict.reason}); no se ejecutará.[/yellow]")

        # Actualizar historial (máx HISTORY_SIZE mensajes = lo mismo que se envía)
        self.conversation_history.append({"role": "user", "content": user_text})
        self.conversation_history.append(
            {"role": "assistant", "content": json.dumps(result)}
        )
        if len(self.conversation_history) > HISTORY_SIZE:
            self.conversation_history = self.conversation_history[-HISTORY_SIZE:]

        console.print(
            f"[dim]Intent: {result.get('intent')} | "
            f"Confidence: {result.get('confidence', 0):.2f} | "
            f"grounding: {result.get('grounding_reason', 'ok')}[/dim]"
        )

        return result
