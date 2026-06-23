"""
ResultAggregateStage: Compile PathfindingResult from per-net routing results.
Stage 4.3 of the Router V6 pipeline.
Part of feat/stage4-astar-strangler.
"""

from __future__ import annotations

from dataclasses import replace

from temper_placer.deterministic.state import BoardState
from temper_placer.deterministic.stages.base import Stage
from temper_placer.router_v6.astar_pathfinding import PathfindingResult
from temper_placer.router_v6.stage_validators import (
    StageDRCFailure,
    register_validator,
)


class ResultAggregateStage(Stage):
    """Stage 4.3: Compile PathfindingResult from per-net routing results."""

    @property
    def name(self) -> str:
        return "ResultAggregate"

    def run(self, state: BoardState) -> BoardState:
        per_net = getattr(state, "per_net_results", None) or {}
        failed = getattr(state, "failed_nets", None) or []
        failure_reports = getattr(state, "failure_reports", None)

        result = PathfindingResult(
            routed_paths=per_net,
            failed_nets=failed,
            failure_reports=failure_reports,
        )

        return replace(state, pathfinding_result=result)


@register_validator("ResultAggregate")
def validate_result_aggregate(state: BoardState) -> list[StageDRCFailure]:
    """Validate result aggregate invariants."""
    failures: list[StageDRCFailure] = []
    result = getattr(state, "pathfinding_result", None)

    if result is None:
        failures.append(StageDRCFailure(
            field="pathfinding_result",
            value=None,
            reason="PathfindingResult not compiled",
            stage="ResultAggregate",
        ))
        return failures

    total = result.success_count + result.failure_count
    if total > 0:
        expected = result.success_count / total
        if abs(result.completion_rate - expected) > 0.001:
            failures.append(StageDRCFailure(
                field="completion_rate",
                value=result.completion_rate,
                reason=f"Expected {expected:.3f} based on success/failure counts",
                stage="ResultAggregate",
            ))

    return failures
