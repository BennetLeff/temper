
import pytest
import jax.numpy as jnp
from pathlib import Path
from temper_placer.optimizer.phases import OptimizationPipeline, PhaseStatus, TopologicalPhase, GeometricPhase
from temper_placer.core.state import PlacementState
from temper_placer.core.board import Board, LayerStackup
from temper_placer.core.netlist import Component, Netlist
from temper_placer.pcl.parser import ConstraintCollection
from temper_placer.optimizer.config import OptimizerConfig
from temper_placer.losses.base import CompositeLoss, LossContext, WeightedLoss
from temper_placer.losses.wirelength import WirelengthLoss

@pytest.fixture
def basic_setup():
    board = Board(width=100, height=100, origin=(0,0), zones=[], ground_domains=[], 
                  layer_stackup=LayerStackup.default_4layer())
    components = [
        Component(ref="R1", footprint="0603", bounds=(1.6, 0.8)),
        Component(ref="U1", footprint="SOIC-8", bounds=(5, 4))
    ]
    netlist = Netlist(components=components)
    constraints = ConstraintCollection([])
    opt_config = OptimizerConfig.fast_test()
    context = LossContext.from_netlist_and_board(netlist, board)
    
    def loss_factory(weights):
        return CompositeLoss([WeightedLoss(WirelengthLoss(), weight=1.0)])
        
    return netlist, board, constraints, opt_config, loss_factory, context

def test_topological_phase_success(basic_setup):
    """Test that topological phase generates initial state."""
    netlist, board, constraints, _, _, _ = basic_setup
    phase = TopologicalPhase()
    result = phase.run(netlist, board, constraints)
    
    assert result.status == PhaseStatus.SUCCESS
    assert result.state is not None
    assert result.state.positions.shape == (2, 2)

def test_pipeline_execution(basic_setup):
    """Test full pipeline execution flow."""
    netlist, board, constraints, opt_config, loss_factory, context = basic_setup
    pipeline = OptimizationPipeline(netlist, board, constraints, opt_config, loss_factory, context)
    
    result = pipeline.run()
    
    assert result.success is True
    assert len(result.phases) == 2
    assert result.phases[0].status == PhaseStatus.SUCCESS
    assert result.phases[1].status == PhaseStatus.SUCCESS
    assert result.final_state is not None

