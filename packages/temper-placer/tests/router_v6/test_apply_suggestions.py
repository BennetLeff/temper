"""
Tests for Router V6 Feedback F.4: Apply Suggestions with Damping

Part of temper-8hx1
"""

import pytest

from temper_placer.router_v6.apply_suggestions import (
    AdjustmentResult,
    AppliedAdjustment,
    apply_suggestions_with_damping,
    update_component_positions,
)
from temper_placer.router_v6.placement_suggestions import (
    PlacementSuggestion,
    PlacementSuggestions,
)


def test_apply_no_suggestions():
    """Test applying empty suggestions."""
    suggestions = PlacementSuggestions(suggestions=[])
    positions = {}

    result = apply_suggestions_with_damping(suggestions, positions)

    assert result.adjustment_count == 0


def test_apply_with_damping():
    """Test suggestion application with damping."""
    suggestion = PlacementSuggestion(
        component_id="U1",
        current_position=(0.0, 0.0),
        suggested_position=(10.0, 0.0),
        reason="test",
        priority=0.8,
    )
    suggestions = PlacementSuggestions(suggestions=[suggestion])
    positions = {"U1": (0.0, 0.0)}

    # 50% damping
    result = apply_suggestions_with_damping(suggestions, positions, damping_factor=0.5)

    assert result.adjustment_count == 1
    adjustment = result.adjustments[0]
    # Should move halfway: 0 + (10-0)*0.5 = 5
    assert adjustment.applied_position[0] == pytest.approx(5.0)


def test_full_damping():
    """Test with 100% damping (full movement)."""
    suggestion = PlacementSuggestion("U1", (0, 0), (10, 10), "test", 0.9)
    suggestions = PlacementSuggestions(suggestions=[suggestion])
    positions = {"U1": (0.0, 0.0)}

    result = apply_suggestions_with_damping(suggestions, positions, damping_factor=1.0)

    adjustment = result.adjustments[0]
    # Should move fully to suggested position
    assert adjustment.applied_position == pytest.approx((10.0, 10.0))


def test_no_damping():
    """Test with 0% damping (no movement)."""
    suggestion = PlacementSuggestion("U1", (0, 0), (10, 10), "test", 0.9)
    suggestions = PlacementSuggestions(suggestions=[suggestion])
    positions = {"U1": (0.0, 0.0)}

    result = apply_suggestions_with_damping(suggestions, positions, damping_factor=0.0)

    adjustment = result.adjustments[0]
    # Should not move at all
    assert adjustment.applied_position == (0.0, 0.0)


def test_applied_adjustment_dataclass():
    """Test AppliedAdjustment dataclass."""
    adjustment = AppliedAdjustment(
        component_id="U1",
        original_position=(0.0, 0.0),
        suggested_position=(10.0, 0.0),
        applied_position=(5.0, 0.0),
        damping_factor=0.5,
    )

    assert adjustment.component_id == "U1"
    assert adjustment.applied_position == (5.0, 0.0)
    assert adjustment.damping_factor == 0.5


def test_adjustment_result_dataclass():
    """Test AdjustmentResult dataclass."""
    adj1 = AppliedAdjustment("U1", (0, 0), (10, 0), (5, 0), 0.5)
    adj2 = AppliedAdjustment("U2", (0, 0), (0, 10), (0, 5), 0.5)

    result = AdjustmentResult(adjustments=[adj1, adj2])

    assert result.adjustment_count == 2
    # Total movement: 5mm + 5mm = 10mm
    assert result.total_movement == pytest.approx(10.0)


def test_priority_filtering():
    """Test that low-priority suggestions are filtered out."""
    suggestion1 = PlacementSuggestion("U1", (0, 0), (10, 0), "test", 0.9)  # High
    suggestion2 = PlacementSuggestion("U2", (0, 0), (10, 0), "test", 0.3)  # Low

    suggestions = PlacementSuggestions(suggestions=[suggestion1, suggestion2])
    positions = {"U1": (0.0, 0.0), "U2": (0.0, 0.0)}

    result = apply_suggestions_with_damping(
        suggestions,
        positions,
        min_priority_threshold=0.5
    )

    # Only high-priority suggestion should be applied
    assert result.adjustment_count == 1
    assert result.adjustments[0].component_id == "U1"


def test_update_component_positions():
    """Test updating positions from adjustment result."""
    adj1 = AppliedAdjustment("U1", (0, 0), (10, 0), (5, 0), 0.5)
    adj2 = AppliedAdjustment("U2", (0, 0), (0, 10), (0, 5), 0.5)
    result = AdjustmentResult(adjustments=[adj1, adj2])

    original_positions = {"U1": (0.0, 0.0), "U2": (0.0, 0.0), "U3": (20.0, 20.0)}

    updated = update_component_positions(original_positions, result)

    # U1 and U2 should be updated
    assert updated["U1"] == (5.0, 0.0)
    assert updated["U2"] == (0.0, 5.0)
    # U3 should remain unchanged
    assert updated["U3"] == (20.0, 20.0)


def test_conservative_damping():
    """Test conservative damping factor (small movements)."""
    suggestion = PlacementSuggestion("U1", (0, 0), (100, 0), "test", 0.9)
    suggestions = PlacementSuggestions(suggestions=[suggestion])
    positions = {"U1": (0.0, 0.0)}

    # Very conservative damping
    result = apply_suggestions_with_damping(suggestions, positions, damping_factor=0.1)

    adjustment = result.adjustments[0]
    # Should move only 10% of the way
    assert adjustment.applied_position[0] == pytest.approx(10.0)
