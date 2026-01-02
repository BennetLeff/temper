
import logging
import sys
import jax.numpy as jnp
from temper_placer.core.board import Board, Pad
from temper_placer.core.netlist import Netlist, Component, Pin, Net
import temper_placer.io.config_loader
print(f"DEBUG: Loading config_loader from {temper_placer.io.config_loader.__file__}")
from temper_placer.io.config_loader import PlacementConstraints, NetClassRule, constraints_to_design_rules
from temper_placer.routing.maze_router import MazeRouter, CLASS_HV, CLASS_LV, CLASS_DEFAULT

logging.basicConfig(level=logging.INFO, format="%(message)s")

def run_experiment():
    print("Running EXP-05-D: Automatic Creepage via Voltage...")
    
    # 1. Setup Constraints
    # Define HV using VOLTAGE, not explicit creepage
    constraints = PlacementConstraints(
        net_class_rules={
            "HighVoltage": NetClassRule(
                name="HighVoltage",
                trace_width_mm=1.0,
                clearance_mm=2.0,
                voltage_v=340.0, # 340V -> Should trigger HV classification and creepage
                creepage_mm=0.0  # Explicitly 0 to test auto-calculation
            ),
            "LowVoltage": NetClassRule(
                name="LowVoltage",
                trace_width_mm=0.2,
                clearance_mm=0.2,
                voltage_v=3.3,
                creepage_mm=0.0
            )
        },
        net_classes={
            "NET_HV": "HighVoltage",
            "NET_LV": "LowVoltage"
        }
    )
    dr = constraints_to_design_rules(constraints)

    # DEBUG: Check what happened
    hv_rules = dr.net_classes.get("HighVoltage")
    if hv_rules:
        print(f"DEBUG_EXP: After conversion, HighVoltage voltage_v={hv_rules.voltage_v}")
        print(f"DEBUG_EXP: Rules object: {hv_rules}")
    else:
        print("DEBUG_EXP: HighVoltage rules NOT found in dr.net_classes")

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
        bounds=(96.0, 20.0), # 96x20mm -> X[2, 98]. 2mm gap < 3mm creepage.
        initial_position=(50.0, 50.0), # Center
        initial_side=0, # Top
        pins=[pin_hv]
    )
    
    # 4. Create LV Net endpoints
    # Start (50, 10) -> End (50, 90). Vertical crossing.
    
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
    print(f"Plate Center (L0): Occ={occ}, Class={cls} (Expected {CLASS_HV}/HV)")
    
    if cls != CLASS_HV:
        print("FAILURE: Plate not marked as HV! Logic for voltage->class_id failed.")
        return

    print("\n--- Route NET_LV ---")
    # Pass sides to ensure correct layer transitions
    sides = [c_start.initial_side, c_end.initial_side]
    path = router.route_net_rrr(
        "NET_LV",
        [c_start.initial_position, c_end.initial_position],
        assignment=None,
        pin_sides=sides
    )
    
    if not path.success:
        print(f"FAILURE: Could not route LV net! Reason: {path.failure_reason}")
        return
        
    print(f"SUCCESS: Route found (Length {len(path.cells)})")
    
    # Verify Geometry
    # 1. Did it use Layer 1 (Bottom)?
    layers = {c.layer for c in path.cells}
    print(f"Layers used: {layers}")
    
    if 1 not in layers:
        print("FAILURE: Did not switch to Layer 1! (Must cross underneath)")
        return
        
    # 2. Check Vias location (Creepage Check)
    vias = []
    for i in range(len(path.cells)-1):
        c_curr = path.cells[i]
        c_next = path.cells[i+1]
        if c_curr.layer != c_next.layer:
            vias.append(c_curr)
            
    print(f"Found {len(vias)} vias.")
    
    # Plate Y range: [40, 60]
    # In MazeRouter.route_net_rrr, we configured MAX_HV=400V.
    # Creepage for 400V is ~3.0mm (or 2.5mm clearance).
    # Plus Plate is on Layer 0. Vias connect L0->L1.
    # The Vias are on L0 (and L1).
    # So Vias must be away from the Plate by Creepage distance.
    # 40 - 3.0 = 37.0
    # 60 + 3.0 = 63.0
    
    safe = True
    min_dist = 999.0
    
    for v in vias:
        y_mm = v.y * 0.1 # grid * cell_size
        dist_to_plate = min(abs(y_mm - 40.0), abs(y_mm - 60.0))
        if 40.0 < y_mm < 60.0: dist_to_plate = 0.0 # Inside
        
        print(f"Via at Y={y_mm:.2f}mm. Dist to Plate: {dist_to_plate:.2f}mm")
        
        min_dist = min(min_dist, dist_to_plate)
        
        # Expected creepage ~2.5mm to 3.0mm
        if 37.5 < y_mm < 62.5:
             # Warning zone
             pass
             
        if 38.0 < y_mm < 62.0:
            print(f"  VIOLATION! Via too close (inside 2mm of plate).")
            safe = False
        else:
            print(f"  Safe (>2mm).")
            
    if min_dist > 2.5:
        print(f"SUCCESS: Min distance {min_dist:.2f}mm > 2.5mm (Auto-Creepage worked!)")
    elif min_dist > 2.0:
        print(f"PARTIAL SUCCESS: Min distance {min_dist:.2f}mm > 2.0mm. Close but maybe okay.")
    else:
        print("FAILURE: Creepage violation detected.")

if __name__ == "__main__":
    run_experiment()
