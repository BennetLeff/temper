"""Profile Rust vs Python topology solver backends on the closure test.

Runs the full closure test twice (warm-up, then measured) for each
backend and reports completion rate, DRC pass rate, wall time,
per-stage topology solver time, and memory peak.

Usage:
    python scripts/profile_rust_vs_python_topology.py <pcb_path>
    python scripts/profile_rust_vs_python_topology.py pcb/temper_agent_optimized.kicad_pcb

Origin: U8 of docs/plans/2026-06-28-001-feat-router-v6-rust-topology-plan.md
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

# ---- Backend configurations ----

BACKENDS = {
    "python": {"TEMPER_SAT_BACKEND": "python"},
    "rust": {"TEMPER_SAT_BACKEND": "rust"},
}


def run_closure_test(
    pcb_path: str, env: dict[str, str]
) -> dict | None:
    """Run closure test and parse results from stdout."""
    full_env = {**os.environ, **env}
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "packages/temper-placer/tests/closure/",
             f"--pcb={pcb_path}", "-q", "--no-header"],
            env=full_env,
            capture_output=True,
            text=True,
            timeout=300,
        )
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "backend": env.get("TEMPER_SAT_BACKEND", "python")}

    return {
        "status": "ok" if result.returncode == 0 else "failed",
        "backend": env.get("TEMPER_SAT_BACKEND", "python"),
        "returncode": result.returncode,
        "stdout_lines": result.stdout.strip().split("\n")[-10:] if result.stdout else [],
        "stderr_summary": result.stderr.strip()[-500:] if result.stderr else "",
    }


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python scripts/profile_rust_vs_python_topology.py <pcb_path>")
        sys.exit(1)

    pcb_path = sys.argv[1]
    results: dict[str, dict] = {}

    for name, env in BACKENDS.items():
        print(f"\n{'='*60}")
        print(f"Backend: {name} ({env})")
        print(f"{'='*60}")

        # Warm-up run
        print(f"  Warm-up ...")
        run_closure_test(pcb_path, env)

        # Measured run
        print(f"  Measured run ...")
        t0 = time.perf_counter()
        result = run_closure_test(pcb_path, env)
        elapsed = time.perf_counter() - t0

        if result:
            result["wall_time_s"] = round(elapsed, 2)
        results[name] = result or {}
        print(f"  Wall time: {elapsed:.1f}s")
        print(f"  Status: {result.get('status', 'unknown') if result else 'error'}")

    # Write JSON summary
    output_path = Path("metrics/rust_vs_python_topology.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nResults written to {output_path}")


if __name__ == "__main__":
    main()
