"""
TDD Test for Dynamic Occupancy Check in Path Simplifier.

Verifies that the simplifier respects dynamic obstacles (other nets)
present in the OccupancyGrid but not in the static SDF.
"""

import unittest
import numpy as np
from temper_placer.routing.geometry_fields.sdf_builder import SDFGrid
from temper_placer.routing.exact_geometry.path_simplifier import PathSimplifier
from temper_placer.router_v6.occupancy_grid import OccupancyGrid


class TestPathSimplifierDynamic(unittest.TestCase):
    def setUp(self):
        # 1. Setup Static SDF (All Safe/Free)
        # Grid 10x10mm, resolution 0.1mm -> 100x100 cells
        width_cells = 100
        height_cells = 100
        resolution = 0.1

        # Distance = 10.0 (far from any obstacle)
        sdf_data = np.full((height_cells, width_cells), 10.0)

        self.sdf = SDFGrid(
            distance_grid=sdf_data,
            origin=(0.0, 0.0),
            cell_size=resolution,
            width_cells=width_cells,
            height_cells=height_cells,
        )

        self.sdf_grids = {"F.Cu": self.sdf}

        # 2. Setup Dynamic OccupancyGrid (With a blockage)
        # Blockage at x=5.0 (indices ~50)
        # Net ID 2 is the blocker. Net ID 1 is the router.
        grid_data = np.zeros((height_cells, width_cells), dtype=np.int32)

        # Create a wall at x=50 (x=5.0mm)
        # From y=0 to y=100
        grid_data[:, 50] = 2  # Net 2 (Blocker)

        self.occ_grid = OccupancyGrid(
            layer_name="F.Cu",  # Missing arg fixed
            grid=grid_data,
            origin=(0.0, 0.0),
            cell_size=resolution,
            width_cells=width_cells,
            height_cells=height_cells,
        )

        self.occ_grids = {"F.Cu": self.occ_grid}

    def test_dynamic_obstacle_rejection(self):
        """
        Verify that a shortcut crossing a dynamic obstacle is rejected.

        Path: (4.0, 5.0) -> (6.0, 5.0).
        Static SDF: Safe (Distance 10.0 everywhere).
        Dynamic Grid: Blocked at x=5.0 by Net 2.

        Expected: Shortcut rejected.
        """
        # Initialize simplifier
        simplifier = PathSimplifier(
            sdf_grids=self.sdf_grids,
            step_size_mm=0.1,
            min_clearance_margin=0.1,
            occupancy_grids=self.occ_grids,  # New parameter
        )

        # Check segment (4,5) -> (6,5) for Net 1
        # It crosses x=5 (Net 2). Should return False.

        # We need to expose _check_segment_safety or call simplify
        # Let's test the check method directly for precision

        start = (4.0, 5.0)
        end = (6.0, 5.0)
        net_id = 1

        is_safe = simplifier._check_segment_safety(
            start,
            end,
            self.sdf,
            0.1,
            occupancy_grid=self.occ_grid,  # Pass explicit grid
            net_id=net_id,
        )

        self.assertFalse(is_safe, "Simplifier should reject path crossing dynamic obstacle (Net 2)")

        # Test valid path (staying on left side)
        # (4.0, 5.0) -> (4.5, 5.0)
        is_safe_valid = simplifier._check_segment_safety(
            (4.0, 5.0), (4.5, 5.0), self.sdf, 0.1, occupancy_grid=self.occ_grid, net_id=net_id
        )
        self.assertTrue(is_safe_valid, "Simplifier should accept valid path")

    def test_self_overlap_allowed(self):
        """Verify that crossing OWN net traces is allowed."""
        # Update grid to be owned by Net 1 at wall
        self.occ_grid.grid[:, 50] = 1  # Net 1

        simplifier = PathSimplifier(sdf_grids=self.sdf_grids, occupancy_grids=self.occ_grids)

        is_safe = simplifier._check_segment_safety(
            (4.0, 5.0),
            (6.0, 5.0),
            self.sdf,
            0.1,
            occupancy_grid=self.occ_grid,
            net_id=1,  # Same net
        )

        self.assertTrue(is_safe, "Simplifier should allow crossing own net cells")


if __name__ == "__main__":
    unittest.main()
