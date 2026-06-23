"""
RouteStage: Route nets using A*/Theta* with ripup/reroute.
Stage 4.2 of the Router V6 pipeline.
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


class RouteStage(Stage):
    """Stage 4.2: Route nets using A* pathfinding with ripup capability."""

    @property
    def name(self) -> str:
        return "Route"

    def run(self, state: BoardState) -> BoardState:
        from temper_placer.router_v6.astar_pathfinding import run_astar_pathfinding

        pcb = state._parsed_pcb
        if pcb is None:
            return state

        grids = state.parsed_grids or {}
        fcu_grid = grids.get("F.Cu")
        if fcu_grid is None:
            return state

        design_rules = getattr(pcb, "design_rules", None)
        result = run_astar_pathfinding(
            channel_mapping=None,
            grid=fcu_grid,
            design_rules=design_rules,
            alternate_grid=grids.get("B.Cu"),
            pcb=pcb,
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
