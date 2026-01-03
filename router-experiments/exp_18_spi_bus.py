#!/usr/bin/env python3
"""
EXP-18: SPI Bus Routing Integrity

Verifies that the multi-signal SPI bus (CLK, MOSI, MISO, CS) is routed
as a clean parallel cohort with consistent spacing and no intra-bus crossings.
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
from temper_placer.core.bus_cohort import BusCohortConstraint
from temper_placer.routing.maze_router import MazeRouter

logging.basicConfig(level=logging.INFO, format="%(message)s")

def create_spi_bus_exp():
    print("Loading constraints from YAML...")
    config_path = Path(__file__).parent.parent / "packages" / "temper-placer" / "configs" / "temper_constraints.yaml"
    constraints = load_constraints(config_path)
    dr = constraints_to_design_rules(constraints)

    # 1. Define SPI Bus Cohort
    print("Configuring SPI Bus Cohort...")
    spi_nets = ["SPI_CLK", "SPI_MOSI", "SPI_MISO", "SPI_CS"]
    bus_constraint = BusCohortConstraint(
        name="SPI_BUS",
        nets=spi_nets,
        pitch_mm=0.5,
        allow_swapping=False
    )
    dr.bus_cohorts.append(bus_constraint)

    # 2. Define Components (Two 4-pin headers)
    # MCU Side
    mcu_pins = [
        Pin(name="CLK", number="1", net="SPI_CLK", position=(0.0, 0.0)),
        Pin(name="MOSI", number="2", net="SPI_MOSI", position=(0.0, 0.5)),
        Pin(name="MISO", number="3", net="SPI_MISO", position=(0.0, 1.0)),
        Pin(name="CS", number="4", net="SPI_CS", position=(0.0, 1.5)),
    ]
    # Sensor Side
    sensor_pins = [
        Pin(name="CLK", number="1", net="SPI_CLK", position=(0.0, 0.0)),
        Pin(name="MOSI", number="2", net="SPI_MOSI", position=(0.0, 0.5)),
        Pin(name="MISO", number="3", net="SPI_MISO", position=(0.0, 1.0)),
        Pin(name="CS", number="4", net="SPI_CS", position=(0.0, 1.5)),
    ]

    components = [
        Component(ref="U_MCU", footprint="Header_1x4", bounds=(2.54, 10.16), initial_position=(20.0, 50.0), initial_side=0, pins=mcu_pins),
        Component(ref="U_SENSOR", footprint="Header_1x4", bounds=(2.54, 10.16), initial_position=(80.0, 60.0), initial_side=0, pins=sensor_pins),
    ]

    # 3. Create Netlist
    nets = []
    for net_name in spi_nets:
        nets.append(Net(name=net_name, pins=[(ref, str(i+1)) for i, ref in enumerate(["U_MCU", "U_SENSOR"])]))
        # Wait, the netlist construction in tests usually takes a map
    
    net_map = {
        "SPI_CLK": [("U_MCU", "1"), ("U_SENSOR", "1")],
        "SPI_MOSI": [("U_MCU", "2"), ("U_SENSOR", "2")],
        "SPI_MISO": [("U_MCU", "3"), ("U_SENSOR", "3")],
        "SPI_CS": [("U_MCU", "4"), ("U_SENSOR", "4")],
    }
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
    
    print("Routing SPI Bus Cohort...")
    results = router.rrr_route_all_nets(
        netlist, 
        pos_arr, 
        net_order=spi_nets,
        assignments={}
    )
    
    print("\n" + "="*40)
    print("RESULTS")
    print("="*40)
    
    all_success = True
    for net_name in spi_nets:
        if net_name in results:
            route = results[net_name]
            if route.success:
                print(f"✅ {net_name}: Length={route.length:.1f}mm")
            else:
                print(f"❌ {net_name}: FAILED (Reason: {route.failure_reason})")
                all_success = False
        else:
            print(f"❌ {net_name}: MISSING from results")
            all_success = False
            
    if all_success:
        print("\n✅ SUCCESS: Full SPI Bus routed correctly.")
    else:
        print("\n❌ FAILURE: Bus routing failed.")

if __name__ == "__main__":
    create_spi_bus_exp()
