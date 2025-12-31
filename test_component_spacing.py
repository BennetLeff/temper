#!/usr/bin/env python3
"""
Test script to verify ComponentSpacingLoss enforcement.

This script creates a simple test case with components that violate
spacing constraints and verifies that the loss function correctly
penalizes these violations.
"""

import jax.numpy as jnp
from pathlib import Path

# Import required modules
from temper_placer.io.kicad_parser import parse_kicad_pcb
from temper_placer.io.config_loader import load_constraints
from temper_placer.losses import ComponentSpacingLoss
from temper_placer.losses.base import LossContext

def main():
    print("=" * 70)
    print("ComponentSpacingLoss Verification Test")
    print("=" * 70)
    
    # Load PCB and constraints
    pcb_path = Path("packages/temper-placer/output_temper_final.kicad_pcb")
    config_path = Path("packages/temper-placer/configs/temper_constraints.yaml")
    
    print(f"\n1. Loading PCB: {pcb_path}")
    parse_result = parse_kicad_pcb(pcb_path)
    board = parse_result.board
    netlist = parse_result.netlist
    
    print(f"   ✓ Loaded {len(netlist.components)} components")
    
    print(f"\n2. Loading constraints: {config_path}")
    constraints = load_constraints(config_path)
    # Clear loop constraints to avoid U_GD validation errors
    constraints.critical_loops = []
    print(f"   ✓ Found {len(constraints.component_spacing_rules)} spacing rules")
    
    for rule in constraints.component_spacing_rules:
        print(f"      - {rule.component_a} ↔ {rule.component_b}: {rule.min_separation_mm}mm")
    
    # Create LossContext with constraints
    print(f"\n3. Creating LossContext with constraints...")
    context = LossContext.from_netlist_and_board(
        netlist, 
        board, 
        constraints=constraints,
    )
    print(f"   ✓ Context created")
    print(f"   ✓ component_name_to_index has {len(context.component_name_to_index)} entries")
    print(f"   ✓ component_spacing_rules has {len(context.component_spacing_rules)} rules")
    
    # Get current positions
    positions = jnp.array([c.initial_position for c in netlist.components])
    rotations = jnp.zeros((len(netlist.components), 4))
    
    # Create ComponentSpacingLoss
    print(f"\n4. Testing ComponentSpacingLoss...")
    spacing_loss = ComponentSpacingLoss(use_rotated_bounds=True)
    
    # Compute loss
    result = spacing_loss(positions, rotations, context)
    
    print(f"\n5. Results:")
    print(f"   Total Loss: {float(result.value):.4f}")
    
    if result.breakdown:
        print(f"\n   Breakdown by component pair:")
        for pair, penalty in result.breakdown.items():
            penalty_val = float(penalty)
            if penalty_val > 0.001:  # Only show non-zero penalties
                print(f"      {pair}: {penalty_val:.4f}")
    
    # Test with components moved closer together (should increase loss)
    print(f"\n6. Testing with components moved closer...")
    
    # Find D2 and C_BUS2 indices
    d2_idx = context.component_name_to_index.get("D2")
    c_bus2_idx = context.component_name_to_index.get("C_BUS2")
    
    if d2_idx is not None and c_bus2_idx is not None:
        # Move D2 closer to C_BUS2
        test_positions = positions.at[d2_idx].set(positions[c_bus2_idx] + jnp.array([2.0, 0.0]))
        
        result_close = spacing_loss(test_positions, rotations, context)
        
        print(f"   Original loss: {float(result.value):.4f}")
        print(f"   Loss with D2 moved closer to C_BUS2: {float(result_close.value):.4f}")
        print(f"   Increase: {float(result_close.value - result.value):.4f}")
        
        if result_close.value > result.value:
            print(f"   ✅ Loss correctly increases when components are too close!")
        else:
            print(f"   ⚠️  Loss did not increase as expected")
    else:
        print(f"   ⚠️  Could not find D2 or C_BUS2 in netlist")
    
    print(f"\n" + "=" * 70)
    print("Test Complete!")
    print("=" * 70)

if __name__ == "__main__":
    main()
