"""
Zone avoidance loss function for temper-placer.

This module penalizes components being placed inside or too close to restricted zones,
especially high-voltage (HV) zones where low-voltage components should not be placed.

The loss uses a soft penalty approach:
- Negative distance (inside zone) → High penalty
- Distance within margin → Smooth gradient pushing away
- Distance beyond margin → Zero penalty

This allows the optimizer to find paths around zones rather than getting stuck
at hard boundaries.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import jax
import jax.numpy as jnp
from jax import Array

from temper_placer.core.board import Board, Zone
from temper_placer.losses.base import LossContext, LossFunction
from temper_placer.losses.types import LossResult


def signed_distance_to_rectangle(
    point: Array,
    bounds: tuple[float, float, float, float],
) -> Array:
    """
    Compute signed distance from a point to an axis-aligned rectangle.

    Negative = inside rectangle, Positive = outside rectangle.

    Args:
        point: (2,) array [x, y] in mm.
        bounds: (x_min, y_min, x_max, y_max) rectangle bounds.

    Returns:
        Signed distance in mm.
    """
    x, y = point[0], point[1]
    x_min, y_min, x_max, y_max = bounds

    dx_left = x_min - x
    dx_right = x - x_max
    dy_bottom = y_min - y
    dy_top = y - y_max

    dx = jnp.maximum(dx_left, dx_right)
    dy = jnp.maximum(dy_bottom, dy_top)

    outside_x = dx > 0
    outside_y = dy > 0

    corner_dist = jnp.sqrt(jnp.maximum(0.0, dx) ** 2 + jnp.maximum(0.0, dy) ** 2 + 1e-8)
    edge_dist = jnp.maximum(dx, dy)
    inside_dist = jnp.maximum(dx, dy)

    return jnp.where(
        outside_x & outside_y,
        corner_dist,
        jnp.where(outside_x | outside_y, edge_dist, inside_dist),
    )


def _point_in_polygon(point: Array, polygon: Array) -> Array:
    """
    Ray casting algorithm to check if point is inside polygon.

    Args:
        point: (2,) array [x, y].
        polygon: (P, 2) array of vertices.

    Returns:
        Boolean array (scalar) - True if inside.
    """
    x, y = point[0], point[1]
    n = polygon.shape[0]

    inside = jnp.array(0.0)
    for i in range(n):
        x0, y0 = polygon[i]
        x1, y1 = polygon[(i + 1) % n]

        intersect = ((y0 > y) != (y1 > y)) & (x < (x1 - x0) * (y - y0) / (y1 - y0 + 1e-10) + x0)
        inside = inside + jnp.where(intersect, 1.0, 0.0)

    return (inside % 2) > 0


def _edge_distance(point: Array, p0: Array, p1: Array) -> Array:
    """Compute distance from point to line segment p0-p1."""
    edge = p1 - p0
    edge_len_sq = jnp.sum(edge**2)

    edge_len_sq_safe = jnp.where(edge_len_sq < 1e-10, 1.0, edge_len_sq)
    t = jnp.clip(jnp.dot(point - p0, edge) / edge_len_sq_safe, 0.0, 1.0)
    closest = p0 + t * edge
    return jnp.linalg.norm(point - closest)


def signed_distance_to_polygon(
    point: Array,
    polygon: Array,
) -> Array:
    """
    Compute signed distance from a point to a polygon boundary.

    Negative = inside polygon, Positive = outside polygon.

    Args:
        point: (2,) array [x, y] in mm.
        polygon: (P, 2) array of vertices in order (clockwise or CCW).

    Returns:
        Signed distance in mm (negative inside, positive outside).
    """
    n_vertices = polygon.shape[0]

    min_edge_dist = jnp.array(float("inf"))
    for i in range(n_vertices):
        p0 = polygon[i]
        p1 = polygon[(i + 1) % n_vertices]
        dist = _edge_distance(point, p0, p1)
        min_edge_dist = jnp.minimum(min_edge_dist, dist)

    is_inside = _point_in_polygon(point, polygon)

    return jnp.where(is_inside, -min_edge_dist, min_edge_dist)


def compute_zone_avoidance_penalty(
    positions: Array,
    context: LossContext,
    zones_to_avoid: Optional[list[str]] = None,
    margin: float = 2.0,
) -> Array:
    """
    Compute penalty for components being inside forbidden zones.

    Uses max(0, -dist - margin)² to penalize being deep inside the zone.
    Components within 'margin' distance of the boundary have zero penalty.

    This gives gradients that PUSH TOWARD THE BOUNDARY when using gradient descent:
    - Inside zone (dist < -margin): Loss increases with depth, gradient points toward boundary
    - Near boundary (dist >= -margin): Zero loss, no gradient

    Args:
        positions: (N, 2) component center positions in mm.
        context: LossContext with board zones.
        zones_to_avoid: List of zone names to avoid. If None, avoids all HV zones.
        margin: Components inside the zone but within this distance of the
            boundary will not be penalized (grace zone).

    Returns:
        Total zone avoidance penalty (scalar).
    """
    if not context.board.zones:
        return jnp.array(0.0)

    if zones_to_avoid is None:
        zones_to_avoid = [z.name for z in context.board.zones if "HV" in z.name.upper()]

    zone_map = {z.name: z for z in context.board.zones}
    total_penalty = jnp.array(0.0)

    for zone_name in zones_to_avoid:
        if zone_name not in zone_map:
            continue

        zone = zone_map[zone_name]

        if zone.polygon is not None:
            polygon_array = jnp.array(zone.polygon, dtype=jnp.float32)

            for i in range(positions.shape[0]):
                dist = signed_distance_to_polygon(positions[i], polygon_array)
                depth_inside = jnp.maximum(0.0, -dist - margin)
                penalty = depth_inside**2
                total_penalty = total_penalty + penalty
        else:
            bounds = zone.bounds
            for i in range(positions.shape[0]):
                dist = signed_distance_to_rectangle(positions[i], bounds)
                depth_inside = jnp.maximum(0.0, -dist - margin)
                penalty = depth_inside**2
                total_penalty = total_penalty + penalty

    return total_penalty


@dataclass
class ZoneAvoidanceLoss(LossFunction):
    """
    Loss function penalizing components placed inside or too close to forbidden zones.

    This loss prevents low-voltage components from being placed in high-voltage zones
    and maintains safety margins around restricted areas.

    The penalty is smooth (quadratic), allowing gradient-based optimization to find
    paths around zones rather than getting stuck at hard boundaries.

    Attributes:
        zones_to_avoid: List of zone names to avoid. If None, avoids all HV zones.
        margin: Safety margin in mm around zones. Components within this distance
            of a forbidden zone boundary will be penalized.
        weight: Base weight for this loss.

    Example:
        >>> loss = ZoneAvoidanceLoss(margin=3.0)
        >>> result = loss(positions, rotations, context)
        >>> print(f"Zone violation: {result.value}")
    """

    zones_to_avoid: Optional[list[str]] = None
    margin: float = 2.0
    weight: float = 10.0

    @property
    def name(self) -> str:
        return "zone_avoidance"

    def __call__(
        self,
        positions: Array,
        rotations: Array,
        context: LossContext,
        epoch: int = 0,
        total_epochs: int = 1,
        net_virtual_nodes: Array | None = None,
    ) -> LossResult:
        """
        Compute zone avoidance loss.

        Args:
            positions: (N, 2) component positions in mm.
            rotations: (N, 4) soft one-hot rotation indicators (unused).
            context: LossContext with board zones.
            epoch: Current epoch for curriculum learning.
            total_epochs: Total epochs for curriculum learning.

        Returns:
            LossResult with penalty value and breakdown.
        """
        penalty = compute_zone_avoidance_penalty(
            positions,
            context,
            zones_to_avoid=self.zones_to_avoid,
            margin=self.margin,
        )

        return LossResult(
            value=penalty * self.weight,
            breakdown={"zone_avoidance": penalty},
        )

    def weight_schedule(self, epoch: int, total_epochs: int) -> float:
        """
        Get weight multiplier for curriculum learning.

        Zone avoidance is most important early in training to establish
        the basic placement structure, then can be relaxed slightly.

        Args:
            epoch: Current epoch number.
            total_epochs: Total number of epochs.

        Returns:
            Weight multiplier (1.0 after brief warmup).
        """
        if total_epochs <= 1:
            return 1.0
        progress = epoch / total_epochs
        if progress < 0.1:
            return 0.5
        return 1.0
