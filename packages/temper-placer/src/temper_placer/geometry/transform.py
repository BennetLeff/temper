"""
Rotation transforms — Rust-backed via temper_geometry.

This module provides rotation operations for PCB component orientations.
All functions delegate to the temper_geometry Rust crate which uses
radians for rotation representation.
"""

import temper_geometry as _tg

# =============================================================================
# Rotation Matrices and Core Rotation
# =============================================================================

get_rotation_matrix = _tg.get_rotation_matrix
rotate_point = _tg.rotate_point
rotate_points = _tg.rotate_points

# =============================================================================
# Rectangle and Bounds Rotation
# =============================================================================

get_rotated_bounds = _tg.get_rotated_bounds
rotate_rectangle_corners = _tg.rotate_rectangle_corners
get_rotated_aabb = _tg.get_rotated_aabb

# =============================================================================
# Pin Position Transforms
# =============================================================================

transform_pin_position = _tg.transform_pin_position
transform_pin_positions = _tg.transform_pin_positions

# =============================================================================
# Batch Operations
# =============================================================================

batch_get_rotated_bounds = _tg.batch_get_rotated_bounds
batch_rotate_points = _tg.batch_rotate_points

# =============================================================================
# Utility Functions (non-collapsible: have Python-side default logic)
# =============================================================================


def rotation_index_to_onehot(idx, n_angles=4):
    """Convert rotation index (0-3) to one-hot vector.

    Args:
        idx: Rotation index
        n_angles: Number of discrete angles (default 4)

    Returns:
        One-hot vector as list
    """
    return _tg.rotation_index_to_onehot(idx, n_angles)


def rotation_degrees_to_onehot(deg, allowed=None):
    """Convert rotation in degrees to one-hot vector.

    Args:
        deg: Rotation in degrees
        allowed: List of allowed angles in degrees (default [0, 90, 180, 270])

    Returns:
        One-hot vector
    """
    if allowed is None:
        allowed = [0.0, 90.0, 180.0, 270.0]
    return _tg.rotation_degrees_to_onehot(deg, allowed)


def onehot_to_rotation_degrees(onehot, allowed=None):
    """Convert one-hot rotation vector to degrees.

    Args:
        onehot: One-hot or soft rotation vector
        allowed: List of allowed angles in degrees (default [0, 90, 180, 270])

    Returns:
        Rotation in degrees
    """
    if allowed is None:
        allowed = [0.0, 90.0, 180.0, 270.0]
    return _tg.onehot_to_rotation_degrees(onehot, allowed)


def onehot_to_rotation_radians(onehot, allowed_rad=None):
    """Convert one-hot rotation vector to radians.

    Args:
        onehot: One-hot or soft rotation vector
        allowed_rad: List of allowed angles in radians

    Returns:
        Rotation in radians
    """
    if allowed_rad is None:
        allowed_rad = [0.0, 1.5707963267948966, 3.141592653589793, 4.71238898038469]
    return _tg.onehot_to_rotation_radians(onehot, allowed_rad)


# =============================================================================
# Gumbel-Softmax Sampling
# =============================================================================

gumbel_softmax = _tg.gumbel_softmax
sample_rotation = _tg.sample_rotation
sample_rotation_batch = _tg.sample_rotation_batch
