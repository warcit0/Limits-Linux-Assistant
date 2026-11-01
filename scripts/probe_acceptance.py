"""Recorrido real de objetivos con proveedores configurados y datos desechables."""

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
from modules.orchestrator import Orquestador, normalizar
from modules.task_tools import HerramientasTarea


def main():
    filas = []
    with tempfile.TemporaryDirectory(prefix="limits-aceptacion-") as temporal, mock.patch("modules.memory.get_store") as memoria:
        memoria.return_value.facts_block.return_value = ""
        memoria.return_value.recent_turns.return_value = []
        datos = Path(temporal) / "datos"
        datos.mkdir()
        originales = {"2026-10-10_nota.txt": b"nota de prueba\n", "2026-10-12_ventas.csv": b"total\n45\n"}
        for nombre, contenido in originales.items():
            (datos / nombre).write_bytes(contenido)
        config = Config()
        config.AGENT_TASK_PATH = str(Path(temporal) / "tareas")
        executor = CommandExecutor()
        for nombre, handler in list(executor.action_map.items()):
            @functools.wraps(handler)
            def prohibido(*args, **kwargs):
                raise AssertionError("La sonda solo permite las herramientas de archivos aisladas.")
            executor.action_map[nombre] = prohibido
        llm = LLMEngine(config)
        llm._history_loaded = True
        c = Orquestador(config, executor)
        llamadas = []
        for rol, proveedor in c.proveedores.items():
            consultar = proveedor.consultar
            def observar(*args, _rol=rol, _proveedor=proveedor, _consultar=consultar, **kwargs):
                inicio = time.monotonic()
                try:
                    return _consultar(*args, **kwargs)
                finally:
                    llamadas.append({"rol": _rol, "segundos": round(time.monotonic() - inicio, 2),
                                     "modelo": getattr(_proveedor, "ultimo_modelo", None) or config.OLLAMA_MODEL})
            proveedor.consultar = observar
        antes = c.herramientas.inventario(datos)
        pipeline = make_pipeline(llm, executor, mock.Mock(), TurnGate(), orchestrator=c)
        frases = [
            f"Revisa {datos} y lee los archivos. Recomienda exactamente dos opciones de organización: la primera por fecha y la segunda por extensión. No modifiques nada.",
            "Explícame la segunda opción y cómo se diferencia de la primera.",
            "Prepara un script Python para esa segunda opción. Usa carpetas txt y csv, conserva nombres y contenido. Pruébalo sin aplicar todavía los cambios originales.",
            "procede con esa propuesta",
        ]
        for numero, frase in enumerate(frases, 1):
            inicio = time.monotonic()
            desde = len(llamadas)
            texto = pipeline(frase, speak=False)
            tarea = c.almacen.cargar("local")
            intacto = c.herramientas.inventario(datos) == antes
            checks = {"tarea_valida": tarea.estado in {"terminada", "aprobacion"}}
            if numero < 4:
                checks["originales_intactos"] = intacto
            if numero == 2:
                checks["segunda_opcion_correcta"] = "extension" in normalizar(texto.completo)
                checks["continua_analisis"] = tarea.rol == "analisis"
            if numero == 3:
                checks["script_generado_y_probado"] = bool(tarea.artefactos and tarea.pruebas)
                checks["aprobacion_vigente"] = tarea.estado == "aprobacion" and bool(tarea.pendiente)
            if numero == 4:
                checks["efecto_verificado"] = all((datos / Path(nombre).suffix[1:] / nombre).is_file()
                    and (datos / Path(nombre).suffix[1:] / nombre).read_bytes() == contenido
                    for nombre, contenido in originales.items())
            fila = {"paso": numero, "estado": tarea.estado, "rol": tarea.rol,
                    "consultas": llamadas[desde:],
                    "segundos": round(time.monotonic() - inicio, 2), "checks": checks,
                    "respuesta": str(texto.completo).replace(temporal, "<temporal>"),
                    "ok": all(checks.values())}
            if not fila["ok"]:
                fila["diagnostico"] = json.loads(json.dumps(tarea.historial, ensure_ascii=False).replace(temporal, "<temporal>"))
            filas.append(fila)
            print(json.dumps(fila, ensure_ascii=False), flush=True)
            Path("logs/probe_acceptance_last.json").write_text(json.dumps(
                {"ok": len(filas) == 4 and all(f["ok"] for f in filas), "filas": filas}, ensure_ascii=False, indent=2))
            if not fila["ok"]:
                return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
