"""
Módulo ElevenLabs TTS — voz natural para respuestas largas.

Opt-in via .env (ver docs/plan-elevenlabs-tts.md). La cuota free es limitada
(~10k caracteres/mes): el VoiceRouter decide QUÉ se envía por API (solo lo
largo/desarrollado) y esta clase añade cache local por contenido para que las
frases repetidas cuesten 0 créditos.

CONTRATO: ante cualquier fallo (red, key, cuota, reproductor) eleva
TTSUnavailable — el router cae a Piper y el asistente jamás se queda mudo.
La API key JAMÁS se loguea.
"""

import hashlib
import subprocess
import time
from pathlib import Path

import requests
from rich.console import Console

from modules.voice_utils import clean_for_voice

console = Console()

API_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
OUTPUT_FORMAT = "mp3_44100_128"
CACHE_MAX_BYTES = 50 * 1024 * 1024  # 50 MB de audio en cache, luego evicción LRU


class TTSUnavailable(Exception):
    """ElevenLabs no disponible: el router debe usar el motor de fallback."""


class ElevenLabsEngine:
    def __init__(
        self,
        api_key: str,
        voice_id: str,
        model: str = "eleven_turbo_v2_5",
        stability: float = 0.5,
        similarity: float = 0.75,
        use_cache: bool = True,
        cache_dir: str | None = None,
        timeout: tuple[float, float] = (5.0, 30.0),
    ):
        if not api_key:
            raise ValueError("api_key vacía")
        if not voice_id:
            raise ValueError("voice_id vacío")
        self.voice_id = voice_id
        self.model = model
        self.stability = max(0.0, min(1.0, float(stability)))
        self.similarity = max(0.0, min(1.0, float(similarity)))
        self.use_cache = use_cache
        self.timeout = timeout
        self.cache_dir = Path(cache_dir) if cache_dir else (
            Path.home() / ".cache" / "limits-tts"
        )
        self._session = requests.Session()
        # La key vive solo aquí dentro; nunca en logs ni errores propagados.
        self._session.headers.update({"xi-api-key": api_key})
        if self.use_cache:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        console.print(f"[green]✓ ElevenLabs listo[/green] [dim]({model})[/dim]")

    # ──────────────────────────────────────────────────────────────────────
    # Público
    # ──────────────────────────────────────────────────────────────────────

    def speak(self, text: str) -> None:
        """Sintetiza (o toma de cache) y reproduce. Eleva TTSUnavailable si falla."""
        text = clean_for_voice(text or "")
        if not text.strip():
            return

        cached = self._cache_lookup(text) if self.use_cache else None
        if cached is not None:
            self._play(cached, est_seconds=self._est_seconds(text))
            return

        audio = self._synthesize(text)

        path: Path | None = None
        if self.use_cache:
            path = self._cache_store(text, audio)
        if path is None:
            path = self.cache_dir / f"tmp-{int(time.time() * 1000)}.mp3"
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            path.write_bytes(audio)

        try:
            self._play(path, est_seconds=self._est_seconds(text))
        finally:
            if not self.use_cache:
                path.unlink(missing_ok=True)

    # ──────────────────────────────────────────────────────────────────────
    # Internos
    # ──────────────────────────────────────────────────────────────────────

    @staticmethod
    def _est_seconds(text: str) -> float:
        """Duración hablada estimada (~13 chars/s en español) + margen."""
        return max(20.0, len(text) / 13.0 + 15.0)

    def _cache_lookup(self, text: str) -> Path | None:
        p = self._cache_path(text)
        if p.exists() and p.stat().st_size > 100:
            return p
        return None

    def _cache_path(self, text: str) -> Path:
        key = "|".join([
            self.voice_id, self.model,
            f"{self.stability:.2f}", f"{self.similarity:.2f}", text,
        ])
        return self.cache_dir / (hashlib.sha256(key.encode()).hexdigest() + ".mp3")

    def _cache_store(self, text: str, audio: bytes) -> Path | None:
        try:
            p = self._cache_path(text)
            p.write_bytes(audio)
            self._evict_if_needed()
            return p
        except OSError:
            return None

    def _evict_if_needed(self) -> None:
        total = 0
        files: list[tuple[float, Path]] = []
        for f in self.cache_dir.glob("*.mp3"):
            try:
                st = f.stat()
                files.append((st.st_mtime, f))
                total += st.st_size
            except OSError:
                continue
        if total <= CACHE_MAX_BYTES:
            return
        for _, f in sorted(files):
            if total <= CACHE_MAX_BYTES:
                break
            try:
                total -= f.stat().st_size
                f.unlink()
            except OSError:
                continue

    def _synthesize(self, text: str) -> bytes:
        payload = {
            "text": text[:4800],  # guard defensivo del límite real por request
            "model_id": self.model,
            "voice_settings": {
                "stability": self.stability,
                "similarity_boost": self.similarity,
                "style": 0.0,
                "use_speaker_boost": True,
            },
        }
        try:
            r = self._session.post(
                API_URL.format(voice_id=self.voice_id),
                json=payload,
                params={"output_format": OUTPUT_FORMAT},
                timeout=self.timeout,
            )
        except requests.RequestException as e:
            raise TTSUnavailable(f"red: {type(e).__name__}") from e

        if r.status_code == 401:
            raise TTSUnavailable(
                "key inválida o sin permiso text_to_speech")
        if r.status_code == 402:
            raise TTSUnavailable(
                "voz de biblioteca no permitida en el plan free: "
                "crea una voz propia en el Voice Lab y usa su voice_id")
        if r.status_code == 429:
            raise TTSUnavailable("cuota o rate limit agotado")
        if r.status_code == 422:
            raise TTSUnavailable("texto rechazado por la API")
        if r.status_code != 200:
            raise TTSUnavailable(f"HTTP {r.status_code}")
        if "audio" not in r.headers.get("content-type", ""):
            raise TTSUnavailable("respuesta sin audio")
        return r.content

    def _play(self, path: Path, est_seconds: float) -> None:
        players = [
            ["mpv", "--no-video", "--terminal=no", "--really-quiet"],
            ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet"],
        ]
        for cmd in players:
            try:
                subprocess.run(
                    cmd + [str(path)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=est_seconds,
                    check=False,
                )
                return
            except FileNotFoundError:
                continue
            except subprocess.TimeoutExpired:
                console.print("[yellow]Reproducción de audio excedió el timeout.[/yellow]")
                return
        raise TTSUnavailable("sin reproductor mpv/ffplay disponible")
