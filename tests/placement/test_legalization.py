"""
TDD Test for Placement Legalizer.

Verifies that overlaps are resolved.
"""

import unittest
from unittest.mock import MagicMock
from temper_placer.placement.legalization import Legalizer
from temper_placer.router_v6.stage0_data import ParsedPCB
from temper_placer.core.netlist import Component, Pin


class TestLegalizer(unittest.TestCase):
    def setUp(self):
        # Create components overlapping
        # C1 at (0, 0), 10x10mm
        # C2 at (5, 0), 10x10mm
        # Overlap area 50mm^2 (5x10)

        pin1 = Pin(name="1", number="1", position=(-5.0, -5.0))
        pin2 = Pin(name="2", number="2", position=(5.0, 5.0))
        pin3 = Pin(name="3", number="3", position=(-5.0, 5.0))
        pin4 = Pin(name="4", number="4", position=(5.0, -5.0))
        pins = [pin1, pin2, pin3, pin4]

        self.c1 = Component(
            ref="C1",
            footprint="Test:C1",
            bounds=(10.0, 10.0),
            pins=pins,
            initial_position=(0.0, 0.0),
            initial_rotation=0,
        )

        self.c2 = Component(
            ref="C2",
            footprint="Test:C2",
            bounds=(10.0, 10.0),
            pins=pins,
            initial_position=(5.0, 0.0),
            initial_rotation=0,
        )

        self.pcb = MagicMock(spec=ParsedPCB)
        self.pcb.components = [self.c1, self.c2]

    def test_legalization(self):
        legalizer = Legalizer(self.pcb, step_size=0.2, max_iterations=50)
        success = legalizer.legalize()

        self.assertTrue(success, "Legalization should converge")

        # Verify positions moved apart
        x1 = self.c1.initial_position[0]
        x2 = self.c2.initial_position[0]
        dist = abs(x2 - x1)

        # Should be > 10.0 + margin (approx 11.0 due to 0.5 buffer on each)
        # Courtyard is 11x11 (10 + 0.5*2)
        # So distance must be >= 11.0

        self.assertGreaterEqual(dist, 11.0, "Components should be separated")

        # Verify no collisions remaining
        from temper_placer.placement.audit import PlacementAuditor

        auditor = PlacementAuditor(self.pcb)
        collisions = auditor.check_collisions()
        self.assertEqual(len(collisions), 0)


if __name__ == "__main__":
    unittest.main()
