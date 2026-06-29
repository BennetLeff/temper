"""Topological stage: rule-based placement with MCU subsystem heuristics."""

from __future__ import annotations

import time
from typing import Any

import numpy as np

from temper_placer.pipeline.dag_types import DataContext, StageResult


class TopologicalStage:
    def __call__(self, state: Any, context: DataContext) -> StageResult:
        start = time.time()
        from temper_placer.heuristics.mcu_subsystem import MCUSubsystemHeuristic
        from temper_placer.optimizer.legalization import legalize_zone_aware
        from temper_placer.placer.deterministic import PlacementResult

        print("Running topological placement...")

        board = context["board"]
        netlist = context["netlist"]

        mcu_heuristic = MCUSubsystemHeuristic()
        try:
            mcu_result = mcu_heuristic.apply(netlist, board, zone_name="control_zone")
        except ValueError:
            try:
                mcu_result = mcu_heuristic.apply(netlist, board, zone_name="MCU_ZONE")
            except ValueError:
                mcu_result = mcu_heuristic.apply(netlist, board)

        positions = np.array(mcu_result.positions)
        rotations = np.array(mcu_result.rotations)

        for i, comp in enumerate(netlist.components):
            if comp.ref in mcu_result.placed_refs:
                continue
            if comp.initial_position:
                positions[i] = comp.initial_position
            else:
                if comp.zone:
                    zone = board.get_zone(comp.zone)
                    positions[i] = zone.center if zone else (board.width / 2, board.height / 2)
                else:
                    positions[i] = (board.width / 2, board.height / 2)
            if comp.initial_rotation is not None:
                rotations[i] = comp.initial_rotation * 90.0

        print("Running zone-aware legalization...")
        fixed_mask = np.array([c.fixed for c in netlist.components], dtype=bool)
        legalized_pos, success = legalize_zone_aware(positions, netlist, board, fixed_mask=fixed_mask)

        if not success:
            print("Warning: Legalization could not fully resolve overlaps.")

        deterministic_result = PlacementResult(
            positions=legalized_pos, rotations=rotations,
            placed_refs=[c.ref for c in netlist.components], unplaced_refs=[],
        )
        state.deterministic_result = deterministic_result

        elapsed = time.time() - start
        return StageResult(
            outputs={"deterministic_result": deterministic_result},
            duration_s=elapsed,
        )
