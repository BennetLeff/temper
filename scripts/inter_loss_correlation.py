#!/usr/bin/env python3
"""
Inter-Loss Correlation Analysis

Computes pairwise correlations between loss functions to identify:
1. Confounded losses (r > 0.7) - may measure the same thing
2. Negatively correlated losses (r < -0.7) - may be in conflict
3. Independent losses (|r| < 0.3) - measure different aspects

Usage:
    python scripts/inter_loss_correlation.py metrics/correlation_analysis_30samples.json
    python scripts/inter_loss_correlation.py metrics/correlation_analysis_30samples.json --heatmap

Related issue: temper-h0n9.8
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np

# Add scripts directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))
from correlation_analysis import compute_inter_loss_correlations


def analyze_inter_loss_correlations(raw_data: dict) -> dict:
    """
    Analyze inter-loss correlations from raw data.

    Args:
        raw_data: Dict with "losses" key containing loss name -> values mapping

    Returns:
        Analysis results with correlation matrix and findings
    """
    if "losses" not in raw_data:
        raise ValueError("raw_data must contain 'losses' key")

    loss_data = raw_data["losses"]

    # Compute correlation matrix
    matrix = compute_inter_loss_correlations(loss_data)

    # Identify confounded pairs (|r| > 0.7, excluding diagonal)
    confounded_pairs = []
    negatively_correlated = []
    independent_pairs = []

    loss_names = sorted(matrix.keys())
    for i, loss_a in enumerate(loss_names):
        for j, loss_b in enumerate(loss_names):
            if i >= j:  # Skip diagonal and duplicates
                continue

            r = matrix[loss_a][loss_b]

            if r > 0.7:
                confounded_pairs.append(
                    {
                        "loss_a": loss_a,
                        "loss_b": loss_b,
                        "r": r,
                        "interpretation": "Highly correlated - may measure same thing",
                    }
                )
            elif r < -0.7:
                negatively_correlated.append(
                    {
                        "loss_a": loss_a,
                        "loss_b": loss_b,
                        "r": r,
                        "interpretation": "Highly anti-correlated - may be in conflict",
                    }
                )
            elif abs(r) < 0.3:
                independent_pairs.append(
                    {
                        "loss_a": loss_a,
                        "loss_b": loss_b,
                        "r": r,
                    }
                )

    return {
        "matrix": matrix,
        "confounded_pairs": confounded_pairs,
        "negatively_correlated": negatively_correlated,
        "independent_pairs": independent_pairs,
        "n_losses": len(loss_names),
        "n_confounded": len(confounded_pairs),
        "n_independent": len(independent_pairs),
    }


def print_analysis(analysis: dict) -> None:
    """Print human-readable analysis results."""
    print(f"\n{'=' * 60}")
    print("Inter-Loss Correlation Analysis")
    print(f"{'=' * 60}")
    print(f"\nAnalyzed {analysis['n_losses']} loss functions")

    # Confounded pairs (problematic - may be redundant)
    print(f"\n🔴 CONFOUNDED PAIRS (r > 0.7): {len(analysis['confounded_pairs'])}")
    if analysis["confounded_pairs"]:
        print("   These losses may measure the same thing - consider removing one:")
        for pair in sorted(analysis["confounded_pairs"], key=lambda x: -x["r"]):
            print(f"   • {pair['loss_a']} ↔ {pair['loss_b']}: r={pair['r']:.3f}")
    else:
        print("   None found - losses appear to measure different things")

    # Negatively correlated (potentially conflicting)
    print(f"\n🟡 NEGATIVELY CORRELATED (r < -0.7): {len(analysis['negatively_correlated'])}")
    if analysis["negatively_correlated"]:
        print("   These losses may be in conflict - optimizing one may hurt the other:")
        for pair in sorted(analysis["negatively_correlated"], key=lambda x: x["r"]):
            print(f"   • {pair['loss_a']} ↔ {pair['loss_b']}: r={pair['r']:.3f}")
    else:
        print("   None found - no strong conflicts between losses")

    # Independent pairs (good - measure different aspects)
    print(f"\n🟢 INDEPENDENT PAIRS (|r| < 0.3): {len(analysis['independent_pairs'])}")
    print(f"   These losses measure independent aspects of placement quality")

    # Recommendations
    print(f"\n{'=' * 60}")
    print("RECOMMENDATIONS")
    print(f"{'=' * 60}")

    if analysis["confounded_pairs"]:
        print("\n1. Consider removing redundant losses:")
        seen = set()
        for pair in analysis["confounded_pairs"]:
            if pair["loss_b"] not in seen:
                seen.add(pair["loss_b"])
                print(f"   - {pair['loss_b']} is redundant with {pair['loss_a']}")

    if analysis["negatively_correlated"]:
        print("\n2. Review conflicting losses - may need weight adjustment:")
        for pair in analysis["negatively_correlated"]:
            print(f"   - {pair['loss_a']} and {pair['loss_b']} work against each other")


def print_heatmap(matrix: dict) -> None:
    """Print ASCII heatmap of correlation matrix."""
    loss_names = sorted(matrix.keys())

    # Truncate names for display
    max_name_len = 15
    short_names = [n[:max_name_len] for n in loss_names]

    print(f"\n{'Correlation Matrix':^{max_name_len + len(loss_names) * 6}}")
    print("-" * (max_name_len + len(loss_names) * 6))

    # Header
    print(" " * (max_name_len + 1), end="")
    for name in short_names:
        print(f"{name[:5]:>5} ", end="")
    print()

    # Rows
    for i, loss_a in enumerate(loss_names):
        print(f"{short_names[i]:<{max_name_len}} ", end="")
        for loss_b in loss_names:
            r = matrix[loss_a][loss_b]
            # Color coding: +++ (>0.7), ++ (>0.3), + (>0), - (<0), -- (<-0.3), --- (<-0.7)
            if r > 0.7:
                sym = "+++"
            elif r > 0.3:
                sym = " ++"
            elif r > 0.0:
                sym = "  +"
            elif r > -0.3:
                sym = "  -"
            elif r > -0.7:
                sym = " --"
            else:
                sym = "---"
            print(f"{sym:>5} ", end="")
        print()


def main():
    parser = argparse.ArgumentParser(
        description="Compute inter-loss correlations from correlation analysis output"
    )
    parser.add_argument(
        "input",
        type=Path,
        help="Path to correlation analysis JSON file (must have raw_data)",
    )
    parser.add_argument(
        "--heatmap",
        action="store_true",
        help="Print ASCII heatmap of correlation matrix",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Save results to file",
    )

    args = parser.parse_args()

    # Load input file
    if not args.input.exists():
        print(f"Error: File not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    with open(args.input) as f:
        data = json.load(f)

    # Check for raw_data
    if "raw_data" not in data:
        print("Error: Input file does not contain 'raw_data'.", file=sys.stderr)
        print("       Re-run correlation_analysis.py with the updated version", file=sys.stderr)
        print("       to generate a file with raw loss values.", file=sys.stderr)
        sys.exit(1)

    # Run analysis
    analysis = analyze_inter_loss_correlations(data["raw_data"])

    # Output
    if args.json:
        # Remove matrix from JSON output (too large)
        output = {k: v for k, v in analysis.items() if k != "matrix"}
        print(json.dumps(output, indent=2))
    else:
        print_analysis(analysis)
        if args.heatmap:
            print_heatmap(analysis["matrix"])

    # Save to file if requested
    if args.output:
        with open(args.output, "w") as f:
            json.dump(analysis, f, indent=2)
        print(f"\nResults saved to: {args.output}")


if __name__ == "__main__":
    main()
