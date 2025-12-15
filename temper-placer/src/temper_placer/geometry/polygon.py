"""
Polygon operations for temper-placer.

This module provides differentiable polygon operations essential for:
- Loop area loss (gate drive loops, bootstrap loops)
- Zone containment checking
- Component grouping and clustering

All functions use JAX for automatic differentiation and are compatible
with jax.jit and jax.grad.

Key algorithms:
- Shoelace formula for polygon area (differentiable)
- Winding number for point-in-polygon (soft version for gradients)
- Convex hull for component bounding
"""

import jax.numpy as jnp
import jax
from jax import Array
from typing import Tuple, Optional


# =============================================================================
# Polygon Area (Shoelace Formula)
# =============================================================================


def polygon_area(vertices: Array) -> Array:
    """
    Compute area of a polygon using the shoelace formula.

    The shoelace formula is fully differentiable:
        A = 0.5 * |sum(x_i * y_{i+1} - x_{i+1} * y_i)|

    Args:
        vertices: Polygon vertices as (N, 2) array, ordered (CW or CCW)

    Returns:
        Polygon area (always positive)
    """
    # Roll vertices to get (i+1) indices
    vertices_next = jnp.roll(vertices, -1, axis=0)

    # Shoelace formula: sum of cross products
    # cross = x_i * y_{i+1} - x_{i+1} * y_i
    cross = vertices[:, 0] * vertices_next[:, 1] - vertices_next[:, 0] * vertices[:, 1]

    # Area is half the absolute value of the sum
    return jnp.abs(jnp.sum(cross)) / 2.0


def polygon_signed_area(vertices: Array) -> Array:
    """
    Compute signed area of a polygon (positive for CCW, negative for CW).

    Args:
        vertices: Polygon vertices as (N, 2) array

    Returns:
        Signed polygon area
    """
    vertices_next = jnp.roll(vertices, -1, axis=0)
    cross = vertices[:, 0] * vertices_next[:, 1] - vertices_next[:, 0] * vertices[:, 1]
    return jnp.sum(cross) / 2.0


def triangle_area(p1: Array, p2: Array, p3: Array) -> Array:
    """
    Compute area of a triangle from three points.

    Args:
        p1, p2, p3: Triangle vertices as (x, y) arrays

    Returns:
        Triangle area (always positive)
    """
    # Using cross product formula
    # Area = 0.5 * |((p2-p1) x (p3-p1))|
    v1 = p2 - p1
    v2 = p3 - p1
    cross = v1[0] * v2[1] - v1[1] * v2[0]
    return jnp.abs(cross) / 2.0


# =============================================================================
# Polygon Centroid
# =============================================================================


def polygon_centroid(vertices: Array) -> Array:
    """
    Compute centroid of a polygon.

    The centroid is the center of mass assuming uniform density.

    Args:
        vertices: Polygon vertices as (N, 2) array

    Returns:
        Centroid as (x, y) array
    """
    vertices_next = jnp.roll(vertices, -1, axis=0)

    # Cross products for area calculation
    cross = vertices[:, 0] * vertices_next[:, 1] - vertices_next[:, 0] * vertices[:, 1]

    # Signed area
    area = jnp.sum(cross) / 2.0

    # Centroid coordinates
    cx = jnp.sum((vertices[:, 0] + vertices_next[:, 0]) * cross) / (6.0 * area)
    cy = jnp.sum((vertices[:, 1] + vertices_next[:, 1]) * cross) / (6.0 * area)

    return jnp.array([cx, cy])


def points_centroid(points: Array) -> Array:
    """
    Compute centroid (mean position) of a set of points.

    Simpler than polygon_centroid - just the mean of coordinates.

    Args:
        points: Points as (N, 2) array

    Returns:
        Centroid as (x, y) array
    """
    return jnp.mean(points, axis=0)


# =============================================================================
# Point-in-Polygon Tests
# =============================================================================


def point_in_polygon_winding(point: Array, vertices: Array) -> Array:
    """
    Check if a point is inside a polygon using winding number.

    Returns 1.0 if inside, 0.0 if outside. This is a hard boundary
    test (not differentiable at the boundary).

    Args:
        point: Query point as (x, y) array
        vertices: Polygon vertices as (N, 2) array

    Returns:
        1.0 if inside, 0.0 if outside
    """
    n = vertices.shape[0]

    def edge_winding(idx):
        i = idx
        j = (idx + 1) % n

        vi = vertices[i]
        vj = vertices[j]

        # Edge vector
        edge = vj - vi
        # Vector to point
        to_point = point - vi

        # Cross product determines side
        cross = edge[0] * to_point[1] - edge[1] * to_point[0]

        # Check if edge crosses horizontal ray from point
        y_above_start = point[1] >= vi[1]
        y_below_end = point[1] < vj[1]
        y_below_start = point[1] < vi[1]
        y_above_end = point[1] >= vj[1]

        # Upward crossing
        upward = y_above_start & y_below_end & (cross > 0)
        # Downward crossing
        downward = y_below_start & y_above_end & (cross < 0)

        return jnp.where(upward, 1.0, 0.0) - jnp.where(downward, 1.0, 0.0)

    # Sum winding contributions
    winding = jnp.sum(jax.vmap(edge_winding)(jnp.arange(n)))

    # Non-zero winding = inside
    return jnp.where(winding != 0, 1.0, 0.0)


def point_in_polygon_soft(point: Array, vertices: Array, smoothness: float = 0.1) -> Array:
    """
    Soft point-in-polygon test (differentiable).

    Returns a value close to 1.0 for points well inside,
    close to 0.0 for points well outside, with smooth transition
    at the boundary.

    Uses signed distance to nearest edge with sigmoid.

    Args:
        point: Query point as (x, y) array
        vertices: Polygon vertices as (N, 2) array
        smoothness: Width of transition region

    Returns:
        Soft containment indicator in range [0, 1]
    """
    # Use SDF approach for soft boundary
    n = vertices.shape[0]

    def edge_signed_distance(idx):
        i = idx
        j = (idx + 1) % n

        vi = vertices[i]
        vj = vertices[j]

        # Edge vector
        edge = vj - vi
        # Perpendicular (inward normal for CCW polygon)
        normal = jnp.array([edge[1], -edge[0]])
        normal = normal / (jnp.sqrt(jnp.sum(normal**2)) + 1e-10)

        # Signed distance to edge line
        to_point = point - vi
        return jnp.sum(to_point * normal)

    # Get signed distance to each edge
    signed_dists = jax.vmap(edge_signed_distance)(jnp.arange(n))

    # For convex polygon, point is inside if all signed distances < 0
    # The "most positive" distance indicates how far outside
    min_dist = jnp.max(signed_dists)

    # Sigmoid for soft transition
    return jax.nn.sigmoid(-min_dist / smoothness)


def point_in_rect(
    point: Array,
    min_corner: Array,
    max_corner: Array,
) -> Array:
    """
    Check if point is inside axis-aligned rectangle.

    Args:
        point: Query point as (x, y) array
        min_corner: Bottom-left corner
        max_corner: Top-right corner

    Returns:
        1.0 if inside, 0.0 if outside
    """
    inside_x = (point[0] >= min_corner[0]) & (point[0] <= max_corner[0])
    inside_y = (point[1] >= min_corner[1]) & (point[1] <= max_corner[1])
    return jnp.where(inside_x & inside_y, 1.0, 0.0)


def point_in_rect_soft(
    point: Array,
    min_corner: Array,
    max_corner: Array,
    smoothness: float = 0.1,
) -> Array:
    """
    Soft check if point is inside rectangle (differentiable).

    Args:
        point: Query point as (x, y) array
        min_corner: Bottom-left corner
        max_corner: Top-right corner
        smoothness: Width of transition region

    Returns:
        Soft containment indicator in range [0, 1]
    """
    # Distance to each edge (negative = inside)
    dist_left = min_corner[0] - point[0]
    dist_right = point[0] - max_corner[0]
    dist_bottom = min_corner[1] - point[1]
    dist_top = point[1] - max_corner[1]

    # Maximum of these is the "most outside" distance
    max_dist = jnp.maximum(jnp.maximum(dist_left, dist_right), jnp.maximum(dist_bottom, dist_top))

    # Sigmoid for soft transition
    return jax.nn.sigmoid(-max_dist / smoothness)


# =============================================================================
# Polygon Perimeter
# =============================================================================


def polygon_perimeter(vertices: Array) -> Array:
    """
    Compute perimeter of a polygon.

    Args:
        vertices: Polygon vertices as (N, 2) array

    Returns:
        Polygon perimeter (sum of edge lengths)
    """
    vertices_next = jnp.roll(vertices, -1, axis=0)
    edges = vertices_next - vertices
    edge_lengths = jnp.sqrt(jnp.sum(edges**2, axis=1))
    return jnp.sum(edge_lengths)


# =============================================================================
# Loop Area for PCB Design
# =============================================================================


def compute_loop_area(pin_positions: Array) -> Array:
    """
    Compute area of a current loop formed by pins.

    Used for gate drive loop area loss and other EMI-sensitive loops.
    The pins should be ordered to form the loop path.

    Args:
        pin_positions: Pin positions as (N, 2) array, ordered around loop

    Returns:
        Loop area
    """
    return polygon_area(pin_positions)


def compute_loop_perimeter(pin_positions: Array) -> Array:
    """
    Compute perimeter of a current loop.

    Longer perimeters generally indicate more inductance.

    Args:
        pin_positions: Pin positions as (N, 2) array, ordered around loop

    Returns:
        Loop perimeter
    """
    return polygon_perimeter(pin_positions)


def loop_area_penalty(
    pin_positions: Array,
    max_area: float,
    weight: float = 1.0,
) -> Array:
    """
    Compute penalty for loop area exceeding maximum.

    Args:
        pin_positions: Pin positions forming the loop
        max_area: Maximum allowed loop area
        weight: Penalty weight

    Returns:
        Squared penalty for area exceeding max_area
    """
    area = compute_loop_area(pin_positions)
    violation = jnp.maximum(0.0, area - max_area)
    return weight * violation**2


# =============================================================================
# Bounding Box and Hull Operations
# =============================================================================


def polygon_bounding_box(vertices: Array) -> Tuple[Array, Array]:
    """
    Compute axis-aligned bounding box of a polygon.

    Args:
        vertices: Polygon vertices as (N, 2) array

    Returns:
        Tuple of (min_corner, max_corner) as (x, y) arrays
    """
    min_corner = jnp.min(vertices, axis=0)
    max_corner = jnp.max(vertices, axis=0)
    return min_corner, max_corner


def polygon_bounding_circle(vertices: Array) -> Tuple[Array, Array]:
    """
    Compute approximate bounding circle of a polygon.

    Uses centroid as center and max distance to any vertex as radius.
    This is not the minimum bounding circle, but is efficient.

    Args:
        vertices: Polygon vertices as (N, 2) array

    Returns:
        Tuple of (center, radius)
    """
    center = points_centroid(vertices)
    distances = jnp.sqrt(jnp.sum((vertices - center) ** 2, axis=1))
    radius = jnp.max(distances)
    return center, radius


# =============================================================================
# Polygon Validation
# =============================================================================


def is_convex(vertices: Array) -> Array:
    """
    Check if a polygon is convex.

    A polygon is convex if all cross products of consecutive edges
    have the same sign.

    Args:
        vertices: Polygon vertices as (N, 2) array

    Returns:
        True if convex, False otherwise
    """
    n = vertices.shape[0]

    # Get consecutive edge vectors
    edges = jnp.roll(vertices, -1, axis=0) - vertices
    edges_next = jnp.roll(edges, -1, axis=0)

    # Cross products of consecutive edges
    cross = edges[:, 0] * edges_next[:, 1] - edges[:, 1] * edges_next[:, 0]

    # All should have same sign for convex polygon
    all_positive = jnp.all(cross >= 0)
    all_negative = jnp.all(cross <= 0)

    return all_positive | all_negative


def polygon_orientation(vertices: Array) -> Array:
    """
    Determine orientation of a polygon.

    Args:
        vertices: Polygon vertices as (N, 2) array

    Returns:
        1.0 for CCW, -1.0 for CW
    """
    signed_area = polygon_signed_area(vertices)
    return jnp.sign(signed_area)


# =============================================================================
# Polygon Transformations
# =============================================================================


def translate_polygon(vertices: Array, offset: Array) -> Array:
    """
    Translate a polygon by an offset.

    Args:
        vertices: Polygon vertices as (N, 2) array
        offset: Translation offset as (x, y) array

    Returns:
        Translated vertices
    """
    return vertices + offset


def scale_polygon(vertices: Array, scale: float, center: Optional[Array] = None) -> Array:
    """
    Scale a polygon around a center point.

    Args:
        vertices: Polygon vertices as (N, 2) array
        scale: Scale factor
        center: Center of scaling (default: centroid)

    Returns:
        Scaled vertices
    """
    if center is None:
        center = points_centroid(vertices)

    return center + scale * (vertices - center)


def rotate_polygon(
    vertices: Array,
    angle: float,
    center: Optional[Array] = None,
) -> Array:
    """
    Rotate a polygon around a center point.

    Args:
        vertices: Polygon vertices as (N, 2) array
        angle: Rotation angle in radians (CCW positive)
        center: Center of rotation (default: centroid)

    Returns:
        Rotated vertices
    """
    if center is None:
        center = points_centroid(vertices)

    cos_a = jnp.cos(angle)
    sin_a = jnp.sin(angle)

    # Translate to origin
    centered = vertices - center

    # Rotate
    rotated = jnp.stack(
        [
            centered[:, 0] * cos_a - centered[:, 1] * sin_a,
            centered[:, 0] * sin_a + centered[:, 1] * cos_a,
        ],
        axis=1,
    )

    # Translate back
    return rotated + center
