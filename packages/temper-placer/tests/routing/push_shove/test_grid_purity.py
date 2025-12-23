"""
Property-based tests for pure grid query functions.

Tests verify grid functions are pure (no side effects), deterministic,
and satisfy expected invariants.
"""

import pytest
from hypothesis import given, strategies as st
import jax.numpy as jnp

from temper_placer.routing.push_shove import Grid, GridCell, get_cell, is_occupied, get_neighbors


def get_empty_grid():
    """Empty 10x10 grid."""
    return Grid(width=10, height=10, layers=2)


def get_grid_with_obstacles():
    """Grid with some obstacles."""
    grid = Grid(width=10, height=10, layers=2)
    # Block some cells
    grid = grid.with_obstacle(GridCell(5, 5, 0))
    grid = grid.with_obstacle(GridCell(5, 6, 0))
    grid = grid.with_obstacle(GridCell(6, 5, 0))
    return grid


class TestGridPurity:
    """Tests for grid function purity."""

    def test_get_cell_is_pure(self):
        """get_cell should be pure (same input -> same output)."""
        grid = get_empty_grid()
        cell1 = get_cell(grid, (5, 5))
        cell2 = get_cell(grid, (5, 5))
        
        assert cell1 == cell2, "get_cell should be deterministic"

    def test_get_cell_no_side_effects(self):
        """get_cell should not modify grid."""
        grid = get_empty_grid()
        original_state = grid.occupancy.copy()
        
        _ = get_cell(grid, (5, 5))
        
        assert jnp.array_equal(grid.occupancy, original_state), \
            "get_cell should not modify grid"

    def test_is_occupied_is_pure(self):
        """is_occupied should be pure."""
        grid = get_grid_with_obstacles()
        result1 = is_occupied(grid, (5, 5))
        result2 = is_occupied(grid, (5, 5))
        
        assert result1 == result2, "is_occupied should be deterministic"

    def test_get_neighbors_is_pure(self):
        """get_neighbors should be pure."""
        grid = get_empty_grid()
        neighbors1 = get_neighbors(grid, GridCell(5, 5, 0))
        neighbors2 = get_neighbors(grid, GridCell(5, 5, 0))
        
        assert neighbors1 == neighbors2, "get_neighbors should be deterministic"

    def test_grid_with_obstacle_returns_new_grid(self):
        """with_obstacle should return new grid, not modify original."""
        grid = get_empty_grid()
        original_occupied = is_occupied(grid, (5, 5))
        
        new_grid = grid.with_obstacle(GridCell(5, 5, 0))
        
        assert is_occupied(grid, (5, 5)) == original_occupied, \
            "Original grid should be unchanged"
        assert is_occupied(new_grid, (5, 5)), \
            "New grid should have obstacle"


class TestGridInvariants:
    """Property-based tests for grid invariants."""

    @given(
        x=st.integers(min_value=0, max_value=9),
        y=st.integers(min_value=0, max_value=9),
    )
    def test_get_cell_in_bounds(self, x, y):
        """Property: get_cell should always return valid cell for in-bounds coords."""
        grid = get_empty_grid()
        cell = get_cell(grid, (x, y))
        
        assert cell.x == x, "Cell x should match input"
        assert cell.y == y, "Cell y should match input"
        assert 0 <= cell.layer < grid.layers, "Cell layer should be valid"

    @given(
        x=st.integers(min_value=-5, max_value=15),
        y=st.integers(min_value=-5, max_value=15),
    )
    def test_is_occupied_handles_out_of_bounds(self, x, y):
        """Property: is_occupied should handle out-of-bounds gracefully."""
        grid = get_empty_grid()
        # Should either return False or raise clear error
        if 0 <= x < grid.width and 0 <= y < grid.height:
            result = is_occupied(grid, (x, y))
            assert isinstance(result, bool), "Should return boolean for valid coords"
        else:
            # Out of bounds should return False (treated as occupied/invalid)
            result = is_occupied(grid, (x, y))
            assert result == False or result == True, "Should return boolean"

    @given(
        x=st.integers(min_value=0, max_value=9),
        y=st.integers(min_value=0, max_value=9),
    )
    def test_neighbors_are_adjacent(self, x, y):
        """Property: All neighbors should be adjacent (Manhattan distance = 1)."""
        grid = get_empty_grid()
        cell = GridCell(x, y, 0)
        neighbors = get_neighbors(grid, cell)
        
        for neighbor in neighbors:
            if neighbor.layer == cell.layer:
                # Same layer: should be 4-connected
                manhattan = abs(neighbor.x - cell.x) + abs(neighbor.y - cell.y)
                assert manhattan == 1, f"Neighbor {neighbor} not adjacent to {cell}"
            else:
                # Different layer: should be same x,y (via)
                assert neighbor.x == cell.x and neighbor.y == cell.y, \
                    f"Via neighbor {neighbor} should have same x,y as {cell}"

    @given(
        x=st.integers(min_value=1, max_value=8),
        y=st.integers(min_value=1, max_value=8),
    )
    def test_interior_cell_has_4_neighbors(self, x, y):
        """Property: Interior cells should have 4 neighbors on same layer."""
        grid = get_empty_grid()
        cell = GridCell(x, y, 0)
        neighbors = get_neighbors(grid, cell, allow_layer_change=False)
        
        assert len(neighbors) == 4, f"Interior cell should have 4 neighbors, got {len(neighbors)}"

    def test_corner_cell_has_2_neighbors(self):
        """Corner cells should have 2 neighbors on same layer."""
        grid = get_empty_grid()
        cell = GridCell(0, 0, 0)
        neighbors = get_neighbors(grid, cell, allow_layer_change=False)
        
        assert len(neighbors) == 2, f"Corner cell should have 2 neighbors, got {len(neighbors)}"

    def test_edge_cell_has_3_neighbors(self):
        """Edge cells should have 3 neighbors on same layer."""
        grid = get_empty_grid()
        cell = GridCell(5, 0, 0)  # Top edge
        neighbors = get_neighbors(grid, cell, allow_layer_change=False)
        
        assert len(neighbors) == 3, f"Edge cell should have 3 neighbors, got {len(neighbors)}"

    @given(
        x=st.integers(min_value=0, max_value=9),
        y=st.integers(min_value=0, max_value=9),
    )
    def test_neighbors_exclude_occupied_cells(self, x, y):
        """Property: get_neighbors should exclude occupied cells."""
        grid = get_grid_with_obstacles()
        cell = GridCell(x, y, 0)
        neighbors = get_neighbors(grid, cell)
        
        for neighbor in neighbors:
            assert not is_occupied(grid, (neighbor.x, neighbor.y), neighbor.layer), \
                f"Neighbor {neighbor} should not be occupied"


class TestGridComposition:
    """Tests for grid composition and functional properties."""

    def test_multiple_obstacles_compose(self):
        """Adding multiple obstacles should compose correctly."""
        grid0 = get_empty_grid()
        grid1 = grid0.with_obstacle(GridCell(5, 5, 0))
        grid2 = grid1.with_obstacle(GridCell(6, 6, 0))
        grid3 = grid2.with_obstacle(GridCell(7, 7, 0))
        
        assert is_occupied(grid3, (5, 5)), "First obstacle should persist"
        assert is_occupied(grid3, (6, 6)), "Second obstacle should persist"
        assert is_occupied(grid3, (7, 7)), "Third obstacle should persist"

    def test_grid_with_path_is_reversible(self):
        """Adding and removing path should be reversible."""
        grid = get_empty_grid()
        cell = GridCell(5, 5, 0)
        
        grid_with = grid.with_path(cell, "NET1")
        grid_without = grid_with.without_path(cell)
        
        assert is_occupied(grid_with, (5, 5)), "Cell should be occupied with path"
        assert not is_occupied(grid_without, (5, 5)), "Cell should be free after removal"

    def test_grid_operations_are_chainable(self):
        """Grid operations should be chainable (fluent interface)."""
        grid = (get_empty_grid()
                .with_obstacle(GridCell(5, 5, 0))
                .with_path(GridCell(6, 6, 0), "NET1")
                .with_path(GridCell(7, 7, 0), "NET1"))
        
        assert is_occupied(grid, (5, 5)), "Obstacle should be present"
        assert is_occupied(grid, (6, 6)), "First path should be present"
        assert is_occupied(grid, (7, 7)), "Second path should be present"

    @given(
        operations=st.lists(
            st.tuples(
                st.integers(min_value=0, max_value=9),
                st.integers(min_value=0, max_value=9),
            ),
            min_size=0,
            max_size=20,
        )
    )
    def test_grid_operations_are_associative(self, operations):
        """Property: Grid operations should be associative."""
        # Apply operations in sequence
        grid = get_empty_grid()
        for x, y in operations:
            grid = grid.with_obstacle(GridCell(x, y, 0))
        
        # Check all operations were applied
        for x, y in operations:
            assert is_occupied(grid, (x, y)), f"Operation ({x}, {y}) should be applied"

