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

smooth_max = _tg.smooth_max
smooth_max_axis = _tg.smooth_max_axis
smooth_max_pair = _tg.smooth_max_pair

# =============================================================================
# Smooth Minimum Functions
# =============================================================================

smooth_min = _tg.smooth_min
smooth_min_axis = _tg.smooth_min_axis
smooth_min_pair = _tg.smooth_min_pair

# =============================================================================
# Smooth ReLU and Related Activation Functions
# =============================================================================

smooth_relu = _tg.smooth_relu
smooth_relu_penalty = _tg.smooth_relu_penalty


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

smooth_abs = _tg.smooth_abs
smooth_clip = _tg.smooth_clip
smooth_step = _tg.smooth_step

# =============================================================================
# HPWL-Specific Functions
# =============================================================================

hpwl_smooth = _tg.hpwl_smooth
weighted_average_smooth = _tg.weighted_average_smooth

# =============================================================================
# Annealing Schedules
# =============================================================================

get_alpha_schedule = _tg.get_alpha_schedule
get_beta_schedule = _tg.get_beta_schedule
