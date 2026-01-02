"""
Unit Tests for Differential Pair Router

Tests core functions without requiring full JAX stack.
"""

import pytest
from typing import Tuple, Set

# Standalone implementations for testing
def test_diff_pair_state_hashing():
    """Test that DiffPairState hashes correctly for use in sets/dicts."""
    from temper_placer.routing.diff_pair_router import DiffPairState
    
    state1 = DiffPairState(
        pos_x=10, pos_y=20, pos_layer=0,
        neg_x=10, neg_y=18, neg_layer=0,
        separation_mm=0.2
    )
    
    state2 = DiffPairState(
        pos_x=10, pos_y=20, pos_layer=0,
        neg_x=10, neg_y=18, neg_layer=0,
        separation_mm=0.2
    )
    
    # Same state should hash the same
    assert hash(state1) == hash(state2)
    
    # Should work in sets
    states = {state1, state2}
    assert len(states) == 1


def test_in_bounds():
    """Test boundary checking."""
    from temper_placer.routing.diff_pair_router import DiffPairRouter
    
    router = DiffPairRouter(
        grid_size=(100, 100, 2),
        cell_size_mm=0.2,
    )
    
    assert router._in_bounds((50, 50, 0)) == True
    assert router._in_bounds((99, 99, 1)) == True
    assert router._in_bounds((-1, 50, 0)) == False
    assert router._in_bounds((100, 50, 0)) == False
    assert router._in_bounds((50, 50, 2)) == False


def test_calculate_separation():
    """Test separation calculation."""
    from temper_placer.routing.diff_pair_router import DiffPairRouter
    
    router = DiffPairRouter(
        grid_size=(100, 100, 2),
        cell_size_mm=0.2,
    )
    
    # Adjacent cells (1 cell apart)
    sep = router._calculate_separation((10, 10, 0), (11, 10, 0))
    assert abs(sep - 0.2) < 0.01  # 1 cell * 0.2mm = 0.2mm
    
    # Diagonal (sqrt(2) cells)
    sep = router._calculate_separation((10, 10, 0), (11, 11, 0))
    expected = 0.2 * 1.414  # sqrt(2) * cell_size
    assert abs(sep - expected) < 0.01


def test_heuristic_admissible():
    """Test that heuristic never overestimates."""
    from temper_placer.routing.diff_pair_router import DiffPairRouter, DiffPairState
    
    router = DiffPairRouter(
        grid_size=(100, 100, 2),
        cell_size_mm=0.2,
    )
    
    start = DiffPairState(10, 10, 0, 10, 8, 0, 0.2)
    goal = DiffPairState(50, 50, 0, 50, 48, 0, 0.2)
    
    h = router._heuristic(start, goal)
    
    # Heuristic should be positive
    assert h > 0
    
    # Should be <= actual manhattan distance
    pos_dist = (abs(50-10) + abs(50-10)) * 0.2
    neg_dist = (abs(50-10) + abs(48-8)) * 0.2
    actual_min = max(pos_dist, neg_dist)
    
    assert h <= actual_min + 0.01  # Small tolerance


def test_serpentine_measure_path_length():
    """Test path length measurement."""
    from temper_placer.routing.serpentine import measure_path_length
    
    # Straight horizontal path (5 cells)
    cells = [(0, 0, 0), (1, 0, 0), (2, 0, 0), (3, 0, 0), (4, 0, 0)]
    length = measure_path_length(cells, cell_size_mm=0.2)
    assert abs(length - 0.8) < 0.01  # 4 steps * 0.2mm = 0.8mm
    
    # Path with via (layer change adds penalty)
    cells_with_via = [(0, 0, 0), (1, 0, 0), (1, 0, 1), (2, 0, 1)]
    length = measure_path_length(cells_with_via, cell_size_mm=0.2)
    assert length > 0.4  # Should include via penalty


def test_serpentine_calculate_params():
    """Test serpentine parameter calculation."""
    from temper_placer.routing.serpentine import calculate_serpentine_params
    
    # Need 2mm of extra length
    amplitude, frequency = calculate_serpentine_params(
        length_deficit_mm=2.0,
        available_space_mm=2.0,
        cell_size_mm=0.2,
    )
    
    # Amplitude should be reasonable
    assert 0 < amplitude <= 1.0
    
    # Frequency should be positive
    assert frequency > 0
    assert frequency <= 10  # Max frequency cap
    
    # Estimated length added
    added = 4 * amplitude * frequency
    assert abs(added - 2.0) < 1.0  # Within ballpark


def test_neighbor_generation_count():
    """Test that neighbor generation produces expected number of neighbors."""
    from temper_placer.routing.diff_pair_router import DiffPairRouter, DiffPairState
    
    router = DiffPairRouter(
        grid_size=(100, 100, 2),
        cell_size_mm=0.2,
    )
    
    state = DiffPairState(50, 50, 0, 50, 48, 0, 0.2)
    obstacles = set()
    
    neighbors = router._generate_coupled_neighbors(state, obstacles)
    
    # Should have neighbors (exact count depends on implementation)
    # At minimum: 4 directions (both_move) + layer changes + divergence moves
    assert len(neighbors) > 0
    assert len(neighbors) < 100  # Reasonable upper bound


if __name__ == "__main__":
    # Run tests
    test_diff_pair_state_hashing()
    print("✅ test_diff_pair_state_hashing passed")
    
    test_in_bounds()
    print("✅ test_in_bounds passed")
    
    test_calculate_separation()
    print("✅ test_calculate_separation passed")
    
    test_heuristic_admissible()
    print("✅ test_heuristic_admissible passed")
    
    test_serpentine_measure_path_length()
    print("✅ test_serpentine_measure_path_length passed")
    
    test_serpentine_calculate_params()
    print("✅ test_serpentine_calculate_params passed")
    
    test_neighbor_generation_count()
    print("✅ test_neighbor_generation_count passed")
    
    print("\n🎉 All unit tests passed!")
