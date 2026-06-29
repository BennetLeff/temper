"""
GradNorm: Gradient Normalization for Adaptive Loss Balancing.

Implements the GradNorm algorithm from Chen et al. (2018):
"GradNorm: Gradient Normalization for Adaptive Loss Balancing in Deep Multitask Networks"

GradNorm dynamically adjusts loss weights during training to balance the
gradient magnitudes of different loss terms, preventing any single loss from
dominating the optimization.
"""

from __future__ import annotations

from collections.abc import Callable

import jax
import jax.numpy as jnp
from jax import Array

from temper_placer.losses.base import CompositeLoss, LossContext


def compute_individual_loss_gradient_norms(
    composite_loss: CompositeLoss,
    loss_context: LossContext,
    positions: Array,
    rotations: Array,
    epoch: int,
    total_epochs: int,
) -> Array:
    """
    Compute gradient norms for each individual loss term.

    This is expensive (requires N forward + backward passes) but necessary
    for GradNorm adaptive weighting.

    Args:
        composite_loss: Composite loss with multiple weighted terms.
        loss_context: Context with netlist, board, etc.
        positions: Current positions (N, 2).
        rotations: Current rotations (N, 4) one-hot.
        epoch: Current training epoch.
        total_epochs: Total training epochs.

    Returns:
        Array of gradient norms (L,) for L loss terms.
    """
    n_losses = len(composite_loss.losses)

    def get_individual_loss(i, pos, rot):
        """Get loss value for i-th term using jax.lax.switch for tracing."""
        def make_loss_thunk(wloss_idx):
            def thunk(p_r):
                pos_in, rot_in = p_r
                wloss = composite_loss.losses[wloss_idx]
                res = wloss.loss_fn(pos_in, rot_in, loss_context, epoch, total_epochs)
                return res.value / wloss.get_normalizer(loss_context)
            return thunk

        thunks = [make_loss_thunk(idx) for idx in range(n_losses)]
        return jax.lax.switch(i, thunks, (pos, rot))

    def get_grad_norm(i):
        """Compute gradient norm for i-th loss term."""
        grad_fn = jax.grad(get_individual_loss, argnums=1)  # w.r.t. positions
        g = grad_fn(i, positions, rotations)
        # Apply fixed mask to match total gradient behavior
        g = jnp.where(loss_context.fixed_mask[:, None], 0.0, g)
        return jnp.linalg.norm(g)

    return jax.vmap(get_grad_norm)(jnp.arange(n_losses))


def update_gradnorm_weights(
    loss_weights: Array,
    current_grad_norms: Array,
    initial_grad_norms: Array,
    epoch: int,
    learning_rate: float = 0.025,
    _alpha: float = 1.5,
) -> tuple[Array, Array]:
    """
    Update loss weights using GradNorm algorithm.

    Args:
        loss_weights: Current dynamic loss weights (L,).
        current_grad_norms: Current gradient norms (L,).
        initial_grad_norms: Initial gradient norms from epoch 0 (L,).
        epoch: Current epoch.
        learning_rate: Learning rate for weight updates.
        alpha: Asymmetry parameter (how aggressively to balance).

    Returns:
        Tuple of (new_loss_weights, new_initial_grad_norms).
    """
    # Update initial norms at epoch 0
    new_initial_grad_norms = jnp.where(
        epoch == 0,
        current_grad_norms,
        initial_grad_norms,
    )
    # Avoid division by zero
    new_initial_grad_norms = jnp.maximum(new_initial_grad_norms, 1e-6)

    # Compute weighted gradient norms: w_i * ||grad(L_i)||
    gw_norms = loss_weights * current_grad_norms

    # Compute target norm: mean(gw_i)
    target_norms = jnp.mean(gw_norms)

    # Compute gradient of GradNorm loss
    # L_grad = sum |gw_i - target_i|
    # grad w.r.t. w_i = sign(gw_i - target_i) * ||grad(L_i)||
    weight_grads = jnp.sign(gw_norms - target_norms) * current_grad_norms

    # Update weights
    new_loss_weights = loss_weights - learning_rate * weight_grads

    # Ensure weights stay positive and sum to n_losses
    new_loss_weights = jnp.maximum(new_loss_weights, 1e-3)
    n_losses = loss_weights.shape[0]
    new_loss_weights = new_loss_weights * (n_losses / jnp.sum(new_loss_weights))

    return new_loss_weights, new_initial_grad_norms


def compute_loss_and_gradients_with_gradnorm(
    value_and_grad_fn: Callable,
    composite_loss: CompositeLoss,
    loss_context: LossContext,
    positions: Array,
    rotations: Array,
    net_virtual_nodes: Array,
    epoch: int,
    total_epochs: int,
    loss_weights: Array,
    initial_grad_norms: Array,
    grad_norm_lr: float = 0.025,
    grad_norm_alpha: float = 1.5,
) -> tuple[float, dict[str, Array], Array, Array, Array, Array, Array]:
    """
    Compute loss and gradients with GradNorm adaptive weighting.

    This function orchestrates the GradNorm algorithm:
    1. Compute individual loss gradient norms
    2. Update loss weights based on gradient balance
    3. Compute total loss and gradients with updated weights

    Args:
        value_and_grad_fn: Function returning ((loss, breakdown), (grad_pos, grad_rot, grad_vn)).
        composite_loss: Composite loss with multiple terms.
        loss_context: Context with netlist, board, etc.
        positions: Current positions (N, 2).
        rotations: Current rotations (N, 4) one-hot.
        net_virtual_nodes: Current virtual nodes (M, 2).
        epoch: Current epoch.
        total_epochs: Total epochs.
        loss_weights: Current dynamic weights (L,).
        initial_grad_norms: Initial gradient norms (L,).
        grad_norm_lr: Learning rate for weight updates.
        grad_norm_alpha: Asymmetry parameter.

    Returns:
        Tuple of (loss, breakdown, grad_pos, grad_rot, grad_vn, new_loss_weights, new_initial_grad_norms).
    """
    # Compute individual gradient norms
    current_grad_norms = compute_individual_loss_gradient_norms(
        composite_loss, loss_context, positions, rotations, epoch, total_epochs
    )

    # Update loss weights using GradNorm
    new_loss_weights, new_initial_grad_norms = update_gradnorm_weights(
        loss_weights,
        current_grad_norms,
        initial_grad_norms,
        epoch,
        learning_rate=grad_norm_lr,
        alpha=grad_norm_alpha,
    )

    # Compute total loss and gradients with current weights
    (loss, breakdown), (grad_pos, grad_rot, grad_vn) = value_and_grad_fn(
        positions, rotations, net_virtual_nodes, epoch, total_epochs, loss_weights
    )

    return loss, breakdown, grad_pos, grad_rot, grad_vn, new_loss_weights, new_initial_grad_norms
