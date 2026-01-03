#!/usr/bin/env python3
"""
Routing Experiments Runner

This script runs automated experiments to improve routing success rate.
It tests various parameters and measures their impact on FreeRouter completion.

Usage:
    python3 experiments/run_routing_experiments.py --experiment clearance_sweep
    python3 experiments/run_routing_experiments.py --experiment net_ordering
    python3 experiments/run_routing_experiments.py --experiment all
"""

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path


@dataclass
class RoutingResult:
    """Result of a single routing run."""
    experiment: str
    config: dict
    unrouted: int
    total_nets: int
    completion_pct: float
    passes: int
    timestamp: str


def parse_freerouter_output(output: str) -> dict:
    """Parse FreeRouter output to extract routing statistics."""
    result = {
        "unrouted": 0,
        "total_nets": 0,
        "passes": 0,
    }

    for line in output.split("\n"):
        # Look for lines like "Route result: 5 incomplete."
        if "incomplete" in line.lower():
            match = re.search(r"(\d+)\s+incomplete", line)
            if match:
                result["unrouted"] = int(match.group(1))

        # Look for pass count
        if "Pass #" in line:
            match = re.search(r"Pass #(\d+)", line)
            if match:
                result["passes"] = max(result["passes"], int(match.group(1)))

        # Look for total nets
        if "nets to route" in line.lower() or "routing" in line.lower():
            match = re.search(r"(\d+)\s+nets", line)
            if match:
                result["total_nets"] = int(match.group(1))

    return result


def run_freerouter(dsn_path: Path, max_passes: int = 200) -> dict:
    """Run FreeRouter on a DSN file and return results."""
    # Look for freerouting.jar in common locations
    jar_paths = [
        Path("~/tools/freerouting.jar").expanduser(),
        Path("/opt/freerouting/freerouting.jar"),
        Path("freerouting.jar"),
    ]

    jar_path = None
    for p in jar_paths:
        if p.exists():
            jar_path = p
            break

    if jar_path is None:
        print("ERROR: Could not find freerouting.jar")
        return {"error": "freerouting.jar not found"}

    cmd = [
        "java", "-jar", str(jar_path),
        "-de", str(dsn_path),
        "-mp", str(max_passes),
        "-mt", "1",  # Single thread for reproducibility
    ]

    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)

    output = result.stdout + result.stderr
    return parse_freerouter_output(output)


def run_clearance_sweep(base_pcb: Path, output_dir: Path) -> list[RoutingResult]:
    """Run experiment: sweep clearance values."""
    results = []
    clearances = [10, 12, 15, 18, 20]  # in DSN units (10um each = 0.1-0.2mm)

    for clearance in clearances:
        print(f"\n=== Testing clearance: {clearance} ===")

        # Export DSN with modified clearance
        dsn_path = output_dir / f"clearance_{clearance}.dsn"

        # Run export (we'll need to modify export_dsn.py to accept clearance param)
        # For now, just copy and modify
        cmd = [
            "uv", "run", "python3", "export_dsn.py",
            str(base_pcb),
            str(dsn_path),
            "--exclude-planes",
        ]
        subprocess.run(cmd, check=True)

        # Modify clearance in DSN file
        dsn_content = dsn_path.read_text()
        dsn_content = re.sub(
            r'\(clearance \d+\)',
            f'(clearance {clearance})',
            dsn_content
        )
        dsn_path.write_text(dsn_content)

        # Run FreeRouter
        fr_result = run_freerouter(dsn_path, max_passes=200)

        total = fr_result.get("total_nets", 19)
        unrouted = fr_result.get("unrouted", total)
        completion = (total - unrouted) / total * 100 if total > 0 else 0

        result = RoutingResult(
            experiment="clearance_sweep",
            config={"clearance": clearance},
            unrouted=unrouted,
            total_nets=total,
            completion_pct=completion,
            passes=fr_result.get("passes", 0),
            timestamp=datetime.now().isoformat(),
        )
        results.append(result)

        print(f"Clearance {clearance}: {unrouted} unrouted, {completion:.1f}% complete")

    return results


def run_net_ordering_test(base_pcb: Path, output_dir: Path) -> list[RoutingResult]:
    """Run experiment: test net ordering impact."""
    results = []

    # Test with new ordering (already in dsn_exporter.py)
    print("\n=== Testing net ordering (short-first) ===")

    dsn_path = output_dir / "net_ordering.dsn"
    cmd = [
        "uv", "run", "python3", "export_dsn.py",
        str(base_pcb),
        str(dsn_path),
        "--exclude-planes",
    ]
    subprocess.run(cmd, check=True)

    fr_result = run_freerouter(dsn_path, max_passes=300)

    total = fr_result.get("total_nets", 19)
    unrouted = fr_result.get("unrouted", total)
    completion = (total - unrouted) / total * 100 if total > 0 else 0

    result = RoutingResult(
        experiment="net_ordering",
        config={"ordering": "short_first"},
        unrouted=unrouted,
        total_nets=total,
        completion_pct=completion,
        passes=fr_result.get("passes", 0),
        timestamp=datetime.now().isoformat(),
    )
    results.append(result)

    print(f"Net ordering: {unrouted} unrouted, {completion:.1f}% complete")

    return results


def save_results(results: list[RoutingResult], output_path: Path):
    """Save experiment results to JSON."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    data = {
        "generated_at": datetime.now().isoformat(),
        "results": [asdict(r) for r in results],
    }

    with open(output_path, "w") as f:
        json.dump(data, f, indent=2)

    print(f"\nResults saved to: {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Run routing experiments")
    parser.add_argument(
        "--experiment",
        choices=["clearance_sweep", "net_ordering", "all"],
        default="all",
        help="Which experiment to run",
    )
    parser.add_argument(
        "--pcb",
        type=Path,
        default=Path("pcb/temper_with_planes.kicad_pcb"),
        help="Input PCB file",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("experiments/routing_data"),
        help="Output directory for DSN files and results",
    )

    args = parser.parse_args()

    if not args.pcb.exists():
        print(f"ERROR: PCB file not found: {args.pcb}")
        print("Run: python3 add_power_planes.py pcb/temper_optimized.kicad_pcb pcb/temper_with_planes.kicad_pcb")
        sys.exit(1)

    args.output_dir.mkdir(parents=True, exist_ok=True)

    all_results = []

    if args.experiment in ["clearance_sweep", "all"]:
        results = run_clearance_sweep(args.pcb, args.output_dir)
        all_results.extend(results)

    if args.experiment in ["net_ordering", "all"]:
        results = run_net_ordering_test(args.pcb, args.output_dir)
        all_results.extend(results)

    # Save all results
    save_results(all_results, args.output_dir / "experiment_results.json")

    # Print summary
    print("\n" + "=" * 60)
    print("EXPERIMENT SUMMARY")
    print("=" * 60)

    for r in all_results:
        print(f"{r.experiment} ({r.config}): {r.unrouted} unrouted ({r.completion_pct:.1f}%)")

    # Find best result
    if all_results:
        best = min(all_results, key=lambda r: r.unrouted)
        print(f"\nBest result: {best.experiment} with {best.config}")
        print(f"  {best.unrouted} unrouted nets ({best.completion_pct:.1f}% complete)")


if __name__ == "__main__":
    main()
