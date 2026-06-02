import os
from dotenv import load_dotenv

load_dotenv()

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
