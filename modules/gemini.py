"""
GeminiBridge — cerebro conversacional vía el CLI gemdev.

Implementa la Fase F1 de docs/integracion-gemini.md (contrato verificado
empíricamente contra gemdev 0.2.x, NO contra su documentación):

    $GEMINI_BIN chat -t N --json [-c SESSION] "prompt"
      → stdout: líneas "[gemdev] ..." + ÚLTIMA línea JSON {ok, url, f, elapsed}
      → texto de respuesta: contenido del archivo apuntado por "f"
      → error: {"ok":false,"err":CODIGO,"msg":...} y exit 1

REGLA DURA (AGENTS.md): la salida va SOLO a TTS/log; jamás alimenta al
executor ni se interpreta como comando.
"""

import json
import logging
import subprocess
from pathlib import Path

from modules.voice_utils import clean_for_voice

log = logging.getLogger("limits.gemini")

PREAMBLE = (
    "Eres Limits, la IA personal de escritorio de warcito (CachyOS + Hyprland), "
    "con tono cercano tipo Jarvis. Responde SIEMPRE en español hablado y natural, "
    "como si lo fueras a decir en voz alta: frases cortas, sin markdown, sin "
    "listas, sin emojis, sin URLs crudas (describe los enlaces con palabras). "
    "Máximo ~120 palabras salvo que te pidan detalle o investigación. Cuando "
    "investigues, contrasta fuentes y menciónalas verbalmente ('según Reuters…')."
)

RESEARCH_MARK = (
    "[MODO INVESTIGACIÓN: usa tu búsqueda de Google, contrasta al menos dos "
    "fuentes y di de dónde sacaste cada dato]\n"
)

# ── Router determinista por palabras clave (decisión del usuario 2026-08-25) ──
# Investigación: verbos explícitos o formas compuestas ("busca" sola NO cuenta:
# "busca el archivo config.py" es búsqueda local).
_RESEARCH_KEYWORDS = (
    "investiga", "infórmame", "informame", "infórmate", "informate",
    "googlea", "googlear",
    "busca en internet", "búscame en internet", "buscame en internet",
    "busca en la web", "búscame en la web", "busca online",
    "qué hay de nuevo", "que hay de nuevo", "novedades sobre",
    "noticias de", "noticias sobre", "qué se sabe de", "que se sabe de",
)
_TALK_PREFIXES = ("gemini", "gémini")
_TALK_CONTAINS = ("pregúntale a gemini", "preguntale a gemini",
                  "pídele a gemini", "pidele a gemini")


def match_gemini_route(text: str) -> tuple[str, str] | None:
    """Devuelve ('research'|'talk', texto) si las palabras clave aplican.

    El texto viaja VERBATIM (sin recortar la palabra clave): Gemini entiende
    lenguaje natural mejor que un recorte regex.
    """
    low = (text or "").strip().lower()
    if not low:
        return None

    if any(low.startswith(p) for p in _TALK_PREFIXES):
        return ("talk", text)
    if any(k in low for k in _TALK_CONTAINS):
        return ("talk", text)

    if any(k in low for k in _RESEARCH_KEYWORDS):
        return ("research", text)

    return None


class GeminiBridge:
    def __init__(self, gemini_bin: str, timeout_s: int = 120,
                 session_file: str | None = None,
                 max_voice_chars: int = 900,
                 preamble: str = PREAMBLE):
        self.bin = gemini_bin
        self.timeout_s = max(30, int(timeout_s))
        self.session_file = session_file
        self.max_voice_chars = max_voice_chars
        self.preamble = preamble

    def available(self) -> bool:
        p = Path(self.bin).expanduser()
        return p.exists()

    # ──────────────────────────────────────────────────────────────────────

    def chat(self, query: str, research: bool = False) -> str:
        """Un turno contra Gemini Web. Devuelve TEXTO PARA VOZ (limpio).

        Nunca lanza: cualquier fallo devuelve una frase hablada amable."""
        body = (RESEARCH_MARK + query.strip()) if research else query.strip()
        full_prompt = f"{self.preamble}\n\n{body}"

        cmd = [
            self.bin, "chat",
            "-t", str(self.timeout_s),   # siempre explícito: bug upstream si falta
            "--json",
        ]
        if self.session_file:
            cmd += ["-c", str(Path(self.session_file).expanduser())]
        cmd.append(full_prompt)

        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True,
                timeout=self.timeout_s + 45,
            )
        except subprocess.TimeoutExpired:
            return "Gemini tardó demasiado en responder."
        except OSError as e:
            log.error("no se pudo ejecutar %s: %s", self.bin, e)
            return "No encuentro el comando de Gemini en el sistema."

        result = self._parse_pointer(proc.stdout)
        if result is None:
            log.error("salida no parseable (rc=%s): %r",
                      proc.returncode, (proc.stdout or "")[-200:])
            return "Gemini respondió algo inesperado. Inténtalo de nuevo."

        if not result.get("ok"):
            return self._friendly_error(str(result.get("err", "")),
                                        str(result.get("msg", "")))

        artifact = result.get("f")
        if not artifact:
            return "Gemini respondió sin contenido."

        try:
            text = Path(artifact).read_text(encoding="utf-8").strip()
        except OSError as e:
            log.error("artefacto ilegible %s: %s", artifact, e)
            return "Recibí la respuesta pero no pude leerla."

        if not text:
            return "Gemini me devolvió una respuesta vacía."

        cleaned = clean_for_voice(text)
        if len(cleaned) > self.max_voice_chars:
            cut = cleaned.rfind(". ", 0, self.max_voice_chars)
            cut = cut + 1 if cut > 200 else self.max_voice_chars
            cleaned = cleaned[:cut].strip() + "... Si quieres, profundizo más."
        return cleaned

    # ── internos ────────────────────────────────────────────────────────────

    @staticmethod
    def _parse_pointer(stdout: str) -> dict | None:
        """Última línea JSON válida del stdout (ignora líneas [gemdev])."""
        for line in reversed((stdout or "").splitlines()):
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                data = json.loads(line)
                if isinstance(data, dict):
                    return data
            except json.JSONDecodeError:
                continue
        return None

    @staticmethod
    def _friendly_error(err: str, msg: str) -> str:
        table = {
            "LOCKED": "Estoy ocupado consultando otra cosa. Repite en unos segundos.",
            "NOT_SIGNED_IN": "Mi sesión de Gemini caducó. Ejecuta 'gemdev login' cuando puedas.",
            "EMPTY": "Gemini me devolvió una respuesta vacía.",
            "TRANSIENT_TIMEOUT": "Gemini tardó demasiado. Inténtalo otra vez.",
            "NO_INPUT": "No encontré la caja de texto de Gemini.",
        }
        log.warning("gemdev error %s: %s", err, msg)
        return table.get(err.upper(), "Gemini falló: " + (msg[:80] or err))
