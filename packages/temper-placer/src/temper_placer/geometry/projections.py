"""
Pure JAX projection operators for C-CAP constraint satisfaction.

This module provides closed-form projection operators for all unary hard
geometric constraints used in the Constraint-Cascade Alternating Projections
(C-CAP) pre-optimization step. Every function is a pure JAX transform:
inputs are JAX arrays, outputs are JAX arrays, no global state or side effects.

Projection operators map a point to the nearest point in a constraint set:

- Zone containment: clamp to polygon interior
- Keepout avoidance: clamp to nearest edge of complement
- Board bounds: orthogonal clamp to [margin, dim - margin]
- HV/LV half-space: project orthogonally onto boundary line
- Edge-mounting: clamp to edge-adjacent strip
- Manufacturing side: clamp to top/bottom half of board
"""

import jax
import jax.numpy as jnp
from jax import Array

from temper_placer.geometry.polygon import (
    nearest_point_on_polygon,
    nearest_point_on_segment,
    point_in_polygon_winding,
)


def identity_projection(point: Array) -> Array:
    """Pass-through for fixed positions — returns the point unchanged.

    Args:
        point: (x, y) array.

    Returns:
        The same point.
    """
    return point


def project_onto_board(
    point: Array,
    margin: float,
    board_w: float,
    board_h: float,
) -> Array:
    """Project a point onto the board interior with edge margin.

    Clamps each coordinate independently to [margin, dim - margin].

    Args:
        point: (x, y) array.
        margin: Edge margin in mm.
        board_w: Board width in mm.
        board_h: Board height in mm.

    Returns:
        Projected (x, y) array within the margin-bounded board rect.
    """
    x = jnp.clip(point[0], margin, board_w - margin)
    y = jnp.clip(point[1], margin, board_h - margin)
    return jnp.array([x, y])


def project_onto_zone(
    point: Array,
    zone_vertices: Array,
    half_w: float = 0.0,
    half_h: float = 0.0,
) -> Array:
    """Project a component center onto a zone interior, respecting half-size.

    If the point is inside the zone (winding-number test), returns identity.
    Otherwise, projects to the nearest point on the zone boundary. When
    half_w > 0 or half_h > 0, the zone interior is shrunk by the half-size
    so the component body fits within the zone.

    For axis-aligned rectangular zones (4 vertices), the half-size shrunken
    interior is computed directly by offsetting the bounds. For generic
    polygon zones (non-4-vertex), half-size offsets are not yet implemented
    (v1 limitation) and the raw nearest-point-on-boundary projection is used.

    Args:
        point: (x, y) component center.
        zone_vertices: (N, 2) zone polygon vertices.
        half_w: Component half-width in mm (default 0).
        half_h: Component half-height in mm (default 0).

    Returns:
        Projected (x, y) array within the zone interior.
    """
    n_vertices = zone_vertices.shape[0]

    # Helper: project onto a rect zone with half-size shrunken interior
    def _rect_projection():
        min_corner = zone_vertices[0]
        max_corner = zone_vertices[2]
        min_x = jnp.minimum(min_corner[0], max_corner[0])
        max_x = jnp.maximum(min_corner[0], max_corner[0])
        min_y = jnp.minimum(min_corner[1], max_corner[1])
        max_y = jnp.maximum(min_corner[1], max_corner[1])
        inner_min_x = min_x + half_w
        inner_max_x = max_x - half_w
        inner_min_y = min_y + half_h
        inner_max_y = max_y - half_h
        # If inner is inverted (component too large), collapse to midpoint
        cx = jnp.where(
            inner_min_x <= inner_max_x,
            jnp.clip(point[0], inner_min_x, inner_max_x),
            (min_x + max_x) / 2.0,
        )
        cy = jnp.where(
            inner_min_y <= inner_max_y,
            jnp.clip(point[1], inner_min_y, inner_max_y),
            (min_y + max_y) / 2.0,
        )
        return jnp.array([cx, cy])

    # Helper: generic polygon projection
    # NOTE: half_w/half_h are accepted but not applied in the generic polygon
    # path. Non-rectangular zone polygons do not support half-size offsets
    # (v1 limitation). For axis-aligned rect zones (4 vertices), the fast
    # path above uses the half-size correctly.
    def _poly_projection():
        inside = point_in_polygon_winding(point, zone_vertices)
        nearest = nearest_point_on_polygon(point, zone_vertices)
        return jnp.where(inside > 0.5, point, nearest)

    # Use rect fast-path when zone has exactly 4 vertices (axis-aligned rect)
    is_rect = n_vertices == 4
    rect_result = _rect_projection()
    poly_result = _poly_projection()
    return jnp.where(is_rect, rect_result, poly_result)


def project_outside_keepout(
    point: Array,
    keepout_rect: tuple[float, float, float, float],
    half_w: float = 0.0,
    half_h: float = 0.0,
) -> Array:
    """Project a component center outside a keepout axis-aligned rectangle.

    The keepout rect is expanded outward by the component half-size, so the
    component body stays entirely outside. The nearest boundary point of the
    expanded rect is found and the component center is snapped there.

    Args:
        point: (x, y) component center.
        keepout_rect: (x_min, y_min, x_max, y_max) keepout bounds in mm.
        half_w: Component half-width in mm (default 0).
        half_h: Component half-height in mm (default 0).

    Returns:
        Projected (x, y) array outside the expanded keepout rect.
    """
    x, y = point[0], point[1]
    kx_min, ky_min, kx_max, ky_max = keepout_rect

    # Expand keepout by component half-size
    ex_min = jnp.asarray(kx_min - half_w, dtype=jnp.float32)
    ex_max = jnp.asarray(kx_max + half_w, dtype=jnp.float32)
    ey_min = jnp.asarray(ky_min - half_h, dtype=jnp.float32)
    ey_max = jnp.asarray(ky_max + half_h, dtype=jnp.float32)

    # Is the point inside the expanded keepout?
    inside = (x >= ex_min) & (x <= ex_max) & (y >= ey_min) & (y <= ey_max)

    # 4 candidate projection points (one per edge of expanded rect)
    c0 = jnp.array([ex_min, jnp.clip(y, ey_min, ey_max)])  # left
    c1 = jnp.array([ex_max, jnp.clip(y, ey_min, ey_max)])  # right
    c2 = jnp.array([jnp.clip(x, ex_min, ex_max), ey_min])  # bottom
    c3 = jnp.array([jnp.clip(x, ex_min, ex_max), ey_max])  # top

    candidates = jnp.stack([c0, c1, c2, c3])
    diffs = candidates - point
    dists_sq = jnp.sum(diffs**2, axis=1)
    nearest_idx = jnp.argmin(dists_sq)

    result = jnp.where(inside, candidates[nearest_idx], point)
    return result


def project_onto_half_plane(
    point: Array,
    boundary_line: float,
    normal_sign: float = 1.0,
) -> Array:
    """Project a point onto a feasible half-plane orthogonally.

    The half-plane is defined by a horizontal boundary line and a sign:
    - normal_sign > 0: feasible region is y >= boundary (HV above boundary)
    - normal_sign < 0: feasible region is y <= boundary (LV below boundary)

    If the point is violating, project orthogonally onto the boundary line
    (i.e., snap y to the boundary value).

    Args:
        point: (x, y) array.
        boundary_line: The y-coordinate of the horizontal boundary.
        normal_sign: +1 for y >= boundary feasible, -1 for y <= boundary.

    Returns:
        Projected (x, y) array on the feasible side.
    """
    x, y = point[0], point[1]
    if normal_sign > 0:
        new_y = jnp.maximum(y, boundary_line)
    else:
        new_y = jnp.minimum(y, boundary_line)
    return jnp.array([x, new_y])


def project_onto_edge_strip(
    point: Array,
    board_w: float,
    board_h: float,
    max_dist: float,
    edge: str,
) -> Array:
    """Project a component center onto an edge-adjacent mounting strip.

    Each board edge defines a strip of width ``max_dist`` adjacent to that
    edge. The component center is clamped to the nearest point within that
    strip.

    Args:
        point: (x, y) component center.
        board_w: Board width in mm.
        board_h: Board height in mm.
        max_dist: Maximum distance from edge in mm.
        edge: Edge identifier: "left", "right", "top", or "bottom".

    Returns:
        Projected (x, y) array within the edge strip.

    Raises:
        ValueError: If ``edge`` is not a valid identifier.
    """
    x, y = point[0], point[1]
    if edge == "left":
        nx = jnp.clip(x, 0.0, max_dist)
        ny = jnp.clip(y, 0.0, board_h)
    elif edge == "right":
        nx = jnp.clip(x, board_w - max_dist, board_w)
        ny = jnp.clip(y, 0.0, board_h)
    elif edge == "top":
        nx = jnp.clip(x, 0.0, board_w)
        ny = jnp.clip(y, board_h - max_dist, board_h)
    elif edge == "bottom":
        nx = jnp.clip(x, 0.0, board_w)
        ny = jnp.clip(y, 0.0, max_dist)
    else:
        valid = {"left", "right", "top", "bottom"}
        raise ValueError(f"Invalid edge '{edge}'. Must be one of {valid}.")
    return jnp.array([nx, ny])


def project_onto_side(
    point: Array,
    board_h: float,
    midline: float,
    side: str,
) -> Array:
    """Project a component center onto a manufacturing side of the board.

    "top" side constrains y < midline, "bottom" side constrains y >= midline.

    Args:
        point: (x, y) component center.
        board_h: Board height in mm (unused, kept for API consistency).
        midline: The y-coordinate dividing top from bottom (board_h / 2).
        side: "top" or "bottom".

    Returns:
        Projected (x, y) array.

    Raises:
        ValueError: If ``side`` is not "top" or "bottom".
    """
    x, y = point[0], point[1]
    if side == "top":
        return jnp.array([x, jnp.minimum(y, midline)])
    elif side == "bottom":
        return jnp.array([x, jnp.maximum(y, midline)])
    else:
        raise ValueError(f"Invalid side '{side}'. Must be 'top' or 'bottom'.")
