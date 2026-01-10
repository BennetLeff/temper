#!/usr/bin/env python3
"""Diagnostic script to trace fixed component positions through the placement pipeline."""

from pathlib import Path

import jax.numpy as jnp
from temper_placer.io.kicad_parser import parse_kicad_pcb
from temper_placer.io.config_loader import (
    load_constraints,
    apply_fixed_components_to_netlist,
    apply_zones_to_netlist,
    create_board_from_constraints,
)
from temper_placer.heuristics.pipeline import create_priority_pipeline

# Load PCB and constraints
print("Loading PCB and constraints...")
result = parse_kicad_pcb(Path("../../pcb/temper.kicad_pcb"))
constraints = load_constraints(Path("configs/temper_constraints.yaml"))
board = create_board_from_constraints(constraints)

# Apply fixed components
apply_fixed_components_to_netlist(result.netlist, constraints)
apply_zones_to_netlist(result.netlist, constraints)

q1_idx = result.netlist.get_component_index("Q1")
u_gate_idx = result.netlist.get_component_index("U_GATE")

print("\n=== STEP 1: After apply_fixed_components_to_netlist ===")
for comp in result.netlist.components:
    if comp.ref in ["Q1", "Q2", "U_GATE", "D1", "C_BUS1"]:
        print(f"  {comp.ref}: fixed={comp.fixed}, initial_pos={comp.initial_position}")

# Create and run heuristic pipeline
print("\n=== STEP 2: Running heuristic pipeline ===")
pipeline = create_priority_pipeline()
heuristic_result = pipeline.run(board, result.netlist, constraints)

print("\n=== STEP 3: After heuristic pipeline (PlacementState) ===")
for ref in ["Q1", "Q2", "U_GATE", "D1", "C_BUS1"]:
    idx = result.netlist.get_component_index(ref)
    pos = heuristic_result.state.positions[idx]
    print(f"  {ref}: position in state = ({float(pos[0]):.1f}, {float(pos[1]):.1f})")

# Expected vs actual
print("\n=== COMPARISON: Expected vs Actual ===")
expected = {
    "Q1": (75.0, 125.0),
    "Q2": (75.0, 115.0),
    "U_GATE": (60.0, 120.0),
    "D1": (71.0, 125.0),
    "C_BUS1": (79.0, 125.0),
}

all_correct = True
for ref, exp_pos in expected.items():
    idx = result.netlist.get_component_index(ref)
    actual = heuristic_result.state.positions[idx]
    actual_tuple = (float(actual[0]), float(actual[1]))
    
    dx = abs(actual_tuple[0] - exp_pos[0])
    dy = abs(actual_tuple[1] - exp_pos[1])
    
    if dx < 1.0 and dy < 1.0:
        status = "✓ CORRECT"
    else:
        status = f"✗ WRONG (off by {dx:.1f}, {dy:.1f})"
        all_correct = False
    
    print(f"  {ref}: expected {exp_pos}, actual {actual_tuple} -> {status}")

if all_correct:
    print("\n✓ All fixed components at correct positions!")
else:
    print("\n✗ Some fixed components are NOT at their expected positions.")
    print("  The fix in _to_placement_state() may not be working correctly.")
