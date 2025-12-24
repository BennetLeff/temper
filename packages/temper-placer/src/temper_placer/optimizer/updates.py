"""
Composable update functions for training step decomposition.

This module provides reusable, composable operations that can be combined
to construct a training step. Each function has a single responsibility and
can be tested independently.
"""

from __future__ import annotations

from typing import Any

import jax.numpy as jnp
import optax
from jax import Array

from temper_placer.losses.base import LossContext


def inject_learning_rate(
    opt_state: Any,
    learning_rate: float,
) -> Any:
    """
    Inject current learning rate into optimizer state.

    Args:
        opt_state: Optimizer state with hyperparams.
        learning_rate: Learning rate to inject.

    Returns:
        Updated optimizer state.
    """
    return opt_state._replace(
        hyperparams={**opt_state.hyperparams, "learning_rate": learning_rate}
    )


def apply_adaptive_overlap_weighting(
    grad_pos: Array,
    grad_rot: Array,
    overlap_weights: Array,
) -> tuple[Array, Array]:
    """
    Apply per-component adaptive overlap weighting to gradients.

    Overlap weights are computed externally based on colliding components
    and ramped up during training to focus optimization on problematic areas.

    Args:
        grad_pos: Position gradients (N, 2).
        grad_rot: Rotation gradients (N, 4).
        overlap_weights: Per-component weights (N,).

    Returns:
        Tuple of (weighted_grad_pos, weighted_grad_rot).
    """
    weighted_grad_pos = grad_pos * overlap_weights[:, None]
    weighted_grad_rot = grad_rot * overlap_weights[:, None]
    return weighted_grad_pos, weighted_grad_rot


def apply_centrality_scaling(
    grad_pos: Array,
    grad_rot: Array,
    centrality: Array,
    priority_scale: float = 1.0,
) -> tuple[Array, Array]:
    """
    Apply centrality-based gradient scaling (Inertia/Priority).

    Hub components (high centrality) receive lower gradient scaling, while
    leaf components (low centrality) receive higher scaling. This implements
    an "inertia" effect where hubs are more resistant to movement.

    Args:
        grad_pos: Position gradients (N, 2).
        grad_rot: Rotation gradients (N, 4).
        centrality: Component centrality scores (N,).
        priority_scale: Maximum scaling for leaf components (>1.0 to enable).

    Returns:
        Tuple of (scaled_grad_pos, scaled_grad_rot).
    """
    if centrality.shape[0] == 0 or priority_scale <= 1.0:
        return grad_pos, grad_rot

    # Normalize centrality to [0, 1]
    c_min = jnp.min(centrality)
    c_max = jnp.max(centrality)
    c_range = jnp.where(c_max - c_min < 1e-10, 1.0, c_max - c_min)
    normalized_c = (centrality - c_min) / c_range

    # Invert: hubs (normalized_c=1) get scale 1.0, leaves (normalized_c=0) get priority_scale
    grad_scale = 1.0 + (priority_scale - 1.0) * (1.0 - normalized_c)

    scaled_grad_pos = grad_pos * grad_scale[:, None]
    scaled_grad_rot = grad_rot * grad_scale[:, None]

    return scaled_grad_pos, scaled_grad_rot


def clamp_positions_to_board(
    positions: Array,
    board_bounds: Array,
) -> Array:
    """
    Hard clamp positions to board boundaries.

    Args:
        positions: Component positions (N, 2).
        board_bounds: Board bounds as [x_min, y_min, x_max, y_max].

    Returns:
        Clamped positions (N, 2).
    """
    return jnp.clip(
        positions,
        min=board_bounds[:2],
        max=board_bounds[2:],
    )


def apply_fixed_component_constraint(
    new_positions: Array,
    old_positions: Array,
    new_rotation_logits: Array,
    old_rotation_logits: Array,
    fixed_mask: Array,
) -> tuple[Array, Array]:
    """
    Ensure fixed components don't move or rotate.

    Args:
        new_positions: Updated positions (N, 2).
        old_positions: Previous positions (N, 2).
        new_rotation_logits: Updated rotation logits (N, 4).
        old_rotation_logits: Previous rotation logits (N, 4).
        fixed_mask: Boolean mask for fixed components (N,).

    Returns:
        Tuple of (constrained_positions, constrained_rotation_logits).
    """
    constrained_positions = jnp.where(
        fixed_mask[:, None],
        old_positions,
        new_positions,
    )
    constrained_rotation_logits = jnp.where(
        fixed_mask[:, None],
        old_rotation_logits,
        new_rotation_logits,
    )
    return constrained_positions, constrained_rotation_logits


def zero_fixed_component_optimizer_state(
    opt_state: Any,
    fixed_mask: Array,
) -> Any:
    """
    Zero out optimizer momentum and variance for fixed components.

    Prevents drift in optimizer state for components that shouldn't move.
    Only applies to Adam-like optimizers with 'mu' and 'nu' state.

    Args:
        opt_state: Optimizer state (Adam or similar).
        fixed_mask: Boolean mask for fixed components (N,).

    Returns:
        Updated optimizer state with zeroed fixed component state.
    """
    if hasattr(opt_state, 'mu'):
        return opt_state._replace(
            mu=jnp.where(fixed_mask[:, None], 0.0, opt_state.mu),
            nu=jnp.where(fixed_mask[:, None], 0.0, opt_state.nu),
        )
    return opt_state


def update_position_ema(
    new_positions: Array,
    old_positions: Array,
    old_ema: float,
    alpha: float = 0.9,
) -> float:
    """
    Update exponential moving average of position delta.

    Used for convergence detection and jiggle/perturbation logic.

    Args:
        new_positions: Updated positions (N, 2).
        old_positions: Previous positions (N, 2).
        old_ema: Previous EMA value.
        alpha: EMA smoothing factor (default 0.9).

    Returns:
        New EMA value.
    """
    update_norm = jnp.linalg.norm(new_positions - old_positions)
    return alpha * old_ema + (1.0 - alpha) * update_norm


def update_parameters_with_optimizer(
    params: Array,
    gradients: Array,
    optimizer: optax.GradientTransformation,
    opt_state: Any,
) -> tuple[Array, Any]:
    """
    Apply optimizer update to parameters.

    Generic wrapper around optax update/apply pattern.

    Args:
        params: Current parameters.
        gradients: Gradients w.r.t. parameters.
        optimizer: Optax gradient transformation.
        opt_state: Optimizer state.

    Returns:
        Tuple of (new_params, new_opt_state).
    """
    updates, new_opt_state = optimizer.update(gradients, opt_state, params)
    new_params = optax.apply_updates(params, updates)
    return new_params, new_opt_state
