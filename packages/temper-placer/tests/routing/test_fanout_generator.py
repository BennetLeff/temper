import unittest
from unittest.mock import MagicMock
from temper_placer.routing.fanout import FanoutGenerator, FanoutConfig
from temper_placer.core.netlist import Netlist, Component, Net, Pin
from kiutils.board import Board

class TestFanoutIntegration(unittest.TestCase):
    def test_fanout_directions(self):
        # Create a simple netlist with one component and one net
        # Component: 3x3 grid of pins
        pins = []
        for x in range(3):
            for y in range(3):
                pins.append(Pin(
                    name=f"{x}_{y}", 
                    number=str(x*3+y), 
                    position=(float(x), float(y))
                ))
        
        comp = Component(
            ref="U1",
            footprint="TestFP",
            bounds=(10.0, 10.0),
            pins=pins,
            initial_position=(100.0, 100.0) # Center of component
        )
        
        # Net connecting to pin (1,1) (Center) -> Should escape NW
        net_center = Net(name="NET_CENTER", pins=[("U1", "1_1")])
        
        # Net connecting to pin (2,1) (Right Edge) -> Should escape E
        net_right = Net(name="NET_RIGHT", pins=[("U1", "2_1")])
        
        netlist = Netlist(components=[comp], nets=[net_center, net_right])
        board = Board() # Mock board
        board.traceItems = [] # Manually init list if kiutils doesn't
        board.nets = [MagicMock(name="NET_CENTER"), MagicMock(name="NET_RIGHT")]
        # Mock board.nets items to have .name attribute matching net names
        board.nets[0].name = "NET_CENTER"
        board.nets[1].name = "NET_RIGHT"

        config = FanoutConfig(pitch=1.0) # 1mm pitch for easy math
        generator = FanoutGenerator(board, netlist, config)
        
        # Generate fanouts
        new_positions = generator.generate_fanouts()
        
        # Verify NET_CENTER (Pin 1_1 at 101, 101)
        # Expected: NW direction. Offset (-0.5, -0.5).
        # Pin pos: 101, 101.
        # Via pos: 100.5, 100.5.
        
        self.assertIn("NET_CENTER", new_positions)
        center_pts = new_positions["NET_CENTER"]
        self.assertEqual(len(center_pts), 1)
        vx, vy = center_pts[0]
        self.assertAlmostEqual(vx, 100.5)
        self.assertAlmostEqual(vy, 100.5)
        
        # Verify NET_RIGHT (Pin 2,1 at 102, 101)
        # Expected: EAST direction. Offset (+0.5, 0).
        # Pin pos: 102, 101.
        # Via pos: 102.5, 101.
        
        self.assertIn("NET_RIGHT", new_positions)
        right_pts = new_positions["NET_RIGHT"]
        self.assertEqual(len(right_pts), 1)
        vx2, vy2 = right_pts[0]
        self.assertAlmostEqual(vx2, 102.5)
        self.assertAlmostEqual(vy2, 101.0)

if __name__ == '__main__':
    unittest.main()
