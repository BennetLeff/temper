
import jax.numpy as jnp
import pytest
from dataclasses import dataclass
from jax import Array

from temper_placer.losses.aesthetic import VisualGroupingLoss
from temper_placer.losses.base import LossResult
from temper_placer.core.board import Board, LayerStackup

@dataclass
class MockNetlist:
    n_components: int
    bounds: Array

    def get_bounds_array(self) -> Array:
        return self.bounds

@dataclass
class MockContext:
    board: Board
    netlist: MockNetlist

@pytest.fixture
def grouping_context():
    board = Board(
        width=100.0,
        height=100.0,
        origin=(0.0, 0.0),
        zones=[],
        ground_domains=[],
        layer_stackup=LayerStackup.default_4layer(),
    )
    # 6 components
    bounds = jnp.full((6, 2), 10.0)
    netlist = MockNetlist(n_components=6, bounds=bounds)
    return MockContext(board=board, netlist=netlist)

def test_visual_grouping_tight_clustering(grouping_context):
    """Test that tighter groups have lower loss."""
    # Group 1: 0, 1, 2. Group 2: 3, 4, 5.
    group_indices = jnp.array([
        [0, 1, 2],
        [3, 4, 5]
    ])
    
    # Case 1: Very tight groups
    pos_tight = jnp.array([
        [10, 10], [11, 10], [10, 11], # Group 1
        [80, 80], [81, 80], [80, 81]  # Group 2
    ])
    
    # Case 2: Spread out groups
    pos_spread = jnp.array([
        [10, 10], [30, 10], [10, 30], # Group 1
        [80, 80], [60, 80], [80, 60]  # Group 2
    ])
    
    rotations = jnp.zeros((6, 4))
    loss_fn = VisualGroupingLoss(group_indices=group_indices, min_gap=10.0)
    
    res_tight = loss_fn(pos_tight, rotations, grouping_context)
    res_spread = loss_fn(pos_spread, rotations, grouping_context)
    
    assert float(res_tight.value) < float(res_spread.value)

def test_visual_grouping_separation(grouping_context):
    """Test that groups too close have higher loss."""
    group_indices = jnp.array([
        [0, 1, 2],
        [3, 4, 5]
    ])
    
    # Case 1: Groups far apart (gap > 10)
    pos_far = jnp.array([
        [10, 10], [11, 10], [10, 11], # Group 1 center ~10,10
        [50, 50], [51, 50], [50, 51]  # Group 2 center ~50,50
    ])
    
    # Case 2: Groups too close (gap < 10)
    pos_close = jnp.array([
        [10, 10], [11, 10], [10, 11], # Group 1
        [15, 15], [16, 15], [15, 16]  # Group 2 - only 5mm away
    ])
    
    rotations = jnp.zeros((6, 4))
    loss_fn = VisualGroupingLoss(group_indices=group_indices, min_gap=10.0)
    
    res_far = loss_fn(pos_far, rotations, grouping_context)
    res_close = loss_fn(pos_close, rotations, grouping_context)
    
    # Inter-group penalty should trigger for pos_close
    assert float(res_far.value) < float(res_close.value)
