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
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

import numpy as np
import temper_geometry as _tg

from temper_placer.router_v6._astar_ordering import _compute_net_order
from temper_placer.router_v6._astar_search import (
    _SEGMENT_3D_FALLBACK_MAX_ITER,
    _has_safe_partial_geometry,
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
    RoutePath,
    RoutePath3D,
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
from temper_placer.router_v6.astar_nlayer_rust import (
    route_segment_3d_rust as _route_segment_3d,
)
from temper_placer.router_v6.clearance_floor import DEFAULT_ROUTING_CLEARANCE_MM
from temper_placer.router_v6.net_classification import classify_net_type
from temper_placer.router_v6.obstacle_map import (
    _circle_buffer_ring,
    _create_pad_polygon,
)
from temper_placer.router_v6.occupancy_grid import (
    OccupancyGrid,
    _area_rings,
    build_occupancy_grid,
)
from temper_placer.router_v6.pair_creepage import default_creepage_table, net_class_of
from temper_placer.router_v6.stage0_data import DesignRules

if TYPE_CHECKING:
    from temper_placer.router_v6.channel_mapping import ChannelMapping
    from temper_placer.router_v6.routing_space import RoutingSpace

logger = logging.getLogger(__name__)

__all__ = [
    "SegmentTier",
    "TierTally",
    "select_routing_grids_nlayer",
    "run_astar_pathfinding_nlayer",
]


class SegmentTier(Enum):
    """Which tier of the cascade resolved one waypoint segment.

    Exhaustive: ``_astar_route_nlayer`` records exactly one of these per
    segment attempt, at the point the outcome is decided. There is no
    "other" bucket and no count is ever inferred by subtracting one
    counter from another -- the failure mode that let
    ``mst_edges_fallback_count`` report edges A* *failed* to route as edges
    the fallback *landed* (``len(edges) - astar_routed_count``).
    """

    #: Cheap same-layer 2D search on the preferred/primary layer (Tier 1).
    PRIMARY_2D = "primary_2d"
    #: Whole-segment 2D detour on some other layer (Tier 2).
    ALTERNATE_2D = "alternate_2d"
    #: Full N-layer via-aware 3D search across every grid (Tier 3).
    NLAYER_VIA_3D = "nlayer_via_3d"
    #: No tier resolved it -- forced-segment / fail-closed decline (Tier 4).
    DECLINED = "declined"


@dataclass
class TierTally:
    """Per-tier segment counts, incremented by classification.

    Measured on the production board 2026-08-18 (route-from-scratch, 105
    nets, 126 segment attempts): Tier 1 resolved 20.6%, Tier 2 23.8%, Tier
    3 **0%** across 70 invocations, and 55.6% declined -- while Tier 3
    consumed 232s of the 455s route. Those numbers came from a throwaway
    monkeypatch harness; this type exists so they are observable from a
    normal run instead of being re-derived by the next person who wonders.
    """

    primary_2d: int = 0
    alternate_2d: int = 0
    nlayer_via_3d: int = 0
    declined: int = 0
    #: Tier-3 invocations, whether or not they resolved the segment. Kept
    #: separately from ``nlayer_via_3d`` because the interesting quantity is
    #: the gap between the two (70 calls, 0 successes).
    nlayer_via_3d_calls: int = 0

    def record(self, tier: SegmentTier) -> None:
        setattr(self, tier.value, getattr(self, tier.value) + 1)

    @property
    def attempts(self) -> int:
        """Total segment attempts -- an explicit sum, never a subtraction."""
        return self.primary_2d + self.alternate_2d + self.nlayer_via_3d + self.declined

    @property
    def resolved(self) -> int:
        """Segments some tier resolved -- again an explicit sum."""
        return self.primary_2d + self.alternate_2d + self.nlayer_via_3d

    def merge(self, other: TierTally) -> None:
        self.primary_2d += other.primary_2d
        self.alternate_2d += other.alternate_2d
        self.nlayer_via_3d += other.nlayer_via_3d
        self.declined += other.declined
        self.nlayer_via_3d_calls += other.nlayer_via_3d_calls

    def as_dict(self) -> dict[str, int]:
        return {
            "primary_2d": self.primary_2d,
            "alternate_2d": self.alternate_2d,
            "nlayer_via_3d": self.nlayer_via_3d,
            "declined": self.declined,
            "nlayer_via_3d_calls": self.nlayer_via_3d_calls,
            "attempts": self.attempts,
            "resolved": self.resolved,
        }


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
    pad_layer_start: str | None = None,
    pad_layer_end: str | None = None,
    tally: TierTally | None = None,
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

    ``pad_layer_start``/``pad_layer_end`` (2026-08-14, docs/evidence/
    2026-08-14-router-primary-grid-selection-fix.md): the net's own real
    pad layer at the OVERALL route's first/last waypoint, when known and
    routable (looked up by the caller from the board's actual pad
    positions, independent of the netclass-SSOT ``preferred_layer``).
    ``primary_grid`` (the SSOT/heuristic working layer) still governs
    Tier 1's search and every mid-route Tier-2 continuity anchor -- this
    intentionally keeps honouring the netclass's declared copper-weight/
    routing-convention intent for the body of the route, and for any net
    whose Tier 1 search succeeds outright (the common case; the pad-layer
    landing fix -- ``_land_route_on_pad_layers`` -- corrects that case's
    endpoints with a via after the fact). What changes here is narrower:
    the anchor layer used at the route's OWN start/end point (never a
    midpoint another segment continues from) falls back to the pad's real
    layer instead of blindly re-using ``primary_grid.layer_name`` there.
    That anchor point has nothing "before"/"after" it to stay continuous
    with -- it IS the pad -- so anchoring it to a layer the pad has no
    copper on is never useful, only ever a defect: it is exactly the
    mechanism that made ``cs_n``/``sdo``/``RTD_DRDY`` still fake-complete
    after the landing-via fix (Tier 2 anchored its own via at the pad's
    (x, y) using the wrong ``primary_grid`` layer, and the landing fix's
    later, separate via at the same point produced three layers stacked
    on one coordinate -- more than ``via_layer_pair`` can resolve). Fixing
    the anchor here means Tier 2 never creates that collision, so the
    landing fix becomes a no-op at that point (it already is correct) and
    no via ever needs to be reconciled with another via at the same spot.
    """
    waypoints = channel_path.waypoints
    if len(waypoints) < 2 or not grids:
        return None, 0

    preferred_layer = getattr(channel_path, "preferred_layer", None)
    # `channel_path` is untyped (ChannelPath in production, various
    # attribute-bag fixtures in tests), so `preferred_layer` is
    # `Any | None` to mypy even though it is a layer-name string whenever
    # present. Narrow with isinstance rather than passing it straight to
    # dict.get(): behaviorally identical (dict.get(None) or any
    # non-matching key already just fell through to the `or` fallback
    # below), but makes the str-keyed lookup explicit instead of relying
    # on grids.get() silently accepting a non-str key.
    primary_grid = (
        grids.get(preferred_layer) if isinstance(preferred_layer, str) else None
    ) or next(iter(grids.values()))
    other_grids = [g for name, g in grids.items() if name != primary_grid.layer_name]

    # The route's own start/end anchor layer: the net's real pad layer when
    # known and this board actually has a routing grid for it, else the same
    # primary_grid fallback as always. See the docstring above for why this
    # is scoped to just the two route-boundary anchors, not primary_grid
    # itself (which stays SSOT-driven for the search and for mid-route
    # continuity).
    effective_start_layer = (
        pad_layer_start if pad_layer_start and pad_layer_start in grids else primary_grid.layer_name
    )
    effective_end_layer = (
        pad_layer_end if pad_layer_end and pad_layer_end in grids else primary_grid.layer_name
    )
    last_segment_index = len(waypoints) - 2

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
            if tally is not None:
                tally.record(SegmentTier.PRIMARY_2D)
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
            # The route's own start/end anchor (effective_start_layer /
            # effective_end_layer) is the pad's real layer, which -- unlike
            # primary_grid.layer_name -- is NOT guaranteed to differ from
            # this segment's chosen alt_layer (other_grids only excludes
            # primary_grid.layer_name, not the pad's own layer). A mid-route
            # anchor (primary_grid.layer_name, the `else` branches below) IS
            # always guaranteed to differ from alt_layer by that same
            # construction, so it never needs this guard. Skipping a via
            # whose two endpoints would be the identical layer avoids
            # emitting a degenerate zero-span via (KiCad ``(layers "F.Cu"
            # "F.Cu")``) -- the point is already correctly landed the
            # moment alt_layer IS the pad's real layer, so there is nothing
            # left to correct.
            start_anchor_layer = effective_start_layer if i == 0 else primary_grid.layer_name
            if start_anchor_layer != alt_layer:
                if i == 0:
                    detailed_segments.append((start_world[0], start_world[1], start_anchor_layer))
                # Real via (layer change at identical x, y) -- never merged
                # by append_grid_path_point/append_exact_terminal_point,
                # which only ever collapse same-layer near-duplicates.
                detailed_segments.append((start_world[0], start_world[1], alt_layer))
                via_positions.append(start_world)
            elif i == 0:
                # First segment, but the pad's own real layer already IS
                # this segment's alt_layer -- nothing to anchor to, just
                # begin directly on alt_layer.
                detailed_segments.append((start_world[0], start_world[1], alt_layer))
            for node in alt_path:
                wx, wy = alt_grid.grid_to_world(node[0], node[1])
                append_grid_path_point(detailed_segments, (wx, wy, alt_layer), alt_tolerance)
            append_exact_terminal_point(
                detailed_segments, (goal_world[0], goal_world[1], alt_layer), alt_tolerance
            )
            # Anchor back to primary for continuity into the NEXT segment --
            # except at the route's own last waypoint, which has no "next
            # segment" to stay continuous with and must anchor on the pad's
            # real layer instead (see this function's docstring on
            # effective_end_layer). Same same-layer guard as the start
            # anchor above.
            end_anchor_layer = effective_end_layer if i == last_segment_index else primary_grid.layer_name
            if end_anchor_layer != alt_layer:
                detailed_segments.append((goal_world[0], goal_world[1], end_anchor_layer))
                via_positions.append(goal_world)
            routed_on_alt = True
            break
        if routed_on_alt:
            if tally is not None:
                tally.record(SegmentTier.ALTERNATE_2D)
            continue

        # Tier 3: full N-layer via-aware 3D search across every grid.
        net_rules = design_rules.get_rules_for_net(net_name) if design_rules else None
        tier3_start_layer = effective_start_layer if i == 0 else primary_grid.layer_name
        tier3_goal_layer = effective_end_layer if i == last_segment_index else primary_grid.layer_name
        result_3d = _route_segment_3d(
            start_world,
            goal_world,
            tier3_start_layer,
            tier3_goal_layer,
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
        if tally is not None:
            tally.nlayer_via_3d_calls += 1
        if result_3d is not None:
            if tally is not None:
                tally.record(SegmentTier.NLAYER_VIA_3D)
            world_path_3d, via_positions_3d = result_3d
            via_positions.extend(via_positions_3d)
            if i == 0:
                detailed_segments.append(world_path_3d[0])
            detailed_segments.extend(world_path_3d[1:])
            continue

        if not allow_forced_segments:
            if tally is not None:
                tally.record(SegmentTier.DECLINED)
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

        if tally is not None:
            tally.record(SegmentTier.DECLINED)
        forced_segments += 1
        failed_waypoint_indices.append(i + 1)
        if i == 0:
            detailed_segments.append((start_world[0], start_world[1], effective_start_layer))
        forced_end_layer = effective_end_layer if i == last_segment_index else primary_grid.layer_name
        detailed_segments.append((goal_world[0], goal_world[1], forced_end_layer))

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


def _pad_layer_at_point(
    pads: list[tuple[float, float, float, str]],
    x: float,
    y: float,
    tolerance_mm: float = 0.05,
) -> str | None:
    """The net's own pad layer at world point ``(x, y)``, or ``None`` when no
    pad of this net's own ``pads`` list matches, or the matching pad is
    THT/``ALL_LAYERS`` (layer containing ``"All"``/``"*.Cu"``/``"Through"``
    -- a via lands on every layer already, so there is no single "wrong
    layer" to report for a through-hole pad).

    Shared by ``_land_route_on_pad_layers`` (the post-route landing-via
    correction) and ``run_astar_pathfinding_nlayer``'s per-net driver (the
    primary_grid / route-boundary-anchor selection fix, docs/evidence/
    2026-08-14-router-primary-grid-selection-fix.md) -- one lookup, two
    call sites, so they cannot silently drift out of agreement about what
    "this net's own pad layer at this point" means.
    """
    for px, py, _radius, layer in pads:
        if abs(px - x) > tolerance_mm or abs(py - y) > tolerance_mm:
            continue
        if layer in ("All", "all") or "*.Cu" in layer or "Through" in layer:
            return None  # THT: nothing to correct
        return layer
    return None


def _attempt_pad_layer_landing(
    net_name: str,
    route_path: RoutePath3D,
    pad_centers_per_net: dict[str, list[tuple[float, float, float, str]]],
    grids: dict[str, OccupancyGrid],
    tolerance_mm: float = 0.05,
) -> tuple[RoutePath3D, tuple[str, ...]]:
    """Core landing-via attempt: insert a via at whichever of the route's
    own first/last emitted points sits exactly on a net pad's (x, y) but on
    a layer that pad has no copper on -- the exact defect this module's
    docstring above measures. Returns ``(attempted_route, blocked_ends)``.

    ``attempted_route`` always carries a landing via for every terminus
    whose pad-layer correction succeeded (or was unnecessary), and is left
    with its ORIGINAL, wrong-layer point for any terminus in
    ``blocked_ends`` ("start" and/or "end") -- a terminus whose pad's own
    layer was not free at that exact point (already claimed by an
    earlier-routed net). ``attempted_route`` must never be treated as a
    genuine completion when ``blocked_ends`` is non-empty: the whole point
    of the fail-closed contract this function's callers honour is that
    copper claiming to reach a pad it does not actually reach must never
    ship. It exists so a caller that wants an honest partial-route
    diagnostic (a net-level decline that still remembers what was
    legitimately computed, rather than discarding it outright -- see
    ``run_astar_pathfinding_nlayer``'s ``partial_paths`` handling) has
    something concrete to record.
    """
    pads = pad_centers_per_net.get(net_name) or []
    if not pads or not route_path.segments:
        return route_path, ()

    def _layer_free_at(x: float, y: float, layer: str) -> bool:
        grid = grids.get(layer)
        if grid is None:
            return False
        gx, gy = grid.world_to_grid(x, y)
        return grid.is_free(gx, gy)

    segments = list(route_path.segments)
    via_positions = list(route_path.via_positions)
    changed = False
    blocked: list[str] = []

    x0, y0, layer0 = segments[0]
    pad_layer_start = _pad_layer_at_point(pads, x0, y0, tolerance_mm)
    if pad_layer_start is not None and pad_layer_start != layer0:
        if _layer_free_at(x0, y0, pad_layer_start):
            segments.insert(0, (x0, y0, pad_layer_start))
            via_positions.insert(0, (x0, y0))
            changed = True
        else:
            blocked.append("start")

    # segments[-1] may have shifted if the start insertion happened above --
    # index from the end, not a stale pre-insertion offset.
    xn, yn, layern = segments[-1]
    pad_layer_end = _pad_layer_at_point(pads, xn, yn, tolerance_mm)
    if pad_layer_end is not None and pad_layer_end != layern:
        if _layer_free_at(xn, yn, pad_layer_end):
            segments.append((xn, yn, pad_layer_end))
            via_positions.append((xn, yn))
            changed = True
        else:
            blocked.append("end")

    if not changed:
        return route_path, tuple(blocked)

    attempted = RoutePath3D(
        net_name=route_path.net_name,
        segments=segments,
        via_positions=via_positions,
        path_length=route_path.path_length,
        via_count=len(via_positions),
        forced_segment_count=route_path.forced_segment_count,
        failed_waypoint_indices=route_path.failed_waypoint_indices,
    )
    return attempted, tuple(blocked)


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

    A thin, contract-preserving wrapper around ``_attempt_pad_layer_landing``
    -- see that function for the shared logic and for the (route, blocked)
    pair a caller wanting a partial-route diagnostic on decline should call
    directly instead of this wrapper.
    """
    attempted, blocked = _attempt_pad_layer_landing(
        net_name, route_path, pad_centers_per_net, grids, tolerance_mm
    )
    if blocked:
        return None
    return attempted


# ---------------------------------------------------------------------------
# Width- and creepage-aware C-space families (2026-08-16).
#
# Root cause being fixed (widths): the occupancy grids are built ONCE, with
# a static erosion of `default_trace_width_mm / 2` (= 0.1mm) around every
# static obstacle, and every routed track is stamped back into them at the
# flat board default width (0.2mm) instead of its own width. The router
# then emits tracks up to 5.0mm wide (the netclass SSOT, threaded into
# assign_trace_widths), so a 5.0mm HighVoltage track threads its
# centerline 0.1mm from a pad and overlaps it by 2.4mm -- measured as 204
# shorting_items on the 6-layer routed board (2026-08-15), of which w1_1
# (5.0mm) alone accounts for 120, split 110 pad<->track / 63 track<->track
# / 31 track<->via.
#
# Root cause being fixed (creepage): the same obstacle map reserved only
# CLEARANCE around obstacles and between routed nets (0.2mm -- the RULE 10
# track-involving floor), while the DRC grades HV<->LV pairs at 12.6mm
# creepage (PD3 reinforced) and HV<->HV tank pairs at 10.0mm (PD3
# functional). The A* therefore routed HV tracks 0.2mm from LV pads and
# tracks -- measured as ~300 pad<->track / track<->track creepage
# violations on the routed board (docs/evidence/2026-08-16-creepage-aware-
# cspace.md). The width-aware C-space (#1249) added per-net WIDTH halos but
# not CREEPAGE halos; this block adds them, keyed on the pair table
# configs/pair_creepage.generated.yaml (the DRU's own creepage rules
# resolved under KiCad's precedence -- see router_v6/pair_creepage.py).
#
# Fix: one occupancy-grid family per distinct (trace_width, floored
# clearance, creepage class) signature among the nets this run actually
# routes. Family (W, C, class) provides the C-space a net of width W,
# clearance C and class `class` needs:
#
#   * static obstacles (pads, vias, board edge, keepouts) eroded by
#     W/2 + C -- the searching net's own half-width plus the DRC's 0.2mm
#     track-involving floor -- so its centerline can never come within its
#     own copper extent of a static obstacle (no pad<->track shorts);
#   * every routed foreign net F stamped at
#     w_F/2 + max(cl_F, C, creepage(class_F, class)) + W/2 -- the marked
#     net's half-width plus the family's searching half-width plus a
#     clearance floor AND the creepage the DRU grades between F's class
#     and this family's class, so the edge-to-edge gap between F and any
#     net searching this family is
#     >= max(cl_F, C, creepage(class_F, class)) > 0 by construction
#     (no track<->track/via shorts or creepage violations), and the
#     separation no longer depends on which of a pair routed first;
#   * the searching net's own class's static pads additionally reserve
#     creepage(class, pad_class) -- stamped per-net as -1 (see
#     `_stamp_foreign_creepage_halos`) so the creepage halo is charged
#     against FOREIGN pads only: the pad's own net keeps its pads
#     enterable through the existing `_unblock_net_pads` mechanism
#     (which clears only -1 cells within the pad + W/2 + C), and the
#     -1 halo is never cleared by it (it sits outside that radius), so
#     no per-net halo can be accidentally routed through.
#
# Each net searches the family matching its own rule; routed copper is
# stamped into EVERY family at that family's radius (the same per-family
# structure profile_grids.py gives the legacy 2-layer path, extended here
# to the static obstacle layer). When `routing_spaces` is unavailable
# (synthetic test fixtures), a single identity family reusing the caller's
# grids keeps the historical behaviour.
# ---------------------------------------------------------------------------


def _family_signature(rule: object) -> tuple[float, float, str]:
    """The (width, floored-clearance, creepage-class) family key for a net."""
    width = float(getattr(rule, "trace_width_mm", 0.0) or 0.0)
    declared = float(getattr(rule, "clearance_mm", 0.0) or 0.0)
    class_name = str(getattr(rule, "name", "Default") or "Default")
    # DEFAULT_ROUTING_CLEARANCE_MM is RULE 10's floor: any pair where
    # either side is a track is graded at >= 0.2mm, so a class declaring
    # less (FinePitch 0.1) still needs the floor charged. Flooring here
    # also merges classes that behave identically once floored (Signal
    # 0.15 and Default 0.2, both 0.2mm wide) into one family.
    return (round(width, 6), round(max(declared, DEFAULT_ROUTING_CLEARANCE_MM), 6), class_name)


def _family_static_inflation(signature: tuple[float, float, str]) -> float:
    """Erosion for a family's static obstacle layer (W/2 + C)."""
    width, clearance, _class = signature
    return round(width / 2.0 + clearance, 9)


def _stamp_foreign_creepage_halos(
    net_name: str,
    grids: dict[str, OccupancyGrid],
    halos: dict[str, list[tuple[str, list, list]]],
) -> None:
    """Re-block the creepage halos around every FOREIGN pad/via/track/zone.

    ``_unblock_net_pads`` clears the -1 cells inside the routing net's own
    pad circles (radius + W/2 + C) -- and, on a dense board, whatever part
    of a foreign pad's much larger creepage halo happens to fall inside
    that circle. That leaves a hole through which the routing net could
    approach a foreign pad inside its required creepage distance, exactly
    the violation class this module exists to prevent. This re-stamps the
    full halo (pad extent + W/2 + C + pair creepage) of every obstacle NOT
    owned by the routing net, restricted to cells that are currently free
    (0): cells already blocked (-1) or already owned by a routed net stay
    untouched, and the routing net's own pads -- cleared to 0 by the
    unblock -- stay free unless a foreign halo genuinely covers them (in
    which case the honest answer is that the pad cannot be reached).

    ``halos`` is the per-layer ``[(net_name, outer_rings, holes)]`` list
    ``_build_width_families`` precomputed for this family (empty for
    synthetic fixtures / identity fallback, making this a no-op).
    """
    if not halos:
        return
    for layer, grid in grids.items():
        entries = halos.get(layer)
        if not entries:
            continue
        foreign = [(outer, holes) for n, outer, holes in entries if n != net_name]
        if not foreign:
            continue
        temp = np.full(grid.grid.shape, 1, dtype=np.int8)
        # Each entry's `outer`/`holes` are themselves the _area_rings
        # marshalling (lists of flat rings); concatenate across polygons.
        _tg.rasterize_area_polygons_py(
            temp,
            [ring for outer, _holes in foreign for ring in outer],
            [holes for _outer, holes in foreign],
            grid.origin[0],
            grid.origin[1],
            grid.cell_size,
        )
        inside = (temp == 0) & (grid.grid == 0)
        grid.grid[inside] = -1


def _family_halo_layers(
    family_signature: tuple[float, float, str],
    layer_grids: dict[str, OccupancyGrid],
    design_rules: DesignRules,
    pcb,
    escape_vias_map: dict[str, list[tuple[float, float, float]]] | None,
) -> dict[str, list[tuple[str, list, list]]]:
    """Per-layer creepage-halo polygons for one family, pre-marshalled.

    Each entry is ``(net_name, outer_rings, holes)`` ready for
    ``temper_geometry.rasterize_area_polygons_py`` (see
    ``_stamp_foreign_creepage_halos``). Sources mirror
    ``obstacle_map.build_obstacle_map``'s obstacle inventory -- pads, escape
    vias, pre-existing vias, pre-routed tracks and net-eligible zones -- so
    the A* reserves the same copper the static layer already blocks, plus
    the pair creepage the DRC grades between this family's class and the
    obstacle's net class. A zero-creepage pair contributes no entry: the
    grid's W/2 + C erosion already reserves that obstacle.
    """
    from shapely.geometry import Polygon

    from temper_placer.core.pin_geometry import pin_world_position

    table = default_creepage_table()
    _w, _c, family_class = family_signature
    base_inflation = _family_static_inflation(family_signature)
    routable_layers = set(layer_grids)

    def _halo_poly(radius_mm: float, base_poly) -> list | None:
        total = base_inflation + radius_mm
        if total <= 0.0:
            return None
        buffered = base_poly.buffer(total, quad_segs=4)
        if buffered.is_empty:
            return None
        outer_rings, holes = _area_rings(buffered)
        if not outer_rings:
            return None
        return [outer_rings, holes]

    per_layer: dict[str, list[tuple[str, list, list]]] = {layer: [] for layer in routable_layers}

    # Pads (mirrors obstacle_map.build_obstacle_map's pad loop).
    for comp in pcb.components:
        comp_x, comp_y = 0.0, 0.0
        if comp.initial_position:
            comp_x, comp_y = comp.initial_position
        angle = 0.0
        if comp.initial_rotation_quadrant is not None:
            angle = float(comp.initial_rotation_quadrant) * math.pi / 2.0
        for pin in comp.pins:
            if not pin.net:
                continue
            px, py = pin_world_position(pin, comp)
            pad_poly = _create_pad_polygon(pin, px, py, angle)
            pad_class = net_class_of(pin.net, design_rules)
            creep = table.required(family_class, pad_class)
            if creep <= 0.0:
                continue
            marshalled = _halo_poly(creep, pad_poly)
            if marshalled is None:
                continue
            if pin.layer in ["All", "all"] or "*.Cu" in pin.layer or "Through" in pin.layer:
                target_layers = routable_layers
            else:
                target_layers = {pin.layer} & routable_layers
            # `target_layers` is a set: iterate a stable order (layer name)
            # rather than the set's PYTHONHASHSEED-dependent iteration order
            # (scripts/check_hash_order_determinism.py). Each layer's list
            # gets exactly one append per pin either way -- no behavior change.
            for layer in sorted(target_layers):
                per_layer[layer].append((pin.net, marshalled[0], marshalled[1]))

    # Escape vias (through-hole: every routable layer).
    for net_name, vias in (escape_vias_map or {}).items():
        via_class = net_class_of(net_name, design_rules)
        creep = table.required(family_class, via_class)
        if creep <= 0.0:
            continue
        for vx, vy, diameter in vias:
            via_poly = Polygon(
                _circle_buffer_ring(vx, vy, diameter / 2.0, 8)
            )
            marshalled = _halo_poly(creep, via_poly)
            if marshalled is None:
                continue
            # `routable_layers` is a set: iterate a stable order (see the
            # pad loop above; scripts/check_hash_order_determinism.py).
            for layer in sorted(routable_layers):
                per_layer[layer].append((net_name, marshalled[0], marshalled[1]))

    # Pre-existing vias (through-hole: every routable layer).
    for via in getattr(pcb, "vias", None) or []:
        via_net = getattr(via, "net", None)
        if not via_net:
            continue
        via_class = net_class_of(via_net, design_rules)
        creep = table.required(family_class, via_class)
        if creep <= 0.0:
            continue
        via_poly = Polygon(
            _circle_buffer_ring(via.position[0], via.position[1], via.diameter / 2.0, 8)
        )
        marshalled = _halo_poly(creep, via_poly)
        if marshalled is None:
            continue
        # `routable_layers` is a set: iterate a stable order (see the pad
        # loop above; scripts/check_hash_order_determinism.py).
        for layer in sorted(routable_layers):
            per_layer[layer].append((via_net, marshalled[0], marshalled[1]))

    # Pre-routed tracks (their declared layer only).
    for track in getattr(pcb, "tracks", None) or []:
        track_net = getattr(track, "net", None)
        if not track_net or track.layer not in routable_layers:
            continue
        track_class = net_class_of(track_net, design_rules)
        creep = table.required(family_class, track_class)
        if creep <= 0.0:
            continue
        from shapely.geometry import LineString

        line = LineString([track.start, track.end])
        line_poly = line.buffer(track.width / 2.0, cap_style=1)
        marshalled = _halo_poly(creep, line_poly)
        if marshalled is None:
            continue
        per_layer[track.layer].append((track_net, marshalled[0], marshalled[1]))

    # Net-eligible zones (same eligibility rule obstacle_map uses; a zone
    # whose net class gets no pour in the routed output is stale input and
    # blocks nothing -- see obstacle_map.py's zone section).
    from temper_placer.router_v6._zone_pour_stitch import _zone_layers_for_net

    for zone in getattr(pcb, "zones", None) or []:
        if not hasattr(zone, "polygon") or not zone.polygon:
            continue
        net_names = [n for n in (getattr(zone, "net_classes", None) or []) if n]
        if net_names and not any(_zone_layers_for_net(n) for n in net_names):
            continue
        zone_creep = max(
            (table.required(family_class, net_class_of(n, design_rules)) for n in net_names),
            default=0.0,
        )
        if zone_creep <= 0.0:
            continue
        try:
            zone_poly = Polygon(zone.polygon)
            if not zone_poly.is_valid:
                zone_poly = zone_poly.buffer(0)
        except Exception:
            continue
        marshalled = _halo_poly(zone_creep, zone_poly)
        if marshalled is None:
            continue
        zone_layers = zone.layers if hasattr(zone, "layers") else ["F.Cu"]
        # `set(zone_layers) & routable_layers` is a set: iterate a stable
        # order (see the pad loop above; scripts/check_hash_order_determinism.py).
        for layer in sorted(set(zone_layers) & routable_layers):
            per_layer[layer].append((net_names[0] if net_names else "", marshalled[0], marshalled[1]))

    return {layer: entries for layer, entries in per_layer.items() if entries}


def _build_creepage_halos(
    families: dict[tuple[float, float, str], dict[str, OccupancyGrid]],
    design_rules: DesignRules,
    pcb,
    escape_vias_map: dict[str, list[tuple[float, float, float]]] | None,
) -> dict[tuple[float, float, str], dict[str, list[tuple[str, list, list]]]]:
    """Precompute each family's per-layer creepage-halo polygon lists."""
    halos: dict[tuple[float, float, str], dict[str, list[tuple[str, list, list]]]] = {}
    for signature, layer_grids in families.items():
        halos[signature] = _family_halo_layers(
            signature, layer_grids, design_rules, pcb, escape_vias_map
        )
    return halos


def _build_width_families(
    grids: dict[str, OccupancyGrid],
    routing_spaces: dict[str, RoutingSpace] | None,
    routable_nets: list[str],
    design_rules: DesignRules,
    pcb=None,
    escape_vias_map: dict[str, list[tuple[float, float, float]]] | None = None,
) -> tuple[
    dict[tuple[float, float, str], dict[str, OccupancyGrid]],
    dict[str, tuple[float, float, str]],
    dict[tuple[float, float, str], dict[str, list[tuple[str, list, list]]]],
]:
    """Build one occupancy-grid family per (width, clearance, class) signature.

    Returns ``(families, family_of_net, family_halos)``. ``families`` maps
    a signature to a per-layer grid dict rebuilt from ``routing_spaces``
    with that signature's static erosion; ``family_of_net`` maps each
    routable net to the signature it searches; ``family_halos`` maps each
    family to its precomputed per-layer creepage-halo polygon lists (empty
    without a ``pcb`` -- synthetic fixtures have no obstacles to halo).
    With ``routing_spaces=None`` a single identity family reuses ``grids``
    unchanged (historical behaviour, and what the unit tests exercise).
    """
    family_of_net = {
        net_name: _family_signature(design_rules.get_rules_for_net(net_name))
        for net_name in routable_nets
    }
    if not routing_spaces:
        # Identity fallback: one family, the caller's grids as-is.
        default_signature = _family_signature(design_rules.get_rules_for_net(""))
        return {default_signature: grids}, family_of_net, {}

    families: dict[tuple[float, float, str], dict[str, OccupancyGrid]] = {}
    # Build in `grids`' own layer order (deterministic; the caller's dict
    # is already in engine-preference order) so `next(iter(...))` picks in
    # the same order the caller's grids did.
    for net_name in routable_nets:
        signature = family_of_net[net_name]
        if signature in families:
            continue
        inflation = _family_static_inflation(signature)
        families[signature] = {
            layer: build_occupancy_grid(routing_spaces[layer], inflation_mm=inflation)
            for layer in grids
            if layer in routing_spaces
        }
    family_halos = _build_creepage_halos(families, design_rules, pcb, escape_vias_map) if pcb else {}
    return families, family_of_net, family_halos


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
    routing_spaces: dict[str, RoutingSpace] | None = None,
) -> PathfindingResult:
    """N-layer, via-aware generalization of ``astar_pathfinding.run_astar_pathfinding``.

    Same per-net driver shape (net ordering, pad unblocking, fail-closed
    exception handling, failure reporting) as the production function,
    generalized to accept an arbitrary-size ``grids`` dict instead of a
    hardcoded ``grid`` + ``alternate_grid`` pair. See this module's
    docstring for what is deliberately out of scope for this spike
    (all-pad-tree, congestion tensor, thermal field support is threaded
    through but untested at scale, rip-up-and-reroute).

    ``routing_spaces`` (2026-08-16): the Stage-2 per-layer
    ``RoutingSpace`` objects, used to rebuild each width family's grids
    with that family's static C-space erosion. ``None`` (synthetic
    fixtures, and every pre-existing unit test) keeps a single identity
    family over the caller's grids -- see ``_build_width_families``.
    """
    if not grids:
        raise ValueError("No occupancy grids available for N-layer A* pathfinding")
    if design_rules is None:
        design_rules = DesignRules()

    # Typed as the PathfindingResult field's declared union (dict is
    # invariant in its value type, so a narrower dict[str, RoutePath3D]
    # here would not be assignable to routed_paths=... below even though
    # every value actually stored is a RoutePath3D) -- not a behavior
    # change, just matching the widened annotation PathfindingResult
    # already declares.
    routed_paths: dict[str, RoutePath | RoutePath3D] = {}
    failed_nets_set: set[str] = set()
    failure_reports: dict[str, RoutingFailureReport] = {}
    blocker_history: dict[str, set[str]] = {}
    # Task 2 (docs/evidence/2026-08-14-router-primary-grid-selection-fix.md):
    # a net-level decline that still has legitimately computed geometry --
    # a landing via blocked at one endpoint, or a forced-segment refusal
    # partway through a long multi-waypoint chain -- keeps that geometry
    # here rather than discarding it outright. Mirrors the SAME pattern
    # ``_astar_reconstruct.py``'s tree-route path already uses for its own
    # partial declines (``_has_safe_partial_geometry`` gate, ``partial_paths``
    # -> ``RoutingResults.partial_routes``): NEVER written to the board
    # (``_write_routes_to_content`` only ever reads ``compiled_routes``,
    # built from ``routed_paths``/``routed`` completions) and NEVER counted
    # toward ``success_count`` (which sums only ``routed_paths``/
    # ``tree_routes``) -- a diagnostic record, not a second copper channel.
    partial_paths: dict[str, RoutePath | RoutePath3D] = {}
    # Visibility counter (this task's "make the disagreement visible"
    # requirement): how many net endpoints had a netclass-SSOT
    # ``preferred_layer`` that disagreed with the net's own real pad layer,
    # and were anchored on the pad's real layer instead. Never silently
    # folded into either "success" or "failure" -- most of these nets still
    # route and land correctly; this only reports how often the SSOT and
    # the physical board disagreed, not whether the net worked.
    layer_divergence_count = 0

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

    # Width/creepage-aware C-space families (2026-08-16): one grid family
    # per (width, clearance, creepage class) signature among the nets this
    # run routes, so the static obstacle layer and every routed-copper
    # stamp reserve the searching net's real half-width and the DRC's pair
    # creepage instead of the flat 0.1mm/0.2mm board defaults.
    families, family_of_net, family_halos = _build_width_families(
        grids, routing_spaces, routable_nets, design_rules, pcb, escape_vias_map
    )

    per_path_latency_ms: dict[str, float] = {}
    fallback_count = 0
    # Per-tier segment accounting, incremented by classification inside
    # _astar_route_nlayer (see TierTally). Observability only -- never
    # folded into success/failure counts.
    tier_tally = TierTally()

    def attempt_route(net_name: str):
        nonlocal fallback_count, layer_divergence_count
        channel_path = channel_mapping.channel_paths[net_name]
        net_id = net_ids[net_name]
        # This net's OWN family: the grids whose static erosion and
        # routed-copper stamps already carry this net's width and
        # clearance -- never the shared `grids` dict directly.
        family_key = family_of_net[net_name]
        active_grids = families[family_key]
        family_inflation = _family_static_inflation(family_key)
        net_rule = design_rules.get_rules_for_net(net_name)
        # Self-creepage (2026-08-16): a same-family net's halo stamp around
        # THIS net's pads carries creepage(family_class, family_class) --
        # nonzero only for HighVoltageTank (10.0mm, RULE 5a tank<->tank).
        # The unblock must punch through that leftover ring too, or a tank
        # net could never reach its own pads after another tank net routed.
        # The over-wide circle's clips into foreign halos are re-blocked by
        # _stamp_foreign_creepage_halos immediately below.
        self_creepage = default_creepage_table().self_creepage(family_key[2])
        unblock_inflation = family_inflation + self_creepage
        primary_grid_for_budget = active_grids.get(channel_path.preferred_layer) or next(
            iter(active_grids.values())
        )

        # Root-cause fix (Task 1, docs/evidence/
        # 2026-08-14-router-primary-grid-selection-fix.md): the net's own
        # real pad layer at the route's overall start/end, looked up from
        # the board's actual pad positions BEFORE any search runs. Passed
        # through to _astar_route_nlayer so Tier 2/3 anchor the route's own
        # boundary points on the pad's real layer instead of blindly
        # re-using the netclass-SSOT preferred_layer there -- see that
        # function's docstring for why this is scoped to just the two
        # route-boundary anchors, not primary_grid itself.
        pads_for_net = pad_centers_per_net.get(net_name) or []
        pad_layer_start = pad_layer_end = None
        if pads_for_net and channel_path.waypoints:
            sx, sy = channel_path.waypoints[0]
            ex, ey = channel_path.waypoints[-1]
            pad_layer_start = _pad_layer_at_point(pads_for_net, sx, sy)
            pad_layer_end = _pad_layer_at_point(pads_for_net, ex, ey)
            for end_name, pad_layer in (("start", pad_layer_start), ("end", pad_layer_end)):
                if pad_layer is not None and pad_layer != channel_path.preferred_layer:
                    layer_divergence_count += 1
                    logger.info(
                        "net %r: netclass-SSOT preferred_layer=%r disagrees with the "
                        "%s pad's own layer=%r; anchoring that route endpoint on the "
                        "pad's real layer instead of the SSOT layer.",
                        net_name, channel_path.preferred_layer, end_name, pad_layer,
                    )

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
            active_grids,
            inflation_mm=unblock_inflation,
            escape_vias_map=escape_vias_map,
            existing_vias_map=existing_vias_per_net,
        )

        # Creepage-aware C-space (2026-08-16): the unblock above cleared the
        # -1 cells inside this net's own pad circles -- including whatever
        # part of a foreign pad's much larger creepage halo fell inside
        # them. Re-stamp the foreign halos so this net cannot route through
        # another net's required creepage distance (see
        # _stamp_foreign_creepage_halos). No-op for synthetic fixtures
        # (family_halos empty).
        _stamp_foreign_creepage_halos(net_name, active_grids, family_halos.get(family_key, {}))

        # Root-cause fix (2026-08-17, docs/evidence/2026-08-17-hop-
        # reachability-rootcause-and-fix.md): Tier 3's own
        # `segment_3d_fallback_max_iter` was left at the flat, unscaled
        # `_SEGMENT_3D_FALLBACK_MAX_ITER` (200_000) default on every call
        # here -- never fed the same per-net, span-derived budget Tier 1/2
        # already get via `per_net_max_iter` above. That default's own
        # docstring says it was sized for "short (waypoint-scale) fallback-
        # tier calls" (U1) -- true when Tier 3 was a last-resort for 2-pad
        # nets, no longer true once `enable_all_pad_tree` made it the
        # primary search for every hop of a multi-pad net, some spanning
        # 100-190mm on this board.
        #
        # `max(per_net_max_iter, _SEGMENT_3D_FALLBACK_MAX_ITER)`: never
        # LOWERS Tier 3's budget for any net (per_net_max_iter's own floor
        # is 1000, well under 200_000, for genuinely short/small nets) --
        # only ever raises it, up to per_net_max_iter's own ceiling (the
        # outer max_iter, 1,000,000 by default), for nets whose own
        # span-derived budget is already larger, matching Tier 1/2 instead
        # of under-cutting them. Verified safe: full router_v6 regression
        # suite (394 passed, 2 pre-existing unrelated failures), bounded
        # at 1,000,000 iterations worst case (never unbounded).
        #
        # NOT shipped: a bolder flat-2,000,000-iteration floor was tried
        # and measured (docs/evidence, §5) to recover 3 specific Class-2
        # hops a read-only probe had found recoverable at that budget --
        # this span-scaled version, capped at 1,000,000, does NOT recover
        # those same 3 hops (measured on a full route, not assumed). It is
        # shipped anyway, not the bolder version, because the bolder
        # version's full-board time/DRC/connectivity impact could not be
        # completed and verified within this task's time budget -- per
        # this project's own hard rule against shipping an unverified
        # change, and per the coordinator's explicit warning that touching
        # this exact budget already produced one reverted fake completion
        # from a sibling who did not verify first. This version is
        # reported as a real (if measured-modest) correctness fix on its
        # own terms -- Tier 3 no longer contradicts Tier 1/2's own budget
        # decision for the same net -- not as the fix for the 3 specific
        # recoverable hops, which remains open (see the evidence doc's
        # "what remains" section).
        route_path, fb = _astar_route_nlayer(
            net_name,
            channel_path,
            active_grids,
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
            pad_layer_start=pad_layer_start,
            pad_layer_end=pad_layer_end,
            segment_3d_fallback_max_iter=max(per_net_max_iter, _SEGMENT_3D_FALLBACK_MAX_ITER),
            tally=tier_tally,
        )
        fallback_count += fb

        landing_blocked = False
        landing_blocked_ends: tuple[str, ...] = ()
        if route_path and route_path.forced_segment_count == 0:
            # Must run BEFORE _restore_net_pads: the pad's own-layer grid
            # cells are only unblocked (static -1 -> free 0) between
            # _unblock_net_pads above and _restore_net_pads below. Checking
            # after restoration would see every never-traversed pad cell
            # reset back to -1 and fail every landing closed, not just the
            # genuine collisions.
            attempted, blocked_ends = _attempt_pad_layer_landing(
                net_name, route_path, pad_centers_per_net, active_grids
            )
            if blocked_ends:
                # Task 2: net-level decline stays net-level (this net's
                # copper must never claim a pad it does not reach -- see
                # this module's FAILURE_REASON_PAD_LAYER_LANDING_BLOCKED
                # docstring history), but the geometry that WAS legitimately
                # computed (every segment, plus a landing via at whichever
                # end succeeded) is preserved as a partial-route diagnostic
                # rather than discarded outright -- never written to the
                # board, never counted as a completion (see partial_paths's
                # docstring above).
                landing_blocked = True
                landing_blocked_ends = blocked_ends
                if _has_safe_partial_geometry(attempted):
                    partial_paths[net_name] = attempted
                route_path = None
            else:
                route_path = attempted

        _restore_net_pads(restoration)

        ripped_ids: list[int] = []
        if route_path and route_path.forced_segment_count > 0:
            blockers = _identify_blocking_nets(channel_path, list(active_grids.values()))
            if blockers:
                ripped_ids = sorted(blockers)
        blocker_names = [id_to_net.get(rid, f"Unknown-{rid}") for rid in ripped_ids]
        blocker_history.setdefault(net_name, set()).update(blocker_names)

        def congestion_region():
            return channel_path.waypoints[len(channel_path.waypoints) // 2] if channel_path.waypoints else None

        if route_path:
            if route_path.forced_segment_count > 0:
                # Same partial-route preservation as the landing-blocked
                # path above, for the OTHER net-level decline shape
                # (Tier 1-3 all failed partway through a multi-waypoint
                # chain): keep whatever prefix of real, A*-searched geometry
                # was computed before the failure, as a diagnostic only --
                # _has_safe_partial_geometry rejects a forced/fabricated
                # edge, matching the exact gate _astar_reconstruct.py's
                # tree-route path already uses for this same shape.
                if _has_safe_partial_geometry(route_path):
                    partial_paths[net_name] = route_path
                return _forced_segment_decline([], congestion_region())
            routed_paths[net_name] = route_path
            # Width/creepage-aware stamp (2026-08-16): the routed net's own
            # real width (not the flat 0.2mm board default, which
            # under-reserved a 5.0mm HighVoltage track's halo by 2.2mm and
            # was the measured cause of the 204 shorting_items on the
            # 6-layer board), into EVERY family at that family's
            # searching-net radius: w_F/2 + max(cl_F, C,
            # creepage(class_F, family_class)) + W/2. Each family's static
            # layer already reserves W/2 + C, so the separation between
            # this net and any net searching that family is >=
            # max(cl_F, C, creepage) > 0 edge-to-edge by construction --
            # the creepage term is what keeps an HV track 12.6mm from an LV
            # net's copper instead of 0.2mm (the DRC-graded bar, resolved
            # from the DRU by router_v6/pair_creepage).
            creepage_table = default_creepage_table()
            for _fam_key, _fam_grids in families.items():
                _fam_w, _fam_c, _fam_class = _fam_key
                pair_creepage = creepage_table.required(net_rule.name, _fam_class)
                _mark_route_blocked(
                    route_path,
                    _fam_grids,
                    trace_width=net_rule.trace_width_mm,
                    clearance=max(net_rule.clearance_mm, _fam_c, pair_creepage)
                    + _fam_w / 2.0,
                    net_id=net_id,
                    via_diameter=net_rule.via_diameter_mm,
                )
            return True, "", [], None, None

        if landing_blocked:
            reason = f"{FAILURE_REASON_PAD_LAYER_LANDING_BLOCKED}:{','.join(landing_blocked_ends)}"
            return False, reason, [], congestion_region(), None
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
        partial_paths=partial_paths,
        layer_divergence_count=layer_divergence_count,
        tier_tally=tier_tally.as_dict(),
    )
