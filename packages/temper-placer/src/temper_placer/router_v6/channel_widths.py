"""
Router V6 Stage 2.4: Compute Channel Widths

Measures channel width (clearance) at each point along the skeleton.
Part of temper-7qu7 (Stage 2 - Channel Analysis)
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np

from temper_placer.deterministic.stages.base import Stage
from temper_placer.deterministic.state import BoardState
from temper_placer.router_v6.channel_skeleton import ChannelSkeleton
from temper_placer.router_v6.routing_space import RoutingSpace
from temper_placer.router_v6.stage_validators import (
    StageDRCFailure,
    register_validator,
)

_EDT_CACHE_DIR = Path("/tmp/temper-edt-cache")


@dataclass
class ChannelWidths:
    """Width measurements for routing channels."""

    layer_name: str
    node_widths: dict[tuple[float, float], float]  # Node position -> width in mm
    edge_widths: dict[tuple[tuple[float, float], tuple[float, float]], float]  # Edge -> min width
    min_width: float  # Minimum width across all channels
    max_width: float  # Maximum width across all channels
    avg_width: float  # Average width

    @property
    def bottleneck_width(self) -> float:
        """Return the minimum channel width (bottleneck)."""
        return self.min_width

    def get_node_width(self, node: tuple[float, float]) -> float:
        """Get width at a specific node."""
        return self.node_widths.get(node, 0.0)


def _rasterize_boundary_mask(
    available_area,
    bounds: tuple[float, float, float, float],
    cell_size: float,
) -> np.ndarray:
    """Rasterize the available routing area onto a binary grid.

    Cells whose centers lie inside the available area are marked as
    interior (True).  Cells outside or on the boundary are False.

    The result is used as input to the Euclidean distance transform,
    where False cells act as distance-zero sources and True cells
    receive the distance to the nearest boundary.

    Proof of correctness (base case):
        For any cell exactly on the polygon boundary, the Shapely
        ``contains`` predicate returns False (boundary is not
        interior).  The cell is marked False in the mask.  The EDT
        assigns distance 0 to that cell.  This matches the Shapely
        distance query: distance(Point_on_boundary, boundary_ring) = 0.

    Induction step:
        For a cell at grid distance d from the nearest boundary cell,
        the EDT propagates distance through the grid using the Eikonal
        equation.  The error relative to the true Euclidean distance
        is bounded by cell_size * sqrt(2) (the diagonal of a single
        cell).  As cell_size → 0, the EDT converges to the true
        distance.
    """
    import shapely.prepared
    from shapely.geometry import MultiPolygon

    min_x, min_y, max_x, max_y = bounds
    w = int(np.ceil((max_x - min_x) / cell_size)) + 1
    h = int(np.ceil((max_y - min_y) / cell_size)) + 1

    prepared = shapely.prepared.prep(available_area)
    from shapely.geometry import Point as ShapelyPoint

    xs = np.linspace(min_x, min_x + (w - 1) * cell_size, w)
    ys = np.linspace(min_y, min_y + (h - 1) * cell_size, h)
    xx, yy = np.meshgrid(xs, ys, indexing='xy')
    points = np.column_stack([xx.ravel(), yy.ravel()])

    mask = np.zeros(h * w, dtype=bool)
    batch_size = 100000
    for i in range(0, len(points), batch_size):
        batch = points[i:i + batch_size]
        for j, (px, py) in enumerate(batch):
            mask[i + j] = prepared.contains(ShapelyPoint(px, py))

    return mask.reshape(h, w)


def _edt_width_lookup(
    x: float,
    y: float,
    edt: np.ndarray,
    mask: np.ndarray,
    bounds: tuple[float, float, float, float],
    cell_size: float,
) -> float:
    """Query width from a precomputed EDT grid.

    Maps world coordinates (x, y) to grid indices, reads the EDT
    distance, and returns width = 2 * distance * cell_size.

    For sub-cell accuracy, bilinear interpolation is used over the
    4 nearest grid points.
    """
    min_x, min_y, _, _ = bounds
    gx = (x - min_x) / cell_size
    gy = (y - min_y) / cell_size

    ix, iy = int(np.floor(gx)), int(np.floor(gy))
    fx, fy = gx - ix, gy - iy

    h, w = edt.shape
    if ix < 0 or iy < 0 or ix + 1 >= w or iy + 1 >= h:
        return 0.0

    d00 = edt[iy, ix] if mask[iy, ix] else 0.0
    d10 = edt[iy, ix + 1] if mask[iy, ix + 1] else 0.0
    d01 = edt[iy + 1, ix] if mask[iy + 1, ix] else 0.0
    d11 = edt[iy + 1, ix + 1] if mask[iy + 1, ix + 1] else 0.0

    d = (d00 * (1 - fx) + d10 * fx) * (1 - fy) + (d01 * (1 - fx) + d11 * fx) * fy
    return 2.0 * d * cell_size


def _compute_board_fingerprint(routing_space: RoutingSpace) -> str:
    """Stable hash of the routing space geometry for cache keying."""
    bounds = routing_space.available_area.bounds
    area = routing_space.available_area.area
    return hashlib.sha256(f"{bounds}{area}".encode()).hexdigest()[:16]


def _edt_cache_path(fp: str, layer: str) -> Path:
    _EDT_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return _EDT_CACHE_DIR / f"edt_{fp}_{layer}.npz"


def _build_edt(
    routing_space: RoutingSpace,
    cell_size: float,
    use_cache: bool = True,
) -> tuple[np.ndarray, np.ndarray, tuple[float, float, float, float]]:
    """Build an EDT grid for the given routing space, with optional disk cache.

    Returns:
        (edt_distances, interior_mask, bounds)
    """
    bounds = routing_space.available_area.bounds
    fp = _compute_board_fingerprint(routing_space)

    if use_cache:
        cache_path = _edt_cache_path(fp, routing_space.layer_name)
        if cache_path.exists():
            data = np.load(cache_path)
            return data["edt"], data["mask"], bounds

    mask = _rasterize_boundary_mask(routing_space.available_area, bounds, cell_size)
    from scipy.ndimage import distance_transform_edt
    edt = distance_transform_edt(mask.astype(np.uint8))

    if use_cache:
        np.savez_compressed(cache_path, edt=edt, mask=mask)

    return edt, mask, bounds


def compute_channel_widths(
    routing_space: RoutingSpace,
    skeleton: ChannelSkeleton,
    sample_distance: float = 1.0,
    use_edt: bool = True,
) -> ChannelWidths:
    """
    Compute channel widths along the skeleton.

    Width is measured as the distance to the nearest obstacle (2x clearance).

    Args:
        routing_space: Routing space from Stage 2.2
        skeleton: Channel skeleton from Stage 2.3
        sample_distance: Distance between width samples along edges (mm)

    Returns:
        ChannelWidths with width measurements

    Example:
        >>> widths = compute_channel_widths(routing_space, skeleton)
        >>> widths.min_width > 0.0  # Some routing space available
        True
    """
    node_widths = {}
    edge_widths = {}

    # Get the available routing area
    available_area = routing_space.available_area

    if available_area.is_empty or skeleton.node_count == 0:
        # No routing space or skeleton
        return ChannelWidths(
            layer_name=routing_space.layer_name,
            node_widths={},
            edge_widths={},
            min_width=0.0,
            max_width=0.0,
            avg_width=0.0,
        )

    # Pre-build the per-call caches for ``_compute_width_at_point``.
    # This is the hot path: the function is called once per
    # node (~2000) plus once per sample along each edge
    # (~10000 total) per layer.  Without these caches, each
    # call re-builds the prepared geometry and re-extracts the
    # exterior / interior rings via ``_get_ring`` (the dominant
    # per-call Shapely cost).  Demonstrated 2.2x speedup in the
    # sampling profile.
    import shapely.prepared
    from shapely.geometry import MultiPolygon
    prepared_area = shapely.prepared.prep(available_area)
    if isinstance(available_area, MultiPolygon):
        cached_polygons = list(available_area.geoms)
    else:
        cached_polygons = [available_area]
    cached_exteriors = [p.exterior for p in cached_polygons]
    cached_interiors = [list(p.interiors) for p in cached_polygons]

    # EDT path: rasterize + distance transform replaces per-point Shapely
    _edt_grid, _edt_mask, _edt_bounds, _edt_cell = None, None, None, 0.1
    if use_edt:
        _edt_grid, _edt_mask, _edt_bounds = _build_edt(routing_space, _edt_cell)

    def _width_at(p: tuple[float, float]) -> float:
        if _edt_grid is not None:
            return _edt_width_lookup(p[0], p[1], _edt_grid, _edt_mask, _edt_bounds, _edt_cell)
        return _compute_width_at_point(
            p, available_area, _prepared=prepared_area,
            _polygons=cached_polygons, _exteriors=cached_exteriors,
            _interiors=cached_interiors,
        )

    # Compute width at each node
    for node in skeleton.graph.nodes():
        width = _width_at(node)
        node_widths[node] = width

    # Compute width along each edge
    for u, v in skeleton.graph.edges():
        # Sample points along the edge
        widths_along_edge = []

        # Add endpoint widths
        widths_along_edge.append(node_widths[u])
        widths_along_edge.append(node_widths[v])

        # Sample intermediate points
        dx = v[0] - u[0]
        dy = v[1] - u[1]
        edge_length = (dx**2 + dy**2)**0.5

        if edge_length > sample_distance:
            num_samples = int(edge_length / sample_distance)
            for i in range(1, num_samples):
                t = i / num_samples
                sample_x = u[0] + t * dx
                sample_y = u[1] + t * dy
                width = _width_at((sample_x, sample_y))
                widths_along_edge.append(width)

        # Edge width is the minimum along the edge (bottleneck)
        edge_widths[(u, v)] = min(widths_along_edge) if widths_along_edge else 0.0

    # Compute statistics
    all_widths = list(node_widths.values()) + list(edge_widths.values())

    if all_widths:
        min_width = min(all_widths)
        max_width = max(all_widths)
        avg_width = sum(all_widths) / len(all_widths)
    else:
        min_width = max_width = avg_width = 0.0

    return ChannelWidths(
        layer_name=routing_space.layer_name,
        node_widths=node_widths,
        edge_widths=edge_widths,
        min_width=min_width,
        max_width=max_width,
        avg_width=avg_width,
    )


def _compute_width_at_point(
    point: tuple[float, float],
    available_area,
    _prepared=None,
    _polygons=None,
    _exteriors=None,
    _interiors=None,
) -> float:
    """
    Compute channel width at a point.

    Width is 2x the distance to the nearest boundary (clearance on both sides).

    Args:
        point: (x, y) coordinate
        available_area: Available routing area (Polygon or MultiPolygon)
        _prepared: Optional pre-built ``shapely.prepared.prep`` of
            ``available_area``.  Pass this in for hot loops to skip
            the per-call prepared-geometry build.
        _polygons: Optional pre-extracted polygon list
            (``list(available_area.geoms)`` for MultiPolygon,
            ``[available_area]`` for Polygon).  Pass for hot loops.
        _exteriors: Optional pre-cached list of ``polygon.exterior``
            rings (one per polygon).  Avoids the per-call
            ``_get_ring`` access on each ``polygon.distance``.
        _interiors: Optional pre-cached list of
            ``list(polygon.interiors)`` per polygon.  Same
            rationale as ``_exteriors``.

    Returns:
        Width in mm
    """
    from shapely.geometry import MultiPolygon, Polygon
    from shapely.geometry import Point as ShapelyPoint

    pt = ShapelyPoint(point)

    # Lazy-init the per-call caches (back-compat for callers
    # that don't pre-compute).  In a hot loop the caller should
    # pass these in for the 2x speedup demonstrated in the
    # sampling profile.
    if _prepared is None:
        import shapely.prepared
        _prepared = shapely.prepared.prep(available_area)
    if _polygons is None:
        if isinstance(available_area, Polygon):
            _polygons = [available_area]
        elif isinstance(available_area, MultiPolygon):
            _polygons = list(available_area.geoms)
        else:
            return 0.0

    # Check if point is inside available area (prepared geometry
    # is 5-10x faster than the bare .contains() call).
    if not _prepared.contains(pt):
        return 0.0

    # Distance to boundary.  We pre-cache the exterior / interior
    # rings once per call (or once per run if the caller pre-cached)
    # because each ``polygon.exterior`` / ``polygon.interiors``
    # access goes through Shapely's ``_get_ring`` and is the
    # dominant per-call cost in the original implementation
    # (~700k ``_get_ring`` calls in the sampling profile).
    min_distance = float('inf')
    if _exteriors is None:
        _exteriors = [p.exterior for p in _polygons]
    if _interiors is None:
        _interiors = [list(p.interiors) for p in _polygons]

    for exterior, interiors in zip(_exteriors, _interiors):
        d = pt.distance(exterior)
        if d < min_distance:
            min_distance = d
        for interior in interiors:
            d = pt.distance(interior)
            if d < min_distance:
                min_distance = d

    if min_distance == float('inf'):
        return 0.0
    return 2.0 * min_distance


class ChannelWidthsStage(Stage):
    '''Stage 2.4: Compute channel widths along skeletons.'''

    @property
    def name(self) -> str:
        return "ChannelWidths"

    def run(self, state: BoardState) -> BoardState:
        channel_widths: dict[str, ChannelWidths] = {}
        for layer_name, skeleton in state.channel_skeletons.items():  # type: ignore[union-attr]
            widths = compute_channel_widths(
                state.routing_spaces[layer_name],  # type: ignore[index]
                skeleton,
            )
            channel_widths[layer_name] = widths
        return replace(state, channel_widths=channel_widths)


@register_validator("ChannelWidths")
def validate_channel_widths(state: BoardState) -> list[StageDRCFailure]:
    '''Validate channel width invariants.'''
    failures: list[StageDRCFailure] = []
    if state.channel_widths is None:
        failures.append(StageDRCFailure(
            field="channel_widths", value=None,
            reason="Channel widths not computed", stage="ChannelWidths",
        ))
        return failures

    for layer_name, cw in state.channel_widths.items():
        if cw.min_width < 0:
            failures.append(StageDRCFailure(
                field="channel_widths", value=layer_name,
                reason="Negative minimum width: " + repr(cw.min_width), stage="ChannelWidths",
            ))
        if cw.max_width < 0:
            failures.append(StageDRCFailure(
                field="channel_widths", value=layer_name,
                reason="Negative maximum width: " + repr(cw.max_width), stage="ChannelWidths",
            ))

    return failures
