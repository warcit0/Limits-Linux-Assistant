"""Reproduce las 32 órdenes en el pipeline nuevo sin voz ni efectos reales."""

from pathlib import Path
import functools
import json
import sys
import tempfile
import time
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import Config
from main import make_pipeline
from modules.executor import CommandExecutor
from modules.gateway import TurnGate
from modules.llm import LLMEngine
from modules.orchestrator import Orquestador, decision_confirmacion


def main():
    base = Path(__file__).resolve().parent.parent
    corpus = json.loads((base / "tests/corpus_ordenes.json").read_text())
    filas, acciones = [], []
    config = Config()
    config.AGENT_SEMANTIC = False
    config.KNOWLEDGE_ENABLED = False
    # Solo el LLM local es real. Ningún handler ni TTS tiene efectos.
    with tempfile.TemporaryDirectory(prefix="limits-pipeline-") as temporal, mock.patch("modules.memory.get_store") as memoria:
        memoria.return_value.facts_block.return_value = ""
        memoria.return_value.recent_turns.return_value = []
        config.AGENT_TASK_PATH = temporal
        executor = CommandExecutor()
        for nombre, handler in list(executor.action_map.items()):
            @functools.wraps(handler)
            def sin_efectos(*args, **kwargs):
                return "Validación sin efectos reales."
            executor.action_map[nombre] = sin_efectos
        ejecutar = executor.execute
        def observar(parsed):
            acciones.append({"action": parsed.get("action"), "grounded": parsed.get("grounded", True)})
            return ejecutar(parsed)
        executor.execute = observar
        llm = LLMEngine(config, actions=frozenset(executor.action_map) | {"confirm", "cancel"})
        coordinador = Orquestador(config, executor)
        pipeline = make_pipeline(llm, executor, mock.Mock(), TurnGate(), orchestrator=coordinador)
        for caso in corpus:
            acciones.clear()
            inicio = time.monotonic()
            texto = pipeline(caso["phrase"], speak=False)
            actual = acciones[-1]["action"] if acciones else {"confirmar": "confirm", "cancelar": "cancel"}.get(decision_confirmacion(caso["phrase"]))
            correcto = actual == caso["action"] and all(a["grounded"] for a in acciones)
            filas.append({"frase": caso["phrase"], "esperado": caso["action"], "obtenido": actual,
                          "ok": correcto, "ms": round((time.monotonic() - inicio) * 1000)})
            print(f'{"OK" if correcto else "FALLO"} {actual}: {caso["phrase"]}', flush=True)
    resultado = {"total": len(filas), "aciertos": sum(f["ok"] for f in filas), "filas": filas,
                 "efectos_reales": False, "modo": "objetivos"}
    destino = base / "logs/probe_pipeline_last.json"
    destino.write_text(json.dumps(resultado, ensure_ascii=False, indent=2))
    print(f'{resultado["aciertos"]}/{resultado["total"]}')
    return 0 if resultado["aciertos"] == resultado["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
