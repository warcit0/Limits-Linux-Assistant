#!/usr/bin/env python3
"""Corpus de órdenes → precisión/latencia del LLM router (Groq/Ollama).

Uso (desde la raíz del repo, con venv):
  ./bin/measure-router
  ./limits-env/bin/python scripts/measure_router.py --limit 5

No ejecuta handlers del sistema: solo llm.process y compara `action`.
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
    args = parser.parse_args()

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
    print(f"Corpus: {len(corpus)} frases | priority={config.LLM_PRIORITY}")
    print("-" * 72)

    for item in corpus:
        phrase = item["phrase"]
        expected = item["action"]
        t0 = time.perf_counter()
        # Misma prioridad que make_pipeline: bypass desktop_task por keywords
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
    latencies = [r["ms"] for r in rows]
    latencies.sort()
    p50 = latencies[len(latencies) // 2] if latencies else 0
    p95 = latencies[max(0, int(len(latencies) * 0.95) - 1)] if latencies else 0
    print("-" * 72)
    print(f"Precisión: {ok}/{len(corpus)} ({100 * ok / total:.1f}%)")
    print(f"Latencia:  p50={p50:.0f} ms  p95={p95:.0f} ms  "
          f"avg={sum(latencies) / total:.0f} ms")

    out = ROOT / "logs" / "measure_router_last.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({
        "accuracy": ok / total,
        "ok": ok,
        "total": len(corpus),
        "p50_ms": p50,
        "p95_ms": p95,
        "rows": rows,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Detalle: {out}")
    return 0 if ok == len(corpus) else 1


if __name__ == "__main__":
    raise SystemExit(main())
