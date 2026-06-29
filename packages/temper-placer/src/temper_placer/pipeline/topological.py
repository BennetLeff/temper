"""
Topological placement phase for temper-placer.

This phase uses rule-based heuristics and templates to establish an
initial overlap-free layout.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from temper_placer.heuristics.mcu_subsystem import MCUSubsystemHeuristic
from temper_placer.optimizer.legalization import legalize_zone_aware
from temper_placer.placer.deterministic import PlacementResult

if TYPE_CHECKING:
    from temper_placer.pipeline.state import PipelineState


def run_topological_phase(state: PipelineState) -> PipelineState:
    """Run topological placement phase."""
    print("Running topological placement...")

    # 1. MCU Subsystem Template
    mcu_heuristic = MCUSubsystemHeuristic()
    try:
        mcu_result = mcu_heuristic.apply(state.netlist, state.board, zone_name="control_zone")
    except ValueError:
        try:
            mcu_result = mcu_heuristic.apply(state.netlist, state.board, zone_name="MCU_ZONE")
        except ValueError:
            mcu_result = mcu_heuristic.apply(state.netlist, state.board)

    positions = np.array(mcu_result.positions)
    rotations = np.array(mcu_result.rotations)

    # 2. Other positions
    for i, comp in enumerate(state.netlist.components):
        if comp.ref in mcu_result.placed_refs:
            continue
        if comp.initial_position:
            positions[i] = comp.initial_position
        else:
            if comp.zone:
                zone = state.board.get_zone(comp.zone)
                positions[i] = zone.center if zone else (state.board.width / 2, state.board.height / 2)
            else:
                positions[i] = (state.board.width / 2, state.board.height / 2)
        if comp.initial_rotation is not None:
            rotations[i] = comp.initial_rotation * 90.0

    # 3. Zone-Aware Legalization
    print("Running zone-aware legalization...")
    fixed_mask = np.array([c.fixed for c in state.netlist.components], dtype=bool)
    legalized_pos, success = legalize_zone_aware(positions, state.netlist, state.board, fixed_mask=fixed_mask)

    if not success:
        print("Warning: Legalization could not fully resolve overlaps.")

    state.deterministic_result = PlacementResult(
        positions=legalized_pos, rotations=rotations,
        placed_refs=[c.ref for c in state.netlist.components], unplaced_refs=[],
    )
    return state
