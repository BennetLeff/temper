"""Debug script to check for NaN values in priority pipeline output."""

from pathlib import Path
import jax
import numpy as np

from temper_placer.io.kicad_parser import parse_kicad_pcb
from temper_placer.io.config_loader import load_constraints
from temper_placer.heuristics.pipeline import create_priority_pipeline

# Load PCB and constraints
pcb_path = Path("../../pcb/temper.kicad_pcb")
config_path = Path("configs/temper_constraints.yaml")

print("Loading PCB and constraints...")
result = parse_kicad_pcb(pcb_path)
board = result.board
netlist = result.netlist
constraints = load_constraints(config_path)

print(f"Board: {board.width}mm x {board.height}mm")
print(f"Components: {len(netlist.components)}")

# Create and run priority pipeline
print("\nRunning priority pipeline...")
pipeline = create_priority_pipeline()
heuristic_key = jax.random.PRNGKey(42)

pipeline_result = pipeline.run(
    board=board,
    netlist=netlist,
    constraints=constraints,
    key=heuristic_key,
)

print(f"Unique placements: {len(pipeline_result.placements)}")
print(f"Unplaced: {len(pipeline_result.unplaced)}")

# Check initial state for NaN
state = pipeline_result.state
positions = np.array(state.positions)
rotation_logits = np.array(state.rotation_logits)

print(f"\nState check:")
print(f"  Positions shape: {positions.shape}")
print(f"  Rotation logits shape: {rotation_logits.shape}")

# Check for NaN
pos_has_nan = np.isnan(positions).any()
rot_has_nan = np.isnan(rotation_logits).any()
pos_has_inf = np.isinf(positions).any()
rot_has_inf = np.isinf(rotation_logits).any()

print(f"\n  Positions has NaN: {pos_has_nan}")
print(f"  Positions has Inf: {pos_has_inf}")
print(f"  Rotation logits has NaN: {rot_has_nan}")
print(f"  Rotation logits has Inf: {rot_has_inf}")

if pos_has_nan or rot_has_nan or pos_has_inf or rot_has_inf:
    print("\n❌ FOUND NaN/Inf IN INITIAL STATE!")
    
    # Find which components have NaN
    for i, comp in enumerate(netlist.components):
        pos = positions[i]
        rot = rotation_logits[i]
        if np.isnan(pos).any() or np.isinf(pos).any():
            print(f"  {comp.ref}: position = {pos}")
        if np.isnan(rot).any() or np.isinf(rot).any():
            print(f"  {comp.ref}: rotation logits = {rot}")
else:
    print("\n✓ No NaN/Inf in initial state")
    
# Check position ranges
print(f"\nPosition ranges:")
print(f"  X: [{positions[:, 0].min():.2f}, {positions[:, 0].max():.2f}]")
print(f"  Y: [{positions[:, 1].min():.2f}, {positions[:, 1].max():.2f}]")

# Show which components were placed by which heuristic
print(f"\nPlacement breakdown:")
for name, stats in pipeline_result.heuristic_stats.items():
    print(f"  {name}: {stats.get('placed', 0)} placed")

# Count unique placements
print(f"\nUnique component placements: {len(pipeline_result.placements)}/{len(netlist.components)}")
if pipeline_result.unplaced:
    print(f"Unplaced components: {pipeline_result.unplaced}")
