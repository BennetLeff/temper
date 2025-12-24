"""
Shared geometric constraint predicates for validation and legalization.

This module provides pure, reusable predicates for checking and computing
violations of geometric constraints such as board boundaries and zone membership.
Used by both validation (checking constraints) and legalization (enforcing constraints).
"""

from __future__ import annotations

from typing import NamedTuple


class BoundaryViolation(NamedTuple):
    """Describes how a component violates board boundaries."""

    left: float  # mm extending beyond left edge (0 if no violation)
    right: float  # mm extending beyond right edge
    bottom: float  # mm extending beyond bottom edge
    top: float  # mm extending beyond top edge

    @property
    def has_violation(self) -> bool:
        """Returns True if any edge is violated."""
        return self.left > 0 or self.right > 0 or self.bottom > 0 or self.top > 0

    @property
    def max_violation(self) -> float:
        """Returns the maximum violation across all edges."""
        return max(self.left, self.right, self.bottom, self.top)

    @property
    def total_violation(self) -> float:
        """Returns the sum of all violations."""
        return self.left + self.right + self.bottom + self.top


class ValidBounds(NamedTuple):
    """Describes the valid placement region for a component center."""

    x_min: float
    x_max: float
    y_min: float
    y_max: float

    def clamp_point(self, x: float, y: float) -> tuple[float, float]:
        """Clamp a point to be within these bounds."""
        return (
            max(self.x_min, min(self.x_max, x)),
            max(self.y_min, min(self.y_max, y)),
        )

    def contains_point(self, x: float, y: float) -> bool:
        """Check if a point is within these bounds."""
        return self.x_min <= x <= self.x_max and self.y_min <= y <= self.y_max


def compute_valid_bounds(
    component_half_width: float,
    component_half_height: float,
    region_x_min: float,
    region_y_min: float,
    region_x_max: float,
    region_y_max: float,
    margin: float = 0.0,
) -> ValidBounds:
    """
    Compute the valid placement region for a component's center.

    Given a component size and a bounding region (board or zone), computes
    the valid range for the component's center position such that the
    component stays entirely within the region.

    Args:
        component_half_width: Half of component width (hw).
        component_half_height: Half of component height (hh).
        region_x_min: Minimum x coordinate of region.
        region_y_min: Minimum y coordinate of region.
        region_x_max: Maximum x coordinate of region.
        region_y_max: Maximum y coordinate of region.
        margin: Additional margin to enforce from region edges.

    Returns:
        ValidBounds describing where the component center can be placed.
    """
    x_min = region_x_min + component_half_width + margin
    x_max = region_x_max - component_half_width - margin
    y_min = region_y_min + component_half_height + margin
    y_max = region_y_max - component_half_height - margin

    # Handle edge case where component is larger than region
    if x_min > x_max:
        x_center = (region_x_min + region_x_max) / 2
        x_min = x_max = x_center
    if y_min > y_max:
        y_center = (region_y_min + region_y_max) / 2
        y_min = y_max = y_center

    return ValidBounds(x_min, x_max, y_min, y_max)


def compute_boundary_violation(
    position_x: float,
    position_y: float,
    component_half_width: float,
    component_half_height: float,
    board_x_min: float,
    board_y_min: float,
    board_x_max: float,
    board_y_max: float,
) -> BoundaryViolation:
    """
    Compute how much a component extends beyond board boundaries.

    Args:
        position_x: Component center x coordinate.
        position_y: Component center y coordinate.
        component_half_width: Half of component width.
        component_half_height: Half of component height.
        board_x_min: Board minimum x (usually 0 or origin_x).
        board_y_min: Board minimum y (usually 0 or origin_y).
        board_x_max: Board maximum x (usually origin_x + width).
        board_y_max: Board maximum y (usually origin_y + height).

    Returns:
        BoundaryViolation describing how component extends beyond edges.
    """
    # Component edges
    comp_x_min = position_x - component_half_width
    comp_x_max = position_x + component_half_width
    comp_y_min = position_y - component_half_height
    comp_y_max = position_y + component_half_height

    # Compute violations (positive = extending beyond)
    left = max(0.0, board_x_min - comp_x_min)
    right = max(0.0, comp_x_max - board_x_max)
    bottom = max(0.0, board_y_min - comp_y_min)
    top = max(0.0, comp_y_max - board_y_max)

    return BoundaryViolation(left, right, bottom, top)


def is_within_bounds(
    position_x: float,
    position_y: float,
    component_half_width: float,
    component_half_height: float,
    region_x_min: float,
    region_y_min: float,
    region_x_max: float,
    region_y_max: float,
    tolerance: float = 1e-6,
) -> bool:
    """
    Check if a component is entirely within a rectangular region.

    Args:
        position_x: Component center x coordinate.
        position_y: Component center y coordinate.
        component_half_width: Half of component width.
        component_half_height: Half of component height.
        region_x_min: Region minimum x.
        region_y_min: Region minimum y.
        region_x_max: Region maximum x.
        region_y_max: Region maximum y.
        tolerance: Small tolerance for floating point comparisons.

    Returns:
        True if component is entirely within region.
    """
    comp_x_min = position_x - component_half_width
    comp_x_max = position_x + component_half_width
    comp_y_min = position_y - component_half_height
    comp_y_max = position_y + component_half_height

    return (
        comp_x_min >= region_x_min - tolerance
        and comp_x_max <= region_x_max + tolerance
        and comp_y_min >= region_y_min - tolerance
        and comp_y_max <= region_y_max + tolerance
    )


def compute_zone_distance(
    position_x: float,
    position_y: float,
    zone_x_min: float,
    zone_y_min: float,
    zone_x_max: float,
    zone_y_max: float,
) -> float:
    """
    Compute signed distance from a point to a rectangular zone.

    This is used by zone loss functions during optimization.

    Returns:
        Negative if inside zone (distance to nearest edge).
        Positive if outside zone (distance to nearest edge).
        Zero if exactly on edge.
    """
    # Clamp point to zone
    clamped_x = max(zone_x_min, min(zone_x_max, position_x))
    clamped_y = max(zone_y_min, min(zone_y_max, position_y))

    # Distance to clamped point
    dx = position_x - clamped_x
    dy = position_y - clamped_y

    # If point is inside, compute negative distance to nearest edge
    if clamped_x == position_x and clamped_y == position_y:
        # Inside the zone
        dist_to_left = position_x - zone_x_min
        dist_to_right = zone_x_max - position_x
        dist_to_bottom = position_y - zone_y_min
        dist_to_top = zone_y_max - position_y
        return -min(dist_to_left, dist_to_right, dist_to_bottom, dist_to_top)
    else:
        # Outside the zone
        return (dx**2 + dy**2) ** 0.5


def point_in_zone(
    position_x: float,
    position_y: float,
    zone_x_min: float,
    zone_y_min: float,
    zone_x_max: float,
    zone_y_max: float,
) -> bool:
    """
    Check if a point is inside a rectangular zone.

    Args:
        position_x: Point x coordinate.
        position_y: Point y coordinate.
        zone_x_min: Zone minimum x.
        zone_y_min: Zone minimum y.
        zone_x_max: Zone maximum x.
        zone_y_max: Zone maximum y.

    Returns:
        True if point is inside zone.
    """
    return (
        zone_x_min <= position_x <= zone_x_max and zone_y_min <= position_y <= zone_y_max
    )
