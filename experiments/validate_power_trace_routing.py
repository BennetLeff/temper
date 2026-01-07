"""
Validation script for power trace routing (Task temper-zy08).

Tests that changing +5V and +3V3 from plane to trace routing
reduces unconnected items.
"""

import json
import subprocess
import sys
from pathlib import Path


def run_feedback_loop(output_dir: str = "output/test_power_trace") -> dict:
    """Run feedback loop and return DRC results."""
    print(f"Running feedback loop with output to {output_dir}...")

    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_feedback_loop.py",
            "--max-iterations",
            "1",
            "--output-dir",
            output_dir,
        ],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent,
    )

    if result.returncode != 0:
        print(f"ERROR: Feedback loop failed")
        print(f"STDOUT:\n{result.stdout}")
        print(f"STDERR:\n{result.stderr}")
        return {}

    # Load DRC report
    drc_path = Path(output_dir) / "iteration_1_drc.json"
    if not drc_path.exists():
        print(f"ERROR: DRC report not found at {drc_path}")
        return {}

    with open(drc_path) as f:
        return json.load(f)


def count_unconnected_by_net(drc: dict) -> dict[str, int]:
    """Count unconnected items grouped by net."""
    import re
    from collections import Counter

    net_counts = Counter()
    for item in drc.get("unconnected_items", []):
        for detail in item["items"]:
            match = re.search(r"\[([^\]]+)\]", detail["description"])
            if match:
                net_counts[match.group(1)] += 1

    return dict(net_counts)


def main():
    print("=" * 70)
    print("Power Trace Routing Validation (temper-zy08)")
    print("=" * 70)
    print()

    # Baseline: Load previous results
    baseline_path = Path("output/test5/iteration_1_drc.json")
    if baseline_path.exists():
        print(f"Loading baseline DRC from {baseline_path}...")
        with open(baseline_path) as f:
            baseline_drc = json.load(f)
        baseline_counts = count_unconnected_by_net(baseline_drc)
        baseline_total = len(baseline_drc.get("unconnected_items", []))
    else:
        print("WARNING: No baseline found, skipping comparison")
        baseline_counts = {}
        baseline_total = 0

    # Test: Run with new config
    test_drc = run_feedback_loop("output/test_power_trace")
    if not test_drc:
        print("FAILED: Could not run feedback loop")
        return 1

    test_counts = count_unconnected_by_net(test_drc)
    test_total = len(test_drc.get("unconnected_items", []))

    # Compare results
    print()
    print("=" * 70)
    print("Results Comparison")
    print("=" * 70)
    print()

    if baseline_counts:
        print(f"{'Net':<20s} {'Baseline':<10s} {'Test':<10s} {'Change':<10s}")
        print("-" * 60)

        all_nets = sorted(set(baseline_counts.keys()) | set(test_counts.keys()))
        for net in all_nets:
            baseline = baseline_counts.get(net, 0)
            test = test_counts.get(net, 0)
            change = test - baseline

            # Color code: green for improvement, red for regression
            if change < 0:
                change_str = f"✓ {change:+d}"
            elif change > 0:
                change_str = f"✗ {change:+d}"
            else:
                change_str = "="

            print(f"{net:<20s} {baseline:<10d} {test:<10d} {change_str:<10s}")

        print("-" * 60)
        print(
            f"{'TOTAL':<20s} {baseline_total:<10d} {test_total:<10d} {test_total - baseline_total:+10d}"
        )
    else:
        print(f"Test total unconnected: {test_total}")

    # Validate expected improvements
    print()
    print("=" * 70)
    print("Validation Checks")
    print("=" * 70)
    print()

    power_nets = ["+5V", "+3V3"]
    power_unconnected = sum(test_counts.get(net, 0) for net in power_nets)
    baseline_power = 0

    if baseline_counts:
        baseline_power = sum(baseline_counts.get(net, 0) for net in power_nets)
        print(f"✓ Power net unconnected (+5V, +3V3): {baseline_power} → {power_unconnected}")

        if power_unconnected < baseline_power:
            print(f"✓ PASS: Power nets improved by {baseline_power - power_unconnected} items")
        else:
            print(f"✗ FAIL: Power nets did not improve")
    else:
        print(f"  Power net unconnected (+5V, +3V3): {power_unconnected}")

    # Check that +15V is still using plane
    print()
    print("Checking +15V plane connectivity...")
    kicad_pcb = Path("output/test_power_trace/iteration_1.kicad_pcb")
    if kicad_pcb.exists():
        with open(kicad_pcb) as f:
            pcb_text = f.read()

        # Look for zone with +15V net
        if '(net_name "+15V")' in pcb_text and "(zone" in pcb_text:
            print("✓ +15V plane zone found in board")
        else:
            print("✗ WARNING: +15V plane zone not found")

    print()
    print("=" * 70)

    if baseline_counts and power_unconnected < baseline_power:
        print("✓ VALIDATION PASSED")
        return 0
    elif not baseline_counts:
        print("⚠ VALIDATION INCOMPLETE (no baseline)")
        return 0
    else:
        print("✗ VALIDATION FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())
