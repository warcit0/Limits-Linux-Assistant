"""Aceptación optativa con proveedores y audio reales; usa tareas desechables."""

import argparse
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import Config
from main import make_pipeline
from modules.executor import CommandExecutor
from modules.gateway import TurnGate
from modules.gemini import GeminiBridge
from modules.orchestrator import Orquestador
from modules.speech_controller import SpeechController
from modules.tts import TTSEngine


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--live",
        action="store_true",
        help="Autoriza cambiar/restaurar workspace y reproducir voz real",
    )
    args = p.parse_args()
    if not args.live:
        p.error(
            "Para esta aceptación real usa --live. Las pruebas sin efectos están en unittest."
        )
    activo = (
        subprocess.run(
            ["systemctl", "--user", "is-active", "--quiet", "limits.service"]
        ).returncode
        == 0
    )
    informe = {
        "microfono_manual": "no probado; usuario solicitó continuar automáticamente"
    }
    try:
        if activo:
            subprocess.run(
                ["systemctl", "--user", "stop", "limits.service"], check=True
            )
        c = Config()
        executor = CommandExecutor()
        w = executor.workspaces
        original = w._leer("activeworkspace")["id"]
        candidatos = [
            e["id"]
            for e in w._leer("workspaces")
            if e["id"] > 0 and e["id"] != original
        ]
        if candidatos:
            try:
                destino = candidatos[0]
                antes = time.monotonic()
                resultado = w.switch(str(destino))
                informe["workspace"] = {
                    "ok": w._leer("activeworkspace")["id"] == destino,
                    "segundos": round(time.monotonic() - antes, 3),
                    "respuesta": resultado,
                }
            finally:
                w.switch(str(original))
                informe["workspace"]["restaurado"] = (
                    w._leer("activeworkspace")["id"] == original
                )
        else:
            informe["workspace"] = {
                "ok": False,
                "motivo": "No hay otro espacio existente; no se crea uno para la prueba.",
            }
        print(
            json.dumps({"workspace": informe["workspace"]}, ensure_ascii=False),
            flush=True,
        )
        with (
            tempfile.TemporaryDirectory(prefix="limits-conversacion-") as d,
            mock.patch("modules.memory.get_store"),
        ):
            c.AGENT_TASK_PATH = d
            voz = SpeechController(
                TTSEngine(c.PIPER_VOICE_MODEL, c.VOICE_SPEED, c.VOICE_SPEAKER),
                enabled=False,
            )
            gemini = GeminiBridge(c.GEMINI_BIN, timeout_s=95, streaming=True)
            orq = Orquestador(c, executor, gemini=gemini)
            pipeline = make_pipeline(
                mock.Mock(), executor, voz, TurnGate(), orchestrator=orq
            )
            inicio = time.monotonic()
            eventos = []

            def avance(ev):
                r = {
                    "tipo": ev.get("type"),
                    "segundos": round(time.monotonic() - inicio, 3),
                    "chars": len(ev.get("text", "")),
                }
                eventos.append(r)
                print(json.dumps(r), flush=True)

            respuesta = pipeline(
                "Investiga dos novedades del sector automotriz publicadas en octubre de 2026. Resume en unas 120 palabras, cita fuentes y fechas y termina con una pregunta concreta para continuar.",
                on_progress=avance,
            )
            metricas = getattr(respuesta, "audio_metricas", [])
            final = next((e["segundos"] for e in eventos if e["tipo"] == "final"), None)
            pcm = [m for m in metricas if "pcm_s" in m]
            contenido = [m for m in pcm if m["tipo"] == "contenido"]
            informe["gemini"] = {
                "ok": getattr(respuesta, "ok", False),
                "segundos_total_con_audio": round(time.monotonic() - inicio, 3),
                "eventos": eventos,
                "audio": metricas,
                "habla_antes_del_final": bool(
                    contenido and final and contenido[0]["pcm_s"] < final
                ),
                "acuse_pcm_menos_2s": bool(pcm and pcm[0]["pcm_s"] <= 2),
                "pregunta_continuacion": bool(
                    getattr(respuesta, "pregunta_abierta", "")
                ),
                "texto_completo": respuesta.completo,
            }
        informe["ok"] = bool(
            informe["workspace"]["ok"]
            and informe["workspace"]["restaurado"]
            and informe["gemini"]["ok"]
            and informe["gemini"]["habla_antes_del_final"]
        )
        return 0 if informe["ok"] else 1
    finally:
        Path("logs/probe_conversation_last.json").write_text(
            json.dumps(informe, ensure_ascii=False, indent=2)
        )
        if activo:
            subprocess.run(
                ["systemctl", "--user", "start", "limits.service"], check=True
            )


if __name__ == "__main__":
    raise SystemExit(main())
