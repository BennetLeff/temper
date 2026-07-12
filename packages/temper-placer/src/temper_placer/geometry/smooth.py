"""
Smooth approximations — Rust-backed via temper_geometry.

This module provides differentiable approximations to min, max, relu, and
related functions. These are essential for computing differentiable HPWL
(Half-Perimeter Wire Length) and other placement metrics.

All functions delegate to the temper_geometry Rust crate.
"""
import temper_geometry as _tg


# =============================================================================
# Smooth Maximum Functions
# =============================================================================


def smooth_max(a, b, alpha=10.0):
    """Smooth approximation of element-wise max(a, b).

    As alpha → inf, smooth_max → max(a, b)

    Args:
        a: First input
        b: Second input
        alpha: Smoothing parameter. Higher = sharper approximation.

    Returns:
        Smooth maximum of a and b
    """
    return _tg.smooth_max(a, b, alpha)


def smooth_max_axis(arr, alpha=10.0):
    """Smooth approximation of max along an axis.

    Args:
        arr: Input array
        alpha: Smoothing parameter

    Returns:
        Smooth max along axis
    """
    return _tg.smooth_max_axis(arr, alpha)


def smooth_max_pair(a, b, alpha=10.0):
    """Smooth approximation of element-wise max(a, b).

    Args:
        a: First input
        b: Second input
        alpha: Smoothing parameter

    Returns:
        Smooth maximum of a and b (element-wise)
    """
    return _tg.smooth_max_pair(a, b, alpha)


# =============================================================================
# Smooth Minimum Functions
# =============================================================================


def smooth_min(a, b, alpha=10.0):
    """Smooth approximation of element-wise min(a, b).

    As alpha → inf, smooth_min → min(a, b)

    Args:
        a: First input
        b: Second input
        alpha: Smoothing parameter. Higher = sharper approximation.

    Returns:
        Smooth minimum of a and b
    """
    return _tg.smooth_min(a, b, alpha)


def smooth_min_axis(arr, alpha=10.0):
    """Smooth approximation of min along an axis.

    Args:
        arr: Input array
        alpha: Smoothing parameter

    Returns:
        Smooth min along axis
    """
    return _tg.smooth_min_axis(arr, alpha)


def smooth_min_pair(a, b, alpha=10.0):
    """Smooth approximation of element-wise min(a, b).

    Args:
        a: First input
        b: Second input
        alpha: Smoothing parameter

    Returns:
        Smooth minimum of a and b (element-wise)
    """
    return _tg.smooth_min_pair(a, b, alpha)


# =============================================================================
# Smooth ReLU and Related Activation Functions
# =============================================================================


def smooth_relu(x, alpha=10.0):
    """Smooth approximation of ReLU: max(0, x).

    Uses softplus: log(1 + exp(alpha * x)) / alpha

    Args:
        x: Input
        alpha: Smoothing parameter. Higher = sharper transition at 0.

    Returns:
        Smooth ReLU applied element-wise
    """
    return _tg.smooth_relu(x, alpha)


def smooth_relu_penalty(x, margin=0.0, alpha=10.0):
    """Smooth penalty for constraint violations: max(0, x - margin)^2.

    Args:
        x: Input (values above margin are violations)
        margin: Threshold for violations
        alpha: Smoothing parameter

    Returns:
        Squared smooth ReLU applied element-wise
    """
    return _tg.smooth_relu_penalty(x, margin, alpha)


def smooth_leaky_relu(x, alpha=10.0, negative_slope=0.01):
    """Smooth approximation of leaky ReLU.

    Args:
        x: Input
        alpha: Smoothing parameter for the transition
        negative_slope: Slope for x < 0 (default 0.01)

    Returns:
        Smooth leaky ReLU applied element-wise
    """
    return _tg.smooth_leaky_relu(x, alpha, negative_slope)


# =============================================================================
# Smooth Absolute Value and Clipping
# =============================================================================


def smooth_abs(x, alpha=10.0):
    """Smooth approximation of |x|.

    Args:
        x: Input
        alpha: Controls smoothness at x=0. Higher = sharper.

    Returns:
        Smooth absolute value applied element-wise
    """
    return _tg.smooth_abs(x, alpha)


def smooth_clip(x, min_val, max_val, alpha=10.0):
    """Smooth approximation of clip(x, min_val, max_val).

    Args:
        x: Input
        min_val: Minimum value
        max_val: Maximum value
        alpha: Smoothing parameter

    Returns:
        Smoothly clipped values
    """
    return _tg.smooth_clip(x, min_val, max_val, alpha)


def smooth_step(x, alpha=10.0):
    """Smooth approximation of step function (Heaviside).

    Args:
        x: Input
        alpha: Controls transition sharpness

    Returns:
        Smooth step function applied element-wise (values in [0, 1])
    """
    return _tg.smooth_step(x, alpha)


# =============================================================================
# HPWL-Specific Functions
# =============================================================================


def hpwl_smooth(points, alpha=10.0):
    """Compute smooth Half-Perimeter Wire Length.

    HPWL = (max_x - min_x) + (max_y - min_y)

    Args:
        points: Flat list of [x1, y1, x2, y2, ...] coordinates
        alpha: Smoothing parameter

    Returns:
        Smooth HPWL value
    """
    return _tg.hpwl_smooth(points, alpha)


def weighted_average_smooth(values, weights, alpha=1.0):
    """Compute weighted average with temperature-controlled softmax weights.

    Args:
        values: Values to average
        weights: Raw weights (will be softmax-normalized)
        alpha: Temperature parameter (lower = sharper selection)

    Returns:
        Weighted average
    """
    return _tg.weighted_average_smooth(values, weights, alpha)


# =============================================================================
# Annealing Schedules
# =============================================================================


def get_alpha_schedule(start_alpha, end_alpha, epochs):
    """Compute alpha value for current epoch using exponential annealing.

    Args:
        start_alpha: Starting alpha value
        end_alpha: Final alpha value
        epochs: Total number of epochs

    Returns:
        Alpha value for current epoch
    """
    return _tg.get_alpha_schedule(start_alpha, end_alpha, epochs)


def get_beta_schedule(start_beta, end_beta, epochs):
    """Compute beta value for current epoch using exponential annealing.

    Args:
        start_beta: Starting beta value
        end_beta: Final beta value
        epochs: Total number of epochs

    Returns:
        Beta value for current epoch
    """
    return _tg.get_beta_schedule(start_beta, end_beta, epochs)
