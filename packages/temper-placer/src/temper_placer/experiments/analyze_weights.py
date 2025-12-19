"""
Analysis script for weight search results.

Loads weight_search.json results and generates visualizations and statistics.

Usage:
    python -m temper_placer.experiments.analyze_weights \
        --input results/weight_search.json \
        --top-k 10 \
        --output results/weight_analysis.html
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

import numpy as np


def load_results(json_path: Path) -> Dict:
    """Load weight search results from JSON file."""
    with open(json_path) as f:
        return json.load(f)


def analyze_weight_correlations(results: Dict) -> None:
    """
    Analyze correlation between individual weights and DRC pass rate.

    Args:
        results: Loaded weight search results.
    """
    print("\n" + "=" * 80)
    print("WEIGHT CORRELATION ANALYSIS")
    print("=" * 80)

    # Extract data
    all_configs = []
    all_scores = []
    all_drc_pass_rates = []

    for entry in results["results"]:
        config = entry["config"]
        pcb_results = entry["pcb_results"]

        # Compute DRC pass rate for this config
        drc_pass_count = sum(1 for r in pcb_results if r["drc_errors"] == 0)
        drc_pass_rate = drc_pass_count / len(pcb_results)

        all_configs.append(config)
        all_scores.append(entry["score"])
        all_drc_pass_rates.append(drc_pass_rate)

    # Convert to numpy arrays
    n = len(all_configs)
    overlap_weights = np.array([c["overlap_weight"] for c in all_configs])
    boundary_weights = np.array([c["boundary_weight"] for c in all_configs])
    clearance_weights = np.array([c["clearance_weight"] for c in all_configs])
    wirelength_weights = np.array([c["wirelength_weight"] for c in all_configs])
    thermal_weights = np.array([c["thermal_weight"] for c in all_configs])
    drc_pass_rates = np.array(all_drc_pass_rates)

    # Compute correlations
    weight_arrays = {
        "overlap_weight": overlap_weights,
        "boundary_weight": boundary_weights,
        "clearance_weight": clearance_weights,
        "wirelength_weight": wirelength_weights,
        "thermal_weight": thermal_weights,
    }

    print("\nCorrelation with DRC Pass Rate:")
    print("-" * 80)
    for weight_name, weight_values in weight_arrays.items():
        corr = np.corrcoef(weight_values, drc_pass_rates)[0, 1]
        print(f"  {weight_name:20s}: {corr:+.3f}")

    # Find best weight ranges
    print("\nBest Weight Ranges (for configs with 100% DRC pass):")
    print("-" * 80)

    perfect_configs = [c for c, rate in zip(all_configs, drc_pass_rates) if rate == 1.0]

    if perfect_configs:
        for weight_name in weight_arrays.keys():
            values = [c[weight_name] for c in perfect_configs]
            print(
                f"  {weight_name:20s}: min={min(values):.1f}, max={max(values):.1f}, "
                f"mean={np.mean(values):.1f}"
            )
    else:
        print("  No configurations achieved 100% DRC pass rate")


def analyze_pcb_difficulty(results: Dict) -> None:
    """
    Analyze which PCBs are hardest to optimize.

    Args:
        results: Loaded weight search results.
    """
    print("\n" + "=" * 80)
    print("PCB DIFFICULTY ANALYSIS")
    print("=" * 80)

    # Group results by PCB
    pcb_stats: Dict[str, List[int]] = {}

    for entry in results["results"]:
        for pcb_result in entry["pcb_results"]:
            pcb_name = pcb_result["pcb_name"]
            drc_errors = pcb_result["drc_errors"]

            if pcb_name not in pcb_stats:
                pcb_stats[pcb_name] = []
            pcb_stats[pcb_name].append(drc_errors)

    # Compute statistics per PCB
    print("\nPCB Success Rates (across all weight configs):")
    print("-" * 80)
    print(f"{'PCB Name':<30} {'Pass Rate':<12} {'Best Errors':<14} {'Worst Errors'}")
    print("-" * 80)

    for pcb_name, drc_error_list in sorted(pcb_stats.items()):
        pass_count = sum(1 for e in drc_error_list if e == 0)
        pass_rate = 100 * pass_count / len(drc_error_list)
        best_errors = min(drc_error_list)
        worst_errors = max(drc_error_list)

        print(f"{pcb_name:<30} {pass_rate:>6.1f}%      {best_errors:<14} {worst_errors}")


def print_summary(results: Dict, top_k: int = 10) -> None:
    """Print summary statistics."""
    print("\n" + "=" * 80)
    print("WEIGHT SEARCH SUMMARY")
    print("=" * 80)
    print(f"Total configurations tested: {len(results['results'])}")
    print(f"Epochs per trial: {results['epochs']}")
    print(f"Heuristics enabled: {results['use_heuristics']}")
    print(f"Curriculum enabled: {results['use_curriculum']}")

    # Print top configs inline
    print(f"\nTop {top_k} Configurations:")
    print("-" * 80)
    print(f"{'Rank':<6} {'DRC Pass':<10} {'Avg WL Ratio':<14} {'Score':<8} {'Weights'}")
    print("-" * 80)

    for rank, entry in enumerate(results["results"][:top_k], 1):
        config = entry["config"]
        score = entry["score"]
        pcb_results = entry["pcb_results"]

        # Compute statistics
        drc_pass_count = sum(1 for r in pcb_results if r["drc_errors"] == 0)
        drc_pass_pct = f"{100 * drc_pass_count / len(pcb_results):.0f}%"

        passing_results = [r for r in pcb_results if r["drc_errors"] == 0]
        if passing_results:
            avg_wl = np.mean([r["wirelength_ratio"] for r in passing_results])
            avg_wl_str = f"{avg_wl:.3f}x"
        else:
            avg_wl_str = "N/A"

        print(
            f"{rank:<6} {drc_pass_pct:<10} {avg_wl_str:<14} {score:<8.2f} "
            f"O={config['overlap_weight']}, B={config['boundary_weight']}, "
            f"C={config['clearance_weight']}, W={config['wirelength_weight']}, "
            f"T={config['thermal_weight']}"
        )

    # Print recommended weights
    if results["results"]:
        best_entry = results["results"][0]
        best_config = best_entry["config"]
        best_score = best_entry["score"]

        print("\n" + "=" * 80)
        print("RECOMMENDED PRODUCTION WEIGHTS")
        print("=" * 80)
        print(f"  overlap_weight: {best_config['overlap_weight']}")
        print(f"  boundary_weight: {best_config['boundary_weight']}")
        print(f"  clearance_weight: {best_config['clearance_weight']}")
        print(f"  wirelength_weight: {best_config['wirelength_weight']}")
        print(f"  thermal_weight: {best_config['thermal_weight']}")
        print(f"\nAggregate Score: {best_score:.2f}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Analyze weight search results")
    parser.add_argument(
        "--input",
        type=Path,
        required=True,
        help="Input JSON file from weight_search",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=10,
        help="Number of top configurations to display",
    )

    args = parser.parse_args()

    # Load results
    results = load_results(args.input)

    # Print summary
    print_summary(results, top_k=args.top_k)

    # Analyze correlations
    analyze_weight_correlations(results)

    # Analyze PCB difficulty
    analyze_pcb_difficulty(results)
