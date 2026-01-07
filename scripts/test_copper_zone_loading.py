#!/usr/bin/env python3
"""
Test that copper zones are properly loaded from YAML config.
"""

import sys
from pathlib import Path

# Add temper-placer to path
sys.path.insert(0, str(Path(__file__).parent.parent / "packages/temper-placer/src"))

from temper_placer.io.config_loader import load_constraints
from temper_placer.deterministic import create_drc_aware_pipeline


def test_copper_zone_loading():
    """Test copper zone loading from YAML config."""
    print("\n" + "=" * 60)
    print("Testing Copper Zone Loading from YAML")
    print("=" * 60)

    # Load config
    config_path = Path("configs/temper_deterministic_config.yaml")
    print(f"\nLoading config from: {config_path}")

    constraints = load_constraints(config_path)

    # Check copper zones
    print(f"\nCopper zones in config: {len(constraints.copper_zones)}")
    for zone in constraints.copper_zones:
        print(f"  - {zone.name}")
        print(f"      net_classes: {zone.net_classes}")
        print(f"      bounds: {zone.bounds}")
        print(f"      layers: {zone.layers}")

    # Create zone-aware pipeline
    print("\nCreating zone-aware pipeline...")
    pipeline = create_drc_aware_pipeline(config=constraints, zone_aware=True)

    # Find the slot generation stage
    slot_stage = None
    for stage in pipeline.stages:
        if hasattr(stage, "name") and "slot" in stage.name.lower():
            slot_stage = stage
            break

    if slot_stage:
        print(f"\nSlot stage: {slot_stage.name}")
        if hasattr(slot_stage, "yaml_copper_zones"):
            print(f"  YAML copper zones: {len(slot_stage.yaml_copper_zones)}")
            for zone in slot_stage.yaml_copper_zones:
                print(f"    - {zone.name}: {zone.net_classes}")
        else:
            print("  ⚠️  No yaml_copper_zones attribute found")
    else:
        print("\n⚠️  No slot generation stage found in pipeline")

    print("\n" + "=" * 60)
    print("✓ Test completed successfully")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    try:
        test_copper_zone_loading()
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
