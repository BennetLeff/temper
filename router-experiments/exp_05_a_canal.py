
import logging
import sys
import jax.numpy as jnp
import numpy as np
from temper_placer.core.board import Board
from temper_placer.core.netlist import Netlist, Component, Pin, Net
from temper_placer.io.config_loader import PlacementConstraints, NetClassRule, constraints_to_design_rules
from temper_placer.routing.maze_router import MazeRouter

logging.basicConfig(level=logging.INFO, format="%(message)s")

def run_experiment():
    print("Running EXP-05-A: High Current Canal...")
    
    # 1. Setup Constraints
    constraints = PlacementConstraints(
        net_class_rules={
            "Power": NetClassRule(
                name="Power",
                trace_width_mm=2.0,
                clearance_mm=0.2, # Width=2.0, Clearance=0.2 -> Total width required = 2.4mm (center-to-edge of obstacle)
                                  # Wait, clearance is edge-to-edge.
                                  # If canal is 1.0mm wide, and obstacles are at y=0 and y=1.0?
                                  # Effective space = 1.0mm.
                                  # Trace width 2.0mm obviously doesn't fit.
                                  # Signal width 0.2mm + 2*0.2 (clearance) = 0.6mm -> Fits.
            ),
            "Signal": NetClassRule(
                name="Signal",
                trace_width_mm=0.2,
                clearance_mm=0.2 
            )
        },
        net_classes={
            "NET_PWR": "Power",
            "NET_SIG": "Signal"
        }
    )
    dr = constraints_to_design_rules(constraints)

    # 2. Setup Board & Router
    # 10x10mm board
    board = Board(width=10.0, height=10.0)
    router = MazeRouter(
        grid_size=(100, 100), # 0.1mm cell
        cell_size_mm=0.1,
        num_layers=2,
        design_rules=dr,
        min_clearance=0.1 # Base clearance
    )
    
    # 3. Create Canal using Components (Walls)
    # Canal width 1.0mm.
    # Center y = 5.0.
    # Top Wall: y > 5.5
    # Bottom Wall: y < 4.5
    # We'll place large components to form these walls.
    
    # Component 1 (Top Wall): Height 4.0, y_pos = 5.5 + 2.0 = 7.5
    c_top = Component(
        ref="WALL_TOP",
        footprint="RECT",
        bounds=(10.0, 4.0),
        initial_position=(5.0, 7.5),
        initial_side=0,
        pins=[]
    )
    # Component 2 (Bottom Wall): Height 4.0, y_pos = 4.5 - 2.0 = 2.5
    c_bottom = Component(
        ref="WALL_BOT",
        footprint="RECT",
        bounds=(10.0, 4.0), 
        initial_position=(5.0, 2.5),
        initial_side=0,
        pins=[]
    )
    
    # Pins for routing through the canal
    # Start (1.0, 5.0) -> End (9.0, 5.0)
    # Nets start/end outside but must pass through canal
    
    # We define virtual pins/components for start/end points
    c_start = Component(ref="START", footprint="PIN", bounds=(0.2,0.2), initial_position=(1.0, 5.0), initial_side=0)
    c_end = Component(ref="END", footprint="PIN", bounds=(0.2,0.2), initial_position=(9.0, 5.0), initial_side=0)
    
    components = [c_top, c_bottom, c_start, c_end] # Virtual pins not necessarily needed in list for block_pads if we handle them separately?
    # Actually block_pads marks components. We want walls blocked.
    
    # Positions array
    positions = jnp.array([c.initial_position for c in components])
    
    # Netlist (dummy for block_pads compliance)
    netlist = Netlist(components=components, nets=[])
    
    # Block Pads (Create the canal)
    print("Blocking obstacles...")
    router.block_pads(components, positions, netlist)
    
    # 4. Attempt Routing
    
    # Case A: NET_SIG (0.2mm width)
    print("\n--- Route NET_SIG (0.2mm) ---")
    # Expected: Success
    path_sig = router.route_net_rrr(
        "NET_SIG",
        [c_start.initial_position, c_end.initial_position],
        assignment=None
    )
    if path_sig.success:
        print("SUCCESS: NET_SIG routed through 1.0mm canal.")
    else:
        print(f"FAILURE: NET_SIG failed to route. Reason: {path_sig.failure_reason}")
        
    # Case B: NET_PWR (2.0mm width)
    print("\n--- Route NET_PWR (2.0mm) ---")
    # Expected: Failure
    path_pwr = router.route_net_rrr(
        "NET_PWR",
        [c_start.initial_position, c_end.initial_position],
        assignment=None
    )
    if path_pwr.success:
        print("FAILURE: NET_PWR routed through 1.0mm canal (Should have failed!).")
    else:
        print(f"SUCCESS: NET_PWR failed as expected (Reason: {path_pwr.failure_reason}).")

    # Case C: Wide Canal (2.5mm) -> NET_PWR Should Pass
    print("\n--- Route NET_PWR (2.0mm) in Wide Canal (2.5mm) ---")
    
    # Re-initialize router for clean slate
    router_wide = MazeRouter(
        grid_size=(100, 100), 
        cell_size_mm=0.1,
        num_layers=2,
        design_rules=dr,
        min_clearance=0.1
    )
    
    # Canal 2.5mm wide. Center 5.0. 
    # Top Wall: y > 6.25. Pos = 6.25 + 2.0 = 8.25
    # Bot Wall: y < 3.75. Pos = 3.75 - 2.0 = 1.75
    c_top_w = Component(ref="WALL_TOP", footprint="RECT", bounds=(10.0, 4.0), initial_position=(5.0, 8.25), initial_side=0, pins=[])
    c_bot_w = Component(ref="WALL_BOT", footprint="RECT", bounds=(10.0, 4.0), initial_position=(5.0, 1.75), initial_side=0, pins=[])
    
    comps_wide = [c_top_w, c_bot_w, c_start, c_end]
    pos_wide = jnp.array([c.initial_position for c in comps_wide])
    
    print("Blocking wide obstacles...")
    router_wide.block_pads(comps_wide, pos_wide, netlist)
    
    path_pwr_wide = router_wide.route_net_rrr(
        "NET_PWR",
        [c_start.initial_position, c_end.initial_position],
        assignment=None
    )
    
    if path_pwr_wide.success:
        print("SUCCESS: NET_PWR routed through 2.5mm canal.")
    else:
        print(f"FAILURE: NET_PWR failed in wide canal! Reason: {path_pwr_wide.failure_reason}")

if __name__ == "__main__":
    run_experiment()
