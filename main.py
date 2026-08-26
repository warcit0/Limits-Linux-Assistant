"""
Limits LINUX — Punto de entrada principal
Orquesta todos los módulos: STT → LLM → Executor → TTS

Uso:
    python main.py              # Modo normal (siempre escuchando con wake word)
    python main.py --text       # Modo texto (sin micrófono, para testing)
    python main.py --once       # Ejecuta un solo comando y sale
"""

import os
import sys
import signal
import logging
import argparse
from pathlib import Path
from rich.console import Console
from rich.panel import Panel

from config import Config
from modules.llm import LLMEngine
from modules.executor import CommandExecutor
from modules.tts import TTSEngine, VoiceRouter
from modules.tts_elevenlabs import ElevenLabsEngine
from modules.gateway import RemoteBusy, TurnGate
from version import __version__, STATUS

console = Console()

# ── Logging a archivo ─────────────────────────────────────────────────────────
Path("logs").mkdir(exist_ok=True)
logging.basicConfig(
    filename="logs/limits.log",
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("limits")


# ── Señales del sistema ───────────────────────────────────────────────────────
_shutdown_requested = False

def _handle_sigterm(signum, frame):
    """Manejo de SIGTERM para shutdown graceful (e.g. systemd stop)."""
    global _shutdown_requested
    _shutdown_requested = True
    console.print("\n[yellow]SIGTERM recibido. Cerrando Limits...[/yellow]")

signal.signal(signal.SIGTERM, _handle_sigterm)


# ── Funciones principales ─────────────────────────────────────────────────────

def print_banner(config: Config):
    eleven_on = (
        config.ELEVENLABS_ENABLED
        and config.ELEVENLABS_API_KEY
        and config.ELEVENLABS_VOICE_ID
        and config.ELEVENLABS_MODE != "off"
    )
    voz = f"piper + ElevenLabs({config.ELEVENLABS_MODE})" if eleven_on else "piper"
    llm_label = (f"{config.OLLAMA_MODEL} (local)" if config.LLM_PRIORITY == "local"
                 else f"Groq {config.GROQ_MODEL.split('/')[-1]}")
    console.print(Panel.fit(
        f"[bold cyan]🤖 Limits LINUX[/bold cyan] [dim]{__version__} ({STATUS})[/dim]\n"
        f"[dim]LLM: {llm_label}[/dim]\n"
        f"[dim]STT: Whisper {config.WHISPER_MODEL} | TTS: {voz}[/dim]\n"
        f"[dim]Wake word: '{config.WAKE_WORD}' — Di 'salir' para terminar[/dim]",
        border_style="cyan",
    ))


def make_pipeline(llm: LLMEngine, executor: CommandExecutor,
                  tts, gate: TurnGate, gemini=None):
    """Pipeline compartido por voz local y gateway móvil.

    El TurnGate serializa turnos: nunca se intercalan respuestas de voz ni
    historial del LLM. wait_timeout=None espera indefinido (voz local);
    el gateway pasa un timeout y recibe RemoteBusy si no hay turno libre.

    Router por palabras clave (decisión 2026-08-25): "investiga/infórmame/
    busca en internet…" van DIRECTO a Gemini sin pasar por el LLM de intents.
    """
    def pipeline(user_input: str, wait_timeout: float | None = None,
                 speak: bool = True) -> str:
        if not gate.acquire(wait_timeout):
            raise RemoteBusy()
        try:
            # ── Ruta conversacional determinista ─────────────────────────────
            if gemini is not None:
                from modules.gemini import match_gemini_route
                route = match_gemini_route(user_input)
                if route:
                    mode = route[0]
                    log.info("turno gemini (%s) vía palabra clave", mode)
                    log.debug(f"INPUT(gemini): {user_input}")
                    response_text = gemini.chat(
                        user_input, research=(mode == "research"))
                    log.info(f"turno gemini completado | chars={len(response_text)}")
                    log.debug(f"RESPONSE(gemini): {response_text}")
                    if speak:
                        tts.speak(response_text)
                    return response_text

            # ── Ruta operativa (LLM router → executor) ───────────────────────
            log.debug(f"INPUT: {user_input}")
            parsed = llm.process(user_input)
            response_text = executor.execute(parsed)
            log.info(f"turno procesado | intent={parsed.get('intent')} "
                     f"confidence={parsed.get('confidence', 0):.2f}")
            log.debug(f"RESPONSE: {response_text}")
            if speak:
                tts.speak(response_text)
            return response_text
        finally:
            gate.release()
    return pipeline


def main():
    parser = argparse.ArgumentParser(description="Limits Linux — Asistente de voz")
    parser.add_argument("--text", action="store_true", help="Modo texto (sin micrófono, ideal para testing)")
    parser.add_argument("--once", action="store_true", help="Ejecutar un solo comando y salir")
    args = parser.parse_args()

    config = Config()
    print_banner(config)
    log.info("Limits iniciado.")

    console.print("\n[bold]Iniciando módulos...[/bold]")
    llm      = LLMEngine(config)
    executor = CommandExecutor()

    # ── Voz dual: Piper (corto/sistema) + ElevenLabs (largo/natural, opt-in) ──
    piper = TTSEngine(
        voice_model=config.PIPER_VOICE_MODEL,
        voice_speed=config.VOICE_SPEED,
        speaker=config.VOICE_SPEAKER
    )
    eleven = None
    if (config.ELEVENLABS_ENABLED
            and config.ELEVENLABS_API_KEY
            and config.ELEVENLABS_VOICE_ID
            and config.ELEVENLABS_MODE != "off"):
        try:
            eleven = ElevenLabsEngine(
                api_key=config.ELEVENLABS_API_KEY,
                voice_id=config.ELEVENLABS_VOICE_ID,
                model=config.ELEVENLABS_MODEL,
                stability=config.ELEVENLABS_STABILITY,
                similarity=config.ELEVENLABS_SIMILARITY,
                use_cache=config.ELEVENLABS_CACHE,
            )
        except Exception as e:
            console.print(f"[yellow]ElevenLabs desactivado: {e}[/yellow]")
    elif config.ELEVENLABS_ENABLED:
        console.print("[dim]ELEVENLABS_ENABLED sin key/voice_id válidos — "
                      "solo Piper.[/dim]")

    tts = VoiceRouter(
        piper=piper,
        eleven=eleven,
        mode=config.ELEVENLABS_MODE if eleven else "off",
        min_chars=config.ELEVENLABS_MIN_CHARS,
        max_turn_chars=config.ELEVENLABS_MAX_TURN_CHARS,
    )

    stt = None
    if not args.text:
        from modules.stt import STTEngine
        stt = STTEngine(
            model_size=config.WHISPER_MODEL,
            language=config.LANGUAGE,
            device=config.STT_DEVICE,
        )

    # ── Pipeline compartido (voz local + gateway móvil) ──────────────────────
    gate = TurnGate()

    # ── Cerebro conversacional Gemini (opt-in; salida solo a voz) ───────────
    gemini_bridge = None
    if config.GEMINI_ENABLED:
        from modules.gemini import GeminiBridge
        candidato = GeminiBridge(
            gemini_bin=os.path.expanduser(config.GEMINI_BIN),
            timeout_s=config.GEMINI_TIMEOUT,
            session_file=(os.path.expanduser(config.GEMINI_SESSION)
                          if config.GEMINI_SESSION else None),
        )
        if candidato.available():
            gemini_bridge = candidato
            executor.gemini = gemini_bridge
            console.print(f"[green]✓ Cerebro conversacional Gemini listo[/green] "
                          f"[dim](investiga/infórmame/… o gemini_talk)[/dim]")
        else:
            console.print(f"[yellow]GEMINI_BIN no encontrado: "
                          f"{config.GEMINI_BIN} — cerebro desactivado[/yellow]")

    pipeline = make_pipeline(llm, executor, tts, gate, gemini=gemini_bridge)

    # ── Gateway móvil: el texto remoto entra al MISMO pipeline (opt-in) ─────
    gateway = None
    if config.GATEWAY_ENABLED:
        from modules.gateway import GatewayServer
        try:
            gateway = GatewayServer(
                pipeline=pipeline,
                host=config.GATEWAY_HOST,
                port=config.GATEWAY_PORT,
                mdns_name=config.GATEWAY_MDNS_NAME,
                token_path=config.GATEWAY_TOKEN_PATH or None,
                app_version=__version__,
                speak_remote=config.GATEWAY_SPEAK_LOCAL,
            )
            gw_info = gateway.start()
            console.print(f"[green]✓ Gateway móvil:[/green] "
                          f"ws://{gw_info['ip']}:{gw_info['port']}/ws "
                          f"[dim](token: {config.GATEWAY_TOKEN_PATH or '~/.limits/gateway_token'})[/dim]")
            # Los archivos locales a castear salen por URLs firmadas del gateway
            executor.tv.media_url_factory = gateway.make_media_url
        except OSError as e:
            console.print(f"[yellow]Gateway no iniciado ({e}); "
                          f"¿otra instancia ya usa el puerto {config.GATEWAY_PORT}?[/yellow]")
            gateway = None

    console.print("\n[bold green]✓ Limits listo.[/bold green]\n")
    tts.speak("Limits listo. ¿En qué te puedo ayudar?")

    global _shutdown_requested

    try:
        while not _shutdown_requested:
            if args.text:
                # ── Modo texto ─────────────────────────────────────────────
                try:
                    user_input = input("\n[Tú]: ").strip()
                except EOFError:
                    break

                if not user_input:
                    continue
                if user_input.lower() in ("salir", "exit", "quit"):
                    break

            else:
                # ── Modo voz ───────────────────────────────────────────────
                user_input = stt.listen_and_transcribe()

                if not user_input:
                    continue

                # Filtrar por wake word si está configurada
                if config.WAKE_WORD:
                    wake_words = [w.strip().lower() for w in config.WAKE_WORD.split(",")]
                    # Añadir variaciones comunes si la palabra es "limits"
                    if "limits" in wake_words:
                        wake_words.extend(["límites", "limites"])
                    
                    found_wake = None
                    user_input_lower = user_input.lower()
                    for w in wake_words:
                        if w in user_input_lower:
                            found_wake = w
                            break
                    
                    if not found_wake:
                        # Feedback visible: sin esto, descartar en silencio
                        # parece "no responde"
                        console.print(f"[dim](sin wake word '{config.WAKE_WORD}' "
                                      f"— ignorado)[/dim]")
                        continue

                    # Extraer comando (remover la wake word y limpiar puntuación)
                    user_input = user_input_lower.replace(found_wake, "", 1).strip()
                    user_input = user_input.lstrip(" ,.¿?¡!").strip()

                if not user_input:
                    tts.speak("¿Sí?")
                    user_input = stt.listen_and_transcribe()

                # Salida por voz
                if user_input and user_input.lower() in ("salir", "exit", "apagarte"):
                    break

            if user_input:
                pipeline(user_input)

            if args.once:
                break

    except KeyboardInterrupt:
        console.print("\n[yellow]Interrumpido por el usuario.[/yellow]")
    finally:
        if gateway:
            gateway.stop()
        tts.speak("Hasta luego.")
        log.info("Limits apagado.")
        if stt:
            stt.cleanup()


if __name__ == "__main__":
    main()
