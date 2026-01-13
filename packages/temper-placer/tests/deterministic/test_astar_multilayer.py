"""
Unit tests for A* routing on different layers.

Tests that the A* pathfinder correctly routes on specified layers.
"""

import pytest
from temper_placer.deterministic.stages.clearance_grid import ClearanceGrid
from temper_placer.deterministic.stages.astar import DeterministicAStar


def test_astar_routing_on_layer_0():
    """Test basic A* routing on layer 0."""
    grid = ClearanceGrid(
        width_mm=50,
        height_mm=50,
        cell_size_mm=1.0,
        layer_count=4
    )
    
    pathfinder = DeterministicAStar(grid)
    
    # Route from (10, 10) to (40, 40) on layer 0
    path = pathfinder.find_path(start=(10, 10), end=(40, 40), layer=0)
    
    assert path is not None
    assert len(path) >= 2
    assert path[0] == (10, 10)
    assert path[-1] == (40, 40)


def test_astar_routing_on_different_layers():
    """Test that routing works independently on different layers."""
    grid = ClearanceGrid(
        width_mm=50,
        height_mm=50,
        cell_size_mm=1.0,
        layer_count=4
    )
    
    # Block obstacle on layer 0 only (smaller radius to allow detour)
    grid.block_circle(center=(25, 25), radius_mm=5.0, clearance_mm=1.0, layer=0)
    
    pathfinder = DeterministicAStar(grid)
    
    # Try routing through the obstacle on layer 0 (should detour)
    path_l0 = pathfinder.find_path(start=(15, 25), end=(35, 25), layer=0)
    
    # Try routing through same area on layer 1 (should be direct since no obstacle)
    path_l1 = pathfinder.find_path(start=(15, 25), end=(35, 25), layer=1)
    
    assert path_l0 is not None
    assert path_l1 is not None
    
    # Path on layer 1 should be shorter or equal (can go direct)
    assert len(path_l1) <= len(path_l0)


def test_astar_blocked_start_on_specific_layer():
    """Test that routing fails when start is blocked on target layer."""
    grid = ClearanceGrid(
        width_mm=50,
        height_mm=50,
        cell_size_mm=1.0,
        layer_count=4
    )
    
    # Block start position on layer 2 only
    grid.block_circle(center=(10, 10), radius_mm=3.0, clearance_mm=0, layer=2)
    
    pathfinder = DeterministicAStar(grid)
    
    # Routing on layer 2 should fail
    path_l2 = pathfinder.find_path(start=(10, 10), end=(40, 40), layer=2)
    assert path_l2 is None
    
    # But routing on layer 0 should succeed
    path_l0 = pathfinder.find_path(start=(10, 10), end=(40, 40), layer=0)
    assert path_l0 is not None


def test_astar_blocked_end_on_specific_layer():
    """Test that routing fails when end is blocked on target layer."""
    grid = ClearanceGrid(
        width_mm=50,
        height_mm=50,
        cell_size_mm=1.0,
        layer_count=4
    )
    
    # Block end position on layer 3 only
    grid.block_circle(center=(40, 40), radius_mm=3.0, clearance_mm=0, layer=3)
    
    pathfinder = DeterministicAStar(grid)
    
    # Routing on layer 3 should fail
    path_l3 = pathfinder.find_path(start=(10, 10), end=(40, 40), layer=3)
    assert path_l3 is None
    
    # But routing on layer 1 should succeed
    path_l1 = pathfinder.find_path(start=(10, 10), end=(40, 40), layer=1)
    assert path_l1 is not None


def test_astar_complex_obstacle_avoidance_per_layer():
    """Test routing around complex obstacles on specific layer."""
    grid = ClearanceGrid(
        width_mm=100,
        height_mm=100,
        cell_size_mm=0.5,
        layer_count=4
    )
    
    # Create a "U" shaped obstacle on layer 1
    grid.block_trace([(20, 20), (20, 80)], width_mm=2.0, clearance_mm=1.0, layer=1)
    grid.block_trace([(20, 20), (80, 20)], width_mm=2.0, clearance_mm=1.0, layer=1)
    grid.block_trace([(80, 20), (80, 80)], width_mm=2.0, clearance_mm=1.0, layer=1)
    
    pathfinder = DeterministicAStar(grid)
    
    # Route from inside the U to outside on layer 1
    path_l1 = pathfinder.find_path(start=(50, 50), end=(90, 50), layer=1)
    
    # Should find a path going up and around
    assert path_l1 is not None
    
    # Route on layer 0 should be more direct (no obstacle)
    path_l0 = pathfinder.find_path(start=(50, 50), end=(90, 50), layer=0)
    assert path_l0 is not None
    assert len(path_l0) < len(path_l1)


def test_astar_default_layer_backward_compatibility():
    """Test that omitting layer parameter defaults to layer 0."""
    grid = ClearanceGrid(
        width_mm=50,
        height_mm=50,
        cell_size_mm=1.0,
        layer_count=2
    )
    
    # Block on layer 1
    grid.block_circle(center=(25, 25), radius_mm=5.0, clearance_mm=0, layer=1)
    
    pathfinder = DeterministicAStar(grid)
    
    # Route without specifying layer (should use layer 0)
    path = pathfinder.find_path(start=(20, 25), end=(30, 25))
    
    # Should succeed since layer 0 is not blocked
    assert path is not None


def test_astar_invalid_layer():
    """Test that routing on invalid layer returns None."""
    grid = ClearanceGrid(
        width_mm=50,
        height_mm=50,
        cell_size_mm=1.0,
        layer_count=4
    )
    
    pathfinder = DeterministicAStar(grid)
    
    # Try routing on layer that doesn't exist
    path_invalid = pathfinder.find_path(start=(10, 10), end=(40, 40), layer=10)
    assert path_invalid is None
    
    # Negative layer
    path_negative = pathfinder.find_path(start=(10, 10), end=(40, 40), layer=-1)
    assert path_negative is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
