import os
from dotenv import load_dotenv

load_dotenv()


def _env_bool(name: str, default: str = "false") -> bool:
    v = os.getenv(name, default).strip().lower()
    return v in ("1", "true", "yes", "si", "sí")


class Config:
    PROJECT_ROOTS: str = os.getenv("PROJECT_ROOTS", "~/Proyectos:~/Work:~/Projects:~/Trabajo:~/Repos")
    PRESENCE_ENABLED: bool = _env_bool("PRESENCE_ENABLED")
    PRESENCE_SIZE: int = max(110, min(240, int(os.getenv("PRESENCE_SIZE", "172"))))
    PRESENCE_MARGIN_TOP: int = max(0, min(500, int(os.getenv("PRESENCE_MARGIN_TOP", "76"))))
    PRESENCE_MARGIN_RIGHT: int = max(0, min(500, int(os.getenv("PRESENCE_MARGIN_RIGHT", "18"))))
    PRESENCE_OPACITY: float = max(.3, min(1, float(os.getenv("PRESENCE_OPACITY", ".95"))))
    PRESENCE_REDUCED_MOTION: bool = _env_bool("PRESENCE_REDUCED_MOTION")
    PRESENCE_MONITOR: str = os.getenv("PRESENCE_MONITOR", "")
    PRESENCE_SOCKET: str = os.path.join(os.getenv("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}"), "limits", "presence.sock")
    LOG_PATH: str = os.getenv("LIMITS_LOG_PATH", "logs/limits.log")
    DIALOGUE_FOLLOWUP_SECONDS: int = max(0, min(30, int(os.getenv("DIALOGUE_FOLLOWUP_SECONDS", "10"))))
    GEMINI_STREAMING: bool = _env_bool("GEMINI_STREAMING", "true")
    # Coordinación por objetivos; modo anterior disponible para reversión.
    AGENT_ENABLED: bool = _env_bool("AGENT_ENABLED")
    # Un selector evita combinar coordinadores incompatibles.
    AGENT_MODE: str = os.getenv("AGENT_MODE", "legacy").strip().lower()
    if AGENT_MODE not in {"legacy", "local"}:
        raise ValueError("AGENT_MODE debe ser local o legacy.")
    AGENT_COGNITIVE_FALLBACK_MODEL: str = os.getenv("AGENT_COGNITIVE_FALLBACK_MODEL", "openai/gpt-oss-20b").strip()
    AGENT_COGNITIVE_PROVIDER: str = os.getenv("AGENT_COGNITIVE_PROVIDER", "ollama").strip().lower()
    AGENT_LOCAL_PROPOSALS: bool = _env_bool("AGENT_LOCAL_PROPOSALS", "true")
    AGENT_COHERENT: bool = _env_bool("AGENT_COHERENT")
    AGENT_SEMANTIC: bool = _env_bool("AGENT_SEMANTIC")
    if AGENT_MODE == "local":
        AGENT_ENABLED = AGENT_SEMANTIC = AGENT_COHERENT = True
        AGENT_LOCAL_PROPOSALS = False
        AGENT_COGNITIVE_PROVIDER = "ollama"
    SPOTIFY_MCP_ENABLED: bool = _env_bool("SPOTIFY_MCP_ENABLED")
    SPOTIFY_CLIENT_ID: str = os.getenv("SPOTIFY_CLIENT_ID", "").strip()
    SPOTIFY_TOKEN_PATH: str = os.path.expanduser(os.getenv("SPOTIFY_TOKEN_PATH", "~/.limits/spotify/token.json"))
    SPOTIFY_REDIRECT_URI: str = "http://127.0.0.1:8898/callback"
    SPOTIFY_MCP_TIMEOUT: float = max(3, min(30, float(os.getenv("SPOTIFY_MCP_TIMEOUT", "15"))))
    KNOWLEDGE_ENABLED: bool = _env_bool("KNOWLEDGE_ENABLED")
    KNOWLEDGE_VAULT: str = os.path.expanduser(os.getenv("KNOWLEDGE_VAULT", "~/Documentos/Limits-Memoria"))
    AGENT_LOCAL_READ_TIMEOUT: float = max(5, min(40, float(os.getenv("AGENT_LOCAL_READ_TIMEOUT", "20"))))
    AGENT_QWEN_DIAGNOSTICS: bool = _env_bool("AGENT_QWEN_DIAGNOSTICS")
    AGENT_ESCALATE: bool = _env_bool("AGENT_ESCALATE", "true")
    AGENT_TASK_PATH: str = os.path.expanduser(os.getenv("AGENT_TASK_PATH", "~/.limits/tareas"))
    AGENT_REMOTE_PROVIDER: str = os.getenv("AGENT_REMOTE_PROVIDER", "opencode_con_respaldo").strip().lower()
    NVIDIA_API_KEY: str = os.getenv("NVIDIA_API_KEY", "")
    NVIDIA_BASE_URL: str = os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
    NVIDIA_DEVELOPMENT_MODEL: str = os.getenv("NVIDIA_DEVELOPMENT_MODEL", "deepseek-ai/deepseek-v4.1-flash")
    NVIDIA_ANALYSIS_MODEL: str = os.getenv("NVIDIA_ANALYSIS_MODEL", "nvidia/nemotron-3.5-bolt-e4b")
    NVIDIA_GLM_API_KEY: str = os.getenv("NVIDIA_GLM_API_KEY", "")
    NVIDIA_GLM_MODEL: str = os.getenv("NVIDIA_GLM_MODEL", "z-ai/glm-5.3-flash")
    NVIDIA_SUPER_API_KEY: str = os.getenv("NVIDIA_SUPER_API_KEY", "")
    NVIDIA_SUPER_MODEL: str = os.getenv("NVIDIA_SUPER_MODEL", "nvidia/nemotron-3.5-super-vl-120b-a12b")
    NVIDIA_BOLT_API_KEY: str = os.getenv("NVIDIA_BOLT_API_KEY", "")
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    GROQ_BASE_URL: str = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
    GROQ_REASONING_EFFORT: str = os.getenv("GROQ_REASONING_EFFORT", "low")
    GROQ_AGENT_MODEL: str = os.getenv("GROQ_AGENT_MODEL", "openai/gpt-oss-120b")
    GROQ_MAX_TOKENS: int = max(512, min(8192, int(os.getenv("GROQ_MAX_TOKENS", "2048"))))
    AGENT_GLM_FALLBACK: bool = _env_bool("AGENT_GLM_FALLBACK")
    AGENT_GROQ_FALLBACK: bool = _env_bool("AGENT_GROQ_FALLBACK")
    AGENT_SUPER_FALLBACK: bool = _env_bool("AGENT_SUPER_FALLBACK")
    NVIDIA_MAX_TOKENS: int = max(512, min(16384, int(os.getenv("NVIDIA_MAX_TOKENS", "4096"))))
    NVIDIA_THINKING_ENABLED: bool = _env_bool("NVIDIA_THINKING_ENABLED", "true")
    NVIDIA_MODEL_COOLDOWN: float = max(0, min(600, float(os.getenv("NVIDIA_MODEL_COOLDOWN", "60"))))
    AGENT_OPENCODE_BIN: str = os.getenv("AGENT_OPENCODE_BIN", "opencode")
    AGENT_DEVELOPMENT_MODEL: str = os.getenv("AGENT_DEVELOPMENT_MODEL", "opencode/deepseek-v4.1-flash-free")
    AGENT_ANALYSIS_MODEL: str = os.getenv("AGENT_ANALYSIS_MODEL", "opencode/big-pickle")
    AGENT_MAX_STEPS: int = max(1, min(20, int(os.getenv("AGENT_MAX_STEPS", "6"))))
    AGENT_TIMEOUT: float = max(5, min(600, float(os.getenv("AGENT_TIMEOUT", "120"))))
    AGENT_CONTEXT_CHARS: int = max(2000, min(24000, int(os.getenv("AGENT_CONTEXT_CHARS", "12000"))))
    AGENT_VOICE_CHARS: int = max(200, min(4000, int(os.getenv("AGENT_VOICE_CHARS", "900"))))
    AGENT_APPROVAL_TTL: int = max(10, min(3600, int(os.getenv("AGENT_APPROVAL_TTL", "300"))))

    OLLAMA_URL: str        = os.getenv("OLLAMA_URL", "http://localhost:11434")
    OLLAMA_MODEL: str      = os.getenv("OLLAMA_MODEL", "qwen2.5:3b-instruct")
    AGENT_CONVERSATION_MODEL: str = os.getenv("AGENT_CONVERSATION_MODEL", "").strip() or OLLAMA_MODEL
    # El router es 100 % local (decisión 2026-10-28): sin proveedor cloud.
    OLLAMA_NUM_CTX: int    = int(os.getenv("OLLAMA_NUM_CTX", "8192"))
    OLLAMA_KEEP_ALIVE: str = os.getenv("OLLAMA_KEEP_ALIVE", "30m")

    # ── Cerebro conversacional Gemini (vía CLI gemdev) ───────────────────────
    # Salida SOLO a voz/log (jamás al executor). Docs: integracion-gemini.md
    GEMINI_ENABLED: bool   = _env_bool("GEMINI_ENABLED")
    GEMINI_BIN: str        = os.getenv("GEMINI_BIN", "~/.local/bin/gemdev")
    GEMINI_TIMEOUT: int    = int(os.getenv("GEMINI_TIMEOUT", "120"))
    GEMINI_SESSION: str    = os.getenv("GEMINI_SESSION",
                                       "~/.limits/gemini_session.json")
    GEMINI_RESEARCH_DAEMON: bool = _env_bool("GEMINI_RESEARCH_DAEMON")
    # Research: debajo de esto → fail-loud (no frases Jarvis vacías)
    GEMINI_MIN_RESEARCH_CHARS: int = int(
        os.getenv("GEMINI_MIN_RESEARCH_CHARS", "200"))

    WHISPER_MODEL: str     = os.getenv("WHISPER_MODEL", "small")
    LANGUAGE: str          = os.getenv("LANGUAGE", "es")
    STT_DEVICE: str        = os.getenv("STT_DEVICE", "cpu")
    PIPER_VOICE_MODEL: str = os.path.expanduser(
        os.getenv("PIPER_VOICE_MODEL", "~/.local/share/piper/es_ES-davefx-medium.onnx")
    )
    VOICE_SPEED: float     = float(os.getenv("VOICE_SPEED", "1.0"))
    VOICE_SPEAKER: int | None = int(os.getenv("VOICE_SPEAKER")) if os.getenv("VOICE_SPEAKER") else None
    WAKE_WORD: str         = os.getenv("WAKE_WORD", "Limits")
    RESPONSE_LANGUAGE: str = os.getenv("RESPONSE_LANGUAGE", "es")
    # Zona horaria para {now}; vacío = la del sistema
    TIMEZONE: str          = os.getenv("TIMEZONE", "")

    # ── Barge-in: interrumpir al asistente hablando (P0-4) ───────────────────
    BARGEIN_ENABLED: bool  = _env_bool("BARGEIN_ENABLED", "true")
    BARGEIN_KEYWORDS: str  = os.getenv(
        "BARGEIN_KEYWORDS", "para,cállate,callate,stop,basta,silencio")
    BARGEIN_MIN_MS: int    = int(os.getenv("BARGEIN_MIN_MS", "350"))

    # ── Voz natural ElevenLabs (solo respuestas largas; opt-in) ──────────────
    ELEVENLABS_ENABLED: bool      = _env_bool("ELEVENLABS_ENABLED")
    ELEVENLABS_API_KEY: str       = os.getenv("ELEVENLABS_API_KEY", "")
    ELEVENLABS_MODE: str          = os.getenv("ELEVENLABS_MODE", "auto")  # auto|gemini|off
    ELEVENLABS_MIN_CHARS: int     = int(os.getenv("ELEVENLABS_MIN_CHARS", "200"))
    ELEVENLABS_MAX_TURN_CHARS: int = int(os.getenv("ELEVENLABS_MAX_TURN_CHARS", "1200"))
    ELEVENLABS_VOICE_ID: str      = os.getenv("ELEVENLABS_VOICE_ID", "")
    ELEVENLABS_MODEL: str         = os.getenv("ELEVENLABS_MODEL", "eleven_turbo_v2_5")
    ELEVENLABS_STABILITY: float   = float(os.getenv("ELEVENLABS_STABILITY", "0.5"))
    ELEVENLABS_SIMILARITY: float  = float(os.getenv("ELEVENLABS_SIMILARITY", "0.75"))
    ELEVENLABS_CACHE: bool        = _env_bool("ELEVENLABS_CACHE", "true")

    # ── Gateway móvil (control remoto por voz desde Android; opt-in) ─────────
    GATEWAY_ENABLED: bool         = _env_bool("GATEWAY_ENABLED")
    GATEWAY_HOST: str             = os.getenv("GATEWAY_HOST", "0.0.0.0")
    GATEWAY_PORT: int             = int(os.getenv("GATEWAY_PORT", "8765"))
    GATEWAY_MDNS_NAME: str        = os.getenv("GATEWAY_MDNS_NAME", "Limits")
    GATEWAY_SPEAK_LOCAL: bool     = _env_bool("GATEWAY_SPEAK_LOCAL", "true")
    GATEWAY_TOKEN_PATH: str       = os.getenv("GATEWAY_TOKEN_PATH", "")
    # QR de emparejamiento en la terminal al arrancar (necesita `qrencode`)
    GATEWAY_SHOW_QR: bool         = _env_bool("GATEWAY_SHOW_QR", "true")

    # ── Memoria persistente (P0-3) ───────────────────────────────────────────
    # SQLite local; apagarla deja el asistente como antes (sin memoria).
    MEMORY_ENABLED: bool          = _env_bool("MEMORY_ENABLED", "true")
    MEMORY_PATH: str              = os.path.expanduser(
        os.getenv("MEMORY_PATH", "~/.limits/memory.db"))
    MEMORY_CONTEXT_BYTES: int     = int(os.getenv("MEMORY_CONTEXT_BYTES", "600"))
    MEMORY_EXPORT_PATH: str       = os.getenv("MEMORY_EXPORT_PATH", "")

    # ── Lane compuesto desktop_task (OpenCode Agent + fallback Ollama) ───────
    # Router de intents sigue en OLLAMA_MODEL (1.5b). El agent NO usa Groq.
    DESKTOP_AGENT_MAX_STEPS: int  = int(os.getenv("DESKTOP_AGENT_MAX_STEPS", "6"))
    DESKTOP_AGENT_PROVIDER: str   = os.getenv("DESKTOP_AGENT_PROVIDER", "opencode")
    DESKTOP_AGENT_FALLBACK: str   = os.getenv("DESKTOP_AGENT_FALLBACK", "nvidia")
    # Modelo Ollama SOLO para el agent (fallback o provider=ollama); no el router
    DESKTOP_AGENT_MODEL: str      = os.getenv(
        "DESKTOP_AGENT_MODEL", "qwen2.5:3b-instruct")
    OPENCODE_API_KEY: str         = os.getenv("OPENCODE_API_KEY", "")
    OPENCODE_BASE_URL: str        = os.getenv(
        "OPENCODE_BASE_URL", "https://opencode.ai/inference/openai/v1")
    OPENCODE_AGENT_MODEL: str     = os.getenv(
        "OPENCODE_AGENT_MODEL", "opencode/deepseek-v4.1-flash-free")


    # ── Búsqueda de archivos (plan focus / muéstramelo) ──────────────────────
    # Raíces separadas por ':' (default: proyectos + escritorio + descargas).
    # Vacío o "~" sola en el intent sigue usando estas raíces, no todo $HOME.
    FILE_SEARCH_ROOT: str = os.getenv(
        "FILE_SEARCH_ROOT",
        "~/Proyectos:~/Escritorio:~/Desktop:~/Descargas:~/Downloads:~/Documentos:~/Documents",
    )
    # Excludes fd/find (coma). Vacío en env = defaults del código.
    FILE_SEARCH_EXCLUDES: str = os.getenv(
        "FILE_SEARCH_EXCLUDES",
        ".git,node_modules,__pycache__,limits-env,site-packages,.venv,venv,.cache",
    )
    FILE_FOCUS_DELAY_S: float = float(os.getenv("FILE_FOCUS_DELAY_S", "0.55"))
