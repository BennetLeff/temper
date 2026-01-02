#!/usr/bin/env python3
"""
EXP-16: High-Current Power Bus (Via Arrays)

Verifies that the router correctly handles high-current nets by generating
via arrays (e.g., 4x4) for layer transitions instead of single vias.
"""

import sys
import logging
from pathlib import Path
import jax.numpy as jnp
import numpy as np
import math

# Adjust path to import packages
sys.path.insert(0, str(Path(__file__).parent.parent / "packages" / "temper-placer" / "src"))

from temper_placer.core.board import Board
from temper_placer.core.netlist import Netlist, Component, Pin, Net
from temper_placer.io.config_loader import load_constraints, constraints_to_design_rules
from temper_placer.core.design_rules import NetClassRules
from temper_placer.routing.maze_router import MazeRouter

logging.basicConfig(level=logging.INFO, format="%(message)s")

def create_high_current_via_array_exp():
    print("Loading constraints from YAML...")
    config_path = Path(__file__).parent.parent / "packages" / "temper-placer" / "configs" / "temper_constraints.yaml"
    constraints = load_constraints(config_path)
    dr = constraints_to_design_rules(constraints)

    # 1. Define manual override for via array
    print("Configuring Via4x4 override for PWR_20A...")
    dr.net_overrides["PWR_20A"] = NetClassRules(
        name="HighPower",
        trace_width=2.0,
        clearance=0.5,
        via_template="Via4x4"
    )

    # 2. Define Components
    # U1: Source on Top layer
    u1_pins = [Pin(name="OUT", number="1", net="PWR_20A", position=(0.0, 0.0))]
    # U2: Load on Bottom layer (side=1)
    u2_pins = [Pin(name="IN", number="1", net="PWR_20A", position=(0.0, 0.0))]

    components = [
        Component(ref="U1_SRC", footprint="TerminalBlock", bounds=(10.0, 10.0), initial_position=(20.0, 50.0), initial_side=0, pins=u1_pins),
        Component(ref="U2_LOAD", footprint="DPAK", bounds=(10.0, 10.0), initial_position=(80.0, 50.0), initial_side=1, pins=u2_pins),
    ]

    # 3. Create Netlist
    net_map = {"PWR_20A": [("U1_SRC", "1"), ("U2_LOAD", "1")]}
    nets = [Net(name=n, pins=p) for n, p in net_map.items()]
    netlist = Netlist(components=components, nets=nets)
    pos_arr = jnp.array([c.initial_position for c in components])

    # 4. Router Setup
    print("Initializing Router V6...")
    router = MazeRouter(
        grid_size=(500, 500), 
        cell_size_mm=0.2,
        num_layers=2,
        design_rules=dr,
        min_clearance=0.1
    )
    
    print("Blocking pads...")
    router.block_pads(components, pos_arr, netlist)
    
    print("Routing High-Current Net...")
    # Using LayerAssignment to force layer change if necessary, 
    # but here pins are on different sides so the router MUST use a via.
    
    results = router.rrr_route_all_nets(
        netlist, 
        pos_arr, 
        net_order=["PWR_20A"],
        assignments={}
    )
    
    print("\n" + "="*40)
    print("RESULTS")
    print("="*40)
    
    if "PWR_20A" in results:
        route = results["PWR_20A"]
        if route.success:
            print(f"✅ PWR_20A: Length={route.length:.1f}mm")
            print(f"   Via Count (Logical): {route.via_count}")
            print(f"   Explicit Via Count: {len(route.explicit_vias)}")
            
            if len(route.explicit_vias) >= 16:
                print("   ✅ SUCCESS: Via array generated correctly (16 vias for 4x4)")
            else:
                print(f"   ❌ FAILURE: Expected 16 vias, got {len(route.explicit_vias)}")
            
            pass
        else:
            print(f"❌ PWR_20A: FAILED (Reason: {route.failure_reason})")
    else:
        print("❌ PWR_20A: MISSING from results")

if __name__ == "__main__":
    create_high_current_via_array_exp()
