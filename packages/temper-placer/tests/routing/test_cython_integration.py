"""Integration tests for MultiLayerAStar class (pure-Python pathfinder).

The Cython twin (routing/astar/astar_core.pyx) was removed June 2026
as part of A* consolidation; MultiLayerAStar now uses its inline
pure-Python implementation exclusively.
"""

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


def test_multilayer_astar_simple_path():
    from temper_placer.deterministic.stages.multilayer_astar import MultiLayerAStar
    grid = MockClearanceGrid(rows=50, cols=50, layers=2, cell_size_mm=0.5)
    astar = MultiLayerAStar(grid=grid, net_name="test_net", via_cost=5.0,
                            allowed_layers=[0, 1])
    path = astar.find_path(start=(1.0, 1.0), end=(10.0, 10.0),
                           start_layer=0, end_layer=0)
    assert path is not None
    assert len(path.segments) > 0


def test_multilayer_astar_iterations_tracked():
    from temper_placer.deterministic.stages.multilayer_astar import MultiLayerAStar
    grid = MockClearanceGrid(rows=50, cols=50, layers=2, cell_size_mm=0.5)
    astar = MultiLayerAStar(grid=grid, net_name="test_net", via_cost=5.0,
                            allowed_layers=[0, 1])
    path = astar.find_path(start=(1.0, 1.0), end=(10.0, 10.0),
                           start_layer=0, end_layer=0)
    assert path is not None
    assert astar.last_iterations > 0


if __name__ == "__main__":
    print("=== MultiLayerAStar Integration Tests ===\n")

    test_multilayer_astar_simple_path()
    test_multilayer_astar_iterations_tracked()

    print("\n✅ All integration tests passed!")
