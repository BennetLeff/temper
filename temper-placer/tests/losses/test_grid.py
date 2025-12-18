
import pytest
import jax
import jax.numpy as jnp
from temper_placer.losses.grid import GridAlignmentLoss, compute_grid_penalty
from temper_placer.losses.base import LossContext

def test_grid_alignment_zero_penalty():
    """Verify that perfectly aligned components have zero penalty."""
    grid_size = 0.5
    positions = jnp.array([
        [10.0, 20.0],
        [10.5, 20.5],
        [0.0, 0.0]
    ])
    penalty = compute_grid_penalty(positions, grid_size)
    assert float(penalty) == pytest.approx(0.0, abs=1e-6)

def test_grid_alignment_positive_penalty():
    """Verify that misaligned components produce positive penalty."""
    grid_size = 1.0
    positions = jnp.array([
        [10.1, 20.0], # 0.1 off
    ])
    penalty = compute_grid_penalty(positions, grid_size)
    # 0.1^2 = 0.01
    assert float(penalty) == pytest.approx(0.01, abs=1e-6)

def test_grid_alignment_wrap():
    """Verify wrap to nearest grid point (e.g. 0.4 off 0.5 is 0.1)."""
    grid_size = 0.5
    positions = jnp.array([
        [0.4, 0.0], # Nearest grid is 0.5, dist is 0.1
    ])
    penalty = compute_grid_penalty(positions, grid_size)
    assert float(penalty) == pytest.approx(0.01, abs=1e-6)

def test_grid_weight_schedule():
    """Verify weight annealing ramp."""
    loss_fn = GridAlignmentLoss(anneal_start=0.5)
    
    # Before ramp
    assert loss_fn.weight_schedule(0, 1000) == 0.0
    assert loss_fn.weight_schedule(499, 1000) == 0.0
    
    # During ramp (50% through ramp)
    # Epoch 750 is 50% from 500 to 1000
    assert loss_fn.weight_schedule(750, 1000) == pytest.approx(0.5, abs=0.01)
    
    # End of ramp
    assert loss_fn.weight_schedule(1000, 1000) == 1.0

def test_grid_gradient():
    """Verify gradients point toward nearest grid point."""
    grid_size = 1.0
    # Positioned at 0.1, should be pushed toward 0.0
    # Positioned at 0.9, should be pushed toward 1.0
    positions = jnp.array([
        [0.1, 0.5],
        [0.9, 0.5]
    ])
    
    def loss_val(pos):
        return compute_grid_penalty(pos, grid_size)
        
    grad = jax.grad(loss_val)(positions)
    
    # First component at 0.1: penalty x^2, grad 2x = 0.2
    # Second component at 0.9: dist is -0.1, grad -0.2
    assert float(grad[0, 0]) > 0 # Pushing away from 0.1 (toward 0.0)? 
    # Wait, penalty is dist^2. dist = 0.1. d/dx (x mod 1.0)^2 = 2 * 0.1 = 0.2.
    # Positive gradient means increasing x increases loss. 
    # So to decrease loss, we move in negative direction (toward 0.0). Correct.
    assert float(grad[0, 0]) == pytest.approx(0.2, abs=1e-6)
    
    # Second component at 0.9: dist = 1.0 - 0.9 = 0.1.
    # But wait, our formula is jnp.minimum(offset, grid - offset)
    # dist_x = 1.0 - 0.9 = 0.1.
    # d/dx (1.0 - x)^2 = 2 * (1.0 - x) * (-1) = -2 * 0.1 = -0.2.
    # Negative gradient means increasing x decreases loss.
    # So we move in positive direction (toward 1.0). Correct.
    assert float(grad[1, 0]) == pytest.approx(-0.2, abs=1e-6)
