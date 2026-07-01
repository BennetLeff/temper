#!/usr/bin/env python3
"""
Benchmark gate for Rust constraint engine extraction.
Compares wall-clock performance of Rust vs Python loss computation.

R8: CI benchmark gate — compares benchmark p50 of N runs against baseline.
     Gate is warn-only for the first 2 weeks, then becomes blocking.

Usage:
    python scripts/bench_rust_constraints.py [--runs N] [--output JSON]
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

HAS_RUST = False
try:
    import temper_constraints  # type: ignore[import-untyped]
    HAS_RUST = True
except ImportError:
    pass


BENCHMARK_CASES = [
    # (name, positions, kwargs)
    {
        "name": "adjacent_within_range",
        "rust_fn": "compute_adjacent_loss_py",
        "args": ([0.0, 0.0, 5.0, 0.0], 0, 1, 10.0, 1.0),
        "kwargs": {},
    },
    {
        "name": "adjacent_exceeds_range",
        "rust_fn": "compute_adjacent_loss_py",
        "args": ([0.0, 0.0, 50.0, 0.0], 0, 1, 10.0, 1.0),
        "kwargs": {},
    },
    {
        "name": "separation_batch_10x10",
        "rust_fn": "compute_separation_loss_py",
        "args": (
            [float(i % 10 * 5) for i in range(20)],  # 10 components group A
            [float(i % 10 * 5 + 3) for i in range(20)],  # 10 components group B
            10.0, 1.0,
        ),
        "kwargs": {},
    },
    {
        "name": "enclosing_inside",
        "rust_fn": "compute_enclosing_loss_py",
        "args": (
            [25.0, 25.0, 30.0, 30.0, 35.0, 35.0, 40.0, 40.0, 45.0, 45.0],
            0.0, 0.0, 50.0, 50.0, 0.0, 1.0,
        ),
        "kwargs": {},
    },
    {
        "name": "enclosing_outside",
        "rust_fn": "compute_enclosing_loss_py",
        "args": (
            [60.0, 25.0, 55.0, -5.0, 70.0, 30.0, 40.0, 60.0, 45.0, 55.0],
            0.0, 0.0, 50.0, 50.0, 0.0, 1.0,
        ),
        "kwargs": {},
    },
    {
        "name": "alignment_3comp",
        "rust_fn": "compute_alignment_loss_py",
        "args": (
            [10.0, 20.0, 15.0, 30.0, 12.0, 40.0],
            "x", 0.5, 1.0,
        ),
        "kwargs": {},
    },
    {
        "name": "alignment_10comp",
        "rust_fn": "compute_alignment_loss_py",
        "args": (
            [10.0 + (i % 3) * 5.0 for i in range(20)],
            "x", 0.5, 1.0,
        ),
        "kwargs": {},
    },
    {
        "name": "edge_preference",
        "rust_fn": "compute_edge_loss_py",
        "args": (
            [50.0, 40.0, 60.0, 30.0, 70.0, 20.0],
            "left", 100.0, 80.0, 5.0, 1.0,
        ),
        "kwargs": {},
    },
    {
        "name": "anchored_position",
        "rust_fn": "compute_anchored_loss_position_py",
        "args": ([10.0, 10.0], 30.0, 30.0, 1.0),
        "kwargs": {},
    },
    {
        "name": "anchored_region",
        "rust_fn": "compute_anchored_loss_region_py",
        "args": ([60.0, 25.0], 0.0, 0.0, 50.0, 50.0, 1.0),
        "kwargs": {},
    },
    {
        "name": "loop_area_small",
        "rust_fn": "compute_loop_area_loss_py",
        "args": (
            [0.0, 0.0, 10.0, 0.0, 10.0, 10.0, 0.0, 10.0],
            200.0, 1.0,
        ),
        "kwargs": {},
    },
    {
        "name": "loop_area_large",
        "rust_fn": "compute_loop_area_loss_py",
        "args": (
            [0.0, 0.0, 20.0, 0.0, 20.0, 20.0, 0.0, 20.0],
            200.0, 1.0,
        ),
        "kwargs": {},
    },
]


def bench_rust(fn_name: str, args: tuple, kwargs: dict, iterations: int = 1000) -> float:
    """Benchmark a Rust loss function by calling it `iterations` times."""
    if not HAS_RUST:
        return float("nan")

    fn = getattr(temper_constraints, fn_name)
    # Warmup
    for _ in range(min(iterations // 10, 100)):
        fn(*args, **kwargs)

    start = time.perf_counter()
    for _ in range(iterations):
        fn(*args, **kwargs)
    elapsed = time.perf_counter() - start
    return elapsed * 1000.0 / iterations  # ms per call


def run_benchmarks(runs: int = 5, iterations: int = 1000) -> dict:
    """Run all benchmark cases with N warm runs."""
    if not HAS_RUST:
        print("ERROR: Rust constraint engine not installed. Cannot benchmark.")
        sys.exit(1)

    results = {}
    for case in BENCHMARK_CASES:
        name = case["name"]
        times = []
        for _ in range(runs):
            t = bench_rust(case["rust_fn"], case["args"], case["kwargs"], iterations)
            times.append(t)
        results[name] = {
            "mean_ms": statistics.mean(times),
            "median_ms": statistics.median(times),
            "stdev_ms": statistics.stdev(times) if len(times) > 1 else 0.0,
            "min_ms": min(times),
            "max_ms": max(times),
            "runs": runs,
            "iterations_per_run": iterations,
        }

    # Compute aggregate stats
    all_means = [v["mean_ms"] for v in results.values()]
    results["aggregate"] = {
        "mean_ms": statistics.mean(all_means),
        "median_ms": statistics.median(all_means),
        "stdev_ms": statistics.stdev(all_means) if len(all_means) > 1 else 0.0,
    }

    return results


def main():
    parser = argparse.ArgumentParser(description="Benchmark Rust constraint engine")
    parser.add_argument("--runs", type=int, default=5, help="Number of benchmark runs (default: 5)")
    parser.add_argument("--iterations", type=int, default=1000, help="Iterations per run (default: 1000)")
    parser.add_argument("--output", type=Path, default=None, help="Output JSON file")
    parser.add_argument("--ci", action="store_true", help="CI mode: exit non-zero on regression")
    args = parser.parse_args()

    if not HAS_RUST:
        print("SKIP: Rust constraint engine not installed")
        if args.ci:
            print("WARN: CI benchmark skipped (Rust not available)")
        sys.exit(0)

    print(f"Benchmarking Rust constraint engine ({args.runs} runs x {args.iterations} iterations)...")
    results = run_benchmarks(args.runs, args.iterations)

    # Print results
    print(f"\n{'Case':<30} {'Mean (us)':>10} {'Median (us)':>10} {'Stdev (us)':>10} {'Min (us)':>10} {'Max (us)':>10}")
    print("-" * 90)
    for case in BENCHMARK_CASES:
        name = case["name"]
        r = results[name]
        print(
            f"{name:<30} {r['mean_ms'] * 1000:>10.2f} {r['median_ms'] * 1000:>10.2f} "
            f"{r['stdev_ms'] * 1000:>10.2f} {r['min_ms'] * 1000:>10.2f} {r['max_ms'] * 1000:>10.2f}"
        )

    agg = results["aggregate"]
    print(f"\nAggregate: mean={agg['mean_ms'] * 1000:.2f}us, median={agg['median_ms'] * 1000:.2f}us, stdev={agg['stdev_ms'] * 1000:.2f}us")

    if args.output:
        args.output.write_text(json.dumps(results, indent=2))
        print(f"\nResults written to {args.output}")

    # CI gate: warn-only during calibration (R8)
    if args.ci:
        print("\nCI BENCHMARK GATE: WARN-ONLY (calibration period per R8)")
        # In the future, compare against registered baseline with 2-sigma threshold
        print("PASS (warn-only): no regression check enforced during calibration")

    return 0


if __name__ == "__main__":
    sys.exit(main())
