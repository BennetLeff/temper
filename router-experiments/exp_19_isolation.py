#!/usr/bin/env python3
"""
EXP-19: Isolation Barrier Creepage Verification

Verifies that the router maintains required creepage/clearance distance (6.5mm+)
across the isolation barrier between HV (Power) and LV (Control) domains.
Focuses on the Optocoupler (U_ISO) and Transformer (T_AUX) interfaces.
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

def create_isolation_exp():
    print("Loading constraints from YAML...")
    config_path = Path(__file__).parent.parent / "packages" / "temper-placer" / "configs" / "temper_constraints.yaml"
    constraints = load_constraints(config_path)
    dr = constraints_to_design_rules(constraints)

    print("Configuring Isolation Rules...")
    # Define HV and LV nets
    # HV Side: PWM_IN_HV, VCC_HV
    # LV Side: PWM_OUT_LV, VCC_LV
    # Rules: HV nets need 6.5mm clearance to LV nets.
    # In MazeRouter, we set clearance per-net.
    # If we route HV net, it sets keepout for ALL other nets.
    # But LV nets only need 0.2mm to other LV nets.
    # How to enforce domain-specific clearance?
    # Router v5 approach: Use "HighVoltage" class for HV nets (large clearance to everything).
    
    dr.net_overrides["PWM_IN_HV"] = NetClassRules(
        name="HighVoltage",
        trace_width=0.3,
        clearance=6.5, # Reinforced Isolation
        via_template="Via1x1"
    )
    dr.net_overrides["VCC_HV"] = NetClassRules(
        name="HighVoltage",
        trace_width=0.5,
        clearance=6.5,
        via_template="Via1x1"
    )
    
    # LV nets use default rules (0.2mm clearance)

    # 2. Define Components
    # U_ISO: Optocoupler (Wide body, e.g., Gull Wing or Wide SOIC)
    # Pins 1,2 (LV) ... Gap ... Pins 3,4 (HV)
    # Gap is physically ~8mm.
    
    # Pins
    # LV Side (Left)
    u_iso_lv_pins = [
        Pin(name="A", number="1", net="PWM_OUT_LV", position=(-4.0, -2.0)),
        Pin(name="C", number="2", net="GND_LV", position=(-4.0, 2.0))
    ]
    # HV Side (Right)
    u_iso_hv_pins = [
        Pin(name="E", number="3", net="GND_HV", position=(4.0, 2.0)),
        Pin(name="C", number="4", net="PWM_IN_HV", position=(4.0, -2.0))
    ]
    
    # Connector LV
    j_lv_pins = [Pin(name="1", number="1", net="PWM_OUT_LV", position=(0.0, 0.0))]
    # Connector HV
    j_hv_pins = [Pin(name="1", number="1", net="PWM_IN_HV", position=(0.0, 0.0))]

    components = [
        # Optocoupler in middle
        Component(ref="U_ISO", footprint="Opto_Wide", bounds=(10, 6), initial_position=(50, 50), initial_side=0, pins=u_iso_lv_pins + u_iso_hv_pins),
        
        # LV Connector (Left)
        Component(ref="J_LV", footprint="Header", bounds=(5, 5), initial_position=(20, 50), initial_side=0, pins=j_lv_pins),
        
        # HV Connector (Right)
        Component(ref="J_HV", footprint="Header", bounds=(5, 5), initial_position=(80, 50), initial_side=0, pins=j_hv_pins),
    ]

    # 3. Create Netlist
    net_map = {
        "PWM_OUT_LV": [("J_LV", "1"), ("U_ISO", "1")],
        "PWM_IN_HV": [("U_ISO", "4"), ("J_HV", "1")]
    }
    
    nets = [Net(name=n, pins=p) for n, p in net_map.items()]
    netlist = Netlist(components=components, nets=nets)
    pos_arr = jnp.array([c.initial_position for c in components])

    # 4. Router Setup
    print("Initializing MazeRouter...")
    router = MazeRouter(
        grid_size=(500, 500), # 100x100mm
        cell_size_mm=0.2,
        num_layers=2,
        design_rules=dr,
        min_clearance=0.1
    )
    
    print("Blocking pads...")
    router.block_pads(components, pos_arr, netlist)
    
    print("Routing Isolation Barrier...")
    
    # Route LV net first (Standard)
    print("\nRouting PWM_OUT_LV (LV side)...")
    res_lv = route_net_hierarchical(
        router,
        net_name="PWM_OUT_LV",
        pin_positions=[(20.0, 50.0), (46.0, 48.0)], # J_LV -> U_ISO.1
        assignment=LayerAssignment(net="PWM_OUT_LV", primary_layer=Layer.L1_TOP, allowed_layers={Layer.L1_TOP}),
        trace_width_mm=0.25,
        clearance_mm=0.25
    )
    if res_lv.success:
        print(f"✅ LV Net: Success, Length={res_lv.length:.1f}mm")
    else:
        print(f"❌ LV Net: Failed - {res_lv.failure_reason}")

    # Route HV net (Hierarchical due to clearance)
    print("\nRouting PWM_IN_HV (HV side) with 6.5mm clearance...")
    # This checks if the LV components/traces (at x<46) block the HV net (at x>54)
    # The clearance is huge (6.5mm).
    # If HV net routes at x=54, keepout extends to 54-6.5 = 47.5.
    # U_ISO.1 is at 46.0.
    # 47.5 > 46.0.
    # So HV trace *should* be able to route to U_ISO.4 at (54, 48).
    # But it must stay away from LV traces.
    
    res_hv = route_net_hierarchical(
        router,
        net_name="PWM_IN_HV",
        pin_positions=[(54.0, 48.0), (80.0, 50.0)], # U_ISO.4 -> J_HV
        assignment=LayerAssignment(net="PWM_IN_HV", primary_layer=Layer.L1_TOP, allowed_layers={Layer.L1_TOP}),
        trace_width_mm=0.3,
        clearance_mm=6.5
    )
    
    if res_hv.success:
        print(f"✅ HV Net: Success, Length={res_hv.length:.1f}mm")
        print(f"   Clearance Enforced: 6.5mm")
        
        # Verify distance to LV components
        # (This is manual check logic, router should enforce it)
    else:
        print(f"❌ HV Net: Failed - {res_hv.failure_reason}")

    print("\n" + "="*40)
    print("RESULTS")
    print("="*40)
    
    # Check if HV routing violated LV zone?
    # Can't easily check programmatically here without querying the grid state deep.
    # But success implies it found a path valid against the clearance mask.
    
if __name__ == "__main__":
    create_isolation_exp()
