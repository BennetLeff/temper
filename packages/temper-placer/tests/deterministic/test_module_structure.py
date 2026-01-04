import pytest
from dataclasses import FrozenInstanceError

def test_can_import_pipeline():
    from temper_placer.deterministic import DeterministicPipeline
    assert DeterministicPipeline is not None

def test_can_import_stages():
    from temper_placer.deterministic.stages import (
        ZoneAssignmentStage,
        ClearanceGridStage,
        SequentialRoutingStage,
    )
    # Should not raise ImportError

def test_board_state_is_frozen():
    from temper_placer.deterministic.state import BoardState
    state = BoardState()
    with pytest.raises(FrozenInstanceError):
        state.routes = []  # Should fail - immutable
