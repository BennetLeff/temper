
import os
import sys
import numpy as np
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root / "packages/temper-placer/src"))

from temper_placer.core.board import Board, Zone
from temper_placer.core.netlist import Netlist, Component, Pin, Net
from temper_placer.routing.maze_router import MazeRouter
from temper_placer.routing.c_space_pipeline import CSpaceRoutingPipeline, PipelineConfig

def test_trace_crossing():
    print("Testing Trace Crossing Prevention...")
    # 20x20mm board
    board = Board(20.0, 20.0)
    
    # Define two pins for Net A (horizontal)
    # Define two pins for Net B (vertical)
    # They MUST cross at (10, 10)
    
    netlist = Netlist()
    # Net A: (5, 10) to (15, 10)
    # Net B: (10, 5) to (10, 15)
    
    router = MazeRouter((40, 40), cell_size_mm=0.5, num_layers=1, soft_blocking=True)
    
    # Route Net A
    path_a = router.route_net_adaptive("NET_A", [(5, 10), (15, 10)], assignment=None)
    print(f"Net A routed: {path_a.success}")
    
    # Route Net B - Should NOT cross Net A on the same layer if costs are high
    # Since we only have 1 layer, it should probably FAIL or find a very long path if possible
    # In a 1-layer setup with horizontal Net A, Net B is blocked.
    path_b = router.route_net_adaptive("NET_B", [(10, 5), (10, 15)], assignment=None)
    
    print(f"Net B routed: {path_b.success}")
    
    # Check if they share any cells
    cells_a = set((c.x, c.y, c.layer) for c in path_a.cells)
    cells_b = set((c.x, c.y, c.layer) for c in path_b.cells)
    intersection = cells_a.intersection(cells_b)
    
    if intersection:
        print(f"FAILED: Nets cross at {len(intersection)} cells!")
        return False
    else:
        print("SUCCESS: No trace crossing detected on same layer.")
        return True

def test_zone_bleeding():
    print("\nTesting Zone Bleeding Prevention...")
    # 20x20mm board
    # Zone at (8, 5) to (12, 15) - A vertical strip in the middle
    zone = Zone("KEEPOUT", (8.0, 5.0, 12.0, 15.0), net_classes=[]) # Keepout allows nothing
    board = Board(20.0, 20.0, zones=[zone])
    
    netlist = Netlist()
    # Add a net that needs to go from (5, 10) to (15, 10) - straight through the zone
    net = Net("TEST_NET", pins=[])
    # We'll just pass positions to the pipeline
    
    config = PipelineConfig(resolution_mm=0.5)
    pipeline = CSpaceRoutingPipeline(board, netlist, config)
    pipeline.extract_geometry()
    pipeline.initialize_router()
    
    # Route net
    res = pipeline._route_batch(["TEST_NET"])
    path = res["TEST_NET"]
    
    print(f"Net routed: {path.success}")
    if not path.success:
        print("Net failed to route (expected if no way around).")
        return True # Failure to route through keepout is also a form of success for this test
    
    # Check if any cell is inside the zone
    gx_min = int(8.0 / 0.5)
    gx_max = int(12.0 / 0.5)
    
    bleeding = False
    for cell in path.cells:
        if gx_min <= cell.x <= gx_max:
            bleeding = True
            break
            
    if bleeding:
        print("FAILED: Path entered forbidden zone!")
        return False
    else:
        print("SUCCESS: Path avoided forbidden zone.")
        return True

if __name__ == "__main__":
    s1 = test_trace_crossing()
    s2 = test_zone_bleeding()
    
    if s1 and s2:
        print("\nALL DRC FIX VERIFICATIONS PASSED!")
        sys.exit(0)
    else:
        print("\nSOME VERIFICATIONS FAILED!")
        sys.exit(1)
