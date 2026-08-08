"""Tests for the N-layer via-aware A* spike prototype (``_astar_nlayer.py``).

Mirrors ``test_astar_route_multilayer_via_fallback.py``'s structure (same
synthetic-grid, tiered-fallback testing style) but exercises N > 2 layers,
which the production ``_astar_route_multilayer`` cannot be given (its
signature caps it at ``primary_grid`` + one ``alternate_grid``).

Per the project's hard constraints, synthetic multi-layer boards here are
NOT a repurposing of the production board's reference planes -- every grid
below is a hand-built ``OccupancyGrid`` fixture, never derived from
``pcb/temper.kicad_pcb``.
"""

from __future__ import annotations

import numpy as np
import pytest

from temper_placer.router_v6._astar_nlayer import (
    _astar_route_nlayer,
    run_astar_pathfinding_nlayer,
    select_routing_grids_nlayer,
)
from temper_placer.router_v6.astar_core import RoutePath3D
from temper_placer.router_v6.channel_mapping import ChannelMapping, ChannelPath
from temper_placer.router_v6.occupancy_grid import OccupancyGrid
from temper_placer.router_v6.stage0_data import DesignRules

_SIZE = 21
_CELL = 0.5
_MID = _SIZE // 2


def _open_grid(name: str) -> OccupancyGrid:
    return OccupancyGrid(name, np.zeros((_SIZE, _SIZE), dtype=np.int8), (0.0, 0.0), _CELL, _SIZE, _SIZE)


def _blocked_grid(name: str) -> OccupancyGrid:
    return OccupancyGrid(
        name, np.full((_SIZE, _SIZE), -1, dtype=np.int8), (0.0, 0.0), _CELL, _SIZE, _SIZE
    )


# ---------------------------------------------------------------------------
# 1. select_routing_grids_nlayer: the generalization of select_routing_grids.
# ---------------------------------------------------------------------------


def test_select_routing_grids_nlayer_returns_every_grid_not_a_pair():
    grids = {
        "F.Cu": _open_grid("F.Cu"),
        "B.Cu": _open_grid("B.Cu"),
        "In1.Cu": _open_grid("In1.Cu"),
    }
    selected = select_routing_grids_nlayer(grids)
    assert set(selected) == {"F.Cu", "B.Cu", "In1.Cu"}, (
        "must return ALL available grids, not the production function's "
        "hardcoded (primary, alternate) pair"
    )


def test_select_routing_grids_nlayer_orders_outer_layers_first():
    grids = {"In1.Cu": _open_grid("In1.Cu"), "B.Cu": _open_grid("B.Cu"), "F.Cu": _open_grid("F.Cu")}
    selected = select_routing_grids_nlayer(grids)
    assert list(selected) == ["F.Cu", "B.Cu", "In1.Cu"]


def test_select_routing_grids_nlayer_raises_on_empty():
    with pytest.raises(ValueError):
        select_routing_grids_nlayer({})
    with pytest.raises(ValueError):
        select_routing_grids_nlayer(None)


def test_select_routing_grids_nlayer_collapses_to_two_on_a_two_layer_board():
    """On today's production board only F.Cu/B.Cu ever have an occupancy
    grid (In1.Cu/In2.Cu are planes, per REQ-ELEC-05, and never get one) --
    the N-layer selector must not fabricate layers that were never given
    to it."""
    grids = {"F.Cu": _open_grid("F.Cu"), "B.Cu": _open_grid("B.Cu")}
    assert set(select_routing_grids_nlayer(grids)) == {"F.Cu", "B.Cu"}


# ---------------------------------------------------------------------------
# 2. _astar_route_nlayer, N=2: must reproduce the production 2-layer
#    behavior it generalizes (same tiered fallback, same via anchoring).
# ---------------------------------------------------------------------------


def test_nlayer_two_grid_open_primary_needs_no_via():
    grids = {"F.Cu": _open_grid("F.Cu"), "B.Cu": _open_grid("B.Cu")}
    channel_path = ChannelPath("NET1", ["CH1"], [(2.0, 2.0), (8.0, 8.0)], 10.0, preferred_layer="F.Cu")
    result, _fb = _astar_route_nlayer("NET1", channel_path, grids, net_id=1)
    assert isinstance(result, RoutePath3D)
    assert result.forced_segment_count == 0
    assert result.via_positions == []


def test_nlayer_two_grid_bottleneck_uses_tier2_alternate_detour():
    """F.Cu open except a single wall column; B.Cu fully open -- tier 2
    (whole-segment detour on the one other layer) must find it, same
    outcome shape as the production 2-layer alternate-grid tier."""
    f_arr = np.zeros((_SIZE, _SIZE), dtype=np.int8)
    f_arr[:, _MID] = -1  # a wall spanning every row -- no F.Cu-only path around it
    f_grid = OccupancyGrid("F.Cu", f_arr, (0.0, 0.0), _CELL, _SIZE, _SIZE)
    b_grid = _open_grid("B.Cu")
    grids = {"F.Cu": f_grid, "B.Cu": b_grid}

    start = f_grid.grid_to_world(2, _MID)
    goal = f_grid.grid_to_world(_SIZE - 3, _MID)
    channel_path = ChannelPath("NET1", ["CH1"], [start, goal], 10.0, preferred_layer="F.Cu")

    result, _fb = _astar_route_nlayer("NET1", channel_path, grids, net_id=1)
    assert result.forced_segment_count == 0
    assert result.via_positions == [start, goal]
    assert any(seg[2] == "B.Cu" for seg in result.segments)


# ---------------------------------------------------------------------------
# 3. N=3: the generalization production code structurally cannot express.
#    Three layers, each individually insufficient alone, only jointly
#    routable via the full N-layer 3D fallback tier (tier 3).
# ---------------------------------------------------------------------------


def _make_three_layer_bottleneck() -> dict[str, OccupancyGrid]:
    """Both endpoints (column 0 and column ``_SIZE - 1``, row ``_MID``)
    are single, ISOLATED free cells on F.Cu -- nothing else on F.Cu is
    free, so F.Cu alone cannot connect them and cannot even be used as a
    "detour to some other layer and back" via any column but these two.
    In1.Cu is open only across columns ``0..10``; B.Cu is open only
    across columns ``10..(_SIZE-1)``. In1.Cu and B.Cu overlap at exactly
    column 10 (a legal via crossing between them); F.Cu meets In1.Cu only
    at column 0, and meets B.Cu only at column ``_SIZE - 1``.

    The only legal path is therefore F.Cu(col 0) -[via]-> In1.Cu(0..10)
    -[via]-> B.Cu(10..end) -[via]-> F.Cu(col end): a genuine 3-layer, 3-via
    crossing. No 2-layer subset of these three grids connects the two
    endpoints at all (verified by
    ``test_two_grid_subset_of_the_same_board_fails_the_same_net_closed``)
    -- this is not merely "3 layers are faster," it is "3 layers are
    required," which a search capped at 2 grids cannot express regardless
    of budget.
    """
    split = _SIZE // 2  # column 10 for _SIZE=21

    f_arr = np.full((_SIZE, _SIZE), -1, dtype=np.int8)
    f_arr[_MID, 0] = 0
    f_arr[_MID, _SIZE - 1] = 0

    mid_arr = np.full((_SIZE, _SIZE), -1, dtype=np.int8)
    mid_arr[_MID, 0 : split + 1] = 0  # In1.Cu open columns 0..split

    b_arr = np.full((_SIZE, _SIZE), -1, dtype=np.int8)
    b_arr[_MID, split : _SIZE] = 0  # B.Cu open columns split..end

    grids = {}
    for name, arr in (("F.Cu", f_arr), ("In1.Cu", mid_arr), ("B.Cu", b_arr)):
        grids[name] = OccupancyGrid(name, arr, (0.0, 0.0), _CELL, _SIZE, _SIZE)
    return grids


def test_nlayer_three_grid_requires_the_third_layer_to_cross():
    grids = _make_three_layer_bottleneck()
    f_grid = grids["F.Cu"]
    start = f_grid.grid_to_world(0, _MID)
    goal = f_grid.grid_to_world(_SIZE - 1, _MID)
    channel_path = ChannelPath("NET1", ["CH1"], [start, goal], 20.0, preferred_layer="F.Cu")

    result, _fb = _astar_route_nlayer(
        "NET1", channel_path, grids, net_id=1, segment_3d_fallback_max_iter=50_000
    )

    assert result is not None
    assert result.forced_segment_count == 0, (
        "a legal path exists ONLY by using all three layers -- a search "
        "capped at 2 grids would fail this net closed"
    )
    layers_used = {seg[2] for seg in result.segments}
    assert layers_used == {"F.Cu", "In1.Cu", "B.Cu"}, (
        f"expected the route to genuinely use all 3 layers, got {layers_used}"
    )
    assert len(result.via_positions) >= 2, "crossing 3 layers requires at least 2 vias"


def test_two_grid_subset_of_the_same_board_fails_the_same_net_closed():
    """Sanity/contrast: the identical net, given only 2 of the 3 layers
    (In1.Cu withheld -- reproducing the production cap), must fail closed
    rather than silently fabricate a path. This is the concrete
    "generalizes beyond 2 layers" claim, demonstrated as a negative
    control on the very fixture that proves the positive."""
    grids = _make_three_layer_bottleneck()
    two_layer = {"F.Cu": grids["F.Cu"], "B.Cu": grids["B.Cu"]}
    f_grid = two_layer["F.Cu"]
    start = f_grid.grid_to_world(0, _MID)
    goal = f_grid.grid_to_world(_SIZE - 1, _MID)
    channel_path = ChannelPath("NET1", ["CH1"], [start, goal], 20.0, preferred_layer="F.Cu")

    result, _fb = _astar_route_nlayer(
        "NET1",
        channel_path,
        two_layer,
        net_id=1,
        allow_forced_segments=False,
        segment_3d_fallback_max_iter=50_000,
    )

    assert result is not None
    assert result.forced_segment_count == 1, "no legal 2-layer path exists; must fail closed"


# ---------------------------------------------------------------------------
# 4. run_astar_pathfinding_nlayer: the per-net driver, end to end.
# ---------------------------------------------------------------------------


def test_run_astar_pathfinding_nlayer_routes_a_net_across_three_layers():
    grids = _make_three_layer_bottleneck()
    f_grid = grids["F.Cu"]
    start = f_grid.grid_to_world(0, _MID)
    goal = f_grid.grid_to_world(_SIZE - 1, _MID)
    channel_path = ChannelPath("NET1", ["CH1"], [start, goal], 20.0, preferred_layer="F.Cu")
    channel_mapping = ChannelMapping(channel_paths={"NET1": channel_path})

    result = run_astar_pathfinding_nlayer(
        channel_mapping, grids, design_rules=DesignRules(), max_iter=200_000
    )

    assert "NET1" in result.routed_paths
    assert "NET1" not in result.failed_nets
    routed = result.routed_paths["NET1"]
    assert {seg[2] for seg in routed.segments} == {"F.Cu", "In1.Cu", "B.Cu"}


def test_run_astar_pathfinding_nlayer_declines_unroutable_net_honestly():
    """A net with a channel path but truly no legal geometry (both
    endpoints inside a fully-blocked region on every layer) must show up
    in failed_nets with a failure report -- never silently dropped, never
    fabricated as routed."""
    blocked = {"F.Cu": _blocked_grid("F.Cu"), "B.Cu": _blocked_grid("B.Cu")}
    channel_path = ChannelPath(
        "DEAD_NET", ["CH1"], [(1.0, 1.0), (9.0, 9.0)], 10.0, preferred_layer="F.Cu"
    )
    channel_mapping = ChannelMapping(channel_paths={"DEAD_NET": channel_path})

    result = run_astar_pathfinding_nlayer(
        channel_mapping, blocked, design_rules=DesignRules(), max_iter=5_000
    )

    assert "DEAD_NET" in result.failed_nets
    assert "DEAD_NET" not in result.routed_paths
    assert "DEAD_NET" in result.failure_reports
