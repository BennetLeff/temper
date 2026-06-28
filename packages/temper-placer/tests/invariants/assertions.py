"""Mathematical invariant assertion helpers for property-based tests.

Each function states a theorem in its docstring and proves it via assertion.
Designed to be imported into test files that use either plain pytest or Hypothesis.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import jax.numpy as jnp
import pytest


def assert_zero_when_no_violation(
    loss_fn: Callable[..., Any],
    positions: jnp.ndarray,
    rotations: jnp.ndarray,
    context: Any,
    *,
    name: str = "",
    **kwargs: Any,
) -> None:
    """Theorem: If no components violate the loss's defining constraint,
    the loss value must be zero.

    Args:
        loss_fn: Loss function to evaluate (BoundaryLoss, OverlapLoss, etc.)
        positions: (N, 2) component positions in a safe (non-violating) configuration
        rotations: (N, 4) soft one-hot rotation indicators
        context: LossContext or equivalent
        name: Human-readable name for the loss (used in failure messages)
        **kwargs: Additional keyword arguments passed to loss_fn

    Raises:
        AssertionError: If loss value is not approximately zero.
    """
    result = loss_fn(positions, rotations, context, **kwargs)
    label = name or loss_fn.__class__.__name__
    assert float(result.value) == pytest.approx(0.0, abs=1e-4), (
        f"{label}: expected zero loss for non-violating configuration, "
        f"got {float(result.value)}"
    )


def assert_positive_when_violation(
    loss_fn: Callable[..., Any],
    positions: jnp.ndarray,
    rotations: jnp.ndarray,
    context: Any,
    *,
    name: str = "",
    **kwargs: Any,
) -> None:
    """Theorem: If at least one component violates the loss's defining
    constraint, the loss value must be strictly positive.

    Args:
        loss_fn: Loss function to evaluate
        positions: (N, 2) component positions inducing a violation
        rotations: (N, 4) soft one-hot rotation indicators
        context: LossContext or equivalent
        name: Human-readable name for the loss
        **kwargs: Additional keyword arguments passed to loss_fn

    Raises:
        AssertionError: If loss value is not strictly positive.
    """
    result = loss_fn(positions, rotations, context, **kwargs)
    label = name or loss_fn.__class__.__name__
    assert float(result.value) > 0, (
        f"{label}: expected positive loss for violating configuration, "
        f"got {float(result.value)}"
    )


def assert_monotonic(
    loss_fn: Callable[..., Any],
    positions_near: jnp.ndarray,
    positions_far: jnp.ndarray,
    rotations: jnp.ndarray,
    context: Any,
    *,
    name: str = "",
    **kwargs: Any,
) -> None:
    """Theorem: For distance-based losses, increasing the violation
    distance produces strictly larger loss.

    Args:
        loss_fn: Loss function to evaluate
        positions_near: (N, 2) positions with a smaller violation
        positions_far: (N, 2) positions with a larger violation
        rotations: (N, 4) soft one-hot rotation indicators
        context: LossContext or equivalent
        name: Human-readable name for the loss
        **kwargs: Additional keyword arguments passed to loss_fn

    Raises:
        AssertionError: If loss at 'far' is not greater than loss at 'near'.
    """
    near_result = loss_fn(positions_near, rotations, context, **kwargs)
    far_result = loss_fn(positions_far, rotations, context, **kwargs)
    label = name or loss_fn.__class__.__name__
    assert float(far_result.value) > float(near_result.value), (
        f"{label}: loss at far distance ({float(far_result.value):.1f}) "
        f"should exceed loss at near distance ({float(near_result.value):.1f})"
    )


def assert_idempotent(
    loss_fn: Callable[..., Any],
    positions: jnp.ndarray,
    rotations: jnp.ndarray,
    context: Any,
    *,
    name: str = "",
    **kwargs: Any,
) -> None:
    """Theorem: Evaluating the same loss twice on identical inputs
    produces the same value (within floating-point tolerance).

    Args:
        loss_fn: Loss function to evaluate
        positions: (N, 2) component positions
        rotations: (N, 4) soft one-hot rotation indicators
        context: LossContext or equivalent
        name: Human-readable name for the loss
        **kwargs: Additional keyword arguments passed to loss_fn

    Raises:
        AssertionError: If two evaluations differ beyond tolerance.
    """
    r1 = loss_fn(positions, rotations, context, **kwargs)
    r2 = loss_fn(positions, rotations, context, **kwargs)
    label = name or loss_fn.__class__.__name__
    assert float(r1.value) == pytest.approx(float(r2.value), rel=1e-6), (
        f"{label}: idempotence violated — "
        f"first={float(r1.value)}, second={float(r2.value)}"
    )


def assert_empty_is_zero(
    loss_fn: Callable[..., Any],
    empty_positions: jnp.ndarray,
    empty_rotations: jnp.ndarray,
    context: Any,
    *,
    name: str = "",
    **kwargs: Any,
) -> None:
    """Theorem: When the input is empty (zero components), the loss
    must be zero.

    Args:
        loss_fn: Loss function to evaluate
        empty_positions: (0, 2) empty position array
        empty_rotations: (0, 4) empty rotation array
        context: LossContext or equivalent (may need empty components)
        name: Human-readable name for the loss
        **kwargs: Additional keyword arguments passed to loss_fn

    Raises:
        AssertionError: If loss value is not zero for empty input.
    """
    result = loss_fn(empty_positions, empty_rotations, context, **kwargs)
    label = name or loss_fn.__class__.__name__
    assert float(result.value) == pytest.approx(0.0, abs=1e-4), (
        f"{label}: expected zero loss for empty input, "
        f"got {float(result.value)}"
    )
