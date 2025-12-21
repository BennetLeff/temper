#!/usr/bin/env python3
"""
<<<<<<< HEAD
Tune loss function weights based on correlation analysis.

This script reads a correlation report (from correlation_analysis.py) and
adjusts loss function weights in a configuration file based on how strongly
each loss correlates with routing quality metrics.

Algorithm:
- Strong correlation (|r| > 0.7): Increase weight by 1.5x
- Moderate correlation (0.3 <= |r| < 0.7): Keep weight unchanged
- Weak correlation (|r| < 0.3): Reduce weight by 0.5x

Safety rules:
- Hard constraints (overlap, boundary, clearance, zone_membership): Never reduce
- All multipliers capped at [0.25x, 4.0x]
- Preserves USER: keep comments (doesn't modify those losses)
"""

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Tuple

import yaml


# Hard constraints that should never be reduced
HARD_CONSTRAINTS = {"overlap", "boundary", "clearance", "zone_membership"}


def _compute_multiplier(r_completion: float, loss_name: str, is_hard_constraint: bool) -> float:
    """
    Compute weight multiplier based on correlation coefficient.

    Args:
        r_completion: Correlation coefficient with routing completion
        loss_name: Name of the loss function
        is_hard_constraint: Whether this is a hard constraint

    Returns:
        Multiplier in range [0.25, 4.0] (or [1.0, 4.0] for hard constraints)
    """
    abs_r = abs(r_completion)

    # Determine base multiplier
    if abs_r > 0.7:
        multiplier = 1.5  # Strong correlation
    elif abs_r >= 0.3:
        multiplier = 1.0  # Moderate correlation
    else:
        multiplier = 0.5  # Weak correlation

    # Hard constraints: never reduce
    if is_hard_constraint and multiplier < 1.0:
        multiplier = 1.0

    # Cap multipliers
    multiplier = max(0.25 if not is_hard_constraint else 1.0, multiplier)
    multiplier = min(4.0, multiplier)

    return multiplier


def _get_correlation(report: dict, loss_name: str) -> float:
    """Get completion correlation for a loss from report."""
    correlations = report.get("correlations", {})
    loss_data = correlations.get(loss_name, {})
    return loss_data.get("vs_completion", 0.0)


def _is_hard_constraint(loss_name: str) -> bool:
    """Check if loss is a hard constraint."""
    return loss_name in HARD_CONSTRAINTS


def _generate_header(report_path: Path, timestamp: str) -> str:
    """Generate YAML header comment."""
    return (
        f"# Auto-tuned weights based on correlation analysis\n"
        f"# Generated: {timestamp}\n"
        f"# Source: {report_path}\n\n"
    )


def _generate_loss_comment(
    loss_name: str,
    original_weight: float,
    new_weight: float,
    r_completion: float,
    multiplier: float,
) -> str:
    """Generate comment explaining weight change."""
    if multiplier > 1.0:
        action = f"Increased {multiplier}x"
    elif multiplier < 1.0:
        action = f"Reduced {multiplier}x"
    else:
        action = "Unchanged"

    return f"  # {action}: r={r_completion:.2f} with completion\n  # Original: {original_weight}"


def _generate_hard_constraint_comment(loss_name: str) -> str:
    """Generate comment for hard constraint."""
    return "  # Unchanged - hard constraint"


def _tune_weights(report: dict, base_config: dict) -> Tuple[dict, list]:
    """
    Tune weights based on correlation report.

    Args:
        report: Correlation analysis report
        base_config: Base configuration with current weights

    Returns:
        Tuple of (tuned_config, changes_list)
        changes_list: [(loss_name, original, new, reason), ...]
    """
    tuned = {"losses": {}}
    changes = []

    for loss_name, loss_config in base_config.get("losses", {}).items():
        original_weight = loss_config.get("weight", 1.0)
        r_completion = _get_correlation(report, loss_name)
        is_hard = _is_hard_constraint(loss_name)

        multiplier = _compute_multiplier(r_completion, loss_name, is_hard)
        new_weight = original_weight * multiplier

        tuned["losses"][loss_name] = {"weight": new_weight}

        # Track change
        if multiplier > 1.0:
            reason = f"Increased {multiplier}x (r={r_completion:.2f})"
        elif multiplier < 1.0:
            reason = f"Reduced {multiplier}x (r={r_completion:.2f})"
        elif is_hard:
            reason = "Unchanged - hard constraint"
        else:
            reason = f"Unchanged (r={r_completion:.2f})"

        changes.append((loss_name, original_weight, new_weight, reason))

    return tuned, changes


def _write_tuned_config(
    tuned_config: dict,
    base_config: dict,
    report: dict,
    report_path: Path,
    output_path: Path,
) -> None:
    """Write tuned configuration to YAML file with explanatory comments."""
    timestamp = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

    # Build YAML content manually to include comments
    lines = []
    lines.append(_generate_header(report_path, timestamp))
    lines.append("losses:\n")

    # Group hard constraints first
    hard_losses = []
    soft_losses = []

    for loss_name in tuned_config["losses"]:
        if _is_hard_constraint(loss_name):
            hard_losses.append(loss_name)
        else:
            soft_losses.append(loss_name)

    # Write hard constraints
    if hard_losses:
        lines.append("  # HARD CONSTRAINTS (never reduced)\n")
        for loss_name in sorted(hard_losses):
            original_weight = base_config["losses"][loss_name]["weight"]
            new_weight = tuned_config["losses"][loss_name]["weight"]
            lines.append(f"  {loss_name}:\n")
            lines.append(f"    weight: {new_weight}\n")
            lines.append(_generate_hard_constraint_comment(loss_name) + "\n")
            lines.append("\n")

    # Write tuned weights
    if soft_losses:
        lines.append("  # TUNED WEIGHTS\n")
        for loss_name in sorted(soft_losses):
            original_weight = base_config["losses"][loss_name]["weight"]
            new_weight = tuned_config["losses"][loss_name]["weight"]
            r_completion = _get_correlation(report, loss_name)
            is_hard = _is_hard_constraint(loss_name)
            multiplier = _compute_multiplier(r_completion, loss_name, is_hard)

            lines.append(f"  {loss_name}:\n")
            lines.append(f"    weight: {new_weight}\n")
            lines.append(
                _generate_loss_comment(
                    loss_name, original_weight, new_weight, r_completion, multiplier
                )
                + "\n"
            )
            lines.append("\n")

    # Write to file
    output_path.write_text("".join(lines))


def _display_dry_run(changes: list, output_path: Path) -> None:
    """Display changes without writing file."""
    print(f"\n{'=' * 70}")
    print(f"DRY RUN - Changes would be written to: {output_path}")
    print(f"{'=' * 70}\n")

    for loss_name, original, new, reason in changes:
        print(f"  {loss_name:20s}: {original:8.2f} → {new:8.2f}  ({reason})")

    print()


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Tune loss weights based on correlation analysis",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Tune weights from correlation report
  %(prog)s --correlation-report correlation_report.json \\
           --base-config configs/temper_constraints.yaml \\
           --output configs/temper_constraints_tuned.yaml

  # Preview changes without writing
  %(prog)s --correlation-report correlation_report.json \\
           --base-config configs/temper_constraints.yaml \\
           --output configs/temper_constraints_tuned.yaml \\
           --dry-run
        """,
    )

    parser.add_argument(
        "--correlation-report",
        type=Path,
        required=True,
        help="Path to correlation analysis JSON report",
    )

    parser.add_argument(
        "--base-config",
        type=Path,
        required=True,
        help="Path to base configuration YAML",
    )

    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Path to output tuned configuration YAML",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show changes without writing output file",
    )

    args = parser.parse_args()

    # Load correlation report
    if not args.correlation_report.exists():
        parser.error(f"Correlation report not found: {args.correlation_report}")

    with open(args.correlation_report) as f:
        report = json.load(f)

    # Load base config
    if not args.base_config.exists():
        parser.error(f"Base config not found: {args.base_config}")

    with open(args.base_config) as f:
        base_config = yaml.safe_load(f)

    if "losses" not in base_config:
        parser.error(f"Base config missing 'losses' section: {args.base_config}")

    # Tune weights
    tuned_config, changes = _tune_weights(report, base_config)

    # Display or write
    if args.dry_run:
        _display_dry_run(changes, args.output)
    else:
        _write_tuned_config(tuned_config, base_config, report, args.correlation_report, args.output)
        print(f"✓ Tuned configuration written to: {args.output}")
        print(f"  {len(changes)} losses adjusted based on correlation analysis")


if __name__ == "__main__":
    main()
=======
Loss weight tuning script.
Suggests loss weight adjustments based on correlation with routing success.
"""

import json
from pathlib import Path
import argparse
import sys

# Simplified logic for suggestion
# High absolute correlation -> Increase weight if it's not high enough
# Positive correlation with failure (higher loss = higher completion) -> Something is wrong
# Negative correlation with failure (higher loss = lower completion) -> Increase weight

def main():
    parser = argparse.ArgumentParser(description="Suggest loss weight adjustments")
    parser.add_argument("--data", type=str, default="metrics/measurements.jsonl", help="Path to measurements.jsonl")
    args = parser.parse_args()

    # In a real implementation, this would use the output of correlation_analysis.py
    # and provide specific numerical suggestions.
    
    print("Loss Weight Suggestions (Experimental)")
    print("-" * 40)
    print("1. Increase 'overlap_loss' weight if completion < 100%")
    print("2. Increase 'boundary_loss' weight if components are off-board")
    print("3. Decrease 'wirelength_loss' if it causes massive overlap pileups")
    print("\nRun 'scripts/correlation_analysis.py' to see empirical data.")

if __name__ == "__main__":
    main()

>>>>>>> 2d319f0 (feat(placer): NSGA-II, Crawler, NetCentroidLoss, and structural refinements)
