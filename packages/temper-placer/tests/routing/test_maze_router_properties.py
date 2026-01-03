"""
Property-based tests for maze router using Hypothesis.

These tests use random generation to find edge cases and invariant violations
that unit tests might miss.

Run with: uv run pytest tests/routing/test_maze_router_properties.py -v
"""

import pytest
from hypothesis import given, strategies as st, settings, assume

import jax.numpy as jnp
from temper_placer.routing.maze_router import (
    MazeRouter,
    GridCell,
    RoutePath,
)
from temper_placer.routing.routing_invariants import (
    validate_path_connectivity,
    validate_within_bounds,
    validate_no_blocked_cells,
)


# =============================================================================
# Custom Strategies
# =============================================================================

@st.composite
def grid_cell_strategy(draw, max_x=49, max_y=49, max_layer=1):
    """Generate a random GridCell within bounds."""
    return GridCell(
        x=draw(st.integers(0, max_x)),
        y=draw(st.integers(0, max_y)),
        layer=draw(st.integers(0, max_layer)),
    )


@st.composite
def grid_config_strategy(draw):
    """Generate a random grid configuration."""
    width = draw(st.integers(5, 50))
    height = draw(st.integers(5, 50))
    cell_size = draw(st.floats(0.5, 2.0))
    num_layers = draw(st.integers(1, 2))
    return width, height, cell_size, num_layers


@st.composite
def routing_problem_strategy(draw):
    """Generate a solvable routing problem (empty grid, two points)."""
    width = draw(st.integers(10, 50))
    height = draw(st.integers(10, 50))
    
    # Ensure start != end
    start_x = draw(st.integers(0, width - 1))
    start_y = draw(st.integers(0, height - 1))
    end_x = draw(st.integers(0, width - 1))
    end_y = draw(st.integers(0, height - 1))
    
    # Reject if same point
    assume(start_x != end_x or start_y != end_y)
    
    return width, height, (start_x, start_y), (end_x, end_y)


@st.composite
def connected_path_strategy(draw, min_length=2, max_length=20):
    """Generate a valid connected path of GridCells."""
    length = draw(st.integers(min_length, max_length))
    
    # Start somewhere reasonable
    x = draw(st.integers(10, 40))
    y = draw(st.integers(10, 40))
    layer = 0
    
    path = [GridCell(x, y, layer)]
    
    for _ in range(length - 1):
        # Pick a random valid move
        direction = draw(st.sampled_from(["up", "down", "left", "right"]))
        if direction == "up":
            y = min(49, y + 1)
        elif direction == "down":
            y = max(0, y - 1)
        elif direction == "left":
            x = max(0, x - 1)
        elif direction == "right":
            x = min(49, x + 1)
        
        path.append(GridCell(x, y, layer))
    
    return path


# =============================================================================
# Property Tests
# =============================================================================

class TestPathfindingProperties:
    """Property-based tests for A* pathfinding."""
    
    @given(routing_problem_strategy())
    @settings(max_examples=100, deadline=5000)
    def test_empty_grid_always_routable(self, problem):
        """Any two distinct points on an empty grid should be connectable."""
        width, height, start, end = problem
        
        router = MazeRouter(grid_size=(width, height), cell_size_mm=1.0, num_layers=1)
        path = router.find_path(start, end, layer=0)
        
        # Should always find a path on empty grid
        assert path is not None, f"No path found from {start} to {end} on {width}x{height} grid"
        
        # Path should start and end correctly
        assert (path[0].x, path[0].y) == start
        assert (path[-1].x, path[-1].y) == end
    
    @given(routing_problem_strategy())
    @settings(max_examples=100, deadline=5000)
    def test_path_is_connected(self, problem):
        """All returned paths should satisfy connectivity invariant."""
        width, height, start, end = problem
        
        router = MazeRouter(grid_size=(width, height), cell_size_mm=1.0, num_layers=1)
        path = router.find_path(start, end, layer=0)
        
        if path:
            violations = validate_path_connectivity(path)
            assert violations == [], f"Path connectivity violations: {violations}"
    
    @given(routing_problem_strategy())
    @settings(max_examples=100, deadline=5000)
    def test_path_within_bounds(self, problem):
        """All returned paths should stay within grid bounds."""
        width, height, start, end = problem
        
        router = MazeRouter(grid_size=(width, height), cell_size_mm=1.0, num_layers=1)
        path = router.find_path(start, end, layer=0)
        
        if path:
            violations = validate_within_bounds(path, (width, height), 1)
            assert violations == [], f"Path bounds violations: {violations}"
    
    @given(routing_problem_strategy())
    @settings(max_examples=50, deadline=5000)
    def test_path_avoids_blocked_cells(self, problem):
        """Paths should never traverse blocked cells."""
        width, height, start, end = problem
        
        router = MazeRouter(grid_size=(width, height), cell_size_mm=1.0, num_layers=1)
        
        # Block a random rectangle (but not start/end)
        block_x = (start[0] + end[0]) // 2
        block_y = (start[1] + end[1]) // 2
        if (block_x, block_y) != start and (block_x, block_y) != end:
            router.block_rect(block_x, block_y, 1, 1, layer=0)
        
        path = router.find_path(start, end, layer=0)
        
        if path:
            violations = validate_no_blocked_cells(path, router.occupancy)
            assert violations == [], f"Path blocked cell violations: {violations}"


class TestPathSymmetry:
    """Tests for path symmetry properties."""
    
    @given(routing_problem_strategy())
    @settings(max_examples=50, deadline=5000)
    def test_path_length_symmetric(self, problem):
        """Path A→B should have similar length to B→A on empty grid."""
        width, height, start, end = problem
        
        router = MazeRouter(grid_size=(width, height), cell_size_mm=1.0, num_layers=1)
        
        path_ab = router.find_path(start, end, layer=0)
        path_ba = router.find_path(end, start, layer=0)
        
        assert path_ab is not None
        assert path_ba is not None
        
        # On a uniform grid, lengths should be equal
        assert len(path_ab) == len(path_ba), (
            f"Asymmetric path lengths: A→B={len(path_ab)}, B→A={len(path_ba)}"
        )


class TestDeterminism:
    """Tests for deterministic behavior."""
    
    @given(routing_problem_strategy())
    @settings(max_examples=30, deadline=5000)
    def test_same_inputs_same_outputs(self, problem):
        """Same routing problem should always produce same result."""
        width, height, start, end = problem
        
        router1 = MazeRouter(grid_size=(width, height), cell_size_mm=1.0, num_layers=1)
        router2 = MazeRouter(grid_size=(width, height), cell_size_mm=1.0, num_layers=1)
        
        path1 = router1.find_path(start, end, layer=0)
        path2 = router2.find_path(start, end, layer=0)
        
        if path1 is None:
            assert path2 is None
        else:
            assert path2 is not None
            # Same path cells
            assert len(path1) == len(path2)
            for c1, c2 in zip(path1, path2):
                assert c1.x == c2.x and c1.y == c2.y and c1.layer == c2.layer


class TestConnectedPathValidation:
    """Tests that validate our connectivity checker itself."""
    
    @given(connected_path_strategy())
    @settings(max_examples=100)
    def test_valid_paths_pass_connectivity(self, path):
        """Paths generated as connected should pass connectivity check."""
        violations = validate_path_connectivity(path)
        assert violations == [], f"Generated valid path failed: {violations}"


class TestManhattanDistance:
    """Tests for path length optimality."""
    
    @given(routing_problem_strategy())
    @settings(max_examples=50, deadline=5000)
    def test_path_length_at_least_manhattan(self, problem):
        """Path length should be >= Manhattan distance."""
        width, height, start, end = problem
        
        manhattan = abs(end[0] - start[0]) + abs(end[1] - start[1])
        
        router = MazeRouter(grid_size=(width, height), cell_size_mm=1.0, num_layers=1)
        path = router.find_path(start, end, layer=0)
        
        assert path is not None
        # Path length (not counting start) should be >= Manhattan distance
        assert len(path) - 1 >= manhattan, (
            f"Path shorter than Manhattan: {len(path)-1} < {manhattan}"
        )
    
    @given(routing_problem_strategy())
    @settings(max_examples=50, deadline=5000)
    def test_empty_grid_optimal_path(self, problem):
        """On empty grid, path length should equal Manhattan distance."""
        width, height, start, end = problem
        
        manhattan = abs(end[0] - start[0]) + abs(end[1] - start[1])
        
        router = MazeRouter(grid_size=(width, height), cell_size_mm=1.0, num_layers=1)
        path = router.find_path(start, end, layer=0)
        
        assert path is not None
        # A* on empty grid should find optimal path
        assert len(path) - 1 == manhattan, (
            f"Non-optimal path on empty grid: {len(path)-1} != {manhattan}"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
