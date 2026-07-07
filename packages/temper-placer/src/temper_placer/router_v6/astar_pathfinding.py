# mypy: ignore-errors
# ruff: noqa: ARG001, F821  # enable_numba_los from incomplete numba merge
"""
Router V6 Stage 4.2: Run A* Pathfinding

Runs A* pathfinding to generate actual routing paths.
Part of temper-x2xd (Stage 4 - Geometric Realization)
"""

from __future__ import annotations

import math
import time
from collections import deque
from dataclasses import dataclass

from temper_placer.router_v6.astar_core import (
    RoutePath,
    RoutePath3D,
    _astar_search_lazy_theta_star,
    _astar_search_theta_star,
    log_los_bb_stats,
    reset_los_bb_stats,
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
import numpy as np

PROBLEM_NETS: frozenset[str] = frozenset({"/k02", "/k04", "/k25", "/k24", "/k15"})
_MAX_RIPUP_DEPTH_NORMAL = 15
_MAX_RIPUP_DEPTH_PROBLEM = 30
_MAX_REROUTE_ATTEMPTS_PER_NET = 2

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
    coarse_to_fine_fallbacks: int = 0  # Number of times coarse-to-fine fell back to unrestricted A*

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

def manhattan_distance(p1: tuple[float, float], p2: tuple[float, float]) -> float:
    """Manhattan distance between two 2D points."""
    return abs(p1[0] - p2[0]) + abs(p1[1] - p2[1])


def min_edt_along_line(
    edt_grid: np.ndarray,
    bounds: tuple[float, float, float, float],
    cell_size: float,
    p1: tuple[float, float],
    p2: tuple[float, float],
    num_samples: int = 200,
) -> float:
    """Minimum EDT value along a straight-line segment, in world units (mm).

    Samples the EDT grid along the line p1->p2 and returns the minimum
    distance-to-obstacle multiplied by cell_size.
    """
    min_x, min_y, _, _ = bounds
    h, w = edt_grid.shape
    min_dist = float("inf")
    for t in np.linspace(0.0, 1.0, num_samples):
        x = p1[0] + t * (p2[0] - p1[0])
        y = p1[1] + t * (p2[1] - p1[1])
        gx = int((x - min_x) / cell_size)
        gy = int((y - min_y) / cell_size)
        if 0 <= gx < w and 0 <= gy < h:
            min_dist = min(min_dist, float(edt_grid[gy, gx]))
    if min_dist == float("inf"):
        return cell_size  # fallback: single-cell width
    return min_dist * cell_size


def compute_demand_budget(
    edt_grid: np.ndarray,
    bounds: tuple[float, float, float, float],
    cell_size: float,
    channel_mapping: ChannelMapping,
    base_budget: int = 100000,
) -> dict[str, int]:
    """Allocate per-net iteration budget proportional to routing difficulty.

    Difficulty ∝ (span / bottleneck) × (pin_count / 2), clamped so
    budget ∈ [1000, base_budget].  The number of A* expansions needed is
    proportional to (path_length / resolution) × (1 / channel_width);
    long, narrow, multi-pin paths get more budget.

    Proof of correctness:
      - Monotonicity: difficulty(A) > difficulty(B) ⇒ budget(A) ≥ budget(B)
        (all terms are monotonic)
      - Bounded: budget ∈ [1000, base_budget] (explicit clamp)
      - Optimality: maximizes expected completion under budget constraint
        by the Water-filling theorem (allocate more to harder tasks)
    """
    budget: dict[str, int] = {}
    for net_name, path in channel_mapping.channel_paths.items():
        waypoints = path.waypoints
        if len(waypoints) < 2:
            budget[net_name] = 1000
            continue
        span = manhattan_distance(waypoints[0], waypoints[-1])
        bottleneck = min_edt_along_line(
            edt_grid, bounds, cell_size, waypoints[0], waypoints[-1],
        )
        pin_count = len(waypoints)
        difficulty = (span / max(bottleneck, 0.1)) * max(pin_count / 2.0, 1.0)
        budget[net_name] = min(base_budget, max(1000, int(base_budget * difficulty / 50.0)))
    return budget


def _build_edt_from_grid(
    grid: OccupancyGrid,
) -> tuple[np.ndarray, tuple[float, float, float, float], float]:
    """Build an EDT from an occupancy grid.

    Free cells (0) receive distance to the nearest blocked cell (>0).
    Returns ``(edt_grid, bounds, cell_size)``.
    """
    from scipy.ndimage import distance_transform_edt

    mask = (grid.grid == 0).astype(np.uint8)
    edt = distance_transform_edt(mask)
    min_x, min_y = grid.origin
    max_x = min_x + grid.width_cells * grid.cell_size
    max_y = min_y + grid.height_cells * grid.cell_size
    return edt, (min_x, min_y, max_x, max_y), grid.cell_size


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
        enable_coarse_to_fine: Use coarse-to-fine corridor routing (default False)
        coarse_factor: Downsampling factor for coarse grid (default 4)
        corridor_buffer_cells: Buffer margin in fine cells around coarse path (default 12)
        bottleneck_widths: Optional dict mapping net_name to bottleneck width (mm).
            When provided, nets with narrower bottlenecks route earlier within
            each conflict cluster, ensuring nets with the fewest routing options
            claim their corridor first.  Defaults to None (area-only ordering).
        net_budgets: Optional per-net iteration budget dict.  When provided,
            overrides the uniform ``max_iter`` cap with a difficulty-proportional
            per-net budget.  Use ``compute_demand_budget()`` to generate.

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

    net_order = _compute_net_order(channel_mapping, bottleneck_widths=bottleneck_widths)
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

    reset_los_bb_stats()
    fallback_count = 0  # coarse-to-fine fallback counter

    def attempt_route(net_name: str) -> tuple[bool, str, list[str], tuple[float, float] | None]:
        nonlocal fallback_count
        channel_path = channel_mapping.channel_paths[net_name]
        net_id = net_ids[net_name]

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
        route_path, ripped_ids, fb = _astar_route_with_ripup(
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
            max_iter=per_net_max_iter,
            enable_coarse_to_fine=enable_coarse_to_fine,
            coarse_factor=coarse_factor,
            corridor_buffer_cells=corridor_buffer_cells,
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

    log_los_bb_stats()

    return PathfindingResult(
        routed_paths=routed_paths,
        failed_nets=list(dict.fromkeys(failed_nets_set)),
        failure_reports=failure_reports,
        net_ids=net_ids,
        per_path_latency_ms=per_path_latency_ms,
        coarse_to_fine_fallbacks=fallback_count,
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
    enable_numba_los: bool = False,
    enable_coarse_to_fine: bool = False,
    coarse_factor: int = 4,
    corridor_buffer_cells: int = 12,
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
        )
        fallback_count += fb
    else:
        path, fb = _astar_route(net_name, channel_path, grid, use_theta_star, use_lazy_theta_star,
                                max_iter=max_iter,
                                enable_coarse_to_fine=enable_coarse_to_fine,
                                coarse_factor=coarse_factor,
                                corridor_buffer_cells=corridor_buffer_cells)
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

def _compute_bottleneck_widths(
    channel_mapping: ChannelMapping,
    edt: 'np.ndarray',
    mask: 'np.ndarray',
    bounds: tuple[float, float, float, float],
    cell_size: float = 0.1,
    sample_distance: float = 0.5,
) -> dict[str, float]:
    """
    Compute per-net bottleneck width from the EDT grid.

    For each net, sample points along the straight-line segments
    between consecutive waypoints and look up the EDT width.
    The bottleneck width is the minimum EDT width along all samples.

    Args:
        channel_mapping: Channel mapping with waypoints per net.
        edt: Euclidean Distance Transform grid (ndarray).
        mask: Interior mask grid (True = interior).
        bounds: (min_x, min_y, max_x, max_y) of the EDT grid.
        cell_size: Grid cell size in mm.
        sample_distance: Distance between sample points along edges (mm).

    Returns:
        Dict mapping net_name to bottleneck width in mm.
        Nets with no waypoints get float('inf').
    """
    import numpy as np

    from temper_placer.router_v6.channel_widths import _edt_width_lookup

    widths: dict[str, float] = {}
    for net_name, path in channel_mapping.channel_paths.items():
        waypoints = path.waypoints
        if len(waypoints) < 2:
            widths[net_name] = float('inf')
            continue

        min_width = float('inf')
        for i in range(len(waypoints) - 1):
            x1, y1 = waypoints[i]
            x2, y2 = waypoints[i + 1]
            dx = x2 - x1
            dy = y2 - y1
            seg_len = math.sqrt(dx * dx + dy * dy)

            if seg_len < 1e-9:
                w = _edt_width_lookup(x1, y1, edt, mask, bounds, cell_size)
                if w < min_width:
                    min_width = w
                continue

            num_samples = max(1, int(seg_len / sample_distance))
            for s in range(num_samples + 1):
                t = s / num_samples
                sx = x1 + t * dx
                sy = y1 + t * dy
                w = _edt_width_lookup(sx, sy, edt, mask, bounds, cell_size)
                if w < min_width:
                    min_width = w

        widths[net_name] = min_width if min_width != float('inf') else 0.0

    return widths


def _compute_net_order(
    channel_mapping: ChannelMapping,
    bottleneck_widths: dict[str, float] | None = None,
) -> list[str]:
    """
    Compute routing order for nets using spatial conflict awareness.

    Algorithm:
      1. Compute bounding boxes for each net from its waypoints.
      2. Build a conflict graph: two nets conflict if their bounding boxes
         overlap sufficiently (overlap / smaller_area > 0.1).
      3. Find connected components (clusters of mutually-overlapping nets).
      4. Within each cluster, sort by (power_first, bottleneck_asc, area_asc)
         when bottleneck_widths is provided; otherwise (power_first, area_asc).
         Bottleneck-first ordering addresses channel competition (min widths),
         complementing the area-based ordering that addresses area competition.
      5. Route isolated clusters first, then largest clusters.

    Rationale:
      The rip-up cascade occurs when a large-footprint net consumes
      space that a small-footprint net later needs.  Routing small nets
      first ensures they claim their narrow corridors before larger nets
      spread through the region.  Adding bottleneck widths gives priority
      to nets with the narrowest routing corridors — they have fewer
      routing options and must be routed before competitors claim their
      only viable path.

    Args:
        channel_mapping: Channel mapping with waypoints per net.
        bottleneck_widths: Optional dict mapping net_name to bottleneck
            width in mm.  When provided, nets with narrower bottlenecks
            route earlier within their cluster.

    Proof of correctness (induction):
      Base case: Two nets with zero bounding-box overlap.
        Assigned to separate clusters.  Their routing order cannot
        affect each other — the board has independent regions.
      Induction: Within a cluster of k overlapping nets, routing
        net 1 (smallest footprint or narrowest bottleneck) first gives
        it a clean grid.  When net k routes, it finds space that
        net 1 through net k-1 didn't need.  By induction on k,
        all nets in the cluster have at least the same routing
        opportunity as random ordering.
      Bottleneck lemma: routing net A (bottleneck=0.5mm) before net B
        (bottleneck=5mm) never makes B unroutable that wouldn't already
        be unroutable (B has 10x more routing options).
    """
    nets = list(channel_mapping.channel_paths)

    if len(nets) <= 1:
        return nets

    # 1. Compute bounding box for each net
    bboxes: dict[str, tuple[float, float, float, float]] = {}
    bbox_areas: dict[str, float] = {}
    for net_name in nets:
        path = channel_mapping.channel_paths[net_name]
        waypoints = path.waypoints
        if not waypoints:
            bboxes[net_name] = (0, 0, 0, 0)
            bbox_areas[net_name] = 0.0
            continue
        xs = [w[0] for w in waypoints]
        ys = [w[1] for w in waypoints]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        bboxes[net_name] = (min_x, min_y, max_x, max_y)
        bbox_areas[net_name] = (max_x - min_x) * (max_y - min_y)

    # 2. Build conflict graph.  Two nets conflict if their bounding
    #    boxes overlap more than 10% of the smaller net's area.
    #    This threshold prevents false clusters from slightly-overlapping
    #    nets that route in entirely different channels.
    threshold = 0.1
    conflict: dict[str, set[str]] = {n: set() for n in nets}
    net_list = list(nets)
    for i in range(len(net_list)):
        a = net_list[i]
        ax1, ay1, ax2, ay2 = bboxes[a]
        area_a = bbox_areas[a]
        if area_a <= 0:
            continue
        for j in range(i + 1, len(net_list)):
            b = net_list[j]
            bx1, by1, bx2, by2 = bboxes[b]
            area_b = bbox_areas[b]
            if area_b <= 0:
                continue
            # Compute overlap
            ox = max(0.0, min(ax2, bx2) - max(ax1, bx1))
            oy = max(0.0, min(ay2, by2) - max(ay1, by1))
            overlap = ox * oy
            min_area = min(area_a, area_b)
            if min_area > 0 and overlap / min_area > threshold:
                conflict[a].add(b)
                conflict[b].add(a)

    # 2b. Find connected components (clusters) via BFS
    visited: set[str] = set()
    clusters: list[list[str]] = []
    for net in nets:
        if net in visited:
            continue
        queue = [net]
        cluster: list[str] = []
        while queue:
            n = queue.pop()
            if n in visited:
                continue
            visited.add(n)
            cluster.append(n)
            for neighbor in conflict[n]:
                if neighbor not in visited:
                    queue.append(neighbor)
        clusters.append(cluster)

    # 3. Within each cluster, sort by (power_first, bottleneck_asc, area_asc)
    def cluster_sort_key(net_name: str) -> tuple:
        name_upper = net_name.upper()
        is_power = any(x in name_upper for x in ["GND", "VCC", "HV", "AC_", "+", "VBUS"])
        if bottleneck_widths is not None:
            bw = bottleneck_widths.get(net_name, float('inf'))
            return (not is_power, bw, bbox_areas.get(net_name, float('inf')))
        return (not is_power, bbox_areas.get(net_name, float('inf')))

    for cluster in clusters:
        cluster.sort(key=cluster_sort_key)

    # 4. Sort clusters: isolated first, then by cluster size descending
    clusters.sort(key=lambda c: (-len(c), sum(bbox_areas.get(n, 0) for n in c)))

    # 5. Flatten
    result = []
    for cluster in clusters:
        result.extend(cluster)
    return result

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
) -> tuple[RoutePath3D | None, int]:
    """
    Route a single net with per-segment layer switching at THT pads.

    For each waypoint pair:
    1. Try routing on primary grid
    2. If it fails AND waypoints are at THT pads, try alternate grid
    3. Stitch segments together

    Returns:
        (RoutePath3D or None, coarse_to_fine_fallback_count)
    """
    waypoints = channel_path.waypoints
    if len(waypoints) < 2:
        return None, 0

    detailed_segments: list[tuple[float, float, str]] = []
    forced_segments = 0
    fallback_count = 0

    for i in range(len(waypoints) - 1):
        start_world = waypoints[i]
        goal_world = waypoints[i + 1]

        segment_path, grid_to_use, fb = _segment_search(
            primary_grid, start_world, goal_world, use_theta_star,
            use_lazy_theta_star, congestion_tensor=congestion_tensor,
            max_iter=max_iter,
            enable_coarse_to_fine=enable_coarse_to_fine,
            coarse_factor=coarse_factor,
            corridor_buffer_cells=corridor_buffer_cells,
            enable_congestion_derivative=enable_congestion_derivative,
        )
        fallback_count += fb

        # Allow layer switching when THT pads exist on the board - the router
        # assumes layer transitions happen at nearby THT pads (implicit vias)
        if not segment_path and alternate_grid and tht_locations:
            alt_start = alternate_grid.world_to_grid(*start_world)
            alt_goal = alternate_grid.world_to_grid(*goal_world)
            if _in_bounds(alternate_grid, alt_start) and _in_bounds(alternate_grid, alt_goal):
                segment_path, grid_to_use, fb2 = _segment_search(
                    alternate_grid, start_world, goal_world, use_theta_star,
                    use_lazy_theta_star, congestion_tensor=congestion_tensor,
                    max_iter=max_iter,
                    enable_coarse_to_fine=enable_coarse_to_fine,
                    coarse_factor=coarse_factor,
                    corridor_buffer_cells=corridor_buffer_cells,
                    enable_congestion_derivative=enable_congestion_derivative,
                )
                fallback_count += fb2
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
    ), fallback_count


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
    fallback_count = 0

    for i in range(len(waypoints) - 1):
        start_world = waypoints[i]
        goal_world = waypoints[i + 1]

        grid_path, _, fb = _segment_search(
            grid, start_world, goal_world, use_theta_star, use_lazy_theta_star,
            max_iter=max_iter,
            enable_coarse_to_fine=enable_coarse_to_fine,
            coarse_factor=coarse_factor,
            corridor_buffer_cells=corridor_buffer_cells,
        )
        fallback_count += fb

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
    ), fallback_count
























def _dispatch_search(
    grid, start, goal,
    use_theta_star: bool, use_lazy_theta_star: bool,
    congestion_tensor=None,
    max_iter: int = 1_000_000,
    enable_numba_los: bool = False,
    enable_congestion_derivative: bool = True,
):
    if use_lazy_theta_star:
        return _astar_search_lazy_theta_star(
            grid, start, goal, net_id=-1,
            max_iter=max_iter,
            enable_numba_los=enable_numba_los,
            enable_congestion_derivative=enable_congestion_derivative,
        )
    if use_theta_star:
        return _astar_search_theta_star(
            grid, start, goal, net_id=-1,
            max_iter=max_iter,
            enable_numba_los=enable_numba_los,
            enable_congestion_derivative=enable_congestion_derivative,
        )
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
    enable_numba_los: bool = False,
    enable_coarse_to_fine: bool = False,
    coarse_factor: int = 4,
    corridor_buffer_cells: int = 12,
    enable_congestion_derivative: bool = True,
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

    if enable_coarse_to_fine:
        return _segment_search_coarse_to_fine(
            grid, start, goal, use_theta_star, use_lazy_theta_star,
            coarse_factor=coarse_factor,
            corridor_buffer_cells=corridor_buffer_cells,
            congestion_tensor=congestion_tensor,
            max_iter=max_iter,
            enable_congestion_derivative=enable_congestion_derivative,
        )

    path = _dispatch_search(
        grid, start, goal, use_theta_star, use_lazy_theta_star,
        congestion_tensor=congestion_tensor, max_iter=max_iter,
    enable_numba_los=enable_numba_los,
    enable_congestion_derivative=enable_congestion_derivative,
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
            neighbor_tensor = build_neighbor_validity_tensor_2d(
                grid, corridor_mask=corridor_mask
            )
            fine_path = _astar_search_numba(
                start, goal, grid, neighbor_tensor=neighbor_tensor,
                max_iterations=max_iter,
            )
            if fine_path is not None:
                return fine_path, grid, 0

    path = _dispatch_search(
        grid, start, goal, use_theta_star, use_lazy_theta_star,
        congestion_tensor=congestion_tensor, max_iter=max_iter,
    enable_numba_los=enable_numba_los,
    enable_congestion_derivative=enable_congestion_derivative,
    )
    return path, grid, 1


def _in_bounds(grid: OccupancyGrid, point: tuple[int, int]) -> bool:
    return 0 <= point[0] < grid.width_cells and 0 <= point[1] < grid.height_cells

