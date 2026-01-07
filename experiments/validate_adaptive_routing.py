#!/usr/bin/env python3.11
"""
Validation script for adaptive A* iteration budgeting.

Compares routing results with adaptive congestion-aware budgeting
against the baseline (fixed 50k iteration limit).

Expected improvements:
- SPI_CLK: 8 → 0-2 unconnected (was timing out at 7,757 iters with fixed limit)
- +5V: 22 → 5-10 unconnected (was timing out at 14,240 iters)
- Total: 81 → <50 unconnected (~38% improvement)
"""

import json
import sys
from pathlib import Path
from collections import defaultdict


def load_drc_report(path: Path) -> dict:
    """Load DRC report JSON and extract unconnected items."""
    with open(path) as f:
        return json.load(f)


def analyze_unconnected(drc_report: dict) -> dict:
    """Analyze unconnected items by net."""
    import re

    by_net = defaultdict(int)
    for item in drc_report.get("unconnected_items", []):
        # Try old format first
        net = item.get("net")

        # If no direct net field, parse from description
        if not net and "items" in item:
            for sub_item in item["items"]:
                desc = sub_item.get("description", "")
                # Parse net from description like "Pad 2 [GND] of U_MCU on F.Cu"
                match = re.search(r"\[([^\]]+)\]", desc)
                if match:
                    net = match.group(1)
                    break

        if not net:
            net = "unknown"

        by_net[net] += 1
    return dict(by_net)


def print_comparison(baseline_path: Path, adaptive_path: Path):
    """Print comparison between baseline and adaptive routing."""

    # Load reports
    baseline = load_drc_report(baseline_path)
    adaptive = load_drc_report(adaptive_path)

    # Analyze by net
    baseline_by_net = analyze_unconnected(baseline)
    adaptive_by_net = analyze_unconnected(adaptive)

    # Total counts
    baseline_total = len(baseline.get("unconnected_items", []))
    adaptive_total = len(adaptive.get("unconnected_items", []))

    # Print header
    print("=" * 80)
    print("ADAPTIVE A* ROUTING VALIDATION")
    print("=" * 80)
    print()

    # Total summary
    improvement = baseline_total - adaptive_total
    pct = (improvement / baseline_total * 100) if baseline_total > 0 else 0

    print(f"TOTAL UNCONNECTED ITEMS:")
    print(f"  Baseline: {baseline_total}")
    print(f"  Adaptive: {adaptive_total}")
    print(f"  Improvement: {improvement} ({pct:.1f}% reduction)")
    print()

    # Target check
    target_met = adaptive_total < 50
    print(f"TARGET (<50 unconnected): {'✓ PASS' if target_met else '✗ FAIL'}")
    print()

    # Per-net breakdown for critical nets
    critical_nets = ["SPI_CLK", "+5V", "+3V3", "VCC_BOOT", "USB_D+", "USB_D-"]

    print("CRITICAL NET IMPROVEMENTS:")
    print(f"{'Net':<15} {'Baseline':>10} {'Adaptive':>10} {'Change':>10} {'Status':>10}")
    print("-" * 60)

    for net in critical_nets:
        baseline_count = baseline_by_net.get(net, 0)
        adaptive_count = adaptive_by_net.get(net, 0)
        change = baseline_count - adaptive_count

        if baseline_count == 0 and adaptive_count == 0:
            status = "N/A"
        elif adaptive_count == 0:
            status = "✓ FIXED"
        elif change > 0:
            status = "✓ BETTER"
        elif change == 0:
            status = "= SAME"
        else:
            status = "✗ WORSE"

        print(f"{net:<15} {baseline_count:>10} {adaptive_count:>10} {change:>+10} {status:>10}")

    print()

    # Top 10 worst nets in adaptive routing
    print("TOP 10 REMAINING UNCONNECTED (Adaptive):")
    print(f"{'Net':<20} {'Count':>10}")
    print("-" * 35)

    sorted_adaptive = sorted(adaptive_by_net.items(), key=lambda x: -x[1])[:10]
    for net, count in sorted_adaptive:
        print(f"{net:<20} {count:>10}")

    print()
    print("=" * 80)

    # Return status code
    return 0 if target_met else 1


if __name__ == "__main__":
    baseline_path = Path("output/test_power_trace/iteration_1_drc.json")
    adaptive_path = Path("output/test_adaptive/iteration_1_drc.json")

    if not baseline_path.exists():
        print(f"ERROR: Baseline report not found: {baseline_path}", file=sys.stderr)
        sys.exit(2)

    if not adaptive_path.exists():
        print(f"ERROR: Adaptive report not found: {adaptive_path}", file=sys.stderr)
        print(f"Run: python3.11 scripts/run_feedback_loop.py \\", file=sys.stderr)
        print(f"  --config configs/temper_deterministic_config.yaml \\", file=sys.stderr)
        print(f"  --board data/temper.kicad_pcb \\", file=sys.stderr)
        print(f"  --output output/test_adaptive \\", file=sys.stderr)
        print(f"  --max-iterations 1", file=sys.stderr)
        sys.exit(2)

    sys.exit(print_comparison(baseline_path, adaptive_path))
