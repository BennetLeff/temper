"""
Unit tests for 4-layer ClearanceGrid functionality.

Tests the multi-layer grid implementation to ensure:
- Per-layer blocking works correctly
- Layer isolation (blocking on L0 doesn't affect L1)
- Layer-specific availability checks
"""

import pytest

from temper_placer.deterministic.stages.clearance_grid import ClearanceGrid


def test_4layer_grid_creation():
    """Test that 4-layer grid is created correctly."""
    grid = ClearanceGrid(
        width_mm=100,
        height_mm=100,
        cell_size_mm=0.5,
        layer_count=4
    )

    assert grid.layer_count == 4
    assert len(grid._trace_net_ids) == 4
    assert len(grid._pad_net_ids) == 4
    assert grid.rows == 200  # 100 / 0.5
    assert grid.cols == 200

    # All layers should start empty
    for layer in range(4):
        assert grid.blocked_count_on_layer(layer) == 0


def test_layer_specific_blocking():
    """Test that blocking on one layer doesn't affect others."""
    grid = ClearanceGrid(
        width_mm=100,
        height_mm=100,
        cell_size_mm=0.5,
        layer_count=4
    )

    # Block a circle on layer 0 only
    grid.block_circle(center=(50, 50), radius_mm=5.0, clearance_mm=1.0, layer=0)

    # Layer 0 should have blocked cells
    assert grid.blocked_count_on_layer(0) > 0

    # Other layers should be unaffected
    assert grid.blocked_count_on_layer(1) == 0
    assert grid.blocked_count_on_layer(2) == 0
    assert grid.blocked_count_on_layer(3) == 0

    # Center should be blocked on L0, available on others
    assert grid.is_available(50, 50, layer=0) == False
    assert grid.is_available(50, 50, layer=1) == True
    assert grid.is_available(50, 50, layer=2) == True
    assert grid.is_available(50, 50, layer=3) == True


def test_multi_layer_blocking():
    """Test blocking the same area on multiple layers."""
    grid = ClearanceGrid(
        width_mm=100,
        height_mm=100,
        cell_size_mm=0.5,
        layer_count=4
    )

    # Block same position on layers 0 and 2
    grid.block_circle(center=(50, 50), radius_mm=3.0, clearance_mm=0.5, layer=0)
    grid.block_circle(center=(50, 50), radius_mm=3.0, clearance_mm=0.5, layer=2)

    # Layers 0 and 2 should be blocked
    assert grid.is_available(50, 50, layer=0) == False
    assert grid.is_available(50, 50, layer=2) == False

    # Layers 1 and 3 should be available
    assert grid.is_available(50, 50, layer=1) == True
    assert grid.is_available(50, 50, layer=3) == True


def test_trace_blocking_per_layer():
    """Test blocking a trace path on specific layer."""
    grid = ClearanceGrid(
        width_mm=100,
        height_mm=100,
        cell_size_mm=0.5,
        layer_count=4
    )

    # Block a straight trace on layer 1
    path = [(20, 20), (20, 80)]
    grid.block_trace(path, width_mm=0.5, clearance_mm=0.2, layer=1)

    # Midpoint should be blocked on L1
    assert grid.is_available(20, 50, layer=1) == False

    # But available on other layers
    assert grid.is_available(20, 50, layer=0) == True
    assert grid.is_available(20, 50, layer=2) == True
    assert grid.is_available(20, 50, layer=3) == True


def test_unblock_per_layer():
    """Test unblocking on specific layer."""
    grid = ClearanceGrid(
        width_mm=100,
        height_mm=100,
        cell_size_mm=0.5,
        layer_count=4
    )

    # Block on all layers
    for layer in range(4):
        grid.block_circle(center=(50, 50), radius_mm=5.0, clearance_mm=0, layer=layer)

    # All should be blocked
    for layer in range(4):
        assert grid.is_available(50, 50, layer=layer) == False

    # Unblock on layer 2 only
    grid.unblock_circle(center=(50, 50), radius_mm=5.0, layer=2)

    # Layer 2 should now be available
    assert grid.is_available(50, 50, layer=2) == True

    # Others still blocked
    assert grid.is_available(50, 50, layer=0) == False
    assert grid.is_available(50, 50, layer=1) == False
    assert grid.is_available(50, 50, layer=3) == False


def test_invalid_layer_access():
    """Test that invalid layer indices are handled gracefully."""
    grid = ClearanceGrid(
        width_mm=100,
        height_mm=100,
        cell_size_mm=0.5,
        layer_count=4
    )

    # Negative layer
    assert grid.is_available(50, 50, layer=-1) == False

    # Out of range layer
    assert grid.is_available(50, 50, layer=4) == False
    assert grid.is_available(50, 50, layer=100) == False

    # Blocking on invalid layer should be silently ignored
    grid.block_circle(center=(50, 50), radius_mm=5.0, clearance_mm=0, layer=-1)
    grid.block_circle(center=(50, 50), radius_mm=5.0, clearance_mm=0, layer=10)

    # Position should still be available on valid layers
    for layer in range(4):
        assert grid.is_available(50, 50, layer=layer) == True


def test_backward_compatibility():
    """Test that default layer=0 maintains backward compatibility."""
    grid = ClearanceGrid(
        width_mm=100,
        height_mm=100,
        cell_size_mm=0.5,
        layer_count=2  # 2-layer board
    )

    # Block without specifying layer (should default to 0)
    grid.block_circle(center=(50, 50), radius_mm=5.0, clearance_mm=1.0)

    # Should be blocked on layer 0
    assert grid.is_available(50, 50, layer=0) == False
    assert grid.is_available(50, 50) == False  # Default layer=0

    # Should be available on layer 1
    assert grid.is_available(50, 50, layer=1) == True


def test_blocked_cells_per_layer():
    """Test that blocked_cells_on_layer returns correct cells."""
    grid = ClearanceGrid(
        width_mm=20,
        height_mm=20,
        cell_size_mm=1.0,
        layer_count=4
    )

    # Block small area on layer 1
    grid.block_circle(center=(10, 10), radius_mm=1.5, clearance_mm=0, layer=1)

    # Get blocked cells on layer 1
    blocked_l1 = grid.blocked_cells_on_layer(1)
    assert len(blocked_l1) > 0

    # Other layers should have no blocked cells
    assert len(grid.blocked_cells_on_layer(0)) == 0
    assert len(grid.blocked_cells_on_layer(2)) == 0
    assert len(grid.blocked_cells_on_layer(3)) == 0

    # Total blocked cells should include layer info
    total_blocked = grid.blocked_cells
    assert len(total_blocked) == len(blocked_l1)

    # All blocked cells should be on layer 1
    for r, c, layer in total_blocked:
        assert layer == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
