
import sys
import logging
from pathlib import Path
import numpy as np
import time

# Adjust path to import packages
sys.path.insert(0, str(Path(__file__).parent.parent / "packages" / "temper-placer" / "src"))

from temper_placer.core.board import Board
from temper_placer.core.design_rules import DesignRules, NetClassRules
from temper_placer.routing.maze_router import MazeRouter, CLASS_HV, CLASS_LV, CLASS_DEFAULT
from temper_placer.routing.layer_assignment import LayerAssignment, Layer

logging.basicConfig(level=logging.INFO, format="%(message)s")

def run_experiment():
    print("EXP-19: HV/LV Asymmetric Clearance Verification")
    print("===============================================")
    
    # 1. Setup Rules
    # Define HV class with voltage > 60V (triggers CLASS_HV)
    hv_rules = NetClassRules(
        name="HighVoltage",
        trace_width=0.5,
        clearance=0.5, # Standard clearance (masked by asymmetric check)
        voltage_v=340.0, # Triggers CLASS_HV
        creepage_mm=8.0  # Just for reference
    )
    
    lv_rules = NetClassRules(
        name="LowVoltage",
        trace_width=0.2,
        clearance=0.2,
        voltage_v=3.3
    )
    
    dr = DesignRules()
    dr.net_overrides["HV_NET"] = hv_rules
    dr.net_overrides["LV_NET"] = lv_rules
    
    # 2. Initialize Router
    # 100x50 grid (1mm cells)
    router = MazeRouter(
        grid_size=(100, 50),
        cell_size_mm=1.0,
        num_layers=1,
        design_rules=dr,
        min_clearance=0.0 # We want to rely on class checks
    )
    
    print(f"Router Grid: {router.grid_size}, Cell Size: {router.cell_size}mm")
    
    # 3. Route HV Net (The Obstacle)
    # Horizontal trace at Y=10
    print("\n1. Routing HV_NET (Y=10)...")
    # Manually route to ensure it's exactly where we want
    hv_start = (0.0, 10.0)
    hv_end = (100.0, 10.0)
    
    # Route
    res_hv = router.route_net_adaptive(
        "HV_NET",
        [hv_start, hv_end],
        LayerAssignment("HV_NET", Layer.L1_TOP, {Layer.L1_TOP})
    )
    print(f"   HV Result: {res_hv.success}, Length: {res_hv.length}")
    
    # Verify HV class registration
    # Check a cell on the trace
    gx, gy = router._world_to_grid(50, 10)
    cls = router.class_grid[gx, gy, 0]
    print(f"   Class ID at (50, 10): {cls} (Expected {CLASS_HV})")
    print(f"   Total Class Grid Sum: {np.sum(router.class_grid)}")
    print(f"   Class Grid Dtype: {router.class_grid.dtype}")
    assert cls == CLASS_HV, "HV Net did not register as CLASS_HV"
    
    # 4. Route LV Net (The Victim)
    # Start (10, 20) -> End (90, 20)
    # Ideally would go straight line at Y=20 (Distance 10mm from Y=10)
    # Required separation: 8mm. 
    # 10mm > 8mm. Safe.
    
    # NOW, introduce a BLOCKER at Y=15 to Y=50 for X=40 to X=60
    # This forces LV net to dip DOWN towards HV net to pass.
    # Blockage: A physical obstacle (not HV)
    print("\n2. Adding Physical Blockage (Y=18 to Y=50)...")
    # We block everything ABOVE Y=18. 
    # LV net starts at Y=20, so it must go DOWN to <18 to pass.
    # It must squeeze between HV (Y=10) and Block (Y=18).
    # Gap is 18 - 10 = 8mm.
    # Keepout from HV is 8mm. Keepout ends at Y=10+8 = 18.
    # So Y=18 is barely safe?
    # If we block Y=17...
    # Block Y=17 to 50.
    # Gap is 10 to 17. 7mm space.
    # Required 8mm.
    # LV should FAIL to find a path.
    
    # Let's try to route.
    
    # Manually block grid
    # Block X=30 to 70, Y=17 to 49
    block_start_x, block_end_x = 30, 70
    block_start_y, block_end_y = 17, 49
    
    for x in range(block_start_x, block_end_x):
        for y in range(block_start_y, block_end_y):
            router.occupancy[x, y, 0] = -1 # Blocked
            
    print(f"   Blocked region: X=[{block_start_x}, {block_end_x}], Y=[{block_start_y}, {block_end_y}]")
            
    print("\n3. Routing LV_NET (Should FAIL due to proximity)...")
    lv_start = (10.0, 20.0)
    lv_end = (90.0, 20.0)
    
    t0 = time.time()
    res_lv = router.route_net_adaptive(
        "LV_NET",
        [lv_start, lv_end],
        LayerAssignment("LV_NET", Layer.L1_TOP, {Layer.L1_TOP})
    )
    t1 = time.time()
    
    print(f"   LV Result: {res_lv.success}")
    print(f"   Time: {(t1-t0)*1000:.2f}ms")
    
    if res_lv.success:
        # Analyze min distance
        min_dist = 100.0
        for cell in res_lv.cells:
            # Distance to Y=10
            dist = abs(cell.y - 10) * router.cell_size
            if dist < min_dist:
                min_dist = dist
        
        print(f"   Minimum distance to HV: {min_dist}mm (Required: 8.0mm)")
        
        if min_dist < 8.0:
            print("   ❌ FAILURE: LV Net routed too close to HV!")
            sys.exit(1)
        else:
            print("   ✅ SUCCESS: LV Net maintained required clearance (forced to detour).")

    else:
        print("   ✅ SUCCESS: LV Net failed to route (correctly blocked by HV proximity)")
        
    # 5. Remove blockage and verify success
    print("\n4. Relaxing blockage (Y=20 to 50)...")
    
    # Rip up previous LV route to clear board
    router.rip_up_net("LV_NET")
    
    # Clear previous block
    for x in range(block_start_x, block_end_x):
        for y in range(block_start_y, block_end_y):
            router.occupancy[x, y, 0] = 0
            
    # New block: Y=22 to 50. Gap 12mm. Safe.
    block_start_y = 22
    for x in range(block_start_x, block_end_x):
        for y in range(block_start_y, block_end_y):
            router.occupancy[x, y, 0] = -1

    print("   Routing LV_NET (Should SUCCEED)...")
    res_lv_2 = router.route_net_adaptive(
        "LV_NET",
        [lv_start, lv_end],
        LayerAssignment("LV_NET", Layer.L1_TOP, {Layer.L1_TOP})
    )
    
    if res_lv_2.success:
        min_dist = 100.0
        for cell in res_lv_2.cells:
            dist = abs(cell.y - 10) * router.cell_size
            if dist < min_dist:
                min_dist = dist
        print(f"   ✅ SUCCESS: LV Net routed. Min Dist: {min_dist}mm")
    else:
        print(f"   ❌ FAILURE: LV Net failed to route even with space! Reason: {res_lv_2.failure_reason}")
        sys.exit(1)

if __name__ == "__main__":
    run_experiment()
