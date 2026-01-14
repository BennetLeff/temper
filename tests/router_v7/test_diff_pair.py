"""
TDD Test for Differential Pair Routing (Phase 10).

Verifies that D+ and D- are routed as a coupled pair with constant spacing.
"""

import unittest
import numpy as np
from temper_placer.router_v6.occupancy_grid import OccupancyGrid
# We will create this
# from temper_placer.router_v7.diff_pair_router import DiffPairRouter


class TestDiffPairRouting(unittest.TestCase):
    def setUp(self):
        # 10x10 Grid, 0.1mm resolution
        resolution = 0.1
        w_cells = 100
        h_cells = 100

        self.grid = OccupancyGrid(
            layer_name="F.Cu",
            grid=np.zeros((h_cells, w_cells), dtype=np.int16),
            origin=(0, 0),
            cell_size=resolution,
            width_cells=w_cells,
            height_cells=h_cells,
        )
        self.grid.__post_init__()

        # Define Pair
        # Spacing: 0.2mm gap. Trace width 0.2mm.
        # Center-to-center pitch: 0.2 + 0.2 = 0.4mm.
        # If we route the "Virtual Center", the physical traces are at +/- 0.2mm.
        self.trace_width = 0.2
        self.pair_gap = 0.2
        self.pitch = self.trace_width + self.pair_gap  # 0.4mm

        # Start/End
        # Start at (1.0, 1.0). Target (9.0, 1.0).
        # Obstacle at (5.0, 1.0).
        # Pair must detour around obstacle TOGETHER.

        # Mark obstacle
        self.grid.mark_via_blocked(5.0, 1.0, 1.0, 0.0, 999)  # 1mm blocker

    def test_coupled_routing_with_fanout(self):
        from temper_placer.router_v7.diff_pair_router import DiffPairRouter

        router = DiffPairRouter(self.grid)

        # Start Pads: Connector (Wide Pitch 0.8mm)
        start_p = (1.0, 1.4)  # Y=1.4
        start_n = (1.0, 0.6)  # Y=0.6. Dist=0.8

        # End Pads: Chip (Narrow Pitch 0.4mm, matches target)
        end_p = (9.0, 1.2)
        end_n = (9.0, 0.8)  # Dist=0.4

        # Target spacing
        width = 0.2
        gap = 0.2  # Target Pitch = 0.4

        # Call new method
        result = router.route_pair_with_fanout(start_p, start_n, end_p, end_n, width, gap)

        self.assertIsNotNone(result, "Should find path with fanout")
        path_p, path_n = result

        # 1. Connectivity
        # Check start/end points
        self.assertEqual(path_p.coordinates[0], start_p)
        self.assertEqual(path_p.coordinates[-1], end_p)

        # 2. Coupling (Middle section)
        # Check middle points
        mid_idx = len(path_p.coordinates) // 2
        p_mid = path_p.coordinates[mid_idx]
        n_mid = path_n.coordinates[mid_idx]
        dist = ((p_mid[0] - n_mid[0]) ** 2 + (p_mid[1] - n_mid[1]) ** 2) ** 0.5

        print(f"Mid-Path Spacing: {dist:.3f}mm (Target 0.4mm)")
        self.assertAlmostEqual(dist, 0.4, delta=0.1, msg="Middle section should be coupled")


if __name__ == "__main__":
    unittest.main()
