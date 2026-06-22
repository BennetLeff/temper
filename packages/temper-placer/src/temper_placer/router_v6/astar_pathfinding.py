"""
Router V6 Stage 4.2: Run A* Pathfinding

Runs A* pathfinding to generate actual routing paths.
Part of temper-x2xd (Stage 4 - Geometric Realization)
"""

from __future__ import annotations

from dataclasses import dataclass

from temper_placer.router_v6.astar_core import (
    RoutePath,
    RoutePath3D,
    RouteNode3D,
    _astar_search,
    _astar_search_lazy_theta_star,
    _astar_search_theta_star,
)
from temper_placer.router_v6.astar_grid import (
    _build_tht_pad_locations,
    _extract_pad_centers_per_net,
    _find_access_node,
    _identify_blocking_nets,
    _is_at_tht_pad,
    _mark_route_blocked,
    _restore_net_pads,
    _unblock_net_pads,
    _unmark_route_blocked,
)
from temper_placer.router_v6.channel_mapping import ChannelMapping
from temper_placer.router_v6.occupancy_grid import OccupancyGrid
from temper_placer.router_v6.stage0_data import DesignRules
import numpy as np
import sys
import time


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
    plane_net_count: int = 0  # Nets excluded (planes, unconnected)
    failure_reports: dict[str, RoutingFailureReport] | None = None  # Detailed failures
    net_ids: dict[str, int] | None = None  # Map of net_name -> net_id used in grid
    per_path_latency_ms: dict[str, float] | None = None  # Per-net A* wall time (ms)

    @property
    def success_count(self) -> int:
        """Number of successfully routed nets."""
        return len(self.routed_paths)

    @property
    def failure_count(self) -> int:
        """Number of failed nets."""
        return len(self.failed_nets)

    @property
    def total_forced_segments(self) -> int:
        """Total number of forced segments across all routes."""
        return sum(path.forced_segment_count for path in self.routed_paths.values())

    def get_path(self, net_name: str) -> RoutePath | None:
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
    design_rules: DesignRules,
    alternate_grid: OccupancyGrid | None = None,
    components: list | None = None,
    pcb=None,  # For accessing pads
    escape_vias_map: dict[str, list[tuple[float, float, float]]] | None = None,
    use_theta_star: bool = False,
    max_nets: int | None = None,
    target_nets: list[str] | None = None,
    use_lazy_theta_star: bool = False,
) -> PathfindingResult:
    # Build grids dictionary for multi-layer blocking
    all_grids = {grid.layer_name: grid}
    if alternate_grid:
        all_grids[alternate_grid.layer_name] = alternate_grid
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
    routed_paths: dict[str, RoutePath] = {}
    failed_nets: list[str] = []
    failure_reports: dict[str, RoutingFailureReport] = {}
    skipped_nets: list[str] = []  # Nets not routed (PLANE/SKIP)

    # Track ripup statistics per net
    ripup_counts: dict[str, int] = {}
    blocker_history: dict[str, set[str]] = {}

    # Build THT pad locations once (for layer switching)
    tht_locations = set()
    pad_centers_per_net: dict[str, list[tuple[float, float, float, str]]] = {}

    if pcb:
        tht_locations = _build_tht_pad_locations(pcb)
        if tht_locations:
            print(f"  Found {len(tht_locations)} THT pads for layer switching")

        # Extract actual pad centers for connectivity
        pad_centers_per_net = _extract_pad_centers_per_net(pcb)

    # Net classification filter
    def should_route(net_name: str) -> bool:
        """Check if net should be trace-routed (not a plane or unconnected net)."""
        # Plane nets - use copper pours, not traces
        plane_nets = {
            "GND",
            "VCC",
            "VBUS",
            "PGND",
            "AGND",
            "CGND",
            "+3V3",
            "+5V",
            "+12V",
            "+15V",
            "V+",
            "V-",
            "PWR",
        }
        if net_name.upper() in {n.upper() for n in plane_nets}:
            return False
        # Unconnected/skip nets
        skip_prefixes = ("unconnected-", "NC-", "DNP-", "NC_", "TP_")
        if any(net_name.startswith(p) for p in skip_prefixes):
            return False
        return True

    # Generate unique Net IDs (starting from 1)
    net_ids = {name: i + 1 for i, name in enumerate(channel_mapping.channel_paths.keys())}
    # Reverse map for checking (Net ID -> Net Name)
    id_to_net = {v: k for k, v in net_ids.items()}

    # Sort nets by routing scheduling priority
    net_order = _compute_net_order(channel_mapping)

    # Filter to only routable nets
    routable_nets = [n for n in net_order if should_route(n)]

    if target_nets:
        print(f"  Profiling Mode: Routing only {len(target_nets)} specific nets")
        routable_nets = [n for n in routable_nets if n in target_nets]
    elif max_nets is not None:
        print(f"  Limiting to first {max_nets} nets for profiling...")
        routable_nets = routable_nets[:max_nets]

    skipped_nets = [n for n in net_order if not should_route(n)]

    # Nets that historically fail - give them more rip-up attempts
    problem_nets = {"/k02", "/k04", "/k25", "/k24", "/k15"}

    reroute_queue: list[str] = []

    def attempt_route(
        net_name: str, depth: int = 0
    ) -> tuple[bool, str, list[str], tuple[float, float] | None]:
        """
        Recursive function to route with rip-up.

        Returns:
            (success, failure_reason, blocking_nets, congestion_region)
        """
        # Adaptive depth limit: problem nets get more attempts
        max_depth = 60 if net_name in problem_nets else 30
        if depth > max_depth:
            return False, "rip_up_limit", [], None

        channel_path = channel_mapping.channel_paths[net_name]
        net_id = net_ids[net_name]

        # Determine primary and alternate grid based on net's preference
        primary_grid = all_grids.get(channel_path.preferred_layer, grid)
        # Alternate grid is the one NOT preferred
        alt_layer = next((l for l in all_grids.keys() if l != channel_path.preferred_layer), None)
        active_alternate = all_grids.get(alt_layer) if alt_layer else alternate_grid

        # Unblock pads for this net to allow A* to connect (Surgery is inflation-aware)
        base_inflation = (
            design_rules.default_trace_width_mm / 2.0
        ) + design_rules.default_clearance_mm
        restoration = _unblock_net_pads(
            net_name,
            pad_centers_per_net,
            all_grids,
            inflation_mm=base_inflation,
            escape_vias_map=escape_vias_map,
        )

        # Route with rip-up capability
        # Adaptive Routing (Experiment O1)
        # If Theta* is enabled, try A* first as it is much faster.
        # Only use Theta* if A* fails or produces a poor path.

        # Route with rip-up capability
        import sys
        import time

        if use_lazy_theta_star:
            mode = "Lazy Theta*"
        elif use_theta_star:
            mode = "Theta*"
        else:
            mode = "A*"
        print(f"    Routing {net_name} using {mode}...", flush=True)
        sys.stdout.flush()

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
            all_grids=all_grids,  # Pass all for blocker identification
            use_theta_star=use_theta_star,
            use_lazy_theta_star=use_lazy_theta_star,
        )

        # Restore grid state
        _restore_net_pads(restoration)

        # Get blocker names for diagnostics
        blocker_names = [id_to_net.get(rid, f"Unknown-{rid}") for rid in ripped_ids]

        # Track blockers
        if net_name not in blocker_history:
            blocker_history[net_name] = set()
        blocker_history[net_name].update(blocker_names)

        # Get approximate congestion region from waypoints
        congestion_region: tuple[float, float] | None = None
        if channel_path.waypoints:
            # Use middle waypoint as approximate stuck location
            mid_idx = len(channel_path.waypoints) // 2
            congestion_region = channel_path.waypoints[mid_idx]

        if route_path:
            print(f"      ✓ {net_name} routed successfully", flush=True)
            sys.stdout.flush()
            # Handle Ripped Nets
            for ripped_id in ripped_ids:
                if ripped_id in id_to_net:
                    ripped_name = id_to_net[ripped_id]
                    if ripped_name in routed_paths:
                        # Unmark the ripped path from grids (layer-aware)
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

                        # Track ripup count
                        ripup_counts[ripped_name] = ripup_counts.get(ripped_name, 0) + 1

            # Mark new path (layer-aware)
            routed_paths[net_name] = route_path
            _mark_route_blocked(
                route_path,
                all_grids,
                trace_width=design_rules.default_trace_width_mm,
                clearance=design_rules.default_clearance_mm,
                net_id=net_id,
            )

            # Check if it was a forced route (which means congestion)
            if route_path.forced_segment_count > 0:
                return True, "congestion_forced", blocker_names, congestion_region
            return True, "", [], None

        # Determine failure reason
        if blocker_names:
            print(
                f"      ✗ {net_name} FAILED: congestion (blockers: {', '.join(blocker_names[:3])})",
                flush=True,
            )
            sys.stdout.flush()
            return False, "congestion", blocker_names, congestion_region
        else:
            print(f"      ✗ {net_name} FAILED: no path found", flush=True)
            sys.stdout.flush()
            return False, "no_path", [], congestion_region

    def record_failure(
        net_name: str, reason: str, blockers: list[str], region: tuple[float, float] | None
    ) -> None:
        """Record a failure with all accumulated data."""
        channel_path = channel_mapping.channel_paths.get(net_name)
        pin_count = len(channel_path.waypoints) if channel_path else 0

        # Merge with previously recorded blockers
        all_blockers = list(blocker_history.get(net_name, set()))

        failure_reports[net_name] = RoutingFailureReport(
            net_name=net_name,
            failure_reason=reason,
            blocking_nets=all_blockers,
            attempted_ripups=ripup_counts.get(net_name, 0),
            congestion_region=region,
            pin_count=pin_count,
        )

    # Per-path latency tracking (U4: benchmark extension)
    per_path_latency_ms: dict[str, float] = {}

    # Per-path latency tracking (U4: benchmark extension)
    per_path_latency_ms: dict[str, float] = {}

    # First pass: Route all routable nets (skip PLANE/unconnected)
    first_pass_success = 0
    first_pass_fail = 0
    for i, net_name in enumerate(routable_nets):
        if net_name not in channel_mapping.channel_paths:
            continue
        t0 = time.perf_counter()
        t0 = time.perf_counter()
        success, reason, blockers, region = attempt_route(net_name)
        per_path_latency_ms[net_name] = (time.perf_counter() - t0) * 1000.0
        per_path_latency_ms[net_name] = (time.perf_counter() - t0) * 1000.0
        if not success:
            first_pass_fail += 1
            failed_nets.append(net_name)
            record_failure(net_name, reason, blockers, region)
        else:
            first_pass_success += 1

    print(f"  First pass: {first_pass_success} routed, {first_pass_fail} failed,"
          f" {len(reroute_queue)} queued for rip-up")
    # Second pass: Reroute queue (iteratively)
    max_reroute_attempts = len(routable_nets) * 5
    attempts = 0

    reroute_success = 0
    reroute_fail = 0
    while reroute_queue and attempts < max_reroute_attempts:
        net_name = reroute_queue.pop(0)
        attempts += 1
        t0 = time.perf_counter()
        t0 = time.perf_counter()
        success, reason, blockers, region = attempt_route(net_name, depth=1)
        per_path_latency_ms[net_name] = (time.perf_counter() - t0) * 1000.0
        per_path_latency_ms[net_name] = (time.perf_counter() - t0) * 1000.0
        if not success:
            reroute_fail += 1
            failed_nets.append(net_name)
            record_failure(net_name, reason, blockers, region)
        else:
            reroute_success += 1

    print(f"  Reroute pass: {reroute_success} recovered, {reroute_fail} still failed")
    # Final cleanup: Record any nets left in queue as failures
    for net_name in reroute_queue:
        failed_nets.append(net_name)
        record_failure(net_name, "rip_up_limit", [], None)

    return PathfindingResult(
        routed_paths=routed_paths,
        failed_nets=list(set(failed_nets)),
        failure_reports=failure_reports,
        net_ids=net_ids,
        per_path_latency_ms=per_path_latency_ms,
    )


def _astar_route_with_ripup(
    net_name: str,
    channel_path,
    grid: OccupancyGrid,
    routed_paths: dict[str, RoutePath],
    design_rules: DesignRules,
    net_ids: dict[str, int],
    alternate_grid: OccupancyGrid | None = None,
    tht_locations: set[tuple[float, float]] | None = None,
    pad_centers: dict[str, list[tuple[float, float, float, str]]] | None = None,
    all_grids: dict[str, OccupancyGrid] | None = None,
    use_theta_star: bool = False,
    use_lazy_theta_star: bool = False,
) -> tuple[RoutePath | RoutePath3D | None, list[int]]:
    """
    Route a net, potentially ripping up blocking nets.

    If alternate_grid and components are provided, uses multilayer routing
    with THT pad layer switching.

    Returns:
        (RoutePath, list_of_net_ids_to_rip)
    """
    # Try multilayer routing if alternate grid available
    if alternate_grid:
        path = _astar_route_multilayer(
            net_name,
            channel_path,
            grid,
            alternate_grid,
            tht_locations,
            use_theta_star,
            use_lazy_theta_star,
        )
    else:
        path = _astar_route(net_name, channel_path, grid, use_theta_star, use_lazy_theta_star)

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
    """
    nets = list(channel_mapping.channel_paths.keys())

    # Nets that historically fail - give them priority
    problem_nets = {"/k02", "/k04", "/k25", "/k24", "/k15"}

    def priority_key(net_name: str):
        path = channel_mapping.channel_paths[net_name]

        # Priority 1: Power nets go FIRST (they need main channels)
        name_upper = net_name.upper()
        is_power = any(x in name_upper for x in ["GND", "VCC", "HV", "AC_", "+", "VBUS"])

        # Priority 2: Problem nets route early (before congestion)
        is_problem = net_name in problem_nets

        # Priority 3: Shortest path length (easier to fit around)
        length = path.total_length

        # Tuple sorts: (False, False, small_length) comes first
        return (not is_power, not is_problem, length)

    return sorted(nets, key=priority_key)


def _astar_route_multilayer(
    net_name: str,
    channel_path,
    primary_grid: OccupancyGrid,
    alternate_grid: OccupancyGrid | None,
    tht_locations: set[tuple[float, float]] | None,
    use_theta_star: bool = False,
    use_lazy_theta_star: bool = False,
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
    waypoints = channel_path.waypoints  # Use skeleton waypoints directly
    if not waypoints or len(waypoints) < 2:
        return None

    detailed_segments = []  # (x, y, layer)
    via_positions = []
    forced_segments = 0

    for i in range(len(waypoints) - 1):
        start_world = waypoints[i]
        goal_world = waypoints[i + 1]

        # Try primary grid first
        grid_to_use = primary_grid
        segment_path = None

        # Convert to grid coordinates
        # Use intelligent access node finding to avoid starting/ending in obstacles
        # Pass dummy net_id=-1 since we haven't routed yet (cells should be 0)
        start_grid = _find_access_node(grid_to_use, start_world, -1)
        if not start_grid:
            start_grid = grid_to_use.world_to_grid(start_world[0], start_world[1])

        goal_grid = _find_access_node(grid_to_use, goal_world, -1)
        if not goal_grid:
            goal_grid = grid_to_use.world_to_grid(goal_world[0], goal_world[1])

        # Check bounds
        start_valid = (
            0 <= start_grid[0] < grid_to_use.width_cells
            and 0 <= start_grid[1] < grid_to_use.height_cells
        )
        goal_valid = (
            0 <= goal_grid[0] < grid_to_use.width_cells
            and 0 <= goal_grid[1] < grid_to_use.height_cells
        )

        if start_valid and goal_valid:
            if use_lazy_theta_star:
                segment_path = _astar_search_lazy_theta_star(
                    grid_to_use, start_grid, goal_grid, net_id=-1
                )
            elif use_theta_star:
                segment_path = _astar_search_theta_star(
                    grid_to_use, start_grid, goal_grid, net_id=-1
                )
            else:
                segment_path = _astar_search(start_grid, goal_grid, grid_to_use)

        # If primary failed and alternate available, try alternate layer
        # Allow layer switching when THT pads exist on the board - the router
        # assumes layer transitions happen at nearby THT pads (implicit vias)
        if not segment_path and alternate_grid:
            # Try alternate layer (THT pads enable layer transitions)
            grid_to_use = alternate_grid
            start_grid = grid_to_use.world_to_grid(start_world[0], start_world[1])
            goal_grid = grid_to_use.world_to_grid(goal_world[0], goal_world[1])

            start_valid = (
                0 <= start_grid[0] < grid_to_use.width_cells
                and 0 <= start_grid[1] < grid_to_use.height_cells
            )
            goal_valid = (
                0 <= goal_grid[0] < grid_to_use.width_cells
                and 0 <= goal_grid[1] < grid_to_use.height_cells
            )

            if start_valid and goal_valid:
                if use_lazy_theta_star:
                    segment_path = _astar_search_lazy_theta_star(
                        grid_to_use, start_grid, goal_grid, net_id=-1
                    )
                elif use_theta_star:
                    segment_path = _astar_search_theta_star(
                        grid_to_use, start_grid, goal_grid, net_id=-1
                    )
                else:
                    segment_path = _astar_search(start_grid, goal_grid, grid_to_use)

        # Add segment to path
        if segment_path:
            # Found path!
            layer_name = grid_to_use.layer_name

            # Stitch: Add start_world if first segment
            if i == 0:
                detailed_segments.append((start_world[0], start_world[1], layer_name))

            for node in segment_path:
                # Node is RouteNode3D(x, y, z, layer_name) or tuple(x, y)
                # We need world coords
                if hasattr(node, "layer_name"):  # 3D node
                    wx, wy = grid_to_use.grid_to_world(node.x, node.y)
                    detailed_segments.append((wx, wy, node.layer_name))
                else:  # 2D tuple (x, y) from normal A*
                    wx, wy = grid_to_use.grid_to_world(node[0], node[1])
                    detailed_segments.append((wx, wy, layer_name))

            # Stitch: Add goal_world if last segment
            if i == len(waypoints) - 2:
                detailed_segments.append((goal_world[0], goal_world[1], layer_name))

            continue

        # If we get here, segment failed
        forced_segments += 1
        # Fallback: add direct segment
        if i == 0:
            detailed_segments.append((start_world[0], start_world[1], grid_to_use.layer_name))
        detailed_segments.append((goal_world[0], goal_world[1], grid_to_use.layer_name))

    # Calculate path length
    path_length = 0.0
    for i in range(len(detailed_segments) - 1):
        x1, y1, _ = detailed_segments[i]
        x2, y2, _ = detailed_segments[i + 1]
        path_length += ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5

    return RoutePath3D(
        net_name=net_name,
        segments=detailed_segments,
        via_positions=via_positions,
        path_length=path_length,
        via_count=len(via_positions),
        forced_segment_count=forced_segments,
    )


def _astar_route(
    net_name: str,
    channel_path,
    grid: OccupancyGrid,
    use_theta_star: bool = False,
    use_lazy_theta_star: bool = False,
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
    # Get waypoints from channel path
    waypoints = channel_path.waypoints

    if not waypoints or len(waypoints) < 2:
        # Need at least 2 waypoints (start and end)
        return None

    # Refine waypoints into detailed path using A*
    detailed_coords = []
    forced_segments = 0

    for i in range(len(waypoints) - 1):
        start_world = waypoints[i]
        goal_world = waypoints[i + 1]

        # Convert world coordinates to grid coordinates
        # Use intelligent access node finding
        start_grid = _find_access_node(grid, start_world, -1)
        if not start_grid:
            start_grid = grid.world_to_grid(start_world[0], start_world[1])

        goal_grid = _find_access_node(grid, goal_world, -1)
        if not goal_grid:
            goal_grid = grid.world_to_grid(goal_world[0], goal_world[1])

        # Check if coordinates are within grid bounds
        start_valid = (
            0 <= start_grid[0] < grid.width_cells and 0 <= start_grid[1] < grid.height_cells
        )
        goal_valid = 0 <= goal_grid[0] < grid.width_cells and 0 <= goal_grid[1] < grid.height_cells

        grid_path = None
        if start_valid and goal_valid:
            # Run A* or Theta* search between waypoints
            if use_lazy_theta_star:
                grid_path = _astar_search_lazy_theta_star(grid, start_grid, goal_grid, net_id=-1)
            elif use_theta_star:
                grid_path = _astar_search_theta_star(grid, start_grid, goal_grid, net_id=-1)
            else:
                grid_path = _astar_search(start_grid, goal_grid, grid)

        if grid_path:
            # Add start point exactly for the first segment (to touch pad center)
            if i == 0:
                detailed_coords.append(start_world)

            # Convert grid path back to world coordinates
            for grid_cell in grid_path:
                world_coord = grid.grid_to_world(grid_cell[0], grid_cell[1])
                # Avoid duplicate coordinates
                if not detailed_coords or detailed_coords[-1] != world_coord:
                    detailed_coords.append(world_coord)

            # Add goal point exactly for the last segment
            if i == len(waypoints) - 2:
                detailed_coords.append(goal_world)
        else:
            # A* failed, fall back to direct line
            if i == 0:
                detailed_coords.append(start_world)
            detailed_coords.append(goal_world)
            forced_segments += 1

    # Ensure we have at least start and end
    if not detailed_coords:
        detailed_coords = waypoints
        forced_segments = len(waypoints) - 1

    # Calculate total path length
    path_length = 0.0
    for i in range(len(detailed_coords) - 1):
        x1, y1 = detailed_coords[i]
        x2, y2 = detailed_coords[i + 1]
        dx = x2 - x1
        dy = y2 - y1
        path_length += (dx**2 + dy**2) ** 0.5

    return RoutePath(
        net_name=net_name,
        coordinates=detailed_coords,
        layer_name=grid.layer_name,
        segment_count=len(detailed_coords) - 1,
        path_length=path_length,
        forced_segment_count=forced_segments,
    )

    return RoutePath(
        net_name=net_name,
        coordinates=detailed_coords,
        layer_name=grid.layer_name,
        path_length=path_length,
        forced_segment_count=forced_segments,
    )
