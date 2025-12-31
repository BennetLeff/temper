
import logging
import sys
import jax.numpy as jnp
from temper_placer.core.board import Board, Pad
from temper_placer.core.netlist import Netlist, Component, Pin, Net
from temper_placer.io.config_loader import PlacementConstraints, NetClassRule, constraints_to_design_rules
from temper_placer.routing.maze_router import MazeRouter, CLASS_HV, CLASS_LV

logging.basicConfig(level=logging.INFO, format="%(message)s")

def run_experiment():
    print("Running EXP-05-B: Creepage Crossing...")
    
    # 1. Setup Constraints
    # HV uses 8mm creepage
    constraints = PlacementConstraints(
        net_class_rules={
            "HighVoltage": NetClassRule(
                name="HighVoltage",
                trace_width_mm=1.0,
                clearance_mm=2.0,
                creepage_mm=8.0 # Key Constraint
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
    dr = constraints_to_design_rules(constraints)

    # 2. Setup Board & Router
    board = Board(width=100.0, height=100.0)
    router = MazeRouter(
        grid_size=(1000, 1000), # 0.1mm cell
        cell_size_mm=0.1,
        num_layers=2,
        design_rules=dr,
        min_clearance=0.1
    )
    
    # 3. Create HV Obstacle (Plate)
    # Spans X=20 to X=80, Y=40 to Y=60.
    # On Layer 0 (Top) ONLY.
    
    pin_hv = Pin(name="1", number="1", net="NET_HV", position=(0,0))
    pin_hv.width = 60.0
    pin_hv.height = 20.0
    
    c_hv_plate = Component(
        ref="HV_PLATE",
        footprint="RECT",
        bounds=(60.0, 20.0), # 60x20mm
        initial_position=(50.0, 50.0), # Center
        initial_side=0, # Top
        pins=[pin_hv]
    )
    
    # 4. Create LV Net endpoints
    # Start (50, 10) -> End (50, 90). Vertical crossing.
    # Distance to plate (Y=40): 30mm. Safe.
    
    c_start = Component(ref="S", footprint="PIN", bounds=(0.5,0.5), initial_position=(50.0, 10.0), initial_side=0, pins=[Pin(name="1", number="1", net="NET_LV", position=(0,0))])
    c_end = Component(ref="E", footprint="PIN", bounds=(0.5,0.5), initial_position=(50.0, 90.0), initial_side=0, pins=[Pin(name="1", number="1", net="NET_LV", position=(0,0))])
    
    components = [c_hv_plate, c_start, c_end]
    positions = jnp.array([c.initial_position for c in components])
    
    netlist = Netlist(
        components=components,
        nets=[
            Net(name="NET_HV", pins=[("HV_PLATE", "1")]), # Dummy net
            Net(name="NET_LV", pins=[("S", "1"), ("E", "1")])
        ]
    )
    
    print("Blocking obstacles...")
    router.block_pads(components, positions, netlist)
    
    # Verify Plate is blocked as CLASS_HV
    gx, gy = router._world_to_grid(50.0, 50.0)
    occ = router.occupancy[gx, gy, 0]
    cls = router.class_grid[gx, gy, 0]
    print(f"Plate Center (L0): Occ={occ}, Class={cls} (Expected 1/HV)")
    
    if cls != CLASS_HV:
        print("FAILURE: Plate not marked as HV!")
        return

    print("\n--- Route NET_LV ---")
    path = router.route_net_rrr(
        "NET_LV",
        [c_start.initial_position, c_end.initial_position],
        assignment=None
    )
    
    if not path.success:
        print(f"FAILURE: Could not route LV net! Reason: {path.failure_reason}")
        return
        
    print(f"SUCCESS: Route found (Length {len(path.cells)})")
    
    # Verify Geometry
    # 1. Did it use Layer 1 (Bottom)? (It MUST, to cross underneath)
    layers = {c.layer for c in path.cells}
    print(f"Layers used: {layers}")
    
    if 1 not in layers:
        print("FAILURE: Did not switch to Layer 1! (Must cross underneath)")
        return
        
    # 2. Check Vias location
    # Find layer transitions
    vias = []
    for i in range(len(path.cells)-1):
        c_curr = path.cells[i]
        c_next = path.cells[i+1]
        if c_curr.layer != c_next.layer:
            vias.append(c_curr)
            
    print(f"Found {len(vias)} vias.")
    
    # Plate Y range: [40, 60]
    # Creepage Zone: [32, 68] (40-8, 60+8)
    # Vias must be OUTSIDE this Y range.
    
    safe = True
    for v in vias:
        y_mm = v.y * 0.1 # grid * cell_size
        print(f"Via at Y={y_mm:.2f}mm")
        if 32.0 < y_mm < 68.0:
            print(f"  VIOLATION! Via inside 8mm creepage zone (32-68mm)")
            safe = False
        else:
            print(f"  Safe.")
            
    if safe:
        print("SUCCESS: All vias respecting 8mm creepage distance.")
    else:
        print("FAILURE: Creepage violation detected.")

if __name__ == "__main__":
    run_experiment()
