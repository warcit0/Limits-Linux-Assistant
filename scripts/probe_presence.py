"""Aceptación optativa del widget con PCM real, sin modelos, memoria ni micrófono."""

import argparse
import json
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import Config
from modules import presence
from modules.speech_controller import SpeechController
from modules.tts import TTSEngine


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", required=True)
    parser.parse_args()
    c = Config()
    activo = (
        subprocess.run(
            ["systemctl", "--user", "is-active", "--quiet", "limits.service"]
        ).returncode
        == 0
    )
    resultados = {}
    bus = None
    try:
        if activo:
            subprocess.run(
                ["systemctl", "--user", "stop", "limits.service"], check=True
            )
        bus = presence.Presencia(
            c.PRESENCE_SOCKET,
            {
                "tamano": c.PRESENCE_SIZE,
                "arriba": c.PRESENCE_MARGIN_TOP,
                "derecha": c.PRESENCE_MARGIN_RIGHT,
            },
        ).iniciar()
        presence.instalar(bus)
        observados = []
        fin = threading.Event()

        def observar():
            with socket.socket(socket.AF_UNIX) as cli:
                cli.connect(c.PRESENCE_SOCKET)
                cli.settimeout(0.2)
                datos = b""
                while not fin.is_set():
                    try:
                        datos += cli.recv(4096)
                    except socket.timeout:
                        continue
                    while b"\n" in datos:
                        linea, datos = datos.split(b"\n", 1)
                        observados.append(json.loads(linea))

        hilo = threading.Thread(target=observar, daemon=True)
        hilo.start()
        voz = SpeechController(
            TTSEngine(c.PIPER_VOICE_MODEL, c.VOICE_SPEED, c.VOICE_SPEAKER),
            enabled=False,
        )
        turno = bus.comenzar(voz.stop)
        bus.fase("investigando")
        antes = json.loads(subprocess.check_output(["hyprctl", "-j", "activewindow"]))
        time.sleep(0.5)
        despues = json.loads(subprocess.check_output(["hyprctl", "-j", "activewindow"]))
        inicio = time.monotonic()
        r = voz.speak(
            "Esta es una prueba de la presencia de Limits. El núcleo responde a mi voz y conserva el foco de tu aplicación."
        )
        bus.terminar(turno)
        time.sleep(0.15)
        resultados["audio"] = {
            "ok": r == "ok",
            "segundos": round(time.monotonic() - inicio, 3),
            "muestras": len(observados),
            "niveles_distintos": len({e["nivel"] for e in observados}),
            "investigacion_durante_voz": any(
                e["estado"] == "hablando" and e["actividad"] == "investigando"
                for e in observados
            ),
            "foco_intacto": antes.get("address") == despues.get("address"),
        }
        # La ruta de audio comprimido de ElevenLabs se prueba sin API ni cuota.
        import tempfile

        from modules.audio_meter import reproducir_archivo

        with tempfile.TemporaryDirectory(prefix="limits-audio-prueba-") as d:
            wav = Path(d) / "senal.wav"
            subprocess.run(
                [
                    "ffmpeg",
                    "-nostdin",
                    "-loglevel",
                    "error",
                    "-f",
                    "lavfi",
                    "-i",
                    "sine=frequency=330:duration=0.35",
                    "-y",
                    str(wav),
                ],
                check=True,
            )
            turno = bus.comenzar()
            resultados["decodificacion_pcm"] = reproducir_archivo(wav) == "ok"
            bus.terminar(turno)
        # Corte real por el mismo mensaje local que envía el botón.
        turno = bus.comenzar(voz.stop)
        resultado = []
        lector = threading.Thread(
            target=lambda: resultado.append(
                voz.speak(
                    "Esta prueba de voz debe detenerse antes de completar esta frase y no continuar hablando después del corte."
                )
            )
        )
        lector.start()
        limite = time.monotonic() + 10
        while bus.audio_id is None and time.monotonic() < limite:
            time.sleep(0.02)
        inicio = time.monotonic()
        with socket.socket(socket.AF_UNIX) as cli:
            cli.connect(c.PRESENCE_SOCKET)
            cli.sendall((json.dumps({"cmd": "stop", "turno": turno}) + "\n").encode())
        lector.join(3)
        if lector.is_alive():
            import faulthandler

            with open("/tmp/limits-widget-hilos.log", "w") as traza:
                faulthandler.dump_traceback(file=traza)
        resultados["cancelacion"] = {
            "ok": resultado == ["interrupted"] and not lector.is_alive(),
            "segundos": round(time.monotonic() - inicio, 3),
        }
        voz.stop()
        lector.join(10)
        bus.terminar(turno)
        fin.set()
        hilo.join(1)
        resultados["ok"] = bool(
            resultados["audio"]["ok"]
            and resultados["audio"]["niveles_distintos"] > 3
            and resultados["audio"]["foco_intacto"]
            and resultados["decodificacion_pcm"]
            and resultados["cancelacion"]["ok"]
        )
        return 0 if resultados["ok"] else 1
    finally:
        if bus:
            bus.cerrar()
            presence.instalar(None)
        Path("logs/probe_presence_last.json").write_text(
            json.dumps(resultados, ensure_ascii=False, indent=2)
        )
        if activo:
            subprocess.run(
                ["systemctl", "--user", "start", "limits.service"], check=True
            )


if __name__ == "__main__":
    raise SystemExit(main())
