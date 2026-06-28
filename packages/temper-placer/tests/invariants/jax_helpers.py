"""JAX-specific invariant assertion helpers.

These helpers verify properties of JAX-compiled or JAX-differentiable
functions: gradient finiteness, pytree compatibility, clip idempotence.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import jax
import jax.numpy as jnp


def assert_gradient_finite(
    loss_fn: Callable[..., Any],
    positions: jnp.ndarray,
    rotations: jnp.ndarray,
    context: Any,
    *,
    name: str = "",
    **kwargs: Any,
) -> None:
    """Theorem: The gradient of the loss function with respect to
    positions contains no NaN or Inf values for valid inputs.

    Args:
        loss_fn: Loss function whose gradient is checked
        positions: (N, 2) component positions
        rotations: (N, 4) soft one-hot rotation indicators
        context: LossContext or equivalent
        name: Human-readable name for the loss
        **kwargs: Additional keyword arguments passed to loss_fn

    Raises:
        AssertionError: If gradient contains NaN or Inf.
    """
    grad_fn = jax.grad(
        lambda p: loss_fn(p, rotations, context, **kwargs).value
    )
    grads = grad_fn(positions)
    label = name or loss_fn.__class__.__name__
    assert not jnp.any(jnp.isnan(grads)), (
        f"{label}: gradient contains NaN values"
    )
    assert not jnp.any(jnp.isinf(grads)), (
        f"{label}: gradient contains Inf values"
    )


def assert_loss_context_is_pytree(context: Any) -> None:
    """Theorem: LossContext is a valid JAX pytree — it can be traversed
    by jax.tree_util without raising.

    Args:
        context: LossContext or equivalent to check

    Raises:
        AssertionError: If tree traversal raises or returns empty.
    """
    leaves = jax.tree_util.tree_leaves(context)
    assert len(leaves) > 0, "LossContext has no JAX-visible leaves"


def assert_clip_idempotent(
    x: jnp.ndarray,
    bounds: jnp.ndarray,
) -> None:
    """Theorem: jnp.clip is idempotent — clipping twice = clipping once.

    Args:
        x: (N, 2) positions to clip
        bounds: (4,) array [x_min, y_min, x_max, y_max]

    Raises:
        AssertionError: If clipping twice produces different result.
    """
    once = jnp.clip(x, min=bounds[:2], max=bounds[2:])
    twice = jnp.clip(once, min=bounds[:2], max=bounds[2:])
    assert jnp.allclose(once, twice), "jnp.clip is not idempotent"
