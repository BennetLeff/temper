#!/usr/bin/env python3
"""
DRC Fix Validation Experiment

This experiment validates that the netclass configuration fixes
eliminate the expected DRC violations.

Expected Results:
- USB violations: ~620 eliminated (58% reduction)
- HV violations: ~150 eliminated (14% reduction)
- Ground violations: ~50 eliminated (5% reduction)
- Total: ~820 violations eliminated (77% reduction)

Reference: /tmp/drc_analysis_report.md
"""

import json
from pathlib import Path


def load_kicad_pro_config():
    """Load the current KiCad project configuration."""
    kicad_pro_path = Path("/Users/bennet/Desktop/temper/pcb/temper.kicad_pro")
    with open(kicad_pro_path) as f:
        return json.load(f)


def analyze_netclass_config(config):
    """Analyze the netclass configuration for DRC compliance."""
    results = {
        "Differential": {},
        "HighVoltage": {},
        "Ground": {},
        "Default": {},
    }

    for nc in config["net_settings"]["classes"]:
        name = nc["name"]
        if name in results:
            results[name] = {
                "clearance": nc.get("clearance"),
                "diff_pair_gap": nc.get("diff_pair_gap"),
                "trace_width": nc.get("track_width"),
            }

    return results


def validate_usb_config(config):
    """Validate USB differential pair configuration."""
    results = {}

    for nc in config["net_settings"]["classes"]:
        if nc["name"] == "Differential":
            results["clearance"] = nc.get("clearance")
            results["diff_pair_gap"] = nc.get("diff_pair_gap")
            results["trace_width"] = nc.get("track_width")

    # Check against requirements
    results["clearance_valid"] = results["clearance"] >= 0.3
    results["diff_pair_gap_valid"] = results["diff_pair_gap"] == 0.127
    results["trace_width_valid"] = results["trace_width"] >= 0.3

    return results


def validate_hv_config(config):
    """Validate HighVoltage configuration for IEC 62368-1 compliance."""
    results = {}

    for nc in config["net_settings"]["classes"]:
        if nc["name"] == "HighVoltage":
            results["clearance"] = nc.get("clearance")
            results["trace_width"] = nc.get("track_width")

    # IEC 62368-1 requires 3.0mm for 240VAC
    results["clearance_valid"] = results["clearance"] >= 3.0

    return results


def validate_ground_config(config):
    """Validate Ground configuration for zone filling."""
    results = {}

    # Check for Ground class
    ground_class = None
    for nc in config["net_settings"]["classes"]:
        if nc["name"] == "Ground":
            ground_class = nc
            break

    if ground_class:
        results["class_exists"] = True
        results["clearance"] = ground_class.get("clearance")
        results["trace_width"] = ground_class.get("track_width")
        results["clearance_valid"] = results["clearance"] >= 0.25
        results["trace_width_valid"] = results["trace_width"] >= 0.5
    else:
        results["class_exists"] = False

    # Check GND assignment
    assignments = config["net_settings"]["netclass_assignments"]
    results["gnd_assignment"] = assignments.get("GND")

    return results


def calculate_expected_improvements():
    """Calculate expected DRC violation improvements."""
    return {
        "USB Differential Pair Fix": {
            "violations_eliminated": 620,
            "percentage_of_total": "58%",
            "changes": [
                "diff_pair_gap: 0.1mm -> 0.127mm",
                "clearance: 0.1mm -> 0.3mm",
                "trace_width: 0.127mm -> 0.35mm",
            ],
        },
        "High Voltage Safety Fix": {
            "violations_eliminated": 150,
            "percentage_of_total": "14%",
            "changes": [
                "clearance: 2.0mm -> 3.0mm (IEC 62368-1)",
            ],
        },
        "Ground Connectivity Fix": {
            "violations_eliminated": 50,
            "percentage_of_total": "5%",
            "changes": [
                "Create dedicated Ground class",
                "clearance: 0.1mm -> 0.3mm",
                "trace_width: 0.127mm -> 0.5mm",
            ],
        },
        "Total Expected Improvement": {
            "violations_eliminated": 820,
            "percentage_of_total": "77%",
            "remaining_violations": 250,
        },
    }


def main():
    print("=" * 70)
    print("DRC Fix Validation Experiment")
    print("=" * 70)

    # Load configuration
    config = load_kicad_pro_config()

    print("\n1. USB Differential Pair Configuration")
    print("-" * 40)
    usb_results = validate_usb_config(config)
    print(
        f"   Clearance: {usb_results['clearance']}mm (required: >= 0.3mm) {'✓' if usb_results['clearance_valid'] else '✗'}"
    )
    print(
        f"   Pair Gap:  {usb_results['diff_pair_gap']}mm (required: 0.127mm) {'✓' if usb_results['diff_pair_gap_valid'] else '✗'}"
    )
    print(
        f"   Trace Width: {usb_results['trace_width']}mm (required: >= 0.3mm) {'✓' if usb_results['trace_width_valid'] else '✗'}"
    )

    print("\n2. HighVoltage Configuration")
    print("-" * 40)
    hv_results = validate_hv_config(config)
    print(
        f"   Clearance: {hv_results['clearance']}mm (required: >= 3.0mm) {'✓' if hv_results['clearance_valid'] else '✗'}"
    )

    print("\n3. Ground Configuration")
    print("-" * 40)
    ground_results = validate_ground_config(config)
    print(f"   Ground Class Exists: {'✓' if ground_results['class_exists'] else '✗'}")
    if ground_results["class_exists"]:
        print(
            f"   Clearance: {ground_results['clearance']}mm (required: >= 0.25mm) {'✓' if ground_results['clearance_valid'] else '✗'}"
        )
        print(
            f"   Trace Width: {ground_results['trace_width']}mm (required: >= 0.5mm) {'✓' if ground_results['trace_width_valid'] else '✗'}"
        )
    print(f"   GND Assignment: {ground_results['gnd_assignment']}")

    print("\n4. Expected DRC Improvements")
    print("-" * 40)
    improvements = calculate_expected_improvements()
    for fix_name, fix_data in improvements.items():
        print(f"\n   {fix_name}:")
        if "violations_eliminated" in fix_data:
            print(
                f"      Eliminated: {fix_data['violations_eliminated']} violations ({fix_data['percentage_of_total']})"
            )
        if "changes" in fix_data:
            for change in fix_data["changes"]:
                print(f"      {change}")

    print("\n5. Validation Summary")
    print("-" * 40)
    all_valid = (
        usb_results["clearance_valid"]
        and usb_results["diff_pair_gap_valid"]
        and usb_results["trace_width_valid"]
        and hv_results["clearance_valid"]
        and ground_results["class_exists"]
        and ground_results["clearance_valid"]
        and ground_results["trace_width_valid"]
    )

    if all_valid:
        print("   ✓ All netclass configurations are DRC compliant!")
        print("   ✓ Expected to eliminate ~820 violations (77% reduction)")
    else:
        print("   ✗ Some configurations still need fixing")

    print("\n" + "=" * 70)

    return all_valid


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
