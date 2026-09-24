"""Coarse-to-fine A* corridor routing A/B benchmark.

Runs baseline (full-resolution) and coarse-to-fine routing on the same
board and compares per-net wall time, closure rate, path lengths, and
fallback count.

Usage:
    PYTHONPATH=packages/temper-placer/src \
    python scripts/bench_coarse_to_fine.py [--pcb temper.kicad_pcb]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
PCB_PATH = REPO_ROOT / "pcb" / "temper.kicad_pcb"


def format_timing(ms: float) -> str:
    if ms < 1:
        return f"{ms * 1000:.0f}us"
    if ms < 1000:
        return f"{ms:.1f}ms"
    return f"{ms / 1000:.2f}s"


def run_routing(pcb_path: Path, enable_c2f: bool) -> dict[str, Any]:
    """Run Router V6 pipeline and collect per-net metrics."""
    from temper_placer.router_v6.pipeline import RouterV6Pipeline

    t0 = time.perf_counter()
    pipeline = RouterV6Pipeline(
        verbose=False,
        enable_theta_star=False,
        enable_coarse_to_fine=enable_c2f,
    )
    result = pipeline.run(pcb_path)
    wall_ms = (time.perf_counter() - t0) * 1000.0

    pf = result.pathfinding_result
    if pf is None:
        return {"error": "No pathfinding result", "wall_ms": wall_ms}

    per_net_ms: dict[str, float] = {}
    for net_name in pf.routed_paths:
        per_net_ms[net_name] = pf.per_path_latency_ms.get(net_name, 0.0) if pf.per_path_latency_ms else 0.0

    path_lengths: dict[str, float] = {}
    for net_name, rp in pf.routed_paths.items():
        if hasattr(rp, "path_length"):
            path_lengths[net_name] = float(rp.path_length)

    return {
        "wall_ms": wall_ms,
        "routed": len(pf.routed_paths),
        "failed": len(pf.failed_nets),
        "failed_nets": list(pf.failed_nets),
        "completion_rate": pf.completion_rate,
        "per_net_ms": per_net_ms,
        "path_lengths": path_lengths,
        "fallbacks": getattr(pf, "coarse_to_fine_fallbacks", 0),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Coarse-to-fine A* corridor routing A/B benchmark"
    )
    parser.add_argument(
        "--pcb", type=Path, default=PCB_PATH,
        help="Path to .kicad_pcb file (default: pcb/temper.kicad_pcb)",
    )
    parser.add_argument(
        "--output", type=Path, default=None,
        help="Optional JSON output path",
    )
    args = parser.parse_args()

    pcb_path = args.pcb
    if not pcb_path.exists():
        print(f"Error: PCB file not found: {pcb_path}", file=sys.stderr)
        sys.exit(1)

    print(f"PCB: {pcb_path}")
    print()

    print("Running BASELINE (full-resolution A*)...")
    sys.stdout.flush()
    baseline = run_routing(pcb_path, enable_c2f=False)
    if "error" in baseline:
        print(f"  ERROR: {baseline['error']}")
        sys.exit(1)
    print(f"  Wall:   {format_timing(baseline['wall_ms'])}")
    print(f"  Routed: {baseline['routed']}/{baseline['routed'] + baseline['failed']}")
    print()

    print("Running COARSE-TO-FINE (corridor-constrained A*)...")
    sys.stdout.flush()
    c2f = run_routing(pcb_path, enable_c2f=True)
    if "error" in c2f:
        print(f"  ERROR: {c2f['error']}")
        sys.exit(1)
    print(f"  Wall:      {format_timing(c2f['wall_ms'])}")
    print(f"  Routed:    {c2f['routed']}/{c2f['routed'] + c2f['failed']}")
    print(f"  Fallbacks: {c2f['fallbacks']}")
    print()

    # Build comparison table
    all_nets = sorted(set(baseline["per_net_ms"]) | set(c2f["per_net_ms"]))

    print(f"{'Net':<28} {'Baseline':>10} {'C2F':>10} {'Delta':>10} {'Same?':>8}")
    print("-" * 68)

    total_b_ms = 0.0
    total_c_ms = 0.0
    same_count = 0
    routed_both = 0

    for net_name in all_nets:
        b_ms = baseline["per_net_ms"].get(net_name, 0.0)
        c_ms = c2f["per_net_ms"].get(net_name, 0.0)
        total_b_ms += b_ms
        total_c_ms += c_ms

        b_len = baseline["path_lengths"].get(net_name)
        c_len = c2f["path_lengths"].get(net_name)
        same = "N/A"
        if b_len is not None and c_len is not None:
            diff_mm = abs(b_len - c_len)
            same = "Y" if diff_mm < 0.5 else f"{diff_mm:.1f}mm"
            if diff_mm < 0.5:
                same_count += 1
            routed_both += 1

        delta_str = "N/A"
        if b_ms > 0:
            pct = (c_ms - b_ms) / b_ms * 100
            delta_str = f"{pct:+.0f}%"

        name = net_name[:26]
        print(f"{name:<28} {format_timing(b_ms):>10} {format_timing(c_ms):>10} {delta_str:>10} {same:>8}")

    # Summary
    print("-" * 68)
    delta_total = (total_c_ms - total_b_ms) / total_b_ms * 100 if total_b_ms > 0 else 0
    print(f"{'TOTAL':<28} {format_timing(total_b_ms):>10} {format_timing(total_c_ms):>10} {delta_total:+.0f}% {'':>8}")
    print()
    print(f"Total wall-clock: Baseline={format_timing(baseline['wall_ms'])}  C2F={format_timing(c2f['wall_ms'])}")
    print(f"Completion rate:   Baseline={baseline['completion_rate']:.1%}  C2F={c2f['completion_rate']:.1%}")
    print(f"Fallbacks:         {c2f['fallbacks']}")
    print(f"Path lengths match (within 0.5mm): {same_count}/{routed_both}")
    if baseline["failed_nets"]:
        print(f"Baseline failures:  {', '.join(baseline['failed_nets'])}")
    if c2f["failed_nets"]:
        print(f"C2F failures:       {', '.join(c2f['failed_nets'])}")

    if args.output:
        report = {
            "baseline": baseline,
            "coarse_to_fine": c2f,
            "total_baseline_ms": total_b_ms,
            "total_c2f_ms": total_c_ms,
            "delta_pct": round(delta_total, 1),
        }
        args.output.write_text(json.dumps(report, indent=2))
        print(f"\nReport written to {args.output}")


if __name__ == "__main__":
    main()
