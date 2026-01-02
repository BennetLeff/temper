#!/usr/bin/env python3
"""
EXP-17: Resonant Tank Routing (L_RESONANT + C_RESONANT)

Verifies that the router can handle the high-current resonant tank connection
which carries 40A peak. Requires 3mm traces and 4x4 via arrays for layer transitions.
"""

import sys
import logging
from pathlib import Path
import jax.numpy as jnp
import numpy as np

# Adjust path to import packages
sys.path.insert(0, str(Path(__file__).parent.parent / "packages" / "temper-placer" / "src"))

from temper_placer.core.board import Board
from temper_placer.core.netlist import Netlist, Component, Pin, Net
from temper_placer.io.config_loader import load_constraints, constraints_to_design_rules
from temper_placer.core.design_rules import NetClassRules
from temper_placer.routing.maze_router import MazeRouter
from temper_placer.routing.layer_assignment import LayerAssignment, Layer
from temper_placer.routing.hierarchical import route_net_hierarchical

logging.basicConfig(level=logging.INFO, format="%(message)s")

def create_resonant_tank_exp():
    print("Loading constraints from YAML...")
    config_path = Path(__file__).parent.parent / "packages" / "temper-placer" / "configs" / "temper_constraints.yaml"
    constraints = load_constraints(config_path)
    dr = constraints_to_design_rules(constraints)

    # 1. Define HighCurrent rule for RESONANT_TANK
    # Note: YAML already has HighCurrent as 3.0mm width and Via4x4
    print("Configuring design rules for RESONANT_TANK...")
    dr.net_overrides["RESONANT_TANK"] = NetClassRules(
        name="HighCurrent",
        trace_width=3.0,
        clearance=1.0,
        via_template="Via4x4"
    )
    
    # 2. Define Components
    # L_TANK: Resonant Inductor terminal on Top layer
    l_pins = [Pin(name="1", number="1", net="RESONANT_TANK", position=(0.0, 0.0))]
    # C_TANK: Resonant Capacitor on Bottom layer (side=1)
    c_pins = [Pin(name="1", number="1", net="RESONANT_TANK", position=(0.0, 0.0))]

    components = [
        Component(ref="L_TANK", footprint="TerminalBlock_8x10", bounds=(8.0, 10.0), initial_position=(30.0, 70.0), initial_side=0, pins=l_pins),
        Component(ref="C_TANK", footprint="Capacitor_Large_Film", bounds=(15.0, 30.0), initial_position=(70.0, 70.0), initial_side=1, pins=c_pins),
    ]

    # 3. Create Netlist
    net_map = {"RESONANT_TANK": [("L_TANK", "1"), ("C_TANK", "1")]}
    nets = [Net(name=n, pins=p) for n, p in net_map.items()]
    netlist = Netlist(components=components, nets=nets)
    pos_arr = jnp.array([c.initial_position for c in components])

    # 4. Router Setup
    print("Initializing MazeRouter...")
    router = MazeRouter(
        grid_size=(500, 500), 
        cell_size_mm=0.2,
        num_layers=2,
        design_rules=dr,
        min_clearance=0.1
    )
    
    print("Blocking pads...")
    router.block_pads(components, pos_arr, netlist)
    
    print("Routing Resonant Tank Net (Hierarchical)...")
    # Hierarchical routing is preferred for high-current wide traces to handle clearance efficiently
    
    # Need to get grid pins
    grid_pins = []
    pin_world = [(30.0, 70.0), (70.0, 70.0)]
    pin_sides = [0, 1]
    
    assignment = LayerAssignment(
        net="RESONANT_TANK",
        primary_layer=Layer.L1_TOP,
        allowed_layers={Layer.L1_TOP, Layer.L4_BOT},
        vias_required=True
    )

    # Call hierarchical router directly
    route = route_net_hierarchical(
        router,
        net_name="RESONANT_TANK",
        pin_positions=pin_world,
        assignment=assignment,
        pin_sides=pin_sides,
        trace_width_mm=3.0,
        clearance_mm=1.0,  # From YAML for HighCurrent
    )
    
    print("\n" + "="*40)
    print("RESULTS")
    print("="*40)
    
    if route.success:
        print(f"✅ RESONANT_TANK: Length={route.length:.1f}mm")
        print(f"   Via Count (Logical): {route.via_count}")
        print(f"   Explicit Via Count: {len(route.explicit_vias)}")
        
        if len(route.explicit_vias) >= 16:
            print("   ✅ SUCCESS: Via array generated correctly (16 vias for 4x4)")
        else:
            print(f"   ❌ FAILURE: Expected at least 16 vias, got {len(route.explicit_vias)}")
        
        # Verify trace width
        print(f"   Estimated Trace Width: {route.trace_width}mm")
        if route.trace_width >= 3.0:
            print("   ✅ SUCCESS: Trace width meets 40A requirement (3.0mm)")
        else:
            print(f"   ❌ FAILURE: Trace width {route.trace_width}mm < 3.0mm")
    else:
        print(f"❌ RESONANT_TANK: FAILED (Reason: {route.failure_reason})")

if __name__ == "__main__":
    create_resonant_tank_exp()
