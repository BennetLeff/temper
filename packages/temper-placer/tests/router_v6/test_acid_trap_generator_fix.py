"""Regression tests for the acid-trap generator fix.

Context: docs/evidence/2026-07-27-acid-trap-elimination.md. A live
re-route of ``pcb/temper.kicad_pcb`` (via ``detect_acid_traps``, now that
it no longer crashes -- see ``test_acid_trap_detection.py``) found 33 acid
traps (20 critical, angle < 45 degrees) across 37 routed nets. Diagnosis
(with per-vertex evidence in the doc above) found the generator: every
per-waypoint sub-path built by ``_astar_route`` (2D), ``_astar_route_multilayer``
(3D, the actual production tier -- 37/37 nets on the live board used this
one), and ``_route_segment_3d`` (via-aware fallback tier) appended the
*exact* off-grid terminal coordinate (a pad, via, or waypoint location)
immediately after (or before) the grid-quantized A* path, using either no
de-duplication at all or an exact-equality check that can never match a
float pad coordinate against a grid cell's center. Since
``OccupancyGrid.grid_to_world`` returns a cell's CENTER and real pad
locations are essentially never exactly on a grid cell center, this
created a near-zero-length "spur" segment at nearly every waypoint, whose
direction relative to the grid-aligned approach is effectively arbitrary
-- a textbook acid-trap shape, but manufactured by path-reconstruction
bookkeeping, not by any real routing decision.

The fix (``astar_core.append_grid_path_point`` /
``append_exact_terminal_point``, used at all three call sites) merges a
grid-cell-center point into the exact terminal it is quantization-noise-
close to (within ``cell_size * sqrt(2) / 2``, the max possible distance
from any point in a cell to that cell's own center) instead of emitting
both. It never merges across a real layer transition (a via) -- the
merge requires matching layer.

These tests fail on the pre-fix code (uncomment `git stash` below to
verify) and pass after.
"""

from __future__ import annotations

import math

import numpy as np

from temper_placer.router_v6._astar_reconstruct import _astar_route, _astar_route_multilayer
from temper_placer.router_v6.acid_trap_detection import (
    _calculate_angle,
    _extract_2d_coordinates,
    detect_acid_traps,
)
from temper_placer.router_v6.astar_core import RoutePath3D, grid_quantization_tolerance
from temper_placer.router_v6.channel_mapping import ChannelPath
from temper_placer.router_v6.occupancy_grid import OccupancyGrid
from temper_placer.router_v6.routing_results import CompiledRoute, RoutingResults

_CELL_SIZE_MM = 0.1
_SIZE = 60


def _build_grid(layer: str = "F.Cu") -> OccupancyGrid:
    return OccupancyGrid(
        layer_name=layer,
        grid=np.zeros((_SIZE, _SIZE), dtype=np.int8),
        origin=(0.0, 0.0),
        cell_size=_CELL_SIZE_MM,
        width_cells=_SIZE,
        height_cells=_SIZE,
    )


def _off_grid_channel_path(start_world, goal_world) -> ChannelPath:
    return ChannelPath(
        net_name="NET_UNDER_TEST",
        channel_sequence=[],
        waypoints=[start_world, goal_world],
        total_length=math.dist(start_world, goal_world),
        preferred_layer="F.Cu",
    )


def _no_acute_interior_angle(coords: list[tuple[float, float]]) -> tuple[bool, float]:
    """Return (all_angles_ok, worst_angle) over interior vertices."""
    filtered: list[tuple[float, float]] = []
    for pt in coords:
        if not filtered or pt != filtered[-1]:
            filtered.append(pt)
    worst = 180.0
    for i in range(1, len(filtered) - 1):
        angle = _calculate_angle(filtered[i - 1], filtered[i], filtered[i + 1])
        worst = min(worst, angle)
    return worst >= 90.0, worst


def test_astar_route_multilayer_off_grid_terminals_produce_no_acid_trap():
    """The real production tier (``_astar_route_multilayer``, used by
    100% of nets on the live board per the evidence doc) must not create
    a spurious acute angle purely from snapping onto an off-grid pad.

    Before the fix: the near-goal and near-start vertices are consistently
    an acute angle (33.69 deg critical, 45.0 deg medium in the doc's
    worked example) with one adjacent segment under one grid cell long.
    After the fix: both endpoints remain geometrically exact, and no
    interior vertex reads below 90 degrees.
    """
    f_grid = _build_grid("F.Cu")
    b_grid = _build_grid("B.Cu")

    # Deliberately off-grid (not a multiple of 0.1mm) -- like a real
    # footprint pad location almost always is.
    start_world = (0.37, 1.53)
    goal_world = (4.62, 1.47)
    channel_path = _off_grid_channel_path(start_world, goal_world)

    path, _fallback_count = _astar_route_multilayer(
        net_name="NET_UNDER_TEST",
        channel_path=channel_path,
        primary_grid=f_grid,
        alternate_grid=b_grid,
        tht_locations=None,
        net_id=1,
    )

    assert path is not None
    assert isinstance(path, RoutePath3D)

    # Endpoints must still be geometrically exact -- the fix must not
    # trade the acute-angle defect for a connectivity gap.
    coords = _extract_2d_coordinates(path)
    assert coords[0] == start_world
    assert coords[-1] == goal_world

    ok, worst = _no_acute_interior_angle(coords)
    assert ok, f"spurious acid-trap-shaped vertex remains: worst interior angle = {worst:.2f} deg"

    # Full acid_trap_detection.py pass, end to end, on a realistic
    # CompiledRoute/RoutingResults wrapping -- not just the raw geometry.
    route = CompiledRoute("NET_UNDER_TEST", path, 0.2, [], None)
    results = RoutingResults(compiled_routes={"NET_UNDER_TEST": route}, failed_nets=[])
    report = detect_acid_traps(results)
    assert report.trap_count == 0, f"expected 0 acid traps, found {report.trap_count}: {report.acid_traps}"


def test_astar_route_2d_off_grid_terminals_produce_no_acid_trap():
    """Same defect, same fix, in the 2D single-layer ``_astar_route`` tier."""
    grid = _build_grid("F.Cu")
    start_world = (0.37, 1.53)
    goal_world = (4.62, 1.47)
    channel_path = _off_grid_channel_path(start_world, goal_world)

    path, _fallback_count = _astar_route(
        net_name="NET_UNDER_TEST",
        channel_path=channel_path,
        grid=grid,
        net_id=1,
    )

    assert path is not None
    assert path.coordinates[0] == start_world
    assert path.coordinates[-1] == goal_world

    ok, worst = _no_acute_interior_angle(path.coordinates)
    assert ok, f"spurious acid-trap-shaped vertex remains: worst interior angle = {worst:.2f} deg"


def test_grid_quantization_tolerance_matches_max_cell_diagonal():
    """The merge tolerance is derived from grid geometry, not tuned to
    make a count go down: it is exactly half the cell diagonal, the
    provable maximum distance from any point inside a cell to that
    cell's own center (``OccupancyGrid.grid_to_world``'s return value).
    """
    cell_size = 0.1
    tolerance = grid_quantization_tolerance(cell_size)
    assert math.isclose(tolerance, cell_size * math.sqrt(2) / 2, rel_tol=1e-12)
    # Sanity: strictly less than one full cell, comfortably more than
    # floating point noise, and independent of any acid-trap threshold.
    assert 0.0 < tolerance < cell_size


def test_real_via_transition_never_merged_across_layers():
    """A genuine via (same x, y, different layer) must never be merged
    away by the quantization-noise de-dup -- only same-layer points are
    eligible, so a real layer transition survives untouched.
    """
    from temper_placer.router_v6.astar_core import (
        append_exact_terminal_point,
        append_grid_path_point,
    )

    tolerance = grid_quantization_tolerance(_CELL_SIZE_MM)
    points: list[tuple[float, float, str]] = [(5.0, 0.0, "F.Cu")]

    # Same (x, y), different layer -- a via. Must be appended, not merged.
    append_grid_path_point(points, (5.0, 0.0, "B.Cu"), tolerance)
    assert points == [(5.0, 0.0, "F.Cu"), (5.0, 0.0, "B.Cu")]

    append_exact_terminal_point(points, (5.0, 0.0, "F.Cu"), tolerance)
    assert points == [(5.0, 0.0, "F.Cu"), (5.0, 0.0, "B.Cu"), (5.0, 0.0, "F.Cu")]
