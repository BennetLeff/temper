#!/usr/bin/env python3
"""Check if escape vias are being created correctly."""

import sys

sys.path.insert(0, "packages/temper-placer/src")

from temper_placer.core.board import Board
from temper_placer.deterministic import create_drc_aware_pipeline
from temper_placer.io.kicad_metadata import KiCadMetadata

# Load board
board = Board.from_kicad("pcb/temper.kicad_pcb")
print(f"Loaded board: {len(board.netlist.components)} components, {len(board.netlist.nets)} nets")

# Load metadata
metadata = KiCadMetadata.from_board("pcb/temper.kicad_pcb")
print(f"Loaded metadata: {len(metadata.courtyards)} courtyards, {len(metadata.pad_sizes)} pads")

# Create pipeline up to fine_pitch_escape stage only
from temper_placer.deterministic.stages import (
    NetClassSetupStage,
    ZoneGeometryStage,
    ZoneAssignmentStage,
    ZoneAwareSlotGenerationStage,
    PhasedComponentAssignmentStage,
    ApplyPlacementsStage,
    CourtyardCheckStage,
    DRCOracleSetupStage,
    ClearanceGridStage,
    NetOrderingStage,
    LayerAssignmentStage,
    PowerPlaneStage,
    FinePitchEscapeStage,
)
from temper_placer.deterministic.pipeline import DeterministicPipeline
from temper_placer.deterministic.state import BoardState
import yaml

# Load config
with open("configs/temper_deterministic_config.yaml") as f:
    config_data = yaml.safe_load(f)

from temper_placer.deterministic.config import PipelineConfig

config = PipelineConfig.from_dict(config_data)

# Minimal pipeline to test escape stage
stages = [
    NetClassSetupStage(net_classes=config.net_classes),
    ZoneGeometryStage(zones=config.zones),
    ZoneAssignmentStage(constraints=config.placement_constraints),
    ZoneAwareSlotGenerationStage(),
    PhasedComponentAssignmentStage(constraints=config.placement_constraints),
    ApplyPlacementsStage(),
    CourtyardCheckStage(metadata=metadata),
    ApplyPlacementsStage(),
    PowerPlaneStage(),
    FinePitchEscapeStage(pin_pitch_threshold_mm=0.65, escape_layer=1),
]

pipeline = DeterministicPipeline(stages)

# Run pipeline
state = BoardState(netlist=board.netlist)
final_state = pipeline.run(state)

print(f"\n=== Escape Vias ===")
print(f"Total vias created: {len(final_state.vias)}")

# Group by net
vias_by_net = {}
for via in final_state.vias:
    if via.net not in vias_by_net:
        vias_by_net[via.net] = []
    vias_by_net[via.net].append(via)

print(f"\nVias by net:")
for net_name in sorted(vias_by_net.keys()):
    vias = vias_by_net[net_name]
    print(f"  {net_name}: {len(vias)} vias")
    for via in vias[:3]:  # Show first 3
        print(
            f"    - Position: {via.position}, Layers: {via.layers}, Drill: {via.drill}mm, Width: {via.width}mm"
        )

# Check PWM_H specifically
print(f"\n=== PWM_H Analysis ===")
pwm_h_net = next((n for n in board.netlist.nets if n.name == "PWM_H"), None)
if pwm_h_net:
    print(f"PWM_H pins: {pwm_h_net.pins}")
    if "PWM_H" in vias_by_net:
        print(f"PWM_H escape vias:")
        for via in vias_by_net["PWM_H"]:
            print(f"  - {via.position} on {via.layers}")
    else:
        print("No escape vias found for PWM_H!")
else:
    print("PWM_H net not found!")
