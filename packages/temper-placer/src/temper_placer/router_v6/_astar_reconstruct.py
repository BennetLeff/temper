# mypy: ignore-errors
"""
Router V6: Route construction from A* search results.

Owns net selection and result aggregation: which nets are routed, in what
order, how per-net outcomes are collected into a PathfindingResult, and how
a declined net is reported. The segment-level search strategies and route
builders it drives live in _astar_search.py; the result and decline-reason
types live in _routing_reports.py; the per-net policy predicates live in
_net_policy.py.

Part of temper-N6 decomposition -- split from astar_pathfinding.py.
"""

from __future__ import annotations

import logging
import math
import time
from collections import deque

logger = logging.getLogger(__name__)

from temper_placer.router_v6._astar_ordering import _compute_net_order
from temper_placer.router_v6._astar_search import (
    _MAX_REROUTE_ATTEMPTS_PER_NET,
    _SEGMENT_3D_FALLBACK_MAX_ITER,
    _TREE_SEGMENT_3D_FALLBACK_MAX_ITER,
    _astar_route,
    _astar_route_multilayer,
    _astar_route_with_ripup,
    _has_safe_partial_geometry,
    _segment_search,
)
from temper_placer.router_v6._astar_theta_star import (
    log_los_bb_stats,
    reset_los_bb_stats,
)
from temper_placer.router_v6._net_policy import (
    _allow_forced_segments,
    _should_route,
)
from temper_placer.router_v6._routing_reports import (
    FAILURE_REASON_PROVER_ERROR,
    RULE_ID_FORCED_SEGMENT_FAIL_CLOSED,
    PathfindingResult,
    RoutingFailureReport,
    TreeRoutingFailure,
    _forced_segment_decline,
)
from temper_placer.router_v6.astar_core import RoutePath, RoutePath3D
from temper_placer.router_v6.astar_grid import (
    _build_tht_pad_locations,
    _extract_existing_via_centers_per_net,
    _extract_pad_centers_per_net,
    _mark_route_blocked,
    _restore_net_pads,
    _unblock_net_pads,
    _unmark_route_blocked,
)
from temper_placer.router_v6.channel_mapping import ChannelMapping
from temper_placer.router_v6.net_classification import classify_net_type
from temper_placer.router_v6.occupancy_grid import OccupancyGrid
from temper_placer.router_v6.stage0_data import DesignRules
from temper_placer.router_v6.tree_route_geometry import TreeRouteBranch, TreeRouteGeometry

# Names above are re-exported for import-site and monkeypatch stability:
# astar_pathfinding.py and the router_v6 tests import several of them from
# this module by name, and run_astar_pathfinding resolves the search
# entry points through this module's globals so tests can patch them here.
__all__ = [
    "FAILURE_REASON_PROVER_ERROR",
    "RULE_ID_FORCED_SEGMENT_FAIL_CLOSED",
    "PathfindingResult",
    "RoutingFailureReport",
    "TreeRoutingFailure",
    "_MAX_REROUTE_ATTEMPTS_PER_NET",
    "_SEGMENT_3D_FALLBACK_MAX_ITER",
    "_TREE_SEGMENT_3D_FALLBACK_MAX_ITER",
    "_astar_route",
    "_astar_route_multilayer",
    "_astar_route_with_ripup",
    "_has_safe_partial_geometry",
    "_segment_search",
    "run_astar_pathfinding",
]


def run_astar_pathfinding(
    channel_mapping: ChannelMapping,
    grid: OccupancyGrid,
    design_rules: DesignRules | None = None,
    alternate_grid: OccupancyGrid | None = None,
    _components: list | None = None,
    pcb=None,  # For accessing pads
    escape_vias_map: dict[str, list[tuple[float, float, float]]] | None = None,
    use_theta_star: bool = False,
    max_nets: int | None = None,
    target_nets: list[str] | None = None,
    use_lazy_theta_star: bool = False,
    congestion_tensor=None,  # U7 / R11: PathFinder history cost
    max_iter: int = 1_000_000,
    enable_coarse_to_fine: bool = False,
    coarse_factor: int = 4,
    corridor_buffer_cells: int = 12,
    bottleneck_widths: dict[str, float] | None = None,
    net_budgets: dict[str, int] | None = None,
    thermal_flat=None,  # U8: thermal cost field (rows*cols, float32)
    thermal_weight: float = 0.0,  # U8: multiplier on per-cell thermal cost
    enforce_all_pad_tree: bool = False,
    tree_3d_fallback_max_iter: int = _TREE_SEGMENT_3D_FALLBACK_MAX_ITER,
) -> PathfindingResult:
    """Run A* or Theta* pathfinding to generate routing paths."""
    if design_rules is None:
        design_rules = DesignRules()
    if tree_3d_fallback_max_iter <= 0:
        raise ValueError("tree_3d_fallback_max_iter must be positive")
    all_grids: dict[str, OccupancyGrid] = {grid.layer_name: grid}
    if alternate_grid:
        all_grids[alternate_grid.layer_name] = alternate_grid

    routed_paths: dict[str, RoutePath | RoutePath3D] = {}
    failed_nets_set: set[str] = set()
    failure_reports: dict[str, RoutingFailureReport] = {}
    tree_failures: dict[str, TreeRoutingFailure] = {}
    partial_paths: dict[str, RoutePath | RoutePath3D] = {}
    tree_routes: dict[str, TreeRouteGeometry] = {}
    partial_tree_routes: dict[str, TreeRouteGeometry] = {}
    ripup_counts: dict[str, int] = {}
    blocker_history: dict[str, set[str]] = {}

    tht_locations: set = set()
    pad_centers_per_net: dict[str, list[tuple[float, float, float, str]]] = {}
    existing_vias_per_net: dict[str, list[tuple[float, float, float]]] = {}

    if pcb:
        tht_locations = _build_tht_pad_locations(pcb)
        if tht_locations:
            print(f"  Found {len(tht_locations)} THT pads for layer switching")
        pad_centers_per_net = _extract_pad_centers_per_net(pcb)
        existing_vias_per_net = _extract_existing_via_centers_per_net(pcb)

    net_order = _compute_net_order(channel_mapping, bottleneck_widths=bottleneck_widths)
    routable_nets = [n for n in net_order if _should_route(n)]

    if target_nets:
        target_set = set(target_nets)
        print(f"  Profiling Mode: Routing only {len(target_nets)} specific nets")
        routable_nets = [n for n in routable_nets if n in target_set]
    elif max_nets is not None:
        print(f"  Limiting to first {max_nets} nets for profiling...")
        routable_nets = routable_nets[:max_nets]

    if congestion_tensor is not None:
        from temper_placer.router_v6.congestion_tensor import CongestionTensor

        if congestion_tensor.array.shape != (grid.height_cells, grid.width_cells):
            congestion_tensor = CongestionTensor.zeros(grid.height_cells, grid.width_cells)

    net_ids = {name: i + 1 for i, name in enumerate(routable_nets)}
    id_to_net = {v: k for k, v in net_ids.items()}

    base_inflation = design_rules.default_trace_width_mm / 2.0

    reroute_queue: deque[str] = deque()

    reset_los_bb_stats()
    fallback_count = 0

    def attempt_route(
        net_name: str,
    ) -> tuple[bool, str, list[str], tuple[float, float] | None, str | None]:
        """Attempt to route one net.

        Returns ``(success, reason, blockers, region, rule_id)``. ``rule_id``
        is only meaningful when ``success`` is ``False`` -- see
        ``RoutingFailureReport``'s docstring for the candor contract it
        implements (``attribution_gap`` is derived from it, never threaded
        separately).
        """
        nonlocal fallback_count
        channel_path = channel_mapping.channel_paths[net_name]
        net_id = net_ids[net_name]
        tree_route_active = enforce_all_pad_tree and len(channel_path.waypoints) > 2
        planned_tree_active = tree_route_active and channel_path.terminal_tree is not None

        primary_grid = all_grids.get(channel_path.preferred_layer, grid)

        if net_budgets is not None:
            per_net_max_iter = net_budgets.get(net_name, max_iter)
        else:
            per_net_max_iter = max_iter
            waypoints = channel_path.waypoints
            if waypoints and len(waypoints) >= 2:
                dx = abs(waypoints[-1][0] - waypoints[0][0])
                dy = abs(waypoints[-1][1] - waypoints[0][1])
                span_cells = int((dx + dy) / primary_grid.cell_size)
                grid_area = primary_grid.width_cells * primary_grid.height_cells
                ellipse_cells = int(math.pi * (span_cells / 2.0) ** 2)
                derived = max(1000, min(ellipse_cells, grid_area))
                per_net_max_iter = min(max_iter, derived)
        alt_layer = next(
            (layer for layer in all_grids if layer != channel_path.preferred_layer), None
        )
        active_alternate = all_grids.get(alt_layer) if alt_layer else alternate_grid

        restoration = _unblock_net_pads(
            net_name,
            pad_centers_per_net,
            all_grids,
            inflation_mm=base_inflation,
            escape_vias_map=escape_vias_map,
            existing_vias_map=existing_vias_per_net,
        )

        if planned_tree_active:
            from temper_placer.router_v6.terminal_tree_execution import (
                NO_ROUTABLE_LAYER,
                execute_terminal_tree,
            )

            execution = execute_terminal_tree(
                channel_path.terminal_tree,
                channel_path.terminals,
                all_grids,
                max_iter=per_net_max_iter,
                net_id=net_id,
                trace_width=design_rules.default_trace_width_mm,
                clearance=design_rules.default_clearance_mm,
            )
            completed_geometry = TreeRouteGeometry(
                net_name=net_name,
                branches=tuple(
                    TreeRouteBranch(edge=edge, path=path)
                    for edge, path in execution.completed_edges
                ),
            )
            if execution.disposition.value == "routed":
                tree_routes[net_name] = completed_geometry
                _restore_net_pads(restoration)
                print(f"      ✓ {net_name} routed successfully", flush=True)
                return True, "", [], None, None
            if completed_geometry.branches:
                partial_tree_routes[net_name] = completed_geometry
            failed_edge = execution.failed_edges[0]
            assert failed_edge is not None
            terminal = next(
                item for item in channel_path.terminals if item.identity == failed_edge.target
            )
            # A layer-selection rejection carries its own diagnostic (which
            # layers the pads share, which layers have grids).  Reporting it
            # as a plain "no legal path" would hide a router configuration
            # gap inside the congestion bucket.
            edge_reason = execution.failure_reasons.get(failed_edge, "no_legal_path")
            summary_reason = (
                NO_ROUTABLE_LAYER if edge_reason.startswith(NO_ROUTABLE_LAYER) else "no_path"
            )
            tree_failures[net_name] = TreeRoutingFailure(
                unresolved_terminal=(terminal.center.x, terminal.center.y),
                completed_edge_count=len(execution.completed_edges),
                reason=edge_reason,
            )
            _restore_net_pads(restoration)
            print(f"      ✗ {net_name} INCOMPLETE: {edge_reason}", flush=True)
            if summary_reason == NO_ROUTABLE_LAYER:
                # b39b382d split this decline out as a router-configuration
                # gap (no occupancy grid for any shared layer). The
                # forced-segment fail-closed rule does not explain it, so
                # naming that rule here would fabricate an attribution --
                # exactly what U1's candor discipline forbids. Report the
                # gap with no rule_id (attribution_gap) instead.
                return False, summary_reason, [], (terminal.center.x, terminal.center.y), None
            # execute_terminal_tree always calls with allow_forced_segments=False
            # (terminal_tree_execution.py) -- this is the same fail-closed gate,
            # just reached via the tree-execution path rather than _astar_route.
            return _forced_segment_decline([], (terminal.center.x, terminal.center.y))

        route_path, ripped_ids, fb = _astar_route_with_ripup(
            net_name,
            channel_path,
            primary_grid,
            design_rules,
            net_ids,
            active_alternate,
            tht_locations,
            all_grids=all_grids,
            use_theta_star=use_theta_star,
            use_lazy_theta_star=use_lazy_theta_star,
            congestion_tensor=congestion_tensor,
            max_iter=per_net_max_iter,
            enable_coarse_to_fine=enable_coarse_to_fine,
            coarse_factor=coarse_factor,
            corridor_buffer_cells=corridor_buffer_cells,
            thermal_flat=thermal_flat,
            thermal_weight=thermal_weight,
            allow_forced_segments=_allow_forced_segments(net_name, design_rules, tree_route_active),
            segment_3d_fallback_max_iter=(
                tree_3d_fallback_max_iter if tree_route_active else _SEGMENT_3D_FALLBACK_MAX_ITER
            ),
        )
        fallback_count += fb

        _restore_net_pads(restoration)

        blocker_names = [id_to_net.get(rid, f"Unknown-{rid}") for rid in ripped_ids]
        blocker_history.setdefault(net_name, set()).update(blocker_names)

        def congestion_region() -> tuple[float, float] | None:
            if not channel_path.waypoints:
                return None
            return channel_path.waypoints[len(channel_path.waypoints) // 2]

        if route_path:
            if tree_route_active and route_path.forced_segment_count:
                failed_index = route_path.failed_waypoint_indices[0]
                tree_failures[net_name] = TreeRoutingFailure(
                    unresolved_terminal=channel_path.waypoints[failed_index],
                    completed_edge_count=failed_index - 1,
                    reason="no_legal_path",
                )
                if _has_safe_partial_geometry(route_path):
                    partial_paths[net_name] = route_path
                print(
                    f"      ✗ {net_name} INCOMPLETE: no legal tree edge to "
                    f"{channel_path.waypoints[failed_index]}",
                    flush=True,
                )
                return _forced_segment_decline([], channel_path.waypoints[failed_index])

            # No net class is exempt from the forced-segment gate (see
            # _allow_forced_segments docstring, which is unconditional --
            # no need to re-call it here). _astar_route /
            # _astar_route_multilayer can still return a non-None path with
            # forced_segment_count > 0; catch that here and fail the net
            # honestly rather than fabricating clearance-violating copper.
            if route_path.forced_segment_count > 0 and not tree_route_active:
                print(
                    f"      ✗ {net_name} FAILED: no legal path found "
                    f"(forced segment disallowed)",
                    flush=True,
                )
                return _forced_segment_decline(
                    [],
                    channel_path.waypoints[len(channel_path.waypoints) // 2]
                    if channel_path.waypoints
                    else None,
                )
            if congestion_tensor is not None:
                if hasattr(route_path, "coordinates"):
                    congestion_tensor.increment_path(route_path.coordinates, primary_grid)
                elif hasattr(route_path, "segments"):
                    coords = []
                    for seg in route_path.segments:
                        coords.append((seg[0], seg[1]))
                    congestion_tensor.increment_path(coords, primary_grid)
            print(f"      ✓ {net_name} routed successfully", flush=True)

            for ripped_id in ripped_ids:
                if ripped_id in id_to_net:
                    ripped_name = id_to_net[ripped_id]
                    if ripped_name in routed_paths:
                        ripped_path = routed_paths[ripped_name]
                        _unmark_route_blocked(
                            ripped_path,
                            all_grids,
                            design_rules.default_trace_width_mm,
                            design_rules.default_clearance_mm,
                            ripped_id,
                        )
                        del routed_paths[ripped_name]
                        reroute_queue.append(ripped_name)
                        ripup_counts[ripped_name] = ripup_counts.get(ripped_name, 0) + 1

            routed_paths[net_name] = route_path
            _mark_route_blocked(
                route_path,
                all_grids,
                trace_width=design_rules.default_trace_width_mm,
                clearance=design_rules.default_clearance_mm,
                net_id=net_id,
            )

            # forced_segment_count > 0 always returns above now (no net
            # class is exempt from the fail-closed gate) -- a route
            # reaching this point is genuinely legal, never forced.
            return True, "", [], None, None

        # Neither branch below currently has a rule-level attribution: a
        # None ``route_path`` only occurs when ``_astar_route`` /
        # ``_astar_route_multilayer`` were given fewer than two waypoints
        # (see their early-return guards), which is a channel-topology
        # anomaly, not a discharged-or-not safety rule. Report the honest
        # gap rather than inventing a rule name for either case.
        if blocker_names:
            print(
                f"      ✗ {net_name} FAILED: congestion (blockers: {', '.join(blocker_names[:3])})",
                flush=True,
            )
            return False, "congestion", blocker_names, congestion_region(), None
        else:
            print(f"      ✗ {net_name} FAILED: no path found", flush=True)
            return False, "no_path", [], congestion_region(), None

    def record_failure(
        net_name: str,
        reason: str,
        _blockers: list[str],
        region: tuple[float, float] | None,
        rule_id: str | None = None,
    ) -> None:
        """Record a failure with all accumulated data.

        ``rule_id`` is U1's decline-reason attribution (see
        ``RoutingFailureReport``'s docstring; ``attribution_gap`` is derived
        from it, never passed separately). ``domain`` is always derived
        from ``net_classification``'s canonical name-pattern helpers --
        never a new ad hoc classifier -- independent of whether a rule was
        attributed.
        """
        channel_path = channel_mapping.channel_paths.get(net_name)
        pin_count = len(channel_path.waypoints) if channel_path else 0

        all_blockers = list(blocker_history.get(net_name, set()))

        failure_reports[net_name] = RoutingFailureReport(
            net_name=net_name,
            failure_reason=reason,
            blocking_nets=all_blockers,
            attempted_ripups=ripup_counts.get(net_name, 0),
            congestion_region=region,
            pin_count=pin_count,
            rule_id=rule_id,
            domain=classify_net_type(net_name),
        )

    per_path_latency_ms: dict[str, float] = {}

    def _add_latency(net_name: str, elapsed: float) -> None:
        per_path_latency_ms[net_name] = per_path_latency_ms.get(net_name, 0.0) + elapsed

    def _attempt_route_fail_closed(
        net_name: str,
    ) -> tuple[bool, str, list[str], tuple[float, float] | None, str | None]:
        """Call ``attempt_route``, declining fail-closed on an unhandled exception.

        R4/candor: a net whose discharge attempt raised is never silently
        dropped or treated as proven-safe -- it is declined with
        ``failure_reason="prover_error"``. This is not a specific safety
        rule (we don't know whether clearance/creepage would have held),
        so ``rule_id`` stays ``None`` (``attribution_gap`` derives to
        ``True``) rather than inventing one.
        """
        try:
            return attempt_route(net_name)
        except Exception:
            logger.exception(
                "Unhandled exception routing net %r; declining fail-closed "
                "rather than treating it as proven-safe.",
                net_name,
            )
            return False, FAILURE_REASON_PROVER_ERROR, [], None, None

    for net_name in routable_nets:
        t0 = time.perf_counter()
        success, reason, blockers, region, rule_id = _attempt_route_fail_closed(net_name)
        _add_latency(net_name, (time.perf_counter() - t0) * 1000.0)
        if not success:
            failed_nets_set.add(net_name)
            record_failure(net_name, reason, blockers, region, rule_id=rule_id)

    max_reroute_attempts = len(routable_nets) * _MAX_REROUTE_ATTEMPTS_PER_NET
    attempts = 0

    while reroute_queue and attempts < max_reroute_attempts:
        net_name = reroute_queue.popleft()
        attempts += 1
        t0 = time.perf_counter()
        success, reason, blockers, region, rule_id = _attempt_route_fail_closed(net_name)
        _add_latency(net_name, (time.perf_counter() - t0) * 1000.0)
        if not success:
            failed_nets_set.add(net_name)
            record_failure(net_name, reason, blockers, region, rule_id=rule_id)

    for net_name in reroute_queue:
        failed_nets_set.add(net_name)
        # Rip-up budget exhaustion is a specific, known mechanism, but it is
        # a routing-algorithm resource limit, not a safety rule the system
        # failed to discharge -- report the honest gap (rule_id=None,
        # so attribution_gap derives to True) rather than naming a "rule"
        # that doesn't exist.
        record_failure(net_name, "rip_up_limit", [], None)

    log_los_bb_stats()

    return PathfindingResult(
        routed_paths=routed_paths,
        failed_nets=list(dict.fromkeys(failed_nets_set)),
        failure_reports=failure_reports,
        net_ids=net_ids,
        per_path_latency_ms=per_path_latency_ms,
        coarse_to_fine_fallbacks=fallback_count,
        tree_failures=tree_failures,
        partial_paths=partial_paths,
        tree_routes=tree_routes,
        partial_tree_routes=partial_tree_routes,
    )
