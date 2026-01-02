
import logging
import sys
import jax.numpy as jnp
from temper_placer.core.board import Board
from temper_placer.core.netlist import Netlist, Component, Pin, Net
from temper_placer.io.config_loader import PlacementConstraints, NetClassRule, constraints_to_design_rules
from temper_placer.routing.maze_router import MazeRouter

logging.basicConfig(level=logging.INFO, format="%(message)s")

def run_experiment():
    print("Running EXP-06-B: The Via Farm...")
    
    # 1. Setup Constraints
    # High Current Net: 20A.
    # Needs wide traces and MULTIPLE vias.
    constraints = PlacementConstraints(
        net_class_rules={
            "HighPower": NetClassRule(
                name="HighPower",
                trace_width_mm=3.0, 
                clearance_mm=1.0,
                via_size_mm=1.0,
                via_template="Via4x4"  # 16 vias for 20A
            )
        },
        net_classes={
            "NET_PWR_20A": "HighPower"
        }
    )
    dr = constraints_to_design_rules(constraints)

    # 2. Board & Router
    router = MazeRouter(
        grid_size=(100, 100), # 10x10mm
        cell_size_mm=0.1,
        num_layers=2,
        design_rules=dr,
        min_clearance=0.1
    )
    
    # 3. Setup Layer Transition Scenario
    # Start: (2.0, 5.0) on Layer 0
    # End: (8.0, 5.0) on Layer 1
    # This FORCES a via transition.
    
    c_start = Component(ref="S", footprint="PIN", bounds=(0.5,0.5), initial_position=(2.0, 5.0), initial_side=0, 
                        pins=[Pin(name="1", number="1", net="NET_PWR_20A", position=(0,0))])
    
    # End component is on BOTTOM (Layer 1)
    # MazeRouter logic for blocking pads usually assumes top layer unless side is specified.
    # initial_side=1 means Bottom.
    c_end = Component(ref="E", footprint="PIN", bounds=(0.5,0.5), initial_position=(8.0, 5.0), initial_side=1, 
                      pins=[Pin(name="1", number="1", net="NET_PWR_20A", position=(0,0))])
                      
    components = [c_start, c_end]
    netlist = Netlist(components=components, nets=[])
    pos_arr = jnp.array([c.initial_position for c in components])
    
    print("Blocking obstacles...")
    router.block_pads(components, pos_arr, netlist)
    
    print("Routing High Power Net (Layer 0 -> Layer 1)...")
    path = router.route_net_rrr("NET_PWR_20A", [c_start.initial_position, c_end.initial_position], assignment=None)
    
    if not path.success:
        print(f"FAILURE: Routing failed. Reason: {path.failure_reason}")
        return

    print("SUCCESS: Route found.")
    
    # Count Vias
    # A via is a transition between layers in the path cells.
    # In MazeRouter, a via might be a distinct cell type or just implied by layer change.
    # We look for layer changes.
    
    vias = []
    # Identify unique (x,y) locations where layer changes occur
    via_locations = set()
    
    for i in range(len(path.cells)-1):
        c_curr = path.cells[i]
        c_next = path.cells[i+1]
        
        if c_curr.layer != c_next.layer:
            # Found a via transition
            # Note: Transition usually happens at the same X,Y or neighbor.
            # Standard via is at c_curr.x, c_curr.y
            via_locations.add((c_curr.x, c_curr.y))
            
    num_vias = len(via_locations)
    print(f"Via Count: {num_vias}")
    
    # We defined via_size_mm=1.0.
    # A single via handles maybe 3-5A. 
    # For 20A, we need at least 4-6 vias (a "Via Farm").
    
    if num_vias < 2:
        print("OBSERVATION: Router placed a SINGLE via (Expected failure mode for V5).")
        print("FAIL: High current nets require a via array/cluster.")
    else:
        print(f"SUCCESS: Router placed {num_vias} vias!")

if __name__ == "__main__":
    run_experiment()
