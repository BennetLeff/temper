"""
Router V6 Stage 2.4: Compute Channel Widths

Measures channel width (clearance) at each point along the skeleton.
Part of temper-7qu7 (Stage 2 - Channel Analysis)
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from pathlib import Path
from typing import cast

import numpy as np
import temper_geometry as _tg

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
    import shapely

    min_x, min_y, max_x, max_y = bounds
    w = int(np.ceil((max_x - min_x) / cell_size)) + 1
    h = int(np.ceil((max_y - min_y) / cell_size)) + 1

    xs = np.linspace(min_x, min_x + (w - 1) * cell_size, w)
    ys = np.linspace(min_y, min_y + (h - 1) * cell_size, h)
    xx, yy = np.meshgrid(xs, ys, indexing="xy")

    # Vectorised, not looped. This previously built one shapely Point per grid
    # cell and called prepared.contains() on it -- the nominal batching was
    # cosmetic, since the inner loop still ran per-point in Python. A single
    # test (test_empty_board_infinite_capacity, 20 Hypothesis examples) spent
    # ~90s making 14,024,826 such calls, and this function was ~90% of the
    # runtime of the four slowest tests in the invariant suite.
    #
    # shapely.contains_xy is the same `contains` predicate evaluated in C over
    # arrays, so the boundary semantics the docstring's proof relies on are
    # unchanged: contains excludes the boundary, boundary cells stay False, and
    # the EDT keeps them as distance-zero sources. Verified bit-identical to
    # the old implementation across plain, multi-cutout, boundary-aligned and
    # fine-cell grids (80-104x faster on those cases).
    mask = shapely.contains_xy(available_area, xx.ravel(), yy.ravel())

    return np.asarray(mask, dtype=bool).reshape(h, w)


def _edt_width_lookup_batch(
    xs: np.ndarray,
    ys: np.ndarray,
    edt: np.ndarray,
    mask: np.ndarray,
    bounds: tuple[float, float, float, float],
    cell_size: float,
) -> np.ndarray:
    """Batch EDT width lookup: one FFI crossing for all samples.

    Bit-identical per point to the pre-batch per-point reference
    implementation (same f64 arithmetic order, computed in
    ``temper-geometry``); the batch form exists because the sampling
    hot loop (~12k calls per layer) is per-call Python overhead.
    """
    h, w = edt.shape
    out = _tg.edt_width_lookup_batch(
        np.ascontiguousarray(xs, dtype=np.float64).tolist(),
        np.ascontiguousarray(ys, dtype=np.float64).tolist(),
        np.ascontiguousarray(edt, dtype=np.float64).tobytes(),
        np.ascontiguousarray(mask).tobytes(),
        h,
        w,
        bounds,
        cell_size,
    )
    return np.asarray(out, dtype=np.float64)


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
    edge_widths: dict[tuple[tuple[float, float], tuple[float, float]], float] = {}

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
        return _compute_width_at_point(
            p,
            available_area,
            _prepared=prepared_area,
            _polygons=cached_polygons,
            _exteriors=cached_exteriors,
            _interiors=cached_interiors,
        )

    if _edt_grid is not None and _edt_mask is not None and _edt_bounds is not None:
        # Batched EDT path: collect every sample point, resolve all widths
        # in one FFI crossing (bit-identical per point to the per-point
        # reference pinned in the differential test suites), then assemble
        # node/edge widths.
        _node_points = list(skeleton.graph.nodes())

        _edge_samples: list[tuple[object, object, list[tuple[float, float]]]] = []
        for u, v in skeleton.graph.edges():
            dx = v[0] - u[0]
            dy = v[1] - u[1]
            edge_length = (dx**2 + dy**2) ** 0.5
            if edge_length > sample_distance:
                num_samples = int(edge_length / sample_distance)
                _edge_samples.append(
                    (
                        u,
                        v,
                        [
                            (u[0] + (i / num_samples) * dx, u[1] + (i / num_samples) * dy)
                            for i in range(1, num_samples)
                        ],
                    )
                )
            else:
                _edge_samples.append((u, v, []))

        _all_points = _node_points + [p for (_, _, pts) in _edge_samples for p in pts]
        if _all_points:
            _widths = _edt_width_lookup_batch(
                np.asarray([p[0] for p in _all_points], dtype=np.float64),
                np.asarray([p[1] for p in _all_points], dtype=np.float64),
                _edt_grid,
                _edt_mask,
                _edt_bounds,
                _edt_cell,
            )
        else:
            _widths = np.zeros(0, dtype=np.float64)

        node_widths = dict(zip(_node_points, _widths[: len(_node_points)]))
        _sample_offset = len(_node_points)
        for u, v, pts in _edge_samples:
            widths_along_edge = [node_widths[u], node_widths[v]]
            for k in range(len(pts)):
                widths_along_edge.append(float(_widths[_sample_offset + k]))
            _sample_offset += len(pts)
            edge_widths[(cast(tuple[float, float], u), cast(tuple[float, float], v))] = min(widths_along_edge) if widths_along_edge else 0.0
    else:
        # Reference path: per-point width sampling (EDT disabled or
        # unavailable).  Keep the original loop untouched for parity.
        for node in skeleton.graph.nodes():
            width = _width_at(node)
            node_widths[node] = width

        for u, v in skeleton.graph.edges():
            widths_along_edge = []

            widths_along_edge.append(node_widths[u])
            widths_along_edge.append(node_widths[v])

            dx = v[0] - u[0]
            dy = v[1] - u[1]
            edge_length = (dx**2 + dy**2) ** 0.5

            if edge_length > sample_distance:
                num_samples = int(edge_length / sample_distance)
                for i in range(1, num_samples):
                    t = i / num_samples
                    sample_x = u[0] + t * dx
                    sample_y = u[1] + t * dy
                    width = _width_at((sample_x, sample_y))
                    widths_along_edge.append(width)

            edge_widths[(cast(tuple[float, float], u), cast(tuple[float, float], v))] = min(widths_along_edge) if widths_along_edge else 0.0

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
    min_distance = float("inf")
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

    if min_distance == float("inf"):
        return 0.0
    return 2.0 * min_distance


class ChannelWidthsStage(Stage):
    """Stage 2.4: Compute channel widths along skeletons."""

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
    """Validate channel width invariants."""
    failures: list[StageDRCFailure] = []
    if state.channel_widths is None:
        failures.append(
            StageDRCFailure(
                field="channel_widths",
                value=None,
                reason="Channel widths not computed",
                stage="ChannelWidths",
            )
        )
        return failures

    for layer_name, cw in state.channel_widths.items():
        if cw.min_width < 0:
            failures.append(
                StageDRCFailure(
                    field="channel_widths",
                    value=layer_name,
                    reason="Negative minimum width: " + repr(cw.min_width),
                    stage="ChannelWidths",
                )
            )
        if cw.max_width < 0:
            failures.append(
                StageDRCFailure(
                    field="channel_widths",
                    value=layer_name,
                    reason="Negative maximum width: " + repr(cw.max_width),
                    stage="ChannelWidths",
                )
            )

    return failures
