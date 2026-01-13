"""Integration test for Cython A* with MultiLayerAStar class."""

import os
import pytest
import numpy as np


# Mock ClearanceGrid for testing
class MockClearanceGrid:
    """Minimal mock of ClearanceGrid for integration testing."""

    def __init__(self, rows=50, cols=50, layers=4, cell_size_mm=0.5):
        self.rows = rows
        self.cols = cols
        self.layer_count = layers
        self.cell_size_mm = cell_size_mm
        self.occupancy_grid = np.zeros((layers, rows, cols), dtype=np.int32)
        self._net_ids = {}

    def _mm_to_cell(self, x, y):
        """Convert mm to cell coordinates."""
        col = int(x / self.cell_size_mm)
        row = int(y / self.cell_size_mm)
        return (row, col)

    def get_net_id(self, net_name):
        """Get or assign net ID."""
        if net_name not in self._net_ids:
            self._net_ids[net_name] = len(self._net_ids) + 1
        return self._net_ids[net_name]

    def is_available(self, x, y, layer, net_id=0):
        """Check if position is available."""
        row, col = self._mm_to_cell(x, y)
        if not (0 <= row < self.rows and 0 <= col < self.cols):
            return False
        if not (0 <= layer < self.layer_count):
            return False

        value = self.occupancy_grid[layer, row, col]
        return value == 0 or value == net_id


def test_multilayer_astar_cython_integration():
    """Test MultiLayerAStar with Cython backend."""
    # Force Cython usage
    os.environ["TEMPER_USE_CYTHON_ASTAR"] = "1"

    from temper_placer.deterministic.stages.multilayer_astar import MultiLayerAStar

    # Create mock grid
    grid = MockClearanceGrid(rows=50, cols=50, layers=2, cell_size_mm=0.5)

    # Create A* instance
    astar = MultiLayerAStar(grid=grid, net_name="test_net", via_cost=5.0, allowed_layers=[0, 1])

    # Test simple path
    path = astar.find_path(start=(1.0, 1.0), end=(10.0, 10.0), start_layer=0, end_layer=0)

    assert path is not None, "Should find path in empty grid"
    assert len(path.segments) > 0, "Path should have segments"
    print(f"✓ Cython integration: {len(path.segments)} segments, cost={path.total_cost:.2f}")


def test_multilayer_astar_python_fallback():
    """Test MultiLayerAStar falls back to Python when Cython disabled."""
    # Force Python usage
    os.environ["TEMPER_USE_CYTHON_ASTAR"] = "0"

    from temper_placer.deterministic.stages.multilayer_astar import MultiLayerAStar

    # Create mock grid
    grid = MockClearanceGrid(rows=50, cols=50, layers=2, cell_size_mm=0.5)

    # Create A* instance
    astar = MultiLayerAStar(grid=grid, net_name="test_net", via_cost=5.0, allowed_layers=[0, 1])

    # Test simple path
    path = astar.find_path(start=(1.0, 1.0), end=(10.0, 10.0), start_layer=0, end_layer=0)

    assert path is not None, "Should find path in empty grid"
    assert len(path.segments) > 0, "Path should have segments"
    assert astar.last_iterations > 0, "Python version should track iterations"
    print(f"✓ Python fallback: {len(path.segments)} segments, {astar.last_iterations} iters")


def test_cython_vs_python_consistency():
    """Verify Cython and Python produce same results."""
    grid = MockClearanceGrid(rows=50, cols=50, layers=2, cell_size_mm=0.5)

    # Add some obstacles to make it interesting
    # Block row 20, columns 10-30 on layer 0
    for i in range(10, 30):
        grid.occupancy_grid[0, 20, i] = -1

    # Test with Cython
    os.environ["TEMPER_USE_CYTHON_ASTAR"] = "1"
    from temper_placer.deterministic.stages.multilayer_astar import MultiLayerAStar as CythonAStar

    astar_cython = CythonAStar(grid=grid, net_name="test_net", via_cost=5.0, allowed_layers=[0, 1])

    # Route from (5, 5) to (5, 15) - will cross obstacle at row 20
    path_cython = astar_cython.find_path(
        start=(5.0, 5.0), end=(5.0, 20.0), start_layer=0, end_layer=0
    )

    # Test with Python
    os.environ["TEMPER_USE_CYTHON_ASTAR"] = "0"
    # Need to reload to pick up env change
    import importlib
    import temper_placer.deterministic.stages.multilayer_astar as ml_module

    importlib.reload(ml_module)
    from temper_placer.deterministic.stages.multilayer_astar import MultiLayerAStar as PythonAStar

    astar_python = PythonAStar(grid=grid, net_name="test_net", via_cost=5.0, allowed_layers=[0, 1])

    # Same route
    path_python = astar_python.find_path(
        start=(5.0, 5.0), end=(5.0, 20.0), start_layer=0, end_layer=0
    )

    # Both should find a path
    assert path_cython is not None, "Cython should find path"
    assert path_python is not None, "Python should find path"

    # Paths should have similar characteristics (may not be identical due to tie-breaking)
    print(f"  Cython: {len(path_cython.segments)} segments, {len(path_cython.via_positions)} vias")
    print(f"  Python: {len(path_python.segments)} segments, {len(path_python.via_positions)} vias")

    # Both should use similar number of vias (routing strategy should be similar)
    assert len(path_cython.via_positions) == len(path_python.via_positions), (
        "Should use same number of vias"
    )

    print("✓ Cython and Python produce consistent results")


if __name__ == "__main__":
    print("=== Cython Integration Tests ===\n")

    test_multilayer_astar_cython_integration()
    test_multilayer_astar_python_fallback()
    test_cython_vs_python_consistency()

    print("\n✅ All integration tests passed!")
