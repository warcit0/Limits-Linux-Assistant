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

from __future__ import annotations

import json
import logging
import re
import subprocess
import unicodedata
from pathlib import Path

from modules.voice_utils import clean_for_voice

log = logging.getLogger("limits.gemini")

PREAMBLE = (
    "Eres Limits, la IA personal de escritorio de warcito (CachyOS + Hyprland), "
    "con tono cercano tipo Jarvis. Responde SIEMPRE en español hablado y natural, "
    "como si lo fueras a decir en voz alta: frases cortas, sin markdown, sin "
    "listas, sin emojis, sin URLs crudas (describe los enlaces con palabras). "
    "Para charla normal: máximo ~120 palabras. "
    "Si el mensaje lleva MODO INVESTIGACIÓN, IGNORA ese tope y da un resumen "
    "hablado sustancial con hechos concretos."
)

RESEARCH_MARK = (
    "[MODO INVESTIGACIÓN — OBLIGATORIO]\n"
    "Usa búsqueda web. Contrasta al menos dos fuentes y menciónalas en voz "
    "('según Reuters', 'según la BBC'). "
    "Responde con un resumen hablado de AL MENOS 120 palabras con hechos "
    "concretos (fechas, nombres, cifras). "
    "PROHIBIDO responder solo con un saludo o apertura vacía tipo "
    "'te comento la situación' sin datos. "
    "Si no hay información fiable, dilo explícitamente y explica qué buscaste.\n"
)

# Aperturas huecas: si research solo contiene esto (o casi), fallar en voz alta
_HOLLOW_OPENERS = (
    "te comento la situación",
    "te cuento la situación",
    "déjame pensarlo",
    "déjame investigar",
    "claro, warcito",
    "por supuesto, warcito",
)

# ── Router determinista por palabras clave ───────────────────────────────────
# Se comparan RAÍCES sobre texto sin acentos: así "investígame", "investigame",
# "investiga" e "investigación" caen todas en el mismo sitio. Bug real: la app
# respondía con web_search porque "investígame" (con tilde) no coincidía con
# "investiga".
_RESEARCH_KEYWORDS = (
    "investig", "averigu", "indag",          # investiga/investígame/investigación
    "googlea", "googlear",
    "informame", "informate",                # infórmame/infórmate
    "busca en internet", "buscame en internet",
    "busca en la web", "buscame en la web", "busca online",
    "busca informacion", "buscame informacion",
    "que hay de nuevo", "novedades", "noticias de", "noticias sobre",
    "que se sabe de",
)
_TALK_PREFIXES = ("gemini", "gémini")
_TALK_CONTAINS = ("pregúntale a gemini", "preguntale a gemini",
                  "pídele a gemini", "pidele a gemini")


def _norm(text: str) -> str:
    """minúsculas y sin diacríticos (para comparar raíces de forma estable)."""
    descompuesto = unicodedata.normalize("NFD", (text or "").lower())
    return "".join(c for c in descompuesto if not unicodedata.combining(c))


_RESEARCH_KEYWORDS_N = tuple(_norm(k) for k in _RESEARCH_KEYWORDS)
_TALK_PREFIXES_N = tuple(_norm(p) for p in _TALK_PREFIXES)
_TALK_CONTAINS_N = tuple(_norm(p) for p in _TALK_CONTAINS)



def match_gemini_route(text: str) -> tuple[str, str] | None:
    """Devuelve ('research'|'talk', texto) si las palabras clave aplican."""
    low = _norm(text)
    if not low.strip():
        return None

    if any(low.startswith(p) for p in _TALK_PREFIXES_N):
        return ("talk", text)
    if any(k in low for k in _TALK_CONTAINS_N):
        return ("talk", text)

    if any(k in low for k in _RESEARCH_KEYWORDS_N):
        return ("research", text)

    return None


def _is_hollow_research(text: str, min_chars: int) -> bool:
    """True si la respuesta de research no aporta sustancia."""
    t = (text or "").strip()
    if len(t) < min_chars:
        return True
    low = t.lower()
    # Solo opener + poco más
    for opener in _HOLLOW_OPENERS:
        if low.startswith(opener) and len(t) < min_chars + 40:
            return True
        if low == opener or low.rstrip(".!, ") == opener:
            return True
    # Casi sin dígitos ni nombres propios largos y muy corta → sospechoso
    words = re.findall(r"\w+", t, flags=re.UNICODE)
    if len(words) < 25 and len(t) < min_chars:
        return True
    return False


class GeminiBridge:
    def __init__(self, gemini_bin: str, timeout_s: int = 120,
                 session_file: str | None = None,
                 max_voice_chars: int = 900,
                 preamble: str = PREAMBLE,
                 min_research_chars: int = 200,
                 min_talk_chars: int = 8):
        self.bin = gemini_bin
        self.timeout_s = max(30, int(timeout_s))
        self.session_file = session_file
        self.max_voice_chars = max_voice_chars
        self.preamble = preamble
        self.min_research_chars = max(50, int(min_research_chars))
        self.min_talk_chars = max(1, int(min_talk_chars))

    def available(self) -> bool:
        p = Path(self.bin).expanduser()
        return p.exists()

    # ──────────────────────────────────────────────────────────────────────

    def chat(self, query: str, research: bool = False) -> str:
        """Un turno contra Gemini Web. Devuelve TEXTO PARA VOZ (limpio).

        Nunca lanza: cualquier fallo / respuesta hueca → frase hablada explícita.
        """
        body = (RESEARCH_MARK + query.strip()) if research else query.strip()
        full_prompt = f"{self.preamble}\n\n{body}"
        mode = "research" if research else "talk"

        cmd = [
            self.bin, "chat",
            "-t", str(self.timeout_s),
            "--json",
        ]
        if self.session_file:
            cmd += ["-c", str(Path(self.session_file).expanduser())]
        cmd.append(full_prompt)

        log.info("gemini %s start timeout=%ss", mode, self.timeout_s)
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True,
                timeout=self.timeout_s + 45,
            )
        except subprocess.TimeoutExpired:
            log.error("gemini %s TimeoutExpired", mode)
            return "Gemini tardó demasiado en responder."
        except OSError as e:
            log.error("no se pudo ejecutar %s: %s", self.bin, e)
            return "No encuentro el comando de Gemini en el sistema."

        stderr_raw = proc.stderr if isinstance(proc.stderr, str) else ""
        stdout_raw = proc.stdout if isinstance(proc.stdout, str) else ""
        stderr_tail = stderr_raw[-300:]
        stdout_tail = stdout_raw[-400:]
        log.debug("gemini rc=%s stderr_tail=%r stdout_tail=%r",
                  proc.returncode, stderr_tail, stdout_tail)

        result = self._parse_pointer(proc.stdout)
        if result is None:
            log.error("gemini %s salida no parseable rc=%s stdout_tail=%r "
                      "stderr_tail=%r",
                      mode, proc.returncode, stdout_tail, stderr_tail)
            return "Gemini respondió algo inesperado. Inténtalo de nuevo."

        ok = bool(result.get("ok"))
        err = str(result.get("err", "") or "")
        msg = str(result.get("msg", "") or "")
        artifact = result.get("f")
        log.info("gemini %s pointer ok=%s err=%s f=%s elapsed=%s",
                 mode, ok, err or "-", artifact or "-",
                 result.get("elapsed"))

        if not ok:
            return self._friendly_error(err, msg)

        if not artifact:
            log.warning("gemini %s ok sin artefacto f", mode)
            return "Gemini respondió sin contenido."

        try:
            text = Path(artifact).read_text(encoding="utf-8").strip()
        except OSError as e:
            log.error("artefacto ilegible %s: %s", artifact, e)
            return "Recibí la respuesta pero no pude leerla."

        preview = text[:200].replace("\n", " ")
        log.info("gemini %s artifact chars=%s preview=%r",
                 mode, len(text), preview)

        if not text:
            return "Gemini me devolvió una respuesta vacía."

        cleaned = clean_for_voice(text)
        log.debug("gemini %s cleaned chars=%s", mode, len(cleaned))

        if research and _is_hollow_research(cleaned, self.min_research_chars):
            log.warning("gemini research hueca/corta chars=%s preview=%r",
                        len(cleaned), cleaned[:120])
            return (
                "No pude investigar ahora: la respuesta de Gemini vino vacía "
                "o incompleta. Prueba 'gemdev login' si caducó la sesión, "
                "o repite en unos segundos."
            )

        if not research and len(cleaned) < self.min_talk_chars:
            log.warning("gemini talk demasiado corta chars=%s", len(cleaned))
            return "Gemini me devolvió casi nada. Inténtalo de nuevo."

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
            "NOT_SIGNED_IN": (
                "No pude investigar ahora: la sesión de Gemini no está "
                "autenticada. Ejecuta 'gemdev login' e inicia sesión."
            ),
            "EMPTY": "No pude investigar ahora: Gemini devolvió una respuesta vacía.",
            "TRANSIENT_TIMEOUT": "Gemini tardó demasiado. Inténtalo otra vez.",
            "NO_INPUT": "No encontré la caja de texto de Gemini.",
        }
        log.warning("gemdev error %s: %s", err, msg)
        key = (err or "").upper()
        if key in table:
            return table[key]
        return "No pude consultar a Gemini: " + (msg[:80] or err or "error desconocido")
