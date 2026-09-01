"""
Router V6: A* search algorithms and shared route dataclasses.

Part of temper-N6-U6 decomposition.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Final

# A* search primitives (formerly in routing/heuristics.py)
OCTILE_DIAG: Final[float] = math.sqrt(2.0) - 1.0

# Configurable diagonal cost multiplier for the A* inner loop.
# 1.0 = standard octile (diagonal  1.414, cardinal  1.0).
# Lower values incentivise diagonals.  Assign to this module attribute
# directly; the former `metrics.octilinear.add_diagonal_incentive` setter was
# retired along with that module (it had no callers).
DIAGONAL_COST_FACTOR: float = 1.0
_BASE_DIAGONAL_COST: Final[float] = math.sqrt(2.0)
# Cost multiplier for cells already occupied by the same net.
# < 1.0 incentivises tree branches to share copper space rather than
# spreading out, reducing the overall footprint and leaving more free
# cells available for cross-net routes.
_SAME_NET_COST_DISCOUNT: Final[float] = 0.25

_SAME_LAYER_DELTAS: tuple[tuple[int, int], ...] = (
    (0, 1),
    (1, 0),
    (0, -1),
    (-1, 0),
    (1, 1),
    (1, -1),
    (-1, 1),
    (-1, -1),
)


def octile_distance(a: tuple[int, int], b: tuple[int, int]) -> float:
    dx = abs(a[0] - b[0])
    dy = abs(a[1] - b[1])
    return max(dx, dy) + OCTILE_DIAG * min(dx, dy)


def in_bounds(x: int, y: int, width_cells: int, height_cells: int) -> bool:
    return 0 <= x < width_cells and 0 <= y < height_cells


# ---------------------------------------------------------------------------
# Grid-quantization-aware path-point de-duplication.
#
# Root cause of docs/evidence/2026-07-27-acid-trap-elimination.md: pad,
# via, and waypoint coordinates are exact floats from the netlist/footprint
# layout; the routing grid is a fixed-pitch lattice.  ``grid_to_world``
# returns a cell's CENTER, so converting the A* path's grid cells back to
# world coordinates and then separately appending the exact terminal
# (``start_world``/``goal_world``) at each waypoint boundary produced two
# almost-but-not-quite-coincident points -- a near-zero-length "spur"
# whose direction is essentially arbitrary relative to the grid-aligned
# approach direction.  That spur's vertex reliably registers as an acute
# angle (`acid_trap_detection.py`), on very nearly every routed net,
# independent of any real routing decision.  These helpers collapse that
# spur at the three call sites that build path geometry from a grid+exact
# terminal pair (`_astar_route`, `_astar_route_multilayer`,
# `_route_segment_3d`) instead of leaving it for a general corner-mitring
# pass to paper over -- the double-vertex is never generated in the first
# place.
# ---------------------------------------------------------------------------


def grid_quantization_tolerance(cell_size: float) -> float:
    """Max distance between a world point and its grid cell's center.

    ``OccupancyGrid.grid_to_world`` returns a cell's center; any point
    inside that cell (e.g. an off-grid pad whose nearest cell is this
    one) is at most half the cell's diagonal away from that center. Two
    path points closer together than this cannot represent a real
    direction change -- they are the same physical location to within
    the grid's own quantization error, not a routing decision.
    """
    return cell_size * math.sqrt(2.0) / 2.0


def _same_path_layer(a: tuple, b: tuple) -> bool:
    """True if two path-point tuples share a layer.

    Points are ``(x, y)`` (single-layer paths) or ``(x, y, layer)``
    (multi-layer paths). 2-tuples are always same-layer by definition.
    Never merge two 3-tuples on different layers -- that would erase a
    real via transition, not a quantization artifact.
    """
    if len(a) > 2 and len(b) > 2:
        return a[2] == b[2]
    return True


def append_grid_path_point(points: list[tuple], point: tuple, tolerance: float) -> None:
    """Append a grid-derived ``point`` unless it duplicates ``points[-1]``
    to within grid quantization noise.

    Used while walking an A* grid path's cells. Keeps the existing last
    point (typically an exact terminal appended just before this loop
    started) rather than the new, merely-approximate grid-cell center.
    """
    if points and _same_path_layer(points[-1], point):
        last = points[-1]
        if math.hypot(point[0] - last[0], point[1] - last[1]) <= tolerance:
            return
    points.append(point)


def append_exact_terminal_point(points: list[tuple], point: tuple, tolerance: float) -> None:
    """Append an exact terminal ``point`` (pad/via/waypoint location),
    replacing ``points[-1]`` instead of duplicating it when the two are
    within grid quantization noise of each other.

    Used when closing out a segment onto its exact goal coordinate: the
    exact terminal is more authoritative than the grid-cell-center point
    that preceded it, so it replaces rather than merely follows it.
    """
    if points and _same_path_layer(points[-1], point):
        last = points[-1]
        if math.hypot(point[0] - last[0], point[1] - last[1]) <= tolerance:
            points[-1] = point
            return
    points.append(point)


# 8-move direction encoding shared with neighbor_validity.DIRS_8.
# Order: E, SE, S, SW, W, NW, N, NE.
_DIRS_8: tuple[tuple[int, int], ...] = (
    (1, 0),
    (1, 1),
    (0, 1),
    (-1, 1),
    (-1, 0),
    (-1, -1),
    (0, -1),
    (1, -1),
)


@dataclass
class RoutePath:
    """A routed path for a net."""

    net_name: str
    coordinates: list[tuple[float, float]]  # (x, y) path coordinates
    layer_name: str
    path_length: float  # Total length in mm
    forced_segment_count: int = 0  # Number of segments using force routing (fallback)
    # Waypoint indices whose incoming edge was not found by A*.  Kept so a
    # multi-terminal caller can fail closed and name the unresolved terminal.
    failed_waypoint_indices: list[int] = field(default_factory=list)

    @property
    def segment_count(self) -> int:
        """Number of segments in path."""
        return max(0, len(self.coordinates) - 1)

    @property
    def success(self) -> bool:
        """Whether the route was successfully found."""
        return len(self.coordinates) >= 2


@dataclass
class RouteNode3D:
    """3D routing state for multi-layer A* pathfinding."""

    x: int  # Grid x coordinate
    y: int  # Grid y coordinate
    layer: str  # Layer name (e.g., "F.Cu", "B.Cu")

    def __hash__(self):
        return hash((self.x, self.y, self.layer))

    def __eq__(self, other):
        if not isinstance(other, RouteNode3D):
            return False
        return self.x == other.x and self.y == other.y and self.layer == other.layer


@dataclass
class RoutePath3D:
    """A routed path with explicit layer information per segment."""

    net_name: str
    segments: list[tuple[float, float, str]]  # (x, y, layer) coordinates
    via_positions: list[tuple[float, float]]  # Positions where layer changes occur
    path_length: float  # Total length in mm
    via_count: int = 0
    forced_segment_count: int = 0
    failed_waypoint_indices: list[int] = field(default_factory=list)

    @property
    def segment_count(self) -> int:
        """Number of segments in path."""
        return max(0, len(self.segments) - 1)

    def to_route_path(self, default_layer: str = "F.Cu") -> RoutePath:
        """Convert to legacy RoutePath format."""
        coords = [(s[0], s[1]) for s in self.segments]
        return RoutePath(
            net_name=self.net_name,
            coordinates=coords,
            layer_name=default_layer,
            path_length=self.path_length,
            forced_segment_count=self.forced_segment_count,
            failed_waypoint_indices=self.failed_waypoint_indices,
        )


# ``_astar_search`` and its ``_heuristic`` lived here until the Rust port
# (2026-08-18). The faithful f64 replacement is
# ``temper_rust_router_core::astar_search2d``, dispatched from
# ``astar_search2d_rust._astar_search_2d_rust``; the pre-port Python is pinned
# verbatim at ``tests/router_v6/_astar_core_py_oracle.py`` and is what
# ``test_astar_search2d_rust_differential.py`` holds the Rust to, on the real
# corridor-backbone grids the one production call site
# (``_corridor_backbone.route_edge_astar``) actually produces.
#
# ``DIAGONAL_COST_FACTOR`` above stays here: it is the module attribute the
# port reads per call, not a constant baked into the kernel.
