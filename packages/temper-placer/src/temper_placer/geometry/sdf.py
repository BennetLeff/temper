"""
Signed Distance Functions (SDF) for temper-placer.

SDFs are a powerful primitive for differentiable geometry. An SDF returns:
- Negative value: point is inside the shape (distance to nearest boundary)
- Zero: point is on the boundary
- Positive value: point is outside the shape (distance to nearest boundary)

Key advantages:
- Smooth gradients everywhere (no discontinuities)
- Easy to combine shapes (union, intersection, subtraction)
- Natural for overlap detection: overlap = relu(-sdf)
- Works well with soft boundaries for optimization

All functions are JAX-compatible for automatic differentiation.
"""
import numpy as np

Array = np.ndarray  # numpy alias replacing JAX Array post-JAX retirement
# =============================================================================
# Basic Shape SDFs
# =============================================================================


def sdf_circle(point: Array, center: Array, radius: float) -> Array:
    """
    Signed distance function for a circle.

    Args:
        point: Query point as (x, y) array
        center: Circle center as (x, y) array
        radius: Circle radius

    Returns:
        Signed distance: negative inside, zero on boundary, positive outside
    """
    dist_to_center = np.sqrt(np.sum((point - center) ** 2))
    return dist_to_center - radius


def sdf_rectangle(point: Array, center: Array, width: float, height: float) -> Array:
    """
    Signed distance function for an axis-aligned rectangle.

    Args:
        point: Query point as (x, y) array
        center: Rectangle center as (x, y) array
        width: Rectangle width
        height: Rectangle height

    Returns:
        Signed distance: negative inside, zero on boundary, positive outside
    """
    # Transform to rectangle's local coordinates
    local = np.abs(point - center)
    half_dims = np.array([width / 2.0, height / 2.0])

    # Distance from point to rectangle edge
    # For points inside: negative of distance to nearest edge
    # For points outside: positive distance to nearest point on rectangle

    # Distance to edges (positive = outside, negative = inside)
    d = local - half_dims

    # Outside distance: sqrt of squared positive components
    # Add small epsilon for numerical stability in gradients
    outside_dist = np.sqrt(np.sum(np.maximum(d, 0.0) ** 2) + 1e-10)

    # For points fully inside, outside_dist should be 0
    is_fully_inside = np.all(d < 0)
    outside_dist = np.where(is_fully_inside, 0.0, outside_dist)

    # Inside distance: negative of min distance to edge
    inside_dist = np.minimum(np.max(d), 0.0)

    return outside_dist + inside_dist


def sdf_box_2d(point: Array, half_extents: Array) -> Array:
    """
    SDF for an axis-aligned box centered at origin.

    Simplified version when center is at origin.

    Args:
        point: Query point as (x, y) array
        half_extents: Half-width and half-height as (hw, hh) array

    Returns:
        Signed distance
    """
    d = np.abs(point) - half_extents
    outside_dist = np.sqrt(np.sum(np.maximum(d, 0.0) ** 2))
    inside_dist = np.minimum(np.max(d), 0.0)
    return outside_dist + inside_dist


def sdf_rounded_rectangle(
    point: Array,
    center: Array,
    width: float,
    height: float,
    corner_radius: float,
) -> Array:
    """
    SDF for a rectangle with rounded corners.

    Args:
        point: Query point as (x, y) array
        center: Rectangle center as (x, y) array
        width: Rectangle width (including rounded corners)
        height: Rectangle height (including rounded corners)
        corner_radius: Radius of corner rounding

    Returns:
        Signed distance
    """
    # Clamp corner radius to valid range
    max_radius = np.minimum(width, height) / 2.0
    r = np.minimum(corner_radius, max_radius)

    # Shrink the rectangle by the corner radius
    inner_half_dims = np.array([(width - 2 * r) / 2.0, (height - 2 * r) / 2.0])

    # SDF of inner rectangle, then offset by radius
    local = np.abs(point - center)
    d = local - inner_half_dims

    # Distance to rounded edge
    outside_dist = np.sqrt(np.sum(np.maximum(d, 0.0) ** 2)) - r
    inside_dist = np.minimum(np.max(d), 0.0) - r

    return outside_dist + inside_dist


def sdf_capsule(
    point: Array,
    start: Array,
    end: Array,
    radius: float,
) -> Array:
    """
    SDF for a capsule (line segment with radius).

    Useful for representing traces or elongated keepout zones.

    Args:
        point: Query point as (x, y) array
        start: Start of capsule centerline as (x, y) array
        end: End of capsule centerline as (x, y) array
        radius: Capsule radius

    Returns:
        Signed distance
    """
    # Vector from start to end
    ab = end - start
    # Vector from start to point
    ap = point - start

    # Project point onto line, clamped to segment
    ab_len_sq = np.sum(ab**2)
    t = np.clip(np.sum(ap * ab) / np.maximum(ab_len_sq, 1e-10), 0.0, 1.0)

    # Closest point on segment
    closest = start + t * ab

    # Distance to closest point, minus radius
    return np.sqrt(np.sum((point - closest) ** 2)) - radius


# =============================================================================
# Polygon SDF
# =============================================================================


def sdf_polygon(point: Array, vertices: Array) -> Array:
    """
    SDF for a convex or concave polygon.

    Uses the winding number approach for robust inside/outside detection.

    Args:
        point: Query point as (x, y) array
        vertices: Polygon vertices as (N, 2) array, ordered (CW or CCW)

    Returns:
        Signed distance (negative inside, positive outside)

    Note: This is an approximation that computes distance to nearest edge.
          For exact SDF, more complex computation is needed.
    """
    n = vertices.shape[0]

    # Compute distance to each edge
    min_dist_sq = np.inf
    sign = np.array(1.0)  # Will be set by winding number

    # Check each edge
    def edge_distance(carry, idx):
        min_d_sq, winding = carry
        i = idx
        j = (idx + 1) % n

        # Edge from vertices[i] to vertices[j]
        vi = vertices[i]
        vj = vertices[j]

        # Vector along edge
        edge = vj - vi
        # Vector from edge start to point
        to_point = point - vi

        # Project point onto edge line, clamped to edge
        edge_len_sq = np.sum(edge**2)
        t = np.clip(np.sum(to_point * edge) / np.maximum(edge_len_sq, 1e-10), 0.0, 1.0)

        # Closest point on edge
        closest = vi + t * edge

        # Distance squared to closest point
        d_sq = np.sum((point - closest) ** 2)

        # Update minimum
        min_d_sq = np.minimum(min_d_sq, d_sq)

        # Winding number contribution
        # Cross product of edge vector with vector to point determines side
        cross = edge[0] * to_point[1] - edge[1] * to_point[0]

        # Check if edge crosses horizontal ray from point going right
        y_above_start = point[1] >= vi[1]
        y_below_end = point[1] < vj[1]
        y_below_start = point[1] < vi[1]
        y_above_end = point[1] >= vj[1]

        # Upward crossing (adds to winding)
        upward = y_above_start & y_below_end & (cross > 0)
        # Downward crossing (subtracts from winding)
        downward = y_below_start & y_above_end & (cross < 0)

        winding = winding + np.where(upward, 1.0, 0.0) - np.where(downward, 1.0, 0.0)

        return (min_d_sq, winding), None

    # Use lax.scan for efficient iteration
    import jax.lax as lax

    (min_dist_sq, winding), _ = lax.scan(edge_distance, (np.inf, 0.0), np.arange(n))

    # Sign based on winding number (non-zero = inside)
    sign = np.where(winding != 0, -1.0, 1.0)

    return sign * np.sqrt(min_dist_sq)


def sdf_convex_polygon(point: Array, vertices: Array) -> Array:
    """
    SDF for a convex polygon (simpler and faster than general polygon).

    Args:
        point: Query point as (x, y) array
        vertices: Convex polygon vertices as (N, 2) array, ordered CCW

    Returns:
        Signed distance (negative inside, positive outside)
    """
    n = vertices.shape[0]

    # For convex polygon, point is inside if it's on the same side
    # of all edges. The SDF is the distance to the nearest edge.

    def edge_signed_distance(idx):
        i = idx
        j = (idx + 1) % n

        vi = vertices[i]
        vj = vertices[j]

        # Edge vector
        edge = vj - vi
        # Normal (pointing inward for CCW polygon)
        normal = np.array([edge[1], -edge[0]])
        normal = normal / np.sqrt(np.sum(normal**2) + 1e-10)

        # Signed distance to infinite line
        to_point = point - vi
        signed_dist = np.sum(to_point * normal)

        return signed_dist

    # Compute signed distance to each edge line
    signed_dists = jax.vmap(edge_signed_distance)(np.arange(n))

    # For convex polygon:
    # - If all signed_dists are negative, point is inside
    # - The SDF is max(signed_dists) (most positive = closest to being outside)

    return np.max(signed_dists)




# =============================================================================
# SDF Combination Operations
# =============================================================================


def sdf_union(sdf1: Array, sdf2: Array) -> Array:
    """
    Union of two SDFs (combines shapes).

    Point is inside result if inside either shape.

    Args:
        sdf1: SDF value for first shape
        sdf2: SDF value for second shape

    Returns:
        SDF of union
    """
    return np.minimum(sdf1, sdf2)


def sdf_intersection(sdf1: Array, sdf2: Array) -> Array:
    """
    Intersection of two SDFs.

    Point is inside result if inside both shapes.

    Args:
        sdf1: SDF value for first shape
        sdf2: SDF value for second shape

    Returns:
        SDF of intersection
    """
    return np.maximum(sdf1, sdf2)


def sdf_subtraction(sdf1: Array, sdf2: Array) -> Array:
    """
    Subtraction of SDFs (sdf1 minus sdf2).

    Point is inside result if inside sdf1 and outside sdf2.

    Args:
        sdf1: SDF value for shape to subtract from
        sdf2: SDF value for shape to subtract

    Returns:
        SDF of subtraction
    """
    return np.maximum(sdf1, -sdf2)


def sdf_smooth_union(sdf1: Array, sdf2: Array, k: float = 0.5) -> Array:
    """
    Smooth union of two SDFs with blending.

    Creates a smooth blend between shapes instead of sharp union.

    Args:
        sdf1: SDF value for first shape
        sdf2: SDF value for second shape
        k: Blending radius (larger = smoother)

    Returns:
        SDF of smooth union
    """
    h = np.clip(0.5 + 0.5 * (sdf2 - sdf1) / k, 0.0, 1.0)
    return sdf2 * (1 - h) + sdf1 * h - k * h * (1 - h)


def sdf_smooth_intersection(sdf1: Array, sdf2: Array, k: float = 0.5) -> Array:
    """
    Smooth intersection of two SDFs with blending.

    Args:
        sdf1: SDF value for first shape
        sdf2: SDF value for second shape
        k: Blending radius (larger = smoother)

    Returns:
        SDF of smooth intersection
    """
    h = np.clip(0.5 - 0.5 * (sdf2 - sdf1) / k, 0.0, 1.0)
    return sdf2 * (1 - h) + sdf1 * h + k * h * (1 - h)


# =============================================================================
# SDF Modifications
# =============================================================================


def sdf_offset(sdf_value: Array, offset: float) -> Array:
    """
    Offset (dilate/erode) an SDF.

    Positive offset makes shape larger (dilation).
    Negative offset makes shape smaller (erosion).

    Args:
        sdf_value: Original SDF value
        offset: Amount to offset (positive = larger)

    Returns:
        Offset SDF value
    """
    return sdf_value - offset


def sdf_round(sdf_value: Array, radius: float) -> Array:
    """
    Round the corners of an SDF shape.

    This is equivalent to Minkowski sum with a circle of given radius.

    Args:
        sdf_value: Original SDF value
        radius: Rounding radius

    Returns:
        Rounded SDF value
    """
    return sdf_value - radius


def sdf_shell(sdf_value: Array, thickness: float) -> Array:
    """
    Create a shell (hollow version) of an SDF shape.

    Args:
        sdf_value: Original SDF value
        thickness: Shell thickness

    Returns:
        SDF of the shell
    """
    return np.abs(sdf_value) - thickness / 2.0


# =============================================================================
# Utility Functions
# =============================================================================


def sdf_to_mask(sdf_value: Array, smoothness: float = 0.1) -> Array:
    """
    Convert SDF to a soft mask (0 outside, 1 inside).

    Uses sigmoid for smooth transition.

    Args:
        sdf_value: SDF value(s)
        smoothness: Width of transition region (smaller = sharper)

    Returns:
        Mask value(s) in range [0, 1]
    """
    return jax.nn.sigmoid(-sdf_value / smoothness)


def sdf_to_penalty(sdf_value: Array, beta: float = 10.0) -> Array:
    """
    Convert SDF to a penalty value for being inside a shape.

    Returns positive penalty when inside (sdf < 0), zero when outside.
    Useful for keepout zone violations.

    Args:
        sdf_value: SDF value
        beta: Smoothing parameter for soft transition

    Returns:
        Penalty value (0 outside, positive inside)
    """
    # Using softplus for smooth ReLU
    return np.logaddexp(0.0, -beta * sdf_value) / beta


def sdf_gradient(sdf_func, point: Array, _epsilon: float = 1e-4) -> Array:
    """
    Compute gradient of an SDF at a point.

    The gradient of an SDF points away from the shape and has magnitude 1
    (for exact SDFs). This gives the direction to move to get away from
    or toward the shape.

    Args:
        sdf_func: SDF function that takes point and returns scalar
        point: Query point as (x, y) array
        epsilon: Finite difference step size

    Returns:
        Gradient vector as (gx, gy) array (normalized)
    """
    # Use JAX automatic differentiation
    grad = jax.grad(lambda p: sdf_func(p))(point)

    # Normalize (SDF gradient should have unit magnitude)
    magnitude = np.sqrt(np.sum(grad**2) + 1e-10)
    return grad / magnitude
