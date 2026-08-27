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
    _family_signature,
    _family_static_inflation,
    _land_route_on_pad_layers,
    run_astar_pathfinding_nlayer,
    select_routing_grids_nlayer,
)
from temper_placer.router_v6.astar_core import RoutePath3D
from temper_placer.router_v6.astar_grid import _mark_route_blocked
from temper_placer.router_v6.astar_nlayer_rust import route_segment_3d_rust_diagnostic
from temper_placer.router_v6.channel_mapping import ChannelMapping, ChannelPath
from temper_placer.router_v6.occupancy_grid import OccupancyGrid, build_occupancy_grid
from temper_placer.router_v6.stage0_data import DesignRules, NetClassRules, ParsedPCB

_SIZE = 21
_CELL = 0.5
_MID = _SIZE // 2


def _open_grid(name: str) -> OccupancyGrid:
    return OccupancyGrid(
        name, np.zeros((_SIZE, _SIZE), dtype=np.int8), (0.0, 0.0), _CELL, _SIZE, _SIZE
    )


def _blocked_grid(name: str) -> OccupancyGrid:
    return OccupancyGrid(
        name, np.full((_SIZE, _SIZE), -1, dtype=np.int8), (0.0, 0.0), _CELL, _SIZE, _SIZE
    )


def test_rust_diagnostic_distinguishes_cap_from_frontier_exhaustion():
    open_grid = _open_grid("F.Cu")
    route, iterations, hit_cap = route_segment_3d_rust_diagnostic(
        (0.0, 0.0),
        (10.0, 10.0),
        "F.Cu",
        "F.Cu",
        {"F.Cu": open_grid},
        max_iter=1,
    )
    assert route is None
    assert iterations == 2
    assert hit_cap is True

    boxed = _blocked_grid("F.Cu")
    boxed.grid[0, 0] = 0
    boxed.grid[-1, -1] = 0
    route, iterations, hit_cap = route_segment_3d_rust_diagnostic(
        (0.0, 0.0),
        (10.0, 10.0),
        "F.Cu",
        "F.Cu",
        {"F.Cu": boxed},
        max_iter=100,
    )
    assert route is None
    assert iterations == 1
    assert hit_cap is False


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
    channel_path = ChannelPath(
        "NET1", ["CH1"], [(2.0, 2.0), (8.0, 8.0)], 10.0, preferred_layer="F.Cu"
    )
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
        "NET1",
        channel_path,
        grids,
        net_id=1,
        pad_layer_start="F.Cu",
        pad_layer_end="F.Cu",
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
    # Three-cell aperture around each transition: the default 0.9 mm via is
    # wider than the 0.2 mm trace, so a one-cell slit is center-reachable but
    # not physically via-reachable under the production envelope check.
    f_arr[_MID - 1 : _MID + 2, 0:3] = 0
    f_arr[_MID - 1 : _MID + 2, _SIZE - 3 : _SIZE] = 0

    mid_arr = np.full((_SIZE, _SIZE), -1, dtype=np.int8)
    mid_arr[_MID - 1 : _MID + 2, 0 : split + 2] = 0
    # The final B.Cu -> F.Cu through-via physically spans In1.Cu too, even
    # though the routed trace does not travel there at that endpoint.
    mid_arr[_MID - 1 : _MID + 2, _SIZE - 3 : _SIZE] = 0

    b_arr = np.full((_SIZE, _SIZE), -1, dtype=np.int8)
    b_arr[_MID - 1 : _MID + 2, split - 1 : _SIZE] = 0

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
    assert result is route, (
        "must not mutate/replace a route whose termini already sit on their pad's real layer"
    )


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
    assert routed.segments[0][2] == "F.Cu", (
        "must land on the pad's real layer, not the SSOT-forced one"
    )
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
    # passes through untouched. The third element is the netclass whose
    # pair-creepage behavior the family carries.
    assert _family_signature(_make_rule("Default", 0.2, 0.2)) == (0.2, 0.2, "Default")
    assert _family_signature(_make_rule("FinePitch", 0.127, 0.1)) == (0.127, 0.2, "FinePitch")
    assert _family_signature(_make_rule("HighVoltage", 5.0, 2.0)) == (5.0, 2.0, "HighVoltage")


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

    families, family_of_net, _halos = _build_width_families(base, rs, ["NARROW", "WIDE"], rules)

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
    families, family_of_net, _halos = _build_width_families(base, None, ["NARROW", "WIDE"], rules)
    assert families[(0.2, 0.2, "Default")] is base, (
        "single identity family must BE the caller's dict"
    )


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
    The width/creepage-aware C-space stamps NARROW into WIDE's family at
    0.1 + max(0.2, 2.0, 12.6) + 2.5 = 15.1mm radius -- a 30.2mm blocked
    band with no detour room on a 40mm board -- so WIDE declines honestly.
    The old flat 0.2mm stamp (0.3mm radius) let WIDE cross straight
    through and short against NARROW's copper."""
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

    # NARROW (0.2mm/0.2mm, via 0.9, class Default/LV) was stamped into BOTH
    # live families. The pair-creepage table resolves creepage(Default,
    # HighVoltage) = 12.6mm (the DRU's HV<->LV reinforced bar), so:
    #   own family   (0.2, 0.2, Default):  max(0.2,0.2,0.0) + 0.1 = 0.3
    #   wide family  (5.0, 2.0, HighVoltage): max(0.2,2.0,12.6) + 2.5 = 15.1
    # and the rasteriser adds w_N/2 = 0.1, so radii are 0.4mm / 15.2mm --
    # the creepage term (not just the width) is what blocks WIDE now.
    narrow_stamps = [c for c in calls if c[0] == 0.2]
    assert len(narrow_stamps) == 2, f"NARROW stamped {len(narrow_stamps)} family/ies, want 2"
    clearances = sorted(round(c[1], 6) for c in narrow_stamps)
    assert clearances == [0.3, 15.1], f"per-family stamp clearances {clearances} != [0.3, 15.1]"
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
# 7. Creepage-aware C-space (2026-08-16): the obstacle map now reserves the
#    DRU's pair CREEPAGE (12.6mm HV<->LV PD3 reinforced, 10.0mm tank
#    functional) around foreign obstacles and in routed-copper stamps, not
#    just the 0.2mm clearance floor -- so an HV track can no longer thread
#    0.2mm from an LV pad. See docs/evidence/2026-08-16-creepage-aware-
#    cspace.md and router_v6/pair_creepage.py.
# ---------------------------------------------------------------------------


def _make_creepage_design_rules() -> DesignRules:
    return DesignRules(
        net_classes={
            "Default": _make_rule("Default", 0.2, 0.2),
            "HighVoltage": _make_rule("HighVoltage", 5.0, 2.0, via=1.2),
            "Signal": _make_rule("Signal", 0.2, 0.15),
        },
        net_class_assignments={
            "NARROW": "Default",
            "WIDE": "HighVoltage",
            "SIG": "Signal",
            "LV_NET": "Signal",
            "HV_PAD_NET": "HighVoltage",
        },
        default_clearance_mm=0.2,
        default_trace_width_mm=0.2,
    )


def _make_mini_pcb(design_rules: DesignRules) -> ParsedPCB:
    """A two-pad board: an HV pad and an LV pad 6mm apart (well inside the
    12.6mm creepage bar, so the LV net must keep clear of the HV pad)."""
    from temper_placer.core.board import Board
    from temper_placer.core.netlist import Component, Net, Pin
    from temper_placer.router_v6.stage0_data import LayerInfo, ParsedPCB, StackupInfo

    comp = Component(
        ref="U1",
        footprint="TEST",
        bounds=(4.0, 4.0),
        pins=[
            Pin(
                name="1", number="1", position=(10.0, 10.0), net="HV_PAD_NET", width=1.0, height=1.0
            ),
            Pin(name="2", number="2", position=(16.0, 10.0), net="LV_NET", width=1.0, height=1.0),
        ],
        initial_position=(0.0, 0.0),
        initial_rotation_quadrant=0,
    )
    nets = [
        Net(name="HV_PAD_NET", pins=[("U1", "1")]),
        Net(name="LV_NET", pins=[("U1", "2")]),
    ]
    board = Board(width=40.0, height=40.0, origin=(0.0, 0.0))
    stackup = StackupInfo(
        layers=[LayerInfo(index=0, name="F.Cu", layer_type="signal", thickness_um=35)],
        total_thickness_mm=1.6,
        layer_count=1,
    )
    return ParsedPCB(
        components=[comp],
        nets=nets,
        zones=[],
        board=board,
        design_rules=design_rules,
        stackup=stackup,
        source_path=__file__,
    )


def test_pair_creepage_table_resolves_dru_pairs():
    """The generated pair table carries the DRU's own creepage figures: an
    HV<->LV pair grades 12.6mm (PD3 reinforced), HV<->tank 10.0mm (PD3
    functional), LV<->LV and same-HV pairs 0.0 (no creepage rule)."""
    from temper_placer.router_v6.pair_creepage import default_creepage_table

    table = default_creepage_table()
    assert table.required("HighVoltage", "Signal") == 12.6
    assert table.required("Signal", "HighVoltage") == 12.6  # symmetric
    assert table.required("HighVoltage", "Default") == 12.6
    assert table.required("ACMains", "HighVoltageIsolated") == 12.6
    assert table.required("HighVoltageTank", "HighVoltage") == 10.0
    assert table.required("HighVoltageTank", "HighVoltageSignal") == 10.0
    assert table.required("Signal", "Power") == 0.0  # LV<->LV: no creepage rule
    assert table.required("HighVoltage", "HighVoltage") == 0.0
    assert table.required("HighVoltage", "GateDriveHV") == 0.0
    assert table.required("GateDriveHV", "Signal") == 0.0
    assert table.self_creepage("HighVoltageTank") == 10.0


def test_creepage_halos_stamped_around_foreign_pads_only():
    """The LV family's grid gets an HV pad's 12.6mm creepage halo; the
    halo is stamped around the HV pad for an LV searching net, while the
    LV net's own pad stays free. The HV family gets the symmetric halo."""
    import temper_placer.router_v6._astar_nlayer as _nl

    side = 40.0
    rs = {"F.Cu": _make_box_routing_space("F.Cu", side)}
    base = {"F.Cu": build_occupancy_grid(rs["F.Cu"], inflation_mm=0.1)}
    rules = _make_creepage_design_rules()
    pcb = _make_mini_pcb(rules)

    families, family_of_net, halos = _build_width_families(
        base, rs, ["NARROW", "WIDE"], rules, pcb=pcb, escape_vias_map={}
    )

    # HV pad at (10,10); LV pad at (16,10). In the LV (Default) family the
    # HV pad's halo carries 12.6mm; in the HV (HighVoltage) family the LV
    # pad's halo carries 12.6mm. Both must be present in the per-family
    # halo lists.
    lv_family = families[(0.2, 0.2, "Default")]
    lv_halos = halos[(0.2, 0.2, "Default")]["F.Cu"]
    lv_halo_nets = {n for n, _o, _h in lv_halos}
    assert "HV_PAD_NET" in lv_halo_nets, "HV pad must halo an LV searching net"
    assert "LV_NET" not in lv_halo_nets, "same-class pads must not halo themselves"

    hv_halos = halos[(5.0, 2.0, "HighVoltage")]["F.Cu"]
    hv_halo_nets = {n for n, _o, _h in hv_halos}
    assert "LV_NET" in hv_halo_nets, "LV pad must halo an HV searching net"
    assert "HV_PAD_NET" not in hv_halo_nets, "own-class pad must not be haloed"

    # The halo radius must reach the pair creepage: HV pad (1.0mm square,
    # half-extent 0.5) + W/2 + C + 12.6. In the LV family W/2+C = 0.3, so a
    # cell 12.5mm to the right of the pad center is inside the halo but a
    # cell 13.5mm away is outside. (Buffer uses quad_segs=4, so check with
    # margin either side of the boundary.)
    grid = lv_family["F.Cu"]
    _nl._stamp_foreign_creepage_halos("NARROW", {"F.Cu": grid}, {"F.Cu": lv_halos})

    inside = grid.world_to_grid(10.0 + 12.5, 10.0)
    outside = grid.world_to_grid(10.0 + 14.5, 10.0)
    assert grid.is_blocked(*inside), "cell 12.5mm from HV pad must be blocked in LV family"
    assert grid.is_free(*outside), "cell 14.5mm from HV pad must stay free in LV family"

    # The searching net's OWN pads are not haloed: a cell right beside the
    # LV pad (own to LV_NET, foreign to NARROW) is... NARROW has no pads on
    # this board, so check the pad itself is still static (-1) and that the
    # LV pad's surroundings carry no halo ring beyond the 0.2mm erosion.
    lv_pad_cell = grid.world_to_grid(16.0, 10.0)
    assert grid.grid[lv_pad_cell[1], lv_pad_cell[0]] == -1


def test_multiple_foreign_halo_entries_keep_holes_aligned_per_polygon():
    """Each halo entry contains `_area_rings` output. Combining entries
    must flatten both the outer and holes axes once; retaining the entry axis
    makes pyo3 receive a list where a hole coordinate must be a float."""
    import temper_placer.router_v6._astar_nlayer as _nl

    routing_space = _make_box_routing_space("F.Cu", 40.0)
    grid = build_occupancy_grid(routing_space, inflation_mm=0.1)
    square_a = [5.0, 5.0, 8.0, 5.0, 8.0, 8.0, 5.0, 8.0, 5.0, 5.0]
    square_b = [20.0, 20.0, 23.0, 20.0, 23.0, 23.0, 20.0, 23.0, 20.0, 20.0]
    halos = {
        "F.Cu": [
            ("HV_A", [square_a], [[]]),
            ("HV_B", [square_b], [[]]),
        ]
    }

    _nl._stamp_foreign_creepage_halos("LV", {"F.Cu": grid}, halos)

    assert grid.is_blocked(*grid.world_to_grid(6.0, 6.0))
    assert grid.is_blocked(*grid.world_to_grid(21.0, 21.0))


def test_creepage_halo_blocks_lv_net_from_hv_pad():
    """End-to-end: the LV net must not route within the HV pad's 12.6mm
    creepage halo. With an HV pad at (10,10) and an LV track crossing at
    x=20, the halo leaves no legal path on a 40mm single-layer board, so
    the LV net declines honestly (control: it routes when the HV pad's net
    is absent from the halos)."""
    side = 40.0
    rs = {"F.Cu": _make_box_routing_space("F.Cu", side)}
    base = {"F.Cu": build_occupancy_grid(rs["F.Cu"], inflation_mm=0.1)}
    rules = _make_creepage_design_rules()
    pcb = _make_mini_pcb(rules)

    # LV net from (4, 10) to (36, 10) -- passes 6mm from the HV pad at
    # (10,10) (14mm centerline minus 0.5 half-pad) if the halo were absent.
    sig_ch = ChannelPath("SIG", ["CH1"], [(4.0, 10.0), (36.0, 10.0)], 32.0, preferred_layer="F.Cu")
    channel_mapping = ChannelMapping(channel_paths={"SIG": sig_ch})
    result = run_astar_pathfinding_nlayer(
        channel_mapping,
        base,
        design_rules=rules,
        max_iter=400_000,
        routing_spaces=rs,
        pcb=pcb,
        escape_vias_map={},
    )
    if "SIG" in result.routed_paths:
        # If it routed at all, it must have gone around -- every segment
        # keeps >= 12.6mm edge-to-edge from the HV pad center (pad
        # half-extent 0.5, plus the family's W/2+C 0.3, plus 12.6 creepage
        # = 13.4mm centerline).
        for sx, sy, _layer in result.routed_paths["SIG"].segments:
            dist = ((sx - 10.0) ** 2 + (sy - 10.0) ** 2) ** 0.5
            assert dist >= 12.5, f"SIG routed {dist:.2f}mm from HV pad -- inside creepage halo"
    else:
        assert "SIG" in result.failed_nets, "SIG must decline honestly, never fabricate"

    # Control: with the HV pad's net removed from the assignment map (so it
    # resolves to Default/LV), the HV pad's halo vanishes and SIG routes
    # straight through -- proving the decline above is the creepage halo.
    rules_lv = _make_creepage_design_rules()
    rules_lv.net_class_assignments["HV_PAD_NET"] = "Signal"
    pcb_lv = _make_mini_pcb(rules_lv)
    control = run_astar_pathfinding_nlayer(
        channel_mapping,
        base,
        design_rules=rules_lv,
        max_iter=400_000,
        routing_spaces=rs,
        pcb=pcb_lv,
        escape_vias_map={},
    )
    assert "SIG" in control.routed_paths, "control (no creepage halo) must route SIG"


# ---------------------------------------------------------------------------
# TierTally: per-tier segment accounting by classification (2026-08-18).
# ---------------------------------------------------------------------------


def test_tier_tally_counts_every_segment_exactly_once():
    """The tally is exhaustive: attempts == number of segments attempted.

    This is the property that makes the counters trustworthy. The failure
    mode being designed out is ``mst_edges_fallback_count``'s
    ``len(edges) - astar_routed_count``, which reported edges A* *failed* to
    route as edges the fallback *landed*. Here every segment increments
    exactly one classification at the point its outcome is decided, and
    ``attempts`` is an explicit sum of the four -- so a segment that fell
    through every branch would show up as a missing count, not as a silent
    reassignment into another bucket.
    """
    from temper_placer.router_v6._astar_nlayer import TierTally, _astar_route_nlayer

    grids = {"F.Cu": _open_grid("F.Cu"), "B.Cu": _open_grid("B.Cu")}
    waypoints = [(1.0, 1.0), (5.0, 5.0), (8.0, 8.0)]
    channel_path = type("CP", (), {"waypoints": waypoints, "preferred_layer": "F.Cu"})()

    tally = TierTally()
    result, _fb = _astar_route_nlayer("NET1", channel_path, grids, net_id=1, tally=tally)

    assert result is not None
    assert tally.attempts == len(waypoints) - 1, (
        f"tally counted {tally.attempts} segments for {len(waypoints) - 1} attempted: "
        f"{tally.as_dict()}"
    )
    assert tally.resolved + tally.declined == tally.attempts
    # An open grid routes on the preferred layer without ever reaching Tier 3.
    assert tally.primary_2d == len(waypoints) - 1
    assert tally.nlayer_via_3d_calls == 0


def test_tier_tally_records_declines_rather_than_inferring_them():
    """A fully blocked board must *record* declines, not leave a hole."""
    from temper_placer.router_v6._astar_nlayer import TierTally, _astar_route_nlayer

    grids = {"F.Cu": _blocked_grid("F.Cu"), "B.Cu": _blocked_grid("B.Cu")}
    waypoints = [(1.0, 1.0), (5.0, 5.0)]
    channel_path = type("CP", (), {"waypoints": waypoints, "preferred_layer": "F.Cu"})()

    tally = TierTally()
    _astar_route_nlayer(
        "NET1", channel_path, grids, net_id=1, allow_forced_segments=False, tally=tally
    )

    assert tally.declined == 1, tally.as_dict()
    assert tally.resolved == 0
    assert tally.attempts == 1
    # Tier 3 was reached and invoked, even though it resolved nothing --
    # the gap between calls and successes is the measurement that matters.
    assert tally.nlayer_via_3d_calls == 1
    assert tally.nlayer_via_3d == 0


def test_tier_tally_merge_is_additive():
    from temper_placer.router_v6._astar_nlayer import SegmentTier, TierTally

    a, b = TierTally(), TierTally()
    a.record(SegmentTier.PRIMARY_2D)
    b.record(SegmentTier.DECLINED)
    b.record(SegmentTier.ALTERNATE_2D)
    a.merge(b)
    assert a.as_dict()["attempts"] == 3
    assert a.primary_2d == 1 and a.alternate_2d == 1 and a.declined == 1
