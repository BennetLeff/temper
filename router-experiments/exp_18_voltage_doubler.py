#!/usr/bin/env python3
"""
EXP-18: Voltage Doubler Stage Routing

Verifies routing of the high-voltage rectification stage (D1, D2) to DC Bus Capacitors (C_BUS1, C_BUS2).
Requires handling of High Voltage clearance (3mm+) and High Current (15A+).
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

def create_voltage_doubler_exp():
    print("Loading constraints from YAML...")
    config_path = Path(__file__).parent.parent / "packages" / "temper-placer" / "configs" / "temper_constraints.yaml"
    constraints = load_constraints(config_path)
    dr = constraints_to_design_rules(constraints)

    # 1. Define Net Rules
    # Input AC is 15A. Rectified DC is high voltage.
    # We'll use 'HighCurrent' for the power path.
    print("Configuring design rules...")
    
    # Override nets
    power_nets = ["AC_L", "AC_N", "+340V_BUS", "DC_BUS_RTN"]
    for net in power_nets:
        dr.net_overrides[net] = NetClassRules(
            name="HighCurrent",
            trace_width=2.5, # 15A capability
            clearance=3.0,   # HV Clearance
            via_template="Via3x3" # Multiple vias for current
        )

    # 2. Define Components
    # D1, D2: Rectifier Diodes (TO-247)
    # C_BUS1, C_BUS2: Bulk Caps (Snap-in 30mm)
    # J_AC: Input connector
    
    # Pins for TO-247 (1=K, 2=A usually, or 1=A, 2=K)
    # Let's assume 1=Anode, 2=Cathode for D1/D2
    
    # AC Input
    j_ac_pins = [
        Pin(name="L", number="1", net="AC_L", position=(0.0, -5.0)),
        Pin(name="N", number="2", net="AC_N", position=(0.0, 5.0))
    ]
    
    # D1 (Top Diode): Anode->AC_L, Cathode->+340V
    d1_pins = [
        Pin(name="A", number="1", net="AC_L", position=(-5.0, 0.0)),
        Pin(name="K", number="2", net="+340V_BUS", position=(5.0, 0.0))
    ]
    
    # D2 (Bottom Diode): Cathode->AC_L, Anode->DC_BUS_RTN
    d2_pins = [
        Pin(name="K", number="1", net="AC_L", position=(-5.0, 0.0)),
        Pin(name="A", number="2", net="DC_BUS_RTN", position=(5.0, 0.0))
    ]
    
    # C_BUS1 (Top Cap): + -> +340V, - -> AC_N (Midpoint)
    c1_pins = [
        Pin(name="+", number="1", net="+340V_BUS", position=(0.0, 5.0)),
        Pin(name="-", number="2", net="AC_N", position=(0.0, -5.0))
    ]
    
    # C_BUS2 (Bottom Cap): + -> AC_N (Midpoint), - -> RTN
    c2_pins = [
        Pin(name="+", number="1", net="AC_N", position=(0.0, 5.0)),
        Pin(name="-", number="2", net="DC_BUS_RTN", position=(0.0, -5.0))
    ]

    components = [
        # Place AC connector on left edge
        Component(ref="J_AC", footprint="Connector", bounds=(20, 15), initial_position=(15, 130), initial_side=0, pins=j_ac_pins),
        
        # Place Diodes near AC
        Component(ref="D1", footprint="TO-247", bounds=(15, 20), initial_position=(40, 140), initial_side=0, pins=d1_pins),
        Component(ref="D2", footprint="TO-247", bounds=(15, 20), initial_position=(40, 120), initial_side=0, pins=d2_pins),
        
        # Place Caps
        Component(ref="C_BUS1", footprint="Cap_30mm", bounds=(30, 30), initial_position=(75, 140), initial_side=0, pins=c1_pins),
        Component(ref="C_BUS2", footprint="Cap_30mm", bounds=(30, 30), initial_position=(75, 100), initial_side=0, pins=c2_pins),
    ]

    # 3. Create Netlist
    net_map = {
        "AC_L": [("J_AC", "1"), ("D1", "1"), ("D2", "1")],
        "AC_N": [("J_AC", "2"), ("C_BUS1", "2"), ("C_BUS2", "1")],
        "+340V_BUS": [("D1", "2"), ("C_BUS1", "1")],
        "DC_BUS_RTN": [("D2", "2"), ("C_BUS2", "2")]
    }
    
    nets = [Net(name=n, pins=p) for n, p in net_map.items()]
    netlist = Netlist(components=components, nets=nets)
    pos_arr = jnp.array([c.initial_position for c in components])

    # 4. Router Setup
    print("Initializing MazeRouter...")
    router = MazeRouter(
        grid_size=(500, 750), # 100x150mm
        cell_size_mm=0.2,
        num_layers=2,
        design_rules=dr,
        min_clearance=0.1
    )
    
    print("Blocking pads...")
    router.block_pads(components, pos_arr, netlist)
    
    print("Routing Voltage Doubler Stage...")
    
    # Route all power nets
    success_count = 0
    for net_name in power_nets:
        if net_name not in net_map:
            continue
            
        print(f"\nRouting {net_name}...")
        
        # Get pins
        net = next(n for n in nets if n.name == net_name)
        pin_positions = []
        pin_sides = []
        
        comp_map = {c.ref: c for c in components}
        
        for ref, pin_num in net.pins:
            c = comp_map[ref]
            for p in c.pins:
                if p.number == pin_num:
                    px, py = p.absolute_position(c.initial_position, 0, 0)
                    pin_positions.append((px, py))
                    pin_sides.append(0) # All THT/Top
                    break
        
        assignment = LayerAssignment(
            net=net_name,
            primary_layer=Layer.L1_TOP,
            allowed_layers={Layer.L1_TOP, Layer.L4_BOT},
            vias_required=True
        )

        route = route_net_hierarchical(
            router,
            net_name=net_name,
            pin_positions=pin_positions,
            assignment=assignment,
            pin_sides=pin_sides,
            trace_width_mm=2.5,
            clearance_mm=3.0, # HV Clearance
        )
        
        if route.success:
            print(f"✅ {net_name}: Success, Length={route.length:.1f}mm")
            print(f"   Vias: {route.via_count} ({len(route.explicit_vias)} explicit)")
            print(f"   Clearance Enforced: {3.0}mm")
            success_count += 1
        else:
            print(f"❌ {net_name}: Failed - {route.failure_reason}")

    print("\n" + "="*40)
    print("RESULTS")
    print("="*40)
    print(f"Routed {success_count}/{len(net_map)} nets")
    
if __name__ == "__main__":
    create_voltage_doubler_exp()
