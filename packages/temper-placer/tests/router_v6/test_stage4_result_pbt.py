"""Property-based tests for ResultAggregateStage."""

from __future__ import annotations

from temper_placer.deterministic.state import BoardState
from temper_placer.router_v6.result_aggregate_stage import (
    ResultAggregateStage,
    validate_result_aggregate,
)


def test_result_aggregate_name():
    """ResultAggregateStage has correct name."""
    stage = ResultAggregateStage()
    assert stage.name == "ResultAggregate"


def test_result_aggregate_empty():
    """Aggregate handles no routing results."""
    stage = ResultAggregateStage()
    state = BoardState()
    result = stage.run(state)
    assert result.pathfinding_result is not None
    assert result.pathfinding_result.success_count == 0
    assert result.pathfinding_result.failure_count == 0


def test_result_aggregate_validator_missing():
    """Validator catches missing result."""
    state = BoardState()
    failures = validate_result_aggregate(state)
    assert len(failures) > 0
