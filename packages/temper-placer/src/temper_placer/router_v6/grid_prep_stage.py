"""
GridPrepStage: Build per-layer occupancy grids for A* pathfinding.
Stage 4.0 of the Router V6 pipeline.
Part of feat/stage4-astar-strangler.
"""

from __future__ import annotations

from dataclasses import replace

from temper_placer.deterministic.state import BoardState
from temper_placer.deterministic.stages.base import Stage
from temper_placer.router_v6.stage_validators import (
    StageDRCFailure,
    register_validator,
)


class GridPrepStage(Stage):
    """Stage 4.0: Build per-layer occupancy grids for A* pathfinding."""

    @property
    def name(self) -> str:
        return "GridPrep"

    def run(self, state: BoardState) -> BoardState:
        pcb = state._parsed_pcb
        if pcb is None:
            return state

        from temper_placer.router_v6.occupancy_grid import OccupancyGrid

        board_width = getattr(pcb, "board_width_mm", 200.0)
        board_height = getattr(pcb, "board_height_mm", 200.0)
        grid_res = 0.1

        if hasattr(pcb, "design_rules"):
            grid_res = getattr(pcb.design_rules, "grid_resolution_mm", 0.1)

        grids: dict[str, OccupancyGrid] = {}
        for layer in ("F.Cu", "B.Cu"):
            grids[layer] = OccupancyGrid(
                width=board_width,
                height=board_height,
                cell_size=grid_res,
                layer_name=layer,
            )

        return replace(state, parsed_grids=grids)


@register_validator("GridPrep")
def validate_grid_prep(state: BoardState) -> list[StageDRCFailure]:
    """Validate grid prep invariants."""
    failures: list[StageDRCFailure] = []
    if state.parsed_grids is None:
        failures.append(StageDRCFailure(
            field="parsed_grids",
            value=None,
            reason="Grids not computed",
            stage="GridPrep",
        ))
        return failures

    for layer in ("F.Cu", "B.Cu"):
        if layer not in state.parsed_grids:
            failures.append(StageDRCFailure(
                field="parsed_grids",
                value=layer,
                reason=f"Missing grid for layer {layer}",
                stage="GridPrep",
            ))

    return failures
