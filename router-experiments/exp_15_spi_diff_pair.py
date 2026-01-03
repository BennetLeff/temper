#!/usr/bin/env python3
"""
EXP-15: SPI Differential Pair Routing

Verifies Dual-Front A* routing for the SPI_CLK differential pair.
Tests:
1. Coupling integrity (traces stay together).
2. Obstacle avoidance (traces move together around obstacles).
3. Skew minimization (serpentine insertion to equalize lengths).
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
from temper_placer.routing.maze_router import MazeRouter

logging.basicConfig(level=logging.INFO, format="%(message)s")

def create_spi_diff_pair():
    print("Loading constraints from YAML...")
    config_path = Path(__file__).parent.parent / "packages" / "temper-placer" / "configs" / "temper_constraints.yaml"
    constraints = load_constraints(config_path)
    dr = constraints_to_design_rules(constraints)

    # 1. Define Components
    # U1: Source (e.g. MCU)
    u1_pins = [
        Pin(name="CLK_P", number="1", net="SPI_CLK_P", position=(-0.5, 0.5)),
        Pin(name="CLK_N", number="2", net="SPI_CLK_N", position=(-0.5, -0.5)),
    ]
    # U2: Sink (e.g. Memory/Sensor)
    # Deliberately offset pins to create a length mismatch in a straight route
    u2_pins = [
        Pin(name="CLK_P", number="1", net="SPI_CLK_P", position=(0.5, 1.0)),
        Pin(name="CLK_N", number="2", net="SPI_CLK_N", position=(0.5, -0.5)),
    ]

    components = [
        Component(ref="U1", footprint="SOIC-8", bounds=(5.0, 5.0), initial_position=(20.0, 50.0), initial_side=0, pins=u1_pins),
        Component(ref="U2", footprint="SOIC-8", bounds=(5.0, 5.0), initial_position=(80.0, 50.0), initial_side=0, pins=u2_pins),
        # Obstacle in the path
        Component(ref="BLOCKER", footprint="MountingHole", bounds=(10.0, 10.0), initial_position=(50.0, 52.0), initial_side=0, pins=[]),
    ]

    # 2. Create Netlist
    net_map = {"SPI_CLK_P": [("U1", "1"), ("U2", "1")], "SPI_CLK_N": [("U1", "2"), ("U2", "2")]}
    nets = [Net(name=n, pins=p) for n, p in net_map.items()]
    netlist = Netlist(components=components, nets=nets)
    pos_arr = jnp.array([c.initial_position for c in components])

    # 3. Router Setup
    print("Initializing Unified Router...")
    from temper_placer.routing.unified_router import UnifiedRouter, RoutingConfig, RoutingStrategy
    
    router = UnifiedRouter(
        board=Board(width=100.0, height=100.0), # Matches 500*0.2
        config=RoutingConfig(maze_cell_size=0.2, strategy=RoutingStrategy.MAZE_ONLY),
        design_rules=dr
    )
    
    # Block pads in the underlying maze router
    router.maze_router.block_pads(components, pos_arr, netlist)
    
    print("Routing Differential Pair (Manual Call)...")
    # Explicitly call the diff pair router via UnifiedRouter
    result = router.route_differential_pair(
        net_pos="SPI_CLK_P",
        net_neg="SPI_CLK_N",
        netlist=netlist,
        positions=pos_arr,
        target_separation_mm=0.2,
        max_skew_mm=1.0, # Relaxed for test
        enable_length_matching=True
    )
    
    print("\n" + "="*40)
    print("RESULTS")
    print("="*40)
    
    if result.success:
        len_p = len(result.pos_cells) * 0.2
        len_n = len(result.neg_cells) * 0.2
        skew = abs(len_p - len_n)
        print(f"✅ SPI_CLK_P: Length={len_p:.1f}mm")
        print(f"✅ SPI_CLK_N: Length={len_n:.1f}mm")
        print(f"Coupling Ratio: {result.coupling_ratio:.1f}%")
        print(f"Skew: {skew:.2f}mm")
        
        if skew <= 0.5:
             print("🎉 SUCCESS: Differential Pair routed with skew matching!")
        else:
             print("⚠️  WARNING: Skew exceeds tolerance (0.5mm).")
    else:
        print(f"❌ FAILED: {result.failure_reason}")

if __name__ == "__main__":
    create_spi_diff_pair()
