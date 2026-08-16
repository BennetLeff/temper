"""
Regression tests for the via-span clearance fix (2026-08-16).

Root cause (docs/evidence/2026-08-16-route-to-100-stitch-cspace-and-power-width.md
Sec 5 item 5): every via-placement site in the N-layer A* machinery checked
the via's clearance on AT MOST ONE layer -- the destination layer of a tier-3
transition, the pad's own layer of a landing via, or nothing at all for a
tier-2 anchor. A through via F.Cu<->B.Cu therefore landed with its
In3.Cu/In4.Cu barrel inside another net's track (11 residual shorting_items).

The fix (astar_core._via_placement_halo_free) verifies, on EVERY layer the
via's barrel physically pierces:
  * the via's center cell is free (or owned by the via's own net), and
  * the via's extra barrel extent beyond the net's track half-width
    (max(0, via_diameter/2 - trace_width/2)) is free as a disc.
"""

from __future__ import annotations

import numpy as np

from temper_placer.router_v6.astar_core import (
    _astar_search_3d,
    _via_placement_halo_free,
    _via_span_layers,
)
from temper_placer.router_v6.occupancy_grid import OccupancyGrid

_SIZE = 100  # 10mm x 10mm at 0.1mm cells


def _make_grid(layer: str, size: int = _SIZE) -> OccupancyGrid:
    return OccupancyGrid(
        layer_name=layer,
        grid=np.zeros((size, size), dtype=np.int8),
        origin=(0.0, 0.0),
        cell_size=0.1,
        width_cells=size,
        height_cells=size,
    )


def test_via_span_layers_through_includes_inner():
    layers = {"F.Cu", "In3.Cu", "In4.Cu", "B.Cu"}
    assert _via_span_layers("F.Cu", "B.Cu", layers) == ["F.Cu", "In3.Cu", "In4.Cu", "B.Cu"]
    assert _via_span_layers("B.Cu", "F.Cu", layers) == ["F.Cu", "In3.Cu", "In4.Cu", "B.Cu"]
    assert _via_span_layers("F.Cu", "In3.Cu", layers) == ["F.Cu", "In3.Cu"]
    assert _via_span_layers("In3.Cu", "In4.Cu", layers) == ["In3.Cu", "In4.Cu"]


def test_via_placement_halo_rejects_inner_layer_foreign_track():
    """A through via F.Cu<->B.Cu whose In3.Cu barrel overlaps a foreign
    track must be rejected even though the via's centre cell is free on
    both endpoint layers."""
    # Foreign track on In3.Cu: a horizontal 0.2mm track at y=5.0mm
    # (cells y=50), spanning x = 3.0..7.0mm. Its width-family stamp
    # (searching net W=0.2, clearance floor C=0.2) is
    # w_F/2 + max(cl_F, C) + W/2 = 0.1 + 0.2 + 0.1 = 0.4mm around the
    # centreline, i.e. cells y in 46..54 for x in 26..74.
    in3 = _make_grid("In3.Cu")
    for y in range(46, 55):
        for x in range(26, 75):
            in3.grid[y, x] = 7  # some other net's id
    grids = {
        "F.Cu": _make_grid("F.Cu"),
        "In3.Cu": in3,
        "In4.Cu": _make_grid("In4.Cu"),
        "B.Cu": _make_grid("B.Cu"),
    }
    # Via centre at (5.0, 5.0) -- free on F.Cu and B.Cu, but the In3.Cu
    # barrel (via 0.8mm, disc radius max(0, 0.4-0.1)=0.3mm around the
    # centre) overlaps the In3.Cu track stamp 0.4mm below it.
    assert not _via_placement_halo_free(
        grids, 5.0, 5.0, "F.Cu", "B.Cu", via_diameter=0.8, trace_width=0.2, net_id=1
    )
    # Moving the via 1.0mm away (y=6.0) clears the track's 0.4mm stamp.
    assert _via_placement_halo_free(
        grids, 5.0, 6.0, "F.Cu", "B.Cu", via_diameter=0.8, trace_width=0.2, net_id=1
    )


def test_via_placement_halo_allows_own_net_cells():
    """Cells owned by the via's own net (net_id) inside the halo are not
    foreign copper and must not reject the placement."""
    grids = {
        "F.Cu": _make_grid("F.Cu"),
        "In3.Cu": _make_grid("In3.Cu"),
        "In4.Cu": _make_grid("In4.Cu"),
        "B.Cu": _make_grid("B.Cu"),
    }
    # Own-net cells inside the halo (e.g. the net's own unblocked pads).
    for y in range(47, 54):
        for x in range(47, 54):
            grids["In3.Cu"].grid[y, x] = 1
    assert _via_placement_halo_free(
        grids, 5.0, 5.0, "F.Cu", "B.Cu", via_diameter=0.8, trace_width=0.2, net_id=1
    )


def test_astar_3d_refuses_via_through_blocked_inner_layer():
    """The tier-3 search must refuse a via transition when the via's
    barrel would land inside a foreign track on an inner pierced layer,
    even though both the source and destination cells are free."""
    from temper_placer.router_v6.astar_core import RouteNode3D

    # Foreign copper covering the ENTIRE In3.Cu grid: every possible
    # F.Cu<->B.Cu via pierces In3.Cu and its barrel must be free there,
    # so no via exists anywhere.
    in3 = _make_grid("In3.Cu")
    in3.grid[:, :] = 7
    grids = {
        "F.Cu": _make_grid("F.Cu"),
        "In3.Cu": in3,
        "In4.Cu": _make_grid("In4.Cu"),
        "B.Cu": _make_grid("B.Cu"),
    }
    start = RouteNode3D(30, 30, "F.Cu")
    goal = RouteNode3D(30, 30, "B.Cu")
    result = _astar_search_3d(
        start, goal, grids, via_diameter=0.8, clearance=0.2, net_id=1, trace_width=0.2
    )
    # The only way to B.Cu is a via; with the inner layer fully blocked
    # the search must fail closed rather than emit an overlapping via.
    assert result is None


def test_astar_3d_allows_via_when_inner_layer_clear():
    from temper_placer.router_v6.astar_core import RouteNode3D

    grids = {
        "F.Cu": _make_grid("F.Cu"),
        "In3.Cu": _make_grid("In3.Cu"),
        "In4.Cu": _make_grid("In4.Cu"),
        "B.Cu": _make_grid("B.Cu"),
    }
    start = RouteNode3D(30, 30, "F.Cu")
    goal = RouteNode3D(30, 30, "B.Cu")
    result = _astar_search_3d(
        start, goal, grids, via_diameter=0.8, clearance=0.2, net_id=1, trace_width=0.2
    )
    assert result is not None
    path, vias = result
    assert vias
