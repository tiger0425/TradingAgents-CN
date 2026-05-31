#!/usr/bin/env python3
"""Benchmark comparing fan_out_enabled=False vs True for the same ticker.

Usage:
    python scripts/benchmark_fanout.py

Requires:
    - API keys configured in .env (OPENAI_API_KEY or DEEPSEEK_API_KEY)
    - All tradingagents dependencies installed

Expected timing (estimate):
    Serial mode:   ~270s  (4 analysts run sequentially)
    Parallel mode: ~150s  (4 analysts run concurrently)
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tradingagents.bootstrap import bootstrap
from tradingagents.graph.executor import GraphExecutor
from tradingagents.planner.schemas import Context, Trigger

TICKER = "000001"


def run_benchmark(
    fan_out_enabled: bool,
    label: str,
    planner,
    executor_ref: GraphExecutor,
    plan: dict,
    trigger: Trigger,
    context: Context,
) -> float:
    """Run analysis with given fan_out setting and return elapsed seconds."""
    bench_executor = GraphExecutor(
        quick_thinking_llm=executor_ref.quick_llm,
        deep_thinking_llm=executor_ref.deep_llm,
        tool_nodes=executor_ref.tool_nodes,
        max_debate_rounds=executor_ref.max_debate_rounds,
        max_risk_rounds=executor_ref.max_risk_rounds,
        max_recur_limit=executor_ref.max_recur_limit,
        fan_out_enabled=fan_out_enabled,
        enable_checkpoint=False,
        data_dir="",
    )
    print(f"  [{label}] Starting analysis of {TICKER} ...")
    start = time.time()
    try:
        result = bench_executor.execute(plan, trigger, context)
        elapsed = time.time() - start
        has_report = bool(result.get("final_report"))
        status = "✓" if has_report else "⚠ (empty report)"
        print(f"  [{label}] {status} — {elapsed:.1f}s")
        return elapsed
    except Exception as exc:
        elapsed = time.time() - start
        print(f"  [{label}] ✗ FAILED after {elapsed:.1f}s — {exc}")
        return elapsed


def main() -> int:
    print("=" * 60)
    print("  Fan-Out Performance Benchmark")
    print("=" * 60)

    # ---- 1. Bootstrap ----
    print("\n[1/3] Bootstrapping system ...")
    result = bootstrap()
    if result is None:
        print("ERROR: bootstrap() returned None — check API keys in .env")
        return 1
    planner, executor, kb, pm = result
    print("      OK")

    # ---- 2. Plan once (same plan used for both runs) ----
    print("[2/3] Creating analysis plan ...")
    trigger = Trigger(
        type="customer_message",
        message=f"分析{TICKER}",
        task="",
    )
    context = Context(
        user_id="benchmark",
        ticker=TICKER,
        industry="",
        portfolio_summary="",
    )
    plan = planner.plan(trigger, context)
    intent = plan.get("intent", "?")
    steps = len(plan.get("workflow", []))
    print(f"      intent={intent}, steps={steps}")

    # ---- 3. Run benchmarks ----
    print("[3/3] Running benchmarks ...\n")

    t_serial = run_benchmark(
        fan_out_enabled=False,
        label="SERIAL  (fan_out=false)",
        planner=planner,
        executor_ref=executor,
        plan=plan,
        trigger=trigger,
        context=context,
    )
    t_parallel = run_benchmark(
        fan_out_enabled=True,
        label="PARALLEL (fan_out=true)",
        planner=planner,
        executor_ref=executor,
        plan=plan,
        trigger=trigger,
        context=context,
    )

    # ---- Results ----
    print()
    print("=" * 60)
    print("  RESULTS")
    print("=" * 60)
    print(f"  Serial mode:    {t_serial:>8.1f}s")
    print(f"  Parallel mode:  {t_parallel:>8.1f}s")

    if t_serial > 0 and t_parallel > 0:
        speedup = t_serial / t_parallel
        print(f"  Speedup:        {speedup:>8.2f}x")
        if speedup > 1.0:
            print(f"  Time saved:     {t_serial - t_parallel:>8.1f}s  ({speedup:.2f}x faster)")
        else:
            print(f"  NOTE: Parallel mode was {1/speedup:.2f}x slower — check for bottlenecks")
    else:
        print("  (one or both runs returned 0 — results unreliable)")

    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
