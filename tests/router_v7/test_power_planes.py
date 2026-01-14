"""
TDD Test for Power Plane Synthesis (Phase 9).

Verifies that power planes are generated correctly around seeds and avoid obstacles.
"""

import unittest
from shapely.geometry import Point, Polygon, box
from temper_placer.router_v6.stage0_data import ParsedPCB
from temper_placer.core.netlist import Net, Pin, Component

# We will create this module
# from temper_placer.router_v7.power_planes import PowerPlaneGenerator


class TestPowerPlanes(unittest.TestCase):
    def setUp(self):
        # Setup PCB
        # Board 10x10
        self.board_bounds = (0, 0, 10, 10)

        # VCC Net with 2 pads
        self.vcc_net = Net(name="VCC", pins=[])  # Pins added later

        # Obstacle (Signal Trace)
        # Rect from (4, 0) to (6, 10) blocking the middle
        self.obstacle = box(4, 0, 6, 10)

        # Pins
        # Pin 1 at (2, 5) - Left side
        # Pin 2 at (8, 5) - Right side
        # Since middle is blocked, we expect 2 disjoint islands or a U-shape if top/bottom open.
        # Let's block middle fully.

        self.pads = [
            (2.0, 5.0),  # Left
            (8.0, 5.0),  # Right
        ]

    def test_plane_generation(self):
        """Verify basic plane generation avoiding obstacles."""
        from temper_placer.router_v7.power_planes import PowerPlaneGenerator

        generator = PowerPlaneGenerator(self.board_bounds)

        # Add Obstacle
        generator.add_obstacle(self.obstacle)

        # Generate Plane for VCC
        # Returns list of Polygons
        planes = generator.generate_plane(self.pads, clearance=0.5)

        # Checks
        self.assertTrue(len(planes) > 0, "Should generate at least one plane")

        # Check clearance
        for plane in planes:
            # Must not intersect obstacle (with clearance)
            # Actually we subtract obstacle + clearance
            self.assertFalse(plane.intersects(self.obstacle), "Plane should not short to obstacle")

        # Check connectivity (Seeds covered)
        # Pin 1 (2,5)
        covered_1 = any(p.contains(Point(2, 5)) for p in planes)
        self.assertTrue(covered_1, "Pin 1 must be connected to plane")

        # Pin 2 (8,5)
        covered_2 = any(p.contains(Point(8, 5)) for p in planes)
        self.assertTrue(covered_2, "Pin 2 must be connected to plane")


if __name__ == "__main__":
    unittest.main()
