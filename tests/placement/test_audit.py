"""
TDD Test for Placement Auditor.

Verifies detection of overlapping components.
"""

import unittest
from unittest.mock import MagicMock
from temper_placer.placement.audit import PlacementAuditor
from temper_placer.router_v6.stage0_data import ParsedPCB
from temper_placer.core.netlist import Component, Pin


class TestPlacementAuditor(unittest.TestCase):
    def setUp(self):
        # Create components
        # C1 at (0, 0), 10x10mm (pins at corners)
        # C2 at (5, 0), 10x10mm
        # Overlap should be detected

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
            initial_position=(5.0, 0.0),  # Shifted by 5mm. C1 ends at x=5. C2 starts at x=0.
            # C1 hull: [-5, 5] x [-5, 5].
            # C2 hull: [0, 10] x [-5, 5].
            # Overlap: [0, 5] x [-5, 5]. Area 25.
            initial_rotation=0,
        )

        self.pcb = MagicMock(spec=ParsedPCB)
        self.pcb.components = [self.c1, self.c2]

    def test_collision_detection(self):
        auditor = PlacementAuditor(self.pcb)
        collisions = auditor.check_collisions()

        self.assertEqual(len(collisions), 1, "Should find 1 collision")
        c = collisions[0]
        self.assertEqual(c.ref1, "C1")
        self.assertEqual(c.ref2, "C2")
        self.assertGreater(c.area, 0.0)

    def test_no_collision(self):
        # Move C2 far away
        self.c2.initial_position = (20.0, 0.0)
        auditor = PlacementAuditor(self.pcb)
        collisions = auditor.check_collisions()
        self.assertEqual(len(collisions), 0, "Should find 0 collisions")


if __name__ == "__main__":
    unittest.main()
