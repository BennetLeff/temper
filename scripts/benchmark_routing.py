#!/usr/bin/env python3.11
"""
Benchmark routing pipeline performance.

This script captures baseline metrics for the MVP3 routing pipeline:
- Net completion rate
- A* timeout rate
- DRC violation counts by type
- Total routing time

Usage:
    python scripts/benchmark_routing.py [--output metrics/baseline_routing.json]
    python scripts/benchmark_routing.py --compare metrics/baseline_routing.json
"""

import argparse
import json
import subprocess
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

# Add packages to path
sys.path.insert(0, str(Path(__file__).parent.parent / "packages" / "temper-placer" / "src"))


def get_git_commit() -> str:
    """Get current git commit hash."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        return "unknown"


def run_pipeline(input_pcb: str, output_dir: str = "/tmp") -> dict:
    """
    Run MVP3 pipeline and collect routing metrics.

    Returns dict with:
        - elapsed_seconds
        - nets: {total, attempted, completed, skipped_plane, failed}
        - routes: count and by-layer breakdown
        - vias: count
    """
    from temper_placer.pipeline.mvp3_runner import MVP3Runner, MVP3Config

    output_path = Path(output_dir) / "benchmark_output.kicad_pcb"
    config_path = Path(__file__).parent.parent / "configs" / "temper_deterministic_config.yaml"

    runner = MVP3Runner(
        pcb_path=Path(input_pcb),
        config_path=config_path,
        output_path=output_path,
        mvp3_config=MVP3Config(),
    )

    start = time.time()
    result = runner.run()
    elapsed = time.time() - start

    metrics = {
        "elapsed_seconds": round(elapsed, 2),
        "success": result.success,
        "error": result.error,
        "nets": {
            "total": result.total_nets,
            "routed": result.nets_routed,
            "completion_rate": round(result.nets_routed / max(result.total_nets, 1), 3),
        },
        "components": {
            "total": result.total_components,
            "placed": result.components_placed,
        },
        "output_file": str(output_path),
    }

    return metrics


def run_drc(pcb_path: str) -> dict:
    """
    Run KiCad DRC and collect violation counts.

    Returns dict with:
        - total: total violation count
        - by_type: {type: count} breakdown
        - actionable: count of non-cosmetic violations
    """
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        drc_path = f.name

    try:
        # First fill zones
        filled_path = pcb_path.replace(".kicad_pcb", "_filled.kicad_pcb")
        fill_script = Path(__file__).parent / "fill_zones.py"

        if fill_script.exists():
            subprocess.run(
                ["python", str(fill_script), pcb_path, filled_path],
                capture_output=True,
                check=True,
            )
            drc_target = filled_path
        else:
            drc_target = pcb_path

        # Run DRC
        subprocess.run(
            [
                "kicad-cli",
                "pcb",
                "drc",
                drc_target,
                "--output",
                drc_path,
                "--format",
                "json",
                "--severity-all",
            ],
            capture_output=True,
            check=True,
        )

        with open(drc_path) as f:
            drc = json.load(f)

        violations = drc.get("violations", [])
        by_type = Counter(v.get("type", "unknown") for v in violations)

        # Expected/cosmetic violations we don't count as actionable
        expected_types = {
            "lib_footprint_issues",
            "silk_overlap",
            "silk_over_copper",
            "silk_edge_clearance",
        }

        actionable = [v for v in violations if v.get("type") not in expected_types]

        return {
            "total": len(violations),
            "actionable": len(actionable),
            "by_type": dict(by_type),
            "expected_types_excluded": list(expected_types),
        }

    except subprocess.CalledProcessError as e:
        return {
            "total": -1,
            "actionable": -1,
            "error": f"DRC failed: {e.stderr.decode() if e.stderr else str(e)}",
            "by_type": {},
        }
    except FileNotFoundError:
        return {
            "total": -1,
            "actionable": -1,
            "error": "kicad-cli not found",
            "by_type": {},
        }
    finally:
        Path(drc_path).unlink(missing_ok=True)


def analyze_routing_details(output_pcb: str) -> dict:
    """
    Analyze the routed PCB for detailed routing statistics.

    Returns dict with:
        - routes_by_layer: {layer: count}
        - vias_count: total vias
        - trace_length_mm: total trace length
    """
    try:
        from kiutils.board import Board

        board = Board.from_file(output_pcb)

        routes_by_layer = Counter()
        total_length = 0.0

        for track in board.traceItems:
            if hasattr(track, "layer"):
                routes_by_layer[track.layer] += 1
            if hasattr(track, "start") and hasattr(track, "end"):
                dx = track.end.X - track.start.X
                dy = track.end.Y - track.start.Y
                total_length += (dx**2 + dy**2) ** 0.5

        vias_count = len([t for t in board.traceItems if hasattr(t, "drill")])

        return {
            "routes_by_layer": dict(routes_by_layer),
            "vias_count": vias_count,
            "trace_length_mm": round(total_length, 2),
        }
    except Exception as e:
        return {
            "error": str(e),
            "routes_by_layer": {},
            "vias_count": 0,
            "trace_length_mm": 0,
        }


def run_benchmark(input_pcb: str, output_dir: str = "/tmp") -> dict:
    """
    Run full benchmark: pipeline + DRC + analysis.

    Returns complete metrics dict.
    """
    print(f"Running benchmark on {input_pcb}...")
    print("-" * 60)

    # Run pipeline
    print("Step 1/3: Running MVP3 pipeline...")
    pipeline_metrics = run_pipeline(input_pcb, output_dir)
    print(f"  Elapsed: {pipeline_metrics['elapsed_seconds']}s")
    print(
        f"  Nets routed: {pipeline_metrics['nets']['routed']}/{pipeline_metrics['nets']['total']}"
    )

    # Run DRC
    print("\nStep 2/3: Running DRC...")
    output_pcb = pipeline_metrics.get("output_file", f"{output_dir}/benchmark_output.kicad_pcb")
    drc_metrics = run_drc(output_pcb)
    print(f"  Total violations: {drc_metrics['total']}")
    print(f"  Actionable violations: {drc_metrics['actionable']}")

    # Analyze routing
    print("\nStep 3/3: Analyzing routing details...")
    routing_details = analyze_routing_details(output_pcb)
    print(f"  Vias: {routing_details.get('vias_count', 0)}")
    print(f"  Trace length: {routing_details.get('trace_length_mm', 0)}mm")

    # Combine all metrics
    metrics = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "commit": get_git_commit(),
        "input_file": input_pcb,
        "pipeline": pipeline_metrics,
        "drc": drc_metrics,
        "routing": routing_details,
    }

    return metrics


def compare_metrics(current: dict, baseline_path: str) -> None:
    """Compare current metrics against baseline and print diff."""
    try:
        with open(baseline_path) as f:
            baseline = json.load(f)
    except FileNotFoundError:
        print(f"Baseline file not found: {baseline_path}")
        return

    print("\n" + "=" * 60)
    print("COMPARISON: Current vs Baseline")
    print("=" * 60)

    # Net completion
    curr_rate = current["pipeline"]["nets"]["completion_rate"]
    base_rate = baseline["pipeline"]["nets"]["completion_rate"]
    delta_rate = curr_rate - base_rate
    symbol = "+" if delta_rate >= 0 else ""
    print(
        f"\nNet Completion Rate: {curr_rate:.1%} (baseline: {base_rate:.1%}, {symbol}{delta_rate:.1%})"
    )

    # DRC violations
    curr_drc = current["drc"]["actionable"]
    base_drc = baseline["drc"]["actionable"]
    delta_drc = curr_drc - base_drc
    symbol = "+" if delta_drc >= 0 else ""
    status = "WORSE" if delta_drc > 0 else ("BETTER" if delta_drc < 0 else "SAME")
    print(f"Actionable DRC: {curr_drc} (baseline: {base_drc}, {symbol}{delta_drc}) [{status}]")

    # Time
    curr_time = current["pipeline"]["elapsed_seconds"]
    base_time = baseline["pipeline"]["elapsed_seconds"]
    delta_time = curr_time - base_time
    symbol = "+" if delta_time >= 0 else ""
    print(f"Elapsed Time: {curr_time}s (baseline: {base_time}s, {symbol}{delta_time:.1f}s)")

    # DRC breakdown changes
    curr_types = current["drc"].get("by_type", {})
    base_types = baseline["drc"].get("by_type", {})
    all_types = set(curr_types.keys()) | set(base_types.keys())

    print("\nDRC Violation Changes:")
    for vtype in sorted(all_types):
        curr_count = curr_types.get(vtype, 0)
        base_count = base_types.get(vtype, 0)
        if curr_count != base_count:
            delta = curr_count - base_count
            symbol = "+" if delta >= 0 else ""
            print(f"  {vtype}: {curr_count} ({symbol}{delta})")


def main():
    parser = argparse.ArgumentParser(description="Benchmark routing pipeline performance")
    parser.add_argument(
        "--input",
        default="pcb/temper.kicad_pcb",
        help="Input PCB file (default: pcb/temper.kicad_pcb)",
    )
    parser.add_argument(
        "--output",
        default="metrics/baseline_routing.json",
        help="Output JSON file (default: metrics/baseline_routing.json)",
    )
    parser.add_argument(
        "--output-dir",
        default="/tmp",
        help="Directory for intermediate PCB files (default: /tmp)",
    )
    parser.add_argument(
        "--compare",
        metavar="BASELINE",
        help="Compare against baseline JSON file",
    )
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="Don't save metrics to file",
    )

    args = parser.parse_args()

    # Run benchmark
    metrics = run_benchmark(args.input, args.output_dir)

    # Print summary
    print("\n" + "=" * 60)
    print("BENCHMARK SUMMARY")
    print("=" * 60)
    print(f"Commit: {metrics['commit']}")
    print(f"Timestamp: {metrics['timestamp']}")
    print(
        f"Net Completion: {metrics['pipeline']['nets']['routed']}/{metrics['pipeline']['nets']['total']} ({metrics['pipeline']['nets']['completion_rate']:.1%})"
    )
    print(f"Actionable DRC: {metrics['drc']['actionable']}")
    print(f"Total DRC: {metrics['drc']['total']}")
    print(f"Elapsed: {metrics['pipeline']['elapsed_seconds']}s")

    # Compare if requested
    if args.compare:
        compare_metrics(metrics, args.compare)

    # Save metrics
    if not args.no_save:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(metrics, f, indent=2)
        print(f"\nMetrics saved to: {output_path}")

    # Return non-zero if pipeline failed
    return 0 if metrics["pipeline"]["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
