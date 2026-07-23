"""PCL parsing utilities: unit conversion, enum parsing, and PCLParseError."""

from __future__ import annotations

from typing import Any

from temper_placer.pcl.constraints import (
    Axis,
    BoardSide,
    ConstraintTier,
    DistanceMetric,
    EdgeType,
)


class PCLParseError(Exception):
    """Error parsing a PCL constraint definition."""

    pass


def _parse_distance_with_unit(value: Any) -> float:
    """Parse distance value with optional unit suffix.

    Supports:
    - Plain float (assumed mm)
    - String with unit: "10mm", "5mil", "0.1in"

    Args:
        value: Distance value (float or string)

    Returns:
        Distance in millimeters

    Raises:
        PCLParseError: If unit is invalid or value cannot be parsed
    """
    if isinstance(value, (int, float)):
        return float(value)

    if not isinstance(value, str):
        raise PCLParseError(f"Distance must be number or string with unit, got {type(value)}")

    value = value.strip()

    for i, char in enumerate(value):
        if not (char.isdigit() or char in ".-"):
            number_str = value[:i]
            unit_str = value[i:].strip().lower()
            break
    else:
        return float(value)

    try:
        number = float(number_str)
    except ValueError as e:
        raise PCLParseError(f"Invalid distance value: {value}") from e

    if number < 0:
        raise PCLParseError(f"Distance cannot be negative: {value}")

    if unit_str in ("mm", ""):
        return number
    elif unit_str == "mil":
        return number * 0.0254
    elif unit_str == "in":
        return number * 25.4
    elif unit_str == "cm":
        return number * 10.0
    else:
        raise PCLParseError(f"Unknown distance unit: {unit_str}")


def _parse_tier(tier_value: Any) -> ConstraintTier:
    """Parse tier from integer or string."""
    if isinstance(tier_value, int):
        if tier_value == 1:
            return ConstraintTier.HARD
        elif tier_value == 2:
            return ConstraintTier.STRONG
        elif tier_value == 3:
            return ConstraintTier.SOFT
        else:
            raise PCLParseError(f"Invalid tier value: {tier_value}. Must be 1, 2, or 3")

    if isinstance(tier_value, str):
        tier_lower = tier_value.lower()
        if tier_lower in ("hard", "1"):
            return ConstraintTier.HARD
        elif tier_lower in ("strong", "2"):
            return ConstraintTier.STRONG
        elif tier_lower in ("soft", "3"):
            return ConstraintTier.SOFT
        else:
            raise PCLParseError(f"Invalid tier: {tier_value}. Must be HARD/STRONG/SOFT or 1/2/3")

    raise PCLParseError(f"Tier must be integer or string, got {type(tier_value)}")


def _parse_metric(metric_value: str | None) -> DistanceMetric:
    """Parse distance metric from string."""
    if metric_value is None:
        return DistanceMetric.EDGE_TO_EDGE

    metric_lower = metric_value.lower().replace("-", "_")
    for dm in DistanceMetric:
        if dm.value == metric_lower:
            return dm

    raise PCLParseError(
        f"Invalid metric: {metric_value}. Valid: edge_to_edge, center_to_center, pin_to_pin"
    )


def _parse_axis(axis_value: str) -> Axis:
    """Parse axis from string."""
    axis_lower = axis_value.lower()

    if axis_lower in ("horizontal", "h"):
        return Axis.X
    elif axis_lower in ("vertical", "v"):
        return Axis.Y

    for axis in Axis:
        if axis.value == axis_lower:
            return axis

    raise PCLParseError(
        f"Invalid axis: {axis_value}. Valid: x, y, major, minor, horizontal, vertical"
    )


def _parse_board_side(side_value: str) -> BoardSide:
    """Parse board side from string."""
    side_lower = side_value.lower()
    for side in BoardSide:
        if side.value == side_lower:
            return side

    raise PCLParseError(f"Invalid side: {side_value}. Valid: top, bottom, left, right")


def _parse_edge_type(edge_value: str) -> EdgeType:
    """Parse edge type from string."""
    edge_lower = edge_value.lower()
    for edge in EdgeType:
        if edge.value == edge_lower:
            return edge

    raise PCLParseError(f"Invalid edge type: {edge_value}. Valid: flush, near, overhang")
