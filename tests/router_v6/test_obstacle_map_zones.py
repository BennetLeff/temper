"""
TDD Test for Obstacle Map Zone Support.

Verifies that build_obstacle_map includes Zones and Tracks as obstacles.
"""

import unittest
from unittest.mock import MagicMock
from shapely.geometry import Polygon
from temper_placer.router_v6.obstacle_map import build_obstacle_map
from temper_placer.router_v6.stage0_data import ParsedPCB, StackupInfo, LayerInfo


class MockZone:
    def __init__(self, layer, points):
        self.layers = [layer]  # List of layers
        self.polygon = points  # list of (x, y)
        self.net_name = "GND"  # Assume it's a net we shouldn't route over if it's a keepout?
        # Or if it's a filled zone of a DIFFERENT net.
        self.is_keepout = False


class MockTrack:
    def __init__(self, layer, start, end, width, net_name):
        self.layer = layer
        self.start = start
        self.end = end
        self.width = width
        self.net_name = net_name


class TestObstacleMapZones(unittest.TestCase):
    def setUp(self):
        # Setup basic PCB
        self.pcb = MagicMock(spec=ParsedPCB)
        self.pcb.components = []
        self.pcb.stackup = StackupInfo(
            layers=[LayerInfo(0, "F.Cu", "signal", 0.035), LayerInfo(1, "B.Cu", "signal", 0.035)],
            total_thickness_mm=1.6,
            layer_count=2,
        )

        # Add a Zone on F.Cu
        # Rectangle (10, 10) to (20, 20)
        self.zone_poly = [(10, 10), (20, 10), (20, 20), (10, 20)]
        self.mock_zone = MockZone("F.Cu", self.zone_poly)
        self.pcb.zones = [self.mock_zone]

        # Add a Track on F.Cu (simulating pre-routed CGND)
        # (30, 10) to (40, 10), width 1.0
        self.mock_track = MockTrack("F.Cu", (30, 10), (40, 10), 1.0, "CGND")
        self.pcb.tracks = [self.mock_track]

    def test_zones_are_obstacles(self):
        """Verify that zones are included in the obstacle map."""
        obstacles = build_obstacle_map(self.pcb, [])

        fcu_poly = obstacles.get("F.Cu")
        self.assertIsNotNone(fcu_poly, "F.Cu should have obstacles")

        # Check if point inside zone is covered
        # Center of zone is (15, 15)
        self.assertTrue(
            fcu_poly.contains(Polygon([(14, 14), (16, 14), (16, 16), (14, 16)]).centroid),
            "Zone area should be an obstacle",
        )

    def test_tracks_are_obstacles(self):
        """Verify that pre-existing tracks are included as obstacles."""
        obstacles = build_obstacle_map(self.pcb, [])

        fcu_poly = obstacles.get("F.Cu")

        # Center of track is (35, 10). Width 1.0 -> y from 9.5 to 10.5
        # Check point (35, 10)
        self.assertTrue(
            fcu_poly.intersects(Polygon([(34, 9), (36, 9), (36, 11), (34, 11)])),
            "Track area should be an obstacle",
        )


if __name__ == "__main__":
    unittest.main()
