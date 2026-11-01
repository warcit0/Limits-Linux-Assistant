"""Prueba general con modelos reales y herramientas simuladas, sin efectos externos."""

import argparse
import functools
import json
import sys
import tempfile
import time
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import Config
from modules.agent_providers import (
    ProveedorNvidia,
    ProveedorOllama,
    crear_cotidiano,
)
from modules.command_result import ResultadoComando
from modules.executor import CommandExecutor
from modules.llm import LLMEngine
from modules.orchestrator import Orquestador

CASOS = [
    ("Dale Play a la música de Spotify", "media_control", {"action": "play"}),
    (
        "I living to primero que nada Abre Spotify y ponme algo de música puede ser bachata",
        "spotify_play",
        {"query": "bachata"},
    ),
    ("Sería genial dejar el volumen al 25", "set_volume", {"level": 25}),
    ("al espacio de trabajo uno", "workspace_switch", {"target": "1"}),
    ("¿Qué canción está sonando de verdad?", "get_current_song", {}),
    (
        "Por favor necesito saber cuánto espacio queda en el disco",
        "get_system_info",
        {},
    ),
    ("Pon el brillo al 40 y el volumen al 20", "set_volume", {"level": 20}),
    ("No cambies el volumen; explícame qué hace ese control", None, {}),
    ("Busca en Spotify bachata y Pon algo", "spotify_play", {"query": "bachata"}),
    ("Me interesa revisar cuánta RAM estoy usando", "get_system_info", {}),
]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--model", default="qwen2.5:1.5b-instruct")
    p.add_argument("--limit", type=int, default=len(CASOS))
    p.add_argument("--local-proposals", action="store_true")
    p.add_argument("--pause", type=float, default=0, help="Pausa entre casos para respetar la cuota gratuita.")
    p.add_argument("--primary-only", action="store_true")
    p.add_argument("--brain", choices=["local", "groq", "nvidia"], default="local")
    p.add_argument(
        "--specialist",
        action="store_true",
        help="Permite escalado real a proveedores configurados; consume cuota.",
    )
    args = p.parse_args()
    filas = []
    compartidos = None
    with tempfile.TemporaryDirectory(prefix="limits-general-") as tmp:
        c = Config()
        c.AGENT_SEMANTIC = True
        c.KNOWLEDGE_ENABLED = False
        c.AGENT_ESCALATE = args.specialist
        c.AGENT_TASK_PATH = tmp
        if args.brain == "local":
            c.OLLAMA_MODEL = args.model
            c.AGENT_CONVERSATION_MODEL = args.model
        if args.brain == "groq" and args.model.startswith("openai/"):
            c.GROQ_AGENT_MODEL = args.model
        c.AGENT_TIMEOUT = 90
        c.AGENT_MAX_STEPS = 6
        if args.primary_only:
            c.AGENT_COGNITIVE_FALLBACK_MODEL = ""
        for i, (frase, esperado, params) in enumerate(CASOS[: args.limit]):
            if i and args.pause:
                time.sleep(min(30,args.pause))
            executor = CommandExecutor()
            llamadas = []
            media = {"playing":False,"query":"Pista de prueba"}
            for nombre, handler in list(executor.action_map.items()):

                def crear(n, h):
                    @functools.wraps(h)
                    def simulado(**kw):
                        llamadas.append({"accion": n, "parametros": kw})
                        if n == "spotify_play":
                            media.update(playing=True,query=kw["query"])
                        elif n == "media_control":
                            media['playing'] = kw.get('action') == 'play'
                        datos = {
                            "get_current_song": ("Spotify está reproduciendo " if media["playing"] else "Spotify está pausado; tiene cargada ")+media["query"],
                            "spotify_play": "Spotify está abierto y reproduciendo "+media["query"]+"; estado simulado verificado.",
                            "media_control": "Spotify está "+("reproduciendo" if media["playing"] else "pausado")+"; estado simulado verificado.",
                            "get_volume": "Volumen observado: 30 %.",
                            "get_system_info": "RAM 2 GB; disco 20 GB libres.",
                        }.get(n, "Efecto simulado y comprobado: " + n)
                        return ResultadoComando(datos, ok=True, verificado=True)

                    return simulado

                executor.action_map[nombre] = crear(nombre, handler)
            if args.specialist:
                orq = Orquestador(c, executor, proveedores=compartidos)
                compartidos = orq.proveedores
            else:
                local = crear_cotidiano(c) if args.brain == "groq" else ProveedorNvidia(c, args.model if not args.model.startswith("qwen") else c.NVIDIA_ANALYSIS_MODEL, clave=c.NVIDIA_BOLT_API_KEY or c.NVIDIA_API_KEY) if args.brain == "nvidia" else ProveedorOllama(c)
                orq = Orquestador(
                    c,
                    executor,
                    proveedores={
                        r: local for r in ("cotidiano", "analisis", "desarrollo")
                    },
                )
            inicio = time.monotonic()
            propuesta = None
            if args.local_proposals:
                with mock.patch("modules.memory.get_store") as memoria:
                    memoria.return_value.facts_block.return_value = ""
                    memoria.return_value.recent_turns.return_value = []
                    propuesta = LLMEngine(c).process(frase)
            r = orq.atender(frase, sesion="evaluacion:" + str(i), propuesta_local=propuesta)
            estado = orq.almacen.cargar("evaluacion:" + str(i))
            ok = (
                not any(l["accion"] in {"set_volume","set_brightness","media_control","spotify_play","workspace_switch","shutdown","reboot"} for l in llamadas)
                if esperado is None
                else any(
                    l["accion"] == esperado
                    and all(
                        str(l["parametros"].get(k)).casefold() == str(v).casefold()
                        for k, v in params.items()
                    )
                    for l in llamadas
                )
            )
            if esperado is not None:
                ok = ok and getattr(r, "ok", None) is True
            fila = {
                "frase": frase,
                "esperado": esperado,
                "ok": bool(ok),
                "segundos": round(time.monotonic() - inicio, 3),
                "respuesta": str(r),
                "llamadas": llamadas,
                "rol": estado.rol,
                "modo": estado.modo,
                "escalado": estado.escalado,
                "historial": estado.historial, "propuesta_local":propuesta,
            }
            filas.append(fila)
            print(
                json.dumps(
                    {
                        k: v
                        for k, v in fila.items()
                        if k not in {"historial", "respuesta"}
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
        salida = {
            "modelo": args.model if args.brain == "local" else c.NVIDIA_ANALYSIS_MODEL if args.brain == "nvidia" else c.GROQ_AGENT_MODEL,
            "especialista": args.specialist, "propuestas_locales":args.local_proposals,
            "efectos_reales": False,
            "aciertos": sum(f["ok"] for f in filas),
            "total": len(filas),
            "filas": filas,
        }
        destino = (
            Path(__file__).resolve().parent.parent
            / "logs"
            / (
                "probe_general_"
                + (args.model if args.brain == "local" else args.brain)
                .replace(":", "_")
                .replace("/", "_")
                + ("_specialist" if args.specialist else "") + ("_runtime" if args.local_proposals else "")
                + ".json"
            )
        )
        destino.write_text(json.dumps(salida, ensure_ascii=False, indent=2))
        print(f"{salida['aciertos']}/{salida['total']}", flush=True)
        return 0 if salida["aciertos"] == salida["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
