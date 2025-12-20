
import pytest
from datetime import datetime, timedelta
from temper_placer.pipeline.convergence import ConvergenceChecker, ConvergenceCriteria, TerminationReason
from temper_placer.pipeline.orchestrator import PipelineState, PipelineConfig
from temper_placer.routing.analysis import RoutabilityReport
from temper_placer.core.state import PlacementState
import jax.numpy as jnp
from pathlib import Path

@pytest.fixture
def criteria():
    return ConvergenceCriteria(
        max_iterations=3,
        timeout_seconds=1.0,
        max_overlap_mm2=0.1
    )

@pytest.fixture
def checker(criteria):
    return ConvergenceChecker(criteria)

def test_timeout_detection(checker):
    # Mock start time to be in the past
    checker.state.start_time = datetime.now() - timedelta(seconds=2)
    
    terminated, reason = checker.check_early_termination(iteration=0)
    assert terminated is True
    assert reason == TerminationReason.TIMEOUT

def test_max_iterations_detection(checker):
    terminated, reason = checker.check_early_termination(iteration=3)
    assert terminated is True
    assert reason == TerminationReason.MAX_ITERATIONS
    
    terminated, reason = checker.check_early_termination(iteration=2)
    assert terminated is False

def test_success_criteria_no_placement(checker):
    config = PipelineConfig(input_pcb=Path("fake.kicad_pcb"))
    state = PipelineState(config=config)
    
    success, reason = checker.check_success(state)
    assert success is False
    assert "No placement state" in reason

def test_infeasibility_detection(checker):
    from temper_placer.core.board import Board
    from temper_placer.core.netlist import Netlist, Component
    from temper_placer.pcl.parser import ConstraintCollection
    
    board = Board(width=10.0, height=10.0) # 100 mm2
    # Component 10x10 = 100 mm2
    comp = Component(ref="U1", footprint="F", bounds=(10.0, 10.0))
    netlist = Netlist(components=[comp])
    constraints = ConstraintCollection(constraints=[])
    
    # 100/100 = 100% fill > 85%
    is_infeasible, reason = checker.check_infeasibility(board, netlist, constraints)
    assert is_infeasible is True
    assert "exeed 85%" in reason or "exceed 85%" in reason

def test_progress_detection(checker):
    assert checker.check_progress(100.0) is True
    assert checker.state.best_loss == 100.0
    
    # Improvement
    assert checker.check_progress(90.0) is True
    assert checker.state.best_loss == 90.0
    assert checker.state.epochs_since_improvement == 0
    
    # No improvement
    assert checker.check_progress(89.99) is True # Need 0.1% improvement
    assert checker.state.best_loss == 90.0
    assert checker.state.epochs_since_improvement == 1
