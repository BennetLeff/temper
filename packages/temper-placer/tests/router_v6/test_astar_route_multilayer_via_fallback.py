"""U2: Tests for the ``_route_segment_3d`` fallback tier wired into
``_astar_route_multilayer``.

Origin: docs/plans/2026-07-18-003-feat-via-aware-layer-transitions-plan.md,
Implementation Unit U2. U1's spike (test_astar_3d_production_scale_spike.py)
validated the fallback-tier *shape* at production scale but found two
concrete bugs U2 had to fix as prerequisites for the mechanism to be safe:

1. ``_route_segment_3d`` never passed ``net_id`` through to
   ``_astar_search_3d`` (silently defaulted to 0), so
   ``mark_via_blocked()`` never actually fired through that entry point
   -- a later segment could legally route straight through an earlier
   segment's via. U2 added a ``net_id`` parameter to ``_route_segment_3d``
   and threads a real net_id from ``_astar_route_with_ripup`` through
   ``_astar_route_multilayer`` into the fallback call site.
2. ``_astar_search_3d`` had no iteration/wall-time safety valve (U1
   measured a 66s worst case on a degenerate long segment). U2 added a
   ``max_iter`` parameter to both ``_astar_search_3d`` and
   ``_route_segment_3d``, following the existing pattern already used by
   ``_astar_search_theta_star``/``_astar_search_lazy_theta_star``.

Test scenarios (per the plan's U2 section):
- Happy: a segment routable only via the 3D-search fallback tier
  produces a non-empty ``via_positions`` in the final ``RoutePath3D``.
- Regression: segments that already succeed on primary/alternate grids
  never invoke the fallback tier (call-counter/spy).
- Integration: real production-scale occupancy grids (corpus board, via
  the actual Stage2Orchestrator pipeline -- not synthetic), calling the
  real production dispatch function ``_astar_route_multilayer``, produce
  a ``RoutePath3D`` with real via positions for a genuinely
  forced-transition segment.
- New: the net_id fix actually works, verified through the real
  integration point (``_astar_route_multilayer``, not the bare
  ``_astar_search_3d``/``mark_via_blocked`` functions U1 already covered).
- New: the max_iter bound actually caps wall time on a degenerate
  long/hard real segment.
"""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest
import yaml
from hypothesis import given, settings
from hypothesis import strategies as st

import temper_placer.router_v6.astar_pathfinding as astar_pathfinding_mod
from temper_placer.router_v6.astar_core import _route_segment_3d as _real_route_segment_3d
from temper_placer.router_v6.channel_mapping import ChannelPath
from temper_placer.router_v6.occupancy_grid import OccupancyGrid
from temper_placer.router_v6.stage0_data import DesignRules, NetClassRules
from temper_placer.router_v6.via_placement import place_vias

_HERE = Path(__file__).resolve()
_REPO_ROOT = _HERE.parents[4]
_CORPUS_PCB = _REPO_ROOT / "power_pcb_dataset" / "corpus" / "temper" / "temper.kicad_pcb"
_PROD_PCB = _REPO_ROOT / "pcb" / "temper.kicad_pcb"
_NETCLASS_CONFIG = yaml.safe_load(
    (_REPO_ROOT / "packages/temper-placer/configs/netclass_rules.yaml").read_text()
)
_CONFIGURED_NET_CLASSES = tuple(_NETCLASS_CONFIG["classes"])

_SIZE = 21
_CELL_SIZE_MM = 0.5
_MID = _SIZE // 2  # corridor row
_WALL_X = 10  # blocked column on F.Cu, breaking the corridor


# ---------------------------------------------------------------------------
# Synthetic fixtures: deterministic, small, exercise the mechanism (not
# scale -- U1 + the integration test below cover scale).
# ---------------------------------------------------------------------------


def _make_bottleneck_via_grids() -> dict[str, OccupancyGrid]:
    """A 2-layer grid where crossing from one side to the other REQUIRES a
    via, and there is exactly one place that via can legally go.

    F.Cu: a single-cell-wide horizontal corridor (row ``_MID``), free
    everywhere along that row except one blocked column (``_WALL_X``) --
    the "wall". Every other row is fully blocked, so there is no way
    around the wall by staying on F.Cu.

    B.Cu: fully blocked EXCEPT a 3-cell window (columns
    ``_WALL_X - 1 .. _WALL_X + 1``) in row ``_MID`` straddling the wall --
    the only place a layer transition can both leave and re-enter F.Cu on
    either side of the wall. This makes the via crossing a genuine,
    unique bottleneck: exactly two via positions
    (``_WALL_X - 1``, ``_WALL_X + 1``) can ever be used to cross it.
    """
    f_arr = np.full((_SIZE, _SIZE), -1, dtype=np.int8)  # all blocked
    f_arr[_MID, :] = 0  # corridor row free...
    f_arr[_MID, _WALL_X] = -1  # ...except the wall column

    b_arr = np.full((_SIZE, _SIZE), -1, dtype=np.int8)  # all blocked
    b_arr[_MID, _WALL_X - 1 : _WALL_X + 2] = 0  # tiny window straddling the wall

    f_grid = OccupancyGrid(
        layer_name="F.Cu", grid=f_arr, origin=(0.0, 0.0),
        cell_size=_CELL_SIZE_MM, width_cells=_SIZE, height_cells=_SIZE,
    )
    b_grid = OccupancyGrid(
        layer_name="B.Cu", grid=b_arr, origin=(0.0, 0.0),
        cell_size=_CELL_SIZE_MM, width_cells=_SIZE, height_cells=_SIZE,
    )
    return {"F.Cu": f_grid, "B.Cu": b_grid}


def _bottleneck_endpoints(f_grid: OccupancyGrid) -> tuple[tuple[float, float], tuple[float, float]]:
    start_world = f_grid.grid_to_world(0, _MID)
    goal_world = f_grid.grid_to_world(_SIZE - 1, _MID)
    return start_world, goal_world


def _configured_design_rules(net_class: str | None) -> DesignRules:
    """Construct router runtime rules from the netclass sizing authority."""
    net_classes = {
        name: NetClassRules(
            name=name,
            clearance_mm=spec["clearance"],
            trace_width_mm=spec["trace_width"],
            via_diameter_mm=spec["via_diameter"],
            via_drill_mm=spec["via_drill"],
        )
        for name, spec in _NETCLASS_CONFIG["classes"].items()
    }
    assignments = {"NET_UNDER_TEST": net_class} if net_class is not None else {}
    return DesignRules(
        net_classes=net_classes,
        net_class_assignments=assignments,
        default_clearance_mm=0.2,
        default_trace_width_mm=0.2,
        default_via_diameter_mm=0.6,
        default_via_drill_mm=0.3,
    )


# ---------------------------------------------------------------------------
# 1. Happy path: primary + alternate (skipped/unavailable) fail; the 3D
#    fallback tier finds a path and reports real via_positions.
# ---------------------------------------------------------------------------


def test_fallback_tier_produces_via_positions_when_primary_and_alternate_fail():
    """A segment that is impossible on F.Cu alone, and for which the
    THT-gated alternate-grid retry is unavailable (``tht_locations=None``),
    is only routable via the U2 3D-search fallback tier -- and its via
    positions land in the final ``RoutePath3D``, no longer the hardcoded
    ``[]`` this unit's R1 fix targets."""
    grids = _make_bottleneck_via_grids()
    f_grid, b_grid = grids["F.Cu"], grids["B.Cu"]
    start_world, goal_world = _bottleneck_endpoints(f_grid)

    channel_path = ChannelPath(
        net_name="NET1", channel_sequence=["CH1"],
        waypoints=[start_world, goal_world], total_length=10.0,
    )

    with patch.object(
        astar_pathfinding_mod, "_route_segment_3d", wraps=_real_route_segment_3d,
    ) as spy:
        result, _fb = astar_pathfinding_mod._astar_route_multilayer(
            "NET1", channel_path, f_grid, b_grid, None, net_id=1,
        )

    assert result is not None
    assert result.via_positions, (
        "Expected non-empty via_positions from the 3D fallback tier -- "
        "via_positions must no longer be a static [] for a segment that "
        "needed it (R1)"
    )
    assert result.via_count == len(result.via_positions)
    assert result.forced_segment_count == 0, (
        "The 3D fallback tier found a real path -- this must NOT be "
        "counted as a forced/failed segment"
    )
    # Sanity: the fallback tier was actually what produced this path (not
    # some pre-existing primary/alternate success).
    spy.assert_called_once()


@pytest.mark.property
@given(net_class=st.sampled_from(_CONFIGURED_NET_CLASSES + (None,)))
@settings(max_examples=100, deadline=15000)
def test_3d_fallback_legality_uses_each_netclass_via_envelope(net_class: str | None):
    """U4/R3: SSOT diameter and clearance reach the 3D legality call."""
    grids = _make_bottleneck_via_grids()
    f_grid, b_grid = grids["F.Cu"], grids["B.Cu"]
    start_world, goal_world = _bottleneck_endpoints(f_grid)
    channel_path = ChannelPath(
        net_name="NET_UNDER_TEST", channel_sequence=["CH1"],
        waypoints=[start_world, goal_world], total_length=10.0,
    )
    design_rules = _configured_design_rules(net_class)

    with patch.object(
        astar_pathfinding_mod, "_route_segment_3d", wraps=_real_route_segment_3d,
    ) as spy:
        result, _ = astar_pathfinding_mod._astar_route_multilayer(
            "NET_UNDER_TEST", channel_path, f_grid, b_grid, None,
            net_id=1, design_rules=design_rules,
        )

    assert result is not None
    assert result.via_positions
    expected = design_rules.get_rules_for_net("NET_UNDER_TEST")
    assert spy.call_args.kwargs["via_diameter"] == expected.via_diameter_mm
    assert spy.call_args.kwargs["clearance"] == expected.clearance_mm

    placement = place_vias(
        astar_pathfinding_mod.PathfindingResult(
            routed_paths={"NET_UNDER_TEST": result}, failed_nets=[]
        ),
        design_rules=design_rules,
    )
    assert placement.vias
    assert placement.vias[0].diameter == spy.call_args.kwargs["via_diameter"]
    assert placement.vias[0].drill == expected.via_drill_mm


# ---------------------------------------------------------------------------
# 2. Regression: segments that succeed on the primary grid never invoke
#    the fallback tier at all -- proves this is additive, not intrusive.
# ---------------------------------------------------------------------------


def test_fallback_tier_not_invoked_when_primary_grid_succeeds():
    """A trivially-routable segment on an open primary grid must never
    reach the 3D fallback tier -- existing behavior/performance for the
    common case is unaffected by U2's change."""
    grid = OccupancyGrid("F.Cu", np.zeros((20, 20), dtype=np.int8), (0.0, 0.0), 1.0, 20, 20)
    channel_path = ChannelPath(
        net_name="NET1", channel_sequence=["CH1"],
        waypoints=[(2.0, 2.0), (15.0, 15.0)], total_length=18.4,
    )

    with patch.object(
        astar_pathfinding_mod, "_route_segment_3d", wraps=_real_route_segment_3d,
    ) as spy:
        result, _fb = astar_pathfinding_mod._astar_route_multilayer(
            "NET1", channel_path, grid, None, None, net_id=1,
        )

    assert result is not None
    assert result.forced_segment_count == 0
    assert result.via_positions == [], "Open primary-grid routing needs no via"
    spy.assert_not_called()


def test_fallback_tier_not_invoked_when_alternate_grid_succeeds():
    """A segment that fails on the primary grid but succeeds on the
    THT-gated alternate-grid retry (tier 2) must not fall through to the
    3D fallback tier (tier 3) -- tier 2 success takes priority."""
    # Primary grid: fully blocked -- forces tier 1 to fail.
    blocked = np.full((20, 20), -1, dtype=np.int8)
    primary_grid = OccupancyGrid("F.Cu", blocked, (0.0, 0.0), 1.0, 20, 20)
    # Alternate grid: fully open -- tier 2 succeeds trivially.
    alt_grid = OccupancyGrid("B.Cu", np.zeros((20, 20), dtype=np.int8), (0.0, 0.0), 1.0, 20, 20)

    channel_path = ChannelPath(
        net_name="NET1", channel_sequence=["CH1"],
        waypoints=[(2.0, 2.0), (15.0, 15.0)], total_length=18.4,
    )
    tht_locations = {(2.0, 2.0)}  # non-empty -> gates tier 2 open

    with patch.object(
        astar_pathfinding_mod, "_route_segment_3d", wraps=_real_route_segment_3d,
    ) as spy:
        result, _fb = astar_pathfinding_mod._astar_route_multilayer(
            "NET1", channel_path, primary_grid, alt_grid, tht_locations, net_id=1,
        )

    assert result is not None
    assert result.forced_segment_count == 0
    assert result.via_positions == [], "Tier-2 (alternate-grid) success needs no via"
    spy.assert_not_called()


# ---------------------------------------------------------------------------
# 3. New: the net_id fix actually works, through the real integration
#    point (_astar_route_multilayer), not the bare _astar_search_3d
#    function U1 already covered directly.
# ---------------------------------------------------------------------------


def test_net_id_blocking_prevents_second_net_reusing_same_via_through_multilayer():
    """Call the real fallback path (via ``_astar_route_multilayer``)
    twice through the sole via bottleneck in ``_make_bottleneck_via_grids``
    -- once per net, sharing the SAME (mutated) grids. The first net's
    via must block the second net from crossing at all.

    This mirrors U1's
    ``test_mark_via_blocked_prevents_second_route_through_same_via_position``
    but drives it through the production entry point
    (``_astar_route_multilayer``), proving U2's net_id-threading fix
    (previously: ``_route_segment_3d`` silently defaulted net_id=0, so
    ``mark_via_blocked()`` never fired) actually protects production via
    placements.
    """
    grids = _make_bottleneck_via_grids()
    f_grid, b_grid = grids["F.Cu"], grids["B.Cu"]
    start_world, goal_world = _bottleneck_endpoints(f_grid)

    cp1 = ChannelPath("NET1", ["CH1"], [start_world, goal_world], 10.0)
    cp2 = ChannelPath("NET2", ["CH1"], [start_world, goal_world], 10.0)

    result1, _ = astar_pathfinding_mod._astar_route_multilayer(
        "NET1", cp1, f_grid, b_grid, None, net_id=1,
    )
    assert result1 is not None
    assert result1.via_positions, "First net must need + place a via to cross the wall"
    assert result1.forced_segment_count == 0

    result2, _ = astar_pathfinding_mod._astar_route_multilayer(
        "NET2", cp2, f_grid, b_grid, None, net_id=2,
    )
    # _astar_route_multilayer always returns a RoutePath3D (it degrades to
    # a forced/failed segment rather than returning None) -- the real
    # assertion is that it did NOT find a legal path through the now-
    # blocked via bottleneck.
    assert result2 is not None
    assert result2.via_positions == [], (
        "Second net must NOT be able to reuse the via position blocked by "
        "the first net's net_id=1 mark_via_blocked() call -- if this "
        "fails, the U2 net_id-threading fix has regressed and vias are "
        "placed with zero occupancy-grid protection again"
    )
    assert result2.forced_segment_count == 1, (
        "With the sole via crossing blocked, the second net's segment "
        "must fail all three tiers and fall through to the existing "
        "forced-segment path -- not silently route through the blocked "
        "cell"
    )


# ---------------------------------------------------------------------------
# 4 & 5. Integration (real production-scale grids) + max_iter bound.
# Marked slow: builds real occupancy grids via the actual
# Stage2Orchestrator pipeline, same method as U1's spike.
# ---------------------------------------------------------------------------


def _build_grids(pcb_path: Path) -> dict[str, OccupancyGrid]:
    """Real Stage2Orchestrator pipeline -- matches how router_v6 builds
    production grids (not a synthetic/hand-rolled grid). Duplicated from
    test_astar_3d_production_scale_spike.py's helper of the same name
    (kept self-contained rather than cross-importing between test
    modules)."""
    from temper_placer.io.kicad_parser import parse_kicad_pcb_v6
    from temper_placer.router_v6.dense_package_detection import identify_dense_packages
    from temper_placer.router_v6.escape_via_generator import generate_escape_vias
    from temper_placer.router_v6.stage2_orchestrator import Stage2Orchestrator

    pcb = parse_kicad_pcb_v6(pcb_path)
    dense_packages = identify_dense_packages(pcb.components)
    escape_vias = []
    for dp in dense_packages:
        vias = generate_escape_vias(dp, pcb.design_rules, strategy="dog-bone")
        if not vias:
            vias = generate_escape_vias(dp, pcb.design_rules, strategy="via-in-pad")
        escape_vias.extend(vias)

    orch = Stage2Orchestrator(verbose=False)
    state = orch.run(pcb, escape_vias)
    assert state.occupancy_grids, f"No occupancy grids built for {pcb_path}"
    return state.occupancy_grids


def _nearest_free_cell(
    grid: OccupancyGrid, x_mm: float, y_mm: float, max_radius: int = 80
) -> tuple[int, int] | None:
    """BFS ring-search outward from (x_mm, y_mm) for the nearest free
    cell. Duplicated from the U1 spike test's helper of the same name."""
    cx, cy = grid.world_to_grid(x_mm, y_mm)
    if grid.is_free(cx, cy):
        return cx, cy
    for r in range(1, max_radius):
        for dx in range(-r, r + 1):
            for dy in (-r, r):
                nx, ny = cx + dx, cy + dy
                if grid.is_free(nx, ny):
                    return nx, ny
        for dy in range(-r + 1, r):
            for dx in (-r, r):
                nx, ny = cx + dx, cy + dy
                if grid.is_free(nx, ny):
                    return nx, ny
    return None


def _carve_local_via_bottleneck(
    fcu: OccupancyGrid, bcu: OccupancyGrid, anchor_world: tuple[float, float], half_span: int = 60,
) -> tuple[OccupancyGrid, OccupancyGrid, tuple[float, float], tuple[float, float]]:
    """Copy the real, production-scale grids and carve a small,
    deterministic via-bottleneck obstruction into a local free region
    near ``anchor_world``.

    Exploration for this test (see the fork/probe that produced this
    helper) found the real corpus board's F.Cu free area is a SINGLE
    connected component at ~9% occupancy -- ``scipy.ndimage.label`` on
    the F.Cu free mask returns exactly 1 component outside a 100-cell
    board-edge margin. There is no naturally occurring "obstruction
    that fully separates two reachable points" to pick deterministically
    on this board today (the real, production failure mode U1 found
    instead is a pad center landing INSIDE a blocked courtyard cell --
    which ``_astar_route_multilayer``'s fallback tier, by design, cannot
    route to either: it keeps a segment's start/goal layer fixed to the
    primary grid's layer, matching the existing "direct forced segment"
    convention, so a goal that's blocked on the primary layer itself is
    unreachable regardless of tier).

    This helper carves a local, fully-sealed obstruction (blocking a
    ``2*half_span`` square region on BOTH copied layers except a
    single-cell-wide F.Cu corridor row broken by one wall cell, and a
    tiny B.Cu via-window straddling that wall) into COPIES of the real
    grid arrays, at a real free anchor point. This keeps the test
    exercising real production-scale grid dimensions, the real
    ``OccupancyGrid``/``Stage2Orchestrator`` pipeline output, and the
    real ``_astar_route_multilayer`` dispatch function, while making the
    "no F.Cu-only path exists" precondition deterministic rather than
    dependent on incidental (and, per the above, currently absent) real
    board topology.
    """
    from dataclasses import replace

    ax, ay = fcu.world_to_grid(*anchor_world)
    assert fcu.is_free(ax, ay) and bcu.is_free(ax, ay), (
        f"Anchor {anchor_world} must be free on both layers before carving"
    )

    fcu2 = replace(fcu, grid=fcu.grid.copy())
    bcu2 = replace(bcu, grid=bcu.grid.copy())

    row0, row1 = ay - half_span, ay + half_span + 1
    col0, col1 = ax - half_span, ax + half_span + 1
    wall_x = ax

    fcu2.grid[row0:row1, col0:col1] = -1  # seal the local region on F.Cu...
    fcu2.grid[ay, col0:col1] = 0  # ...except one corridor row...
    fcu2.grid[ay, wall_x] = -1  # ...broken by one wall cell

    bcu2.grid[row0:row1, col0:col1] = -1  # seal the same region on B.Cu...
    bcu2.grid[ay, wall_x - 1 : wall_x + 2] = 0  # ...except a via window at the wall

    start_world = fcu2.grid_to_world(col0, ay)
    goal_world = fcu2.grid_to_world(col1 - 1, ay)
    return fcu2, bcu2, start_world, goal_world


@pytest.fixture(scope="module")
def corpus_grids() -> dict[str, OccupancyGrid]:
    assert _CORPUS_PCB.exists(), f"Corpus board fixture not found: {_CORPUS_PCB}"
    return _build_grids(_CORPUS_PCB)


@pytest.fixture(scope="module")
def production_grids() -> dict[str, OccupancyGrid]:
    assert _PROD_PCB.exists(), f"Production board fixture not found: {_PROD_PCB}"
    return _build_grids(_PROD_PCB)


@pytest.mark.slow
@pytest.mark.integration
def test_integration_corpus_board_forced_transition_produces_real_vias(corpus_grids):
    """Real production-scale occupancy grids (corpus board, built via the
    actual Stage2Orchestrator pipeline -- the same grids router_v6 uses
    in production) and the real production dispatch function
    (``_astar_route_multilayer``): the fallback tier produces a
    ``RoutePath3D`` with real, non-empty via positions for a segment that
    -- before this unit -- would have returned ``via_positions=[]``
    unconditionally (the R1 bug this unit fixes).

    The obstruction forcing primary/alternate-grid failure is carved
    locally into a copy of the real grids (see
    ``_carve_local_via_bottleneck``'s docstring for why: this board's
    F.Cu free area has no naturally occurring detour-requiring
    bottleneck to pick deterministically). Grid dimensions, cell size,
    origin, and all surrounding real board data are untouched real
    production-scale grids from the real pipeline.
    """
    fcu = corpus_grids["F.Cu"]
    bcu = corpus_grids["B.Cu"]

    anchor_cell = _nearest_free_cell(fcu, 60.0, 80.0)
    assert anchor_cell is not None
    anchor_world = fcu.grid_to_world(*anchor_cell)

    fcu2, bcu2, start_world, goal_world = _carve_local_via_bottleneck(fcu, bcu, anchor_world)

    channel_path = ChannelPath(
        net_name="INTEGRATION_NET", channel_sequence=["CH1"],
        waypoints=[start_world, goal_world], total_length=12.0,
    )

    # tht_locations=None: the alternate-grid retry (tier 2) is
    # deliberately unavailable here. max_iter is tight enough that the
    # primary-grid-only search cannot exhaust the real (large, ~1.6M
    # cell) free area looking for a way around the local wall within
    # budget -- matching how a real, bounded per-net max_iter budget
    # behaves in production (see compute_demand_budget /
    # run_astar_pathfinding's own max_iter) -- while still being ample
    # for the small, local 3D fallback-tier search to find the via
    # detour (as scenario 1's synthetic-grid test also confirms
    # succeeds in well under 1000 iterations for an equivalent pattern).
    result, _fb = astar_pathfinding_mod._astar_route_multilayer(
        "INTEGRATION_NET", channel_path, fcu2, bcu2, None,
        max_iter=5_000, net_id=1,
    )

    assert result is not None
    assert result.via_positions, (
        "Expected real via_positions from the fallback tier on a genuine "
        "forced-transition segment at production board scale -- "
        "via_positions must not be the pre-U2 static []"
    )
    assert result.via_count == len(result.via_positions)
    assert result.forced_segment_count == 0


@pytest.mark.slow
def test_max_iter_bound_caps_wall_time_on_degenerate_long_segment(production_grids):
    """U1 measured up to 66.2s wall time on a degenerate, effectively
    unreachable long-distance same-layer segment on the production board
    (pad center inside a blocked courtyard cell, forcing exploration of
    most of the combined multi-layer state space) because
    ``_astar_search_3d`` had no iteration cap. This test proves the U2
    max_iter fix actually bounds wall time on that exact call pattern --
    it does NOT assert the search finds (or fails to find) a path; per
    the plan, only that it returns in bounded time."""
    # Same real long-distance, degenerate segment coordinates U1's spike
    # measured at 66.2s worst-case with no cap.
    start_world = (46.25, 30.73)
    goal_world = (85.00, 118.50)

    small_max_iter = 500

    t0 = time.monotonic()
    _real_route_segment_3d(
        start_world, goal_world, "F.Cu", "F.Cu", production_grids,
        via_cost=10.0, net_id=1, max_iter=small_max_iter,
    )
    dt = time.monotonic() - t0

    print(
        f"\n[max_iter bound] degenerate segment with max_iter={small_max_iter}: "
        f"{dt:.4f}s (U1's unbounded baseline on this exact segment: up to 66.2s)"
    )

    # Generous bound: a few seconds is comfortably enough for 500
    # iterations of neighbor generation across 5 layers; the real point
    # is that this is orders of magnitude below U1's unbounded 66s.
    assert dt < 10.0, (
        f"_route_segment_3d with max_iter={small_max_iter} took {dt:.2f}s -- "
        f"the max_iter cap does not appear to be bounding wall time"
    )
