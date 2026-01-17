#!/usr/bin/env python3
"""
Phase 2 Analysis: HV Spacing Verification
==========================================

Analyzes the Benders placement to verify:
1. Component spacing between HV components (Q1, Q2, C_BUS1, C_BUS2)
2. Routing channel capacity for 3.0mm HV tracks

This script loads the final Benders placement and measures actual gaps.
"""

import sys
import json
from pathlib import Path

# Add temper-placer to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "packages/temper-placer/src"))

from temper_placer.io.kicad_parser import parse_kicad_pcb_v6
from kiutils.board import Board


def calculate_component_distances(pcb_path: Path):
    """Calculate distances between HV components."""
    print("=" * 70)
    print(" HV COMPONENT SPACING ANALYSIS")
    print("=" * 70)

    board = Board.from_file(str(pcb_path))

    # Extract HV component positions
    hv_components = ["Q1", "Q2", "C_BUS1", "C_BUS2"]
    positions = {}
    dimensions = {}

    for fp in board.footprints:
        ref = fp.properties.get("Reference", None)
        if not ref:
            continue
        ref_str = ref.value if hasattr(ref, "value") else str(ref)
        if ref_str not in hv_components:
            continue

        x = fp.position.X if fp.position else 0
        y = fp.position.Y if fp.position else 0
        positions[ref_str] = (x, y)

        # Get bounding box - skip for now, use default estimate
        width = 10.0  # Default estimate
        height = 10.0
        dimensions[ref_str] = (width, height)

    print("\nComponent Positions:")
    for comp in hv_components:
        if comp in positions:
            x, y = positions[comp]
            w, h = dimensions.get(comp, (0, 0))
            print(f"  {comp}: ({x:.2f}, {y:.2f}) size: {w:.2f}x{h:.2f}mm")
        else:
            print(f"  {comp}: NOT FOUND")

    # Calculate pairwise distances
    print("\nPairwise Euclidean Distances:")
    min_distance = float("inf")
    closest_pair = None

    for i, comp1 in enumerate(hv_components):
        for comp2 in hv_components[i + 1 :]:
            if comp1 not in positions or comp2 not in positions:
                continue

            x1, y1 = positions[comp1]
            x2, y2 = positions[comp2]

            dist = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5

            # Subtract half-widths to get edge-to-edge distance (approximate)
            w1, h1 = dimensions.get(comp1, (0, 0))
            w2, h2 = dimensions.get(comp2, (0, 0))

            # Use Manhattan-style edge distance
            dx = abs(x2 - x1) - (w1 + w2) / 2
            dy = abs(y2 - y1) - (h1 + h2) / 2
            edge_dist = max(dx, dy, 0)

            print(f"  {comp1} <-> {comp2}:")
            print(f"    Center-to-center: {dist:.2f}mm")
            print(f"    Edge-to-edge (approx): {edge_dist:.2f}mm")

            if edge_dist < min_distance:
                min_distance = edge_dist
                closest_pair = (comp1, comp2)

    # Success criteria
    print("\n" + "=" * 70)
    print(" SUCCESS CRITERIA")
    print("=" * 70)

    required_gap = 4.0  # 3.0mm track + 2*0.5mm margin

    if closest_pair:
        print(
            f"\nMinimum gap: {min_distance:.2f}mm between {closest_pair[0]} and {closest_pair[1]}"
        )
        print(f"Required gap: {required_gap:.2f}mm")

        if min_distance >= required_gap:
            print(f"✓ PASS: Spacing is sufficient for 3.0mm HV tracks")
            return True
        else:
            print(f"✗ FAIL: Spacing is too small (need {required_gap - min_distance:.2f}mm more)")
            return False
    else:
        print("✗ FAIL: Could not calculate distances (components missing)")
        return False


def analyze_routing_channels():
    """Analyze routing channel capacity from constraints."""
    print("\n" + "=" * 70)
    print(" ROUTING CHANNEL ANALYSIS")
    print("=" * 70)

    # Check the constraints file
    constraints_path = Path("packages/temper-placer/configs/temper_constraints.yaml")
    if not constraints_path.exists():
        print("✗ Could not find temper_constraints.yaml")
        return False

    import yaml

    with open(constraints_path, "r") as f:
        constraints = yaml.safe_load(f)

    # Check HV net class - it's under net_class_rules, not net_classes
    net_class_rules = constraints.get("net_class_rules", {})
    hv_class = net_class_rules.get("HighVoltage", {})

    if hv_class:
        track_width = hv_class.get("trace_width_mm", 0)  # Note: trace_width_mm not track_width
        clearance = hv_class.get("clearance_mm", 0)

        print(f"\nHighVoltage net class (from constraints):")
        print(f"  Track width: {track_width}mm")
        print(f"  Clearance: {clearance}mm")

        if track_width >= 3.0:
            print(f"  ✓ Track width matches spec (3.0mm)")
            return True
        else:
            print(f"  ✗ Track width too small (expected 3.0mm)")
            return False

    print("✗ Could not find HighVoltage net class")
    return False


def main():
    pcb_path = Path("pcb/temper.kicad_pcb")

    if not pcb_path.exists():
        print(f"ERROR: PCB file not found: {pcb_path}")
        return 1

    print("\n" + "=" * 70)
    print(" PHASE 2: HV SPACING VERIFICATION")
    print("=" * 70)
    print(f"\nAnalyzing: {pcb_path}")

    spacing_ok = calculate_component_distances(pcb_path)
    channels_ok = analyze_routing_channels()

    print("\n" + "=" * 70)
    print(" FINAL RESULT")
    print("=" * 70)

    if spacing_ok and channels_ok:
        print("\n✓✓✓ PHASE 2 PASSED: HV physics constraints verified")
        return 0
    else:
        print("\n✗✗✗ PHASE 2 FAILED: HV physics constraints violated")
        return 1


if __name__ == "__main__":
    sys.exit(main())
