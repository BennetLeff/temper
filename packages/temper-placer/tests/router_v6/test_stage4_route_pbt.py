"""Property-based tests for RouteStage."""

from __future__ import annotations

from temper_placer.deterministic.state import BoardState
from temper_placer.router_v6.route_stage import RouteStage, validate_route


def test_route_name():
    """RouteStage has correct name."""
    stage = RouteStage()
    assert stage.name == "Route"


def test_route_empty_state():
    """RouteStage handles empty state."""
    stage = RouteStage()
    state = BoardState()
    result = stage.run(state)
    assert getattr(result, "pathfinding_result", None) is None or hasattr(result, "per_net_results")


def test_route_validator_missing():
    """Validator catches missing routing result."""
    state = BoardState()
    failures = validate_route(state)
    assert len(failures) > 0
