#!/usr/bin/env python3
"""
Phase 13: Router Benchmarking Suite.

Compares Router V6/V7 performance against a "Gold Standard" (Human Routed) board.
"""

import sys
import subprocess
import json
import time
from pathlib import Path
from temper_placer.io.kicad_writer import strip_routing, get_routing_statistics
from temper_placer.io.kicad_parser import parse_kicad_pcb_v6


def get_detailed_metrics(pcb_path: Path) -> dict:
    """Calculate detailed metrics (length, vias) from a PCB file."""
    # kicad_writer.get_routing_statistics gives counts.
    # We want length too.
    stats = get_routing_statistics(pcb_path)

    # Calculate length manually
    total_length = 0.0
    try:
        # We need to parse it to get geometry
        # parse_kicad_pcb_v6 parses traces if updated in Phase 5?
        # Yes, I added 'tracks' to ParsedPCB.
        pcb = parse_kicad_pcb_v6(pcb_path)
        if hasattr(pcb, "tracks") and pcb.tracks:
            for track in pcb.tracks:
                l = (
                    (track.end[0] - track.start[0]) ** 2 + (track.end[1] - track.start[1]) ** 2
                ) ** 0.5
                total_length += l
    except Exception as e:
        print(f"Warning: Failed to calculate length: {e}")

    stats["length_mm"] = total_length
    return stats


def run_benchmark(gold_path: Path):
    if not gold_path.exists():
        print(f"Error: Gold file {gold_path} not found")
        sys.exit(1)

    print(f"Benchmarking against {gold_path.name}...")

    # 1. Analyze Gold
    print("  Analyzing Gold Standard...")
    gold_metrics = get_detailed_metrics(gold_path)

    # 2. Strip
    stripped_path = gold_path.with_name(f"{gold_path.stem}_stripped.kicad_pcb")
    print(f"  Stripping routing to {stripped_path.name}...")
    strip_routing(gold_path, stripped_path, keep_zones=True, keep_fills=False)

    # 3. Route
    output_path = gold_path.with_name(f"{gold_path.stem}_autorouted.kicad_pcb")
    metrics_path = gold_path.with_name(f"{gold_path.stem}_metrics.json")

    print("  Running Router V6...")
    start_time = time.time()

    # Call run_router_v6.py as subprocess
    cmd = [
        "python3",
        "run_router_v6.py",
        "--pcb",
        str(stripped_path),
        "--output",
        str(output_path),
        "--metrics",
        str(metrics_path),
        "--lazy-theta",
        "--smoothing",
        # "--negotiated", # Optional: Enable Phase 8
        "--no-legalize",  # Don't move components for benchmark (preserve placement)
    ]

    try:
        # Set timeout 10m
        subprocess.run(cmd, check=True, timeout=600, capture_output=True)
    except subprocess.CalledProcessError as e:
        print("  Router Failed!")
        print(e.stderr.decode())
        return
    except subprocess.TimeoutExpired:
        print("  Router Timed Out!")
        return

    duration = time.time() - start_time
    print(f"  Routing Complete in {duration:.1f}s")

    # 4. Analyze Auto
    auto_metrics = get_detailed_metrics(output_path)
    auto_metrics["duration"] = duration

    # 5. Compare
    print("\n" + "=" * 60)
    print(f"BENCHMARK RESULTS: {gold_path.stem}")
    print("=" * 60)
    print(f"{'Metric':<20} | {'Human (Gold)':<15} | {'Auto (V6)':<15} | {'Delta':<10}")
    print("-" * 66)

    for key in ["length_mm", "vias", "traces"]:
        val_g = gold_metrics.get(key, 0)
        val_a = auto_metrics.get(key, 0)

        if key == "length_mm":
            vg_str = f"{val_g:.1f} mm"
            va_str = f"{val_a:.1f} mm"
        else:
            vg_str = str(val_g)
            va_str = str(val_a)

        # Delta
        if val_g > 0:
            delta = (val_a - val_g) / val_g * 100
            delta_str = f"{delta:+.1f}%"
        else:
            delta_str = "N/A"

        print(f"{key:<20} | {vg_str:<15} | {va_str:<15} | {delta_str:<10}")

    print("-" * 66)
    print(f"Duration             | N/A             | {duration:.1f} s         |")

    # Score
    # Simple score: Lower length is better. Lower vias is better.
    # But completion is king. We assume 100% completion (checked by router logs).


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("gold_pcb", type=Path, help="Path to fully routed .kicad_pcb")
    args = parser.parse_args()

    run_benchmark(args.gold_pcb)
