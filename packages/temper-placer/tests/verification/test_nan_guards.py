import jax
import jax.numpy as jnp
import pytest
from temper_placer.losses.loop_area import LoopAreaLoss
from temper_placer.losses.base import LossContext, LoopConstraint

def test_loop_area_nan_position(simple_netlist, simple_board, simple_placement_state):
    """Loss with one NaN position should handle it gracefully."""
    loop_constraints = [
        LoopConstraint(name="L1", pins=[("U1", "VCC"), ("C1", "1"), ("C1", "2")], max_area=10.0, weight=1.0)
    ]
    context = LossContext.from_netlist_and_board(
        simple_netlist, 
        simple_board, 
        loop_constraints=loop_constraints
    )
    
    loss_fn = LoopAreaLoss()
    
    positions = simple_placement_state.positions
    # Inject NaN
    positions = positions.at[0, 0].set(jnp.nan)
    
    n_comp = positions.shape[0]
    rotations = jnp.zeros((n_comp, 4))
    rotations = rotations.at[:, 0].set(1.0)
    
    result = loss_fn(positions, rotations, context)
    
    # Current behavior likely returns NaN
    # We WANT it to return Inf or a large penalty, and definitely not NaN
    assert not jnp.isnan(result.value)

def test_loop_area_inf_gradient(simple_netlist, simple_board, simple_placement_state):
    """Gradient with Inf input should be handled."""
    loop_constraints = [
        LoopConstraint(name="L1", pins=[("U1", "VCC"), ("C1", "1"), ("C1", "2")], max_area=10.0, weight=1.0)
    ]
    context = LossContext.from_netlist_and_board(
        simple_netlist, 
        simple_board, 
        loop_constraints=loop_constraints
    )
    
    loss_fn = LoopAreaLoss()
    
    def total_loss(pos):
        n_comp = pos.shape[0]
        rot = jnp.zeros((n_comp, 4)).at[:, 0].set(1.0)
        return loss_fn(pos, rot, context).value
    
    grad_fn = jax.grad(total_loss)
    
    positions = simple_placement_state.positions
    # Inject Inf
    positions = positions.at[0, 0].set(jnp.inf)
    
    grads = grad_fn(positions)
    
    # We want gradients to be finite if possible, or at least not NaN
    assert jnp.all(jnp.isfinite(grads))

def test_overlap_nan_position(simple_netlist, simple_board, simple_placement_state):
    """OverlapLoss with NaN position should handle it gracefully."""
    from temper_placer.losses.overlap import OverlapLoss
    
    context = LossContext.from_netlist_and_board(simple_netlist, simple_board)
    loss_fn = OverlapLoss()
    
    positions = simple_placement_state.positions
    positions = positions.at[0, 0].set(jnp.nan)
    
    n_comp = positions.shape[0]
    rotations = jnp.zeros((n_comp, 4)).at[:, 0].set(1.0)
    
    result = loss_fn(positions, rotations, context)
    assert not jnp.isnan(result.value)
