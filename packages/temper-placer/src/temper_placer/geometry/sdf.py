"""
Signed Distance Functions (SDF) — Rust-backed via temper_geometry.

SDFs are a powerful primitive for differentiable geometry. An SDF returns:
- Negative value: point is inside the shape (distance to nearest boundary)
- Zero: point is on the boundary
- Positive value: point is outside the shape (distance to nearest boundary)

All functions delegate to the temper_geometry Rust crate except sdf_gradient,
which takes a Python callable and cannot be ported to Rust.
"""

import numpy as np
import temper_geometry as _tg

# =============================================================================
# Basic Shape SDFs
# =============================================================================


def sdf_circle(px, py, cx, cy, r):
    """Signed distance function for a circle.

    Args:
        px, py: Query point coordinates
        cx, cy: Circle center coordinates
        r: Circle radius

    Returns:
        Signed distance: negative inside, zero on boundary, positive outside
    """
    return _tg.sdf_circle(px, py, cx, cy, r)


def sdf_rectangle(px, py, cx, cy, half_w, half_h):
    """Signed distance function for an axis-aligned rectangle.

    Args:
        px, py: Query point coordinates
        cx, cy: Rectangle center coordinates
        half_w: Half-width
        half_h: Half-height

    Returns:
        Signed distance: negative inside, zero on boundary, positive outside
    """
    return _tg.sdf_rectangle(px, py, cx, cy, half_w, half_h)


def sdf_box_2d(px, py, center_x, center_y, half_x, half_y):
    """SDF for an axis-aligned box.

    Args:
        px, py: Query point coordinates
        center_x, center_y: Box center coordinates
        half_x, half_y: Box half-extents

    Returns:
        Signed distance
    """
    return _tg.sdf_box_2d(px, py, center_x, center_y, half_x, half_y)


def sdf_rounded_rectangle(px, py, cx, cy, half_w, half_h, r):
    """SDF for a rectangle with rounded corners.

    Args:
        px, py: Query point coordinates
        cx, cy: Rectangle center coordinates
        half_w: Half-width
        half_h: Half-height
        r: Corner radius

    Returns:
        Signed distance
    """
    return _tg.sdf_rounded_rectangle(px, py, cx, cy, half_w, half_h, r)


def sdf_capsule(px, py, ax, ay, bx, by, r):
    """SDF for a capsule (line segment with radius).

    Args:
        px, py: Query point coordinates
        ax, ay: Capsule centerline start coordinates
        bx, by: Capsule centerline end coordinates
        r: Capsule radius

    Returns:
        Signed distance
    """
    return _tg.sdf_capsule(px, py, ax, ay, bx, by, r)


# =============================================================================
# Polygon SDF
# =============================================================================


def sdf_polygon(px, py, vertices):
    """SDF for a convex or concave polygon.

    Args:
        px, py: Query point coordinates
        vertices: Flat list of [x1, y1, x2, y2, ...] vertex coordinates

    Returns:
        Signed distance (negative inside, positive outside)
    """
    return _tg.sdf_polygon(px, py, vertices)


def sdf_convex_polygon(px, py, vertices):
    """SDF for a convex polygon (faster than general polygon).

    Args:
        px, py: Query point coordinates
        vertices: Flat list of [x1, y1, x2, y2, ...] vertex coordinates, ordered CCW

    Returns:
        Signed distance (negative inside, positive outside)
    """
    return _tg.sdf_convex_polygon(px, py, vertices)


# =============================================================================
# SDF Combination Operations
# =============================================================================


def sdf_union(d1, d2):
    """Union of two SDFs (combines shapes via min).

    Args:
        d1: SDF value for first shape
        d2: SDF value for second shape

    Returns:
        SDF of union
    """
    return _tg.sdf_union(d1, d2)


def sdf_intersection(d1, d2):
    """Intersection of two SDFs (via max).

    Args:
        d1: SDF value for first shape
        d2: SDF value for second shape

    Returns:
        SDF of intersection
    """
    return _tg.sdf_intersection(d1, d2)


def sdf_subtraction(d1, d2):
    """Subtraction of SDFs (d1 minus d2).

    Args:
        d1: SDF value for shape to subtract from
        d2: SDF value for shape to subtract

    Returns:
        SDF of subtraction
    """
    return _tg.sdf_subtraction(d1, d2)


def sdf_smooth_union(d1, d2, k=0.5):
    """Smooth union of two SDFs with blending.

    Args:
        d1: SDF value for first shape
        d2: SDF value for second shape
        k: Blending radius (larger = smoother)

    Returns:
        SDF of smooth union
    """
    return _tg.sdf_smooth_union(d1, d2, k)


def sdf_smooth_intersection(d1, d2, k=0.5):
    """Smooth intersection of two SDFs with blending.

    Args:
        d1: SDF value for first shape
        d2: SDF value for second shape
        k: Blending radius (larger = smoother)

    Returns:
        SDF of smooth intersection
    """
    return _tg.sdf_smooth_intersection(d1, d2, k)


# =============================================================================
# SDF Modifications
# =============================================================================


def sdf_offset(d, offset):
    """Offset (dilate/erode) an SDF.

    Args:
        d: Original SDF value
        offset: Amount to offset (positive = larger)

    Returns:
        Offset SDF value
    """
    return _tg.sdf_offset(d, offset)


def sdf_round(d, r):
    """Round the corners of an SDF shape.

    Args:
        d: Original SDF value
        r: Rounding radius

    Returns:
        Rounded SDF value
    """
    return _tg.sdf_round(d, r)


def sdf_shell(d, thickness):
    """Create a shell (hollow version) of an SDF shape.

    Args:
        d: Original SDF value
        thickness: Shell thickness

    Returns:
        SDF of the shell
    """
    return _tg.sdf_shell(d, thickness)


# =============================================================================
# Utility Functions
# =============================================================================


def sdf_to_mask(distances, threshold=0.1):
    """Convert SDF to a soft mask (0 outside, 1 inside).

    The Rust implementation expects a sequence; wraps scalar in a list.

    Args:
        distances: SDF value(s)
        threshold: Width of transition region (smaller = sharper)

    Returns:
        Mask value(s) in range [0, 1]
    """
    if isinstance(distances, (int, float)):
        return _tg.sdf_to_mask([distances], threshold)[0]
    return _tg.sdf_to_mask(distances, threshold)


def sdf_to_penalty(distances, alpha=10.0):
    """Convert SDF to a penalty value for being inside a shape.

    The Rust implementation expects a sequence; wraps scalar in a list.

    Args:
        distances: SDF value
        alpha: Smoothing parameter

    Returns:
        Penalty value (0 outside, positive inside)
    """
    if isinstance(distances, (int, float)):
        return _tg.sdf_to_penalty([distances], alpha)[0]
    return _tg.sdf_to_penalty(distances, alpha)


def sdf_gradient(sdf_func, point, epsilon=1e-4):
    """Compute gradient of an SDF at a point using central finite differences.

    This function takes a Python callable and cannot be delegated to Rust.

    Args:
        sdf_func: SDF function that takes point and returns scalar
        point: Query point coordinates
        epsilon: Finite difference step size

    Returns:
        Gradient vector as (gx, gy) — finite-difference approximation
    """
    # Finite-difference gradient approximation
    px, py = point
    dx = (sdf_func((px + epsilon, py)) - sdf_func((px - epsilon, py))) / (2 * epsilon)
    dy = (sdf_func((px, py + epsilon)) - sdf_func((px, py - epsilon))) / (2 * epsilon)
    grad = np.array([dx, dy])

    # Normalize
    magnitude = np.sqrt(np.sum(grad**2) + 1e-10)
    return grad / magnitude
