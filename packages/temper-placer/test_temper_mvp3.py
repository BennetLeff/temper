"""Direct test of MVP-3 deterministic pipeline on Temper board.

This script bypasses the CLI and directly calls the MVP-3 pipeline stages
to test zone-based placement and routing on the full 25-net Temper board.
"""

from pathlib import Path
from temper_placer.deterministic import DeterministicPipeline, BoardState
from temper_placer.deterministic.stages import (
    ZoneGeometryStage,
    ZoneAssignmentStage,
    SlotGenerationStage,
    ComponentAssignmentStage,
    ApplyPlacementsStage,
    ClearanceGridStage,
    NetOrderingStage,
    SequentialRoutingStage,
    LayerAssignmentStage,
)
from temper_placer.core.board import Board
from temper_placer.io.kicad_parser import parse_kicad_pcb
from temper_placer.io.config_loader import load_constraints
from temper_placer.core.design_rules import DesignRules, NetClassRules

# Load Temper board
print("Loading Temper PCB...")
pcb_path = Path("../../pcb/temper.kicad_pcb")
netlist, board_info = parse_kicad_pcb(pcb_path)

print(f"Loaded {len(netlist.nets)} nets, {len(netlist.components)} components")
for net in sorted([n.name for n in netlist.nets])[:10]:
    print(f"  - {net}")

# Load constraints
print("\nLoading constraints...")
config_path = Path("../../configs/temper_deterministic_config.yaml")
constraints = load_constraints(config_path)

print(f"Zones defined: {[z.name for z in constraints.zones]}")
print(f"Net classes: {set(constraints.net_classes.values())}")

# Create Board object
board = Board(
    width=constraints.board_width_mm,
    height=constraints.board_height_mm,
    zones=constraints.zones
)

# Create design rules
design_rules = DesignRules()
design_rules.net_classes = {}
for name, rule in constraints.net_class_rules.items():
    design_rules.net_classes[name] = NetClassRules(
        name=name,
        trace_width=rule.trace_width_mm,
        clearance=rule.clearance_mm,
        via_diameter=rule.via_size_mm,
        via_drill=rule.via_drill_mm
    )

print(f"\nDesign rules loaded: {list(design_rules.net_classes.keys())}")

# Create initial state
initial_state = BoardState(board=board, netlist=netlist)

# Build pipeline
print("\nBuilding MVP-3 pipeline (4-layer routing)...")
pipeline = DeterministicPipeline(stages=[
    # Phase 1-4: MVP-3 Placement
    ZoneGeometryStage(),
    ZoneAssignmentStage(),
    SlotGenerationStage(slot_spacing_mm=5.0),
    ComponentAssignmentStage(),
    ApplyPlacementsStage(),
    # Phase 5: MVP-2 Routing (4-layer)
    ClearanceGridStage(cell_size_mm=0.5, layer_count=4),
    LayerAssignmentStage(),
    NetOrderingStage(),
    SequentialRoutingStage(design_rules=design_rules),
])

# Run pipeline
print("\nRunning pipeline...")
try:
    final_state = pipeline.run(initial_state)
    print("\n✓ Pipeline completed successfully!")
    
    # Check results
    placements = dict(final_state.placements) if final_state.placements else {}
    routes = list(final_state.routes) if final_state.routes else []
    
    print(f"\nResults:")
    print(f"  Components placed: {len(placements)}")
    print(f"  Nets routed: {len(routes)}")
    print(f"  Routing completion: {len(routes)}/{len(netlist.nets)} ({100*len(routes)/len(netlist.nets):.1f}%)")
    
    if len(routes) > 0:
        print(f"\n  Sample routed nets:")
        for route in routes[:5]:
            print(f"    - {route.net}")
    
except Exception as e:
    print(f"\n✗ Pipeline failed: {e}")
    import traceback
    traceback.print_exc()
