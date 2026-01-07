#!/usr/bin/env python3
"""
Test script for zone-aware placement integration.

Tests both:
1. MazeRouter workflow with ZoneAwareSpectralInitializer
2. DeterministicPipeline with ZoneAwareSlotGenerationStage
"""

import sys
from pathlib import Path

# Add src to path if needed
src_path = Path(__file__).parent.parent / "packages" / "temper-placer" / "src"
if src_path.exists():
    sys.path.insert(0, str(src_path))


def test_zone_aware_config():
    """Test zone-aware configuration."""
    print("\n=== Testing Zone-Aware Config ===")

    from temper_placer.optimizer.config import InitializationConfig, ZoneAwareConfig

    # Default config
    cfg = InitializationConfig()
    assert cfg.method == "random"
    print(f"✓ Default method: {cfg.method}")

    # Zone-aware spectral config
    cfg = InitializationConfig(
        method="zone_aware_spectral",
        zone_aware=ZoneAwareConfig(
            zone_penalty=15.0,
            boundary_margin=4.0,
            adjustment_iters=100,
        ),
    )
    assert cfg.method == "zone_aware_spectral"
    assert cfg.zone_aware.zone_penalty == 15.0
    print(f"✓ Zone-aware method configured: penalty={cfg.zone_aware.zone_penalty}")

    return True


def test_zone_aware_initializer():
    """Test ZoneAwareSpectralInitializer."""
    print("\n=== Testing ZoneAwareSpectralInitializer ===")

    from temper_placer.optimizer import ZoneAwareSpectralInitializer

    initializer = ZoneAwareSpectralInitializer(
        normalized_laplacian=True,
        margin_fraction=0.1,
        zone_penalty=10.0,
        boundary_margin=3.0,
        adjustment_iters=50,
    )

    print(f"✓ ZoneAwareSpectralInitializer created")
    print(f"  - zone_penalty: {initializer.zone_penalty}")
    print(f"  - boundary_margin: {initializer.boundary_margin}")
    print(f"  - adjustment_iters: {initializer.adjustment_iters}")

    return True


def test_zone_aware_slot_stage():
    """Test ZoneAwareSlotGenerationStage."""
    print("\n=== Testing ZoneAwareSlotGenerationStage ===")

    from temper_placer.deterministic.stages import (
        ZoneAwareSlotGenerationStage,
        RoutingChannelAwareSlotStage,
    )

    stage = ZoneAwareSlotGenerationStage(
        slot_spacing_mm=5.0,
        copper_zone_margin=2.0,
        min_routing_channel=3.0,
    )

    print(f"✓ ZoneAwareSlotGenerationStage created")
    print(f"  - name: {stage.name}")
    print(f"  - slot_spacing_mm: {stage.slot_spacing_mm}")
    print(f"  - copper_zone_margin: {stage.copper_zone_margin}")

    # Also test the extended stage
    channel_stage = RoutingChannelAwareSlotStage(
        slot_spacing_mm=5.0,
        channel_density_threshold=0.6,
    )
    print(f"✓ RoutingChannelAwareSlotStage created")
    print(f"  - name: {channel_stage.name}")

    return True


def test_pipeline_creation():
    """Test creating zone-aware pipeline."""
    print("\n=== Testing Pipeline Creation ===")

    from temper_placer.deterministic import create_drc_aware_pipeline

    # Standard pipeline
    pipeline = create_drc_aware_pipeline(zone_aware=False)
    slot_stages = [s for s in pipeline.stages if "slot" in s.name.lower()]
    print(f"✓ Standard pipeline: {len(pipeline.stages)} stages")
    print(f"  - Slot stage: {slot_stages[0].name if slot_stages else 'none'}")

    # Zone-aware pipeline
    pipeline_za = create_drc_aware_pipeline(zone_aware=True)
    slot_stages_za = [s for s in pipeline_za.stages if "slot" in s.name.lower()]
    print(f"✓ Zone-aware pipeline: {len(pipeline_za.stages)} stages")
    print(f"  - Slot stage: {slot_stages_za[0].name if slot_stages_za else 'none'}")

    # Verify different slot stages
    assert slot_stages[0].name != slot_stages_za[0].name, "Should use different slot stages"
    print(f"✓ Pipelines use different slot generation stages")

    return True


def test_zone_cost_field():
    """Test zone cost field creation."""
    print("\n=== Testing Zone Cost Field ===")

    from temper_placer.optimizer.zone_aware_init import create_zone_cost_field
    from temper_placer.core.board import Board

    # Create a simple board
    board = Board(
        width=100.0,
        height=100.0,
        origin=(0, 0),
    )

    # No zones - should return uniform cost
    cost_field, grid_size, cell_size = create_zone_cost_field(
        board=board,
        zones=None,
        grid_resolution=1.0,
    )

    print(f"✓ Zone cost field created (no zones)")
    print(f"  - Grid size: {grid_size}")
    print(f"  - Cell size: {cell_size}mm")
    print(f"  - Cost range: [{float(cost_field.min()):.2f}, {float(cost_field.max()):.2f}]")

    # All costs should be 1.0 (uniform) when no zones
    assert float(cost_field.min()) == 1.0
    assert float(cost_field.max()) == 1.0
    print(f"✓ Uniform cost field verified (all 1.0)")

    return True


def main():
    """Run all tests."""
    print("=" * 60)
    print("Zone-Aware Placement Integration Tests")
    print("=" * 60)

    tests = [
        ("Config", test_zone_aware_config),
        ("Initializer", test_zone_aware_initializer),
        ("Slot Stage", test_zone_aware_slot_stage),
        ("Pipeline", test_pipeline_creation),
        ("Cost Field", test_zone_cost_field),
    ]

    passed = 0
    failed = 0

    for name, test_fn in tests:
        try:
            if test_fn():
                passed += 1
        except Exception as e:
            failed += 1
            print(f"\n✗ {name} FAILED: {e}")
            import traceback

            traceback.print_exc()

    print("\n" + "=" * 60)
    print(f"Results: {passed}/{passed + failed} tests passed")
    print("=" * 60)

    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
