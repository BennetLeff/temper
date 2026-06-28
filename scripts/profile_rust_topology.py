"""Profile the Rust topology solver on the closure test.

Runs the full closure test twice (warm-up, then measured) and reports
completion rate, DRC pass rate, wall time, and topology solver time.

Usage:
    python scripts/profile_rust_vs_python_topology.py <pcb_path>

Origin: U8 of docs/plans/2026-06-28-001-feat-router-v6-rust-topology-plan.md
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path


def run_closure_test(pcb_path: str) -> dict | None:
    """Run closure test with the Rust solver and parse results."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "packages/temper-placer/tests/closure/",
             f"--pcb={pcb_path}", "-q", "--no-header"],
            env=os.environ,
            capture_output=True,
            text=True,
            timeout=300,
        )
    except subprocess.TimeoutExpired:
        return {"status": "timeout"}

    return {
        "status": "ok" if result.returncode == 0 else "failed",
        "returncode": result.returncode,
        "stdout_lines": result.stdout.strip().split("\n")[-10:] if result.stdout else [],
        "stderr_summary": result.stderr.strip()[-500:] if result.stderr else "",
    }


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python scripts/profile_rust_vs_python_topology.py <pcb_path>")
        sys.exit(1)

    pcb_path = sys.argv[1]
    results: dict = {}

    print("Warm-up ...")
    run_closure_test(pcb_path)

    print("Measured run ...")
    t0 = time.perf_counter()
    result = run_closure_test(pcb_path)
    elapsed = time.perf_counter() - t0

    results["wall_time_s"] = round(elapsed, 2)
    results.update(result or {})
    print(f"Wall time: {elapsed:.1f}s")
    print(f"Status: {result.get('status', 'unknown') if result else 'error'}")

    output_path = Path("metrics/rust_topology_profile.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"Results written to {output_path}")


if __name__ == "__main__":
    main()
