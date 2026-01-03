
import logging
import sys
import numpy as np
from temper_placer.routing.maze_router import MazeRouter, GridCell

def test_net_isolation():
    """Verify that nets cannot cross each other (strict isolation)."""
    print("Testing DRC-1: Net Isolation...")
    
    # 10x10 grid, 1 layer (to force collision)
    # 1.0mm cell size for simplicity
    router = MazeRouter(
        grid_size=(10, 10),
        cell_size_mm=1.0,
        num_layers=1,
        soft_blocking=True # RRR mode (usually allows shorts)
    )
    
    # Net A: Horizontal (1, 5) -> (8, 5)
    # Net B: Vertical (5, 1) -> (5, 8)
    # They MUST cross at (5, 5)
    
    pins_a = [(1.0, 5.0), (8.0, 5.0)]
    pins_b = [(5.0, 1.0), (5.0, 8.0)]
    
    print("Routing Net A...")
    path_a = router.route_net_rrr("NET_A", pins_a, None)
    if not path_a.success:
        print("FAIL: Net A failed to route")
        return False
        
    print(f"Net A routed: {len(path_a.cells)} cells")
    
    # Verify owner
    if router.cell_owner[(5, 5, 0)] != "NET_A":
        print(f"FAIL: Ownership not registered! Owner at (5,5): {router.cell_owner.get((5,5,0))}")
        return False
        
    print("Routing Net B (Should fail due to strict isolation)...")
    path_b = router.route_net_rrr("NET_B", pins_b, None)
    
    if path_b.success:
        print("FAIL: Net B routed successfully (Short created!)")
        # Check for intersection
        cells_a = set((c.x, c.y) for c in path_a.cells)
        cells_b = set((c.x, c.y) for c in path_b.cells)
        intersection = cells_a.intersection(cells_b)
        print(f"Intersection cells: {intersection}")
        print(f"Path A: {sorted(list(cells_a))}")
        print(f"Path B: {sorted(list(cells_b))}")
        print(f"Occupancy at (5,5,0): {router.occupancy[5,5,0]}")
        print(f"Cell Owner at (5,5,0): {router.cell_owner.get((5,5,0))}")
        return False
    else:
        print("SUCCESS: Net B failed to route (Isolation working)")
        # Verify failure reason contains "blocked"
        print(f"Failure Reason: {path_b.failure_reason}")
        return True

if __name__ == "__main__":
    success = test_net_isolation()
    sys.exit(0 if success else 1)
