"""
Módulo LLM — Motor de inteligencia artificial
Soporta Ollama (local, principal) con fallback automático a Groq API (cloud, gratuita).

Prioridad:
  1. Ollama local (qwen2.5-coder:7b) → privado, sin costo, sin internet, sin límites
  2. Groq API (llama-3.1-8b-instant) → fallback oficial si Ollama falla, muy rápido, gratis

Por qué este orden:
  - Ollama garantiza privacidad y disponibilidad offline
  - Groq es la API cloud más rápida del mercado en free tier (oficial)
  - Ambas usan formato de mensajes compatible con OpenAI spec
"""

import json
import requests
from rich.console import Console
from config import Config

console = Console()

# Intentar importar Groq (opcional si no hay API key)
try:
    from groq import Groq
    _GROQ_AVAILABLE = True
except ImportError:
    _GROQ_AVAILABLE = False

# Número de mensajes de historial a conservar Y enviar al LLM (deben ser iguales)
HISTORY_SIZE = 6


class LLMEngine:
    def __init__(self, config: Config):
        self.config = config
        self.system_prompt = self._load_system_prompt()
        self.conversation_history: list[dict] = []

        # Inicializar cliente Groq si hay API key
        self.groq_client = None
        if config.GROQ_API_KEY and _GROQ_AVAILABLE:
            self.groq_client = Groq(api_key=config.GROQ_API_KEY)
            console.print("[green]✓ Groq API configurada (Prioridad Turbo Activa)[/green]")
        elif not config.GROQ_API_KEY:
            console.print("[dim]Groq API key no configurada — solo modo Ollama local[/dim]")

        self._check_ollama()

    def _load_system_prompt(self) -> str:
        """Carga el system prompt desde archivo e inyecta variables de entorno."""
        import os
        try:
            with open("prompts/system_prompt.txt", "r", encoding="utf-8") as f:
                prompt = f.read()
            prompt = prompt.replace("{username}", os.getenv("USER", "usuario"))
            return prompt
        except FileNotFoundError:
            console.print("[red]⚠️  prompts/system_prompt.txt no encontrado[/red]")
            return "Eres Limits, un asistente de Linux. Responde SIEMPRE en JSON válido."

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
            console.print("[yellow]⚠️  Ollama no responde. Usando Groq como principal (si está configurado).[/yellow]")
            console.print("[yellow]   Para iniciar: sudo systemctl start ollama[/yellow]")

    def _query_ollama(self, user_text: str) -> dict | None:
        """Consulta al LLM local via Ollama."""
        try:
            payload = {
                "model": self.config.OLLAMA_MODEL,
                "messages": [
                    {"role": "system", "content": self.system_prompt},
                    *self.conversation_history,
                    {"role": "user", "content": user_text},
                ],
                "stream": False,
                "format": "json",
                "options": {
                    "temperature": 0.1,
                    "num_predict": 300,
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

        except (requests.exceptions.RequestException, json.JSONDecodeError, KeyError) as e:
            console.print(f"[yellow]Ollama falló: {e}. Intentando Groq...[/yellow]")
            return None

    def _query_groq(self, user_text: str) -> dict | None:
        """Consulta a Groq API como fallback (oficial, gratuita)."""
        if not self.groq_client:
            console.print("[red]Error: Groq no disponible (falta API key o paquete groq).[/red]")
            return None

        try:
            response = self.groq_client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    *self.conversation_history,
                    {"role": "user", "content": user_text},
                ],
                temperature=0.1,
                max_tokens=300,
                response_format={"type": "json_object"},
            )

            content = response.choices[0].message.content
            return json.loads(content)

        except Exception as e:
            console.print(f"[red]Groq también falló: {e}[/red]")
            return None

    def process(self, user_text: str) -> dict:
        """
        Procesa texto del usuario y devuelve la intención estructurada.
        Prioriza Groq (si está configurado) por su velocidad, usando Ollama como fallback.
        """
        console.print(f"[dim]Procesando: '{user_text}'[/dim]")

        if self.groq_client:
            result = self._query_groq(user_text) or self._query_ollama(user_text)
        else:
            result = self._query_ollama(user_text)

        if not result:
            return {
                "intent": "unknown",
                "action": "speak_error",
                "params": {},
                "response": "No pude procesar ese comando. ¿Puedes repetirlo?",
                "confidence": 0.0,
            }

        # Actualizar historial (máx HISTORY_SIZE mensajes = lo mismo que se envía)
        self.conversation_history.append({"role": "user", "content": user_text})
        self.conversation_history.append(
            {"role": "assistant", "content": json.dumps(result)}
        )
        if len(self.conversation_history) > HISTORY_SIZE:
            self.conversation_history = self.conversation_history[-HISTORY_SIZE:]

        console.print(
            f"[dim]Intent: {result.get('intent')} | "
            f"Confidence: {result.get('confidence', 0):.2f}[/dim]"
        )

        return result
