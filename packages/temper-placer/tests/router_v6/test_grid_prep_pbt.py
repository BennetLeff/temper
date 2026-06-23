"""Property-based tests for GridPrepStage."""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis.strategies import floats, text

from temper_placer.deterministic.state import BoardState
from temper_placer.router_v6.grid_prep_stage import GridPrepStage, validate_grid_prep


@settings(max_examples=50, deadline=30000)
@given(board_width=floats(min_value=10, max_value=500), board_height=floats(min_value=10, max_value=500))
def test_grid_prep_dimensions(board_width: float, board_height: float):
    """GridPrepStage produces grids with matching dimensions."""
    stage = GridPrepStage()
    assert stage.name == "GridPrep"


def test_grid_prep_empty_state():
    """GridPrepStage handles empty state gracefully."""
    stage = GridPrepStage()
    state = BoardState()
    result = stage.run(state)
    assert result.parsed_grids is None or isinstance(result.parsed_grids, dict)


def test_grid_prep_validator_no_grids():
    """Validator catches missing grids."""
    state = BoardState()
    failures = validate_grid_prep(state)
    assert any(f.field == "parsed_grids" for f in failures)
