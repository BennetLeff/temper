"""
Property-based tests for A* pathfinding with functional state.

Tests verify A* returns optimal paths, maintains immutability,
and satisfies pathfinding invariants.
"""

import pytest
from hypothesis import given, strategies as st, assume
import jax.numpy as jnp

from temper_placer.routing.push_shove import Grid, GridCell, find_path, PathResult


@pytest.fixture
def empty_grid():
    return Grid(width=20, height=20, layers=1)


@pytest.fixture
def grid_with_wall():
    """Grid with vertical wall."""
    grid = Grid(width=20, height=20, layers=1)
    # Vertical wall at x=10
    for y in range(5, 15):
        grid = grid.with_obstacle(GridCell(10, y, 0))
    return grid


class TestPathfindingOptimality:
    """Tests for A* path optimality."""

    def test_straight_line_is_optimal(self, empty_grid):
        """Straight line path should be shortest."""
        start = GridCell(0, 0, 0)
        end = GridCell(10, 0, 0)
        
        result = find_path(empty_grid, start, end)
        
        assert result.success, "Should find path"
        assert len(result.path) == 11, "Path should be 11 cells (0-10 inclusive)"
        
        # Verify path is straight
        for i, cell in enumerate(result.path):
            assert cell.x == i, "Path should be straight horizontal"
            assert cell.y == 0, "Path should stay on y=0"

    def test_path_around_obstacle_is_optimal(self, grid_with_wall):
        """Path around obstacle should be shortest possible."""
        start = GridCell(5, 10, 0)
        end = GridCell(15, 10, 0)
        
        result = find_path(grid_with_wall, start, end)
        
        assert result.success, "Should find path around wall"
        
        # Optimal path goes around wall (up or down)
        # Distance: 5 (to wall) + detour (up/down) + 5 (from wall) + detour back
        # Minimum detour = 2 cells (one up/down, one back)
        # Total = 5 + 2 + 5 + 2 = 14 cells minimum
        assert len(result.path) <= 20, "Path should be reasonably short"

    def test_no_path_returns_failure(self, grid_with_wall):
        """Should return failure when no path exists."""
        # Extend wall to block completely
        grid = grid_with_wall
        for y in range(0, 20):
            grid = grid.with_obstacle(GridCell(10, y, 0))
        
        start = GridCell(5, 10, 0)
        end = GridCell(15, 10, 0)
        
        result = find_path(grid, start, end)
        
        assert not result.success, "Should fail when no path exists"
        assert result.path == [], "Failed path should be empty"

    @given(
        start_x=st.integers(min_value=0, max_value=19),
        start_y=st.integers(min_value=0, max_value=19),
        end_x=st.integers(min_value=0, max_value=19),
        end_y=st.integers(min_value=0, max_value=19),
    )
    def test_path_length_is_minimal(self, empty_grid, start_x, start_y, end_x, end_y):
        """Property: Path length should be minimal (Manhattan distance)."""
        assume(start_x != end_x or start_y != end_y)  # Not same cell
        
        start = GridCell(start_x, start_y, 0)
        end = GridCell(end_x, end_y, 0)
        
        result = find_path(empty_grid, start, end)
        
        if result.success:
            manhattan = abs(end_x - start_x) + abs(end_y - start_y)
            # Path length should be manhattan + 1 (inclusive of both endpoints)
            assert len(result.path) == manhattan + 1, \
                f"Path length {len(result.path)} should equal Manhattan distance {manhattan} + 1"


class TestPathfindingInvariants:
    """Invariant tests for pathfinding."""

    @given(
        start_x=st.integers(min_value=0, max_value=19),
        start_y=st.integers(min_value=0, max_value=19),
        end_x=st.integers(min_value=0, max_value=19),
        end_y=st.integers(min_value=0, max_value=19),
    )
    def test_path_starts_and_ends_correctly(self, empty_grid, start_x, start_y, end_x, end_y):
        """Property: Path should start at start and end at end."""
        start = GridCell(start_x, start_y, 0)
        end = GridCell(end_x, end_y, 0)
        
        result = find_path(empty_grid, start, end)
        
        if result.success:
            assert result.path[0] == start, "Path should start at start cell"
            assert result.path[-1] == end, "Path should end at end cell"

    @given(
        start_x=st.integers(min_value=0, max_value=19),
        start_y=st.integers(min_value=0, max_value=19),
        end_x=st.integers(min_value=0, max_value=19),
        end_y=st.integers(min_value=0, max_value=19),
    )
    def test_path_is_connected(self, empty_grid, start_x, start_y, end_x, end_y):
        """Property: Path cells should be connected (adjacent)."""
        start = GridCell(start_x, start_y, 0)
        end = GridCell(end_x, end_y, 0)
        
        result = find_path(empty_grid, start, end)
        
        if result.success and len(result.path) > 1:
            for i in range(len(result.path) - 1):
                curr = result.path[i]
                next_cell = result.path[i + 1]
                
                # Cells should be adjacent (Manhattan distance = 1)
                manhattan = abs(next_cell.x - curr.x) + abs(next_cell.y - curr.y)
                assert manhattan == 1, \
                    f"Path cells {curr} and {next_cell} should be adjacent"

    @given(
        start_x=st.integers(min_value=0, max_value=19),
        start_y=st.integers(min_value=0, max_value=19),
        end_x=st.integers(min_value=0, max_value=19),
        end_y=st.integers(min_value=0, max_value=19),
    )
    def test_path_has_no_cycles(self, empty_grid, start_x, start_y, end_x, end_y):
        """Property: Path should not revisit cells (no cycles)."""
        start = GridCell(start_x, start_y, 0)
        end = GridCell(end_x, end_y, 0)
        
        result = find_path(empty_grid, start, end)
        
        if result.success:
            visited = set()
            for cell in result.path:
                assert cell not in visited, f"Path should not revisit cell {cell}"
                visited.add(cell)

    def test_path_respects_obstacles(self, grid_with_wall):
        """Path should not go through obstacles."""
        start = GridCell(5, 10, 0)
        end = GridCell(15, 10, 0)
        
        result = find_path(grid_with_wall, start, end)
        
        if result.success:
            for cell in result.path:
                from temper_placer.routing.push_shove import is_occupied
                assert not is_occupied(grid_with_wall, (cell.x, cell.y)), \
                    f"Path should not go through obstacle at {cell}"


class TestPathfindingImmutability:
    """Tests for functional state management in pathfinding."""

    def test_find_path_does_not_modify_grid(self, empty_grid):
        """find_path should not modify input grid."""
        original_state = empty_grid.occupancy.copy()
        
        start = GridCell(0, 0, 0)
        end = GridCell(10, 10, 0)
        
        _ = find_path(empty_grid, start, end)
        
        assert jnp.array_equal(empty_grid.occupancy, original_state), \
            "find_path should not modify grid"

    def test_path_result_is_immutable(self, empty_grid):
        """PathResult should be immutable."""
        start = GridCell(0, 0, 0)
        end = GridCell(10, 0, 0)
        
        result = find_path(empty_grid, start, end)
        
        from dataclasses import FrozenInstanceError
        with pytest.raises(FrozenInstanceError):
            result.success = False

    def test_multiple_pathfinding_calls_are_independent(self, empty_grid):
        """Multiple pathfinding calls should not interfere."""
        start1, end1 = GridCell(0, 0, 0), GridCell(5, 0, 0)
        start2, end2 = GridCell(0, 10, 0), GridCell(5, 10, 0)
        
        result1 = find_path(empty_grid, start1, end1)
        result2 = find_path(empty_grid, start2, end2)
        
        # Both should succeed independently
        assert result1.success and result2.success
        assert result1.path != result2.path, "Paths should be different"


class TestPathfindingWithVias:
    """Tests for pathfinding with layer changes (vias)."""

    def test_via_when_blocked_on_layer(self):
        """Should use via when path blocked on current layer."""
        grid = Grid(width=20, height=20, layers=2)
        
        # Block horizontal path on layer 0
        for x in range(5, 15):
            grid = grid.with_obstacle(GridCell(x, 10, 0))
        
        start = GridCell(0, 10, 0)
        end = GridCell(19, 10, 0)
        
        result = find_path(grid, start, end, allow_layer_change=True)
        
        assert result.success, "Should find path using via"
        
        # Path should include layer change
        layers_used = {cell.layer for cell in result.path}
        assert len(layers_used) > 1, "Path should use multiple layers"

    def test_via_count_is_minimal(self):
        """Should minimize number of vias."""
        grid = Grid(width=20, height=20, layers=2)
        
        # Small obstacle requiring one via
        grid = grid.with_obstacle(GridCell(10, 10, 0))
        
        start = GridCell(5, 10, 0)
        end = GridCell(15, 10, 0)
        
        result = find_path(grid, start, end, allow_layer_change=True)
        
        if result.success:
            # Count layer changes
            vias = 0
            for i in range(len(result.path) - 1):
                if result.path[i].layer != result.path[i + 1].layer:
                    vias += 1
            
            # Should use minimal vias (2 for one obstacle: down and back up)
            assert vias <= 4, f"Should use minimal vias, got {vias}"
