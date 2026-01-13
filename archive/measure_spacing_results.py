#!/usr/bin/env python3
"""
Measure component spacing in the optimized PCB.
"""

import numpy as np
from pathlib import Path
from temper_placer.io.kicad_parser import parse_kicad_pcb
from temper_placer.losses.component_spacing import ComponentSpacingLoss
from temper_placer.losses.base import LossContext
from temper_placer.io.config_loader import load_constraints
import jax.numpy as jnp

def measure_spacing():
    # Load optimized PCB
    pcb_path = Path("packages/temper-placer/output_pipeline_test.kicad_pcb")
    if not pcb_path.exists():
        print(f"Error: {pcb_path} not found")
        return

    print(f"Loading {pcb_path}...")
    parse_result = parse_kicad_pcb(pcb_path)
    board = parse_result.board
    netlist = parse_result.netlist
    
    # Load constraints
    config_path = Path("packages/temper-placer/configs/temper_constraints.yaml")
    constraints = load_constraints(config_path)
    constraints.critical_loops = [] # Avoid validation errors
    
    # Create context
    context = LossContext.from_netlist_and_board(
        netlist, 
        board, 
        constraints=constraints
    )
    
    # Get positions
    positions = jnp.array([c.initial_position for c in netlist.components])
    rotations = jnp.zeros((len(netlist.components), 4)) # Assuming 0 rotation for now or need to extract
    
    # Calculate spacing loss to get breakdown
    spacing_loss = ComponentSpacingLoss(use_rotated_bounds=True)
    result = spacing_loss(positions, rotations, context)
    
    print("\nSpacing Analysis Results:")
    print("-" * 50)
    
    print(f"Total Spacing Loss: {float(result.value):.4f}")
    
    if result.breakdown:
        print("\nViolations (penalty > 0):")
        for pair, penalty in result.breakdown.items():
            if float(penalty) > 0.001:
                print(f"  ❌ {pair}: {float(penalty):.4f}")
            else:
                print(f"  ✅ {pair}: OK")
    
    # Manually check specific pairs of interest
    print("\nDetailed Measurements:")
    pairs_to_check = [
        ("C_BUS1", "Q1"),
        ("C_BUS2", "Q2"),
        ("D2", "C_BUS2"),
        ("D2", "C_BUS1"),
        ("Q1", "Q2")
    ]
    
    name_to_idx = context.component_name_to_index
    
    for name_a, name_b in pairs_to_check:
        if name_a in name_to_idx and name_b in name_to_idx:
            idx_a = name_to_idx[name_a]
            idx_b = name_to_idx[name_b]
            pos_a = positions[idx_a]
            pos_b = positions[idx_b]
            dist = float(jnp.linalg.norm(pos_a - pos_b))
            print(f"  {name_a} ↔ {name_b}: Center-to-Center = {dist:.2f}mm")

if __name__ == "__main__":
    measure_spacing()
