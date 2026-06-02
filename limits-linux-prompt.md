# 🤖 Limits LINUX — Prompt Completo del Sistema

> Asistente de voz estilo Jarvis para CachyOS + Omarchy.
> Stack oficial: Python · Ollama (local, principal) · Groq API (fallback cloud, gratuito) · faster-whisper · piper-tts
> 100% terminal — sin GUI, sin overhead, nativo en Hyprland.

---

## 📋 ÍNDICE

1. [Visión General del Sistema](#1-visión-general-del-sistema)
2. [Arquitectura Técnica](#2-arquitectura-técnica)
3. [Requisitos y Dependencias](#3-requisitos-y-dependencias)
4. [Estructura del Proyecto](#4-estructura-del-proyecto)
5. [System Prompt del LLM](#5-system-prompt-del-llm)
6. [Módulo de Voz a Texto (STT)](#6-módulo-de-voz-a-texto-stt)
7. [Módulo del Motor LLM](#7-módulo-del-motor-llm)
8. [Módulo de Ejecución de Comandos](#8-módulo-de-ejecución-de-comandos)
9. [Módulo de Texto a Voz (TTS)](#9-módulo-de-texto-a-voz-tts)
10. [Orquestador Principal](#10-orquestador-principal)
11. [Configuración y Variables de Entorno](#11-configuración-y-variables-de-entorno)
12. [Comandos Reconocidos y Ejemplos](#12-comandos-reconocidos-y-ejemplos)
13. [Extensión y Personalización](#13-extensión-y-personalización)
14. [GitHub y Portafolio](#14-github-y-portafolio)
15. [Troubleshooting](#15-troubleshooting)

---

## 1. Visión General del Sistema

### ¿Qué es Limits Linux?

Un asistente de voz personal que corre **completamente en tu máquina**, sin interfaces gráficas,
sin overhead de navegador, nativo en la terminal. Capaz de:

- Escuchar comandos de voz en español o inglés
- Entender la intención usando un LLM local (Ollama) con fallback automático a Groq API
- Ejecutar acciones reales en el sistema operativo (abrir apps, controlar ventanas, buscar archivos, ejecutar scripts)
- Responder en voz usando síntesis de texto a voz con piper-tts
- Operar sin GUI — vive en la terminal, perfecto para Hyprland/Omarchy
- Correr como servicio systemd en segundo plano, sin consumir recursos visuales

### Filosofía de diseño

```
PRIVACIDAD PRIMERO   → Ollama local por defecto, Groq solo como fallback
TERMINAL NATIVA      → sin Electron, sin Chromium, sin GUI innecesaria
VELOCIDAD            → faster-whisper tiny/base para STT en tiempo real
EXTENSIBILIDAD       → comandos nuevos = agregar una función Python
SIN DEPENDENCIAS GPU → funciona con CPU + 16GB RAM
CONFIABLE            → Ollama + Groq son APIs oficiales y estables
```

### Por qué Ollama + Groq (y no otras alternativas)

| Herramienta | Por qué está en este stack |
|---|---|
| **Ollama** | 100% local, privado, sin costo, sin límites. Modelos 7b funcionan bien con 16GB RAM |
| **Groq API** | Gratuita (free tier oficial), extremadamente rápida, SDK idéntico a OpenAI |
| **faster-whisper** | STT local, sin enviar audio a la nube, modelo `small` suficiente para comandos |
| **piper-tts** | TTS local, voces naturales en español, sin latencia de red |

> ⚠️ **Nota sobre alternativas**: Herramientas como plugins no oficiales de Antigravity
> o proxies de sesiones web funcionan pero dependen de ingeniería inversa que puede
> romperse con cualquier actualización. Este stack usa únicamente APIs y herramientas
> con soporte oficial y términos de uso claros.

---

## 2. Arquitectura Técnica

```
┌─────────────────────────────────────────────────────────────────┐
│                        LIMITS LINUX                             │
│                    (proceso en terminal)                        │
│                                                                 │
│  ┌──────────┐    ┌──────────────┐    ┌────────────────────┐    │
│  │   MIC    │───▶│  STT Module  │───▶│   Intent Parser    │    │
│  │(PyAudio) │    │faster-whisper│    │  (Ollama / Groq)   │    │
│  └──────────┘    └──────────────┘    └────────┬───────────┘    │
│                                               │                 │
│                                               ▼                 │
│  ┌──────────┐    ┌──────────────┐    ┌────────────────────┐    │
│  │  SPEAKER │◀───│  TTS Module  │◀───│  Command Executor  │    │
│  │ (piper)  │    │  piper-tts   │    │   (subprocess)     │    │
│  └──────────┘    └──────────────┘    └────────────────────┘    │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    CONFIG (.env)                        │   │
│  │  OLLAMA_MODEL · GROQ_API_KEY · WAKE_WORD · LANGUAGE    │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘

  Sin GUI · Sin navegador · ~30MB overhead · Corre como systemd service
```

### Flujo de datos paso a paso

```
1. Sistema escucha el micrófono continuamente (modo siempre activo)
2. Detecta la wake word (ej: "Limits")
3. Graba el audio del comando (hasta silencio o 10 segundos)
4. faster-whisper transcribe el audio a texto (local, sin red)
5. El texto va al LLM con el system prompt + contexto del sistema
   ├── Intenta Ollama local (qwen2.5:7b) — privado, sin costo
   └── Si Ollama falla → fallback a Groq API (gratuita, oficial)
6. El LLM responde con un JSON estructurado: { intent, action, params, response }
7. El Command Executor interpreta el JSON y ejecuta la acción via subprocess
8. piper-tts sintetiza la respuesta en voz (local)
9. Vuelve al paso 1
```

### Consumo de recursos estimado (16GB RAM)

```
Ollama con qwen2.5:7b   → ~5-6 GB RAM
faster-whisper small    → ~1 GB RAM
piper-tts               → ~200 MB RAM
Python runtime          → ~100 MB RAM
─────────────────────────────────────
Total activo            → ~7-8 GB RAM
Libre para el resto     → ~8-9 GB RAM   ✅ suficiente
```

---

## 3. Requisitos y Dependencias

### Sistema operativo

- CachyOS / Arch Linux con Hyprland (Omarchy)
- Python 3.11+
- RAM: 8GB mínimo, 16GB recomendado
- CPU: cualquier moderno (AMD o Intel)
- GPU: opcional (acelera STT y TTS, no requerida)

### Instalación de dependencias del sistema

```bash
# Dependencias del sistema
sudo pacman -S python python-pip portaudio ffmpeg espeak-ng

# Ollama (LLM local) — API oficial, gratuita, sin límites
yay -S ollama
sudo systemctl enable --now ollama

# Modelo recomendado para 16GB RAM (5-6GB en uso)
ollama pull qwen2.5:7b

# Modelo ligero alternativo si quieres menor consumo (~2-3GB RAM)
# ollama pull llama3.2:3b

# Piper TTS (síntesis de voz en español, local)
yay -S piper-tts

# Descargar voz en español
mkdir -p ~/.local/share/piper
cd ~/.local/share/piper
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/es/es_ES/davefx/medium/es_ES-davefx-medium.onnx
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/es/es_ES/davefx/medium/es_ES-davefx-medium.onnx.json
```

### Obtener Groq API Key (gratuita)

```
1. Ir a https://console.groq.com
2. Crear cuenta (Google OAuth disponible)
3. API Keys → Create API Key
4. Copiar la key al .env
```

El free tier de Groq incluye:
- 14,400 requests/día con `llama-3.1-8b-instant`
- Suficiente para un uso intensivo de Limits

### Instalación de dependencias Python

```bash
# Crear entorno virtual
python -m venv ~/.limits-env
source ~/.limits-env/bin/activate

# Instalar paquetes
pip install \
  faster-whisper \
  pyaudio \
  groq \
  python-dotenv \
  requests \
  rich \
  pynput \
  webrtcvad \
  numpy \
  scipy
```

---

## 4. Estructura del Proyecto

```
~/Limits/
├── .env                    # Variables de entorno y configuración
├── .gitignore              # Excluir .env, __pycache__, logs, .onnx
├── README.md               # Documentación pública (ver sección 14)
├── main.py                 # Orquestador principal / punto de entrada
├── config.py               # Carga y valida la configuración
│
├── modules/
│   ├── __init__.py
│   ├── stt.py              # Speech-to-Text (faster-whisper)
│   ├── llm.py              # Motor LLM (Ollama principal + Groq fallback)
│   ├── executor.py         # Ejecutor de comandos del sistema
│   ├── tts.py              # Text-to-Speech (piper)
│   └── listener.py         # Escucha continua + detección de wake word
│
├── commands/
│   ├── __init__.py
│   ├── apps.py             # Abrir/cerrar aplicaciones
│   ├── system.py           # Control del sistema (volumen, brillo, etc.)
│   ├── files.py            # Operaciones de archivos
│   ├── web.py              # Búsquedas y navegación web
│   ├── dev.py              # Comandos de desarrollo (git, docker, etc.)
│   └── custom.py           # Comandos personalizados
│
├── prompts/
│   └── system_prompt.txt   # System prompt del LLM (editable sin tocar código)
│
└── logs/
    └── limits.log          # Log de sesiones
```

---

## 5. System Prompt del LLM

Este es el corazón del sistema. Pégalo en `prompts/system_prompt.txt`:

```
Eres Limits, un asistente de voz para Linux que controla un sistema CachyOS con Hyprland.
Tu única función es interpretar comandos de voz del usuario y devolver un JSON estructurado
con la acción a ejecutar. NUNCA respondas en formato libre. SIEMPRE responde en JSON válido.

## SISTEMA OPERATIVO
- Distro: CachyOS (base Arch Linux)
- Window Manager: Hyprland (Wayland)
- Shell: Fish
- Usuario: {username}
- Home: /home/{username}

## FORMATO DE RESPUESTA OBLIGATORIO
Responde ÚNICAMENTE con este JSON, sin texto adicional, sin markdown, sin explicaciones:

{
  "intent": "string",
  "action": "string",
  "params": {},
  "response": "string",
  "confidence": 0.0
}

Campos:
- intent: categoría del comando (app_open, app_close, system_volume, system_brightness,
          file_open, file_search, web_search, web_open, dev_git, dev_docker,
          dev_terminal, system_info, custom, unknown)
- action: nombre de la función Python a ejecutar (snake_case)
- params: parámetros necesarios para ejecutar la acción (dict)
- response: lo que Limits debe decir en voz alta (máximo 20 palabras, natural, en español)
- confidence: qué tan seguro estás de la interpretación (0.0 a 1.0)

## APLICACIONES DISPONIBLES
Mapea nombres coloquiales a sus comandos reales:
- "firefox" / "navegador" / "internet" → firefox
- "terminal" / "consola" → ghostty
- "código" / "editor" / "neovim" / "nvim" → ghostty -e nvim
- "spotify" / "música" → spotify
- "discord" → discord
- "slack" → slack
- "obsidian" / "notas" → obsidian
- "thunar" / "archivos" / "explorador" → thunar
- "calculadora" → gnome-calculator
- "configuración" → hyprctl dispatch exec [configuración del sistema]

## EJEMPLOS DE ENTRADA Y SALIDA

Entrada: "abre el navegador"
Salida:
{
  "intent": "app_open",
  "action": "open_application",
  "params": {"app": "firefox", "args": []},
  "response": "Abriendo Firefox.",
  "confidence": 0.98
}

Entrada: "sube el volumen al 70 por ciento"
Salida:
{
  "intent": "system_volume",
  "action": "set_volume",
  "params": {"level": 70, "mode": "absolute"},
  "response": "Volumen al 70 por ciento.",
  "confidence": 0.97
}

Entrada: "busca en google cómo instalar docker en arch"
Salida:
{
  "intent": "web_search",
  "action": "web_search",
  "params": {"query": "cómo instalar docker en arch linux", "engine": "google"},
  "response": "Buscando en Google.",
  "confidence": 0.95
}

Entrada: "muestra el estado de docker"
Salida:
{
  "intent": "dev_docker",
  "action": "run_terminal_command",
  "params": {"command": "docker ps", "show_output": true},
  "response": "Mostrando contenedores de Docker.",
  "confidence": 0.96
}

Entrada: "¿cuánta RAM estoy usando?"
Salida:
{
  "intent": "system_info",
  "action": "get_system_info",
  "params": {"type": "memory"},
  "response": "Revisando uso de memoria.",
  "confidence": 0.99
}

Entrada: "cierra spotify"
Salida:
{
  "intent": "app_close",
  "action": "close_application",
  "params": {"app": "spotify"},
  "response": "Cerrando Spotify.",
  "confidence": 0.97
}

Entrada: "modo no molestar"
Salida:
{
  "intent": "system_volume",
  "action": "set_volume",
  "params": {"level": 0, "mode": "absolute"},
  "response": "Silenciando el sistema.",
  "confidence": 0.90
}

Entrada: "abre una terminal nueva"
Salida:
{
  "intent": "app_open",
  "action": "open_application",
  "params": {"app": "ghostty", "args": []},
  "response": "Abriendo una nueva terminal.",
  "confidence": 0.99
}

## REGLAS CRÍTICAS
1. NUNCA incluyas texto fuera del JSON
2. Si no entiendes el comando, usa intent "unknown" y pide clarificación en "response"
3. Para comandos de terminal potencialmente destructivos (rm -rf, sudo, etc.),
   establece "requires_confirmation": true en params
4. El campo "response" debe ser conversacional y breve, como hablaría un asistente real
5. Si el confidence es menor a 0.6, pide confirmación al usuario
6. NUNCA inventes aplicaciones o comandos que no existan en el sistema
7. Infiere el idioma del usuario y responde en ese mismo idioma
```

---

## 6. Módulo de Voz a Texto (STT)

**Archivo: `modules/stt.py`**

```python
"""
Módulo STT — Speech to Text usando faster-whisper
Transcribe audio del micrófono a texto en tiempo real.
Corre 100% local, sin enviar audio a la nube.

Modelos disponibles (en orden de velocidad/precisión):
  tiny    → ~1GB RAM, muy rápido, menos preciso
  base    → ~1GB RAM, buena velocidad, aceptable precisión
  small   → ~2GB RAM, balance ideal                         ← RECOMENDADO
  medium  → ~5GB RAM, muy preciso, más lento
  large-v3→ ~10GB RAM, mejor precisión, requiere GPU
"""

import io
import numpy as np
import pyaudio
import wave
import webrtcvad
from faster_whisper import WhisperModel
from rich.console import Console

console = Console()

class STTEngine:
    def __init__(self, model_size: str = "small", language: str = "es", device: str = "cpu"):
        """
        Args:
            model_size: Tamaño del modelo Whisper (tiny/base/small/medium)
            language:   Código de idioma (es=español, en=inglés, None=autodetect)
            device:     'cpu' o 'cuda' si tienes GPU NVIDIA
        """
        console.print(f"[cyan]Cargando modelo Whisper '{model_size}'...[/cyan]")

        self.model = WhisperModel(
            model_size,
            device=device,
            compute_type="int8",  # int8 = menos RAM, suficiente precisión
        )
        self.language = language

        # Configuración de audio
        self.RATE = 16000          # Hz requerido por Whisper
        self.CHUNK = 480           # 30ms chunks (requerido por webrtcvad)
        self.FORMAT = pyaudio.paInt16
        self.CHANNELS = 1
        self.SILENCE_THRESHOLD = 30  # frames de silencio antes de cortar
        self.MAX_DURATION = 10       # segundos máximos de grabación

        # VAD (Voice Activity Detection) para detectar cuando hablas
        self.vad = webrtcvad.Vad(2)  # agresividad 0-3, 2 es buen balance

        self.audio = pyaudio.PyAudio()
        console.print("[green]✓ STT listo[/green]")

    def record_until_silence(self) -> bytes:
        """
        Graba audio desde el micrófono hasta detectar silencio.
        Returns: bytes del audio grabado en formato WAV
        """
        stream = self.audio.open(
            format=self.FORMAT,
            channels=self.CHANNELS,
            rate=self.RATE,
            input=True,
            frames_per_buffer=self.CHUNK
        )

        frames = []
        silent_frames = 0
        speaking = False
        total_frames = 0
        max_frames = int(self.RATE / self.CHUNK * self.MAX_DURATION)

        console.print("[yellow]🎙️  Escuchando...[/yellow]")

        while total_frames < max_frames:
            data = stream.read(self.CHUNK, exception_on_overflow=False)
            frames.append(data)
            total_frames += 1

            try:
                is_speech = self.vad.is_speech(data, self.RATE)
            except Exception:
                is_speech = False

            if is_speech:
                speaking = True
                silent_frames = 0
            elif speaking:
                silent_frames += 1
                if silent_frames > self.SILENCE_THRESHOLD:
                    break

        stream.stop_stream()
        stream.close()

        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, 'wb') as wf:
            wf.setnchannels(self.CHANNELS)
            wf.setsampwidth(self.audio.get_sample_size(self.FORMAT))
            wf.setframerate(self.RATE)
            wf.writeframes(b''.join(frames))

        return wav_buffer.getvalue()

    def transcribe(self, audio_bytes: bytes) -> str:
        """
        Transcribe audio WAV a texto.
        Args:
            audio_bytes: Audio en formato WAV como bytes
        Returns:
            Texto transcrito
        """
        audio_buffer = io.BytesIO(audio_bytes)

        segments, info = self.model.transcribe(
            audio_buffer,
            language=self.language,
            beam_size=5,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=500)
        )

        text = " ".join([segment.text for segment in segments]).strip()

        if text:
            console.print(f"[blue]📝 Transcrito:[/blue] {text}")

        return text

    def listen_and_transcribe(self) -> str:
        """Helper: graba y transcribe en un solo paso."""
        audio = self.record_until_silence()
        return self.transcribe(audio)

    def cleanup(self):
        """Libera recursos de audio."""
        self.audio.terminate()
```

---

## 7. Módulo del Motor LLM

**Archivo: `modules/llm.py`**

```python
"""
Módulo LLM — Motor de inteligencia artificial
Soporta Ollama (local, principal) con fallback automático a Groq API (cloud, gratuita).

Prioridad:
  1. Ollama local (qwen2.5:7b) → privado, sin costo, sin internet, sin límites
  2. Groq API (llama3-8b)      → fallback oficial si Ollama falla, muy rápido, gratis

Por qué este orden:
  - Ollama garantiza privacidad y disponibilidad offline
  - Groq es la API cloud más rápida del mercado en free tier (oficial)
  - Ambas usan formato de mensajes compatible con OpenAI spec
"""

import json
import requests
from groq import Groq
from rich.console import Console
from config import Config

console = Console()

class LLMEngine:
    def __init__(self, config: Config):
        self.config = config
        self.system_prompt = self._load_system_prompt()
        self.conversation_history = []

        # Inicializar cliente Groq si hay API key
        self.groq_client = None
        if config.GROQ_API_KEY:
            self.groq_client = Groq(api_key=config.GROQ_API_KEY)
            console.print("[green]✓ Groq API configurada como fallback[/green]")

        self._check_ollama()

    def _load_system_prompt(self) -> str:
        """Carga el system prompt desde archivo."""
        try:
            with open("prompts/system_prompt.txt", "r", encoding="utf-8") as f:
                prompt = f.read()
            import os
            prompt = prompt.replace("{username}", os.getenv("USER", "usuario"))
            return prompt
        except FileNotFoundError:
            console.print("[red]⚠️  system_prompt.txt no encontrado[/red]")
            return "Eres Limits, un asistente de Linux. Responde en JSON."

    def _check_ollama(self):
        """Verifica que Ollama esté corriendo y el modelo disponible."""
        try:
            response = requests.get(
                f"{self.config.OLLAMA_URL}/api/tags",
                timeout=3
            )
            if response.status_code == 200:
                models = [m["name"] for m in response.json().get("models", [])]
                model_base = self.config.OLLAMA_MODEL.split(":")[0]
                available = any(model_base in m for m in models)

                if available:
                    console.print(f"[green]✓ Ollama listo con {self.config.OLLAMA_MODEL}[/green]")
                else:
                    console.print(f"[yellow]⚠️  Modelo {self.config.OLLAMA_MODEL} no encontrado.[/yellow]")
                    console.print(f"[yellow]   Ejecuta: ollama pull {self.config.OLLAMA_MODEL}[/yellow]")
        except requests.exceptions.ConnectionError:
            console.print("[yellow]⚠️  Ollama no está corriendo. Usando Groq como principal.[/yellow]")
            console.print("[yellow]   Para iniciar: sudo systemctl start ollama[/yellow]")

    def _query_ollama(self, user_text: str) -> dict | None:
        """Consulta al LLM local via Ollama."""
        try:
            payload = {
                "model": self.config.OLLAMA_MODEL,
                "messages": [
                    {"role": "system", "content": self.system_prompt},
                    *self.conversation_history[-6:],
                    {"role": "user", "content": user_text}
                ],
                "stream": False,
                "format": "json",
                "options": {
                    "temperature": 0.1,
                    "num_predict": 300,
                }
            }

            response = requests.post(
                f"{self.config.OLLAMA_URL}/api/chat",
                json=payload,
                timeout=30
            )

            if response.status_code == 200:
                content = response.json()["message"]["content"]
                return json.loads(content)

        except (requests.exceptions.RequestException, json.JSONDecodeError, KeyError) as e:
            console.print(f"[yellow]Ollama falló: {e}. Usando Groq...[/yellow]")
            return None

    def _query_groq(self, user_text: str) -> dict | None:
        """Consulta a Groq API como fallback (oficial, gratuita)."""
        if not self.groq_client:
            console.print("[red]Error: No hay Groq API key configurada.[/red]")
            return None

        try:
            response = self.groq_client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    *self.conversation_history[-6:],
                    {"role": "user", "content": user_text}
                ],
                temperature=0.1,
                max_tokens=300,
                response_format={"type": "json_object"}
            )

            content = response.choices[0].message.content
            return json.loads(content)

        except Exception as e:
            console.print(f"[red]Groq también falló: {e}[/red]")
            return None

    def process(self, user_text: str) -> dict:
        """
        Procesa texto del usuario y devuelve la intención estructurada.
        Intenta Ollama primero, luego Groq automáticamente.
        """
        console.print(f"[dim]Procesando: '{user_text}'[/dim]")

        result = self._query_ollama(user_text) or self._query_groq(user_text)

        if not result:
            return {
                "intent": "unknown",
                "action": "speak_error",
                "params": {},
                "response": "No pude procesar ese comando. ¿Puedes repetirlo?",
                "confidence": 0.0
            }

        self.conversation_history.append({"role": "user", "content": user_text})
        self.conversation_history.append({
            "role": "assistant",
            "content": json.dumps(result)
        })

        if len(self.conversation_history) > 10:
            self.conversation_history = self.conversation_history[-10:]

        console.print(f"[dim]Intent: {result.get('intent')} | Confidence: {result.get('confidence', 0):.2f}[/dim]")

        return result
```

---

## 8. Módulo de Ejecución de Comandos

**Archivo: `modules/executor.py`**

```python
"""
Módulo Executor — Ejecuta acciones reales en el sistema operativo.
Mapea los intents del LLM a funciones Python concretas via subprocess.

SEGURIDAD: Los comandos destructivos requieren confirmación verbal.
"""

import subprocess
import psutil
from rich.console import Console
from commands.apps import AppCommands
from commands.system import SystemCommands
from commands.web import WebCommands
from commands.dev import DevCommands

console = Console()

class CommandExecutor:
    def __init__(self):
        self.apps = AppCommands()
        self.system = SystemCommands()
        self.web = WebCommands()
        self.dev = DevCommands()

        self.action_map = {
            "open_application":     self.apps.open_app,
            "close_application":    self.apps.close_app,
            "list_running_apps":    self.apps.list_running,
            "set_volume":           self.system.set_volume,
            "get_volume":           self.system.get_volume,
            "set_brightness":       self.system.set_brightness,
            "lock_screen":          self.system.lock_screen,
            "shutdown":             self.system.shutdown,
            "reboot":               self.system.reboot,
            "get_system_info":      self.system.get_info,
            "take_screenshot":      self.system.screenshot,
            "web_search":           self.web.search,
            "open_url":             self.web.open_url,
            "run_terminal_command": self.dev.run_command,
            "git_status":           self.dev.git_status,
            "docker_status":        self.dev.docker_status,
            "open_project":         self.dev.open_project,
            "speak_error":          self._noop,
        }

        self.DANGEROUS_ACTIONS = {"shutdown", "reboot", "run_terminal_command"}

    def execute(self, parsed_result: dict) -> str:
        """
        Ejecuta la acción indicada por el LLM.
        Returns: Texto de respuesta para sintetizar en voz
        """
        action = parsed_result.get("action", "speak_error")
        params = parsed_result.get("params", {})
        response = parsed_result.get("response", "Hecho.")
        confidence = parsed_result.get("confidence", 1.0)
        requires_confirmation = params.get("requires_confirmation", False)

        if confidence < 0.5:
            return "No estoy seguro de lo que quieres hacer. ¿Puedes ser más específico?"

        if action in self.DANGEROUS_ACTIONS or requires_confirmation:
            return "Este comando requiere confirmación. Di 'confirmar' para ejecutarlo."

        handler = self.action_map.get(action)

        if handler:
            try:
                result = handler(**params)
                if result and isinstance(result, str) and result != response:
                    return f"{response} {result}"
                return response
            except TypeError as e:
                console.print(f"[red]Error en parámetros de '{action}': {e}[/red]")
                return "Ocurrió un error al ejecutar ese comando."
            except Exception as e:
                console.print(f"[red]Error ejecutando '{action}': {e}[/red]")
                return "No pude completar esa acción."
        else:
            console.print(f"[yellow]Acción no implementada: '{action}'[/yellow]")
            return response

    def _noop(self, **kwargs) -> None:
        pass
```

**Archivo: `commands/apps.py`**

```python
"""Comandos para abrir y cerrar aplicaciones."""

import subprocess
import psutil
from rich.console import Console

console = Console()

class AppCommands:
    APP_MAP = {
        "firefox":          ["firefox"],
        "ghostty":          ["ghostty"],
        "spotify":          ["spotify"],
        "discord":          ["discord"],
        "slack":            ["slack"],
        "obsidian":         ["obsidian"],
        "thunar":           ["thunar"],
        "nvim":             ["ghostty", "-e", "nvim"],
        "neovim":           ["ghostty", "-e", "nvim"],
        "lazygit":          ["ghostty", "-e", "lazygit"],
        "htop":             ["ghostty", "-e", "htop"],
        "bruno":            ["bruno"],
        "tableplus":        ["tableplus"],
        "figma-linux":      ["figma-linux"],
        "gnome-calculator": ["gnome-calculator"],
        "flameshot":        ["flameshot", "gui"],
        "obs":              ["obs"],
    }

    def open_app(self, app: str, args: list = []) -> None:
        cmd = self.APP_MAP.get(app.lower(), [app]) + args
        try:
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, start_new_session=True)
            console.print(f"[green]✓ Abriendo {app}[/green]")
        except FileNotFoundError:
            console.print(f"[red]✗ Aplicación '{app}' no encontrada[/red]")

    def close_app(self, app: str) -> None:
        app_lower = app.lower()
        killed = False
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                if app_lower in proc.info['name'].lower():
                    proc.terminate()
                    killed = True
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        if not killed:
            console.print(f"[yellow]'{app}' no estaba corriendo[/yellow]")

    def list_running(self) -> str:
        apps = set()
        for proc in psutil.process_iter(['name']):
            try:
                apps.add(proc.info['name'])
            except psutil.NoSuchProcess:
                pass
        return ", ".join(sorted(apps)[:10])
```

**Archivo: `commands/system.py`**

```python
"""Comandos de control del sistema operativo."""

import subprocess
import psutil
from rich.console import Console

console = Console()

class SystemCommands:
    def set_volume(self, level: int, mode: str = "absolute") -> None:
        if mode == "relative":
            sign = "+" if level > 0 else ""
            cmd = f"wpctl set-volume @DEFAULT_AUDIO_SINK@ {sign}{level}%"
        else:
            level = max(0, min(100, level))
            cmd = f"wpctl set-volume @DEFAULT_AUDIO_SINK@ {level}%"
        subprocess.run(cmd, shell=True, check=True)

    def get_volume(self) -> str:
        result = subprocess.run(
            "wpctl get-volume @DEFAULT_AUDIO_SINK@",
            shell=True, capture_output=True, text=True
        )
        return result.stdout.strip()

    def set_brightness(self, level: int) -> None:
        level = max(0, min(100, level))
        subprocess.run(f"brightnessctl set {level}%", shell=True, check=True)

    def lock_screen(self) -> None:
        subprocess.Popen(["hyprlock"], start_new_session=True)

    def screenshot(self) -> None:
        subprocess.Popen(["flameshot", "gui"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def get_info(self, type: str = "all") -> str:
        if type == "memory":
            mem = psutil.virtual_memory()
            used_gb = mem.used / (1024**3)
            total_gb = mem.total / (1024**3)
            return f"Usas {used_gb:.1f} GB de {total_gb:.1f} GB ({mem.percent}%)"
        elif type == "cpu":
            cpu = psutil.cpu_percent(interval=1)
            return f"CPU al {cpu}%"
        elif type == "disk":
            disk = psutil.disk_usage('/')
            free_gb = disk.free / (1024**3)
            return f"Tienes {free_gb:.1f} GB libres en disco"
        else:
            mem = psutil.virtual_memory()
            cpu = psutil.cpu_percent(interval=0.5)
            return f"CPU: {cpu}% | RAM: {mem.percent}%"

    def shutdown(self) -> None:
        subprocess.run(["shutdown", "now"])

    def reboot(self) -> None:
        subprocess.run(["reboot"])
```

---

## 9. Módulo de Texto a Voz (TTS)

**Archivo: `modules/tts.py`**

```python
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
    def __init__(self, voice_model: str = None, voice_speed: float = 1.0):
        self.voice_model = voice_model or os.path.expanduser(
            "~/.local/share/piper/es_ES-davefx-medium.onnx"
        )
        self.voice_speed = voice_speed
        self._verify_voice()

    def _verify_voice(self):
        if not os.path.exists(self.voice_model):
            console.print(f"[red]⚠️  Voz no encontrada: {self.voice_model}[/red]")
        else:
            console.print("[green]✓ TTS listo[/green]")

    def speak(self, text: str) -> None:
        if not text or not text.strip():
            return

        console.print(f"[magenta]🔊 Limits:[/magenta] {text}")

        try:
            piper_cmd = [
                "piper",
                "--model", self.voice_model,
                "--output-raw",
                "--length-scale", str(1.0 / self.voice_speed),
            ]

            aplay_cmd = ["aplay", "-r", "22050", "-f", "S16_LE", "-t", "raw", "-"]

            piper_proc = subprocess.Popen(
                piper_cmd, stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
            )

            aplay_proc = subprocess.Popen(
                aplay_cmd, stdin=piper_proc.stdout,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )

            piper_proc.stdin.write(text.encode("utf-8"))
            piper_proc.stdin.close()
            aplay_proc.wait()

        except FileNotFoundError:
            console.print("[yellow]piper no encontrado, usando espeak...[/yellow]")
            subprocess.run(["espeak-ng", "-v", "es", "-s", "150", text],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as e:
            console.print(f"[red]Error en TTS: {e}[/red]")
```

---

## 10. Orquestador Principal

**Archivo: `main.py`**

```python
"""
Limits LINUX — Punto de entrada principal
Orquesta todos los módulos: STT → LLM → Executor → TTS

Uso:
    python main.py              # Modo normal (siempre escuchando)
    python main.py --text       # Modo texto (sin micrófono, para testing)
    python main.py --once       # Ejecuta un solo comando y sale
"""

import sys
import argparse
from rich.console import Console
from rich.panel import Panel

from config import Config
from modules.stt import STTEngine
from modules.llm import LLMEngine
from modules.executor import CommandExecutor
from modules.tts import TTSEngine

console = Console()

def print_banner():
    console.print(Panel.fit(
        "[bold cyan]Limits LINUX[/bold cyan]\n"
        "[dim]CachyOS + Ollama (local) + Groq (fallback)[/dim]\n"
        "[dim]Di 'Limits' para activar[/dim]",
        border_style="cyan"
    ))

def run_pipeline(user_input: str, llm: LLMEngine, executor: CommandExecutor, tts: TTSEngine):
    """Ejecuta el pipeline completo para un input de usuario."""
    parsed = llm.process(user_input)
    response_text = executor.execute(parsed)
    tts.speak(response_text)

def main():
    parser = argparse.ArgumentParser(description="Limits Linux Assistant")
    parser.add_argument("--text", action="store_true", help="Modo texto (sin micrófono)")
    parser.add_argument("--once", action="store_true", help="Ejecutar un solo comando")
    args = parser.parse_args()

    print_banner()

    config = Config()

    console.print("\n[bold]Iniciando módulos...[/bold]")

    llm = LLMEngine(config)
    executor = CommandExecutor()
    tts = TTSEngine(voice_speed=config.VOICE_SPEED)

    if not args.text:
        stt = STTEngine(
            model_size=config.WHISPER_MODEL,
            language=config.LANGUAGE,
            device=config.STT_DEVICE
        )

    console.print("\n[bold green]✓ Limits listo.[/bold green]\n")
    tts.speak("Limits listo. ¿En qué te puedo ayudar?")

    try:
        while True:
            if args.text:
                user_input = input("\n[Tú]: ").strip()
                if not user_input:
                    continue
                if user_input.lower() in ("salir", "exit", "quit"):
                    break
            else:
                user_input = stt.listen_and_transcribe()

                if not user_input:
                    continue

                wake = config.WAKE_WORD.lower()
                if wake and wake not in user_input.lower():
                    continue

                user_input = user_input.lower().replace(wake, "").strip()

                if not user_input:
                    tts.speak("¿Sí?")
                    user_input = stt.listen_and_transcribe()

            if user_input:
                run_pipeline(user_input, llm, executor, tts)

            if args.once:
                break

    except KeyboardInterrupt:
        console.print("\n[yellow]Limits apagado.[/yellow]")
        tts.speak("Hasta luego.")
    finally:
        if not args.text:
            stt.cleanup()

if __name__ == "__main__":
    main()
```

---

## 11. Configuración y Variables de Entorno

**Archivo: `.env`**

```ini
# ─── LLM LOCAL (PRINCIPAL) ──────────────────────────────────────────────────
# Ollama corre localmente, sin costo, sin internet
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5:7b

# ─── LLM CLOUD (FALLBACK GRATUITO) ──────────────────────────────────────────
# Groq API — oficial, gratuita, extremadamente rápida
# Obtén tu key en: https://console.groq.com (gratis, sin tarjeta)
GROQ_API_KEY=gsk_xxxxxxxxxxxxxxxxxxxxxxxx

# ─── SPEECH TO TEXT ─────────────────────────────────────────────────────────
# Modelo Whisper: tiny, base, small (recomendado), medium
WHISPER_MODEL=small
# Idioma: es (español), en (inglés), None (autodetect)
LANGUAGE=es
# Dispositivo: cpu o cuda (GPU NVIDIA)
STT_DEVICE=cpu

# ─── TEXT TO SPEECH ─────────────────────────────────────────────────────────
PIPER_VOICE_MODEL=~/.local/share/piper/es_ES-davefx-medium.onnx
# Velocidad de la voz (0.8=lento, 1.0=normal, 1.2=rápido)
VOICE_SPEED=1.0

# ─── COMPORTAMIENTO ─────────────────────────────────────────────────────────
# Palabra de activación. Dejar vacío para siempre activo.
WAKE_WORD=Limits
RESPONSE_LANGUAGE=es
```

**Archivo: `config.py`**

```python
import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
    OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")
    GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
    WHISPER_MODEL = os.getenv("WHISPER_MODEL", "small")
    LANGUAGE = os.getenv("LANGUAGE", "es")
    STT_DEVICE = os.getenv("STT_DEVICE", "cpu")
    PIPER_VOICE_MODEL = os.getenv("PIPER_VOICE_MODEL", "~/.local/share/piper/es_ES-davefx-medium.onnx")
    VOICE_SPEED = float(os.getenv("VOICE_SPEED", "1.0"))
    WAKE_WORD = os.getenv("WAKE_WORD", "Limits")
    RESPONSE_LANGUAGE = os.getenv("RESPONSE_LANGUAGE", "es")
```

**Archivo: `.gitignore`**

```gitignore
# Nunca subir a GitHub
.env
*.onnx
*.onnx.json
logs/
__pycache__/
*.pyc
.Limits-env/
*.wav
*.mp3
```

---

## 12. Comandos Reconocidos y Ejemplos

### Apps
| Di esto | Acción |
|---|---|
| "Limits, abre Firefox" | Abre Firefox |
| "Limits, abre una terminal" | Abre Ghostty |
| "Limits, abre Spotify" | Abre Spotify |
| "Limits, cierra Discord" | Cierra Discord |
| "Limits, abre el editor de código" | Abre Neovim en Ghostty |

### Sistema
| Di esto | Acción |
|---|---|
| "Limits, sube el volumen al 80" | Volumen → 80% |
| "Limits, silencia todo" | Volumen → 0% |
| "Limits, ¿cuánta RAM estoy usando?" | Info de memoria |
| "Limits, toma una captura de pantalla" | Lanza Flameshot |
| "Limits, bloquea la pantalla" | Ejecuta Hyprlock |

### Web
| Di esto | Acción |
|---|---|
| "Limits, busca en Google Spring Boot tips" | Abre Google con la búsqueda |
| "Limits, abre GitHub" | Abre github.com |

### Desarrollo
| Di esto | Acción |
|---|---|
| "Limits, muestra los contenedores de Docker" | `docker ps` en terminal |
| "Limits, ¿cuánta RAM tengo libre?" | Muestra memoria disponible |

---

## 13. Extensión y Personalización

### Agregar un comando nuevo

1. Agrega la función en `commands/custom.py`:

```python
def mi_comando(self, param1: str) -> str:
    subprocess.Popen(["mi-app", param1])
    return f"Ejecutando con {param1}"
```

2. Regístrala en `modules/executor.py`:

```python
"mi_accion": self.custom.mi_comando,
```

3. Agrega un ejemplo en `prompts/system_prompt.txt`:

```
Entrada: "haz mi cosa especial"
Salida:
{
  "intent": "custom",
  "action": "mi_accion",
  "params": {"param1": "valor"},
  "response": "Ejecutando tu cosa especial.",
  "confidence": 0.95
}
```

### Cambiar idioma a inglés

En `.env`:
```ini
LANGUAGE=en
WAKE_WORD=Limits
RESPONSE_LANGUAGE=en
PIPER_VOICE_MODEL=~/.local/share/piper/en_US-lessac-medium.onnx
```

### Ejecutar como servicio del sistema (sin GUI, segundo plano)

```bash
mkdir -p ~/.config/systemd/user

cat > ~/.config/systemd/user/Limits.service << EOF
[Unit]
Description=Limits Linux Assistant
After=network.target sound.target

[Service]
Type=simple
WorkingDirectory=%h/Limits
ExecStart=%h/.Limits-env/bin/python main.py
Restart=on-failure
Environment=DISPLAY=:0
Environment=WAYLAND_DISPLAY=wayland-1

[Install]
WantedBy=default.target
EOF

systemctl --user enable --now Limits
systemctl --user status Limits
```

---

## 14. GitHub y Portafolio

### Por qué este proyecto tiene peso en un portafolio

Este proyecto demuestra habilidades que van más allá de tutoriales:

- **Arquitectura desacoplada**: módulos independientes con responsabilidad única
- **ML aplicado**: integración real de modelos de lenguaje y voz sin wrappers mágicos
- **Decisiones técnicas justificables**: patrón híbrido local/cloud, tradeoffs de modelos por RAM
- **Sistemas**: integración con systemd, Wayland, PipeWire
- **Stack confiable**: solo APIs y herramientas con soporte oficial

### Estructura del README.md para GitHub

```markdown
# 🤖 Limits Linux

> Voice assistant for Linux — runs entirely on your machine.
> No GUI · No cloud dependency · Hyprland/Wayland native

[GIF de demo aquí — grabado con OBS, ~15 segundos]

## Stack
- **STT**: faster-whisper (local)
- **LLM**: Ollama qwen2.5:7b (local) + Groq API fallback (cloud)
- **TTS**: piper-tts (local)
- **OS**: CachyOS + Hyprland (Wayland)

## Architecture
[diagrama ASCII del flujo — ya está en este doc]

## Why this stack?
- Ollama: private, no cost, no rate limits, works offline
- Groq: official free tier, fastest inference available, OpenAI-compatible
- Everything else runs locally → ~30MB overhead beyond the LLM

## Quick Start
[instrucciones de instalación]

## Extending
Adding a new command is a single Python function + one JSON example in the prompt.
```

### Badges recomendados para el README

```markdown
![Python](https://img.shields.io/badge/Python-3.11+-blue)
![Ollama](https://img.shields.io/badge/LLM-Ollama-green)
![Groq](https://img.shields.io/badge/Fallback-Groq-orange)
![License](https://img.shields.io/badge/License-MIT-lightgrey)
![Platform](https://img.shields.io/badge/Platform-Linux-informational)
```

### Lo más importante para el demo

Graba un video corto (15-30 segundos) con OBS mostrando:

```
1. Terminal abierta, Limits corriendo
2. Di: "Limits, abre Firefox"  → Firefox se abre
3. Di: "Limits, ¿cuánta RAM uso?"  → responde en voz
4. Di: "Limits, sube el volumen al 60"  → volumen cambia
```

Ese GIF en el README vale más que mil líneas de descripción.

---

## 15. Troubleshooting

### "Ollama no responde"
```bash
sudo systemctl status ollama
sudo systemctl start ollama
ollama list  # verificar que el modelo está descargado
```

### "No se escucha el micrófono"
```bash
arecord -l                              # listar dispositivos
alsamixer                               # ajustar volumen de entrada
arecord -d 3 test.wav && aplay test.wav # probar grabación
```

### "faster-whisper da error de memoria"
```bash
# En .env: WHISPER_MODEL=tiny
# O liberar RAM cerrando otras apps antes de iniciar Limits
```

### "piper no produce audio"
```bash
echo "Hola mundo" | piper \
  --model ~/.local/share/piper/es_ES-davefx-medium.onnx \
  --output-raw | aplay -r 22050 -f S16_LE -t raw -
```

### "Groq devuelve error 429 (rate limit)"
```bash
# El free tier tiene límite diario.
# Solución: asegurarse de que Ollama esté corriendo correctamente
# Groq solo debería activarse como fallback, no como principal.
sudo systemctl start ollama
ollama pull qwen2.5:7b
```

### "El LLM no entiende bien los comandos"
- Ajusta la temperatura en `llm.py` (más baja = más determinístico)
- Agrega más ejemplos al `system_prompt.txt`
- Prueba con un modelo más grande: `ollama pull llama3.1:8b`

---

*Stack: Python · Ollama (local) · Groq API (fallback oficial gratuito) · faster-whisper · piper-tts*
*Plataforma: CachyOS + Omarchy (Hyprland/Wayland) · 100% terminal, sin GUI*
