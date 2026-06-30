"""
Router V6 Stage 4.2: Run A* Pathfinding

Runs A* pathfinding to generate actual routing paths.
Part of temper-x2xd (Stage 4 - Geometric Realization)
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass

from temper_placer.router_v6.astar_core import (
    RoutePath,
    RoutePath3D,
    _astar_search_lazy_theta_star,
    _astar_search_theta_star,
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
from temper_placer.router_v6.net_classification import (
    is_ground_net,
    is_hv_net,
    is_power_net,
)
from temper_placer.router_v6.occupancy_grid import OccupancyGrid
from temper_placer.router_v6.stage0_data import DesignRules

PROBLEM_NETS: frozenset[str] = frozenset({"/k02", "/k04", "/k25", "/k24", "/k15"})
_MAX_RIPUP_DEPTH_NORMAL = 15
_MAX_RIPUP_DEPTH_PROBLEM = 30
_MAX_REROUTE_ATTEMPTS_PER_NET = 5

_SKIP_NET_PREFIXES = ("unconnected-", "NC-", "DNP-", "NC_", "TP_")

@dataclass
class RoutingFailureReport:
    """Detailed failure report for a net that failed to route."""

    net_name: str
    failure_reason: str  # "congestion", "no_path", "rip_up_limit", "no_channel"
    blocking_nets: list[str]  # Which nets are blocking
    attempted_ripups: int
    congestion_region: tuple[float, float] | None  # Approximate (x, y) of stuck location
    pin_count: int = 0  # Number of pins in the net

@dataclass
class PathfindingResult:
    """Result of A* pathfinding."""

    routed_paths: dict[str, RoutePath | RoutePath3D]  # net_name -> RoutePath
    failed_nets: list[str]  # Nets that failed to route
    failure_reports: dict[str, RoutingFailureReport] | None = None  # Detailed failures
    net_ids: dict[str, int] | None = None  # Map of net_name -> net_id used in grid
    per_path_latency_ms: dict[str, float] | None = None  # Per-net routing latency

    @property
    def success_count(self) -> int:
        """Number of successfully routed nets."""
        return len(self.routed_paths)

    @property
    def failure_count(self) -> int:
        """Number of failed nets."""
        return len(self.failed_nets)

    @property
    def completion_rate(self) -> float:
        """success_count / (success_count + failure_count), or 0.0
        if both are 0.  Used by the ``ResultAggregate`` validator
        and by the closure runner's ``completion_pct`` metric.
        """
        total = self.success_count + self.failure_count
        if total == 0:
            return 0.0
        return self.success_count / total

    @property
    def total_forced_segments(self) -> int:
        """Total number of forced segments across all routes."""
        return sum(path.forced_segment_count for path in self.routed_paths.values())

    def get_path(self, net_name: str) -> RoutePath | RoutePath3D | None:
        """Get routed path for a specific net."""
        return self.routed_paths.get(net_name)

    def print_failure_analysis(self) -> None:
        """Print a diagnostic summary of routing failures."""
        if not self.failure_reports:
            print("No detailed failure reports available.")
            return

        print(f"\n{'=' * 60}")
        print(f"ROUTING FAILURE ANALYSIS ({len(self.failed_nets)} failures)")
        print(f"{'=' * 60}")

        # Count by reason
        reasons: dict[str, int] = {}
        blocking_counts: dict[str, int] = {}

        for report in self.failure_reports.values():
            reasons[report.failure_reason] = reasons.get(report.failure_reason, 0) + 1
            for blocker in report.blocking_nets:
                blocking_counts[blocker] = blocking_counts.get(blocker, 0) + 1

        print("\n1. FAILURE REASONS:")
        for reason, count in sorted(reasons.items(), key=lambda x: -x[1]):
            print(f"   {reason}: {count} nets")

        print("\n2. TOP BLOCKING NETS (most frequently blocking others):")
        for net, count in sorted(blocking_counts.items(), key=lambda x: -x[1])[:10]:
            print(f"   {net}: blocked {count} other nets")

        print("\n3. INDIVIDUAL FAILURES:")
        for report in self.failure_reports.values():
            region = (
                f"({report.congestion_region[0]:.1f}, {report.congestion_region[1]:.1f})"
                if report.congestion_region
                else "N/A"
            )
            print(f"   {report.net_name} ({report.pin_count} pins): {report.failure_reason}")
            print(f"      Region: {region}, Ripups: {report.attempted_ripups}")
            if report.blocking_nets:
                print(f"      Blocked by: {', '.join(report.blocking_nets[:5])}")
        print()

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
) -> PathfindingResult:
    """
    Run A* or Theta* pathfinding to generate routing paths.

    Uses the channel mapping as guidance and the occupancy grid
    for obstacle avoidance to find actual geometric paths.

    Supports THT pad layer fallback: if routing fails on primary grid,
    attempts alternate grid at waypoints with THT pads.

    Args:
        channel_mapping: Channel paths from Stage 4.1
        grid: Primary occupancy grid from Stage 2.5
        design_rules: PCB design rules for width/clearance
        alternate_grid: Optional alternate layer grid for THT fallback
        components: Optional component list (deprecated, use pcb)
        pcb: ParsedPCB with pads for THT detection
        escape_vias_map: Map of net_name -> list of (x, y, diameter) for escape vias

    Returns:
        PathfindingResult with routed paths and failure reports
    """
    if design_rules is None:
        design_rules = DesignRules()
    all_grids: dict[str, OccupancyGrid] = {grid.layer_name: grid}
    if alternate_grid:
        all_grids[alternate_grid.layer_name] = alternate_grid

    routed_paths: dict[str, RoutePath | RoutePath3D] = {}
    failed_nets_set: set[str] = set()
    failure_reports: dict[str, RoutingFailureReport] = {}
    ripup_counts: dict[str, int] = {}
    blocker_history: dict[str, set[str]] = {}

    tht_locations: set = set()
    pad_centers_per_net: dict[str, list[tuple[float, float, float, str]]] = {}

    if pcb:
        tht_locations = _build_tht_pad_locations(pcb)
        if tht_locations:
            print(f"  Found {len(tht_locations)} THT pads for layer switching")
        pad_centers_per_net = _extract_pad_centers_per_net(pcb)

    net_order = _compute_net_order(channel_mapping)
    routable_nets = [n for n in net_order if _should_route(n)]

    if target_nets:
        target_set = set(target_nets)
        print(f"  Profiling Mode: Routing only {len(target_nets)} specific nets")
        routable_nets = [n for n in routable_nets if n in target_set]
    elif max_nets is not None:
        print(f"  Limiting to first {max_nets} nets for profiling...")
        routable_nets = routable_nets[:max_nets]

    # U7 / R11: build the PathFinder-style congestion tensor
    # when the caller passed one in.  Size matches the primary
    # grid; the Numba A* kernel reads it per expansion.
    if congestion_tensor is not None:
        from temper_placer.router_v6.congestion_tensor import (
            CongestionTensor,
        )
        if congestion_tensor.array.shape != (grid.height_cells, grid.width_cells):
            # Caller passed a different-size tensor; build a
            # fresh one matching the grid.
            congestion_tensor = CongestionTensor.zeros(
                grid.height_cells, grid.width_cells
            )

    net_ids = {name: i + 1 for i, name in enumerate(routable_nets)}
    id_to_net = {v: k for k, v in net_ids.items()}

    base_inflation = (
        design_rules.default_trace_width_mm / 2.0
    )

    reroute_queue: deque[str] = deque()

    def attempt_route(net_name: str) -> tuple[bool, str, list[str], tuple[float, float] | None]:
        channel_path = channel_mapping.channel_paths[net_name]
        net_id = net_ids[net_name]

        primary_grid = all_grids.get(channel_path.preferred_layer, grid)
        alt_layer = next((layer for layer in all_grids if layer != channel_path.preferred_layer), None)
        active_alternate = all_grids.get(alt_layer) if alt_layer else alternate_grid

        # Surgery is inflation-aware: unblock pads so A* can connect
        restoration = _unblock_net_pads(
            net_name,
            pad_centers_per_net,
            all_grids,
            inflation_mm=base_inflation,
            escape_vias_map=escape_vias_map,
        )

        # Pass dummy net_id=-1 since we haven't routed yet (cells should be 0)
        route_path, ripped_ids = _astar_route_with_ripup(
            net_name,
            channel_path,
            primary_grid,
            routed_paths,
            design_rules,
            net_ids,
            active_alternate,
            tht_locations,
            pad_centers_per_net,
            all_grids=all_grids,
            use_theta_star=use_theta_star,
            use_lazy_theta_star=use_lazy_theta_star,
            congestion_tensor=congestion_tensor,
            max_iter=max_iter,
        )

        _restore_net_pads(restoration)

        blocker_names = [id_to_net.get(rid, f"Unknown-{rid}") for rid in ripped_ids]
        blocker_history.setdefault(net_name, set()).update(blocker_names)

        def congestion_region() -> tuple[float, float] | None:
            if not channel_path.waypoints:
                return None
            return channel_path.waypoints[len(channel_path.waypoints) // 2]

        if route_path:
            # U7 / R11: bump the congestion tensor along the routed
            # path so the next net naturally detours around it.
            # Increments per cell along the path; the Numba kernel
            # reads this in the next A* call.
            if congestion_tensor is not None:
                if hasattr(route_path, "coordinates"):
                    congestion_tensor.increment_path(
                        route_path.coordinates, primary_grid
                    )
                elif hasattr(route_path, "segments"):
                    # RoutePath3D: flatten segments
                    coords = []
                    for seg in route_path.segments:
                        coords.append((seg[0], seg[1]))
                    congestion_tensor.increment_path(
                        coords, primary_grid
                    )
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

            if route_path.forced_segment_count > 0:
                return True, "congestion_forced", blocker_names, congestion_region()
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

    # First pass: Route all routable nets
    for net_name in routable_nets:
        t0 = time.perf_counter()
        success, reason, blockers, region = attempt_route(net_name)
        _add_latency(net_name, (time.perf_counter() - t0) * 1000.0)
        if not success:
            failed_nets_set.add(net_name)
            record_failure(net_name, reason, blockers, region)

    # Second pass: Reroute queue
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

    # Final cleanup: Record any nets left in queue as failures
    for net_name in reroute_queue:
        failed_nets_set.add(net_name)
        record_failure(net_name, "rip_up_limit", [], None)

    return PathfindingResult(
        routed_paths=routed_paths,
        failed_nets=list(dict.fromkeys(failed_nets_set)),
        failure_reports=failure_reports,
        net_ids=net_ids,
        per_path_latency_ms=per_path_latency_ms,
    )


def _should_route(net_name: str) -> bool:
    if is_power_net(net_name) or is_ground_net(net_name) or is_hv_net(net_name):
        return False
    return not any(net_name.startswith(p) for p in _SKIP_NET_PREFIXES)

def _astar_route_with_ripup(
    net_name: str,
    channel_path,
    grid: OccupancyGrid,
    _routed_paths: dict[str, RoutePath | RoutePath3D],
    _design_rules: DesignRules,
    _net_ids: dict[str, int],
    alternate_grid: OccupancyGrid | None = None,
    tht_locations: set[tuple[float, float]] | None = None,
    _pad_centers: dict[str, list[tuple[float, float, float, str]]] | None = None,
    all_grids: dict[str, OccupancyGrid] | None = None,
    use_theta_star: bool = False,
    use_lazy_theta_star: bool = False,
    congestion_tensor=None,
    max_iter: int = 1_000_000,
) -> tuple[RoutePath | RoutePath3D | None, list[int]]:
    """
    Route a net, potentially ripping up blocking nets.

    If alternate_grid and components are provided, uses multilayer routing
    with layer switching at any pad (THT preferred when available).

    Returns:
        (RoutePath, list_of_net_ids_to_rip)
    """
    # Try multilayer routing if alternate grid available.  The
    # ``tht_locations`` gate is no longer required: layer switching at
    # SMD pads is enabled when an alternate grid exists.  When THT pads
    # are present they remain the preferred layer-switch site (handled
    # inside ``_astar_route_multilayer``).
    path: RoutePath | RoutePath3D | None
    if alternate_grid:
        path = _astar_route_multilayer(
            net_name,
            channel_path,
            grid,
            alternate_grid,
            tht_locations,
            use_theta_star,
            use_lazy_theta_star,
            congestion_tensor=congestion_tensor,
            max_iter=max_iter,
        )
    else:
        path = _astar_route(net_name, channel_path, grid, use_theta_star, use_lazy_theta_star,
                            max_iter=max_iter)

    if path and path.forced_segment_count == 0:
        return path, []

    # Identify blockers if forced
    if path and path.forced_segment_count > 0:
        # Check ALL grids for blockers if available, otherwise just current grid
        target_grids = list(all_grids.values()) if all_grids else [grid]
        blockers = _identify_blocking_nets(channel_path, target_grids)
        if blockers:
            return path, list(blockers)

    return path, []

def _compute_net_order(channel_mapping: ChannelMapping) -> list[str]:
    """
    Compute routing order for nets.

    Priority (highest to lowest):
    1. Power/HV/Critical nets (establish main arteries)
    2. Historically problematic nets (route early before congestion)
    3. Shortest paths first (easier to fit)

    Note (Wave 5 / R12 attempt, reverted 2026-06-23): routing
    high-pin nets first within the signal class was tried and
    REGRESSED closure from 15/24 to 13/24 on temper.kicad_pcb.
    The 8-pin I_SENSE still hits the iter cap even with first
    claim, and routing it first blocks the 2-3 pin nets that
    were successfully routing under the shortest-first order.
    The shortest-first heuristic is empirically better on this
    board.  If a future board needs different ordering, expose
    this as a tunable rather than changing the default.
    """
    nets = list(channel_mapping.channel_paths)

    def priority_key(net_name: str):
        path = channel_mapping.channel_paths[net_name]
        name_upper = net_name.upper()
        is_power = any(x in name_upper for x in ["GND", "VCC", "HV", "AC_", "+", "VBUS"])
        is_problem = net_name in PROBLEM_NETS
        return (not is_power, not is_problem, path.total_length)

    return sorted(nets, key=priority_key)

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
) -> RoutePath3D | None:
    """
    Route a single net with per-segment layer switching at THT pads.

    For each waypoint pair:
    1. Try routing on primary grid
    2. If it fails AND waypoints are at THT pads, try alternate grid
    3. Stitch segments together

    Args:
        net_name: Net to route
        channel_path: Channel path guidance
        primary_grid: Primary layer grid (e.g., F.Cu)
        alternate_grid: Alternate layer grid (e.g., B.Cu)
        tht_locations: Set of THT pad positions for layer switching
        use_theta_star: Use Theta* any-angle routing instead of standard A*

    Returns:
        RoutePath3D with segments potentially on multiple layers
    """
    waypoints = channel_path.waypoints
    if len(waypoints) < 2:
        return None

    detailed_segments: list[tuple[float, float, str]] = []
    forced_segments = 0

    for i in range(len(waypoints) - 1):
        start_world = waypoints[i]
        goal_world = waypoints[i + 1]

        segment_path, grid_to_use = _segment_search(
            primary_grid, start_world, goal_world, use_theta_star,
            use_lazy_theta_star, congestion_tensor=congestion_tensor,
            max_iter=max_iter,
        )

        # Allow layer switching when THT pads exist on the board - the router
        # assumes layer transitions happen at nearby THT pads (implicit vias)
        if not segment_path and alternate_grid and tht_locations:
            alt_start = alternate_grid.world_to_grid(*start_world)
            alt_goal = alternate_grid.world_to_grid(*goal_world)
            if _in_bounds(alternate_grid, alt_start) and _in_bounds(alternate_grid, alt_goal):
                segment_path = _dispatch_search(
                    alternate_grid, alt_start, alt_goal, use_theta_star,
                    use_lazy_theta_star, congestion_tensor=congestion_tensor,
                    max_iter=max_iter,
                )
                if segment_path:
                    grid_to_use = alternate_grid

        if segment_path:
            layer_name = grid_to_use.layer_name
            if i == 0:
                detailed_segments.append((start_world[0], start_world[1], layer_name))

            for node in segment_path:
                if hasattr(node, "layer_name"):
                    wx, wy = grid_to_use.grid_to_world(node.x, node.y)
                    detailed_segments.append((wx, wy, node.layer_name))
                else:
                    wx, wy = grid_to_use.grid_to_world(node[0], node[1])
                    detailed_segments.append((wx, wy, layer_name))

            if i == len(waypoints) - 2:
                detailed_segments.append((goal_world[0], goal_world[1], layer_name))
            continue

        # Fallback: add direct segment
        forced_segments += 1
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
        via_positions=[],
        path_length=path_length,
        via_count=0,
        forced_segment_count=forced_segments,
    )


def _astar_route(
    net_name: str,
    channel_path,
    grid: OccupancyGrid,
    use_theta_star: bool = False,
    use_lazy_theta_star: bool = False,
    max_iter: int = 1_000_000,
) -> RoutePath | None:
    """
    Route a single net using A* or Theta* pathfinding.

    Args:
        net_name: Net to route
        channel_path: Channel path guidance
        grid: Occupancy grid
        use_theta_star: Use Theta* any-angle routing instead of standard A*

    Returns:
        RoutePath or None if routing fails
    """
    waypoints = channel_path.waypoints
    if len(waypoints) < 2:
        return None

    detailed_coords: list[tuple[float, float]] = []
    forced_segments = 0

    for i in range(len(waypoints) - 1):
        start_world = waypoints[i]
        goal_world = waypoints[i + 1]

        grid_path, _ = _segment_search(
            grid, start_world, goal_world, use_theta_star, use_lazy_theta_star,
            max_iter=max_iter,
        )

        if grid_path:
            if i == 0:
                detailed_coords.append(start_world)
            for grid_cell in grid_path:
                world_coord = grid.grid_to_world(grid_cell[0], grid_cell[1])
                if not detailed_coords or detailed_coords[-1] != world_coord:
                    detailed_coords.append(world_coord)
            if i == len(waypoints) - 2:
                detailed_coords.append(goal_world)
        else:
            if i == 0:
                detailed_coords.append(start_world)
            detailed_coords.append(goal_world)
            forced_segments += 1

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
    )
























def _dispatch_search(
    grid, start, goal,
    use_theta_star: bool, use_lazy_theta_star: bool,
    congestion_tensor=None,
    max_iter: int = 1_000_000,
):
    if use_lazy_theta_star:
        return _astar_search_lazy_theta_star(grid, start, goal, net_id=-1, max_iter=max_iter)
    if use_theta_star:
        return _astar_search_theta_star(grid, start, goal, net_id=-1, max_iter=max_iter)
    # 2D plain A*.  Delegate to the Numba-jitted kernel when available
    # and the grid is small enough that the overhead of building the
    # bit tensor (once per call) is amortized.  Falls through to the
    # pure-Python _astar_search otherwise.
    from temper_placer.router_v6.astar_core_numba import (
        _astar_search_numba,
    )
    # U7 / R11: thread the optional congestion tensor through.  The
    # Numba kernel reads it as a flat float32 array per expansion.
    if congestion_tensor is not None:
        return _astar_search_numba(
            start, goal, grid,
            max_iterations=max_iter,
            congestion_flat=congestion_tensor.array.reshape(-1),
            congestion_weight=congestion_tensor.weight,
            max_congestion_cost=congestion_tensor.max_cost,
        )
    return _astar_search_numba(start, goal, grid, max_iterations=max_iter)


def _segment_search(
    grid: OccupancyGrid,
    start_world: tuple[float, float],
    goal_world: tuple[float, float],
    use_theta_star: bool,
    use_lazy_theta_star: bool,
    congestion_tensor=None,
    max_iter: int = 1_000_000,
) -> tuple[list | None, OccupancyGrid]:
    """Run A* between two world-coordinate waypoints on ``grid``.

    Returns ``(path, grid)`` where ``path`` is a list of grid cells or
    ``None`` if no path was found (or start/goal are out of bounds), and
    ``grid`` is the grid that was searched.  The caller may retry on
    ``alternate_grid`` if ``path`` is ``None`` and an alternate grid is
    available.
    """
    start = grid.world_to_grid(*start_world)
    goal = grid.world_to_grid(*goal_world)
    if not _in_bounds(grid, start) or not _in_bounds(grid, goal):
        return None, grid
    path = _dispatch_search(
        grid, start, goal, use_theta_star, use_lazy_theta_star,
        congestion_tensor=congestion_tensor, max_iter=max_iter,
    )
    return path, grid


def _in_bounds(grid: OccupancyGrid, point: tuple[int, int]) -> bool:
    return 0 <= point[0] < grid.width_cells and 0 <= point[1] < grid.height_cells

