
import logging
import sys
import math
import numpy as np
from temper_placer.routing.maze_router import MazeRouter, GridCell

def test_clearance_inflation():
    """Verify correct clearance enforcement (DRC-2)."""
    print("Testing DRC-2: Clearance Inflation...")
    
    # 0.1mm grid
    cell_size = 0.1
    grid_size = (100, 100) # 10mm x 10mm
    router = MazeRouter(
        grid_size=grid_size,
        cell_size_mm=cell_size,
        num_layers=1,
        min_clearance=0.0 # Will override per net
    )
    
    # Net A (LV): Width 0.2mm, Clearance 0.2mm
    # Placed at X=5mm (cell 50).
    pins_a = [(5.0, 1.0), (5.0, 9.0)]
    
    # Route Net A
    # Pass metrics explicitly
    print("Routing Net A (LV)...")
    path_a = router.route_net_rrr(
        "NET_A", pins_a, None, 
        trace_width_mm=0.2, clearance_mm=0.2
    )
    if not path_a.success:
        print("FAIL: Net A failed")
        return False
        
    print(f"Net A routed at X={path_a.cells[0].x}")
    # Verify A Occupancy (Should be Copper Only: Width 0.2 -> Radius 0.1 -> 1 cell)
    # Center 50. Occupied: 49, 50, 51.
    if router.occupancy[52, 5, 0] != 0:
        print(f"FAIL: Net A occupancy is too wide! Cell 52 is occupied (should be free).")
        # Check actual occupancy range
        occ_indices = np.where(router.occupancy[:, 5, 0] != 0)[0]
        print(f"Occupied X indices at Y=5: {occ_indices}")
        # Note: Depending on strict inequality in inflation, radius might be 1.
        # ceil(0.1/0.1) = 1. Range [-1, 1].
        # 50-1=49, 50+1=51. So 52 should be free.
    
    # Net B (HV): Width 0.2mm, Clearance 1.0mm (Test Case)
    # Trying to route parallel. A* should push it away.
    # Gap required = 1.0mm.
    # Center Dist required = A_h + B_h + Gap = 0.1 + 0.1 + 1.0 = 1.2mm.
    # 1.2mm = 12 cells.
    # A is at 50. B should be at <= 38 or >= 62.
    
    # Net B (HV): Width 0.2mm, Clearance 1.0mm
    # Required Center Gap = 1.2mm (12 cells).
    # Mask blocks [50-12, 50+12] = [38, 62].
    
    # CASE 1: Valid Placement (X=3.0, Dist 2.0mm)
    print("\n--- CASE 1: Valid Clearance (X=3.0mm, Dist 2.0mm) ---")
    pins_b_valid = [(3.0, 1.0), (3.0, 9.0)] # 30 is outside mask? 30 < 38. YES.
    
    path_b = router.route_net_rrr(
        "NET_B", pins_b_valid, None,
        trace_width_mm=0.2, clearance_mm=1.0
    )
    
    if not path_b.success:
        print("FAIL: Valid placement X=3.0 failed to route! (Mask too aggressive?)")
        # Check occupancy around 30.
        # Mask radius likely 12. 50-12 = 38. 30 is safe.
        return False
        
    print(f"SUCCESS: Valid placement routed at X={path_b.cells[0].x}")
    
    # CASE 2: Invalid Placement (X=4.0, Dist 1.0mm)
    print("\n--- CASE 2: Invalid Clearance (X=4.0mm, Dist 1.0mm) ---")
    pins_b_invalid = [(4.0, 1.0), (4.0, 9.0)] # 40 is inside [38, 62].
    
    path_b_inv = router.route_net_rrr(
        "NET_B_INV", pins_b_invalid, None,
        trace_width_mm=0.2, clearance_mm=1.0
    )
    
    if path_b_inv.success:
        print("FAIL: Invalid placement X=4.0 routed! (Should be blocked by clearance)")
        return False
        
    print("SUCCESS: Invalid placement correctly blocked.")
    return True

if __name__ == "__main__":
    success = test_clearance_inflation()
    sys.exit(0 if success else 1)
