#!/usr/bin/env python3
"""Corpus de órdenes → precisión/latencia del router LOCAL (Ollama).

Uso (desde la raíz del repo, con venv + Ollama arriba):
  ./bin/measure-router
  ./bin/measure-router --min-accuracy 0.90
  ./limits-env/bin/python scripts/measure_router.py --limit 5

No ejecuta handlers del sistema: solo llm.process (y bypass desktop_task).
Por defecto fuerza LLM_PRIORITY=local (Groq fuera del hot path del router).
"""

from __future__ import annotations

import argparse
import json
import os
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
    parser.add_argument(
        "--allow-cloud", action="store_true",
        help="No forzar LLM_PRIORITY=local (usa .env tal cual)",
    )
    args = parser.parse_args()

    if not args.allow_cloud:
        os.environ["LLM_PRIORITY"] = "local"

    corpus = json.loads(Path(args.corpus).read_text(encoding="utf-8"))
    if args.limit > 0:
        corpus = corpus[: args.limit]

    from config import Config
    from modules.desktop_agent import match_desktop_task_route
    from modules.llm import LLMEngine

    config = Config()
    llm = LLMEngine(config)

    ok = 0
    rows = []
    print(f"Corpus: {len(corpus)} frases | priority={config.LLM_PRIORITY} "
          f"| model={config.OLLAMA_MODEL}")
    print("-" * 72)

    for item in corpus:
        phrase = item["phrase"]
        expected = item["action"]
        t0 = time.perf_counter()
        if match_desktop_task_route(phrase):
            got = "desktop_task"
            via = "keyword"
        else:
            parsed = llm.process(phrase)
            got = parsed.get("action", "")
            via = "llm"
        ms = (time.perf_counter() - t0) * 1000
        hit = got == expected
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
        "priority": config.LLM_PRIORITY,
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
