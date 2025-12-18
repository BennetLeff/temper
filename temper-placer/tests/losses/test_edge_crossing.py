
import pytest
import jax.numpy as jnp
from temper_placer.losses.planarity import EdgeCrossingLoss

class MockContext:
    def __init__(self, indices, offsets, mask):
        self.net_pin_indices = indices
        self.net_pin_offsets = offsets
        self.net_pin_mask = mask

def test_edge_crossing_x():
    """Verify that an 'X' crossing produces a positive penalty."""
    # Net A: (0, 10) -> (20, 10)
    # Net B: (10, 0) -> (10, 20)
    indices = jnp.array([[0, 1], [2, 3]], dtype=jnp.int32)
    # Need to pad to P=4 because LossContext usually has max_pins padding
    # But for our EdgeCrossingLoss, it assumes pins are at 0 and 1
    p_indices = jnp.zeros((2, 4), dtype=jnp.int32).at[:, :2].set(indices)
    p_offsets = jnp.zeros((2, 4, 2))
    p_mask = jnp.zeros((2, 4), dtype=bool).at[:, :2].set(True)
    
    context = MockContext(p_indices, p_offsets, p_mask)
    
    positions = jnp.array([
        [0.0, 10.0], [20.0, 10.0], # Net A
        [10.0, 0.0], [10.0, 20.0]  # Net B
    ])
    
    loss_fn = EdgeCrossingLoss()
    # rotations: 4 components, all 0 degrees
    rotations = jnp.eye(4)[jnp.zeros(4, dtype=jnp.int32)]
    
    res = loss_fn(positions, rotations, context)
    assert float(res.value) > 0

def test_edge_crossing_parallel():
    """Verify that parallel nets have zero penalty."""
    indices = jnp.array([[0, 1], [2, 3]], dtype=jnp.int32)
    p_indices = jnp.zeros((2, 4), dtype=jnp.int32).at[:, :2].set(indices)
    p_offsets = jnp.zeros((2, 4, 2))
    p_mask = jnp.zeros((2, 4), dtype=bool).at[:, :2].set(True)
    context = MockContext(p_indices, p_offsets, p_mask)
    
    # Parallel lines
    positions = jnp.array([
        [0.0, 0.0], [10.0, 0.0], # Net A
        [0.0, 5.0], [10.0, 5.0]  # Net B
    ])
    
    loss_fn = EdgeCrossingLoss()
    # rotations: 4 components, all 0 degrees
    rotations = jnp.eye(4)[jnp.zeros(4, dtype=jnp.int32)]
    
    res = loss_fn(positions, rotations, context)
    assert float(res.value) == pytest.approx(0.0, abs=1e-6)

def test_edge_crossing_touching():
    """Verify that touching but not crossing nets have zero penalty."""
    # Shared vertex
    positions = jnp.array([
        [0.0, 0.0], [10.0, 0.0], # Net A
        [10.0, 0.0], [10.0, 10.0] # Net B
    ])
    
    indices = jnp.array([[0, 1], [2, 3]], dtype=jnp.int32)
    p_indices = jnp.zeros((2, 4), dtype=jnp.int32).at[:, :2].set(indices)
    p_offsets = jnp.zeros((2, 4, 2))
    p_mask = jnp.zeros((2, 4), dtype=bool).at[:, :2].set(True)
    context = MockContext(p_indices, p_offsets, p_mask)
    
    loss_fn = EdgeCrossingLoss()
    # rotations: 4 components, all 0 degrees
    rotations = jnp.eye(4)[jnp.zeros(4, dtype=jnp.int32)]
    
    res = loss_fn(positions, rotations, context)
    # They touch at (10,0), but s1*s2 = 0*val = 0.
    assert float(res.value) == pytest.approx(0.0, abs=1e-6)
