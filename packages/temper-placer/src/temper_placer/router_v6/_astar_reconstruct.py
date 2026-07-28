# mypy: ignore-errors
# ruff: noqa: ARG001, F821  # enable_numba_los from incomplete numba merge
"""
Router V6: Route construction from A* search results.

Builds geometric paths by stitching A* segment results across waypoints,
with support for multilayer routing, rip-up-and-reroute, coarse-to-fine
corridor search, and 3D via-aware fallback.

Part of temper-N6 decomposition -- split from astar_pathfinding.py.
"""

from __future__ import annotations

import logging
import math
import time
from collections import deque

logger = logging.getLogger(__name__)

from temper_placer.router_v6._astar_ordering import _compute_net_order

# Result/report types live in _astar_results (temper-N8-split extraction) and
# are re-exported here so every existing `from ..._astar_reconstruct import
# PathfindingResult` import keeps working.
from temper_placer.router_v6._astar_results import (
    PathfindingResult,
    RoutingFailureReport,
    TreeRoutingFailure,
)
from temper_placer.router_v6._astar_theta_star import (
    _astar_search_lazy_theta_star,
    _astar_search_theta_star,
    log_los_bb_stats,
    reset_los_bb_stats,
)
from temper_placer.router_v6.astar_core import (
    RoutePath,
    RoutePath3D,
    _astar_search,
    _route_segment_3d,
    append_exact_terminal_point,
    append_grid_path_point,
    grid_quantization_tolerance,
)
from temper_placer.router_v6.astar_grid import (
    _build_tht_pad_locations,
    _extract_pad_centers_per_net,
    _identify_blocking_nets,
    _mark_route_blocked,
    _restore_net_pads,
    _unblock_net_pads,
    _unmark_route_blocked,
)
from temper_placer.router_v6.channel_mapping import ChannelMapping
from temper_placer.router_v6.occupancy_grid import OccupancyGrid
from temper_placer.router_v6.stage0_data import DesignRules
from temper_placer.router_v6.tree_route_geometry import TreeRouteBranch, TreeRouteGeometry

# U2 (docs/plans/2026-07-18-003-*): explicit iteration bound for the
# third-tier ``_route_segment_3d`` fallback call in
# ``_astar_route_multilayer``. Passed explicitly (rather than relying
# solely on ``_route_segment_3d``'s own default) so the bound used at
# this specific call site is visible and independently tunable here.
# See astar_core.py's ``_ROUTE_SEGMENT_3D_DEFAULT_MAX_ITER`` docstring
# for the reasoning behind this order of magnitude.
_SEGMENT_3D_FALLBACK_MAX_ITER = 200_000
# Experimental all-terminal trees may invoke the 3D fallback once per edge.
# Keep that expensive retry bounded until production evidence justifies a
# larger search budget; two-pad routing deliberately retains the value above.
_TREE_SEGMENT_3D_FALLBACK_MAX_ITER = 10_000
_MAX_REROUTE_ATTEMPTS_PER_NET = 2

_SKIP_NET_PREFIXES = ("unconnected-", "NC-", "DNP-", "NC_", "TP_")


def _should_route(net_name: str) -> bool:
    """Return True if net should be routed by A* (signal nets only).

    Power, ground, and HV nets are handled by zone pours, not path routing.
    """
    from temper_placer.router_v6.net_classification import (
        is_ground_net,
        is_hv_net,
        is_power_net,
    )

    if is_power_net(net_name) or is_ground_net(net_name) or is_hv_net(net_name):
        return False
    return not any(net_name.startswith(p) for p in _SKIP_NET_PREFIXES)


def _allow_forced_segments(
    net_name: str,
    design_rules: DesignRules | None,
    tree_route_active: bool,
) -> bool:
    """Determine whether forced segments are permitted for a net.

    Always ``False``. Forced segments draw a raw, unchecked line between
    waypoints with zero clearance checking -- fabricating copper that may
    violate netclass clearance for the net it's drawn for. Nothing on this
    board is worth an honest "unrouted" less than a silently unsafe
    "routed": a net that can't find a real, clearance-respecting path is
    reported as failed (see ``attempt_route``'s forced-segment interception,
    ``_astar_reconstruct.py:409-448``), never fabricated.

    This gate was originally class-conditional (only HV/AC-class nets, per
    R6 of docs/plans/2026-07-23-008-feat-property-test-hardening-plan.md)
    until docs/plans/2026-07-24-001-fix-forced-segment-fail-closed-plan.md
    generalized it: congested power/ground nets were still fabricating
    clearance-violating copper through this same fallback, which is why
    ``shorting_items`` didn't improve after the netclass-clearance wiring
    fix landed. ``net_name``, ``design_rules``, and ``tree_route_active``
    are accepted for call-site stability but no longer change the outcome.
    """
    return False


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
    enable_numba_los: bool = False,
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

    if pcb:
        tht_locations = _build_tht_pad_locations(pcb)
        if tht_locations:
            print(f"  Found {len(tht_locations)} THT pads for layer switching")
        pad_centers_per_net = _extract_pad_centers_per_net(pcb)

    net_order = _compute_net_order(channel_mapping, bottleneck_widths=bottleneck_widths)
    routable_nets = [n for n in net_order if _should_route(n)]
    skipped_nets = [n for n in net_order if n not in set(routable_nets)]

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

    def attempt_route(net_name: str) -> tuple[bool, str, list[str], tuple[float, float] | None]:
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
                return True, "", [], None
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
            return False, summary_reason, [], (terminal.center.x, terminal.center.y)

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
                return False, "no_path", [], channel_path.waypoints[failed_index]

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
                return (
                    False,
                    "no_path",
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
            return True, "", [], None

        if blocker_names:
            print(
                f"      ✗ {net_name} FAILED: congestion (blockers: {', '.join(blocker_names[:3])})",
                flush=True,
            )
            return False, "congestion", blocker_names, congestion_region()
        else:
            print(f"      ✗ {net_name} FAILED: no path found", flush=True)
            return False, "no_path", [], congestion_region()

    def record_failure(
        net_name: str, reason: str, _blockers: list[str], region: tuple[float, float] | None
    ) -> None:
        """Record a failure with all accumulated data."""
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
        )

    per_path_latency_ms: dict[str, float] = {}

    def _add_latency(net_name: str, elapsed: float) -> None:
        per_path_latency_ms[net_name] = per_path_latency_ms.get(net_name, 0.0) + elapsed

    for net_name in routable_nets:
        t0 = time.perf_counter()
        success, reason, blockers, region = attempt_route(net_name)
        _add_latency(net_name, (time.perf_counter() - t0) * 1000.0)
        if not success:
            failed_nets_set.add(net_name)
            record_failure(net_name, reason, blockers, region)

    max_reroute_attempts = len(routable_nets) * _MAX_REROUTE_ATTEMPTS_PER_NET
    attempts = 0

    while reroute_queue and attempts < max_reroute_attempts:
        net_name = reroute_queue.popleft()
        attempts += 1
        t0 = time.perf_counter()
        success, reason, blockers, region = attempt_route(net_name)
        _add_latency(net_name, (time.perf_counter() - t0) * 1000.0)
        if not success:
            failed_nets_set.add(net_name)
            record_failure(net_name, reason, blockers, region)

    for net_name in reroute_queue:
        failed_nets_set.add(net_name)
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


def _has_safe_partial_geometry(path: RoutePath | RoutePath3D) -> bool:
    """A partial result must contain actual A* geometry, never a forced edge."""
    points = path.segments if isinstance(path, RoutePath3D) else path.coordinates
    return len(points) >= 2 and path.path_length > 0.0


def _in_bounds(grid: OccupancyGrid, point: tuple[int, int]) -> bool:
    return 0 <= point[0] < grid.width_cells and 0 <= point[1] < grid.height_cells


def _dispatch_search(
    grid,
    start,
    goal,
    use_theta_star: bool,
    use_lazy_theta_star: bool,
    congestion_tensor=None,
    max_iter: int = 1_000_000,
    enable_numba_los: bool = False,
    enable_congestion_derivative: bool = True,
    thermal_flat=None,
    thermal_weight: float = 0.0,
    net_id: int = -1,
):
    if use_lazy_theta_star:
        return _astar_search_lazy_theta_star(
            grid,
            start,
            goal,
            net_id=net_id,
            max_iter=max_iter,
            enable_numba_los=enable_numba_los,
            enable_congestion_derivative=enable_congestion_derivative,
        )
    if use_theta_star:
        return _astar_search_theta_star(
            grid,
            start,
            goal,
            net_id=net_id,
            max_iter=max_iter,
            enable_numba_los=enable_numba_los,
            enable_congestion_derivative=enable_congestion_derivative,
        )
    # 2D plain A*.  Delegate to the Numba-jitted kernel when available
    # and the grid is small enough that the overhead of building the
    # bit tensor (once per call) is amortized.  Falls through to the
    # pure-Python _astar_search otherwise.
    if net_id >= 0:
        # The Numba kernel consumes a binary validity tensor and cannot
        # distinguish committed copper belonging to this net.  Tree edges use
        # the reference search so same-net attachment remains legal.
        return _astar_search(start, goal, grid, net_id=net_id)

    from temper_placer.router_v6.astar_core_numba import (
        _astar_search_numba,
    )

    # U7 / R11: thread the optional congestion tensor through.  The
    # Numba kernel reads it as a flat float32 array per expansion.
    kwargs = {"max_iterations": max_iter}
    if thermal_flat is not None:
        kwargs["thermal_flat"] = thermal_flat
        kwargs["thermal_weight"] = thermal_weight
    if congestion_tensor is not None:
        kwargs["congestion_flat"] = congestion_tensor.array.reshape(-1)
        kwargs["congestion_weight"] = congestion_tensor.weight
        kwargs["max_congestion_cost"] = congestion_tensor.max_cost
    return _astar_search_numba(start, goal, grid, **kwargs)


def _segment_search(
    grid: OccupancyGrid,
    start_world: tuple[float, float],
    goal_world: tuple[float, float],
    use_theta_star: bool,
    use_lazy_theta_star: bool,
    congestion_tensor=None,
    max_iter: int = 1_000_000,
    enable_numba_los: bool = False,
    enable_coarse_to_fine: bool = False,
    coarse_factor: int = 4,
    corridor_buffer_cells: int = 12,
    enable_congestion_derivative: bool = True,
    thermal_flat=None,
    thermal_weight: float = 0.0,
    net_id: int = -1,
) -> tuple[list | None, OccupancyGrid, int]:
    """Run A* between two world-coordinate waypoints on ``grid``.

    Returns ``(path, grid, fallback_count)`` where ``path`` is a list
    of grid cells or ``None``, ``grid`` is the grid searched, and
    ``fallback_count`` is 1 if coarse-to-fine fell back to unrestricted
    A* (0 otherwise).
    """
    start = grid.world_to_grid(*start_world)
    goal = grid.world_to_grid(*goal_world)
    if not _in_bounds(grid, start) or not _in_bounds(grid, goal):
        return None, grid, 0

    if enable_coarse_to_fine and net_id < 0:
        return _segment_search_coarse_to_fine(
            grid,
            start,
            goal,
            use_theta_star,
            use_lazy_theta_star,
            coarse_factor=coarse_factor,
            corridor_buffer_cells=corridor_buffer_cells,
            congestion_tensor=congestion_tensor,
            max_iter=max_iter,
            enable_congestion_derivative=enable_congestion_derivative,
            thermal_flat=thermal_flat,
            thermal_weight=thermal_weight,
        )

    path = _dispatch_search(
        grid,
        start,
        goal,
        use_theta_star,
        use_lazy_theta_star,
        congestion_tensor=congestion_tensor,
        max_iter=max_iter,
        enable_numba_los=enable_numba_los,
        enable_congestion_derivative=enable_congestion_derivative,
        thermal_flat=thermal_flat,
        thermal_weight=thermal_weight,
        net_id=net_id,
    )
    return path, grid, 0


def _segment_search_coarse_to_fine(
    grid: OccupancyGrid,
    start: tuple[int, int],
    goal: tuple[int, int],
    use_theta_star: bool,
    use_lazy_theta_star: bool,
    coarse_factor: int = 4,
    corridor_buffer_cells: int = 12,
    congestion_tensor=None,
    max_iter: int = 1_000_000,
    enable_numba_los: bool = False,
    enable_congestion_derivative: bool = True,
    thermal_flat=None,
    thermal_weight: float = 0.0,
) -> tuple[list | None, OccupancyGrid, int]:
    """Coarse-to-fine corridor routing.

    1. Downsample grid to coarse resolution.
    2. Run plain A* on coarse grid.
    3. Extract corridor mask from coarse path.
    4. Run constrained fine A* within corridor.
    5. Fall back to unrestricted A* on any failure.
    """
    from temper_placer.router_v6.astar_core_numba import _astar_search_numba
    from temper_placer.router_v6.corridor import extract_corridor_mask
    from temper_placer.router_v6.neighbor_validity import (
        build_neighbor_validity_tensor_2d,
    )

    coarse_grid = grid.downsample(factor=coarse_factor)

    coarse_start = (start[0] // coarse_factor, start[1] // coarse_factor)
    coarse_goal = (goal[0] // coarse_factor, goal[1] // coarse_factor)

    coarse_path = _astar_search_numba(coarse_start, coarse_goal, coarse_grid)

    if coarse_path is not None:
        corridor_mask = extract_corridor_mask(
            coarse_path,
            coarse_factor=coarse_factor,
            buffer_cells=corridor_buffer_cells,
            fine_rows=grid.height_cells,
            fine_cols=grid.width_cells,
        )
        if corridor_mask[start[1], start[0]] and corridor_mask[goal[1], goal[0]]:
            neighbor_tensor = build_neighbor_validity_tensor_2d(grid, corridor_mask=corridor_mask)
            fine_path = _astar_search_numba(
                start,
                goal,
                grid,
                neighbor_tensor=neighbor_tensor,
                max_iterations=max_iter,
            )
            if fine_path is not None:
                return fine_path, grid, 0

    path = _dispatch_search(
        grid,
        start,
        goal,
        use_theta_star,
        use_lazy_theta_star,
        congestion_tensor=congestion_tensor,
        max_iter=max_iter,
        enable_numba_los=enable_numba_los,
        enable_congestion_derivative=enable_congestion_derivative,
        thermal_flat=thermal_flat,
        thermal_weight=thermal_weight,
    )
    return path, grid, 1


def _astar_route(
    net_name: str,
    channel_path,
    grid: OccupancyGrid,
    use_theta_star: bool = False,
    use_lazy_theta_star: bool = False,
    max_iter: int = 1_000_000,
    enable_numba_los: bool = False,
    enable_coarse_to_fine: bool = False,
    coarse_factor: int = 4,
    corridor_buffer_cells: int = 12,
    thermal_flat=None,
    thermal_weight: float = 0.0,
    allow_forced_segments: bool = True,
    net_id: int = -1,
) -> tuple[RoutePath | None, int]:
    """
    Route a single net using A* or Theta* pathfinding.

    Returns:
        (RoutePath or None, coarse_to_fine_fallback_count)
    """
    waypoints = channel_path.waypoints
    if len(waypoints) < 2:
        return None, 0

    detailed_coords: list[tuple[float, float]] = []
    forced_segments = 0
    failed_waypoint_indices: list[int] = []
    fallback_count = 0

    for i in range(len(waypoints) - 1):
        start_world = waypoints[i]
        goal_world = waypoints[i + 1]

        grid_path, _, fb = _segment_search(
            grid,
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
            net_id=net_id,
        )
        fallback_count += fb

        if grid_path:
            tolerance = grid_quantization_tolerance(grid.cell_size)
            if i == 0:
                detailed_coords.append(start_world)
            for grid_cell in grid_path:
                world_coord = grid.grid_to_world(grid_cell[0], grid_cell[1])
                append_grid_path_point(detailed_coords, world_coord, tolerance)
            # A multi-terminal fallback is a serial incremental tree; every
            # target must be an actual path node, not merely the next search
            # start coordinate. Snap onto the exact terminal rather than
            # duplicating it next to the last (approximate) grid-cell
            # center -- see astar_core.append_exact_terminal_point.
            append_exact_terminal_point(detailed_coords, goal_world, tolerance)
        else:
            if not allow_forced_segments:
                failed_waypoint_indices.append(i + 1)
                path_length = sum(
                    ((p2[0] - p1[0]) ** 2 + (p2[1] - p1[1]) ** 2) ** 0.5
                    for p1, p2 in zip(detailed_coords, detailed_coords[1:])
                )
                return RoutePath(
                    net_name=net_name,
                    coordinates=detailed_coords,
                    layer_name=grid.layer_name,
                    path_length=path_length,
                    forced_segment_count=1,
                    failed_waypoint_indices=failed_waypoint_indices,
                ), fallback_count
            if i == 0:
                detailed_coords.append(start_world)
            detailed_coords.append(goal_world)
            forced_segments += 1
            failed_waypoint_indices.append(i + 1)

    if not detailed_coords:
        detailed_coords = list(waypoints)
        forced_segments = len(waypoints) - 1

    path_length = sum(
        ((p2[0] - p1[0]) ** 2 + (p2[1] - p1[1]) ** 2) ** 0.5
        for p1, p2 in zip(detailed_coords, detailed_coords[1:])
    )

    return RoutePath(
        net_name=net_name,
        coordinates=detailed_coords,
        layer_name=grid.layer_name,
        path_length=path_length,
        forced_segment_count=forced_segments,
        failed_waypoint_indices=failed_waypoint_indices,
    ), fallback_count


def _astar_route_multilayer(
    net_name: str,
    channel_path,
    primary_grid: OccupancyGrid,
    alternate_grid: OccupancyGrid | None,
    tht_locations: set[tuple[float, float]] | None,
    use_theta_star: bool = False,
    use_lazy_theta_star: bool = False,
    congestion_tensor=None,
    max_iter: int = 1_000_000,
    enable_numba_los: bool = False,
    enable_coarse_to_fine: bool = False,
    coarse_factor: int = 4,
    corridor_buffer_cells: int = 12,
    enable_congestion_derivative: bool = True,
    thermal_flat=None,
    thermal_weight: float = 0.0,
    net_id: int = 0,
    design_rules: DesignRules | None = None,
    allow_forced_segments: bool = True,
    segment_3d_fallback_max_iter: int = _SEGMENT_3D_FALLBACK_MAX_ITER,
) -> tuple[RoutePath3D | None, int]:
    """
    Route a single net with per-segment layer switching at THT pads.

    For each waypoint pair:
    1. Try routing on primary grid
    2. If it fails AND waypoints are at THT pads, try alternate grid
    3. U2: if that also fails (or is unavailable), try ``_route_segment_3d``
       (the 3D via-aware A* search) as a last-resort fallback tier --
       see docs/plans/2026-07-18-003-feat-via-aware-layer-transitions-plan.md
    4. Stitch segments together

    Args:
        net_id: Real net id (>0) for the net being routed, used only by
            the U2 fallback tier below so any via it places is actually
            blocked against later nets via ``mark_via_blocked()``.
            Defaults to 0 (no via-blocking protection) for backward
            compatibility with any caller that doesn't have a net id
            available yet -- production callers should always pass a
            real net_id.
        design_rules: Per-netclass rules used only by the 3D fallback to
            reserve each candidate via at its resolved diameter and clearance.

    Returns:
        (RoutePath3D or None, coarse_to_fine_fallback_count)
    """
    waypoints = channel_path.waypoints
    if len(waypoints) < 2:
        return None, 0

    detailed_segments: list[tuple[float, float, str]] = []
    via_positions: list[tuple[float, float]] = []
    forced_segments = 0
    failed_waypoint_indices: list[int] = []
    fallback_count = 0

    for i in range(len(waypoints) - 1):
        start_world = waypoints[i]
        goal_world = waypoints[i + 1]

        segment_path, grid_to_use, fb = _segment_search(
            primary_grid,
            start_world,
            goal_world,
            use_theta_star,
            use_lazy_theta_star,
            congestion_tensor=congestion_tensor,
            max_iter=max_iter,
            enable_coarse_to_fine=enable_coarse_to_fine,
            coarse_factor=coarse_factor,
            corridor_buffer_cells=corridor_buffer_cells,
            enable_congestion_derivative=enable_congestion_derivative,
            thermal_flat=thermal_flat,
            thermal_weight=thermal_weight,
        )
        fallback_count += fb

        # The alternate-grid route is a genuine B.Cu detour, not an implicit
        # layer change.  Preserve the established route-search tier, while
        # spelling out F.Cu -> B.Cu at its start and B.Cu -> F.Cu at its end
        # so ``via_positions`` and the writer have a physically connected
        # path to emit.  The historical code returned only B.Cu points here,
        # relying on the presence of any THT pad elsewhere on the board.
        if not segment_path and alternate_grid and tht_locations:
            alt_start = alternate_grid.world_to_grid(*start_world)
            alt_goal = alternate_grid.world_to_grid(*goal_world)
            if _in_bounds(alternate_grid, alt_start) and _in_bounds(alternate_grid, alt_goal):
                alternate_path, _unused_grid, fb2 = _segment_search(
                    alternate_grid,
                    start_world,
                    goal_world,
                    use_theta_star,
                    use_lazy_theta_star,
                    congestion_tensor=congestion_tensor,
                    max_iter=max_iter,
                    enable_coarse_to_fine=enable_coarse_to_fine,
                    coarse_factor=coarse_factor,
                    corridor_buffer_cells=corridor_buffer_cells,
                    enable_congestion_derivative=enable_congestion_derivative,
                    thermal_flat=thermal_flat,
                    thermal_weight=thermal_weight,
                )
                fallback_count += fb2
                if alternate_path:
                    primary_layer = primary_grid.layer_name
                    alternate_layer = alternate_grid.layer_name
                    alt_tolerance = grid_quantization_tolerance(alternate_grid.cell_size)
                    if i == 0:
                        detailed_segments.append((start_world[0], start_world[1], primary_layer))
                    # Real via (layer change at identical x, y) -- never
                    # merged, append_grid_path_point/append_exact_terminal_point
                    # only merge same-layer points.
                    detailed_segments.append((start_world[0], start_world[1], alternate_layer))
                    for node in alternate_path:
                        if hasattr(node, "layer_name"):
                            wx, wy = alternate_grid.grid_to_world(node.x, node.y)
                            append_grid_path_point(
                                detailed_segments, (wx, wy, node.layer_name), alt_tolerance
                            )
                        else:
                            wx, wy = alternate_grid.grid_to_world(node[0], node[1])
                            append_grid_path_point(
                                detailed_segments, (wx, wy, alternate_layer), alt_tolerance
                            )
                    append_exact_terminal_point(
                        detailed_segments, (goal_world[0], goal_world[1], alternate_layer), alt_tolerance
                    )
                    detailed_segments.append((goal_world[0], goal_world[1], primary_layer))
                    via_positions.extend((start_world, goal_world))
                    continue

        if segment_path:
            layer_name = grid_to_use.layer_name
            tolerance = grid_quantization_tolerance(grid_to_use.cell_size)
            if i == 0:
                detailed_segments.append((start_world[0], start_world[1], layer_name))

            for node in segment_path:
                if hasattr(node, "layer_name"):
                    wx, wy = grid_to_use.grid_to_world(node.x, node.y)
                    append_grid_path_point(detailed_segments, (wx, wy, node.layer_name), tolerance)
                else:
                    wx, wy = grid_to_use.grid_to_world(node[0], node[1])
                    append_grid_path_point(detailed_segments, (wx, wy, layer_name), tolerance)

            # Preserve every terminal explicitly.  Without this, consecutive
            # grid paths can stop at adjacent cell centres and silently omit
            # an intermediate pad from the emitted copper chain. Snap onto
            # the exact terminal instead of duplicating it next to the
            # last (approximate) grid-cell center -- that duplication is
            # what generated a spurious acid-trap-shaped vertex at nearly
            # every waypoint; see astar_core.append_exact_terminal_point
            # and docs/evidence/2026-07-27-acid-trap-elimination.md.
            append_exact_terminal_point(detailed_segments, (goal_world[0], goal_world[1], layer_name), tolerance)
            continue

        # U2 (docs/plans/2026-07-18-003-*): via-aware fallback tier. Both
        # the primary-grid attempt and the explicitly anchored alternate-grid
        # retry above have failed, so use the existing property-tested 3D A*
        # implementation as a last resort.  It records and blocks each
        # actual via.
        # (``_route_segment_3d``) as a last resort before giving up and
        # forcing a direct (unrouted) segment. This is additive: it only
        # runs when ``segment_path`` is still falsy at this point, so
        # segments that already succeeded on the primary/alternate grid
        # never reach this branch (see
        # test_astar_route_multilayer_via_fallback.py's regression test).
        grids_3d: dict[str, OccupancyGrid] = {primary_grid.layer_name: primary_grid}
        if alternate_grid is not None:
            grids_3d[alternate_grid.layer_name] = alternate_grid

        # Both endpoints are nominally on the primary grid's layer --
        # matching the "Fallback: add direct segment" branch below and
        # the primary-grid search attempt above. The 3D search is free
        # to detour through any other layer in ``grids_3d`` internally
        # (and back) to escape local congestion; a real via is recorded
        # (and grid-blocked, given a real net_id) for every such detour.
        fallback_layer = primary_grid.layer_name
        net_rules = design_rules.get_rules_for_net(net_name) if design_rules else None
        result_3d = _route_segment_3d(
            start_world,
            goal_world,
            fallback_layer,
            fallback_layer,
            grids_3d,
            via_cost=10.0,
            via_diameter=net_rules.via_diameter_mm if net_rules else 0.6,
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
            path_length = sum(
                ((s2[0] - s1[0]) ** 2 + (s2[1] - s1[1]) ** 2) ** 0.5
                for s1, s2 in zip(detailed_segments, detailed_segments[1:])
            )
            return RoutePath3D(
                net_name=net_name,
                segments=detailed_segments,
                via_positions=via_positions,
                path_length=path_length,
                via_count=len(via_positions),
                forced_segment_count=1,
                failed_waypoint_indices=failed_waypoint_indices,
            ), fallback_count

        # Legacy two-pad compatibility fallback: add a direct segment.
        forced_segments += 1
        failed_waypoint_indices.append(i + 1)
        if i == 0:
            detailed_segments.append((start_world[0], start_world[1], primary_grid.layer_name))
        detailed_segments.append((goal_world[0], goal_world[1], primary_grid.layer_name))

    path_length = sum(
        ((s2[0] - s1[0]) ** 2 + (s2[1] - s1[1]) ** 2) ** 0.5
        for s1, s2 in zip(detailed_segments, detailed_segments[1:])
    )

    return RoutePath3D(
        net_name=net_name,
        segments=detailed_segments,
        via_positions=via_positions,
        path_length=path_length,
        via_count=len(via_positions),
        forced_segment_count=forced_segments,
        failed_waypoint_indices=failed_waypoint_indices,
    ), fallback_count


def _astar_route_with_ripup(
    net_name: str,
    channel_path,
    grid: OccupancyGrid,
    _design_rules: DesignRules,
    net_ids: dict[str, int],
    alternate_grid: OccupancyGrid | None = None,
    tht_locations: set[tuple[float, float]] | None = None,
    all_grids: dict[str, OccupancyGrid] | None = None,
    use_theta_star: bool = False,
    use_lazy_theta_star: bool = False,
    congestion_tensor=None,
    max_iter: int = 1_000_000,
    enable_numba_los: bool = False,
    enable_coarse_to_fine: bool = False,
    coarse_factor: int = 4,
    corridor_buffer_cells: int = 12,
    thermal_flat=None,
    thermal_weight: float = 0.0,
    allow_forced_segments: bool = True,
    segment_3d_fallback_max_iter: int = _SEGMENT_3D_FALLBACK_MAX_ITER,
) -> tuple[RoutePath | RoutePath3D | None, list[int], int]:
    """
    Route a net, potentially ripping up blocking nets.

    If alternate_grid and components are provided, uses multilayer routing
    with layer switching at any pad (THT preferred when available).

    Returns:
        (RoutePath, list_of_net_ids_to_rip, coarse_to_fine_fallback_count)
    """
    # Try multilayer routing if alternate grid available.  The
    # ``tht_locations`` gate is no longer required: layer switching at
    # SMD pads is enabled when an alternate grid exists.  When THT pads
    # are present they remain the preferred layer-switch site (handled
    # inside ``_astar_route_multilayer``).
    path: RoutePath | RoutePath3D | None
    fallback_count = 0
    if alternate_grid:
        # U2: real net_id, threaded through to the ``_route_segment_3d``
        # fallback tier so any via it places is actually blocked via
        # ``mark_via_blocked()`` (which requires net_id > 0). Falls back
        # to 0 (no protection) only if the net isn't in the id map, which
        # should not happen for any net reaching this call site.
        net_id = net_ids.get(net_name, 0)
        path, fb = _astar_route_multilayer(
            net_name,
            channel_path,
            grid,
            alternate_grid,
            tht_locations,
            use_theta_star,
            use_lazy_theta_star,
            congestion_tensor=congestion_tensor,
            max_iter=max_iter,
            enable_coarse_to_fine=enable_coarse_to_fine,
            coarse_factor=coarse_factor,
            corridor_buffer_cells=corridor_buffer_cells,
            thermal_flat=thermal_flat,
            thermal_weight=thermal_weight,
            net_id=net_id,
            design_rules=_design_rules,
            allow_forced_segments=allow_forced_segments,
            segment_3d_fallback_max_iter=segment_3d_fallback_max_iter,
        )
        fallback_count += fb
    else:
        path, fb = _astar_route(
            net_name,
            channel_path,
            grid,
            use_theta_star,
            use_lazy_theta_star,
            max_iter=max_iter,
            enable_coarse_to_fine=enable_coarse_to_fine,
            coarse_factor=coarse_factor,
            corridor_buffer_cells=corridor_buffer_cells,
            thermal_flat=thermal_flat,
            thermal_weight=thermal_weight,
            allow_forced_segments=allow_forced_segments,
        )
        fallback_count += fb

    if path and path.forced_segment_count == 0:
        return path, [], fallback_count

    # Identify blockers if forced
    if path and path.forced_segment_count > 0:
        # Check ALL grids for blockers if available, otherwise just current grid
        target_grids = list(all_grids.values()) if all_grids else [grid]
        blockers = _identify_blocking_nets(channel_path, target_grids)
        if blockers:
            return path, list(blockers), fallback_count

    return path, [], fallback_count
