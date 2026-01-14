#!/usr/bin/env python3
"""
Run Placement Experiments: Physics vs Analytical.

Executes the router with both strategies and compares metrics.
"""

import subprocess
import json
import time
from pathlib import Path


def run_experiment(mode: str, output_prefix: str) -> dict:
    print(f"\n--- Running Experiment: {mode} ---")

    cmd = [
        "python3",
        "run_router_v6.py",
        "--lazy-theta",
        "--smoothing",
        "--max-nets",
        "20",  # Limit to 20 nets for speed/comparability
        "--placement-mode",
        mode,
        "--metrics",
        f"pcb/metrics_{output_prefix}.json",
        "--output",
        f"pcb/output_{output_prefix}.kicad_pcb",
    ]

    start = time.time()
    try:
        # Run with timeout to prevent hang
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        duration = time.time() - start

        if result.returncode != 0:
            print(f"Experiment failed (Code {result.returncode})")
            print(result.stderr[-500:])
            return {"success": False, "error": result.stderr}

        print(f"Completed in {duration:.1f}s")

        # Load metrics
        with open(f"pcb/metrics_{output_prefix}.json") as f:
            metrics = json.load(f)

        metrics["real_duration"] = duration
        metrics["success"] = True
        return metrics

    except subprocess.TimeoutExpired:
        print("Experiment Timed Out!")
        return {"success": False, "error": "Timeout"}


def main():
    print("Starting Placement Comparison...")

    # 1. Physics (Baseline)
    res_physics = run_experiment("physics", "physics")

    # 2. Analytical (Challenger)
    res_analytical = run_experiment("analytical", "analytical")

    print("\n" + "=" * 40)
    print("COMPARISON RESULTS")
    print("=" * 40)
    print(f"{'Metric':<20} | {'Physics':<10} | {'Analytical':<10}")
    print("-" * 46)

    metrics = [
        "runtime_seconds",
        "success_count",
        "failure_count",
        "completion_rate",
        "escape_vias",
    ]

    for m in metrics:
        v1 = res_physics.get(m, "N/A")
        v2 = res_analytical.get(m, "N/A")

        # Format floats
        if isinstance(v1, float):
            v1 = f"{v1:.2f}"
        if isinstance(v2, float):
            v2 = f"{v2:.2f}"

        print(f"{m:<20} | {v1:<10} | {v2:<10}")

    print("-" * 46)

    # Conclusion
    score_p = res_physics.get("success_count", 0)
    score_a = res_analytical.get("success_count", 0)

    if score_a > score_p:
        print("WINNER: Analytical Placement")
    elif score_p > score_a:
        print("WINNER: Physics Placement")
    else:
        print("TIE (Based on routing success)")


if __name__ == "__main__":
    main()
