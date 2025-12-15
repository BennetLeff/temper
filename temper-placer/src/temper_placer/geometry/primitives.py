"""
Basic geometric primitives for temper-placer.

This module provides JAX-compatible geometric functions for:
- Point operations (distance, midpoint)
- Rectangle representation and operations
- Axis-aligned bounding box (AABB) operations
- Distance to board edge calculations

All functions are designed to be compatible with jax.jit and jax.grad
for use in differentiable optimization.
"""

import jax.numpy as jnp
import jax.nn
from jax import Array
from typing import Tuple


# =============================================================================
# Point Operations
# =============================================================================


def point_distance(p1: Array, p2: Array) -> Array:
    """
    Compute Euclidean distance between two points.

    Args:
        p1: First point as (x, y) array
        p2: Second point as (x, y) array

    Returns:
        Scalar distance between points
    """
    diff = p2 - p1
    return jnp.sqrt(jnp.sum(diff**2))


def point_distance_squared(p1: Array, p2: Array) -> Array:
    """
    Compute squared Euclidean distance between two points.

    More efficient than point_distance when only comparing distances,
    as it avoids the sqrt operation.

    Args:
        p1: First point as (x, y) array
        p2: Second point as (x, y) array

    Returns:
        Scalar squared distance between points
    """
    diff = p2 - p1
    return jnp.sum(diff**2)


def point_midpoint(p1: Array, p2: Array) -> Array:
    """
    Compute midpoint between two points.

    Args:
        p1: First point as (x, y) array
        p2: Second point as (x, y) array

    Returns:
        Midpoint as (x, y) array
    """
    return (p1 + p2) / 2.0


def points_centroid(points: Array) -> Array:
    """
    Compute centroid (mean position) of a set of points.

    Args:
        points: Array of shape (N, 2) containing N points

    Returns:
        Centroid as (x, y) array
    """
    return jnp.mean(points, axis=0)


def point_to_line_distance(point: Array, line_start: Array, line_end: Array) -> Array:
    """
    Compute shortest distance from a point to a line segment.

    Args:
        point: The point as (x, y) array
        line_start: Start of line segment as (x, y) array
        line_end: End of line segment as (x, y) array

    Returns:
        Shortest distance from point to line segment
    """
    # Vector from line_start to line_end
    line_vec = line_end - line_start
    line_len_sq = jnp.sum(line_vec**2)

    # Handle degenerate case (line is a point)
    line_len_sq = jnp.maximum(line_len_sq, 1e-10)

    # Project point onto line, clamped to [0, 1]
    t = jnp.sum((point - line_start) * line_vec) / line_len_sq
    t = jnp.clip(t, 0.0, 1.0)

    # Find closest point on line segment
    closest = line_start + t * line_vec

    return point_distance(point, closest)


# =============================================================================
# Rectangle Operations
# =============================================================================


def rect_from_center(center: Array, width: float, height: float) -> Tuple[Array, Array]:
    """
    Create rectangle corners from center point and dimensions.

    Args:
        center: Center point as (x, y) array
        width: Rectangle width
        height: Rectangle height

    Returns:
        Tuple of (min_corner, max_corner) as (x, y) arrays
    """
    half_w = width / 2.0
    half_h = height / 2.0
    min_corner = center - jnp.array([half_w, half_h])
    max_corner = center + jnp.array([half_w, half_h])
    return min_corner, max_corner


def rect_center(min_corner: Array, max_corner: Array) -> Array:
    """
    Compute center of rectangle from corners.

    Args:
        min_corner: Bottom-left corner as (x, y) array
        max_corner: Top-right corner as (x, y) array

    Returns:
        Center point as (x, y) array
    """
    return (min_corner + max_corner) / 2.0


def rect_dimensions(min_corner: Array, max_corner: Array) -> Tuple[Array, Array]:
    """
    Compute dimensions of rectangle from corners.

    Args:
        min_corner: Bottom-left corner as (x, y) array
        max_corner: Top-right corner as (x, y) array

    Returns:
        Tuple of (width, height)
    """
    dims = max_corner - min_corner
    return dims[0], dims[1]


def rect_area(width: float, height: float) -> float:
    """
    Compute area of rectangle.

    Args:
        width: Rectangle width
        height: Rectangle height

    Returns:
        Area of rectangle
    """
    return width * height


def rect_contains_point(min_corner: Array, max_corner: Array, point: Array) -> Array:
    """
    Check if a point is inside a rectangle (soft version for gradients).

    Returns a value close to 1.0 if point is inside, close to 0.0 if outside.
    Uses a soft sigmoid for differentiability.

    Args:
        min_corner: Bottom-left corner as (x, y) array
        max_corner: Top-right corner as (x, y) array
        point: Point to test as (x, y) array

    Returns:
        Soft containment indicator (0.0 to 1.0)
    """
    # Distance inside rectangle (positive if inside)
    dist_inside_x = jnp.minimum(point[0] - min_corner[0], max_corner[0] - point[0])
    dist_inside_y = jnp.minimum(point[1] - min_corner[1], max_corner[1] - point[1])

    # Minimum distance (negative if outside)
    min_dist = jnp.minimum(dist_inside_x, dist_inside_y)

    # Soft sigmoid for differentiability (steep transition)
    beta = 10.0  # Steepness parameter
    return jax.nn.sigmoid(beta * min_dist)


def rect_corners(center: Array, width: float, height: float) -> Array:
    """
    Get all four corners of a rectangle.

    Args:
        center: Center point as (x, y) array
        width: Rectangle width
        height: Rectangle height

    Returns:
        Array of shape (4, 2) with corners in order:
        [bottom-left, bottom-right, top-right, top-left]
    """
    half_w = width / 2.0
    half_h = height / 2.0

    return jnp.array(
        [
            [center[0] - half_w, center[1] - half_h],  # bottom-left
            [center[0] + half_w, center[1] - half_h],  # bottom-right
            [center[0] + half_w, center[1] + half_h],  # top-right
            [center[0] - half_w, center[1] + half_h],  # top-left
        ]
    )


# =============================================================================
# Axis-Aligned Bounding Box (AABB) Operations
# =============================================================================


def aabb_from_points(points: Array) -> Tuple[Array, Array]:
    """
    Compute axis-aligned bounding box for a set of points.

    Args:
        points: Array of shape (N, 2) containing N points

    Returns:
        Tuple of (min_corner, max_corner) as (x, y) arrays
    """
    min_corner = jnp.min(points, axis=0)
    max_corner = jnp.max(points, axis=0)
    return min_corner, max_corner


def aabb_intersects(min1: Array, max1: Array, min2: Array, max2: Array) -> Array:
    """
    Check if two AABBs intersect (soft version for gradients).

    Returns a value indicating overlap amount. Positive if overlapping,
    negative if separated.

    Args:
        min1, max1: First AABB corners
        min2, max2: Second AABB corners

    Returns:
        Overlap indicator (positive = overlap, negative = separation)
    """
    # Compute overlap in each dimension
    overlap_x = jnp.minimum(max1[0], max2[0]) - jnp.maximum(min1[0], min2[0])
    overlap_y = jnp.minimum(max1[1], max2[1]) - jnp.maximum(min1[1], min2[1])

    # Both dimensions must overlap for intersection
    return jnp.minimum(overlap_x, overlap_y)


def aabb_overlap_area(min1: Array, max1: Array, min2: Array, max2: Array) -> Array:
    """
    Compute overlap area between two AABBs.

    Args:
        min1, max1: First AABB corners
        min2, max2: Second AABB corners

    Returns:
        Overlap area (0 if no overlap)
    """
    # Compute overlap in each dimension
    overlap_x = jnp.maximum(0.0, jnp.minimum(max1[0], max2[0]) - jnp.maximum(min1[0], min2[0]))
    overlap_y = jnp.maximum(0.0, jnp.minimum(max1[1], max2[1]) - jnp.maximum(min1[1], min2[1]))

    return overlap_x * overlap_y


def aabb_union(min1: Array, max1: Array, min2: Array, max2: Array) -> Tuple[Array, Array]:
    """
    Compute union bounding box of two AABBs.

    Args:
        min1, max1: First AABB corners
        min2, max2: Second AABB corners

    Returns:
        Tuple of (min_corner, max_corner) of union AABB
    """
    min_corner = jnp.minimum(min1, min2)
    max_corner = jnp.maximum(max1, max2)
    return min_corner, max_corner


def aabb_expand(min_corner: Array, max_corner: Array, margin: float) -> Tuple[Array, Array]:
    """
    Expand an AABB by a margin in all directions.

    Args:
        min_corner: Bottom-left corner
        max_corner: Top-right corner
        margin: Amount to expand by

    Returns:
        Tuple of (new_min, new_max) corners
    """
    margin_vec = jnp.array([margin, margin])
    return min_corner - margin_vec, max_corner + margin_vec


# =============================================================================
# Distance to Board Edge Functions
# =============================================================================


def distance_to_rect_edge(point: Array, min_corner: Array, max_corner: Array) -> Array:
    """
    Compute distance from point to nearest edge of a rectangle.

    Positive if point is inside, negative if outside.

    Args:
        point: Point as (x, y) array
        min_corner: Bottom-left corner of rectangle
        max_corner: Top-right corner of rectangle

    Returns:
        Signed distance to nearest edge (positive inside, negative outside)
    """
    # Distance to each edge (positive if inside)
    dist_left = point[0] - min_corner[0]
    dist_right = max_corner[0] - point[0]
    dist_bottom = point[1] - min_corner[1]
    dist_top = max_corner[1] - point[1]

    # If all positive, point is inside - return distance to nearest edge
    # If any negative, point is outside - return most negative
    return jnp.minimum(jnp.minimum(dist_left, dist_right), jnp.minimum(dist_bottom, dist_top))


def distance_to_specific_edge(
    point: Array, edge: str, min_corner: Array, max_corner: Array
) -> Array:
    """
    Compute distance from point to a specific edge of a rectangle.

    Args:
        point: Point as (x, y) array
        edge: Edge identifier - "TOP", "BOTTOM", "LEFT", or "RIGHT"
        min_corner: Bottom-left corner of board
        max_corner: Top-right corner of board

    Returns:
        Distance to the specified edge
    """
    if edge == "TOP":
        return max_corner[1] - point[1]
    elif edge == "BOTTOM":
        return point[1] - min_corner[1]
    elif edge == "LEFT":
        return point[0] - min_corner[0]
    elif edge == "RIGHT":
        return max_corner[0] - point[0]
    else:
        # Default to nearest edge
        return distance_to_rect_edge(point, min_corner, max_corner)


def distance_to_board_boundary(
    point: Array,
    component_width: float,
    component_height: float,
    board_min: Array,
    board_max: Array,
) -> Array:
    """
    Compute how far inside the board boundary a component is.

    Takes into account component dimensions (ensures entire component is inside).

    Args:
        point: Component center as (x, y) array
        component_width: Component width
        component_height: Component height
        board_min: Bottom-left corner of board
        board_max: Top-right corner of board

    Returns:
        Minimum distance to boundary (negative if any part is outside)
    """
    half_w = component_width / 2.0
    half_h = component_height / 2.0

    # Effective board boundaries accounting for component size
    effective_min = board_min + jnp.array([half_w, half_h])
    effective_max = board_max - jnp.array([half_w, half_h])

    return distance_to_rect_edge(point, effective_min, effective_max)


# =============================================================================
# Batch Operations for Efficiency
# =============================================================================


def pairwise_distances(points: Array) -> Array:
    """
    Compute pairwise Euclidean distances between all points.

    Args:
        points: Array of shape (N, 2) containing N points

    Returns:
        Array of shape (N, N) with distance[i, j] = distance between points i and j
    """
    # Expand dimensions for broadcasting
    # points[:, None, :] has shape (N, 1, 2)
    # points[None, :, :] has shape (1, N, 2)
    diff = points[:, None, :] - points[None, :, :]  # (N, N, 2)
    return jnp.sqrt(jnp.sum(diff**2, axis=-1))  # (N, N)


def pairwise_distances_squared(points: Array) -> Array:
    """
    Compute pairwise squared Euclidean distances between all points.

    More efficient than pairwise_distances for comparisons.

    Args:
        points: Array of shape (N, 2) containing N points

    Returns:
        Array of shape (N, N) with squared distances
    """
    diff = points[:, None, :] - points[None, :, :]
    return jnp.sum(diff**2, axis=-1)


def batch_point_distance(points1: Array, points2: Array) -> Array:
    """
    Compute distances between corresponding points in two arrays.

    Args:
        points1: Array of shape (N, 2)
        points2: Array of shape (N, 2)

    Returns:
        Array of shape (N,) with distances
    """
    diff = points2 - points1
    return jnp.sqrt(jnp.sum(diff**2, axis=-1))
