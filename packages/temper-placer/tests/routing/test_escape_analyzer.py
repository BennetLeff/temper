import unittest
from temper_placer.routing.escape_analyzer import RingClassifier, PinInfo, EscapeDirection

class TestEscapeAnalyzer(unittest.TestCase):
    def test_3x3_grid(self):
        # 3x3 grid centered at 1,1
        pins = []
        for x in range(3):
            for y in range(3):
                pins.append(PinInfo(id=f"{x}_{y}", x=float(x), y=float(y)))
                
        classifier = RingClassifier(pins)
        results = classifier.analyze()
        
        # Outer Ring (Ring 0)
        self.assertEqual(results["0_0"].ring_index, 0)
        self.assertEqual(results["0_0"].direction, EscapeDirection.NORTH_WEST)
        
        self.assertEqual(results["1_0"].ring_index, 0)
        self.assertEqual(results["1_0"].direction, EscapeDirection.NORTH)  # y=0 is top (min_y)
        
        self.assertEqual(results["2_0"].ring_index, 0)
        self.assertEqual(results["2_0"].direction, EscapeDirection.NORTH_EAST)
        
        self.assertEqual(results["0_1"].ring_index, 0)
        self.assertEqual(results["0_1"].direction, EscapeDirection.WEST)
        
        self.assertEqual(results["2_1"].ring_index, 0)
        self.assertEqual(results["2_1"].direction, EscapeDirection.EAST)
        
        self.assertEqual(results["0_2"].ring_index, 0)
        self.assertEqual(results["0_2"].direction, EscapeDirection.SOUTH_WEST)
        
        self.assertEqual(results["1_2"].ring_index, 0)
        self.assertEqual(results["1_2"].direction, EscapeDirection.SOUTH)
        
        self.assertEqual(results["2_2"].ring_index, 0)
        self.assertEqual(results["2_2"].direction, EscapeDirection.SOUTH_EAST)
        
        # Inner Ring (Ring 1) - The center pin
        self.assertEqual(results["1_1"].ring_index, 1)
        # Center pin in 1x1 rect hits all edges, defaults to NW in current logic
        self.assertEqual(results["1_1"].direction, EscapeDirection.NORTH_WEST)

    def test_4x4_grid(self):
        # 4x4 grid
        pins = []
        for x in range(4):
            for y in range(4):
                pins.append(PinInfo(id=f"{x}_{y}", x=float(x), y=float(y)))
                
        classifier = RingClassifier(pins)
        results = classifier.analyze()
        
        # Check inner 2x2 block
        # (1,1), (2,1)
        # (1,2), (2,2)
        
        self.assertEqual(results["1_1"].ring_index, 1)
        self.assertEqual(results["1_1"].direction, EscapeDirection.NORTH_WEST)
        
        self.assertEqual(results["2_1"].ring_index, 1)
        self.assertEqual(results["2_1"].direction, EscapeDirection.NORTH_EAST)
        
        self.assertEqual(results["1_2"].ring_index, 1)
        self.assertEqual(results["1_2"].direction, EscapeDirection.SOUTH_WEST)
        
        self.assertEqual(results["2_2"].ring_index, 1)
        self.assertEqual(results["2_2"].direction, EscapeDirection.SOUTH_EAST)

    def test_rectangular_grid(self):
        # 3x5 grid
        # x: 0..2
        # y: 0..4
        pins = []
        for x in range(3):
            for y in range(5):
                pins.append(PinInfo(id=f"{x}_{y}", x=float(x), y=float(y)))
                
        classifier = RingClassifier(pins)
        results = classifier.analyze()
        
        # Center column (x=1)
        # (1,0) -> Ring 0, N
        # (1,4) -> Ring 0, S
        
        # Inner block: x=1, y=1..3
        # (1,1) -> Ring 1. Bounds of remaining: x[1,1], y[1,3].
        
        self.assertEqual(results["1_1"].ring_index, 1)
        self.assertEqual(results["1_1"].direction, EscapeDirection.NORTH_WEST) # Because width is 1
        
        # (1,2) -> Middle of inner strip.
        self.assertEqual(results["1_2"].ring_index, 1)
        self.assertEqual(results["1_2"].direction, EscapeDirection.WEST)
        
        # (1,3) -> Bottom of inner strip.
        self.assertEqual(results["1_3"].ring_index, 1)
        self.assertEqual(results["1_3"].direction, EscapeDirection.SOUTH_WEST)

if __name__ == '__main__':
    unittest.main()
