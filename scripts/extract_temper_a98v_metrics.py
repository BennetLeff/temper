#!/usr/bin/env python3.11
"""
Extract metrics from temper-a98v experiment placements.

Reads placement JSON files and computes:
- Average distance to nearest board edge
- Min/max edge distances
- Component spread metrics
- Loss trajectory data from logs

Usage:
    python3.11 scripts/extract_temper_a98v_metrics.py
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

    # Compute centroid
    centroid_x = statistics.mean(x for x, y in positions)
    centroid_y = statistics.mean(y for y, y in positions)

    return {
        "n_components": len(placements),
        "avg_edge_distance_mm": statistics.mean(edge_distances),
        "min_edge_distance_mm": min(edge_distances),
        "max_edge_distance_mm": max(edge_distances),
        "std_edge_distance_mm": statistics.stdev(edge_distances)
        if len(edge_distances) > 1
        else 0.0,
        "max_spread_mm": max_spread,
        "centroid_x": centroid_x,
        "centroid_y": centroid_y,
    }


def parse_log_file(log_path: Path) -> Dict:
    """Extract loss trajectory from log file."""
    with open(log_path) as f:
        log_content = f.read()

    # Extract final loss and best loss
    final_match = re.search(r"Final loss:\s+([\d.]+)", log_content)
    best_match = re.search(r"Best loss:\s+([\d.]+)", log_content)
    time_match = re.search(r"Time:\s+([\d.]+)s", log_content)

    # Extract epoch losses
    epoch_pattern = r"Epoch\s+(\d+)/\d+:\s+loss=([\d.]+)"
    epochs = []
    losses = []
    for match in re.finditer(epoch_pattern, log_content):
        epochs.append(int(match.group(1)))
        losses.append(float(match.group(2)))

    # Extract number of loss functions created
    loss_fn_match = re.search(r"Created (\d+) loss functions", log_content)

    return {
        "final_loss": float(final_match.group(1)) if final_match else None,
        "best_loss": float(best_match.group(1)) if best_match else None,
        "time_seconds": float(time_match.group(1)) if time_match else None,
        "n_loss_functions": int(loss_fn_match.group(1)) if loss_fn_match else None,
        "epoch_trajectory": list(zip(epochs, losses)),
        "initial_loss": losses[0] if losses else None,
        "n_epochs": len(epochs),
    }


def main():
    project_root = Path(__file__).parent.parent
    results_dir = project_root / "experiments" / "temper-a98v"

    # Find all placement JSON files
    placement_files = sorted(results_dir.glob("*_placements.json"))

    all_metrics = []

    print("=" * 80)
    print("temper-a98v POC Metrics Extraction")
    print("=" * 80)
    print()

    for json_file in placement_files:
        # Parse condition and run number from filename
        # Format: {condition}_run{N}_placements.json
        stem = json_file.stem  # e.g., "baseline_run1_placements"
        parts = stem.replace("_placements", "").rsplit("_run", 1)
        condition = parts[0]
        run_num = int(parts[1])

        # Find corresponding log file
        log_file = results_dir / f"{condition}_run{run_num}.log"

        print(f"Processing: {condition} run {run_num}")
        print(f"  JSON: {json_file.name}")
        print(f"  Log:  {log_file.name}")

        # Extract metrics
        placement_metrics = analyze_placement_json(json_file)
        log_metrics = parse_log_file(log_file) if log_file.exists() else {}

        # Combine metrics
        metrics = {
            "condition": condition,
            "run": run_num,
            "json_file": str(json_file.relative_to(project_root)),
            "log_file": str(log_file.relative_to(project_root)),
            **placement_metrics,
            **log_metrics,
        }

        all_metrics.append(metrics)

        # Print summary
        print(f"    Components: {metrics['n_components']}")
        print(f"    Loss functions: {metrics.get('n_loss_functions', 'N/A')}")
        print(f"    Best loss: {metrics.get('best_loss', 'N/A'):.2f}")
        print(f"    Final loss: {metrics.get('final_loss', 'N/A'):.2f}")
        print(f"    Avg edge distance: {metrics['avg_edge_distance_mm']:.2f} mm")
        print(f"    Min edge distance: {metrics['min_edge_distance_mm']:.2f} mm")
        print(f"    Max spread: {metrics['max_spread_mm']:.2f} mm")
        print(f"    Time: {metrics.get('time_seconds', 'N/A')} s")
        print()

    # Save combined metrics
    output_file = results_dir / "poc_metrics.json"
    with open(output_file, "w") as f:
        json.dump(all_metrics, f, indent=2)

    print(f"✓ Saved metrics to: {output_file.relative_to(project_root)}")
    print()

    # Compute summary statistics by condition
    print("=" * 80)
    print("Summary Statistics by Condition")
    print("=" * 80)
    print()

    conditions = sorted(set(m["condition"] for m in all_metrics))

    for condition in conditions:
        cond_metrics = [m for m in all_metrics if m["condition"] == condition]

        print(f"{condition.upper()}")
        print(f"  N = {len(cond_metrics)} runs")
        print(f"  Loss functions: {cond_metrics[0].get('n_loss_functions', 'N/A')}")

        # Best loss stats
        best_losses = [m["best_loss"] for m in cond_metrics if m.get("best_loss")]
        if best_losses:
            print(
                f"  Best loss: {statistics.mean(best_losses):.2f} ± {statistics.stdev(best_losses):.2f}"
            )

        # Final loss stats
        final_losses = [m["final_loss"] for m in cond_metrics if m.get("final_loss")]
        if final_losses:
            print(
                f"  Final loss: {statistics.mean(final_losses):.2f} ± {statistics.stdev(final_losses):.2f}"
            )

        # Edge distance stats
        avg_edge_dists = [m["avg_edge_distance_mm"] for m in cond_metrics]
        print(
            f"  Avg edge distance: {statistics.mean(avg_edge_dists):.2f} ± {statistics.stdev(avg_edge_dists):.2f} mm"
        )

        min_edge_dists = [m["min_edge_distance_mm"] for m in cond_metrics]
        print(
            f"  Min edge distance: {statistics.mean(min_edge_dists):.2f} ± {statistics.stdev(min_edge_dists):.2f} mm"
        )

        # Spread stats
        max_spreads = [m["max_spread_mm"] for m in cond_metrics]
        print(
            f"  Max spread: {statistics.mean(max_spreads):.2f} ± {statistics.stdev(max_spreads):.2f} mm"
        )

        print()

    print("=" * 80)
    print("✓ Metrics extraction complete")
    print("=" * 80)
    print()
    print("Next steps:")
    print("  1. Review poc_metrics.json for detailed data")
    print("  2. Run full experiment with N=30 runs per condition")
    print("  3. Perform statistical analysis (ANOVA + post-hoc)")
    print()


if __name__ == "__main__":
    main()
