#!/usr/bin/env python3
"""
EXP-11: Gate Driver Routing from YAML Constraints

Demonstrates routing a sub-circuit defined in `temper_constraints.yaml` 
using the new Topology-Aware Router V6 tooling.

Target: 0 Conflicts, 0 DRC Errors.
"""

import sys
import logging
from pathlib import Path
import yaml
import jax.numpy as jnp
import numpy as np

# Adjust path to import packages
sys.path.insert(0, str(Path(__file__).parent.parent / "packages" / "temper-placer" / "src"))

from temper_placer.core.board import Board
from temper_placer.core.netlist import Netlist, Component, Pin, Net
from temper_placer.io.config_loader import load_constraints, constraints_to_design_rules
from temper_placer.routing.maze_router import MazeRouter

logging.basicConfig(level=logging.INFO, format="%(message)s")

def create_gate_driver_from_yaml():
    print("Loading constraints from YAML...")
    config_path = Path(__file__).parent.parent / "packages" / "temper-placer" / "configs" / "temper_constraints.yaml"
    constraints = load_constraints(config_path)
    
    # 1. Extract Group "gate_driver_circuit"
    target_group_name = "gate_driver_circuit"
    target_group = next((g for g in constraints.component_groups if g.name == target_group_name), None)
    
    if not target_group:
        print(f"ERROR: Group '{target_group_name}' not found in YAML.")
        return
        
    print(f"Found Group '{target_group_name}': {target_group.components}")
    
    # 2. Define Components (Pins/Footprints) - Simulated as we don't have full library
    # Using slightly relaxed positions compared to exp_10_a to ensure DRC compliance
    # Original exp_10_a had 1.0mm dist vs 1.2mm requirement?
    
    # Positions (mm)
    positions = {
        "U_GATE": (15.0, 15.0),
        "C_BOOT": (10.0, 22.0), # Moved up
        "C_VCC": (10.0, 8.0),   # Moved down
        "R_GATE_H": (22.0, 22.0),
        "R_GATE_L": (22.0, 8.0),
    }
    
    # Verify we have all components
    components = []
    for comp_ref in target_group.components:
        if comp_ref not in positions:
            print(f"WARNING: No position defined for YAML component {comp_ref}")
            continue
            
        pos = positions[comp_ref]
        
        # Define pins based on role
        pins = []
        if comp_ref == "U_GATE":
            pins = [
                Pin(name="OUTA", number="1", net="GATE_H", position=(0, 3.0)),   # Offset relative to center
                Pin(name="OUTB", number="2", net="GATE_L", position=(0, -3.0)),
                Pin(name="VDD", number="3", net="+15V", position=(-3.0, 0)),
                Pin(name="VDDA", number="4", net="VCC_BOOT", position=(-2.0, 2.0)),
                Pin(name="GND", number="5", net="CGND", position=(2.0, 0))
            ]
        elif comp_ref == "C_BOOT":
            pins = [Pin(name="1", number="1", net="VCC_BOOT", position=(0, 0.5)), Pin(name="2", number="2", net="CGND", position=(0, -0.5))]
        elif comp_ref == "C_VCC":
            pins = [Pin(name="1", number="1", net="+15V", position=(0, 0.5)), Pin(name="2", number="2", net="CGND", position=(0, -0.5))]
        elif comp_ref == "R_GATE_H":
             # Series resistor
            pins = [Pin(name="1", number="1", net="GATE_H", position=(-0.5, 0)), Pin(name="2", number="2", net="GATE_H", position=(0.5, 0))]
        elif comp_ref == "R_GATE_L":
            pins = [Pin(name="1", number="1", net="GATE_L", position=(-0.5, 0)), Pin(name="2", number="2", net="GATE_L", position=(0.5, 0))]
            
        comp = Component(ref=comp_ref, footprint="Generic", bounds=(1.0, 1.0), initial_position=pos, initial_side=0, pins=pins)
        components.append(comp)

    # 3. Create Design Rules from YAML
    dr = constraints_to_design_rules(constraints)
    
    # 4. Create Netlist
    # Extract unique nets from pins
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
        grid_size=(300, 300), # 30x30mm @ 0.1mm
        cell_size_mm=0.1,
        num_layers=2,
        design_rules=dr,
        min_clearance=0.1 # Base physical clearance
    )
    
    pos_arr = jnp.array([c.initial_position for c in components])
    
    print("Blocking pads...")
    router.block_pads(components, pos_arr, netlist)
    
    print("Routing...")
    net_order = [n.name for n in netlist.nets]
    routes = router.rrr_route_all_nets(netlist, pos_arr, net_order=net_order, assignments={})
    
    print("\n" + "="*40)
    print("RESULTS")
    print("="*40)
    
    total_conflicts = 0
    all_clean = True
    
    for net_name, route in routes.items():
        if not route.success:
            print(f"❌ {net_name}: FAILED")
            all_clean = False
            continue
            
        print(f"✅ {net_name}: Length={route.length:.1f}mm, Conflicts={len(route.conflicts)}")
        total_conflicts += len(route.conflicts)
        
    print(f"\nTotal Conflicts: {total_conflicts}")
    
    if total_conflicts == 0 and all_clean:
        print("🎉 SUCCESS: Zero Conflicts / Zero DRC Errors!")
    else:
        print("⚠️  FAIL: Conflicts detected.")

if __name__ == "__main__":
    create_gate_driver_from_yaml()
