"""
TDD Test for Negotiated Congestion (PathFinder).

Verifies that congestion costs force nets to diversify paths.
"""

import unittest
import numpy as np
from temper_placer.router_v6.occupancy_grid import OccupancyGrid, CellState


class TestCongestionSolver(unittest.TestCase):
    def setUp(self):
        # 10x10 Grid
        self.grid = OccupancyGrid(
            layer_name="Test",
            grid=np.zeros((10, 10), dtype=np.int16),
            origin=(0, 0),
            cell_size=1.0,
            width_cells=10,
            height_cells=10,
        )
        # Initialize congestion arrays
        self.grid.__post_init__()

    def test_history_cost_accumulation(self):
        """Verify history cost increases on congestion."""
        # Use cell (5,5) twice
        self.grid.add_usage(5, 5)
        self.grid.add_usage(5, 5)

        self.assertEqual(self.grid.usage_count[5, 5], 2)

        # Update history
        self.grid.update_history_cost(history_factor=1.0)

        # History cost should increase by usage * factor = 2 * 1.0 = 2.0
        self.assertEqual(self.grid.congestion_cost[5, 5], 2.0)

        # Uncongested cell should be 0
        self.assertEqual(self.grid.congestion_cost[0, 0], 0.0)

    def test_cost_function(self):
        """Verify get_cost includes congestion."""
        self.grid.add_usage(5, 5)
        self.grid.congestion_cost[5, 5] = 10.0

        # Base(1) + Usage(1 * Penalty=2) + History(10) = 13
        cost = self.grid.get_cost(5, 5, current_congestion_penalty=2.0)
        self.assertEqual(cost, 13.0)


if __name__ == "__main__":
    unittest.main()
