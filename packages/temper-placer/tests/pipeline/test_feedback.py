import jax.numpy as jnp
import pytest

from temper_placer.core.board import Board
from temper_placer.core.netlist import Component, Netlist
from temper_placer.core.state import PlacementState
from temper_placer.pipeline.feedback import (
    FeedbackGenerator,
    FeedbackLoopConfig,
    ValidationFailure,
    analyze_root_cause,
    run_feedback_loop,
)


@pytest.fixture
def sample_env():
    board = Board(width=100, height=100)
    # Need 3 components for a loop
    c1 = Component("Q1", "Pkg", (10, 10))
    c2 = Component("Q2", "Pkg", (10, 10))
    c3 = Component("C_BUS1", "Pkg", (10, 10))
    netlist = Netlist([c1, c2, c3], [])

    # Large area triangle: (0,0), (10,0), (0,10) -> Area = 50
    state = PlacementState.from_positions(jnp.array([[0.0, 0.0], [10.0, 0.0], [0.0, 10.0]]))
    return board, netlist, state

def test_analyze_loop_failure(sample_env):
    board, netlist, state = sample_env
    failure = ValidationFailure(
        spec_name='loop_area_power',
        actual_value=100.0, # Routing area
        limit_value=20.0,
        margin=-80.0
    )

    # min_placement_area should be 50.0 (from state)
    # placement_contrib should be 50 / 100 * 100 = 50%

    analysis = analyze_root_cause(failure, state, netlist, board)

    assert analysis.placement_contribution >= 50
    assert any(f.target == 'placement' for f in analysis.fixes)
    assert any(f.target == 'routing' for f in analysis.fixes)

def test_feedback_generator(sample_env):

    board, netlist, state = sample_env

    failure = ValidationFailure(

        spec_name='thermal_max_tj',

        actual_value=130.0,

        limit_value=110.0,

        margin=-20.0

    )



    generator = FeedbackGenerator(state, netlist, board)

    adjustments = generator.generate([failure])



    assert len(adjustments) == 1

    assert adjustments[0].adjustment_type.value == 'placement'



def test_run_feedback_loop(sample_env):

    from unittest.mock import MagicMock

    board, netlist, state = sample_env



    # Mock pipeline state

    pipeline_state = MagicMock()

    pipeline_state.board = board

    pipeline_state.netlist = netlist

    pipeline_state.placement_state = state

    pipeline_state.physics_report = None # No report = no failures



    config = FeedbackLoopConfig(max_iterations=2)

    result = run_feedback_loop(pipeline_state, config)



    assert result.success

    assert result.iterations == 0
