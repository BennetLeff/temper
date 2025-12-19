"""
Smooth approximations for non-differentiable operations.

This module provides differentiable approximations to min, max, relu, and
related functions using LogSumExp and other techniques. These are essential
for computing differentiable HPWL (Half-Perimeter Wire Length) and other
placement metrics.

The smoothness is controlled by alpha/beta parameters:
- Higher alpha/beta = sharper approximation (closer to true min/max)
- Lower alpha/beta = smoother gradients (better for early training)

These parameters should be annealed during training: start low for exploration,
increase for refinement.
"""

import jax.numpy as jnp
from jax import Array
from jax.scipy.special import logsumexp

# =============================================================================
# Smooth Maximum Functions
# =============================================================================


def smooth_max(x: Array, alpha: float = 10.0) -> Array:
    """
    Smooth approximation of max(x) using LogSumExp.

    As alpha → ∞, smooth_max → max(x)

    The LogSumExp trick:
        max(x) ≈ (1/alpha) * log(sum(exp(alpha * x)))

    This is always >= max(x), with equality as alpha → ∞.

    Args:
        x: Input array of any shape. Max is computed over flattened array.
        alpha: Smoothing parameter. Higher = sharper approximation.
               Recommended range: 1.0 (smooth) to 100.0 (sharp)

    Returns:
        Smooth maximum value (scalar)

    Gradient behavior:
        When alpha is low, gradients are distributed across all elements.
        When alpha is high, gradients concentrate on the maximum element.
    """
    # Flatten if needed
    x_flat = x.ravel()
    return logsumexp(alpha * x_flat) / alpha


def smooth_max_axis(x: Array, alpha: float = 10.0, axis: int = -1) -> Array:
    """
    Smooth approximation of max along a specific axis.

    Args:
        x: Input array
        alpha: Smoothing parameter
        axis: Axis along which to compute max

    Returns:
        Array with one fewer dimension (max computed along axis)
    """
    return logsumexp(alpha * x, axis=axis) / alpha


def smooth_max_pair(a: Array, b: Array, alpha: float = 10.0) -> Array:
    """
    Smooth approximation of max(a, b) for two scalars or arrays.

    Args:
        a: First input
        b: Second input
        alpha: Smoothing parameter

    Returns:
        Smooth maximum of a and b (element-wise for arrays)
    """
    # Stack and compute logsumexp
    stacked = jnp.stack([a, b], axis=-1)
    return logsumexp(alpha * stacked, axis=-1) / alpha


# =============================================================================
# Smooth Minimum Functions
# =============================================================================


def smooth_min(x: Array, alpha: float = 10.0) -> Array:
    """
    Smooth approximation of min(x) using LogSumExp.

    Uses the identity: min(x) = -max(-x)

    As alpha → ∞, smooth_min → min(x)

    Args:
        x: Input array of any shape. Min is computed over flattened array.
        alpha: Smoothing parameter. Higher = sharper approximation.

    Returns:
        Smooth minimum value (scalar)

    Gradient behavior:
        When alpha is low, gradients are distributed across all elements.
        When alpha is high, gradients concentrate on the minimum element.
    """
    x_flat = x.ravel()
    return -logsumexp(-alpha * x_flat) / alpha


def smooth_min_axis(x: Array, alpha: float = 10.0, axis: int = -1) -> Array:
    """
    Smooth approximation of min along a specific axis.

    Args:
        x: Input array
        alpha: Smoothing parameter
        axis: Axis along which to compute min

    Returns:
        Array with one fewer dimension (min computed along axis)
    """
    return -logsumexp(-alpha * x, axis=axis) / alpha


def smooth_min_pair(a: Array, b: Array, alpha: float = 10.0) -> Array:
    """
    Smooth approximation of min(a, b) for two scalars or arrays.

    Args:
        a: First input
        b: Second input
        alpha: Smoothing parameter

    Returns:
        Smooth minimum of a and b (element-wise for arrays)
    """
    stacked = jnp.stack([a, b], axis=-1)
    return -logsumexp(-alpha * stacked, axis=-1) / alpha


# =============================================================================
# Smooth ReLU and Related Activation Functions
# =============================================================================


def smooth_relu(x: Array, beta: float = 10.0) -> Array:
    """
    Smooth approximation of ReLU: max(0, x).

    Uses softplus: log(1 + exp(beta * x)) / beta

    As beta → ∞, smooth_relu → relu(x)

    Args:
        x: Input array
        beta: Smoothing parameter. Higher = sharper transition at 0.
              Recommended range: 1.0 (smooth) to 50.0 (sharp)

    Returns:
        Smooth ReLU applied element-wise

    Gradient behavior:
        - For x << 0: gradient ≈ 0
        - For x >> 0: gradient ≈ 1
        - For x ≈ 0: smooth transition (sigmoid-like)
    """
    # Use softplus for numerical stability
    # softplus(x) = log(1 + exp(x))
    # smooth_relu(x, beta) = softplus(beta * x) / beta
    return jnp.logaddexp(0.0, beta * x) / beta


def smooth_relu_penalty(x: Array, beta: float = 10.0) -> Array:
    """
    Smooth penalty for constraint violations: max(0, x)^2.

    Useful for penalizing positive violations while ignoring negative values.
    The squaring provides quadratic penalty growth.

    Args:
        x: Input array (positive values are violations)
        beta: Smoothing parameter

    Returns:
        Squared smooth ReLU applied element-wise
    """
    return smooth_relu(x, beta) ** 2


def smooth_leaky_relu(x: Array, negative_slope: float = 0.01, beta: float = 10.0) -> Array:
    """
    Smooth approximation of leaky ReLU.

    Args:
        x: Input array
        negative_slope: Slope for x < 0 (default 0.01)
        beta: Smoothing parameter for the transition

    Returns:
        Smooth leaky ReLU applied element-wise
    """
    return smooth_relu(x, beta) + negative_slope * smooth_relu(-x, beta) * (-1)


# =============================================================================
# Smooth Absolute Value and Clipping
# =============================================================================


def smooth_abs(x: Array, beta: float = 10.0) -> Array:
    """
    Smooth approximation of |x|.

    Uses: |x| = max(x, -x) ≈ smooth_max([x, -x])

    Alternatively uses: sqrt(x^2 + epsilon) for simplicity

    Args:
        x: Input array
        beta: Controls smoothness at x=0. Higher = sharper.

    Returns:
        Smooth absolute value applied element-wise
    """
    # Using sqrt(x^2 + epsilon) where epsilon = 1/beta^2
    epsilon = 1.0 / (beta * beta)
    return jnp.sqrt(x * x + epsilon)


def smooth_clip(x: Array, min_val: float, max_val: float, beta: float = 10.0) -> Array:
    """
    Smooth approximation of clip(x, min_val, max_val).

    Args:
        x: Input array
        min_val: Minimum value
        max_val: Maximum value
        beta: Smoothing parameter

    Returns:
        Smoothly clipped values
    """
    # clip(x) = min(max(x, min_val), max_val)
    clipped_low = smooth_max_pair(x, jnp.full_like(x, min_val), beta)
    clipped_both = smooth_min_pair(clipped_low, jnp.full_like(x, max_val), beta)
    return clipped_both


def smooth_step(x: Array, edge: float = 0.0, beta: float = 10.0) -> Array:
    """
    Smooth approximation of step function (Heaviside).

    Returns ≈1 for x > edge, ≈0 for x < edge, with smooth transition.
    Uses sigmoid function.

    Args:
        x: Input array
        edge: Location of step (default 0)
        beta: Controls transition sharpness

    Returns:
        Smooth step function applied element-wise (values in [0, 1])
    """
    import jax.nn

    return jax.nn.sigmoid(beta * (x - edge))


# =============================================================================
# HPWL-Specific Functions
# =============================================================================


def hpwl_smooth(pin_positions: Array, alpha: float = 10.0) -> Array:
    """
    Compute smooth Half-Perimeter Wire Length for a set of pin positions.

    HPWL = (max_x - min_x) + (max_y - min_y)

    This is the standard metric for estimating wirelength in placement.

    Args:
        pin_positions: Array of shape (N, 2) with pin (x, y) coordinates
        alpha: Smoothing parameter for min/max approximation

    Returns:
        Smooth HPWL value (scalar)
    """
    # Extract x and y coordinates
    x_coords = pin_positions[:, 0]
    y_coords = pin_positions[:, 1]

    # Compute smooth bounding box
    x_max = smooth_max(x_coords, alpha)
    x_min = smooth_min(x_coords, alpha)
    y_max = smooth_max(y_coords, alpha)
    y_min = smooth_min(y_coords, alpha)

    # Half-perimeter
    return (x_max - x_min) + (y_max - y_min)


def weighted_average_smooth(values: Array, weights: Array, temperature: float = 1.0) -> Array:
    """
    Compute weighted average with temperature-controlled softmax weights.

    As temperature → 0, this approaches a hard selection of the highest-weighted value.
    As temperature → ∞, this approaches uniform averaging.

    Useful for differentiable selection among discrete options.

    Args:
        values: Values to average
        weights: Raw weights (will be softmax-normalized)
        temperature: Controls softness of weighting

    Returns:
        Weighted average (scalar)
    """
    import jax.nn

    soft_weights = jax.nn.softmax(weights / temperature)
    return jnp.sum(values * soft_weights)


# =============================================================================
# Annealing Schedules
# =============================================================================


def get_alpha_schedule(
    epoch: int,
    total_epochs: int,
    initial_alpha: float = 1.0,
    final_alpha: float = 50.0,
) -> float:
    """
    Compute alpha value for current epoch using exponential annealing.

    Starts with low alpha (smooth) and increases to high alpha (sharp)
    as training progresses.

    Args:
        epoch: Current epoch number
        total_epochs: Total number of epochs
        initial_alpha: Starting alpha value
        final_alpha: Final alpha value

    Returns:
        Alpha value for current epoch
    """
    # Exponential schedule
    progress = epoch / max(total_epochs - 1, 1)
    return initial_alpha * (final_alpha / initial_alpha) ** progress


def get_beta_schedule(
    epoch: int,
    total_epochs: int,
    initial_beta: float = 1.0,
    final_beta: float = 50.0,
) -> float:
    """
    Compute beta value for current epoch using exponential annealing.

    Same as alpha schedule, but named separately for clarity when used
    for different purposes (e.g., ReLU smoothing vs min/max smoothing).

    Args:
        epoch: Current epoch number
        total_epochs: Total number of epochs
        initial_beta: Starting beta value
        final_beta: Final beta value

    Returns:
        Beta value for current epoch
    """
    progress = epoch / max(total_epochs - 1, 1)
    return initial_beta * (final_beta / initial_beta) ** progress
