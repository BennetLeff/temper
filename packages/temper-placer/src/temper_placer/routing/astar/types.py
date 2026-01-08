"""Shared types for A* pathfinding module."""

from dataclasses import dataclass
from typing import List, Tuple


@dataclass
class RouteSegment:
    """A segment of a routed path.

    Attributes:
        start: (x, y) start position in mm
        end: (x, y) end position in mm
        layer: Layer index (0-based)
    """

    start: Tuple[float, float]
    end: Tuple[float, float]
    layer: int


@dataclass
class MultiLayerPath:
    """Result of multi-layer pathfinding.

    Attributes:
        segments: List of path segments
        via_positions: List of (x, y, from_layer, to_layer) tuples
        total_cost: Total cost of the path
    """

    segments: List[RouteSegment]
    via_positions: List[Tuple[float, float, int, int]]  # (x, y, from_layer, to_layer)
    total_cost: float
