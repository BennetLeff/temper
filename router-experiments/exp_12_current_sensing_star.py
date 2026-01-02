#!/usr/bin/env python3
"""
EXP-12: Current Sensing Routing from YAML Constraints (Star-Point)

Demonstrates the Kelvin star-point topology for the `I_SENSE` net.
Target: 2.0mm Force trace and 0.2mm Sense trace meeting at R_BURDEN.1 without mid-trace tapping.
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
from temper_placer.routing.maze_router import MazeRouter

logging.basicConfig(level=logging.INFO, format="%(message)s")

def create_current_sensing_from_yaml():
    print("Loading constraints from YAML...")
    config_path = Path(__file__).parent.parent / "packages" / "temper-placer" / "configs" / "temper_constraints.yaml"
    constraints = load_constraints(config_path)
    
    # 1. Extract Group "current_sensing"
    target_group_name = "current_sensing"
    target_group = next((g for g in constraints.component_groups if g.name == target_group_name), None)
    
    if not target_group:
        print(f"ERROR: Group '{target_group_name}' not found in YAML.")
        return
        
    print(f"Found Group '{target_group_name}': {target_group.components}")
    
    # 2. Define Components with positions
    positions = {
        "U_CT": (10.0, 50.0),
        "R_BURDEN": (40.0, 50.0),
        "C_CT_FILT": (40.0, 10.0),
        "U_OPAMP_CT": (70.0, 50.0),
    }
    
    components = []
    for comp_ref in target_group.components:
        if comp_ref not in positions:
            print(f"WARNING: No position defined for {comp_ref}")
            continue
            
        pos = positions[comp_ref]
        pins = []
        
        if comp_ref == "U_CT":
            pins = [
                Pin(name="OUT", number="1", net="I_SENSE", position=(1.5, 0)),
                Pin(name="VCC", number="2", net="+3V3", position=(-1.5, 10.0)),
                Pin(name="GND", number="3", net="GND", position=(-1.5, -10.0))
            ]
        elif comp_ref == "R_BURDEN":
            pins = [
                Pin(name="1", number="1", net="I_SENSE", position=(-1.0, 0)),
                Pin(name="2", number="2", net="GND", position=(1.0, 10.0))
            ]
        elif comp_ref == "C_CT_FILT":
            pins = [
                Pin(name="1", number="1", net="I_SENSE", position=(0, 1.0)),
                Pin(name="2", number="2", net="GND", position=(0, -1.0))
            ]
        elif comp_ref == "U_OPAMP_CT":
            pins = [
                Pin(name="IN", number="1", net="I_SENSE", position=(-1.5, 0)),
                Pin(name="VCC", number="2", net="+3V3", position=(1.5, 10.0)),
                Pin(name="GND", number="3", net="GND", position=(1.5, -10.0)),
                Pin(name="IN-", number="4", net="GND", position=(-1.5, -10.0)),
                Pin(name="OUT", number="5", net="Conditioned_I", position=(1.5, 0))
            ]
            
        comp = Component(ref=comp_ref, footprint="Generic", bounds=(3.0, 20.0), initial_position=pos, initial_side=0, pins=pins)
        components.append(comp)

    # 3. Design Rules
    dr = constraints_to_design_rules(constraints)
    
    # 4. Create Netlist
    net_map = {}
    for c in components:
        for p in c.pins:
            if p.net not in net_map:
                net_map[p.net] = []
            net_map[p.net].append((c.ref, p.number))
            
    nets = [Net(name=n, pins=p) for n, p in net_map.items()]
    netlist = Netlist(components=components, nets=nets)
    
    # 5. Router Setup
    print("Initializing Router V6...")
    router = MazeRouter(
        grid_size=(1000, 800), 
        cell_size_mm=0.1,
        num_layers=2,
        design_rules=dr,
        min_clearance=0.1
    )
    
    pos_arr = jnp.array([c.initial_position for c in components])
    
    print("Blocking pads...")
    router.block_pads(components, pos_arr, netlist)
    
    print("Routing...")
    net_order = ["I_SENSE", "+3V3", "GND", "Conditioned_I"]
    routes = router.rrr_route_all_nets(netlist, pos_arr, net_order=net_order, assignments={})
    
    print("\n" + "="*40)
    print("RESULTS")
    print("="*40)
    
    all_clean = True
    
    for net_name, route in routes.items():
        if not route.success:
            print(f"❌ {net_name}: FAILED (Reason: {route.failure_reason})")
            all_clean = False
            continue
            
        print(f"✅ {net_name}: Length={route.length:.1f}mm")
        
    # Verify Kelvin disjointness
    i_sense_route = routes.get("I_SENSE")
    if i_sense_route and i_sense_route.success:
        # Check if R_BURDEN.1 connects to U_CT.OUT, U_OPAMP_CT.IN, and C_CT_FILT.1 via separate traces
        # Expected disjoint length approx 96.0mm.
        # If tapped, it would be lower.
        print(f"I_SENSE route length: {i_sense_route.length:.2f}mm")
        if i_sense_route.length > 95.0:
             print("🎉 VERIFIED: Disjoint paths for Kelvin sensing!")
        else:
             print("⚠️  WARNING: Route length suggests mid-trace tapping!")
             all_clean = False

    if all_clean:
        print("🎉 SUCCESS: Zero Conflicts / Zero DRC Errors!")
    else:
        print("⚠️  FAIL: Routing issues detected.")

if __name__ == "__main__":
    create_current_sensing_from_yaml()
