"""Direct test of deterministic pipeline on Temper board.

This script uses the production create_drc_aware_pipeline which includes
PowerPlaneStage for proper ground/power plane routing.
"""

from pathlib import Path
from temper_placer.deterministic import create_drc_aware_pipeline, BoardState
from temper_placer.io.kicad_parser import parse_kicad_pcb
from temper_placer.io.config_loader import load_constraints

# Load Temper board
print("Loading Temper PCB...")
pcb_path = Path("../../pcb/temper.kicad_pcb")
result = parse_kicad_pcb(pcb_path)
netlist = result.netlist
board_info = result.board

print(f"Loaded {len(netlist.nets)} nets, {len(netlist.components)} components")
for net in sorted([n.name for n in netlist.nets])[:10]:
    print(f"  - {net}")

# Load constraints
print("\nLoading constraints...")
config_path = Path("../../configs/temper_deterministic_config.yaml")
constraints = load_constraints(config_path)

print(f"Zones defined: {[z.name for z in constraints.zones]}")
print(f"Net classes: {set(constraints.net_classes.values())}")

# Create metadata dict for DRC oracle from ParseResult
from dataclasses import dataclass

@dataclass
class Metadata:
    courtyards: dict
    pad_sizes: dict
    board_width: float
    board_height: float

metadata = Metadata(
    courtyards=result.courtyards if hasattr(result, 'courtyards') else {},
    pad_sizes=result.pad_sizes if hasattr(result, 'pad_sizes') else {},
    board_width=board_info.width,
    board_height=board_info.height,
)

# Create initial state
initial_state = BoardState(board=board_info, netlist=netlist)

# Build production pipeline with PowerPlaneStage
print("\nBuilding production DRC-aware pipeline (includes PowerPlaneStage)...")
pipeline = create_drc_aware_pipeline(
    config=constraints,
    metadata=metadata,
    zone_aware=True,
    parsed_pads=result.pads,  # Use exact KiCad positions
)

# Run pipeline
print("\nRunning pipeline...")
try:
    final_state = pipeline.run(initial_state)
    print("\n✓ Pipeline completed successfully!")
    
    # Check results
    placements = dict(final_state.placements) if final_state.placements else {}
    routes = list(final_state.routes) if final_state.routes else []
    vias = list(final_state.vias) if final_state.vias else []

    routed_net_names = {route.net for route in routes if route.net}
    if vias:
        routed_net_names.update({via.net for via in vias if via.net})
    num_routed_nets = len(routed_net_names)
    
    print(f"\nResults:")
    print(f"  Components placed: {len(placements)}")
    print(f"  Nets routed: {num_routed_nets}")
    print(f"  Routing completion: {num_routed_nets}/{len(netlist.nets)} ({100*num_routed_nets/len(netlist.nets):.1f}%)")
    
    if len(routes) > 0:
        print(f"\n  Sample routed nets:")
        for route in routes[:5]:
            print(f"    - {route.net}")
    
except Exception as e:
    print(f"\n✗ Pipeline failed: {e}")
    import traceback
    traceback.print_exc()
