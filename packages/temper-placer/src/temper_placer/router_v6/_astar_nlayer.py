# mypy: ignore-errors
"""Spike prototype: N-layer, via-aware A* pathfinding.

**Status: prototype, not production.** Branch ``spike/nlayer-via-astar``,
spun up to answer a design question, not to replace the production A*
path. See ``docs/evidence/2026-08-08-nlayer-via-astar-spike.md`` for the
full writeup (why, what was measured, and the honest assessment).

**The gap this closes.** Two independent places in the production router
cap pathfinding at exactly two layers:

- ``_pipeline_route.select_routing_grids`` always returns a
  ``(primary, alternate)`` pair -- ``occupancy_grids.get("F.Cu")`` and
  ``occupancy_grids.get("B.Cu")``, with inner-layer fallback, but never
  more than two.
- ``astar_pathfinding.run_astar_pathfinding``'s signature caps it again:
  one ``grid`` plus one *singular* ``alternate_grid``. ``all_grids`` is
  built as ``{grid.layer_name: grid}`` plus at most one more entry.

**What already existed and did NOT need reinventing.** The per-segment
search primitive underneath both of those, ``astar_core._astar_search_3d``
/ ``_route_segment_3d``, already accepts an arbitrary-size
``grids: dict[str, OccupancyGrid]`` and treats a layer transition (via) as
a real, costed, clearance-checked move (``mark_via_blocked`` on every
layer a via spans). It is real, tested (see
``test_astar_route_multilayer_via_fallback.py``), and N-layer-capable --
it is just used only as a last-resort *third tier* inside
``_astar_route_multilayer``, itself fed at most 2 grids no matter how many
exist. ``astar_grid._mark_route_blocked`` / ``_unmark_route_blocked`` /
``_identify_blocking_nets`` are likewise already ``dict``-of-arbitrary-size
callers, not 2-capped. So this prototype is a plumbing generalization, not
a new search algorithm: it re-threads the already-N-layer-capable core
through call sites that were artificially narrowed to 2 above it.

**This module's shape.** Three pieces, mirroring
``_pipeline_route.select_routing_grids`` / ``_astar_search._astar_route_multilayer``
/ ``_astar_reconstruct.run_astar_pathfinding`` one-for-one, generalized:

1. ``select_routing_grids_nlayer`` -- returns every available occupancy
   grid (all *signal* layers; plane layers never get a grid in the first
   place -- see ``routing_space.py`` -- so no additional filtering is
   needed), not a hardcoded pair.
2. ``_astar_route_nlayer`` -- generalizes ``_astar_route_multilayer``'s
   3-tier cascade (cheap same-layer search on the preferred layer, then a
   whole-segment detour on ONE alternate layer, then a 3D via-aware
   fallback across at most 2 grids) to N grids: tier 1 unchanged, tier 2
   tries *every* other available layer as a whole-segment detour (not
   just one), tier 3 runs the full via-aware 3D search across *all* grids
   simultaneously (not just primary+alternate).
3. ``run_astar_pathfinding_nlayer`` -- generalizes
   ``run_astar_pathfinding``'s per-net driver loop to call the above with
   an N-grid dict instead of a 2-grid pair.

**Deliberately out of scope for this spike** (see the evidence doc for
why each is safe to omit for a feasibility measurement, not a claim they
are unimportant):

- The experimental all-pad-tree terminal expansion
  (``enable_all_pad_tree`` / ``terminal_tree_execution.py``) -- disabled
  by default in production; not exercised here.
- The congestion-tensor history-cost term and thermal cost field -- the
  production ``_run_stage4`` call this spike is compared against does not
  pass either (net-batching production runs use neither), so omitting
  them does not change comparability.
- The rip-up-and-reroute queue in ``run_astar_pathfinding``'s
  ``attempt_route``. Traced end-to-end (see the evidence doc): under the
  current, unconditional ``_allow_forced_segments() -> False`` fail-closed
  policy, ``_astar_route_with_ripup``'s ``ripped_ids`` return value is
  non-empty ONLY when the returned path has ``forced_segment_count > 0``,
  and ``run_astar_pathfinding``'s ``attempt_route`` always returns a
  forced-segment decline *before* reaching the loop that would act on
  those ripped IDs (the loop only runs on a *clean* success, where
  ``ripped_ids`` is always ``[]``). So the rip-up-and-reroute mechanism is
  currently dead code under production policy -- dropping it from this
  prototype is a verified equivalence, not an uncontrolled simplification.
  Restated: if ``_allow_forced_segments`` is ever made conditional again,
  this prototype's parity claim would need re-checking; it does not hold
  in general, only under today's policy.
"""

from __future__ import annotations

import logging
import math
import time
from typing import TYPE_CHECKING

from temper_placer.router_v6._astar_ordering import _compute_net_order
from temper_placer.router_v6._astar_search import (
    _SEGMENT_3D_FALLBACK_MAX_ITER,
    _in_bounds,
    _segment_search,
)
from temper_placer.router_v6._net_policy import _allow_forced_segments, _should_route
from temper_placer.router_v6._routing_reports import (
    FAILURE_REASON_PROVER_ERROR,
    PathfindingResult,
    RoutingFailureReport,
    _forced_segment_decline,
)
from temper_placer.router_v6.astar_core import (
    RoutePath3D,
    _route_segment_3d,
    append_exact_terminal_point,
    append_grid_path_point,
    grid_quantization_tolerance,
)
from temper_placer.router_v6.astar_grid import (
    _extract_existing_via_centers_per_net,
    _extract_pad_centers_per_net,
    _identify_blocking_nets,
    _mark_route_blocked,
    _restore_net_pads,
    _unblock_net_pads,
)
from temper_placer.router_v6.net_classification import classify_net_type
from temper_placer.router_v6.stage0_data import DesignRules

if TYPE_CHECKING:
    from temper_placer.router_v6.channel_mapping import ChannelMapping
    from temper_placer.router_v6.occupancy_grid import OccupancyGrid

logger = logging.getLogger(__name__)

__all__ = [
    "select_routing_grids_nlayer",
    "run_astar_pathfinding_nlayer",
]


def select_routing_grids_nlayer(
    occupancy_grids: dict[str, OccupancyGrid] | None,
) -> dict[str, OccupancyGrid]:
    """Return every available occupancy grid, in a stable preference order.

    The N-layer generalization of ``_pipeline_route.select_routing_grids``,
    which always returns exactly a ``(primary, alternate)`` pair. An
    occupancy grid exists only for layers ``_parse_board.py`` classified
    as signal/mixed -- ``routing_space.py`` skips plane/non-signal layers
    entirely at grid-construction time -- so ``occupancy_grids`` already
    contains exactly the *signal* layers and nothing more; this function
    does not need to (and does not) apply any additional plane-exclusion
    filtering of its own.

    On today's production board (post 2026-08-13 layer-architecture
    decision) that is ``{"F.Cu", "In3.Cu", "In4.Cu", "B.Cu"}`` (4 layers;
    ``In1.Cu``/``In2.Cu`` are GND/PWR planes per REQ-ELEC-05 and never get
    an occupancy grid passed to this function -- callers are expected to
    filter ``occupancy_grids`` to the board's routable signal layers, e.g.
    via ``core.board_layer_roles.routable_signal_layers_from_path``, before
    calling this). On a board with more signal layers, every one of them
    is returned.

    Order: the engine-capability ordered tuple
    (``core.board_layer_roles.ENGINE_SUPPORTED_SIGNAL_LAYERS_ORDERED``,
    outer layers first, matching the existing outer-layer preference)
    first, then any remaining layers sorted by name -- deterministic
    regardless of the input dict's insertion order.
    """
    if not occupancy_grids:
        raise ValueError("No occupancy grid available for A* pathfinding")
    from temper_placer.core.board_layer_roles import ENGINE_SUPPORTED_SIGNAL_LAYERS_ORDERED

    preferred_order = list(ENGINE_SUPPORTED_SIGNAL_LAYERS_ORDERED)
    ordered_names = [name for name in preferred_order if name in occupancy_grids]
    ordered_names += sorted(name for name in occupancy_grids if name not in ordered_names)
    return {name: occupancy_grids[name] for name in ordered_names}


def _emit_2d_segment(detailed_segments, segment_path, grid_used, layer_name, tolerance, i, start_world, goal_world):
    if i == 0:
        detailed_segments.append((start_world[0], start_world[1], layer_name))
    for node in segment_path:
        wx, wy = grid_used.grid_to_world(node[0], node[1])
        append_grid_path_point(detailed_segments, (wx, wy, layer_name), tolerance)
    append_exact_terminal_point(detailed_segments, (goal_world[0], goal_world[1], layer_name), tolerance)


def _astar_route_nlayer(
    net_name: str,
    channel_path,
    grids: dict[str, OccupancyGrid],
    use_theta_star: bool = False,
    use_lazy_theta_star: bool = False,
    max_iter: int = 1_000_000,
    enable_coarse_to_fine: bool = False,
    coarse_factor: int = 4,
    corridor_buffer_cells: int = 12,
    thermal_flat=None,
    thermal_weight: float = 0.0,
    net_id: int = 0,
    design_rules: DesignRules | None = None,
    allow_forced_segments: bool = True,
    segment_3d_fallback_max_iter: int = _SEGMENT_3D_FALLBACK_MAX_ITER,
) -> tuple[RoutePath3D | None, int]:
    """Route one net's waypoint chain across an arbitrary number of layers.

    Generalizes ``_astar_search._astar_route_multilayer``'s 3-tier cascade
    (primary 2D -> one alternate 2D -> 2-layer 3D via fallback) to N
    layers:

    1. Cheap same-layer 2D search on the segment's preferred layer.
    2. Cheap same-layer 2D search on every OTHER available layer in turn
       (first success wins), each anchored with explicit vias at both
       ends -- generalizes the old single-``alternate_grid`` detour to
       N-1 alternates.
    3. The full via-aware 3D search (``_route_segment_3d`` /
       ``_astar_search_3d``) across *every* grid simultaneously -- this is
       the one search tier that is genuinely multi-layer-native rather
       than "try each layer in isolation": it can detour through more
       than one intermediate layer within a single segment if that is
       cheaper than any single-via crossing.
    4. Forced segment / fail-closed decline, exactly matching the
       production contract (``allow_forced_segments`` is always ``False``
       in production; see ``_net_policy._allow_forced_segments``).

    Tiers 1-2 are deliberately kept cheap-and-layer-local rather than
    always running the full N-layer 3D search: the 3D search's state
    space is ``O(cells * layers)``, so preferring same-layer search when
    it suffices (the common case) keeps per-net cost close to today's
    production cost on a 2-layer board, and keeps the *additional* cost
    of more layers bounded by how often tiers 1-2 fail, not by state
    space size on every segment.
    """
    waypoints = channel_path.waypoints
    if len(waypoints) < 2 or not grids:
        return None, 0

    preferred_layer = getattr(channel_path, "preferred_layer", None)
    primary_grid = grids.get(preferred_layer) or next(iter(grids.values()))
    other_grids = [g for name, g in grids.items() if name != primary_grid.layer_name]

    detailed_segments: list[tuple[float, float, str]] = []
    via_positions: list[tuple[float, float]] = []
    forced_segments = 0
    failed_waypoint_indices: list[int] = []
    fallback_count = 0

    for i in range(len(waypoints) - 1):
        start_world = waypoints[i]
        goal_world = waypoints[i + 1]

        # Tier 1: same-layer search on the preferred/primary layer.
        segment_path, grid_used, fb = _segment_search(
            primary_grid,
            start_world,
            goal_world,
            use_theta_star,
            use_lazy_theta_star,
            max_iter=max_iter,
            enable_coarse_to_fine=enable_coarse_to_fine,
            coarse_factor=coarse_factor,
            corridor_buffer_cells=corridor_buffer_cells,
            thermal_flat=thermal_flat,
            thermal_weight=thermal_weight,
        )
        fallback_count += fb

        if segment_path:
            tolerance = grid_quantization_tolerance(grid_used.cell_size)
            _emit_2d_segment(
                detailed_segments, segment_path, grid_used, primary_grid.layer_name,
                tolerance, i, start_world, goal_world,
            )
            continue

        # Tier 2: whole-segment detour on every OTHER available layer.
        routed_on_alt = False
        for alt_grid in other_grids:
            alt_start = alt_grid.world_to_grid(*start_world)
            alt_goal = alt_grid.world_to_grid(*goal_world)
            if not (_in_bounds(alt_grid, alt_start) and _in_bounds(alt_grid, alt_goal)):
                continue
            alt_path, _unused, fb2 = _segment_search(
                alt_grid,
                start_world,
                goal_world,
                use_theta_star,
                use_lazy_theta_star,
                max_iter=max_iter,
                enable_coarse_to_fine=enable_coarse_to_fine,
                coarse_factor=coarse_factor,
                corridor_buffer_cells=corridor_buffer_cells,
                thermal_flat=thermal_flat,
                thermal_weight=thermal_weight,
            )
            fallback_count += fb2
            if not alt_path:
                continue
            alt_layer = alt_grid.layer_name
            alt_tolerance = grid_quantization_tolerance(alt_grid.cell_size)
            if i == 0:
                detailed_segments.append((start_world[0], start_world[1], primary_grid.layer_name))
            # Real via (layer change at identical x, y) -- never merged by
            # append_grid_path_point/append_exact_terminal_point, which
            # only ever collapse same-layer near-duplicates.
            detailed_segments.append((start_world[0], start_world[1], alt_layer))
            for node in alt_path:
                wx, wy = alt_grid.grid_to_world(node[0], node[1])
                append_grid_path_point(detailed_segments, (wx, wy, alt_layer), alt_tolerance)
            append_exact_terminal_point(
                detailed_segments, (goal_world[0], goal_world[1], alt_layer), alt_tolerance
            )
            detailed_segments.append((goal_world[0], goal_world[1], primary_grid.layer_name))
            via_positions.extend((start_world, goal_world))
            routed_on_alt = True
            break
        if routed_on_alt:
            continue

        # Tier 3: full N-layer via-aware 3D search across every grid.
        net_rules = design_rules.get_rules_for_net(net_name) if design_rules else None
        result_3d = _route_segment_3d(
            start_world,
            goal_world,
            primary_grid.layer_name,
            primary_grid.layer_name,
            grids,
            via_cost=10.0,
            # Fallback 0.6 -> 0.9mm 2026-08-13, same fab-floor fix as the
            # identical fallback in _astar_search.py (docs/evidence/
            # 2026-08-13-jlcpcb-fab-capability-envelope.md).
            via_diameter=net_rules.via_diameter_mm if net_rules else 0.9,
            clearance=net_rules.clearance_mm if net_rules else 0.2,
            net_id=net_id,
            max_iter=segment_3d_fallback_max_iter,
        )
        if result_3d is not None:
            world_path_3d, via_positions_3d = result_3d
            via_positions.extend(via_positions_3d)
            if i == 0:
                detailed_segments.append(world_path_3d[0])
            detailed_segments.extend(world_path_3d[1:])
            continue

        if not allow_forced_segments:
            failed_waypoint_indices.append(i + 1)
            path_length = _path_length_3d(detailed_segments)
            return RoutePath3D(
                net_name=net_name,
                segments=detailed_segments,
                via_positions=via_positions,
                path_length=path_length,
                via_count=len(via_positions),
                forced_segment_count=1,
                failed_waypoint_indices=failed_waypoint_indices,
            ), fallback_count

        forced_segments += 1
        failed_waypoint_indices.append(i + 1)
        if i == 0:
            detailed_segments.append((start_world[0], start_world[1], primary_grid.layer_name))
        detailed_segments.append((goal_world[0], goal_world[1], primary_grid.layer_name))

    path_length = _path_length_3d(detailed_segments)
    return RoutePath3D(
        net_name=net_name,
        segments=detailed_segments,
        via_positions=via_positions,
        path_length=path_length,
        via_count=len(via_positions),
        forced_segment_count=forced_segments,
        failed_waypoint_indices=failed_waypoint_indices,
    ), fallback_count


def _path_length_3d(segments: list[tuple[float, float, str]]) -> float:
    return sum(
        ((s2[0] - s1[0]) ** 2 + (s2[1] - s1[1]) ** 2) ** 0.5
        for s1, s2 in zip(segments, segments[1:])
    )


# Measured 2026-08-14 (docs/evidence/2026-08-14-router-pad-layer-landing.md):
# feeding the N-layer engine a board whose netclass SSOT assigns a net's
# *working* layer (e.g. GateDriveSELV/GateDriveHV's ``layer: "B.Cu"``,
# channel_mapping._assign_layer) independent of which layer that net's own
# footprints were actually placed on (this board places every SMD part on
# F.Cu) reproduces the b39b382d fake-completion shape: Tier 1's same-layer
# 2D search has no notion of "does this XY correspond to a real pad on THIS
# layer" -- an SMD pad leaves no obstacle on a layer it has no copper on, so
# Tier 1 walks straight to the pad's exact (x, y) on the WRONG layer and
# calls it arrival, and because Tier 1 "succeeded" tiers 2/3 (the only tiers
# that ever place a via) never run. 71 nets on the real board reproduce this;
# 9 of them (2-pad, pad_count==2, e.g. GATE_HS/PWM_HS/PWM_LS/sclk/RTD_SDI)
# were confirmed by direct coordinate audit: the emitted copper's endpoint
# sits exactly on the pad's (x, y), on a layer that pad has no copper on, no
# via anywhere in the net.
FAILURE_REASON_PAD_LAYER_LANDING_BLOCKED = "pad_layer_landing_blocked"


def _land_route_on_pad_layers(
    net_name: str,
    route_path: RoutePath3D,
    pad_centers_per_net: dict[str, list[tuple[float, float, float, str]]],
    grids: dict[str, OccupancyGrid],
    tolerance_mm: float = 0.05,
) -> RoutePath3D | None:
    """Insert a landing via wherever the route's own first/last emitted
    point sits exactly on a net pad's (x, y) but on a layer that pad has no
    copper on -- the exact defect this module's docstring above measures.

    A no-op (returns ``route_path`` unchanged) whenever both route termini
    already land on their pad's real layer -- true for the large majority
    of nets, and for every existing ``_astar_nlayer``/``run_astar_pathfinding_nlayer``
    unit test, none of which pass ``pcb=`` (so ``pad_centers_per_net`` is
    always empty there and this function is never reached by them).

    Fails closed (returns ``None``) when the pad's own layer is not free at
    that exact point (already claimed by an earlier-routed net) -- this
    function must never write copper that then collides with something
    else's copper to make a completion counter look better; a net this
    happens to belongs in ``failed_nets``, not ``routed_paths``.

    THT/``ALL_LAYERS`` terminals (layer containing ``"All"``/``"*.Cu"``/
    ``"Through"``) are left alone: a via lands on every layer already,
    there is no "wrong layer" for a through-hole pad.
    """
    pads = pad_centers_per_net.get(net_name) or []
    if not pads or not route_path.segments:
        return route_path

    def _pad_layer_at(x: float, y: float) -> str | None:
        for px, py, _radius, layer in pads:
            if abs(px - x) > tolerance_mm or abs(py - y) > tolerance_mm:
                continue
            if layer in ("All", "all") or "*.Cu" in layer or "Through" in layer:
                return None  # THT: nothing to correct
            return layer
        return None

    def _layer_free_at(x: float, y: float, layer: str) -> bool:
        grid = grids.get(layer)
        if grid is None:
            return False
        gx, gy = grid.world_to_grid(x, y)
        return grid.is_free(gx, gy)

    segments = list(route_path.segments)
    via_positions = list(route_path.via_positions)
    changed = False

    x0, y0, layer0 = segments[0]
    pad_layer_start = _pad_layer_at(x0, y0)
    if pad_layer_start is not None and pad_layer_start != layer0:
        if not _layer_free_at(x0, y0, pad_layer_start):
            return None
        segments.insert(0, (x0, y0, pad_layer_start))
        via_positions.insert(0, (x0, y0))
        changed = True

    xn, yn, layern = segments[-1]
    pad_layer_end = _pad_layer_at(xn, yn)
    if pad_layer_end is not None and pad_layer_end != layern:
        if not _layer_free_at(xn, yn, pad_layer_end):
            return None
        segments.append((xn, yn, pad_layer_end))
        via_positions.append((xn, yn))
        changed = True

    if not changed:
        return route_path

    return RoutePath3D(
        net_name=route_path.net_name,
        segments=segments,
        via_positions=via_positions,
        path_length=route_path.path_length,
        via_count=len(via_positions),
        forced_segment_count=route_path.forced_segment_count,
        failed_waypoint_indices=route_path.failed_waypoint_indices,
    )


def run_astar_pathfinding_nlayer(
    channel_mapping: ChannelMapping,
    grids: dict[str, OccupancyGrid],
    design_rules: DesignRules | None = None,
    pcb=None,
    escape_vias_map: dict[str, list[tuple[float, float, float]]] | None = None,
    use_theta_star: bool = False,
    max_nets: int | None = None,
    target_nets: list[str] | None = None,
    use_lazy_theta_star: bool = False,
    max_iter: int = 1_000_000,
    enable_coarse_to_fine: bool = False,
    coarse_factor: int = 4,
    corridor_buffer_cells: int = 12,
    net_budgets: dict[str, int] | None = None,
    thermal_flat=None,
    thermal_weight: float = 0.0,
) -> PathfindingResult:
    """N-layer, via-aware generalization of ``astar_pathfinding.run_astar_pathfinding``.

    Same per-net driver shape (net ordering, pad unblocking, fail-closed
    exception handling, failure reporting) as the production function,
    generalized to accept an arbitrary-size ``grids`` dict instead of a
    hardcoded ``grid`` + ``alternate_grid`` pair. See this module's
    docstring for what is deliberately out of scope for this spike
    (all-pad-tree, congestion tensor, thermal field support is threaded
    through but untested at scale, rip-up-and-reroute).
    """
    if not grids:
        raise ValueError("No occupancy grids available for N-layer A* pathfinding")
    if design_rules is None:
        design_rules = DesignRules()

    routed_paths: dict[str, RoutePath3D] = {}
    failed_nets_set: set[str] = set()
    failure_reports: dict[str, RoutingFailureReport] = {}
    blocker_history: dict[str, set[str]] = {}

    # Note: unlike the production run_astar_pathfinding, THT pad locations
    # are not collected here -- tier 2 (whole-segment layer detour) has no
    # THT-only gate in this spike (see _astar_route_nlayer's docstring:
    # "THT-pad gating no longer required"), so there is no consumer for
    # them.
    pad_centers_per_net: dict[str, list[tuple[float, float, float, str]]] = {}
    existing_vias_per_net: dict[str, list[tuple[float, float, float]]] = {}
    if pcb:
        pad_centers_per_net = _extract_pad_centers_per_net(pcb)
        existing_vias_per_net = _extract_existing_via_centers_per_net(pcb)

    net_order = _compute_net_order(channel_mapping)
    routable_nets = [n for n in net_order if _should_route(n)]
    if target_nets:
        target_set = set(target_nets)
        routable_nets = [n for n in routable_nets if n in target_set]
    elif max_nets is not None:
        routable_nets = routable_nets[:max_nets]

    net_ids = {name: i + 1 for i, name in enumerate(routable_nets)}
    id_to_net = {v: k for k, v in net_ids.items()}
    base_inflation = design_rules.default_trace_width_mm / 2.0
    per_path_latency_ms: dict[str, float] = {}
    fallback_count = 0

    def attempt_route(net_name: str):
        nonlocal fallback_count
        channel_path = channel_mapping.channel_paths[net_name]
        net_id = net_ids[net_name]
        primary_grid_for_budget = grids.get(channel_path.preferred_layer) or next(iter(grids.values()))

        # Same per-net elliptical iteration-budget derivation as production
        # run_astar_pathfinding (_astar_reconstruct.py:189-201) -- NOT just
        # the flat `max_iter` for every net. This matters for
        # comparability: a flat, always-maximal budget gives every net
        # more search attempts than production allows, which can let a
        # net "succeed" where production's tighter, span-derived budget
        # would have it fail closed -- a confound this spike must not
        # introduce silently.
        if net_budgets is not None:
            per_net_max_iter = net_budgets.get(net_name, max_iter)
        else:
            per_net_max_iter = max_iter
            waypoints = channel_path.waypoints
            if waypoints and len(waypoints) >= 2:
                dx = abs(waypoints[-1][0] - waypoints[0][0])
                dy = abs(waypoints[-1][1] - waypoints[0][1])
                span_cells = int((dx + dy) / primary_grid_for_budget.cell_size)
                grid_area = primary_grid_for_budget.width_cells * primary_grid_for_budget.height_cells
                ellipse_cells = int(math.pi * (span_cells / 2.0) ** 2)
                derived = max(1000, min(ellipse_cells, grid_area))
                per_net_max_iter = min(max_iter, derived)

        restoration = _unblock_net_pads(
            net_name,
            pad_centers_per_net,
            grids,
            inflation_mm=base_inflation,
            escape_vias_map=escape_vias_map,
            existing_vias_map=existing_vias_per_net,
        )

        route_path, fb = _astar_route_nlayer(
            net_name,
            channel_path,
            grids,
            use_theta_star=use_theta_star,
            use_lazy_theta_star=use_lazy_theta_star,
            max_iter=per_net_max_iter,
            enable_coarse_to_fine=enable_coarse_to_fine,
            coarse_factor=coarse_factor,
            corridor_buffer_cells=corridor_buffer_cells,
            thermal_flat=thermal_flat,
            thermal_weight=thermal_weight,
            net_id=net_id,
            design_rules=design_rules,
            allow_forced_segments=_allow_forced_segments(net_name, design_rules, False),
        )
        fallback_count += fb

        landing_blocked = False
        if route_path and route_path.forced_segment_count == 0:
            # Must run BEFORE _restore_net_pads: the pad's own-layer grid
            # cells are only unblocked (static -1 -> free 0) between
            # _unblock_net_pads above and _restore_net_pads below. Checking
            # after restoration would see every never-traversed pad cell
            # reset back to -1 and fail every landing closed, not just the
            # genuine collisions.
            landed = _land_route_on_pad_layers(net_name, route_path, pad_centers_per_net, grids)
            if landed is None:
                landing_blocked = True
                route_path = None
            else:
                route_path = landed

        _restore_net_pads(restoration)

        ripped_ids: list[int] = []
        if route_path and route_path.forced_segment_count > 0:
            blockers = _identify_blocking_nets(channel_path, list(grids.values()))
            if blockers:
                ripped_ids = sorted(blockers)
        blocker_names = [id_to_net.get(rid, f"Unknown-{rid}") for rid in ripped_ids]
        blocker_history.setdefault(net_name, set()).update(blocker_names)

        def congestion_region():
            return channel_path.waypoints[len(channel_path.waypoints) // 2] if channel_path.waypoints else None

        if route_path:
            if route_path.forced_segment_count > 0:
                return _forced_segment_decline([], congestion_region())
            routed_paths[net_name] = route_path
            _mark_route_blocked(
                route_path,
                grids,
                trace_width=design_rules.default_trace_width_mm,
                clearance=design_rules.default_clearance_mm,
                net_id=net_id,
            )
            return True, "", [], None, None

        if landing_blocked:
            return False, FAILURE_REASON_PAD_LAYER_LANDING_BLOCKED, [], congestion_region(), None
        return False, "no_path", [], congestion_region(), None

    def attempt_route_fail_closed(net_name: str):
        try:
            return attempt_route(net_name)
        except Exception:
            logger.exception(
                "Unhandled exception routing net %r (N-layer spike path); "
                "declining fail-closed rather than treating it as proven-safe.",
                net_name,
            )
            return False, FAILURE_REASON_PROVER_ERROR, [], None, None

    def record_failure(net_name: str, reason: str, region, rule_id: str | None = None):
        channel_path = channel_mapping.channel_paths.get(net_name)
        pin_count = len(channel_path.waypoints) if channel_path else 0
        failure_reports[net_name] = RoutingFailureReport(
            net_name=net_name,
            failure_reason=reason,
            blocking_nets=list(blocker_history.get(net_name, set())),
            attempted_ripups=0,
            congestion_region=region,
            pin_count=pin_count,
            rule_id=rule_id,
            domain=classify_net_type(net_name),
        )

    for net_name in routable_nets:
        t0 = time.perf_counter()
        success, reason, _blockers, region, rule_id = attempt_route_fail_closed(net_name)
        per_path_latency_ms[net_name] = (time.perf_counter() - t0) * 1000.0
        if not success:
            failed_nets_set.add(net_name)
            record_failure(net_name, reason, region, rule_id=rule_id)

    return PathfindingResult(
        routed_paths=routed_paths,
        failed_nets=list(dict.fromkeys(failed_nets_set)),
        failure_reports=failure_reports,
        net_ids=net_ids,
        per_path_latency_ms=per_path_latency_ms,
        coarse_to_fine_fallbacks=fallback_count,
    )
