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
import re
import time
import threading
import uuid
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
Path(Config.LOG_PATH).parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    filename=Config.LOG_PATH,
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
    llm_label = f"{config.OLLAMA_MODEL} (local)"
    if getattr(config,'AGENT_MODE','legacy') == 'conversacional':
        llm_label = f"asistente cotidiano {config.AGENT_CONVERSATION_MODEL} (local)"
    console.print(Panel.fit(
        f"[bold cyan]🤖 Limits LINUX[/bold cyan] [dim]{__version__} ({STATUS})[/dim]\n"
        f"[dim]LLM: {llm_label}[/dim]\n"
        f"[dim]STT: Whisper {config.WHISPER_MODEL} | TTS: {voz}[/dim]\n"
        f"[dim]Wake word: '{config.WAKE_WORD}' — Di 'salir' para terminar[/dim]",
        border_style="cyan",
    ))


def make_pipeline(llm: LLMEngine, executor: CommandExecutor,
                  tts, gate: TurnGate, gemini=None, orchestrator=None):
    """Pipeline compartido por voz local y gateway móvil.

    El TurnGate serializa turnos: nunca se intercalan respuestas de voz ni
    historial del LLM. wait_timeout=None espera indefinido (voz local);
    el gateway pasa un timeout y recibe RemoteBusy si no hay turno libre.
    on_response(texto) se ejecuta bajo el mismo bloqueo antes de liberarlo.

    Router por palabras clave (decisión 2026-08-25): "investiga/infórmame/
    busca en internet…" van DIRECTO a Gemini sin pasar por el LLM de intents.
    """
    historiales_ordenes = {}

    def pipeline(user_input: str, wait_timeout: float | None = None,
                 speak: bool = True, on_response=None, session_id="local",
                 turn_generation=None, on_progress=None, progress_voice=None) -> str:
        if orchestrator is not None and turn_generation is None:
            turn_generation = orchestrator.generacion(session_id)
        if not gate.acquire(wait_timeout):
            raise RemoteBusy()
        from modules.presence import obtener as presencia_actual
        presencia = presencia_actual()
        detenido_visual = threading.Event()

        def detener_visual():
            detenido_visual.set()
            if orchestrator is not None:
                orchestrator.cancelar(session_id)
            executor.cancel_pending()
            voz = progress_voice if progress_voice is not None else tts
            if callable(getattr(voz, "stop", None)):
                voz.stop()

        turno_visual = presencia.comenzar(detener_visual) if presencia else None
        final_visual = "oculto"

        def ejecutar_visual(parsed):
            if detenido_visual.is_set():
                return "Tarea cancelada."
            from modules.presence import actividad
            with actividad("ejecutando"):
                resultado = executor.execute(parsed)
            if isinstance(resultado, str):
                import re
                from modules.command_result import ResultadoComando
                accion = parsed.get("action")
                if not isinstance(resultado, ResultadoComando):
                    from modules.command_result import normalizar_resultado
                    from modules.task_tools import LECTURAS
                    recibo = normalizar_resultado(resultado,lectura=accion in LECTURAS)
                    resultado = ResultadoComando(resultado,ok=recibo['ok'] if recibo['verificado'] or not recibo['ok'] else None,
                                                 verificado=recibo['verificado'])
                resultado.acciones = [{"accion":accion,"ok":resultado.ok,"verificado":resultado.verificado}]
            return resultado

        escucha_activa = False
        flujo = None
        frases = None
        flujo_cerrado = False
        inicio_turno = time.monotonic()
        turno_id = uuid.uuid4().hex
        primer_texto = False
        aviso_espera = None
        fin_aviso = threading.Event()
        bloqueo_progreso = threading.RLock()

        def progreso(evento):
            with bloqueo_progreso:
                if evento.get('type') == 'espera' and fin_aviso.is_set():
                    return
                _progreso(evento)

        def _progreso(evento):
            nonlocal flujo, frases, primer_texto
            if presencia and evento.get("type") == "status":
                presencia.fase("investigando")
            from modules.streaming import FlujoVoz, FrasesProgresivas
            vigente = lambda: turn_generation == orchestrator.generacion(session_id)
            if not vigente():
                return
            if on_progress:
                on_progress(evento)
            if evento.get("type") == "delta" and not primer_texto:
                primer_texto = True
                log.info("turno=%s primer_texto_s=%.3f", turno_id, time.monotonic()-inicio_turno)
            if evento.get("type") == "final":
                log.info("turno=%s fin_gemini_s=%.3f", turno_id, time.monotonic()-inicio_turno)
            voz = progress_voice if progress_voice is not None else tts if speak else None
            if flujo is None and evento.get("type") in {"status", "delta", "espera"} and getattr(type(voz), "_listen", None) is not None:
                terminar_escucha()
                flujo = FlujoVoz(voz, lambda: orchestrator.cancelar(session_id), vigente)
                frases = FrasesProgresivas(flujo.decir)
                if on_progress:
                    on_progress({"type":"audio","state":"started"})
                flujo.decir("Estoy con ello." if evento.get("type") == "espera" else "Voy investigando. Te contaré avances provisionales mientras contrasto las fuentes.", tipo="estado")
                log.info("turno=%s primer_estado_s=%.3f", turno_id, time.monotonic() - inicio_turno)
            if flujo is not None and frases is None:
                frases = FrasesProgresivas(flujo.decir)
            if flujo is not None and evento.get("type") == "delta":
                frases.recibir(evento.get("text", ""))
                if frases.revisado:
                    flujo.descartar_pendientes()

        def terminar_escucha():
            nonlocal escucha_activa
            if escucha_activa:
                tts.finalizar_espera()
                escucha_activa = False

        def cerrar_aviso():
            fin_aviso.set()
            if aviso_espera is not None:
                aviso_espera.cancel()
                aviso_espera.join()

        def entregar(texto: str) -> str:
            nonlocal response_text, flujo_cerrado, final_visual
            if detenido_visual.is_set():
                from modules.task_state import RespuestaTurno
                texto = RespuestaTurno("Tarea cancelada.")
                texto.cancelada = True
            cerrar_aviso()
            pendiente_visual = getattr(executor, "_pending_action", None)
            if presencia and orchestrator is not None:
                tarea_visual = orchestrator.almacen.cargar(session_id)
                pendiente_visual = pendiente_visual or (tarea_visual and tarea_visual.estado == "aprobacion")
            final_visual = "confirmacion" if pendiente_visual else "interrumpido" if getattr(texto, "cancelada", False) else "error" if getattr(texto, "ok", None) is False else "oculto"
            terminar_escucha()
            if orchestrator is not None and turn_generation != orchestrator.generacion(session_id):
                from modules.task_state import RespuestaTurno
                texto = RespuestaTurno("Tarea cancelada.")
                texto.cancelada = True
                response_text = texto
            response_text = texto
            if flujo is not None:
                # Reservar la voz para el flujo antes de entregar el texto al
                # gateway: así el callback no inicia otro reproductor.
                texto.audio_entregado = True
                if on_response is not None:
                    on_response(texto)
                try:
                    if not getattr(texto, "cancelada", False):
                        frases.recibir(getattr(texto, "completo", str(texto)), final=True)
                        if frases.revisado:
                            flujo.descartar_pendientes()
                            flujo.decir("La respuesta final corrige o no confirma el avance anterior.")
                            from modules.voice_utils import clean_for_voice
                            flujo.decir(clean_for_voice(getattr(texto, "completo", str(texto))))
                    flujo.cerrar()
                    flujo_cerrado = True
                    texto.audio_metricas = flujo.metricas
                finally:
                    if on_progress:
                        on_progress({"type":"audio","state":"finished"})
            elif on_response is not None:
                # El callback reproduce dentro del mismo bloqueo de turno.
                on_response(texto)
            if speak and not getattr(texto, "cancelada", False) and not getattr(texto, "audio_entregado", False):
                if hasattr(texto, "source"):
                    resultado_voz = tts.speak(texto, source=texto.source,
                                             cancel_event=getattr(texto, "cancel_event", None))
                else:
                    resultado_voz = tts.speak(texto)
                if resultado_voz == "interrupted":
                    final_visual = "interrumpido"
                    executor.cancel_pending()
                    if orchestrator is not None:
                        orchestrator.cancelar(session_id)
            return texto

        response_text = ""
        intent = None
        try:
            if orchestrator is not None and turn_generation != orchestrator.generacion(session_id):
                return entregar("Tarea cancelada.")
            from modules.workspace_router import match_workspace_route
            from modules.orchestrator import ruta_rapida_admisible
            workspace = match_workspace_route(user_input) if ruta_rapida_admisible(user_input) else None
            if workspace and not (orchestrator is not None and getattr(orchestrator.config,"AGENT_MODE","legacy") in {"local","conversacional"}):
                if orchestrator is not None:
                    orchestrator.invalidar(session_id)
                executor.cancel_pending()
                response_text = ejecutar_visual(workspace)
                intent = "workspace"
                return entregar(response_text)
            if orchestrator is not None:
                if turn_generation != orchestrator.generacion(session_id):
                    from modules.task_state import RespuestaTurno
                    response_text = RespuestaTurno("Tarea cancelada.")
                    response_text.cancelada = True
                    return entregar(response_text)
                orchestrator.entrar_sesion(session_id)
                # Referente efímero por sesión: destino elegido por el usuario, no estado del player.
                if not hasattr(orchestrator, '_reproductores_sesion'):
                    orchestrator._reproductores_sesion = {}
                from modules.grounding import fold
                texto_media = fold(user_input)
                menciones = re.findall(r'\b(spotify|firefox|vlc|mpv)\b', texto_media)
                control_media = re.search(r'\b(musica|cancion|tema|reproduccion|reproduce\w*|pausa\w*|reanuda\w*|siguiente|anterior|play|stop)\b', texto_media)
                cierre_app = re.search(r'\b(cierra\w*|cerrar|termina\w*)\b', texto_media)
                if len(set(menciones)) == 1 and not cierre_app and (control_media or menciones[0] in {'spotify','vlc','mpv'}) and not re.search(r'\b(no|nunca|sin)\b', texto_media):
                    orchestrator._reproductores_sesion[session_id] = (menciones[0], time.monotonic(), turn_generation)
                elif cierre_app:
                    previo_media = orchestrator._reproductores_sesion.get(session_id)
                    if previo_media and previo_media[0] in menciones:
                        orchestrator._reproductores_sesion.pop(session_id, None)
                orchestrator._reproductores_sesion = {k:v for k,v in orchestrator._reproductores_sesion.items() if time.monotonic()-v[1] < 300}
                referente = orchestrator._reproductores_sesion.get(session_id)
                reproductor = referente[0] if referente and time.monotonic()-referente[1] < 300 and referente[2] == turn_generation else None

                # En local, atajos y Qwen comparten compilación, ejecutor y recibos.
                if (getattr(orchestrator.config,"AGENT_MODE","legacy") in {"local","conversacional"}
                        and executor._pending_action is None):
                    voz_espera = progress_voice if progress_voice is not None else tts if speak else None
                    if voz_espera is tts and getattr(type(tts),'iniciar_espera',None) is not None:
                        tts.iniciar_espera(lambda:orchestrator.cancelar(session_id))
                        escucha_activa = True
                    if getattr(orchestrator.config,'AGENT_MODE','legacy') == 'conversacional' and voz_espera is not None:
                        def avisar_espera():
                            if fin_aviso.is_set() or detenido_visual.is_set():
                                return
                            try:
                                progreso({'type':'espera'})
                            except Exception:
                                log.debug('No se pudo emitir el aviso de espera',exc_info=True)
                        aviso_espera = threading.Timer(2.5,avisar_espera)
                        aviso_espera.daemon = True
                        aviso_espera.start()
                    response_text = orchestrator.atender(user_input, sesion=session_id,
                        generacion=turn_generation, on_event=progreso)
                    intent = "agent"
                    return entregar(response_text)

                from modules.orchestrator import ruta_rapida_admisible, decision_confirmacion, comando_compatible
                from modules.desktop_agent import match_desktop_task_route
                from modules.quick_routes import match_quick_route
                from modules.memory_router import match_memory_route
                from modules.file_router import match_file_route
                from modules.app_router import match_app_route
                from modules.media_router import match_media_route
                # Solo una orden completa toma la vía mecánica. El resto es objetivo.
                rapida = None
                if ruta_rapida_admisible(user_input):
                    # Cortesía solo al inicio; conserva mayúsculas/rutas del resto.
                    entrada_rapida = re.sub(r"^(?:(?:bien|vale|perfecto|por favor|limits|limites)[,.! ]+)+", "", user_input, flags=re.I)
                    for router in (match_quick_route, match_memory_route, match_file_route,
                                   match_app_route, match_media_route):
                        rapida = router(entrada_rapida)
                        if rapida:
                            break
                if (rapida and rapida.get("action") == "spotify_play"
                        and getattr(orchestrator.config,"AGENT_MODE","legacy") == "local"
                        and getattr(orchestrator.config,"SPOTIFY_MCP_ENABLED",False)):
                    rapida = None  # La búsqueda con OAuth debe usar URI observadas y verificación MCP.
                if rapida and rapida.get('action') == 'media_control' and reproductor:
                    if not rapida.setdefault('params', {}).get('player'):
                        rapida['params']['player'] = reproductor
                from modules.operation_intent import referencia_explicita
                anterior_operativo = orchestrator.almacen.cargar(session_id)
                if anterior_operativo and anterior_operativo.referente and anterior_operativo.estado not in {"cancelada", "sustituida"} and referencia_explicita(user_input):
                    rapida = None
                confirmar = decision_confirmacion(user_input)
                compuesto = match_desktop_task_route(user_input)
                if compuesto and not user_input.strip().lower().startswith(("busca", "encuentra")):
                    compuesto = None
                if compuesto and any(p in user_input.lower().split() for p in ("no", "nunca", "analiza", "explica", "recomienda")):
                    compuesto = None
                if confirmar and executor._pending_action is not None:
                    response_text = ejecutar_visual({"action": "confirm" if confirmar == "confirmar" else "cancel",
                                                      "params": {}, "response": "", "confidence": 1})
                elif rapida:
                    orchestrator.invalidar(session_id)
                    response_text = ejecutar_visual(rapida)
                elif compuesto and not getattr(orchestrator.config, "AGENT_SEMANTIC", False):
                    orchestrator.invalidar(session_id)
                    executor.desktop_agent.cancel_event = orchestrator.evento_turno(session_id, turn_generation)
                    try:
                        response_text = ejecutar_visual({"intent": "desktop_task", "action": "desktop_task",
                            "params": {"goal": compuesto}, "response": "Voy.", "confidence": 1.0})
                    finally:
                        executor.desktop_agent.cancel_event = None
                elif comando_compatible(user_input) and not getattr(orchestrator.config, "AGENT_SEMANTIC", False):
                    orchestrator.invalidar(session_id)
                    # El historial del router anterior también se aísla por sesión.
                    if isinstance(getattr(llm, "conversation_history", None), list):
                        llm.conversation_history = list(historiales_ordenes.get(session_id, []))
                        llm._history_loaded = True
                    parsed = llm.process(user_input)
                    if turn_generation != orchestrator.generacion(session_id):
                        return entregar("Tarea cancelada.")
                    if isinstance(getattr(llm, "conversation_history", None), list):
                        historiales_ordenes[session_id] = list(llm.conversation_history)
                    response_text = ejecutar_visual(parsed)
                else:
                    if getattr(type(tts), "iniciar_espera", None) is not None:
                        tts.iniciar_espera(lambda: orchestrator.cancelar(session_id))
                        escucha_activa = True
                    propuesta_local = None
                    historial_antes = list(historiales_ordenes.get(session_id,[]))
                    if getattr(orchestrator.config,"AGENT_SEMANTIC",False) and getattr(orchestrator.config,"AGENT_LOCAL_PROPOSALS",True) and not getattr(orchestrator.config,"AGENT_COHERENT",False):
                        from modules.gemini import match_gemini_route
                        if not match_gemini_route(user_input):
                            if orchestrator.conocimiento:
                                orchestrator.conocimiento.sincronizar()
                            if isinstance(getattr(llm,"conversation_history",None),list):
                                llm.conversation_history = list(historiales_ordenes.get(session_id,[]))
                                llm._history_loaded = True
                            propuesta_local = llm.process(user_input)
                            if isinstance(getattr(llm,"conversation_history",None),list):
                                historiales_ordenes[session_id] = list(llm.conversation_history)
                    response_text = orchestrator.atender(user_input, session_id, turn_generation, on_event=progreso, propuesta_local=propuesta_local)
                    if propuesta_local is not None:
                        fiable = str(response_text) if getattr(response_text,"ok",None) is not False else "El turno no se completó; consultar el estado antes de afirmar resultados."
                        historiales_ordenes[session_id] = (historial_antes + [{"role":"user","content":user_input},{"role":"assistant","content":fiable}])[-6:]
                intent = "objetivo"
                return entregar(response_text)

            # ── Ruta conversacional determinista ─────────────────────────────
            if gemini is not None:
                from modules.gemini import match_gemini_route
                route = match_gemini_route(user_input)
                if route:
                    executor.cancel_pending()
                    mode = route[0]
                    log.info("turno gemini (%s) vía palabra clave", mode)
                    log.debug(f"INPUT(gemini): {user_input}")
                    response_text = gemini.chat(
                        user_input, research=(mode == "research"))
                    intent = f"gemini_{mode}"
                    log.info(f"turno gemini completado | chars={len(response_text)}")
                    log.debug(f"RESPONSE(gemini): {response_text}")
                    return entregar(response_text)

            # ── Lane compuesto archivos (multi-paso) por palabras clave ─────
            from modules.desktop_agent import match_desktop_task_route
            desktop_goal = match_desktop_task_route(user_input)
            if desktop_goal:
                log.info("turno desktop_task vía palabra clave")
                parsed = {
                    "intent": "desktop_task",
                    "action": "desktop_task",
                    "params": {"goal": desktop_goal},
                    "response": "Voy.",
                    "confidence": 1.0,
                }
                response_text = ejecutar_visual(parsed)
                intent = "desktop_task"
                log.info("turno desktop_task completado")
                return entregar(response_text)

            # ── Rutas de un solo dato (hora/fecha), sin LLM ─────────────────
            from modules.quick_routes import match_quick_route
            quick = match_quick_route(user_input)
            if quick:
                log.info("turno quick_route | action=%s", quick["action"])
                response_text = ejecutar_visual(quick)
                intent = quick.get("intent")
                log.debug(f"RESPONSE(quick): {response_text}")
                return entregar(response_text)

            # ── Memoria explícita (recuerda / olvida / qué sabes) ────────────
            from modules.memory_router import match_memory_route
            memory_route = match_memory_route(user_input)
            if memory_route:
                log.info("turno memoria | action=%s", memory_route["action"])
                response_text = ejecutar_visual(memory_route)
                intent = memory_route.get("intent")
                log.debug(f"RESPONSE(memoria): {response_text}")
                return entregar(response_text)

            # ── Ruta determinista de archivos (carpeta explícita) ────────────
            # El LLM inventa rutas ("/Proyectos", "work") aunque tenga el mapa
            # del equipo. "lista la carpeta X" es mecánico: se resuelve aquí.
            from modules.file_router import match_file_route
            file_route = match_file_route(user_input)
            if file_route:
                log.info("turno archivos vía router determinista | "
                         f"action={file_route['action']}")
                response_text = ejecutar_visual(file_route)
                intent = file_route.get("intent")
                log.debug(f"RESPONSE(archivos): {response_text}")
                return entregar(response_text)

            # ── Ruta determinista de apps (abrir/cerrar/enfocar) ─────────────
            # «abre discord» o «pon spotify en pantalla» no necesitan modelo:
            # el 1.5b a veces las confundía entre sí.
            from modules.app_router import match_app_route
            app_route = match_app_route(user_input)
            if app_route:
                log.info("turno apps vía router determinista | "
                         f"action={app_route['action']}")
                response_text = ejecutar_visual(app_route)
                intent = app_route.get("intent")
                log.debug(f"RESPONSE(apps): {response_text}")
                return entregar(response_text)

            # ── Ruta determinista de música (control y "pon X") ──────────────
            from modules.media_router import match_media_route
            media_route = match_media_route(user_input)
            if media_route:
                log.info("turno música vía router determinista | "
                         f"action={media_route['action']}")
                response_text = ejecutar_visual(media_route)
                intent = media_route.get("intent")
                log.debug(f"RESPONSE(música): {response_text}")
                return entregar(response_text)

            # ── Ruta operativa (LLM router → executor) ───────────────────────
            log.debug(f"INPUT: {user_input}")
            parsed = llm.process(user_input)
            response_text = ejecutar_visual(parsed)
            intent = parsed.get("intent")
            log.info(f"turno procesado | intent={parsed.get('intent')} "
                     f"confidence={parsed.get('confidence', 0):.2f}")
            log.debug(f"RESPONSE: {response_text}")
            return entregar(response_text)
        finally:
            cerrar_aviso()
            if flujo is not None and not flujo_cerrado:
                orchestrator.cancelar(session_id)
                flujo.cerrar()
            try:
                terminar_escucha()
            except Exception:
                log.warning("No se pudo finalizar la escucha del turno", exc_info=True)
            if response_text:
                try:
                    from modules.memory import get_store
                    store = get_store()
                    meta = {"sesion": session_id, "turno": turno_id, "segundos": round(time.monotonic() - inicio_turno, 3), "acciones": getattr(response_text, "acciones", [])}
                    store.log_turn("user", user_input, intent=intent, meta=meta)
                    store.log_turn("assistant", response_text, intent=intent, ok=getattr(response_text, "ok", None), meta=meta)
                    if orchestrator is not None:
                        orchestrator.registrar_dialogo(user_input, response_text, session_id)
                except Exception as error:
                    log.warning("No se pudo actualizar historial o memoria (%s)", type(error).__name__)
            if presencia:
                if orchestrator is not None and turn_generation != orchestrator.generacion(session_id):
                    final_visual = "interrumpido"
                presencia.terminar(turno_visual, final_visual)
            gate.release()
    pipeline.session_aware = orchestrator is not None
    pipeline.progress_aware = orchestrator is not None
    pipeline.cancel = orchestrator.cancelar if orchestrator is not None else None
    pipeline.generation = orchestrator.generacion if orchestrator is not None else None
    return pipeline


def main():
    parser = argparse.ArgumentParser(description="Limits Linux — Asistente de voz")
    parser.add_argument("--text", action="store_true", help="Modo texto (sin micrófono, ideal para testing)")
    parser.add_argument("--once", action="store_true", help="Ejecutar un solo comando y salir")
    args = parser.parse_args()

    config = Config()
    from modules import presence
    presencia = None
    if config.PRESENCE_ENABLED:
        try:
            presencia = presence.Presencia(config.PRESENCE_SOCKET, {
                "tamano": config.PRESENCE_SIZE, "arriba": config.PRESENCE_MARGIN_TOP,
                "derecha": config.PRESENCE_MARGIN_RIGHT, "opacidad": config.PRESENCE_OPACITY,
                "movimiento_reducido": config.PRESENCE_REDUCED_MOTION,
                "monitor": config.PRESENCE_MONITOR,
            }).iniciar()
            presence.instalar(presencia)
        except OSError:
            log.warning("Widget no disponible; Limits continúa sin interfaz.", exc_info=True)
    print_banner(config)
    log.info("Limits iniciado.")

    console.print("\n[bold]Iniciando módulos...[/bold]")
    llm      = LLMEngine(config)
    from modules.desktop_agent import DesktopAgent, load_opencode_api_key
    from modules.agent_providers import crear_respaldos, ProveedorConRespaldo
    remotos = crear_respaldos(config)
    oc_key = load_opencode_api_key(config.OPENCODE_API_KEY) if config.DESKTOP_AGENT_PROVIDER == "opencode" else ""
    desktop_agent = DesktopAgent(
        files=None,  # CommandExecutor re-bind a self.files
        ollama_url=config.OLLAMA_URL,
        ollama_model=config.DESKTOP_AGENT_MODEL,
        keep_alive=config.OLLAMA_KEEP_ALIVE,
        num_ctx=config.OLLAMA_NUM_CTX,
        max_steps=config.DESKTOP_AGENT_MAX_STEPS,
        provider=config.DESKTOP_AGENT_PROVIDER,
        opencode_api_key=oc_key,
        opencode_base_url=config.OPENCODE_BASE_URL,
        opencode_model=config.OPENCODE_AGENT_MODEL,
        fallback=config.DESKTOP_AGENT_FALLBACK,
        proveedor_remoto=ProveedorConRespaldo(remotos["desarrollo"], enfriamiento=config.NVIDIA_MODEL_COOLDOWN),
    )
    if config.DESKTOP_AGENT_PROVIDER == "nvidia":
        console.print("[green]✓ Desktop agent: NVIDIA DeepSeek (selección explícita)[/green]")
    elif config.DESKTOP_AGENT_PROVIDER == "opencode":
        if oc_key:
            console.print("[green]✓ Desktop agent: OpenCode "
                          f"{config.OPENCODE_AGENT_MODEL}[/green] "
                          f"[dim](fallback {config.DESKTOP_AGENT_FALLBACK})[/dim]")
        else:
            console.print("[yellow]Desktop agent: sin OPENCODE_API_KEY — "
                          f"usará fallback {config.DESKTOP_AGENT_FALLBACK}"
                          f" ({config.DESKTOP_AGENT_MODEL})[/yellow]")
    else:
        console.print(f"[dim]Desktop agent: {config.DESKTOP_AGENT_PROVIDER} "
                      f"/ {config.DESKTOP_AGENT_MODEL}[/dim]")
    executor = CommandExecutor(desktop_agent=desktop_agent)
    executor.configure_files(
        search_roots=config.FILE_SEARCH_ROOT,
        search_excludes=config.FILE_SEARCH_EXCLUDES,
        focus_delay_s=config.FILE_FOCUS_DELAY_S,
    )
    # P1: el router solo puede emitir acciones que existan de verdad.
    # `confirm`/`cancel` no viven en el action_map (los resuelve `execute()`),
    # pero son acciones legítimas del protocolo.
    llm.known_actions = frozenset(executor.action_map) | {"confirm", "cancel"}

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

    # ── Barge-in: TTS + escucha simultánea (P0-4) ───────────────────────────
    from modules.speech_controller import SpeechController
    speech = SpeechController(
        tts,
        stt=stt,
        enabled=config.BARGEIN_ENABLED,
        keywords=[k.strip() for k in config.BARGEIN_KEYWORDS.split(",")
                  if k.strip()],
        min_ms=config.BARGEIN_MIN_MS,
    )
    if speech.enabled:
        console.print("[green]✓ Barge-in listo[/green] "
                      "[dim](di «para» mientras hablo)[/dim]")

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
            min_research_chars=config.GEMINI_MIN_RESEARCH_CHARS,
            research_daemon=config.GEMINI_RESEARCH_DAEMON,
            streaming=config.GEMINI_STREAMING,
        )
        if candidato.available():
            gemini_bridge = candidato
            executor.gemini = gemini_bridge
            console.print(f"[green]✓ Cerebro conversacional Gemini listo[/green] "
                          f"[dim](investiga/investigame/busca/infórmame/… o gemini_talk)[/dim]")
        else:
            console.print(f"[yellow]GEMINI_BIN no encontrado: "
                          f"{config.GEMINI_BIN} — cerebro desactivado[/yellow]")

    orchestrator = None
    if config.AGENT_ENABLED:
        from modules.orchestrator import Orquestador
        orchestrator = Orquestador(config, executor, gemini=gemini_bridge, remoto=remotos)
        console.print("[green]✓ Coordinación por objetivos activada[/green]")
    pipeline = make_pipeline(llm, executor, speech, gate, gemini=gemini_bridge,
                             orchestrator=orchestrator)

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
                speak_fn=speech.speak,
                stop_fn=speech.stop,
                # El micro del móvil dicta «para» como texto: eso también corta.
                stop_words=[k.strip() for k in config.BARGEIN_KEYWORDS.split(",")
                            if k.strip()],
            )
            gw_info = gateway.start()
            console.print(f"[green]✓ Gateway móvil:[/green] "
                          f"ws://{gw_info['ip']}:{gw_info['port']}/ws")
            if config.GATEWAY_SHOW_QR:
                # print() plano: el QR trae secuencias ANSI que rich alteraría
                gateway.print_pairing()
            else:
                console.print(f"[dim]   token: "
                              f"{config.GATEWAY_TOKEN_PATH or '~/.limits/gateway_token'}"
                              f" (QR: `limits-qr`)[/dim]")
            # Los archivos locales a castear salen por URLs firmadas del gateway
            executor.tv.media_url_factory = gateway.make_media_url
        except OSError as e:
            console.print(f"[yellow]Gateway no iniciado ({e}); "
                          f"¿otra instancia ya usa el puerto {config.GATEWAY_PORT}?[/yellow]")
            gateway = None

    console.print("\n[bold green]✓ Limits listo.[/bold green]\n")
    speech.speak("Limits listo. ¿En qué te puedo ayudar?")

    global _shutdown_requested

    seguimiento_hasta = 0.0
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
                sin_wake_word = time.monotonic() < seguimiento_hasta
                user_input = stt.listen_and_transcribe()
                presence.escucha(False)

                if not user_input:
                    continue

                # Filtrar por wake word si está configurada
                if config.WAKE_WORD and not sin_wake_word:
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
                    speech.speak("¿Sí?")
                    user_input = stt.listen_and_transcribe()
                presence.escucha(False)

                # Salida por voz
                if user_input and user_input.lower() in ("salir", "exit", "apagarte"):
                    break

            if user_input:
                respuesta_turno = pipeline(user_input)
                seguimiento_hasta = (time.monotonic() + config.DIALOGUE_FOLLOWUP_SECONDS
                                     if (getattr(respuesta_turno, "pregunta_abierta", "") or str(respuesta_turno).rstrip().endswith("?")) and not getattr(respuesta_turno, "cancelada", False) else 0.0)
                # Barge-in: si interrumpiste con un comando, se encadena.
                while speech.pending_text:
                    follow = speech.pending_text
                    speech.pending_text = ""
                    console.print(f"[dim]Turno encadenado: {follow}[/dim]")
                    pipeline(follow)

            if args.once:
                break

    except KeyboardInterrupt:
        console.print("\n[yellow]Interrumpido por el usuario.[/yellow]")
    finally:
        if orchestrator is not None:
            orchestrator.cancelar("local")
        if gateway:
            gateway.stop()
        speech.speak("Hasta luego.")
        log.info("Limits apagado.")
        if stt:
            stt.cleanup()
        if presencia:
            presencia.cerrar()
            presence.instalar(None)


if __name__ == "__main__":
    main()
