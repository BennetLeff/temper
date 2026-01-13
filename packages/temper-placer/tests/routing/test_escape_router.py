
import unittest
from unittest.mock import MagicMock
from pathlib import Path
import sys

# Ensure packages are in path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from temper_placer.routing.escape_router import EscapeRouter, EscapeResult
from temper_placer.routing.fanout import FanoutConfig
from temper_placer.core.netlist import Netlist, Component, Net, Pin
from kiutils.board import Board

class TestEscapeRouter(unittest.TestCase):
    def setUp(self):
        # Create a simple netlist
        self.pins = [
            Pin(name="1", number="1", position=(-1.0, -1.0)),
            Pin(name="2", number="2", position=(1.0, -1.0)),
            Pin(name="3", number="3", position=(-1.0, 1.0)),
            Pin(name="4", number="4", position=(1.0, 1.0)),
            Pin(name="5", number="5", position=(0.0, 0.0)), # Trapped in center
        ]
        
        self.comp = Component(
            ref="U1",
            footprint="TestFP",
            bounds=(4.0, 4.0),
            pins=self.pins,
            initial_position=(50.0, 50.0)
        )
        
        self.net = Net(name="NET1", pins=[("U1", "5"), ("U1", "1")])
        self.netlist = Netlist(components=[self.comp], nets=[self.net])
        
        self.ki_board = Board()
        self.ki_board.traceItems = []
        self.ki_board.nets = [MagicMock()]
        self.ki_board.nets[0].name = "NET1"
        
        self.config = FanoutConfig(pitch=1.0)
        self.router = EscapeRouter(self.ki_board, self.netlist, self.config)

    def test_route_net_escapes(self):
        result = self.router.route_net_escapes("NET1")
        
        self.assertTrue(result.success)
        self.assertEqual(result.net_name, "NET1")
        self.assertEqual(len(result.escape_positions), 2)
        
        # Verify that positions have shifted (dog-bone)
        # Pin 5 was at (50, 50). 
        # With 3x3 grid (simulated by pins 1-4 and 5), Pin 5 is center.
        # RingClassifier should put it in Ring 1.
        # Escape direction should be NW (default for center if multiple flags match)
        # Actually it depends on the bounds of all pins.
        
        # We just check if they are different from original
        for orig, esc in zip(result.original_positions, result.escape_positions):
            self.assertNotEqual(orig, esc)
            
        # Verify vias were added to board
        via_count = sum(1 for item in self.ki_board.traceItems if hasattr(item, 'drill'))
        self.assertEqual(via_count, 2)

if __name__ == '__main__':
    unittest.main()
