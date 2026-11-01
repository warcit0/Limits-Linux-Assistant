"""Mide selección de roles con Ollama; nunca ejecuta herramientas ni acciones."""

from pathlib import Path
import argparse
import json
import statistics
import sys
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import Config
from modules.agent_providers import ProveedorOllama
from modules.orchestrator import modo_autorizado, contexto_ruta
from modules.task_state import Tarea


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--output", default="logs/probe_objectives_last.json")
    parser.add_argument("--min-accuracy", type=float, default=0.90)
    args = parser.parse_args()
    base = Path(__file__).resolve().parent.parent
    corpus = json.loads((base / "tests/corpus_objetivos.json").read_text())
    if args.limit:
        corpus = corpus[:args.limit]
    proveedor = ProveedorOllama(Config())
    prompt = (base / "prompts/agent_router.txt").read_text()
    anterior = {"objetivo": "Organizar la carpeta /tmp/limits-demo",
                "modo": "leer", "historial": [{"asistente": "Opción 1: organizar por fecha. Opción 2: organizar por extensión. Script anterior: organizar.py."}]}
    resultados = []
    for caso in corpus:
        inicio = time.monotonic()
        salida, error = {}, None
        try:
            contexto = contexto_ruta(caso["entrada"], anterior if caso.get("continuar") else None)
            salida = proveedor.consultar(prompt,
                contexto,
                tarea=Tarea("sonda", caso["entrada"]), cancelar=threading.Event(), timeout=45)
            salida["modo"] = modo_autorizado(caso["entrada"], salida.get("modo"))
            salida["continuar"] = contexto["referencia_anterior"] and contexto["tarea_anterior"] is not None
        except Exception as exc:
            error = type(exc).__name__
        correcto = (salida.get("rol") == caso["rol"] and salida.get("modo") == caso["modo"]
                    and salida.get("continuar") == caso.get("continuar", False))
        duracion = round((time.monotonic() - inicio) * 1000)
        resultados.append({"caso": caso, "salida": salida, "ok": correcto,
                           "error": error, "ms": duracion})
        print(f'{"OK" if correcto else "FALLO"} {duracion:5d} ms {caso["entrada"]}', flush=True)
    resumen = {"total": len(resultados), "aciertos": sum(r["ok"] for r in resultados),
               "p50_ms": statistics.median(r["ms"] for r in resultados),
               "resultados": resultados}
    destino = Path(args.output)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(resumen, ensure_ascii=False, indent=2))
    print(f'{resumen["aciertos"]}/{resumen["total"]}; p50={resumen["p50_ms"]} ms')
    return 0 if resumen["aciertos"] / resumen["total"] >= args.min_accuracy else 1


if __name__ == "__main__":
    raise SystemExit(main())
