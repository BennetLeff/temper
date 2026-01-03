
import jax.numpy as jnp
import pytest
from temper_placer.core.board import Board
from temper_placer.core.netlist import Netlist, Component, Pin, Net
from temper_placer.io.config_loader import PlacementConstraints, NetClassRule, constraints_to_design_rules
from temper_placer.routing.maze_router import MazeRouter, CLASS_HV

def test_creepage_crossing():
    """
    EXP-05-B Verification:
    Verify HV/LV separation in dense crossing scenarios.
    - HV Plate on Layer 0 (Top).
    - LV Net crossing vertically.
    - Must switch to Layer 1 (Bottom) to cross.
    - Vias must be outside 8mm creepage zone.
    """
    
    # 1. Setup Constraints
    constraints = PlacementConstraints(
        net_class_rules={
            "HighVoltage": NetClassRule(
                name="HighVoltage",
                trace_width_mm=1.0,
                clearance_mm=2.0,
                creepage_mm=8.0 
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
        bounds=(60.0, 20.0), 
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
            Net(name="NET_HV", pins=[("HV_PLATE", "1")]), 
            Net(name="NET_LV", pins=[("S", "1"), ("E", "1")])
        ]
    )
    
    router.block_pads(components, positions, netlist)
    
    # Verify Plate is blocked as CLASS_HV
    gx, gy = router._world_to_grid(50.0, 50.0)
    cls = router.class_grid[gx, gy, 0]
    assert cls == CLASS_HV, f"Plate center at (50,50) L0 not marked as CLASS_HV (Got {cls})"
    
    path = router.route_net_rrr(
        "NET_LV",
        [c_start.initial_position, c_end.initial_position],
        assignment=None
    )
    
    assert path.success, f"Could not route LV net! Reason: {path.failure_reason}"
    
    # Verify Geometry
    # 1. Did it use Layer 1 (Bottom)?
    layers = {c.layer for c in path.cells}
    assert 1 in layers, "LV Net did not switch to Layer 1 to cross HV plate!"
        
    # 2. Check Vias location
    vias = []
    for i in range(len(path.cells)-1):
        c_curr = path.cells[i]
        c_next = path.cells[i+1]
        if c_curr.layer != c_next.layer:
            vias.append(c_curr)
            
    assert len(vias) >= 2, f"Expected at least 2 vias for crossing, found {len(vias)}"
    
    # Plate Y range: [40, 60]
    # Creepage Zone: [32, 68] (40-8, 60+8)
    # Vias must be OUTSIDE this Y range.
    
    violation_count = 0
    for v in vias:
        y_mm = v.y * 0.1 
        if 32.0 < y_mm < 68.0:
            violation_count += 1
            print(f"Via Violation at Y={y_mm:.2f}mm")
            
    assert violation_count == 0, f"Found {violation_count} vias inside 8mm creepage zone (32-68mm)"
