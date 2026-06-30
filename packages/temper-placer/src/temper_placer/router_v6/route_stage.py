"""
RouteStage: Route nets using A*/Theta* with ripup/reroute.
Stage 4.2 of the Router V6 pipeline.
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


class RouteStage(Stage):
    """Stage 4.2: Route nets using A* pathfinding with ripup capability."""

    @property
    def name(self) -> str:
        return "Route"

    def run(self, state: BoardState) -> BoardState:
        from temper_placer.router_v6.astar_pathfinding import run_astar_pathfinding
        from temper_placer.router_v6.congestion_tensor import CongestionTensor

        pcb = state._parsed_pcb
        if pcb is None:
            return state

        grids = state.parsed_grids or {}
        fcu_grid = grids.get("F.Cu")
        if fcu_grid is None:
            return state

        channel_mapping = getattr(state, "channel_mapping", None)
        if channel_mapping is None:
            return state

        design_rules = getattr(pcb, "design_rules", None)
        escape_vias_map = getattr(state, "escape_vias_map", None)
        use_theta_star = getattr(state, "enable_theta_star", False)
        use_lazy_theta_star = getattr(state, "enable_lazy_theta_star", False)
        enable_coarse_to_fine = getattr(state, "enable_coarse_to_fine", False)
        coarse_factor = getattr(state, "coarse_factor", 4)
        corridor_buffer_cells = getattr(state, "corridor_buffer_cells", 12)

        # U7 / R11: PathFinder history cost.  Build a per-cell
        # congestion tensor matching the primary grid.  The
        # pathfinding increments the tensor along each routed
        # path; subsequent A* calls add the per-cell cost to
        # f_score so the next net naturally detours around
        # already-routed channels.
        #
        # The default weight is 0.0 (opt-in).  Empirically on
        # temper.kicad_pcb the hard signal nets (SPI/PWM/AC)
        # need direct paths, and any non-zero weight pushes
        # them into blocked detours (10/24 vs 15/24 with
        # weight=0.1, 13/24 with weight=1.0).  The
        # implementation is correct and the unit tests pass;
        # this just defaults to off for the closure test.
        # Override ``state.congestion_weight`` to enable.
        cong_weight = getattr(state, "congestion_weight", 0.0)
        congestion_tensor = CongestionTensor.zeros(
            fcu_grid.height_cells, fcu_grid.width_cells,
            weight=cong_weight,
        )

        result = run_astar_pathfinding(
            channel_mapping=channel_mapping,
            grid=fcu_grid,
            design_rules=design_rules,
            alternate_grid=grids.get("B.Cu"),
            pcb=pcb,
            escape_vias_map=escape_vias_map,
            use_theta_star=use_theta_star,
            use_lazy_theta_star=use_lazy_theta_star,
            congestion_tensor=congestion_tensor,
            enable_coarse_to_fine=enable_coarse_to_fine,
            coarse_factor=coarse_factor,
            corridor_buffer_cells=corridor_buffer_cells,
        )

        return replace(
            state,
            pathfinding_result=result,
            per_net_results=result.routed_paths,
            failed_nets=result.failed_nets,
            failure_reports=result.failure_reports,
        )


@register_validator("Route")
def validate_route(state: BoardState) -> list[StageDRCFailure]:
    """Validate route stage invariants."""
    failures: list[StageDRCFailure] = []
    result = getattr(state, "pathfinding_result", None)
    if result is None:
        failures.append(StageDRCFailure(
            field="pathfinding_result",
            value=None,
            reason="Pathfinding not completed",
            stage="Route",
        ))
        return failures

    per_net = getattr(state, "per_net_results", None) or {}
    failed = getattr(state, "failed_nets", None) or []
    if len(per_net) + len(failed) == 0 and hasattr(state, "_parsed_pcb") and state._parsed_pcb:
        failures.append(StageDRCFailure(
            field="per_net_results",
            value={"routed": len(per_net), "failed": len(failed)},
            reason="All nets skipped or empty",
            stage="Route",
        ))

    return failures
