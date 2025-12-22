#!/usr/bin/env python3
"""
Loss Weight Tuning Script

Adjusts loss function weights based on correlation analysis results.
Automatically updates configuration files to improve optimizer performance.

Usage:
    python scripts/tune_loss_weights.py --correlation-report correlation_report.json --config current_config.yaml
"""

import argparse
import json
from pathlib import Path
from typing import Any

import yaml


def load_correlation_report(report_path: Path) -> dict[str, Any]:
    """Load correlation analysis JSON report."""
    with open(report_path) as f:
        return json.load(f)


def load_config(config_path: Path) -> dict[str, Any]:
    """Load optimizer configuration YAML."""
    with open(config_path) as f:
        return yaml.safe_load(f)


def tune_weights(
    current_config: dict[str, Any],
    report: dict[str, Any],
    learning_rate: float = 0.1,
    max_multiplier: float = 10.0,
    min_multiplier: float = 0.1,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """
    Adjust weights based on correlations.

    Strategy:
    - Weight_new = Weight_old * (1.0 - correlation * learning_rate)
    - If correlation is negative (Loss ↑, Completion ↓), weight increases.
    - If correlation is positive, weight decreases.
    """
    new_config = current_config.copy()
    if "losses" not in new_config:
        new_config["losses"] = {}

    changes = []
    correlations = report["correlations"]

    for loss_name, metrics in correlations.items():
        if loss_name == "total_loss":
            continue

        # Use completion correlation as primary signal
        corr = metrics["completion"]
        
        # Skip low correlations
        if abs(corr) < 0.1:
            continue

        # Get current weight
        old_weight = current_config.get("losses", {}).get(loss_name, 1.0)
        
        # Compute multiplier
        # Negative correlation -> Increase weight
        multiplier = 1.0 - (corr * learning_rate)
        multiplier = max(min_multiplier, min(max_multiplier, multiplier))
        
        new_weight = old_weight * multiplier
        
        # Don't reduce weights of known hard constraints below 1.0
        hard_constraints = {"overlap", "boundary", "clearance"}
        if loss_name in hard_constraints:
            new_weight = max(1.0, new_weight)

        new_config["losses"][loss_name] = round(float(new_weight), 4)
        
        changes.append({
            "loss": loss_name,
            "old": old_weight,
            "new": new_config["losses"][loss_name],
            "correlation": corr,
            "change_pct": (multiplier - 1.0) * 100.0
        })

    return new_config, changes


def _display_dry_run(changes: list[dict[str, Any]], output_path: Path):
    """Print proposed changes without writing."""
    print(f"=== Proposed Weight Tuning for {output_path.name} ===")
    print(f"{ 'Loss Function':<25} | { 'Old':>8} | { 'New':>8} | { 'Corr':>6} | {'Change'}")
    print("-" * 65)
    
    for c in sorted(changes, key=lambda x: abs(x["change_pct"]), reverse=True):
        print(f"{c['loss']:<25} | {c['old']:>8.2f} | {c['new']:>8.2f} | {c['correlation']:>6.2f} | {c['change_pct']:>+6.1f}%")


def _write_tuned_config(
    new_config: dict[str, Any],
    base_config: dict[str, Any],
    report: dict[str, Any],
    report_path: Path,
    output_path: Path
):
    """Write updated configuration with metadata."""
    # Add metadata about tuning
    if "metadata" not in new_config:
        new_config["metadata"] = {}
    
    new_config["metadata"]["tuned_from"] = report_path.name
    new_config["metadata"]["tuned_at"] = datetime.now().isoformat()
    new_config["metadata"]["samples"] = report["n_samples"]

    with open(output_path, "w") as f:
        # Header comment
        f.write(f"# Auto-tuned weights based on {report_path.name}\n")
        f.write(f"# Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        yaml.dump(new_config, f, sort_keys=False)


def main():
    from datetime import datetime
    parser = argparse.ArgumentParser(description="Tune loss weights based on correlation analysis.")
    parser.add_argument("--correlation-report", "-r", type=str, required=True, help="JSON report from analysis")
    parser.add_argument("--config", "-c", type=str, required=True, help="Current configuration YAML")
    parser.add_argument("--output", "-o", type=str, help="Output configuration file")
    parser.add_argument("--lr", type=float, default=0.2, help="Adjustment sensitivity")
    parser.add_argument("--dry-run", action="store_true", help="Display changes without writing")

    args = parser.parse_args()

    report_path = Path(args.correlation_report)
    config_path = Path(args.config)
    output_path = Path(args.output) if args.output else config_path

    if not report_path.exists():
        print(f"Error: Report not found: {report_path}")
        sys.exit(1)
    
    if not config_path.exists():
        print(f"Error: Config not found: {config_path}")
        sys.exit(1)

    # Load data
    report = load_correlation_report(report_path)
    base_config = load_config(config_path)

    # Tune
    tuned_config, changes = tune_weights(base_config, report, learning_rate=args.lr)

    # Display or write
    if args.dry_run:
        _display_dry_run(changes, output_path)
    else:
        _write_tuned_config(tuned_config, base_config, report, report_path, output_path)
        print(f"✓ Tuned configuration written to: {output_path}")
        print(f"  {len(changes)} losses adjusted based on correlation analysis")


if __name__ == "__main__":
    main()