"""Property-based tests for NetPrepStage."""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis.strategies import text

from temper_placer.deterministic.state import BoardState
from temper_placer.router_v6.net_prep_stage import NetPrepStage, validate_net_prep


def test_net_prep_name():
    """NetPrepStage has correct name."""
    stage = NetPrepStage()
    assert stage.name == "NetPrep"


def test_net_prep_empty_state():
    """NetPrepStage handles empty state gracefully."""
    stage = NetPrepStage()
    state = BoardState()
    result = stage.run(state)
    assert hasattr(result, "tht_locations")


def test_net_prep_validator_no_tht():
    """Validator flags missing tht_locations."""
    state = BoardState()
    failures = validate_net_prep(state)
    assert len(failures) > 0
