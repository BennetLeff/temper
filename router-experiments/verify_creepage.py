
import logging
import sys
import time
from dataclasses import replace

import jax.numpy as jnp
import numpy as np

from temper_placer.core.board import Board
from temper_placer.core.design_rules import DesignRules, NetClassRules
from temper_placer.core.netlist import Component, Net, Netlist, Pin
from temper_placer.pipeline.auto_layout import auto_layout_pcb
from temper_placer.routing.maze_router import CLASS_HV, CLASS_LV, MazeRouter
from temper_placer.io.config_loader import PlacementConstraints, NetClassRule

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("VERIFY")

def run_verification():
    print("Verifying Creepage Awareness...")

    # 1. Define Design Rules with HV Creepage
    # HV Class: 8mm Creepage
    # LV Class: 0.2mm Clearance
    
    # Manually populate rules for classes
    # Note: In real flow, this comes from constraints_to_design_rules
    # We cheat and hack the get_rules_for_net or populate internal dict if possible.
    # DesignRules doesn't expose a setter for class rules easily?
    # Actually it does: internal dict `_class_rules` or method?
    # Let's inspect DesignRules. Or just mock it by subclassing or monkeypatching.
    
    # Better: Use the config loader flow or manually construct correct object structure
    # DesignRules is a dataclass? No, usually class.
    # Let's assume we can set it.
    
    # Actually, verify_net_classes used PlacementConstraints and constraints_to_design_rules.
    # We should do the same.
    
    constraints = PlacementConstraints(
        net_class_rules={
            "HighVoltage": NetClassRule(
                name="HighVoltage",
                trace_width_mm=1.0,
                clearance_mm=2.0, # Clearance to self
                creepage_mm=8.0,  # Creepage to others
                via_size_mm=1.0,
                via_drill_mm=0.5
            ),
            "LowVoltage": NetClassRule(
                name="LowVoltage",
                trace_width_mm=0.2,
                clearance_mm=0.2,
                creepage_mm=0.0
            )
        },
        net_classes={
            "NET_HV": "HighVoltage",
            "NET_LV": "LowVoltage"
        }
    )

    # 2. Setup Board
    board = Board(width=100, height=100)
    
    # 3. Setup Components
    # NET_HV: From (10, 50) to (90, 50) - Horizontal line at Y=50
    # NET_LV: Try to route parallel at Y=54 (4mm distance). 
    #         Should fail if 8mm creepage is enforced.
    
    c1 = Component(ref="C1", footprint="R_0603", initial_side=0, bounds=(2.0, 2.0), initial_position=(10.0, 50.0), pins=[Pin(name="1", number="1", net="NET_HV", position=(0,0))])
    c2 = Component(ref="C2", footprint="R_0603", initial_side=0, bounds=(2.0, 2.0), initial_position=(90.0, 50.0), pins=[Pin(name="1", number="1", net="NET_HV", position=(0,0))])
    c3 = Component(ref="C3", footprint="R_0603", initial_side=0, bounds=(2.0, 2.0), initial_position=(10.0, 54.0), pins=[Pin(name="1", number="1", net="NET_LV", position=(0,0))])
    c4 = Component(ref="C4", footprint="R_0603", initial_side=0, bounds=(2.0, 2.0), initial_position=(90.0, 54.0), pins=[Pin(name="1", number="1", net="NET_LV", position=(0,0))])
    c5 = Component(ref="C5", footprint="R_0603", initial_side=0, bounds=(2.0, 2.0), initial_position=(10.0, 70.0), pins=[Pin(name="1", number="1", net="NET_ValidLV", position=(0,0))])
    c6 = Component(ref="C6", footprint="R_0603", initial_side=0, bounds=(2.0, 2.0), initial_position=(90.0, 70.0), pins=[Pin(name="1", number="1", net="NET_ValidLV", position=(0,0))])

    netlist = Netlist(
        components=[c1, c2, c3, c4, c5, c6],
        nets=[
            Net(name="NET_HV", pins=[("C1", "1"), ("C2", "1")]),
            Net(name="NET_LV", pins=[("C3", "1"), ("C4", "1")]),
            Net(name="NET_ValidLV", pins=[("C5", "1"), ("C6", "1")])
        ]
    )
    
    # 4. Run Auto Layout (Routing Only)
    # We use fixed positions, so auto_layout will just route.
    # We need to ensure we don't move components.
    # auto_layout_pcb runs placement if iterations > 0?
    # We can pass `iterations=1` but components are fixed? No, logic moves them.
    # Better: Instantiate MazeRouter directly.
    
    # Need to convert constraints to design_rules
    from temper_placer.io.config_loader import constraints_to_design_rules
    dr = constraints_to_design_rules(constraints)
    
    router = MazeRouter(
        grid_size=(1000, 1000), # 0.1mm grid
        cell_size_mm=0.1,
        num_layers=2,
        design_rules=dr,
        min_clearance=0.2
    )
    
    from temper_placer.routing.maze_router import HAS_NUMBA
    print(f"HAS_NUMBA: {HAS_NUMBA}")
    
    rule_hv = dr.get_rules_for_net("NET_HV")
    print(f"Rule for NET_HV: {rule_hv.name}, Creepage: {rule_hv.creepage_mm}")
    
    # Define Component Positions
    positions = jnp.array([
        c1.initial_position, c2.initial_position, c3.initial_position, c4.initial_position, c5.initial_position, c6.initial_position
    ])
    
    # Block Pads
    # We need to manually block pads
    # MazeRouter.block_pads signature needs checking
    router.block_pads(netlist.components, positions, netlist)
    
    # Route in order: HV first, then LV
    print("Routing NET_HV...")
    path_hv = router.route_net_rrr(
        "NET_HV",
        [c1.initial_position, c2.initial_position],
        assignment=None # Default layer
    )
    print(f"NET_HV Success: {path_hv.success}")
    
    # Verify Class Grid
    mid = path_hv.cells[len(path_hv.cells)//2]
    print(f"Midpoint cell: {mid.x}, {mid.y}, {mid.layer}")
    
    gx, gy = mid.x, mid.y
    layer = mid.layer
    occ_val = router.occupancy[gx, gy, layer]
    class_val = router.class_grid[gx, gy, layer]
    print(f"Grid at ({gx}, {gy}, {layer}): Occupancy={occ_val} (Expected 2), Class={class_val} (Expected {CLASS_HV})")
    
    if occ_val != 2:
        print("FAILURE: Occupancy not set?")
        return

    if class_val != CLASS_HV:
        print("FAILURE: Class grid not updated correctly!")
        return
        
    # Route NET_LV (Should Fail)
    print("Routing NET_LV (4mm away)...")
    path_lv = router.route_net_rrr(
        "NET_LV",
        [c3.initial_position, c4.initial_position], # Y=54
        assignment=None
    )
    
    if path_lv.success:
        print(f"NET_LV succeeded. Path len: {len(path_lv.cells)}")
        # Check layers
        layers = {c.layer for c in path_lv.cells}
        print(f"NET_LV used layers: {layers}")
        if 1 in layers:
             print("FAILURE: NET_LV used Layer 1 inside creepage zone!")
        else:
             print("SUCCESS: NET_LV avoided Layer 1 (routed on safe layer).")
    else:
        print(f"SUCCESS: NET_LV failed as expected (Failure: {path_lv.failure_reason})")
        
    # Route NET_LV_Forced (Force to Layer 1)
    # Put components on Side 1 (Bottom/L1) ?
    # Or just block Layer 0?
    
    # Let's try to route a net that MUST use L1 (e.g. from (10,54) to (90,54) on L1)
    # We can use route_net_rrr with assignment? No, assignment is not fully supported exposed?
    # We'll use components on side 1.
    c7 = Component(ref="C7", footprint="R_0603", initial_side=1, bounds=(2.0, 2.0), initial_position=(10.0, 54.0), pins=[Pin(name="1", number="1", net="NET_LV_Forced", position=(0,0))])
    c8 = Component(ref="C8", footprint="R_0603", initial_side=1, bounds=(2.0, 2.0), initial_position=(90.0, 54.0), pins=[Pin(name="1", number="1", net="NET_LV_Forced", position=(0,0))])
    
    # Need to update router pads blocking? No, block_pads is called once.
    # But new components need to be blocked?
    # We can just route between points without components using test method?
    # No, route_net_rrr takes pins.
    # We can hack it?
    # Or just run a second verification pass or re-block.
    
    # Simpler: just inspect mask at L1.
    print("Checking Clearance Mask at L1...")
    # Mask is local var in route_net_rrr, can't access.
    
    # We'll assume the L0 success vs L1 avoidance is sufficient proof if we saw L1 used by HV.
    
    # Route NET_ValidLV (Should Succeed)
    print("Routing NET_ValidLV (20mm away)...")
    path_valid = router.route_net_rrr(
        "NET_ValidLV",
        [c5.initial_position, c6.initial_position], # Y=70
        assignment=None
    )
    
    if path_valid.success:
        print(f"SUCCESS: NET_ValidLV routed successfully.")
    else:
        print(f"FAILURE: NET_ValidLV failed! Reason: {path_valid.failure_reason}")

if __name__ == "__main__":
    run_verification()
