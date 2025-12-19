#!/usr/bin/env python3
"""
DRC-Loss Correlation Analysis Script.

This script analyzes the correlation between optimizer loss components
and KiCad DRC violations to inform weight selection.
"""

import json
import sys
from pathlib import Path
from typing import List, Dict, Any

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from temper_placer.analysis.drc_correlation import (
    analyze_drc_correlation,
    PlacementResult,
    DRCResult,
)


def load_existing_data() -> tuple[List[PlacementResult], List[DRCResult]]:
    """Load existing DRC correlation data from test results."""
    # Load the existing correlation data
    data_path = (
        Path(__file__).parent.parent.parent.parent
        / "tests"
        / "validation"
        / "results"
        / "drc_correlation_data.json"
    )

    if not data_path.exists():
        print(f"Error: Could not find data file at {data_path}")
        return [], []

    with open(data_path) as f:
        data = json.load(f)

    placements = []
    drc_results = []

    # Convert the existing data format to our analysis format
    for point in data.get("data_points", []):
        quality_level = point["quality_level"]
        overlap_loss = point["overlap_loss"]
        total_loss = point["total_loss"]
        drc_errors = point["drc_errors"]

        # Estimate other loss components based on total loss and overlap
        # This is a simplification - in real analysis we'd have the actual values
        wirelength_loss = total_loss * 0.1  # Rough estimate
        boundary_loss = 0.0  # Most placements seem to have minimal boundary issues

        placements.append(
            PlacementResult(
                quality_level=quality_level,
                overlap_loss=overlap_loss,
                boundary_loss=boundary_loss,
                wirelength_loss=wirelength_loss,
                total_loss=total_loss,
            )
        )

        # Parse DRC errors by type (we only have total errors in the existing data)
        # In a real analysis, we'd have the detailed breakdown
        drc_results.append(
            DRCResult(
                courtyards_overlap=max(0, drc_errors // 3),  # Estimate
                edge_clearance=max(0, drc_errors // 4),  # Estimate
                pad_clearance=max(0, drc_errors // 2),  # Estimate
                total_errors=drc_errors,
            )
        )

    return placements, drc_results


def load_detailed_drc_data() -> tuple[List[PlacementResult], List[DRCResult]]:
    """Load detailed DRC data from the correlation report."""
    report_path = (
        Path(__file__).parent.parent.parent.parent
        / "tests"
        / "validation"
        / "results"
        / "drc_correlation_report.json"
    )

    if not report_path.exists():
        print(f"Error: Could not find report file at {report_path}")
        return [], []

    with open(report_path) as f:
        report = json.load(f)

    placements = []
    drc_results = []

    for entry in report.get("placements", []):
        quality_level = entry["quality_level"]
        opt_metrics = entry["optimizer_metrics"]
        drc_metrics = entry["drc_results"]

        placements.append(
            PlacementResult(
                quality_level=quality_level,
                overlap_loss=opt_metrics.get("overlap_loss", 0.0),
                boundary_loss=opt_metrics.get("boundary_loss", 0.0),
                wirelength_loss=opt_metrics.get("wirelength_loss", 0.0),
                total_loss=opt_metrics.get("total_loss", 0.0),
            )
        )

        # Parse violations by type from DRC results
        violations_by_type = drc_metrics.get("violations_by_type", {})

        drc_results.append(
            DRCResult(
                courtyards_overlap=violations_by_type.get("courtyards_overlap", 0),
                edge_clearance=violations_by_type.get("silk_edge_clearance", 0)
                + violations_by_type.get("copper_edge_clearance", 0),
                pad_clearance=violations_by_type.get("clearance", 0),
                total_errors=drc_metrics.get("error_count", 0),
            )
        )

    return placements, drc_results


def generate_report(
    placements: List[PlacementResult], drc_results: List[DRCResult]
) -> Dict[str, Any]:
    """Generate comprehensive correlation analysis report."""
    print("Running DRC-Loss Correlation Analysis...")
    print(f"Analyzing {len(placements)} placement samples")

    # Run correlation analysis
    report = analyze_drc_correlation(placements, drc_results)

    # Create comprehensive output
    output = {
        "description": "DRC-Loss Correlation Analysis Results",
        "summary": {
            "placements_analyzed": len(placements),
            "correlations_computed": len(report.correlations),
            "data_quality": "Good" if len(placements) >= 3 else "Limited",
        },
        "correlations": report.correlations,
        "recommendations": report.recommendations,
        "interpretation": generate_interpretation(report.correlations),
        "data_points": [
            {
                "quality_level": p.quality_level,
                "optimizer_metrics": {
                    "overlap_loss": p.overlap_loss,
                    "boundary_loss": p.boundary_loss,
                    "wirelength_loss": p.wirelength_loss,
                    "total_loss": p.total_loss,
                },
                "drc_violations": {
                    "courtyards_overlap": d.courtyards_overlap,
                    "edge_clearance": d.edge_clearance,
                    "pad_clearance": d.pad_clearance,
                    "total_errors": d.total_errors,
                },
            }
            for p, d in zip(placements, drc_results)
        ],
    }

    return output


def generate_interpretation(correlations: List[Dict[str, Any]]) -> Dict[str, str]:
    """Generate human-readable interpretation of correlations."""
    interpretation = {}

    for corr in correlations:
        component = corr["loss_component"]
        pearson = corr["pearson_r"]
        spearman = corr["spearman_rho"]
        p_value = corr["p_value"]
        drc_type = corr["drc_type"]

        # Interpret correlation strength
        if abs(pearson) >= 0.8:
            strength = "very strong"
        elif abs(pearson) >= 0.6:
            strength = "strong"
        elif abs(pearson) >= 0.4:
            strength = "moderate"
        elif abs(pearson) >= 0.2:
            strength = "weak"
        else:
            strength = "very weak"

        # Interpret direction
        direction = "positive" if pearson > 0 else "negative"

        # Statistical significance
        significance = "significant" if p_value < 0.05 else "not significant"

        interpretation[component] = (
            f"{strength.capitalize()} {direction} correlation (r={pearson:.3f}, ρ={spearman:.3f}) "
            f"with {drc_type}. Statistical significance: {significance} (p={p_value:.3f})."
        )

    return interpretation


def print_report(report: Dict[str, Any]) -> None:
    """Print formatted report to console."""
    print("\n" + "=" * 70)
    print("DRC-Loss Correlation Analysis")
    print("=" * 70)

    print(f"\nSummary:")
    print(f"  Placements analyzed: {report['summary']['placements_analyzed']}")
    print(f"  Correlations computed: {report['summary']['correlations_computed']}")
    print(f"  Data quality: {report['summary']['data_quality']}")

    print(f"\nCorrelation Results:")
    print(
        f"{'Loss Component':<18} {'Pearson r':<12} {'Spearman ρ':<12} {'p-value':<10} {'DRC Type'}"
    )
    print("-" * 70)

    for corr in report["correlations"]:
        print(
            f"{corr['loss_component']:<18} "
            f"{corr['pearson_r']:<12.3f} "
            f"{corr['spearman_rho']:<12.3f} "
            f"{corr['p_value']:<10.3f} "
            f"{corr['drc_type']}"
        )

    print(f"\nRecommended Initial Weights:")
    for loss_type, weight in report["recommendations"].items():
        print(f"  {loss_type.capitalize():<12}: {weight:>6.1f}")

    print(f"\nInterpretation:")
    for component, interp in report["interpretation"].items():
        print(f"  {component}: {interp}")

    print("=" * 70)


def save_report(report: Dict[str, Any], output_path: Path) -> None:
    """Save report to JSON file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w") as f:
        json.dump(report, f, indent=2)

    print(f"\nReport saved to: {output_path}")


def main():
    """Main analysis function."""
    # Try to load detailed DRC data first, fall back to basic data
    placements, drc_results = load_detailed_drc_data()

    if not placements:
        print("Could not load DRC data. Exiting.")
        return 1

    # Generate analysis report
    report = generate_report(placements, drc_results)

    # Print to console
    print_report(report)

    # Save to file
    output_path = (
        Path(__file__).parent.parent.parent.parent
        / "tests"
        / "validation"
        / "results"
        / "drc_correlation_analysis.json"
    )
    save_report(report, output_path)

    return 0


if __name__ == "__main__":
    sys.exit(main())
