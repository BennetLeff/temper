"""Basic tests for Cython A* algorithm implementation.

This tests the core A* pathfinding without full integration,
using a simple mock grid for faster iteration.
"""

import numpy as np
import pytest
from typing import Tuple


class MockGrid:
    """Minimal mock grid for testing A* without full ClearanceGrid."""

    def __init__(self, rows: int, cols: int, layers: int, cell_size_mm: float = 1.0):
        self.rows = rows
        self.cols = cols
        self.layer_count = layers
        self.cell_size_mm = cell_size_mm
        # 0 = empty, positive = net_id, -1 = obstacle
        self.occupancy_grid = np.zeros((layers, rows, cols), dtype=np.int32)

    def _mm_to_cell(self, x: float, y: float) -> Tuple[int, int]:
        """Convert mm coordinates to grid cell indices."""
        col = int(x / self.cell_size_mm)
        row = int(y / self.cell_size_mm)
        return (row, col)

    def set_obstacle(self, row: int, col: int, layer: int = 0):
        """Mark a cell as blocked (obstacle)."""
        self.occupancy_grid[layer, row, col] = -1

    def set_net(self, row: int, col: int, layer: int, net_id: int):
        """Mark a cell as occupied by a net."""
        self.occupancy_grid[layer, row, col] = net_id


def test_straight_path():
    """Test simple straight-line path with no obstacles."""
    try:
        from temper_placer.routing.astar.astar_core import find_path_cython
    except ImportError:
        pytest.skip("Cython module not built")

    # Create 10x10 grid, 1 layer
    grid = MockGrid(rows=10, cols=10, layers=1, cell_size_mm=1.0)

    # Route from (1, 1) to (8, 8)
    config = {"via_cost": 5.0, "max_iterations": 1000}
    path = find_path_cython(
        grid=grid,
        start_pos=(1.5, 1.5),
        end_pos=(8.5, 8.5),
        net_id=1,
        config=config,
        start_layer=0,
        end_layer=0,
    )

    assert path is not None, "Should find a path in empty grid"
    assert len(path.segments) > 0, "Path should have segments"
    assert len(path.via_positions) == 0, "No vias needed for single-layer path"
    print(f"✓ Straight path: {len(path.segments)} segments, cost={path.total_cost:.2f}")


def test_path_with_obstacle():
    """Test routing around an obstacle."""
    try:
        from temper_placer.routing.astar.astar_core import find_path_cython
    except ImportError:
        pytest.skip("Cython module not built")

    # Create 10x10 grid
    grid = MockGrid(rows=10, cols=10, layers=1, cell_size_mm=1.0)

    # Add vertical wall blocking direct path
    for row in range(3, 8):
        grid.set_obstacle(row, 5, layer=0)

    # Route from (1, 1) to (1, 8) - must go around wall
    config = {"via_cost": 5.0, "max_iterations": 1000}
    path = find_path_cython(
        grid=grid,
        start_pos=(1.5, 1.5),
        end_pos=(8.5, 1.5),
        net_id=1,
        config=config,
        start_layer=0,
        end_layer=0,
    )

    assert path is not None, "Should find path around obstacle"
    assert len(path.segments) > 0, "Path should have segments"
    print(f"✓ Path with obstacle: {len(path.segments)} segments, cost={path.total_cost:.2f}")


def test_multilayer_path():
    """Test routing across multiple layers with vias."""
    try:
        from temper_placer.routing.astar.astar_core import find_path_cython
    except ImportError:
        pytest.skip("Cython module not built")

    # Create 10x10 grid, 2 layers
    grid = MockGrid(rows=10, cols=10, layers=2, cell_size_mm=1.0)

    # Block ENTIRE width on layer 0 to force via usage
    for col in range(10):
        grid.set_obstacle(5, col, layer=0)

    # Route from (1, 5, layer=0) to (9, 5, layer=0)
    # MUST use layer 1 to bypass complete blockage
    config = {"via_cost": 2.0, "max_iterations": 5000}
    path = find_path_cython(
        grid=grid,
        start_pos=(5.5, 1.5),  # col=5, row=1
        end_pos=(5.5, 9.5),  # col=5, row=9
        net_id=1,
        config=config,
        start_layer=0,
        end_layer=0,
    )

    assert path is not None, "Should find path using multiple layers"
    assert len(path.via_positions) >= 2, "Should use at least 2 vias (up and down)"
    print(
        f"✓ Multi-layer path: {len(path.segments)} segments, {len(path.via_positions)} vias, cost={path.total_cost:.2f}"
    )


def test_no_path_blocked():
    """Test that None is returned when no path exists."""
    try:
        from temper_placer.routing.astar.astar_core import find_path_cython
    except ImportError:
        pytest.skip("Cython module not built")

    # Create 10x10 grid
    grid = MockGrid(rows=10, cols=10, layers=1, cell_size_mm=1.0)

    # Completely surround the goal
    for row in range(6, 9):
        for col in range(6, 9):
            if not (row == 7 and col == 7):  # Leave center empty (goal)
                grid.set_obstacle(row, col, layer=0)

    # Try to route to surrounded goal
    config = {"via_cost": 5.0, "max_iterations": 1000}
    path = find_path_cython(
        grid=grid,
        start_pos=(1.5, 1.5),
        end_pos=(7.5, 7.5),
        net_id=1,
        config=config,
        start_layer=0,
        end_layer=0,
    )

    assert path is None, "Should return None when no path exists"
    print("✓ No path: correctly returned None")


def test_any_layer_end():
    """Test end_layer=-1 (accept any layer at goal)."""
    try:
        from temper_placer.routing.astar.astar_core import find_path_cython
    except ImportError:
        pytest.skip("Cython module not built")

    # Create 10x10 grid, 2 layers
    grid = MockGrid(rows=10, cols=10, layers=2, cell_size_mm=1.0)

    # Route with end_layer=-1 (any layer OK)
    config = {"via_cost": 5.0, "max_iterations": 1000}
    path = find_path_cython(
        grid=grid,
        start_pos=(1.5, 1.5),
        end_pos=(8.5, 8.5),
        net_id=1,
        config=config,
        start_layer=0,
        end_layer=-1,  # Accept any layer
    )

    assert path is not None, "Should find path to any layer"
    print(f"✓ Any-layer end: {len(path.segments)} segments, {len(path.via_positions)} vias")


if __name__ == "__main__":
    """Run tests manually for quick iteration."""
    print("=== Basic A* Algorithm Tests ===\n")

    test_straight_path()
    test_path_with_obstacle()
    test_multilayer_path()
    test_no_path_blocked()
    test_any_layer_end()

    print("\n✅ All basic tests passed!")
