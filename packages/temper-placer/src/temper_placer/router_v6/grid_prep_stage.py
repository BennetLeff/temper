"""
GridPrepStage: Build per-layer occupancy grids for A* pathfinding.
Stage 4.0 of the Router V6 pipeline.
Part of feat/stage4-astar-strangler.
"""

from __future__ import annotations

from dataclasses import replace

from temper_placer.deterministic.stages.base import Stage
from temper_placer.deterministic.state import BoardState
from temper_placer.router_v6.stage_validators import (
    StageDRCFailure,
    register_validator,
)


def _routable_layers_for(pcb) -> tuple[str, ...]:
    """Resolve the layer set this stage should build grids for.

    Reads through ``core.board_layer_roles.routable_signal_layers_from_path``
    -- the board's own declared signal layers intersected with the router's
    real engine capability -- rather than a hardcoded pair, so a stackup
    edit (e.g. the 2026-08-13 6-layer decision) propagates here
    automatically. Falls back to the engine-capability constant alone
    (never a bare ``("F.Cu", "B.Cu")`` literal) when ``pcb`` has no real
    ``source_path`` to read (synthetic/test fixtures) or the board file
    can't be parsed for its declared roles.
    """
    from temper_placer.core.board_layer_roles import (
        ENGINE_SUPPORTED_SIGNAL_LAYERS_ORDERED,
        routable_signal_layers_from_path,
    )

    source_path = getattr(pcb, "source_path", None)
    if source_path:
        try:
            layers = routable_signal_layers_from_path(source_path)
            if layers:
                return tuple(layers)
        except (OSError, ValueError):
            pass
    return ENGINE_SUPPORTED_SIGNAL_LAYERS_ORDERED


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

        width_cells = 2000
        height_cells = 2000
        grid_res = 0.1

        if hasattr(pcb, "design_rules"):
            grid_res = getattr(pcb.design_rules, "grid_resolution_mm", 0.1)

        import numpy as np

        grids: dict[str, OccupancyGrid] = {}
        for layer in _routable_layers_for(pcb):
            grid_array = np.zeros((height_cells, width_cells), dtype=np.int8)
            grids[layer] = OccupancyGrid(
                layer_name=layer,
                grid=grid_array,
                origin=(0.0, 0.0),
                cell_size=grid_res,
                width_cells=width_cells,
                height_cells=height_cells,
            )

        return replace(state, parsed_grids=grids)


@register_validator("GridPrep")
def validate_grid_prep(state: BoardState) -> list[StageDRCFailure]:
    """Validate grid prep invariants."""
    failures: list[StageDRCFailure] = []
    if state.parsed_grids is None:
        failures.append(
            StageDRCFailure(
                field="parsed_grids",
                value=None,
                reason="Grids not computed",
                stage="GridPrep",
            )
        )
        return failures

    expected_layers = _routable_layers_for(state._parsed_pcb)
    for layer in expected_layers:
        if layer not in state.parsed_grids:
            failures.append(
                StageDRCFailure(
                    field="parsed_grids",
                    value=layer,
                    reason=f"Missing grid for layer {layer}",
                    stage="GridPrep",
                )
            )

    return failures
