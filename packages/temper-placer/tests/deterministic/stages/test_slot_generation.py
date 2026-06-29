"""
Unit tests for SlotGenerationStage.

Tests grid-based slot generation within each zone with 5mm spacing.
"""

from temper_placer.core.board import Board
from temper_placer.deterministic.stages.slot_generation import SlotGenerationStage
from temper_placer.deterministic.stages.zone_geometry import ZoneGeometryStage
from temper_placer.deterministic.state import BoardState


def test_slots_generated_for_all_zones():
    """Verify slots are generated for all 4 zones."""
    board = Board(width=100, height=100)
    initial_state = BoardState(board=board)

    # Create zones first
    zone_stage = ZoneGeometryStage()
    state_with_zones = zone_stage.run(initial_state)

    # Generate slots
    slot_stage = SlotGenerationStage(slot_spacing_mm=5.0)
    result_state = slot_stage.run(state_with_zones)

    # Verify
    zone_slots = dict(result_state.zone_slots)
    assert len(zone_slots) == 4
    assert "HV" in zone_slots
    assert "Power" in zone_slots
    assert "Signal" in zone_slots
    assert "MCU" in zone_slots

    # All zones should have slots
    for zone_name, slots in zone_slots.items():
        assert len(slots) > 0, f"{zone_name} has no slots"


def test_slots_within_zone_bounds():
    """Every slot position should be inside its zone bounds."""
    board = Board(width=100, height=100)
    initial_state = BoardState(board=board)

    zone_stage = ZoneGeometryStage()
    state_with_zones = zone_stage.run(initial_state)

    slot_stage = SlotGenerationStage(slot_spacing_mm=5.0)
    result_state = slot_stage.run(state_with_zones)

    # Get zones by name
    zones_by_name = {z.name: z for z in result_state.zones}
    zone_slots = dict(result_state.zone_slots)

    for zone_name, slots in zone_slots.items():
        zone = zones_by_name[zone_name]
        (x_min, y_min), (x_max, y_max) = zone.bounds

        for x, y in slots:
            assert x_min <= x <= x_max, f"Slot ({x}, {y}) outside {zone_name} X bounds"
            assert y_min <= y <= y_max, f"Slot ({x}, {y}) outside {zone_name} Y bounds"


def test_slot_spacing_is_uniform():
    """Verify 5mm grid spacing is maintained."""
    board = Board(width=100, height=100)
    initial_state = BoardState(board=board)

    zone_stage = ZoneGeometryStage()
    state_with_zones = zone_stage.run(initial_state)

    slot_spacing = 5.0
    slot_stage = SlotGenerationStage(slot_spacing_mm=slot_spacing)
    result_state = slot_stage.run(state_with_zones)

    zone_slots = dict(result_state.zone_slots)

    # Check spacing for HV zone (sample)
    hv_slots = sorted(zone_slots["HV"])
    if len(hv_slots) > 1:
        # Check X spacing in first row
        first_row = [slot for slot in hv_slots if slot[1] == hv_slots[0][1]]
        if len(first_row) > 1:
            x_spacing = first_row[1][0] - first_row[0][0]
            assert abs(x_spacing - slot_spacing) < 0.01

        # Check Y spacing in first column
        first_col = [slot for slot in hv_slots if slot[0] == hv_slots[0][0]]
        if len(first_col) > 1:
            y_spacing = first_col[1][1] - first_col[0][1]
            assert abs(y_spacing - slot_spacing) < 0.01


def test_sufficient_slots_for_components():
    """Number of slots should be greater than number of components in typical case."""
    board = Board(width=100, height=100)
    initial_state = BoardState(board=board)

    zone_stage = ZoneGeometryStage()
    state_with_zones = zone_stage.run(initial_state)

    slot_stage = SlotGenerationStage(slot_spacing_mm=5.0)
    result_state = slot_stage.run(state_with_zones)

    zone_slots = dict(result_state.zone_slots)

    # Count total slots
    total_slots = sum(len(slots) for slots in zone_slots.values())

    # For 100x100mm board with 5mm spacing:
    # HV (30mm wide): ~6 columns x 20 rows = 120 slots
    # Power (30mm): ~6 x 20 = 120 slots
    # Signal (30mm): ~6 x 20 = 120 slots
    # MCU (10mm): ~2 x 20 = 40 slots
    # Total: ~400 slots

    # Verify we have a reasonable number
    assert total_slots > 100, f"Only {total_slots} total slots generated"


def test_different_spacing_values():
    """Verify slot generation works with different spacing values."""
    board = Board(width=100, height=100)
    initial_state = BoardState(board=board)

    zone_stage = ZoneGeometryStage()
    state_with_zones = zone_stage.run(initial_state)

    # Test with 10mm spacing
    slot_stage_10mm = SlotGenerationStage(slot_spacing_mm=10.0)
    result_10mm = slot_stage_10mm.run(state_with_zones)
    zone_slots_10mm = dict(result_10mm.zone_slots)
    total_10mm = sum(len(slots) for slots in zone_slots_10mm.values())

    # Test with 5mm spacing
    slot_stage_5mm = SlotGenerationStage(slot_spacing_mm=5.0)
    result_5mm = slot_stage_5mm.run(state_with_zones)
    zone_slots_5mm = dict(result_5mm.zone_slots)
    total_5mm = sum(len(slots) for slots in zone_slots_5mm.values())

    # Smaller spacing should produce more slots (approximately 4x for 2x denser grid)
    assert total_5mm > total_10mm * 2
