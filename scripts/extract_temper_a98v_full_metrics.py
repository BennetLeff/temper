#!/usr/bin/env python3.11
"""
Extract metrics from temper-a98v full experiment (N=30).

Reads placement JSON files, logs, and routing summary.
Computes summary statistics and prepares data for ANOVA.
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Tuple
import statistics

# Board dimensions and origin (matches medium_board.kicad_pcb)
BOARD_WIDTH = 60.0  # mm
BOARD_HEIGHT = 40.0  # mm
BOARD_ORIGIN_X = 100.0  # mm
BOARD_ORIGIN_Y = 85.0   # mm


def compute_edge_distance(x: float, y: float) -> float:
    """Compute minimum distance to any board edge."""
    dist_left = x - BOARD_ORIGIN_X
    dist_right = (BOARD_ORIGIN_X + BOARD_WIDTH) - x
    dist_bottom = y - BOARD_ORIGIN_Y
    dist_top = (BOARD_ORIGIN_Y + BOARD_HEIGHT) - y
    return min(dist_left, dist_right, dist_bottom, dist_top)


def analyze_placement_json(json_path: Path) -> Dict:
    """Extract metrics from a single placement JSON."""
    with open(json_path) as f:
        placements = json.load(f)

    edge_distances = []
    positions = []

    for comp_ref, data in placements.items():
        x = data["x"]
        y = data["y"]
        positions.append((x, y))
        edge_dist = compute_edge_distance(x, y)
        edge_distances.append(edge_dist)

    # Compute spread (max distance between any two components)
    max_spread = 0.0
    for i, (x1, y1) in enumerate(positions):
        for x2, y2 in positions[i + 1 :]:
            dist = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
            max_spread = max(max_spread, dist)

    return {
        "n_components": len(placements),
        "avg_edge_distance_mm": statistics.mean(edge_distances),
        "min_edge_distance_mm": min(edge_distances),
        "max_edge_distance_mm": max(edge_distances),
        "max_spread_mm": max_spread,
    }


def parse_log_file(log_path: Path) -> Dict:
    """Extract loss data from log file."""
    if not log_path.exists():
        return {}
    
    with open(log_path) as f:
        log_content = f.read()

    final_match = re.search(r"Final loss:\s+([\d.]+)", log_content)
    best_match = re.search(r"Best loss:\s+([\d.]+)", log_content)
    
    return {
        "final_loss": float(final_match.group(1)) if final_match else None,
        "best_loss": float(best_match.group(1)) if best_match else None,
    }


def parse_routing_summary(summary_path: Path) -> Dict[Tuple[str, int], float]:
    """Parse routing_summary.txt into a mapping of (condition, run) -> completion_pct."""
    routing_data = {}
    if not summary_path.exists():
        return {}
    
    with open(summary_path) as f:
        # Skip header lines
        lines = f.readlines()[3:]
        for line in lines:
            if "|" not in line:
                continue
            parts = [p.strip() for p in line.split("|")]
            if len(parts) < 3 or "--" in parts[1]:
                continue
            condition = parts[0]
            run_num = int(parts[1])
            completion_str = parts[2].replace("%", "")
            completion_pct = float(completion_str)
            routing_data[(condition, run_num)] = completion_pct
            
    return routing_data


def main():
    project_root = Path(__file__).parent.parent
    results_dir = project_root / "experiments" / "temper-a98v"

    # Load routing data
    routing_data = parse_routing_summary(results_dir / "routing_summary.txt")

    # Find all placement JSON files
    placement_files = sorted(results_dir.glob("*_placements.json"))

    all_metrics = []

    print("=" * 80)
    print("temper-a98v Full Metrics Extraction")
    print("=" * 80)

    for json_file in placement_files:
        stem = json_file.stem
        parts = stem.replace("_placements", "").rsplit("_run", 1)
        condition = parts[0]
        run_num = int(parts[1])

        log_file = results_dir / f"{condition}_run{run_num}.log"

        # Extract metrics
        placement_metrics = analyze_placement_json(json_file)
        log_metrics = parse_log_file(log_file)
        routing_pct = routing_data.get((condition, run_num))

        # Combine metrics
        metrics = {
            "condition": condition,
            "run": run_num,
            "routing_completion_pct": routing_pct,
            **placement_metrics,
            **log_metrics,
        }

        all_metrics.append(metrics)

    # Save combined metrics
    output_file = results_dir / "full_metrics.json"
    with open(output_file, "w") as f:
        json.dump(all_metrics, f, indent=2)

    print(f"✓ Processed {len(all_metrics)} runs")
    print(f"✓ Saved metrics to: {output_file.relative_to(project_root)}")
    print()

    # Summary Statistics
    print("=" * 80)
    print(f"{'Condition':<15} | {'N':<3} | {'Routing %':<15} | {'Min Edge Dist':<15}")
    print("-" * 80)

    conditions = sorted(set(m["condition"] for m in all_metrics))

    for condition in conditions:
        cond_metrics = [m for m in all_metrics if m["condition"] == condition]
        n = len(cond_metrics)
        
        # Routing stats
        rout_vals = [m["routing_completion_pct"] for m in cond_metrics if m["routing_completion_pct"] is not None]
        rout_str = f"{statistics.mean(rout_vals):.2f} ± {statistics.stdev(rout_vals):.2f}" if len(rout_vals) > 1 else "N/A"
        
        # Min edge distance stats
        edge_vals = [m["min_edge_distance_mm"] for m in cond_metrics]
        edge_str = f"{statistics.mean(edge_vals):.2f} ± {statistics.stdev(edge_vals):.2f}"
        
        print(f"{condition:<15} | {n:<3} | {rout_str:<15} | {edge_str:<15}")

    print("=" * 80)
    print()
    
    # Check Hypothesis H1
    baseline_rout = statistics.mean([m["routing_completion_pct"] for m in all_metrics if m["condition"] == "baseline"])
    opt_c_rout = statistics.mean([m["routing_completion_pct"] for m in all_metrics if m["condition"] == "option_c"])
    diff = opt_c_rout - baseline_rout
    
    print(f"Baseline Routing Mean: {baseline_rout:.2f}%")
    print(f"Option C Routing Mean: {opt_c_rout:.2f}%")
    print(f"Difference: {diff:+.2f} percentage points")
    
    if diff >= 10.0:
        print(">>> RESULT: Option C meets the 10pp improvement target!")
    elif diff > 0:
        print(">>> RESULT: Option C shows improvement but below the 10pp target.")
    else:
        print(">>> RESULT: Option C did not improve routing completion.")

if __name__ == "__main__":
    main()
