#!/usr/bin/env python3
"""Corpus de órdenes → precisión/latencia del router LOCAL (Ollama).

Uso (desde la raíz del repo, con venv + Ollama arriba):
  ./bin/measure-router
  ./bin/measure-router --min-accuracy 0.90
  ./limits-env/bin/python scripts/measure_router.py --limit 5

No ejecuta handlers del sistema: solo llm.process (y bypass desktop_task).
El router es 100% local (Ollama); el grounding forma parte de la medida: una
acción bloqueada cuenta como fallo porque no se ejecutaría.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description="Mide el router de intents")
    parser.add_argument(
        "--corpus",
        default=str(ROOT / "tests" / "corpus_ordenes.json"),
        help="JSON con phrase/action esperada",
    )
    parser.add_argument("--limit", type=int, default=0,
                        help="Solo las primeras N frases (0 = todas)")
    parser.add_argument(
        "--min-accuracy", type=float, default=0.90,
        help="Umbral de precisión (default 0.90). Exit 1 si no se alcanza.",
    )
    args = parser.parse_args()

    corpus = json.loads(Path(args.corpus).read_text(encoding="utf-8"))
    if args.limit > 0:
        corpus = corpus[: args.limit]

    from config import Config
    from modules.app_router import match_app_route
    from modules.desktop_agent import match_desktop_task_route
    from modules.executor import CommandExecutor
    from modules.file_router import match_file_route
    from modules.llm import LLMEngine
    from modules.media_router import match_media_route

    config = Config()
    # Catálogo real (P1): medimos lo mismo que ejecutará el asistente.
    # `confirm`/`cancel` no están en el action_map (los resuelve `execute()`).
    executor = CommandExecutor()
    known = frozenset(executor.action_map) | {"confirm", "cancel"}
    llm = LLMEngine(config, actions=known)

    ok = 0
    rows = []
    print(f"Corpus: {len(corpus)} frases | model={config.OLLAMA_MODEL}")
    print("-" * 72)

    for item in corpus:
        phrase = item["phrase"]
        expected = item["action"]
        t0 = time.perf_counter()
        if match_desktop_task_route(phrase):
            got = "desktop_task"
            via = "keyword"
        elif (route := match_file_route(phrase)):
            # Mismo orden que `main.run_pipeline`: archivos sin LLM.
            got = route["action"]
            via = "file_router"
        elif (route := match_app_route(phrase)):
            got = route["action"]
            via = "app_router"
        elif (route := match_media_route(phrase)):
            got = route["action"]
            via = "media_router"
        else:
            parsed = llm.process(phrase)
            got = parsed.get("action", "")
            via = "llm"
            # Una acción bloqueada por grounding no se ejecuta: cuenta como fallo.
            if parsed.get("grounded") is False:
                via = f"bloqueada:{parsed.get('grounding_reason', '?')}"
        ms = (time.perf_counter() - t0) * 1000
        hit = got == expected and not str(via).startswith("bloqueada")
        if hit:
            ok += 1
        mark = "OK" if hit else "FAIL"
        print(f"[{mark}] {ms:7.0f} ms  expect={expected:20s} got={got:20s} "
              f"({via}) | {phrase}")
        rows.append({"phrase": phrase, "expected": expected, "got": got,
                     "via": via, "ms": round(ms, 1), "ok": hit})

    total = len(corpus) or 1
    accuracy = ok / total
    latencies = sorted(r["ms"] for r in rows)
    p50 = latencies[len(latencies) // 2] if latencies else 0
    p95 = latencies[max(0, int(len(latencies) * 0.95) - 1)] if latencies else 0
    print("-" * 72)
    print(f"Precisión: {ok}/{len(corpus)} ({100 * accuracy:.1f}%) "
          f"[umbral {100 * args.min_accuracy:.0f}%]")
    print(f"Latencia:  p50={p50:.0f} ms  p95={p95:.0f} ms  "
          f"avg={sum(latencies) / total:.0f} ms")

    out = ROOT / "logs" / "measure_router_last.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({
        "accuracy": accuracy,
        "ok": ok,
        "total": len(corpus),
        "min_accuracy": args.min_accuracy,
        "passed_threshold": accuracy + 1e-9 >= args.min_accuracy,
        "p50_ms": p50,
        "p95_ms": p95,
        "ollama_model": config.OLLAMA_MODEL,
        "rows": rows,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Detalle: {out}")

    if accuracy + 1e-9 < args.min_accuracy:
        print(f"FAIL: precisión {accuracy:.1%} < umbral {args.min_accuracy:.0%}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
