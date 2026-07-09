"""
Rotation transforms for discrete PCB component angles.

This module provides differentiable rotation operations for the four valid
PCB component orientations: 0°, 90°, 180°, 270°. These transforms are designed
to work with Gumbel-Softmax one-hot rotation vectors, enabling gradient flow
through discrete rotation selection.

Rotation encoding:
    One-hot vector of length 4: [0°, 90°, 180°, 270°]
    Example: [0, 1, 0, 0] = 90° rotation

All rotations are counter-clockwise around a center point.
"""

import math
from typing import TypeAlias

import numpy as np

Array: TypeAlias = np.ndarray  # numpy alias replacing JAX Array post-JAX retirement

from temper_placer.core.units import Degrees, DegreesArray, RadiansArray

# =============================================================================
# Rotation Matrices
# =============================================================================

# Pre-computed rotation matrices for 0°, 90°, 180°, 270° (counter-clockwise)
# Each matrix is 2x2: [[cos(θ), -sin(θ)], [sin(θ), cos(θ)]]
ROTATION_MATRICES = np.array(
    [
        [[1.0, 0.0], [0.0, 1.0]],  # 0°
        [[0.0, -1.0], [1.0, 0.0]],  # 90°
        [[-1.0, 0.0], [0.0, -1.0]],  # 180°
        [[0.0, 1.0], [-1.0, 0.0]],  # 270°
    ]
)

# Rotation angles in radians
ROTATION_ANGLES = np.array([0.0, math.pi / 2, math.pi, 3 * math.pi / 2])

# Rotation angles in degrees
ROTATION_ANGLES_DEG = np.array([0.0, 90.0, 180.0, 270.0])


# =============================================================================
# Core Rotation Functions
# =============================================================================


def get_rotation_matrix(rotation_onehot: Array) -> Array:
    """
    Get blended rotation matrix from one-hot (or soft) rotation vector.

    When using Gumbel-Softmax, rotation_onehot is soft (sums to 1 but not
    exactly one-hot). This function computes the weighted average of rotation
    matrices, enabling gradient flow.

    Args:
        rotation_onehot: One-hot vector of shape (4,) indicating rotation.
                        Can be soft (from Gumbel-Softmax) for differentiability.

    Returns:
        2x2 rotation matrix
    """
    # Weighted sum of rotation matrices
    # rotation_onehot: (4,), ROTATION_MATRICES: (4, 2, 2)
    # Result: (2, 2)
    return np.einsum("r,rij->ij", rotation_onehot, ROTATION_MATRICES)


def rotate_point(point: Array, rotation_onehot: Array, center: Array | None = None) -> Array:
    """
    Rotate a point around a center using one-hot rotation encoding.

    Args:
        point: Point to rotate as (x, y) array
        rotation_onehot: One-hot rotation vector (4,) for [0°, 90°, 180°, 270°]
        center: Center of rotation as (x, y) array. If None, rotates around origin.

    Returns:
        Rotated point as (x, y) array
    """
    if center is None:
        center = np.zeros(2)

    # Translate to origin
    point_centered = point - center

    # Get rotation matrix and apply
    rot_matrix = get_rotation_matrix(rotation_onehot)
    point_rotated = rot_matrix @ point_centered

    # Translate back
    return point_rotated + center


def rotate_points(points: Array, rotation_onehot: Array, center: Array | None = None) -> Array:
    """
    Rotate multiple points around a center.

    Args:
        points: Points to rotate as (N, 2) array
        rotation_onehot: One-hot rotation vector (4,)
        center: Center of rotation as (x, y) array. If None, rotates around origin.

    Returns:
        Rotated points as (N, 2) array
    """
    if center is None:
        center = np.zeros(2)

    # Translate to origin
    points_centered = points - center

    # Get rotation matrix and apply to all points
    rot_matrix = get_rotation_matrix(rotation_onehot)
    # points_centered: (N, 2), rot_matrix: (2, 2)
    # We need (N, 2) @ (2, 2).T = (N, 2)
    points_rotated = points_centered @ rot_matrix.T

    # Translate back
    return points_rotated + center


# =============================================================================
# Rectangle and Bounds Rotation
# =============================================================================


def get_rotated_bounds(width: float, height: float, rotation_onehot: Array) -> tuple[Array, Array]:
    """
    Get width and height after rotation.

    For 90° and 270° rotations, width and height are swapped.
    This function provides a differentiable way to compute the effective
    dimensions of a rotated axis-aligned bounding box.

    Args:
        width: Original width
        height: Original height
        rotation_onehot: One-hot rotation vector (4,) for [0°, 90°, 180°, 270°]

    Returns:
        Tuple of (rotated_width, rotated_height)
    """
    # For 0° and 180°: (width, height) stays same
    # For 90° and 270°: swap to (height, width)
    # Use one-hot to blend: [0°, 90°, 180°, 270°] -> [no_swap, swap, no_swap, swap]
    swap_weights = np.array([0.0, 1.0, 0.0, 1.0])
    swap_amount = np.dot(rotation_onehot, swap_weights)

    # Blend between (width, height) and (height, width)
    rotated_width = width * (1 - swap_amount) + height * swap_amount
    rotated_height = height * (1 - swap_amount) + width * swap_amount

    return rotated_width, rotated_height


def rotate_rectangle_corners(
    center: Array, width: float, height: float, rotation_onehot: Array
) -> Array:
    """
    Get corners of a rotated rectangle.

    Args:
        center: Rectangle center as (x, y) array
        width: Rectangle width (before rotation)
        height: Rectangle height (before rotation)
        rotation_onehot: One-hot rotation vector (4,)

    Returns:
        Array of shape (4, 2) with corner positions:
        [bottom-left, bottom-right, top-right, top-left] (all rotated)
    """
    half_w = width / 2.0
    half_h = height / 2.0

    # Corners relative to center (before rotation)
    corners = np.array(
        [
            [-half_w, -half_h],  # bottom-left
            [half_w, -half_h],  # bottom-right
            [half_w, half_h],  # top-right
            [-half_w, half_h],  # top-left
        ]
    )

    # Rotate corners around center (which is origin for relative coords)
    rot_matrix = get_rotation_matrix(rotation_onehot)
    corners_rotated = corners @ rot_matrix.T

    # Translate to actual center
    return corners_rotated + center


def get_rotated_aabb(
    center: Array, width: float, height: float, rotation_onehot: Array
) -> tuple[Array, Array]:
    """
    Get axis-aligned bounding box of a rotated rectangle.

    Args:
        center: Rectangle center as (x, y) array
        width: Rectangle width (before rotation)
        height: Rectangle height (before rotation)
        rotation_onehot: One-hot rotation vector (4,)

    Returns:
        Tuple of (min_corner, max_corner) as (x, y) arrays
    """
    corners = rotate_rectangle_corners(center, width, height, rotation_onehot)
    min_corner = np.min(corners, axis=0)
    max_corner = np.max(corners, axis=0)
    return min_corner, max_corner


# =============================================================================
# Pin Position Transforms
# =============================================================================


def transform_pin_position(
    pin_offset: Array, component_center: Array, rotation_onehot: Array
) -> Array:
    """
    Transform a pin position based on component center and rotation.

    Pin positions are typically specified as offsets from component center
    at 0° rotation. This function computes the actual world position.

    Args:
        pin_offset: Pin offset from component center at 0° as (x, y) array
        component_center: Component center position as (x, y) array
        rotation_onehot: Component rotation as one-hot vector (4,)

    Returns:
        World position of pin as (x, y) array
    """
    # Rotate the pin offset around origin (component center)
    rotated_offset = rotate_point(pin_offset, rotation_onehot, center=np.zeros(2))

    # Add component center to get world position
    return component_center + rotated_offset


def transform_pin_positions(
    pin_offsets: Array, component_center: Array, rotation_onehot: Array
) -> Array:
    """
    Transform multiple pin positions for a component.

    Args:
        pin_offsets: Pin offsets from component center at 0° as (N, 2) array
        component_center: Component center position as (x, y) array
        rotation_onehot: Component rotation as one-hot vector (4,)

    Returns:
        World positions of pins as (N, 2) array
    """
    # Rotate all pin offsets around origin
    rotated_offsets = rotate_points(pin_offsets, rotation_onehot, center=np.zeros(2))

    # Add component center to get world positions
    return rotated_offsets + component_center


# =============================================================================
# Batch Operations
# =============================================================================


def batch_get_rotated_bounds(
    widths: Array, heights: Array, rotation_onehots: Array
) -> tuple[Array, Array]:
    """
    Get rotated bounds for multiple components.

    Args:
        widths: Array of shape (N,) with component widths
        heights: Array of shape (N,) with component heights
        rotation_onehots: Array of shape (N, 4) with rotation one-hot vectors

    Returns:
        Tuple of (rotated_widths, rotated_heights) each of shape (N,)
    """
    # Swap weights for each rotation: [0°, 90°, 180°, 270°] -> [0, 1, 0, 1]
    swap_weights = np.array([0.0, 1.0, 0.0, 1.0])

    # Compute swap amount for each component
    swap_amounts = rotation_onehots @ swap_weights  # (N,)

    # Blend between original and swapped dimensions
    rotated_widths = widths * (1 - swap_amounts) + heights * swap_amounts
    rotated_heights = heights * (1 - swap_amounts) + widths * swap_amounts

    return rotated_widths, rotated_heights


def batch_rotate_points(points: Array, rotation_onehots: Array, centers: Array) -> Array:
    """
    Rotate multiple sets of points, each with different rotation and center.

    This is useful for rotating pin positions for multiple components at once.

    Args:
        points: Array of shape (N, M, 2) - N components, M points each
        rotation_onehots: Array of shape (N, 4) - rotation for each component
        centers: Array of shape (N, 2) - rotation center for each component

    Returns:
        Rotated points as (N, M, 2) array
    """
    # Get rotation matrices for all components: (N, 2, 2)
    rot_matrices = np.einsum("nr,rij->nij", rotation_onehots, ROTATION_MATRICES)

    # Center the points: (N, M, 2)
    points_centered = points - centers[:, None, :]

    # Apply rotation: (N, M, 2) @ (N, 2, 2).T -> (N, M, 2)
    # Using einsum: points[n, m, i] * rot_matrices[n, j, i] -> result[n, m, j]
    points_rotated = np.einsum("nmi,nji->nmj", points_centered, rot_matrices)

    # Translate back
    return points_rotated + centers[:, None, :]


# =============================================================================
# Utility Functions
# =============================================================================


def rotation_index_to_onehot(index: int) -> Array:
    """
    Convert rotation index (0-3) to one-hot vector.

    Args:
        index: Rotation index (0=0°, 1=90°, 2=180°, 3=270°)

    Returns:
        One-hot vector of shape (4,)
    """
    return np.eye(4)[index]


def rotation_degrees_to_onehot(degrees: float | Degrees | DegreesArray) -> Array:
    """
    Convert rotation in degrees to one-hot vector.

    Rounds to nearest valid rotation (0°, 90°, 180°, 270°).

    Args:
        degrees: Rotation in degrees

    Returns:
        One-hot vector of shape (4,)
    """
    # Normalize to 0-360
    degrees_val = np.array(degrees) % 360.0

    # Find nearest valid rotation
    index = np.round(degrees_val / 90.0).astype(np.int32) % 4
    if index.ndim == 0:
        return rotation_index_to_onehot(int(index))
    return np.eye(4)[index]


def onehot_to_rotation_degrees(rotation_onehot: Array) -> DegreesArray:
    """
    Convert one-hot rotation vector to degrees.

    For soft one-hot vectors (from Gumbel-Softmax), returns weighted average.

    Args:
        rotation_onehot: One-hot or soft rotation vector (4,)

    Returns:
        Rotation in degrees
    """
    return np.dot(rotation_onehot, ROTATION_ANGLES_DEG)


def onehot_to_rotation_radians(rotation_onehot: Array) -> RadiansArray:
    """
    Convert one-hot rotation vector to radians.

    Args:
        rotation_onehot: One-hot or soft rotation vector (4,)

    Returns:
        Rotation in radians
    """
    return np.dot(rotation_onehot, ROTATION_ANGLES)


# =============================================================================
# Gumbel-Softmax Sampling for Differentiable Discrete Rotation
# =============================================================================


def gumbel_softmax(
    logits: Array,
    key: Array,
    temperature: float = 1.0,
    hard: bool = True,
) -> Array:
    """DEPRECATED: JAX Gumbel-Softmax sampling removed (JAX retirement).

    This was a differentiable discrete-sampling primitive for the JAX
    gradient-descent placer, which no longer exists. Use the CP-SAT placer
    for discrete rotation decisions instead.
    """
    raise NotImplementedError(
        "gumbel_softmax removed (JAX retirement). "
        "Use the CP-SAT placer for discrete rotation decisions."
    )


def sample_rotation(
    logits: Array,
    key: Array,
    temperature: float = 1.0,
) -> Array:
    """DEPRECATED: JAX Gumbel-Softmax rotation sampling removed (JAX retirement).

    Use the CP-SAT placer for discrete rotation decisions instead.
    """
    raise NotImplementedError(
        "sample_rotation removed (JAX retirement). "
        "Use the CP-SAT placer for discrete rotation decisions."
    )


def sample_rotation_batch(
    logits: Array,
    key: Array,
    temperature: float = 1.0,
) -> Array:
    """DEPRECATED: JAX Gumbel-Softmax batch rotation sampling removed (JAX retirement).

    Use the CP-SAT placer for discrete rotation decisions instead.
    """
    raise NotImplementedError(
        "sample_rotation_batch removed (JAX retirement). "
        "Use the CP-SAT placer for discrete rotation decisions."
    )
