"""
TDD Test for Path Simplifier Clearance Logic.

Verifies that the PathSimplifier correctly accounts for trace width
when checking clearance against the SDF.
"""

import unittest
import numpy as np
from temper_placer.routing.geometry_fields.sdf_builder import SDFGrid
from temper_placer.routing.exact_geometry.path_simplifier import PathSimplifier
from temper_placer.router_v6.astar_pathfinding import RoutePath


class TestPathSimplifierClearance(unittest.TestCase):
    def setUp(self):
        # Create a synthetic SDF
        # Obstacle at x <= 10. Free space x > 10.
        # SDF = x - 10
        # We need a grid covering x=9 to x=12

        resolution = 0.1
        width_cells = 40
        height_cells = 120  # Cover up to Y=12.0

        # Grid values: distance to x=10
        # dim 0 is y, dim 1 is x
        # Use arange to match resolution exactly
        x_coords = np.arange(9.0, 9.0 + width_cells * resolution, resolution)
        # Broadcast to 2D
        dist_grid = x_coords - 10.0
        sdf_data = np.tile(dist_grid, (height_cells, 1))

        self.sdf = SDFGrid(
            distance_grid=sdf_data,
            origin=(9.0, 0.0),
            cell_size=resolution,
            width_cells=width_cells,
            height_cells=height_cells,
        )

        self.sdf_grids = {"F.Cu": self.sdf}

    def test_centerline_fallacy(self):
        """
        Verify H1: The centerline must be (width/2 + clearance) away.

        Scenario:
        - Obstacle edge: x = 10.0
        - Trace width: 0.5mm (half-width = 0.25mm)
        - Clearance: 0.2mm
        - Required Distance: 0.45mm (x >= 10.45)

        Test Path: Vertical line at x = 10.4
        - Distance = 0.4mm
        - 0.4 < 0.45, so this violates clearance!
        - Current Logic (SDF > clearance): 0.4 > 0.2 (Passes - WRONG)
        """
        trace_width = 0.5
        clearance = 0.2

        # The simplifier is initialized with min_clearance_margin
        # To fix H1, we must pass (width/2 + clearance)
        # But first, let's test the FAILURE of the old logic

        # OLD LOGIC simulation: margin = clearance
        simplifier_bad = PathSimplifier(
            sdf_grids=self.sdf_grids,
            min_clearance_margin=clearance,  # 0.2
        )

        # Path: (10.4, 0) -> (10.4, 10)
        # This segment is unsafe but "simplifier_bad" will think it's safe
        # Debug clearance reading
        clearance_at_test = self.sdf.get_distance(10.4, 5.0)
        print(f"DEBUG: Clearance at x=10.4 is {clearance_at_test}")

        safe = simplifier_bad._check_segment_safety((10.4, 0.0), (10.4, 10.0), self.sdf)
        self.assertTrue(safe, "Old logic incorrectly marks unsafe path as safe (Reproduced H1)")

        # CORRECT LOGIC: margin = width/2 + clearance
        required_margin = (trace_width / 2.0) + clearance  # 0.45

        simplifier_good = PathSimplifier(
            sdf_grids=self.sdf_grids,
            min_clearance_margin=required_margin,  # 0.45
        )

        safe = simplifier_good._check_segment_safety((10.4, 0.0), (10.4, 10.0), self.sdf)
        self.assertFalse(safe, "Correct logic should reject path at 0.4mm distance")

        # Test a valid path at x = 10.5 (Dist 0.5 > 0.45)
        safe_valid = simplifier_good._check_segment_safety((10.5, 0.0), (10.5, 10.0), self.sdf)
        self.assertTrue(safe_valid, "Correct logic should accept path at 0.5mm distance")


if __name__ == "__main__":
    unittest.main()
