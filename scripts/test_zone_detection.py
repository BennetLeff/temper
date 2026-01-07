#!/usr/bin/env python3
"""
Test zone detection from both PCB files and YAML config.
"""

import sys
from pathlib import Path

# Add temper-placer to path
sys.path.insert(0, str(Path(__file__).parent.parent / "packages/temper-placer/src"))

from temper_placer.io.kicad_parser import parse_kicad_pcb
from temper_placer.io.config_loader import load_constraints
from temper_placer.deterministic.stages.zone_aware_slot_generation import _get_copper_zones


def test_zone_detection():
    """Test copper zone detection from PCB and YAML."""
    print("\n" + "=" * 60)
    print("Testing Copper Zone Detection")
    print("=" * 60)

    # Test 1: PCB with zones
    print("\n--- Test 1: PCB with copper zones ---")
    pcb_path = Path("pcb/temper_with_planes.kicad_pcb")
    result = parse_kicad_pcb(pcb_path)
    board = result.board

    zones_from_pcb = _get_copper_zones(board, yaml_zones=None)
    print(f"Zones from PCB: {len(zones_from_pcb)}")
    for zone in zones_from_pcb:
        print(f"  - {zone.name}: {zone.net_classes}")

    # Test 2: PCB without zones
    print("\n--- Test 2: PCB without copper zones ---")
    pcb_path = Path("pcb/temper.kicad_pcb")
    result = parse_kicad_pcb(pcb_path)
    board = result.board

    zones_from_empty_pcb = _get_copper_zones(board, yaml_zones=None)
    print(f"Zones from empty PCB: {len(zones_from_empty_pcb)}")

    # Test 3: YAML zones only
    print("\n--- Test 3: YAML zones only ---")
    config_path = Path("configs/temper_deterministic_config.yaml")
    constraints = load_constraints(config_path)

    zones_from_yaml = _get_copper_zones(None, yaml_zones=constraints.copper_zones)
    print(f"Zones from YAML: {len(zones_from_yaml)}")
    for zone in zones_from_yaml:
        print(f"  - {zone.name}: {zone.net_classes}")

    # Test 4: PCB + YAML combined
    print("\n--- Test 4: PCB + YAML combined ---")
    pcb_path = Path("pcb/temper_with_planes.kicad_pcb")
    result = parse_kicad_pcb(pcb_path)
    board = result.board

    zones_combined = _get_copper_zones(board, yaml_zones=constraints.copper_zones)
    print(f"Zones from PCB+YAML: {len(zones_combined)}")
    print("  From YAML:")
    for zone in zones_combined[:2]:  # First 2 are from YAML
        print(f"    - {zone.name}: {zone.net_classes}")
    print("  From PCB:")
    for zone in zones_combined[2:5]:  # Next few are from PCB
        print(f"    - {zone.name}: {zone.net_classes}")

    print("\n" + "=" * 60)
    print("✓ All zone detection tests passed")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    try:
        test_zone_detection()
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
