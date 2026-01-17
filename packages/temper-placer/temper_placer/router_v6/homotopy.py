"""
Router V6 Stage 2.2: Homotopy Classification

Routes partition into homotopy classes based on how they wind around obstacles.
Two routes are homotopic iff one can be continuously deformed into the other
without crossing obstacles.

H-signature encoding: +O₁ -O₂ +O₃ means 'right of O₁, left of O₂, right of O₃'.

RRT explores one homotopy class (whichever random sampling finds). If that class
is congested, it fails — even when another class has capacity.

Part of temper-flhd (Phase 3 - Homotopy Routing)
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union
from temper_placer.router_v6.stage0_data import ParsedPCB


class Side(Enum):
    """Side of an obstacle relative to path traversal."""

    LEFT = -1
    RIGHT = 1

    def __lt__(self, other: "Side") -> bool:
        return self.value < other.value

    def __le__(self, other: "Side") -> bool:
        return self.value <= other.value

    def __gt__(self, other: "Side") -> bool:
        return self.value > other.value

    def __ge__(self, other: "Side") -> bool:
        return self.value >= other.value


@dataclass(frozen=True, order=True)
class HSignatureElement:
    """Single element of H-signature: obstacle id and side."""

    obstacle_id: str
    side: Side


@dataclass(frozen=True, order=True)
class HSignature:
    """
    Homotopy signature encoding path's topological relationship to obstacles.

    The signature is a sequence of (obstacle_id, side) pairs representing
    which side of each obstacle the path passes on. For a path that goes
    right of obstacle O1, left of O2, and right of O3, the signature is:
    (+O₁, -O₂, +O₃) or equivalently [(O1, RIGHT), (O2, LEFT), (O3, RIGHT)]

    Two paths are homotopic iff their H-signatures match.
    """

    elements: tuple[HSignatureElement, ...] = field(default_factory=tuple)

    def __str__(self) -> str:
        parts = []
        for elem in self.elements:
            sign = "+" if elem.side == Side.RIGHT else "-"
            parts.append(f"{sign}{elem.obstacle_id}")
        return " ".join(parts) if parts else "∅"

    def __repr__(self) -> str:
        return f"HSignature({self.elements})"


def compute_h_signature(
    path: list[tuple[float, float]],
    obstacles: dict[str, Polygon | tuple[Polygon, ...]],
) -> HSignature:
    """
    Compute the H-signature for a path given a set of obstacles.

    The signature is computed by tracking which side of each obstacle the path
    passes on. This is determined by checking the winding of the path around
    each obstacle's reference point.

    Args:
        path: List of (x, y) coordinates defining the path.
        obstacles: Dictionary mapping obstacle IDs to their polygons.

    Returns:
        HSignature representing the topological class of the path.

    Example:
        >>> path = [(0, 0), (5, 0), (5, 5), (10, 5)]
        >>> obstacles = {"O1": Polygon([(3, -1), (3, 1), (7, 1), (7, -1)])}
        >>> sig = compute_h_signature(path, obstacles)
        >>> str(sig)
        '+O1'
    """
    if len(path) < 2:
        return HSignature()

    path_line = LineString(path)
    elements = []

    for obs_id, obs_poly in obstacles.items():
        if isinstance(obs_poly, tuple):
            obs_poly = unary_union(list(obs_poly))

        if isinstance(obs_poly, Polygon):
            if obs_poly.is_empty:
                continue
            side = _get_path_side_of_obstacle(path_line, obs_poly)
        else:
            side = None

        if side is not None:
            elements.append(HSignatureElement(obs_id, side))

    return HSignature(tuple(sorted(elements)))


def _get_path_side_of_obstacle(
    path: LineString,
    obstacle: Polygon,
) -> Side | None:
    """
    Determine which side of an obstacle a path passes on.

    Uses ray casting to count crossings. A path that goes predominantly
    on one side will have consistent winding behavior.

    Args:
        path: The path as a LineString.
        obstacle: The obstacle polygon.

    Returns:
        Side.LEFT or Side.RIGHT, or None if path doesn't intersect obstacle region.
    """
    if path.is_empty or obstacle.is_empty:
        return None

    path_bounds = path.bounds
    obs_centroid = obstacle.centroid

    if not obstacle.contains(path) and not path.intersects(obstacle):
        return None

    closest_point = path.interpolate(path.project(obs_centroid))
    path_direction = _get_path_direction_at_point(path, closest_point)

    if path_direction is None:
        return None

    return _get_side_relative_to_obstacle(obs_centroid, closest_point, path_direction)


def _get_path_direction_at_point(
    path: LineString,
    point: Point,
) -> tuple[float, float] | None:
    """
    Get the direction of the path at a given point.

    Args:
        path: The path LineString.
        point: A point on or near the path.

    Returns:
        Unit direction vector (dx, dy) or None if cannot determine.
    """
    nearest_point = path.interpolate(path.project(point))
    path_coords = list(path.coords)

    try:
        idx = next(
            i
            for i, coord in enumerate(path_coords)
            if (coord[0] - nearest_point.x) ** 2 + (coord[1] - nearest_point.y) ** 2 < 1e-6
        )
    except StopIteration:
        return None

    if idx < len(path_coords) - 1:
        next_coord = path_coords[idx + 1]
        dx = next_coord[0] - nearest_point.x
        dy = next_coord[1] - nearest_point.y
    elif idx > 0:
        prev_coord = path_coords[idx - 1]
        dx = nearest_point.x - prev_coord[0]
        dy = nearest_point.y - prev_coord[1]
    else:
        return None

    length = (dx**2 + dy**2) ** 0.5
    if length < 1e-9:
        return None

    return (dx / length, dy / length)


def _get_side_relative_to_obstacle(
    obstacle_center: Point,
    path_point: Point,
    path_direction: tuple[float, float],
) -> Side:
    """
    Determine which side of an obstacle the path is on.

    Uses cross product to determine left/right relative to path direction.

    Args:
        obstacle_center: Center of the obstacle.
        path_point: Point on the path near the obstacle.
        path_direction: Direction vector of path at path_point.

    Returns:
        Side.LEFT or Side.RIGHT.
    """
    dx = obstacle_center.x - path_point.x
    dy = obstacle_center.y - path_point.y

    cross = path_direction[0] * dy - path_direction[1] * dx

    return Side.LEFT if cross < 0 else Side.RIGHT


def enumerate_homotopy_classes(
    source: tuple[float, float],
    target: tuple[float, float],
    obstacles: dict[str, Polygon | tuple[Polygon, ...]],
) -> list[HSignature]:
    """
    Enumerate all possible homotopy classes for paths from source to target.

    For k obstacles, there are up to 2^k possible homotopy classes
    (left/right of each obstacle). This method uses BFS on the obstacle
    arrangement to find all valid classes.

    Args:
        source: Starting point (x, y).
        target: Ending point (x, y).
        obstacles: Dictionary mapping obstacle IDs to their polygons.

    Returns:
        List of HSignatures representing all possible homotopy classes.
        Classes are pruned if geometrically impossible (e.g., obstacle
        completely blocks the path).

    Example:
        >>> source, target = (0, 0), (10, 10)
        >>> obstacles = {"O1": Polygon([(4, -1), (4, 1), (6, 1), (6, -1)])}
        >>> classes = enumerate_homotopy_classes(source, target, obstacles)
        >>> len(classes)
        2
    """
    obstacle_list = list(obstacles.items())
    n = len(obstacle_list)

    classes = []
    source_point = Point(source)
    target_point = Point(target)

    for bitmask in range(1 << n):
        signature_elements = []
        valid = True

        for i, (obs_id, obs_poly) in enumerate(obstacle_list):
            if isinstance(obs_poly, tuple):
                obs_poly = unary_union(list(obs_poly))

            if obs_poly.is_empty:
                continue

            if not isinstance(obs_poly, Polygon):
                continue

            side = Side.RIGHT if ((bitmask >> i) & 1) == 0 else Side.LEFT
            signature_elements.append(HSignatureElement(obs_id, side))

            if not _is_geometrically_possible(source_point, target_point, obs_poly, side):
                valid = False
                break

        if valid:
            classes.append(HSignature(tuple(signature_elements)))

    return sorted(classes)


def _is_geometrically_possible(
    source: Point,
    target: Point,
    obstacle: Polygon,
    preferred_side: Side,
) -> bool:
    """
    Check if a path on the preferred side is geometrically possible.

    Args:
        source: Starting point.
        target: Ending point.
        obstacle: The obstacle polygon.
        preferred_side: The side we want to pass on.

    Returns:
        True if geometrically possible, False otherwise.
    """
    if obstacle.is_empty:
        return True

    source_side = _point_side_of_obstacle(source, obstacle)
    target_side = _point_side_of_obstacle(target, obstacle)

    if source_side is None and target_side is None:
        return True

    if source_side == preferred_side and target_side == preferred_side:
        return True

    return _can_bypass_obstacle(source, target, obstacle, preferred_side)


def _point_side_of_obstacle(point: Point, obstacle: Polygon) -> Side | None:
    """
    Determine which side of an obstacle a point is on.

    Args:
        point: The point to check.
        obstacle: The obstacle polygon.

    Returns:
        Side.LEFT or Side.RIGHT, or None if point is inside/near obstacle.
    """
    if obstacle.contains(point):
        return None

    if obstacle.bounds[0] - 1e-6 <= point.x <= obstacle.bounds[2] + 1e-6:
        if obstacle.bounds[1] - 1e-6 <= point.y <= obstacle.bounds[3] + 1e-6:
            return None

    centroid = obstacle.centroid
    dx = point.x - centroid.x
    dy = point.y - centroid.y

    if abs(dx) < 1e-9 and abs(dy) < 1e-9:
        return None

    quadrant = (0 if point.x >= centroid.x else 1) | (0 if point.y >= centroid.y else 2)
    return Side.RIGHT if quadrant in (0, 3) else Side.LEFT


def _can_bypass_obstacle(
    source: Point,
    target: Point,
    obstacle: Polygon,
    side: Side,
) -> bool:
    """
    Check if obstacle can be bypassed on the given side.

    Args:
        source: Starting point.
        target: Ending point.
        obstacle: The obstacle polygon.
        side: The side to bypass on.

    Returns:
        True if bypass is possible, False if blocked.
    """
    bounds = obstacle.bounds
    minx, miny, maxx, maxy = bounds

    if side == Side.LEFT:
        bypass_polygon = Polygon(
            [
                (minx - 1000, miny - 1000),
                (minx - 1000, maxy + 1000),
                (maxx + 1000, maxy + 1000),
                (maxx + 1000, miny - 1000),
            ]
        )
    else:
        bypass_polygon = Polygon(
            [
                (minx - 1000, miny - 1000),
                (minx - 1000, maxy + 1000),
                (maxx + 1000, maxy + 1000),
                (maxx + 1000, miny - 1000),
            ]
        )

    if isinstance(bypass_polygon, Polygon):
        bypass_polygon = bypass_polygon.difference(obstacle)

    direct_line = LineString([source, target])

    if isinstance(bypass_polygon, Polygon) and not bypass_polygon.is_empty:
        exterior = bypass_polygon.exterior
        return (
            not direct_line.intersects(exterior)
            or bypass_polygon.contains(source)
            or bypass_polygon.contains(target)
        )

    return True


def paths_are_homotopic(
    path1: list[tuple[float, float]],
    path2: list[tuple[float, float]],
    obstacles: dict[str, Polygon | tuple[Polygon, ...]],
) -> bool:
    """
    Check if two paths are homotopic (belong to the same topological class).

    Two paths are homotopic iff they have the same H-signature.

    Args:
        path1: First path as list of (x, y) coordinates.
        path2: Second path as list of (x, y) coordinates.
        obstacles: Dictionary mapping obstacle IDs to their polygons.

    Returns:
        True if paths are homotopic, False otherwise.

    Example:
        >>> path1 = [(0, 0), (5, 0), (5, 5), (10, 5)]
        >>> path2 = [(0, 0), (5, -1), (5, 6), (10, 5)]
        >>> obstacles = {"O1": Polygon([(3, -1), (3, 1), (7, 1), (7, -1)])}
        >>> paths_are_homotopic(path1, path2, obstacles)
        True
    """
    sig1 = compute_h_signature(path1, obstacles)
    sig2 = compute_h_signature(path2, obstacles)

    return sig1 == sig2


def build_obstacle_map(pcb: ParsedPCB) -> dict[str, Polygon]:
    """
    Build a simplified obstacle map from PCB data for homotopy analysis.

    This is a convenience function that extracts obstacles from a ParsedPCB
    in a format suitable for homotopy computation.

    Args:
        pcb: Parsed PCB data.

    Returns:
        Dictionary mapping obstacle IDs to Shapely Polygons.
    """
    from temper_placer.router_v6.obstacle_map import build_obstacle_map as full_build

    full_map = full_build(pcb, [])

    result = {}
    layer_name = pcb.stackup.layers[0].name if pcb.stackup.layers else "F.Cu"

    obstacles_on_layer = full_map.get(layer_name)
    if obstacles_on_layer:
        if hasattr(obstacles_on_layer, "geoms"):
            for i, poly in enumerate(obstacles_on_layer.geoms):
                result[f"O{i}"] = poly
        else:
            result["O0"] = obstacles_on_layer

    return result
