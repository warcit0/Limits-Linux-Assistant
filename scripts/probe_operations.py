"""Aceptación restaurable de la conversación: ventanas reales, sin micrófono."""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from unittest import mock

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
FRASES = [
    "qué tal estás hoy",
    "bien livings primero muéveme al espacio de trabajo 3",
    "quiero que abras code con la carpeta creador de videos",
    "Ábrelo Ábreme mi pantalla en el espacio de trabajo 3",
    "bien entonces abre el gestor de cotizaciones con code",
    "mejor muévete al espacio de trabajo donde tengo firefox y Busca en YouTube un video sobre perros",
    "un video sobre perro haciendo acariciados",
    "Abre Spotify y Reproduce la música",
    "Abre Spotify",
    "Reproduce la música",
]


def leer(consulta):
    return json.loads(subprocess.check_output(["hyprctl", "-j", consulta], text=True))


def ejecutar(*args):
    return subprocess.run(
        list(args),
        capture_output=True,
        text=True,
        timeout=30 if args[0] == "systemctl" else 5,
    )


def esperar(comprobar, segundos=8):
    limite = time.monotonic() + segundos
    while time.monotonic() < limite:
        r = comprobar()
        if r:
            return r
        time.sleep(0.1)
    return None


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--live", action="store_true", required=True)
    p.parse_args()
    informe = {"microfono": False, "cuota_remota": False, "turnos": []}
    activo = (
        ejecutar(
            "systemctl", "--user", "is-active", "--quiet", "limits.service"
        ).returncode
        == 0
    )
    originales = leer("clients")
    previas = {c["address"]: c for c in originales}
    foco = leer("activewindow").get("address")
    espacio = leer("activeworkspace")["id"]
    reproductor = ejecutar("playerctl", "--player", "spotify", "status").stdout.strip()
    creados = set()
    lanzados = []
    try:
        if activo:
            ejecutar("systemctl", "--user", "stop", "limits.service").check_returncode()
        with tempfile.TemporaryDirectory(prefix="limits-aceptacion-") as temporal:
            os.environ["LIMITS_LOG_PATH"] = str(Path(temporal) / "prueba.log")
            from config import Config
            from main import make_pipeline
            from modules.agent_providers import ProveedorOllama
            from modules.executor import CommandExecutor
            from modules.gateway import TurnGate
            from modules.llm import LLMEngine
            from modules.orchestrator import Orquestador

            c = Config()
            c.AGENT_SEMANTIC = False
            c.KNOWLEDGE_ENABLED = False
            c.AGENT_TASK_PATH = str(Path(temporal) / "tareas")
            executor = CommandExecutor()
            local = ProveedorOllama(c)

            class SinRemoto:
                def consultar(self, *a, **kw):
                    raise AssertionError(
                        "Esta prueba no debe consultar un proveedor remoto"
                    )

            orq = Orquestador(
                c,
                executor,
                proveedores={
                    "cotidiano": local,
                    "analisis": SinRemoto(),
                    "desarrollo": SinRemoto(),
                },
            )
            original_popen = subprocess.Popen

            def abrir(args, **kwargs):
                args = list(args)
                if args[0] == "firefox" and "--new-tab" in args:
                    args[args.index("--new-tab")] = "--new-window"
                if args[0] in {"firefox", "code", "spotify-launcher"}:
                    lanzados.append({"programa": args[0], "argumento": args[-1]})
                return original_popen(args, **kwargs)

            with (
                mock.patch("modules.memory.get_store") as memoria,
                mock.patch("subprocess.Popen", side_effect=abrir),
            ):
                memoria.return_value.facts_block.return_value = ""
                memoria.return_value.recent_turns.return_value = []
                llm = LLMEngine(c)
                pipeline = make_pipeline(
                    llm, executor, mock.Mock(), TurnGate(), orchestrator=orq
                )
                for i, frase in enumerate(FRASES):
                    antes = time.monotonic()
                    respuesta = pipeline(
                        frase, speak=False, session_id="aceptacion:conversacion"
                    )
                    clientes = leer("clients")
                    actual = leer("activeworkspace")["id"]
                    for cliente in clientes:
                        if cliente["address"] not in previas and (
                            cliente.get("class", "").lower()
                            in {
                                "code",
                                "code-oss",
                                "vscodium",
                                "spotify",
                                "firefox",
                                "alacritty",
                            }
                        ):
                            creados.add(cliente["address"])
                    evidencia = {
                        "workspace": actual,
                        "ventanas_code": sum(
                            c.get("class", "").lower()
                            in {"code", "code-oss", "vscodium"}
                            for c in clientes
                        ),
                        "spotify": ejecutar(
                            "playerctl", "--player", "spotify", "status"
                        ).stdout.strip(),
                    }
                    ok = True
                    if i in {1, 3}:
                        ok = actual == 3
                    if i == 2:
                        ok = any(
                            "creador de videos" in c.get("title", "").lower()
                            for c in clientes
                        )
                    if i == 4:
                        ok = any(
                            "gestor de cotizaciones" in c.get("title", "").lower()
                            for c in clientes
                        )
                    if i in {5, 6}:
                        ok = any(
                            x["programa"] == "firefox"
                            and "youtube.com/results?" in x["argumento"]
                            for x in lanzados
                        ) and (
                            i != 5
                            or any(
                                c.get("address") == leer("activewindow").get("address")
                                and c.get("class", "").lower() == "firefox"
                                for c in clientes
                            )
                        )
                    if i in {7, 9}:
                        ok = evidencia["spotify"] == "Playing" or (
                            "canción o artista" in respuesta
                            and getattr(respuesta, "ok", None) is not True
                        )
                    if i == 8:
                        ok = any(
                            c.get("class", "").lower() == "spotify" for c in clientes
                        )
                    registro = {
                        "indice": i,
                        "frase": frase,
                        "respuesta": str(respuesta),
                        "ok": ok,
                        "cumplimiento": getattr(respuesta, "ok", None),
                        "segundos": round(time.monotonic() - antes, 3),
                        "acciones": getattr(respuesta, "acciones", []),
                        "evidencia": evidencia,
                    }
                    informe["turnos"].append(registro)
                    print(
                        json.dumps(
                            {
                                k: v
                                for k, v in registro.items()
                                if k not in {"respuesta", "evidencia"}
                            },
                            ensure_ascii=False,
                        ),
                        flush=True,
                    )
                    if not ok:
                        informe["diagnostico"] = {
                            "ventana_activa": leer("activewindow"),
                            "clientes": clientes,
                        }
                        break
                informe["sin_memoria_real"] = memoria.return_value.log_turn.called
        informe["ok"] = len(informe["turnos"]) == 10 and all(
            t["ok"] for t in informe["turnos"]
        )
    finally:
        # Solo cerrar las ventanas abiertas durante este escenario; no cerrar las previas.
        for c in leer("clients"):
            if c["address"] in creados and re.fullmatch(
                r"0x[0-9a-fA-F]+", c["address"]
            ):
                ejecutar(
                    "hyprctl", "dispatch", "closewindow", "address:" + c["address"]
                )
        for c in leer("clients"):
            viejo = previas.get(c["address"])
            if viejo and viejo.get("workspace", {}).get("id") != c.get(
                "workspace", {}
            ).get("id"):
                ejecutar(
                    "hyprctl",
                    "dispatch",
                    "movetoworkspacesilent",
                    str(viejo["workspace"]["id"]) + ",address:" + c["address"],
                )
        if reproductor in {"Paused", "Stopped"}:
            ejecutar(
                "playerctl",
                "--player",
                "spotify",
                "pause" if reproductor == "Paused" else "stop",
            )
        if foco and any(c["address"] == foco for c in leer("clients")):
            ejecutar("hyprctl", "dispatch", "focuswindow", "address:" + foco)
        else:
            ejecutar("hyprctl", "dispatch", "workspace", str(espacio))
        informe["restauracion"] = {
            "workspace": leer("activeworkspace")["id"] == espacio,
            "foco": leer("activewindow").get("address") == foco,
        }
        informe["ok"] = informe.get("ok", False) and all(informe["restauracion"].values())
        (BASE / "logs/probe_operations_last.json").write_text(
            json.dumps(informe, ensure_ascii=False, indent=2)
        )
        if activo:
            ejecutar(
                "systemctl", "--user", "start", "limits.service"
            ).check_returncode()

    return 0 if informe["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
