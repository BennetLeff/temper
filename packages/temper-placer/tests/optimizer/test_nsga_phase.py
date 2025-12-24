
import pytest
import jax.numpy as jnp
from unittest.mock import MagicMock
from temper_placer.optimizer.nsga2 import select_knee_point
from temper_placer.optimizer.phases import NsgaPhase, ParetoFrontResult
from temper_placer.core.state import PlacementState
from temper_placer.core.board import Board, LayerStackup
from temper_placer.core.netlist import Component, Netlist
from temper_placer.losses.base import LossContext
from temper_placer.optimizer.config import OptimizerConfig

@pytest.fixture
def basic_setup():
    board = Board(width=100, height=100, origin=(0,0), zones=[], ground_domains=[],
                  layer_stackup=LayerStackup.default_4layer())
    components = [
        Component(ref="R1", footprint="0603", bounds=(1.6, 0.8)),
        Component(ref="U1", footprint="SOIC-8", bounds=(5, 4))
    ]
    netlist = Netlist(components=components)
    opt_config = OptimizerConfig.fast_test()
    context = LossContext.from_netlist_and_board(netlist, board)

    return netlist, board, None, opt_config, None, context

def test_select_knee_point_2d():
    """Verify knee point selection on a simple 2D front."""
    # Front with 3 points: (0, 10), (5, 5), (10, 0)
    # Normalized: (0, 1), (0.5, 0.5), (1, 0)
    # L2 distances: 1.0, sqrt(0.5) approx 0.707, 1.0
    # Knee point should be (5, 5) at index 1
    objectives = jnp.array([
        [0.0, 10.0],
        [5.0, 5.0],
        [10.0, 0.0]
    ])
    
    idx = select_knee_point(objectives)
    assert idx == 1

def test_select_knee_point_3d():
    """Verify knee point selection on a 3D front."""
    # ideal point is (0,0,0) after normalization
    objectives = jnp.array([
        [1.0, 0.0, 0.0],
        [0.0, 1.0, 0.0],
        [0.0, 0.0, 1.0],
        [0.4, 0.4, 0.4] # Closer to ideal point than corners
    ])
    
    idx = select_knee_point(objectives)
    assert idx == 3

def test_select_knee_point_weighted():
    """Verify that weights can steer knee point selection."""
    # (0, 10), (10, 0)
    # Norm: (0, 1), (1, 0)
    objectives = jnp.array([
        [0.0, 10.0],
        [10.0, 0.0]
    ])
    
    # Weighting the second objective heavily should pick the one where it's 0
    idx_w1 = select_knee_point(objectives, weights=jnp.array([1.0, 10.0]))
    assert idx_w1 == 1
    
    # Weighting the first objective heavily should pick the one where it's 0
    idx_w2 = select_knee_point(objectives, weights=jnp.array([10.0, 1.0]))
    assert idx_w2 == 0

def test_nsga_phase_returns_pareto_front(basic_setup):
    """Integration test: verify NsgaPhase returns full Pareto front result."""
    netlist, board, _, _, _, context = basic_setup
    
    # Mock objectives that create a trade-off
    def obj1(pos, rot, ctx, e, te):
        # penalize X
        return MagicMock(value=jnp.mean(pos[:, 0]))
    
    def obj2(pos, rot, ctx, e, te):
        # penalize Y
        return MagicMock(value=jnp.mean(pos[:, 1]))
        
    phase = NsgaPhase(generations=10, pop_size=20)
    
    # We need a topo result to get an initial state
    from temper_placer.optimizer.phases import TopologicalPhase
    topo = TopologicalPhase()
    # Mock constraints
    from temper_placer.pcl.parser import ConstraintCollection
    constraints = ConstraintCollection([])
    topo_res = topo.run(netlist, board, constraints)
    
    result = phase.run(netlist, board, [obj1, obj2], context, topo_res.state)
    
    assert isinstance(result, ParetoFrontResult)
    assert len(result.states) > 0
    assert result.objectives.shape[0] == len(result.states)
    assert result.objectives.shape[1] == 2
    assert result.state is not None # Knee point

def test_nsga_phase_non_dominated(basic_setup):
    """Test that all solutions in returned front are non-dominated."""
    netlist, board, _, _, _, context = basic_setup
    
    def obj1(pos, rot, ctx, e, te): return MagicMock(value=jnp.sum(pos**2))
    def obj2(pos, rot, ctx, e, te): return MagicMock(value=jnp.sum((pos-10)**2))
        
    phase = NsgaPhase(generations=20, pop_size=40)
    
    from temper_placer.optimizer.phases import TopologicalPhase
    topo = TopologicalPhase()
    from temper_placer.pcl.parser import ConstraintCollection
    constraints = ConstraintCollection([])
    topo_res = topo.run(netlist, board, constraints)
    
    result = phase.run(netlist, board, [obj1, obj2], context, topo_res.state)
    
    objs = result.objectives
    n = objs.shape[0]
    
    # Verify non-domination within the returned front
    for i in range(n):
        for j in range(n):
            if i == j: continue
            # idx i should NOT be dominated by idx j
            diff = objs[j] - objs[i]
            j_dominates_i = jnp.all(diff <= 0) and jnp.any(diff < 0)
            assert not j_dominates_i, f"Solution {i} is dominated by {j}"
