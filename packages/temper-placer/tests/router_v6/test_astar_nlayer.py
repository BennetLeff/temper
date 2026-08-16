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
    _build_width_families,
    _family_static_inflation,
    _land_route_on_pad_layers,
    _width_family_signature,
    run_astar_pathfinding_nlayer,
    select_routing_grids_nlayer,
)
from temper_placer.router_v6.astar_core import RoutePath3D
from temper_placer.router_v6.astar_grid import _mark_route_blocked
from temper_placer.router_v6.channel_mapping import ChannelMapping, ChannelPath
from temper_placer.router_v6.occupancy_grid import OccupancyGrid, build_occupancy_grid
from temper_placer.router_v6.routing_space import RoutingSpace
from temper_placer.router_v6.stage0_data import DesignRules, NetClassRules

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


def test_nlayer_tier2_skips_degenerate_same_layer_anchor_via():
    """Measured 2026-08-14 (docs/evidence/
    2026-08-14-router-primary-grid-selection-fix.md, Task 1 follow-up): when
    the pad's own real layer (pad_layer_start/pad_layer_end) happens to
    equal the layer Tier 2's alternate-detour actually lands on, the route's
    own boundary anchor must NOT still emit a same-(x, y) duplicate point --
    that would produce a KiCad via record spanning zero real layers
    (``(layers "F.Cu" "F.Cu")``), a defect the very first production
    measurement of this fix's ``via_layer_pair``-facing surface caught
    (net RTD_SDO). B.Cu is entirely blocked so Tier 1 (primary=B.Cu) fails
    outright and Tier 2 detours onto F.Cu, which is ALSO the pads' own real
    layer -- so the route must land directly on F.Cu with no via anywhere.
    """
    b_arr = np.full((_SIZE, _SIZE), -1, dtype=np.int8)
    b_grid = OccupancyGrid("B.Cu", b_arr, (0.0, 0.0), _CELL, _SIZE, _SIZE)
    f_grid = _open_grid("F.Cu")
    grids = {"F.Cu": f_grid, "B.Cu": b_grid}

    start, goal = (2.0, 2.0), (8.0, 8.0)
    channel_path = ChannelPath("NET1", ["CH1"], [start, goal], 10.0, preferred_layer="B.Cu")

    result, _fb = _astar_route_nlayer(
        "NET1", channel_path, grids, net_id=1,
        pad_layer_start="F.Cu", pad_layer_end="F.Cu",
    )
    assert result is not None
    assert result.forced_segment_count == 0
    assert result.via_positions == [], (
        "the pad's real layer already matches the alt-layer Tier 2 landed "
        "on -- no via is needed or correct here"
    )
    assert all(seg[2] == "F.Cu" for seg in result.segments), (
        "must never emit a B.Cu anchor point (and therefore no degenerate "
        "same-layer via) when the pad's own layer already equals alt_layer"
    )


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


# ---------------------------------------------------------------------------
# 5. _land_route_on_pad_layers: measured 2026-08-14 fix for the b39b382d
#    fake-completion shape this module's own SSOT-driven preferred_layer can
#    reproduce -- a net's *working* layer (netclass SSOT, e.g.
#    GateDriveSELV's ``layer: "B.Cu"``) can differ from the layer its own
#    footprints are actually placed on (this board places every SMD part on
#    F.Cu). Tier 1 has no notion of "does this XY have real copper on THIS
#    layer" -- an SMD pad leaves no grid obstacle on a layer it has no
#    copper on, so Tier 1 walks straight to the pad's (x, y) on the WRONG
#    layer and calls it arrival, with no via ever placed.
# ---------------------------------------------------------------------------


def test_land_route_on_pad_layers_is_a_noop_when_termini_already_match():
    grids = {"F.Cu": _open_grid("F.Cu"), "B.Cu": _open_grid("B.Cu")}
    route = RoutePath3D(
        net_name="NET1",
        segments=[(2.0, 2.0, "F.Cu"), (8.0, 8.0, "F.Cu")],
        via_positions=[],
        path_length=10.0,
    )
    pads = {"NET1": [(2.0, 2.0, 0.5, "F.Cu"), (8.0, 8.0, 0.5, "F.Cu")]}
    result = _land_route_on_pad_layers("NET1", route, pads, grids)
    assert result is route, "must not mutate/replace a route whose termini already sit on their pad's real layer"


def test_land_route_on_pad_layers_inserts_landing_vias_at_both_termini():
    grids = {"F.Cu": _open_grid("F.Cu"), "B.Cu": _open_grid("B.Cu")}
    route = RoutePath3D(
        net_name="NET1",
        segments=[(2.0, 2.0, "B.Cu"), (8.0, 8.0, "B.Cu")],
        via_positions=[],
        path_length=10.0,
    )
    pads = {"NET1": [(2.0, 2.0, 0.5, "F.Cu"), (8.0, 8.0, 0.5, "F.Cu")]}
    result = _land_route_on_pad_layers("NET1", route, pads, grids)
    assert result is not None
    assert result.segments[0] == (2.0, 2.0, "F.Cu")
    assert result.segments[1] == (2.0, 2.0, "B.Cu")
    assert result.segments[-2] == (8.0, 8.0, "B.Cu")
    assert result.segments[-1] == (8.0, 8.0, "F.Cu")
    assert (2.0, 2.0) in result.via_positions
    assert (8.0, 8.0) in result.via_positions


def test_land_route_on_pad_layers_fails_closed_when_pad_layer_occupied():
    """A landing via must never be fabricated through another net's
    already-claimed copper -- decline (None), don't emit a colliding via."""
    f_grid = _open_grid("F.Cu")
    gx, gy = f_grid.world_to_grid(2.0, 2.0)
    f_grid.grid[gy, gx] = 7  # claimed by a different, earlier-routed net
    grids = {"F.Cu": f_grid, "B.Cu": _open_grid("B.Cu")}
    route = RoutePath3D(
        net_name="NET1",
        segments=[(2.0, 2.0, "B.Cu"), (8.0, 8.0, "B.Cu")],
        via_positions=[],
        path_length=10.0,
    )
    pads = {"NET1": [(2.0, 2.0, 0.5, "F.Cu"), (8.0, 8.0, 0.5, "F.Cu")]}
    result = _land_route_on_pad_layers("NET1", route, pads, grids)
    assert result is None


def test_land_route_on_pad_layers_leaves_tht_pads_alone():
    grids = {"F.Cu": _open_grid("F.Cu"), "B.Cu": _open_grid("B.Cu")}
    route = RoutePath3D(
        net_name="NET1",
        segments=[(2.0, 2.0, "B.Cu"), (8.0, 8.0, "B.Cu")],
        via_positions=[],
        path_length=10.0,
    )
    pads = {"NET1": [(2.0, 2.0, 0.5, "All"), (8.0, 8.0, 0.5, "All")]}
    result = _land_route_on_pad_layers("NET1", route, pads, grids)
    assert result is route, "a THT/ALL_LAYERS pad has no 'wrong layer' -- nothing to land"


def test_run_astar_pathfinding_nlayer_lands_a_route_forced_onto_the_wrong_layer(monkeypatch):
    """End-to-end reproduction of the measured defect and its fix: a net
    whose SSOT ``preferred_layer`` (B.Cu) differs from the layer its real
    pads sit on (F.Cu, as every SMD part on the production board does) must
    still terminate on copper that actually reaches those pads, not on
    B.Cu copper that merely coincides with the pad's (x, y)."""
    grids = {"F.Cu": _open_grid("F.Cu"), "B.Cu": _open_grid("B.Cu")}
    start, goal = (2.0, 2.0), (8.0, 8.0)
    channel_path = ChannelPath("NET1", ["CH1"], [start, goal], 10.0, preferred_layer="B.Cu")
    channel_mapping = ChannelMapping(channel_paths={"NET1": channel_path})

    monkeypatch.setattr(
        "temper_placer.router_v6._astar_nlayer._extract_pad_centers_per_net",
        lambda _pcb: {"NET1": [(*start, 0.5, "F.Cu"), (*goal, 0.5, "F.Cu")]},
    )
    monkeypatch.setattr(
        "temper_placer.router_v6._astar_nlayer._extract_existing_via_centers_per_net",
        lambda _pcb: {},
    )

    result = run_astar_pathfinding_nlayer(
        channel_mapping, grids, design_rules=DesignRules(), pcb=object()
    )

    assert "NET1" in result.routed_paths
    assert "NET1" not in result.failed_nets
    routed = result.routed_paths["NET1"]
    assert routed.segments[0][2] == "F.Cu", "must land on the pad's real layer, not the SSOT-forced one"
    assert routed.segments[-1][2] == "F.Cu"
    assert start in routed.via_positions
    assert goal in routed.via_positions


# ---------------------------------------------------------------------------
# 6. Width-aware C-space (2026-08-16): one occupancy-grid family per
#    (width, clearance) signature -- static obstacles eroded by W/2 + C,
#    routed copper stamped into every family at
#    w_F/2 + max(cl_F, C) + W/2 -- so a 5.0mm track can no longer be routed
#    through copper the old flat 0.1mm halo failed to reserve. See
#    docs/evidence/2026-08-16-width-aware-cspace.md.
# ---------------------------------------------------------------------------


def _make_rule(name: str, width: float, clearance: float, via: float = 0.9) -> NetClassRules:
    return NetClassRules(
        name=name,
        clearance_mm=clearance,
        trace_width_mm=width,
        via_diameter_mm=via,
        via_drill_mm=0.3,
    )


def _make_width_aware_design_rules() -> DesignRules:
    return DesignRules(
        net_classes={
            "Default": _make_rule("Default", 0.2, 0.2),
            "HighVoltage": _make_rule("HighVoltage", 5.0, 2.0, via=1.2),
        },
        net_class_assignments={"NARROW": "Default", "WIDE": "HighVoltage"},
        default_clearance_mm=0.2,
        default_trace_width_mm=0.2,
    )


def _make_box_routing_space(layer: str, side_mm: float):
    from shapely.geometry import MultiPolygon, box

    from temper_placer.router_v6.routing_space import RoutingSpace

    b = box(0.0, 0.0, side_mm, side_mm)
    area = side_mm * side_mm
    return RoutingSpace(
        layer_name=layer,
        available_area=MultiPolygon([b]),
        total_area=area,
        obstacle_area=0.0,
        routing_area=area,
        obstacles=None,
    )


def test_width_family_signature_floors_clearance_and_merges():
    # Default 0.2/0.2 stays as-is; FinePitch's declared 0.1mm is below the
    # DRC's 0.2mm track-involving floor and must be floored; HighVoltage
    # passes through untouched. The signature carries the net CLASS as its
    # third element so HighVoltage and HighVoltageTank (both 5.0/2.0) get
    # distinct families for creepage-aware halos.
    assert _width_family_signature(_make_rule("Default", 0.2, 0.2)) == (0.2, 0.2, "Default")
    assert _width_family_signature(_make_rule("FinePitch", 0.127, 0.1)) == (0.127, 0.2, "FinePitch")
    assert _width_family_signature(_make_rule("HighVoltage", 5.0, 2.0)) == (5.0, 2.0, "HighVoltage")


def test_family_static_inflation_is_half_width_plus_clearance():
    assert _family_static_inflation((0.2, 0.2, "Default")) == 0.3  # 0.1 + 0.2
    assert _family_static_inflation((5.0, 2.0, "HighVoltage")) == 4.5  # 2.5 + 2.0
    assert _family_static_inflation((0.127, 0.2, "FinePitch")) == 0.2635  # floored clearance


def test_build_width_families_erodes_static_layer_per_width():
    """The wide family's static layer is eroded by 4.5mm, the narrow
    family's by 0.3mm -- identical grid frames, different free area."""
    side = 40.0
    rs = {"F.Cu": _make_box_routing_space("F.Cu", side)}
    base = {"F.Cu": build_occupancy_grid(rs["F.Cu"], inflation_mm=0.1)}
    rules = _make_width_aware_design_rules()

    families, family_of_net = _build_width_families(base, rs, ["NARROW", "WIDE"], rules)

    assert family_of_net == {
        "NARROW": (0.2, 0.2, "Default"),
        "WIDE": (5.0, 2.0, "HighVoltage"),
    }
    narrow = families[(0.2, 0.2, "Default")]["F.Cu"]
    wide = families[(5.0, 2.0, "HighVoltage")]["F.Cu"]
    assert (narrow.origin, narrow.cell_size, narrow.width_cells, narrow.height_cells) == (
        wide.origin,
        wide.cell_size,
        wide.width_cells,
        wide.height_cells,
    ), "families must share the grid frame, differing only in erosion"
    assert narrow.free_cell_count > wide.free_cell_count

    # World x=1.0 is 0.7mm inside the narrow family's 0.3mm-eroded area but
    # 3.5mm outside the wide family's 4.5mm-eroded area.
    gx, gy = narrow.world_to_grid(1.0, 20.0)
    assert narrow.is_free(gx, gy)
    assert wide.is_blocked(gx, gy)


def test_build_width_families_without_routing_spaces_is_identity():
    """Synthetic fixtures (and every pre-existing unit test) pass no
    routing_spaces -- the caller's grids must be reused as-is."""
    base = {"F.Cu": _open_grid("F.Cu"), "B.Cu": _open_grid("B.Cu")}
    rules = _make_width_aware_design_rules()
    families, family_of_net = _build_width_families(base, None, ["NARROW", "WIDE"], rules)
    assert families[(0.2, 0.2, "Default")] is base, "single identity family must BE the caller's dict"


def _min_centerline_distance(path_a, path_b) -> float:
    pts_a = [(s[0], s[1]) for s in path_a.segments]
    pts_b = [(s[0], s[1]) for s in path_b.segments]
    best = float("inf")
    for x1, y1 in pts_a:
        for x2, y2 in pts_b:
            best = min(best, ((x1 - x2) ** 2 + (y1 - y2) ** 2) ** 0.5)
    return best


def test_wide_net_cannot_cross_narrow_net_width_aware_halo():
    """NARROW (0.2mm, Default) routes first down x=20; WIDE (5.0mm,
    HighVoltage) then tries to cross at y=20 on the same single layer.
    The width-aware C-space stamps NARROW into WIDE's family at
    0.1 + max(0.2, 2.0) + 2.5 = 4.6mm radius -- a 9.2mm blocked band with
    no detour room on a 40mm board -- so WIDE declines honestly. The old
    flat 0.2mm stamp (0.3mm radius) let WIDE cross straight through and
    short against NARROW's copper."""
    side = 40.0
    rs = {"F.Cu": _make_box_routing_space("F.Cu", side)}
    base = {"F.Cu": build_occupancy_grid(rs["F.Cu"], inflation_mm=0.1)}
    rules = _make_width_aware_design_rules()
    narrow_ch = ChannelPath(
        "NARROW", ["CH1"], [(20.0, 4.0), (20.0, 36.0)], 32.0, preferred_layer="F.Cu"
    )
    wide_ch = ChannelPath(
        "WIDE", ["CH2"], [(6.0, 20.0), (34.0, 20.0)], 28.0, preferred_layer="F.Cu"
    )
    channel_mapping = ChannelMapping(channel_paths={"NARROW": narrow_ch, "WIDE": wide_ch})

    result = run_astar_pathfinding_nlayer(
        channel_mapping, base, design_rules=rules, max_iter=200_000, routing_spaces=rs
    )

    assert "NARROW" in result.routed_paths
    if "WIDE" in result.routed_paths:
        min_d = _min_centerline_distance(result.routed_paths["WIDE"], result.routed_paths["NARROW"])
        assert min_d >= 2.0, f"WIDE crossed NARROW within {min_d:.3f}mm -- a short"
    else:
        assert "WIDE" in result.failed_nets, "WIDE must decline honestly, never fabricate"

    # Control: with NARROW's copper absent, WIDE routes fine through the
    # same 4.5mm-eroded corridor -- proving the decline above is caused by
    # NARROW's width-aware halo, not by the wide family being unroutable.
    wide_only = ChannelMapping(channel_paths={"WIDE": wide_ch})
    control = run_astar_pathfinding_nlayer(
        wide_only, base, design_rules=rules, max_iter=200_000, routing_spaces=rs
    )
    assert "WIDE" in control.routed_paths


def test_narrow_net_stamp_radius_differs_between_families(monkeypatch):
    """The stamp NARROW's copper leaves behind must be 4.6mm in WIDE's
    family (0.1 + max(0.2, 2.0) + 2.5) but only 0.4mm in its own
    (0.1 + max(0.2, 0.2) + 0.1) -- verified at the driver's actual
    ``_mark_route_blocked`` call sites."""
    side = 40.0
    rs = {"F.Cu": _make_box_routing_space("F.Cu", side)}
    base = {"F.Cu": build_occupancy_grid(rs["F.Cu"], inflation_mm=0.1)}
    rules = _make_width_aware_design_rules()
    narrow_ch = ChannelPath(
        "NARROW", ["CH1"], [(20.0, 4.0), (20.0, 36.0)], 32.0, preferred_layer="F.Cu"
    )
    wide_ch = ChannelPath(
        "WIDE", ["CH2"], [(6.0, 20.0), (34.0, 20.0)], 28.0, preferred_layer="F.Cu"
    )
    channel_mapping = ChannelMapping(channel_paths={"NARROW": narrow_ch, "WIDE": wide_ch})

    import temper_placer.router_v6._astar_nlayer as _nl

    calls: list[tuple[float, float, float]] = []
    real_mark = _nl._mark_route_blocked

    def spy(route_path, grids, trace_width, clearance, net_id, via_diameter=0.6):
        calls.append((trace_width, clearance, via_diameter))
        return real_mark(route_path, grids, trace_width, clearance, net_id, via_diameter)

    monkeypatch.setattr(_nl, "_mark_route_blocked", spy)

    result = run_astar_pathfinding_nlayer(
        channel_mapping, base, design_rules=rules, max_iter=200_000, routing_spaces=rs
    )
    assert "NARROW" in result.routed_paths
    # WIDE is expected to decline here (see
    # test_wide_net_cannot_cross_narrow_net_width_aware_halo) -- the point
    # of THIS test is the stamp NARROW left in both families regardless.
    assert "WIDE" in result.failed_nets

    # No pcb is passed, so no creepage table is wired up and the stamp
    # clearances are the width-aware figures from #1261:
    #   own family   (0.2, 0.2): clearance max(0.2,0.2) + 0.1 = 0.3
    #   wide family  (5.0, 2.0): clearance max(0.2,2.0) + 2.5 = 4.5
    # and the rasteriser adds w_N/2 = 0.1, so radii are 0.4mm / 4.6mm.
    narrow_stamps = [c for c in calls if c[0] == 0.2]
    assert len(narrow_stamps) == 2, f"NARROW stamped {len(narrow_stamps)} family/ies, want 2"
    clearances = sorted(round(c[1], 6) for c in narrow_stamps)
    assert clearances == [0.3, 4.5], f"per-family stamp clearances {clearances} != [0.3, 4.5]"
    assert all(c[2] == 0.9 for c in narrow_stamps), "NARROW's via_diameter 0.9 must be used"


def test_mark_route_blocked_uses_net_via_diameter():
    """Vias are stamped at the routed net's real via diameter, not the
    historical hardcoded 0.6mm (a 1.2mm HV via marked at 0.6mm under-
    reserved its halo by 0.3mm per side)."""
    grid = _open_grid("F.Cu")  # 0.5mm cells
    route = RoutePath3D(
        net_name="NET1",
        segments=[(1.0, 1.0, "F.Cu"), (5.0, 1.0, "F.Cu")],
        via_positions=[(3.0, 3.0)],  # off the segment line, so the via radius
        # check below is not contaminated by the segment's own stamp
        path_length=4.0,
        via_count=1,
    )
    # 1.2mm via, 0.2 clearance -> radius 0.8mm -> expansion ceil(0.8/0.5)=2
    _mark_route_blocked(
        route, {"F.Cu": grid}, trace_width=0.2, clearance=0.2, net_id=3, via_diameter=1.2
    )
    gx, gy = grid.world_to_grid(3.0, 3.0)
    assert grid.grid[gy, gx] == 3
    assert grid.grid[gy, gx + 1] == 3, "0.5mm <= 0.8mm radius must be blocked"
    assert grid.grid[gy, gx + 2] == 0, "1.0mm > 0.8mm radius must stay free"


def test_mark_route_blocked_via_diameter_default_preserves_legacy_behavior():
    grid = _open_grid("F.Cu")
    route = RoutePath3D(
        net_name="NET1",
        segments=[(1.0, 1.0, "F.Cu"), (5.0, 1.0, "F.Cu")],
        via_positions=[(3.0, 3.0)],
        path_length=4.0,
        via_count=1,
    )
    # default 0.6mm via, 0.2 clearance -> radius 0.5mm -> expansion 1
    _mark_route_blocked(route, {"F.Cu": grid}, trace_width=0.2, clearance=0.2, net_id=3)
    gx, gy = grid.world_to_grid(3.0, 3.0)
    assert grid.grid[gy, gx + 1] == 3, "0.5mm <= 0.5mm radius must be blocked (legacy behavior)"
    assert grid.grid[gy, gx + 2] == 0


# ---------------------------------------------------------------------------
# 7. Creepage-aware obstacle halos (2026-08-16): family grids additionally
#    carve the pair-creepage annulus around obstacle net classes whose
#    creepage to the family's routing class exceeds the DRC clearance.
#    See docs/evidence/2026-08-16-creepage-aware-obstacle-halos.md.
# ---------------------------------------------------------------------------


def _make_creepage_design_rules() -> DesignRules:
    return DesignRules(
        net_classes={
            "Default": _make_rule("Default", 0.2, 0.2),
            "Signal": _make_rule("Signal", 0.2, 0.2),
            "HighVoltage": _make_rule("HighVoltage", 5.0, 2.0, via=1.2),
            "HighVoltageTank": _make_rule("HighVoltageTank", 5.0, 2.0, via=1.2),
        },
        net_class_assignments={
            "SIG": "Signal",
            "HV": "HighVoltage",
            "TANK": "HighVoltageTank",
        },
        default_clearance_mm=0.2,
        default_trace_width_mm=0.2,
    )


def test_creepage_aware_grid_carves_hv_obstacle_ring_into_lv_family():
    """A Signal family (0.2/0.2) built over a board carrying a HighVoltage
    pad must reserve W/2 + max(0.2, 12.6) = 12.7mm around that pad -- the
    DRC clearance floor (0.3mm) would let an LV track thread within
    creepage distance of HV copper."""
    from shapely.geometry import MultiPolygon, box

    from temper_placer.router_v6.zone_pour_creepage import default_creepage_table

    side = 40.0
    # Production shape: the routing space's available_area already excludes
    # the obstacle (board - obstacle); the base erosion reserves W/2 + C
    # around it and the creepage carve adds the 4.5..12.7mm annulus.
    hv_pad = MultiPolygon([box(20.0, 20.0, 21.0, 21.0)])
    full_area = box(0.0, 0.0, side, side)
    available = full_area.difference(hv_pad)
    rs = {
        "F.Cu": RoutingSpace(
            layer_name="F.Cu",
            available_area=available,
            total_area=side * side,
            obstacle_area=1.0,
            routing_area=side * side - 1.0,
            obstacles=hv_pad,
        )
    }
    base = {"F.Cu": build_occupancy_grid(rs["F.Cu"], inflation_mm=0.1)}
    rules = _make_creepage_design_rules()

    class_obstacles = {
        "F.Cu": {
            "HighVoltage": hv_pad,
        }
    }
    creepage_table = default_creepage_table()

    families, family_of_net = _build_width_families(
        base,
        rs,
        ["SIG", "HV"],
        rules,
        class_obstacles=class_obstacles,
        creepage_table=creepage_table,
    )

    sig = families[(0.2, 0.2, "Signal")]["F.Cu"]
    hv = families[(5.0, 2.0, "HighVoltage")]["F.Cu"]

    # Same frame, both eroded at their own class's clearance:
    assert (sig.origin, sig.cell_size, sig.width_cells, sig.height_cells) == (
        hv.origin,
        hv.cell_size,
        hv.width_cells,
        hv.height_cells,
    )

    # Cell at (26.0, 20.5): 5.0mm from the HV pad edge.
    #   Signal family: 5.0 < 12.7 (0.1 + 12.6) -> BLOCKED by creepage ring.
    #   HV family:     5.0 > 4.5 (2.5 + 2.0) and same-class creepage 0 -> FREE.
    gx, gy = sig.world_to_grid(26.0, 20.5)
    assert sig.is_blocked(gx, gy), "LV net must be blocked 5mm from HV pad (creepage 12.6)"
    gx_hv, gy_hv = hv.world_to_grid(26.0, 20.5)
    assert hv.is_free(gx_hv, gy_hv), "HV net may approach its own-class obstacle at 5mm"

    # Cell at (22.0, 20.5): 1.0mm from the pad.  BOTH families block it
    # (HV family at clearance 2.0: 1.0 < 4.5).
    gx, gy = sig.world_to_grid(22.0, 20.5)
    assert sig.is_blocked(gx, gy)
    assert hv.is_blocked(*hv.world_to_grid(22.0, 20.5))


def test_creepage_aware_grid_tank_class_carves_10mm_ring_around_hv():
    """HighVoltageTank and HighVoltage share (5.0, 2.0) but the tank net
    needs 10.0mm functional creepage from HighVoltage copper while
    HighVoltage-to-HighVoltage needs only clearance.  The class-bearing
    family signature must give them DIFFERENT families."""
    from shapely.geometry import MultiPolygon, box

    from temper_placer.router_v6.zone_pour_creepage import default_creepage_table

    side = 40.0
    hv_pad = MultiPolygon([box(20.0, 20.0, 21.0, 21.0)])
    available = box(0.0, 0.0, side, side).difference(hv_pad)
    rs = {
        "F.Cu": RoutingSpace(
            layer_name="F.Cu",
            available_area=available,
            total_area=side * side,
            obstacle_area=1.0,
            routing_area=side * side - 1.0,
            obstacles=hv_pad,
        )
    }
    base = {"F.Cu": build_occupancy_grid(rs["F.Cu"], inflation_mm=0.1)}
    rules = _make_creepage_design_rules()

    class_obstacles = {
        "F.Cu": {
            "HighVoltage": hv_pad,
        }
    }
    creepage_table = default_creepage_table()

    families, family_of_net = _build_width_families(
        base,
        rs,
        ["HV", "TANK"],
        rules,
        class_obstacles=class_obstacles,
        creepage_table=creepage_table,
    )

    # Distinct families: tank must not search HV's (5.0, 2.0) grids.
    assert family_of_net["HV"] == (5.0, 2.0, "HighVoltage")
    assert family_of_net["TANK"] == (5.0, 2.0, "HighVoltageTank")
    assert family_of_net["HV"] != family_of_net["TANK"]

    hv = families[(5.0, 2.0, "HighVoltage")]["F.Cu"]
    tank = families[(5.0, 2.0, "HighVoltageTank")]["F.Cu"]

    # Cell at (26.0, 20.5): 5.0mm from the pad edge.
    #   tank family: 5.0 < 7.5 (2.5 + 10.0 functional creepage) -> BLOCKED.
    #   hv family:   5.0 > 4.5 (2.5 + 2.0) -> FREE.
    assert tank.is_blocked(*tank.world_to_grid(26.0, 20.5)), (
        "tank must hold 10.0mm creepage from HV copper"
    )
    assert hv.is_free(*hv.world_to_grid(26.0, 20.5)), "HV-vs-HV needs only the clearance floor"


def test_creepage_stamp_charges_pair_between_stamped_and_family_class():
    """The routed-copper stamp must reserve max(cl_F, C, creepage(F_class,
    family_class)) + W/2 -- a HighVoltage track stamped into a Signal
    family's grids reserves 12.6mm creepage, not just the 2.0mm clearance
    figure, while same-class stamps keep the width-aware figure.  Tests
    ``_stamp_clearance``, the exact function the driver's stamp loop calls
    for every (routed net, family) pair."""
    from temper_placer.router_v6._astar_nlayer import _stamp_clearance
    from temper_placer.router_v6.zone_pour_creepage import default_creepage_table

    rules = _make_creepage_design_rules()
    hv_rule = rules.get_rules_for_net("HV")
    table = default_creepage_table()

    hv_family = (5.0, 2.0, "HighVoltage")
    sig_family = (0.2, 0.2, "Signal")

    # HV copper stamped into HV's own family: max(2.0, 2.0, 0.0) + 2.5
    assert _stamp_clearance(hv_rule, hv_family, table) == 4.5

    # HV copper stamped into the Signal family: max(2.0, 0.2, 12.6) + 0.1
    assert _stamp_clearance(hv_rule, sig_family, table) == 12.7

    # Without a creepage table (synthetic fixtures) the width-aware-only
    # figures from #1261 apply unchanged.
    assert _stamp_clearance(hv_rule, hv_family, None) == 4.5
    assert _stamp_clearance(hv_rule, sig_family, None) == 2.1

    # Same-class stamp stays at the width-aware figure even WITH a table
    # (creepage HighVoltage|HighVoltage = 0.0).
    assert _stamp_clearance(hv_rule, hv_family, table) == 4.5
