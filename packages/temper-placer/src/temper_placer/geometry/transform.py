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


def get_rotation_matrix(angle_rad):
    """Get 2x2 rotation matrix for a given angle.

    Args:
        angle_rad: Rotation angle in radians (CCW positive)

    Returns:
        2x2 rotation matrix as flat list [a, b, c, d]
    """
    return _tg.get_rotation_matrix(angle_rad)


def rotate_point(x, y, angle_rad, center_x=0.0, center_y=0.0):
    """Rotate a point around a center.

    Args:
        x, y: Point coordinates
        angle_rad: Rotation angle in radians
        center_x, center_y: Center of rotation (default origin)

    Returns:
        (rx, ry) rotated point coordinates
    """
    return _tg.rotate_point(x, y, angle_rad, center_x, center_y)


def rotate_points(points, angle_rad, center_x=0.0, center_y=0.0):
    """Rotate multiple points around a center.

    Args:
        points: Flat list of [x1, y1, x2, y2, ...] coordinates
        angle_rad: Rotation angle in radians
        center_x, center_y: Center of rotation (default origin)

    Returns:
        Flat list of rotated point coordinates
    """
    return _tg.rotate_points(points, angle_rad, center_x, center_y)


# =============================================================================
# Rectangle and Bounds Rotation
# =============================================================================


def get_rotated_bounds(rx, ry, rw, rh, angle_rad):
    """Get axis-aligned bounding rectangle of a rotated rectangle.

    Returns the AABB as (x, y, w, h) that contains the rotated rectangle.

    Args:
        rx, ry: Rectangle position
        rw, rh: Rectangle size
        angle_rad: Rotation angle in radians

    Returns:
        (x, y, w, h) of the rotated bounding rectangle
    """
    return _tg.get_rotated_bounds(rx, ry, rw, rh, angle_rad)


def rotate_rectangle_corners(rx, ry, rw, rh, angle_rad, center_x, center_y):
    """Get corners of a rotated rectangle.

    Args:
        rx, ry: Rectangle position
        rw, rh: Rectangle size
        angle_rad: Rotation angle in radians
        center_x, center_y: Center of rotation

    Returns:
        Flat list [x1, y1, x2, y2, x3, y3, x4, y4] of rotated corner positions
    """
    return _tg.rotate_rectangle_corners(rx, ry, rw, rh, angle_rad, center_x, center_y)


def get_rotated_aabb(vertices):
    """Get axis-aligned bounding box of a polygon/rectangle.

    Args:
        vertices: Flat list of [x1, y1, x2, y2, ...] vertex coordinates

    Returns:
        (x1, y1, x2, y2) of AABB
    """
    return _tg.get_rotated_aabb(vertices)


# =============================================================================
# Pin Position Transforms
# =============================================================================


def transform_pin_position(pin_x, pin_y, comp_x, comp_y, rotation_rad):
    """Transform a pin position based on component center and rotation.

    Args:
        pin_x, pin_y: Pin offset from component center at 0° rotation
        comp_x, comp_y: Component center position
        rotation_rad: Component rotation in radians

    Returns:
        (wx, wy) world position of pin
    """
    return _tg.transform_pin_position(pin_x, pin_y, comp_x, comp_y, rotation_rad)


def transform_pin_positions(pin_positions, comp_x, comp_y, rotation_rad):
    """Transform multiple pin positions for a component.

    Args:
        pin_positions: Flat list of [x1, y1, x2, y2, ...] pin offsets
        comp_x, comp_y: Component center position
        rotation_rad: Component rotation in radians

    Returns:
        Flat list of world positions of pins
    """
    return _tg.transform_pin_positions(pin_positions, comp_x, comp_y, rotation_rad)


# =============================================================================
# Batch Operations
# =============================================================================


def batch_get_rotated_bounds(rects, angles):
    """Get rotated bounds for multiple rectangles.

    Args:
        rects: Flat list of [x1, y1, w1, h1, x2, y2, w2, h2, ...] rects
        angles: Flat list of rotation angles in radians

    Returns:
        (x_out, y_out, w_out, h_out) flat list of rotated bounds
    """
    return _tg.batch_get_rotated_bounds(rects, angles)


def batch_rotate_points(points, angles, centers):
    """Rotate multiple sets of points, each with different rotation and center.

    Args:
        points: Flat list of point coordinates
        angles: Flat list of rotation angles in radians
        centers: Flat list of [cx1, cy1, cx2, cy2, ...] centers

    Returns:
        Flat list of rotated points
    """
    return _tg.batch_rotate_points(points, angles, centers)


# =============================================================================
# Utility Functions
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


def gumbel_softmax(logits, temperature=1.0):
    """Gumbel-Softmax differentiable sampling.

    Args:
        logits: Raw logits
        temperature: Temperature parameter

    Returns:
        Differentiable sample
    """
    return _tg.gumbel_softmax(logits, temperature)


def sample_rotation(logits):
    """Sample a rotation from logits.

    Args:
        logits: Rotation logits

    Returns:
        Sampled rotation
    """
    return _tg.sample_rotation(logits)


def sample_rotation_batch(logits):
    """Sample rotations for a batch.

    Args:
        logits: Batch rotation logits

    Returns:
        Batch of sampled rotations
    """
    return _tg.sample_rotation_batch(logits)
