import os
from dotenv import load_dotenv

load_dotenv()


def _env_bool(name: str, default: str = "false") -> bool:
    v = os.getenv(name, default).strip().lower()
    return v in ("1", "true", "yes", "si", "sí")


class Config:
    OLLAMA_URL: str        = os.getenv("OLLAMA_URL", "http://localhost:11434")
    OLLAMA_MODEL: str      = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:7b")
    GROQ_API_KEY: str      = os.getenv("GROQ_API_KEY", "")
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
