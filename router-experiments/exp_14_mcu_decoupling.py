#!/usr/bin/env python3
"""
EXP-14: MCU Subsystem with High-Density Decoupling

Demonstrates high-density escape routing for the ESP32-S3 MCU (QFN-56).
Uses FanoutGenerator to create dog-bone fanouts (via + trace) for decoupling caps.
Verifies that the router can handle dense pin fields using fanout overrides.
"""

import sys
import logging
from pathlib import Path
import jax.numpy as jnp
import numpy as np
import math

# Adjust path to import packages
sys.path.insert(0, str(Path(__file__).parent.parent / "packages" / "temper-placer" / "src"))

from temper_placer.core.board import Board as TemperBoard
from temper_placer.core.netlist import Netlist, Component, Pin, Net
from temper_placer.io.config_loader import load_constraints, constraints_to_design_rules
from temper_placer.routing.maze_router import MazeRouter
from temper_placer.routing.fanout import FanoutGenerator, FanoutConfig

# For FanoutGenerator compatibility
from kiutils.board import Board as KiBoard
from kiutils.items.common import Position

logging.basicConfig(level=logging.INFO, format="%(message)s")

def create_mcu_system():
    print("Loading constraints from YAML...")
    config_path = Path(__file__).parent.parent / "packages" / "temper-placer" / "configs" / "temper_constraints.yaml"
    constraints = load_constraints(config_path)
    dr = constraints_to_design_rules(constraints)

    # 1. Define Components
    # U_MCU: ESP32-S3 QFN-56 (7x7mm body, 0.4mm pitch)
    # Simplified pin map for decoupling
    mcu_pins = []
    # 4 sides, ~14 pins per side
    for i in range(1, 15): # Side 1 (West)
        mcu_pins.append(Pin(name=str(i), number=str(i), net="GND" if i % 4 == 0 else f"IO_{i}", position=(-3.5, -3.5 + 0.5 * i)))
    for i in range(15, 29): # Side 2 (South)
        mcu_pins.append(Pin(name=str(i), number=str(i), net="_PLUS3V3" if i % 4 == 1 else f"IO_{i}", position=(-3.5 + 0.5 * (i-14), 3.5)))
    for i in range(29, 43): # Side 3 (East)
        mcu_pins.append(Pin(name=str(i), number=str(i), net="GND" if i % 4 == 2 else f"IO_{i}", position=(3.5, 3.5 - 0.5 * (i-28))))
    for i in range(43, 57): # Side 4 (North)
        mcu_pins.append(Pin(name=str(i), number=str(i), net="_PLUS3V3" if i % 4 == 3 else f"IO_{i}", position=(3.5 - 0.5 * (i-42), -3.5)))

    # Decoupling Caps (0402: 1.0x0.5mm)
    def create_cap(ref, pos):
        return Component(
            ref=ref, 
            footprint="Cap_0402", 
            bounds=(1.0, 0.5), 
            initial_position=pos, 
            initial_side=0,
            pins=[
                Pin(name="1", number="1", net="_PLUS3V3", position=(-0.4, 0)),
                Pin(name="2", number="2", net="GND", position=(0.4, 0))
            ]
        )

    components = [
        Component(ref="U_MCU", footprint="QFN-56", bounds=(7.0, 7.0), initial_position=(50.0, 50.0), initial_side=0, pins=mcu_pins),
        create_cap("C_MCU_1", (45.0, 42.0)),
        create_cap("C_MCU_2", (55.0, 42.0)),
        create_cap("C_MCU_3", (45.0, 58.0)),
        create_cap("C_MCU_4", (55.0, 58.0)),
    ]

    # 2. Create Netlist
    net_map = {}
    for c in components:
        for p in c.pins:
            if p.net not in net_map:
                net_map[p.net] = []
            net_map[p.net].append((c.ref, p.number))
            
    nets = [Net(name=n, pins=p) for n, p in net_map.items()]
    netlist = Netlist(components=components, nets=nets)
    pos_arr = jnp.array([c.initial_position for c in components])

    # 3. Fanout Generation
    print("Generating Fanouts...")
    ki_board = KiBoard()
    # Add nets to ki_board for FanoutGenerator
    from kiutils.board import Net as KiNet
    for i, net_name in enumerate(net_map.keys()):
        ki_board.nets.append(KiNet(number=i, name=net_name))

    fanout_gen = FanoutGenerator(ki_board, netlist, config=FanoutConfig(pitch=0.5, via_size=0.4, via_drill=0.2))
    # We want fanout for decoupling nets to escape the QFN pins
    fanout_overrides = fanout_gen.generate_fanouts(target_nets=["_PLUS3V3", "GND"])
    
    # 4. Router Setup
    print("Initializing Router V6...")
    router = MazeRouter(
        grid_size=(500, 500), 
        cell_size_mm=0.1, # Fine grid for high-density
        num_layers=4,    # MCU subsystem usually needs 4 layers
        design_rules=dr,
        min_clearance=0.1
    )
    
    print("Blocking pads...")
    router.block_pads(components, pos_arr, netlist)
    
    print("Routing...")
    # Pass fanout_overrides to the router
    # Note: MazeRouter.rrr_route_all_nets takes pin_positions_overrides
    routes = router.rrr_route_all_nets(
        netlist, 
        pos_arr, 
        net_order=["_PLUS3V3", "GND"] + [n for n in net_map.keys() if n not in ["_PLUS3V3", "GND"]],
        assignments={},
        pin_positions_overrides=fanout_overrides
    )
    
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

    if all_clean:
         print("🎉 SUCCESS: High-Density Decoupling Routed with Fanouts!")
    else:
         print("⚠️  FAIL: Some nets could not be escaped.")

if __name__ == "__main__":
    create_mcu_system()
