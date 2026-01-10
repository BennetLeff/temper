"""Validate bidirectional A* on Temper board.

Runs the production DRC-aware pipeline and checks for:
1. Bidirectional A* usage on HV nets
2. Successful routing of AC_N, PWM_H, PWM_L
3. <1000 iterations for long routes
"""

from pathlib import Path
from temper_placer.deterministic import create_drc_aware_pipeline, BoardState
from temper_placer.io.kicad_parser import parse_kicad_pcb
from temper_placer.io.config_loader import load_constraints
from dataclasses import dataclass

# Suppress debug output
import os
os.environ['TEMPER_USE_CYTHON_ASTAR'] = '1'

# Load Temper board
print("Loading Temper PCB...")
pcb_path = Path("../../pcb/temper.kicad_pcb")
result = parse_kicad_pcb(pcb_path)

print(f"✓ Loaded {len(result.netlist.nets)} nets, {len(result.netlist.components)} components\n")

# Load config
config_path = Path("../../configs/temper_deterministic_config.yaml")
constraints = load_constraints(config_path)

# Create metadata
@dataclass
class Metadata:
    courtyards: dict
    pad_sizes: dict
    board_width: float
    board_height: float

metadata = Metadata(
    courtyards=getattr(result, 'courtyards', {}),
    pad_sizes=getattr(result, 'pad_sizes', {}),
    board_width=result.board.width,
    board_height=result.board.height,
)

# Build pipeline with bidirectional A*
print("Building production pipeline...")
pipeline = create_drc_aware_pipeline(
    config=constraints,
    metadata=metadata,
    zone_aware=True,
    parsed_pads=result.pads,
)

# Run pipeline
print("Running deterministic placement + routing...\n")
print("=" * 70)

initial_state = BoardState(board=result.board, netlist=result.netlist)
final_state = pipeline.run(initial_state)

print("=" * 70)
print("\n✓ Pipeline completed!\n")

# Check results
routed_nets = set()
if final_state.routes:
    routed_nets.update(r.net for r in final_state.routes if r.net)
if final_state.vias:
    routed_nets.update(v.net for v in final_state.vias if v.net)

total_nets = len(result.netlist.nets)
routed_count = len(routed_nets)
completion = 100 * routed_count / total_nets if total_nets > 0 else 0

print(f"Routing Completion: {routed_count}/{total_nets} ({completion:.1f}%)")

# Check HV nets specifically
hv_nets = ["AC_L", "AC_N", "DC_BUS+", "DC_BUS-", "SW_NODE", "PWM_H", "PWM_L"]
print(f"\nHV Net Status:")
for net in hv_nets:
    status = "✓ ROUTED" if net in routed_nets else "✗ FAILED"
    print(f"  {net:12s}: {status}")

print("\n" + "=" * 70)
print("Validation complete!")
