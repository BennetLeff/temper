"""
Router V6 Stage 4.2: Run A* Pathfinding

Runs A* pathfinding to generate actual routing paths.
Part of temper-x2xd (Stage 4 - Geometric Realization)
"""

from __future__ import annotations

from dataclasses import dataclass

from temper_placer.router_v6.channel_mapping import ChannelMapping
from temper_placer.router_v6.occupancy_grid import OccupancyGrid
from temper_placer.router_v6.stage0_data import DesignRules
import numpy as np
import sys


@dataclass
class RoutePath:
    """A routed path for a net."""

    net_name: str
    coordinates: list[tuple[float, float]]  # (x, y) path coordinates
    layer_name: str
    path_length: float  # Total length in mm
    forced_segment_count: int = 0  # Number of segments using force routing (fallback)

    @property
    def segment_count(self) -> int:
        """Number of segments in path."""
        return max(0, len(self.coordinates) - 1)


@dataclass
class RouteNode3D:
    """3D routing state for multi-layer A* pathfinding."""

    x: int  # Grid x coordinate
    y: int  # Grid y coordinate
    layer: str  # Layer name (e.g., "F.Cu", "B.Cu")

    def __hash__(self):
        return hash((self.x, self.y, self.layer))

    def __eq__(self, other):
        if not isinstance(other, RouteNode3D):
            return False
        return self.x == other.x and self.y == other.y and self.layer == other.layer


@dataclass
class RoutePath3D:
    """A routed path with explicit layer information per segment."""

    net_name: str
    segments: list[tuple[float, float, str]]  # (x, y, layer) coordinates
    via_positions: list[tuple[float, float]]  # Positions where layer changes occur
    path_length: float  # Total length in mm
    via_count: int = 0
    forced_segment_count: int = 0

    @property
    def segment_count(self) -> int:
        """Number of segments in path."""
        return max(0, len(self.segments) - 1)

    def to_route_path(self, default_layer: str = "F.Cu") -> RoutePath:
        """Convert to legacy RoutePath format."""
        coords = [(s[0], s[1]) for s in self.segments]
        return RoutePath(
            net_name=self.net_name,
            coordinates=coords,
            layer_name=default_layer,
            path_length=self.path_length,
            forced_segment_count=self.forced_segment_count,
        )


@dataclass
class RoutingFailureReport:
    """Detailed failure report for a net that failed to route."""

    net_name: str
    failure_reason: str  # "congestion", "no_path", "rip_up_limit", "no_channel", "channel_capacity_exceeded"
    blocking_nets: list[str]  # Which nets are blocking
    attempted_ripups: int
    congestion_region: tuple[float, float] | None  # Approximate (x, y) of stuck location
    pin_count: int = 0  # Number of pins in the net
    
    # Enhanced diagnostics for Benders cut generation
    failed_at: tuple[float, float] | None = None  # Exact failure location (mm)
    congested_channel: 'ChannelState | None' = None  # Channel that was full
    suggested_spacing_mm: float | None = None  # Estimated spacing needed
    blocking_components: list[str] | None = None  # Components to separate
    confidence: float = 0.0  # Confidence in diagnosis (0.0-1.0)


@dataclass
class PathfindingResult:
    """Result of A* pathfinding."""

    routed_paths: dict[str, RoutePath | RoutePath3D]  # net_name -> RoutePath
    failed_nets: list[str]  # Nets that failed to route
    failure_reports: dict[str, RoutingFailureReport] | None = None  # Detailed failures
    net_ids: dict[str, int] | None = None  # Map of net_name -> net_id used in grid
    competing_nets: set[str] | None = None  # Nets that oscillated and need negotiated routing

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


def _build_tht_pad_locations(pcb) -> set[tuple[float, float]]:
    """
    Build set of THT pad locations from parsed PCB data.

    Iterates through components and pins, checking pin.is_pth to find
    through-hole pads that can serve as layer transition points.

    Args:
        pcb: ParsedPCB object with components

    Returns:
        Set of (x, y) positions where THT pads exist (absolute coordinates)
    """
    import math

    tht_locations = set()

    if not hasattr(pcb, "components"):
        return tht_locations

    for comp in pcb.components:
        # Get component position and rotation
        comp_x, comp_y = comp.initial_position or (0.0, 0.0)
        angle = float(comp.initial_rotation or 0) * math.pi / 2.0

        for pin in comp.pins:
            # Check if pin is PTH (through-hole)
            if getattr(pin, "is_pth", False):
                # Call absolute_position() as a method to get world coordinates
                abs_pos = pin.absolute_position((comp_x, comp_y), angle)
                if abs_pos:
                    # Round to 0.1mm for matching tolerance
                    pos = (round(abs_pos[0], 1), round(abs_pos[1], 1))
                    tht_locations.add(pos)

    return tht_locations


def _extract_pad_centers_per_net(pcb) -> dict[str, list[tuple[float, float, float, str]]]:
    """
    Extract pad center coordinates, radius, and layer for each net.

    Returns dictionary mapping net_name -> list of (x, y, radius, layer) coordinates.
    radius is approximated as max(width, height) / 2.
    """
    import math

    pad_info: dict[str, list[tuple[float, float, float, str]]] = {}

    if not hasattr(pcb, "components"):
        return pad_info

    for comp in pcb.components:
        # Skip if no position or pins
        if not comp.initial_position or not hasattr(comp, "pins"):
            continue

        # Get component rotation (in degrees, need to convert to radians)
        rotation_deg = comp.initial_rotation * 90.0 if comp.initial_rotation is not None else 0.0
        rotation_rad = math.radians(rotation_deg)
        side = (
            comp.initial_side
            if hasattr(comp, "initial_side") and comp.initial_side is not None
            else 0
        )

        for pin in comp.pins:
            # Get pin's net
            if not pin.net:
                continue

            # Use Pin.absolute_position() method to get absolute coordinates
            abs_pos = pin.absolute_position(comp.initial_position, rotation_rad, side)

            # Approximate radius
            pin_w = pin.width if hasattr(pin, "width") else 0.0
            pin_h = pin.height if hasattr(pin, "height") else 0.0
            radius = max(pin_w, pin_h) / 2.0
            if radius == 0.0:
                radius = 0.5  # Default fallback

            layer = pin.layer if hasattr(pin, "layer") else "F.Cu"

            if pin.net not in pad_info:
                pad_info[pin.net] = []
            pad_info[pin.net].append((abs_pos[0], abs_pos[1], radius, layer))

    return pad_info


def _unblock_net_pads(
    net_name: str,
    pad_info: dict,
    grids: dict[str, OccupancyGrid],
    inflation_mm: float = 0.0,
    escape_vias_map: dict[str, list[tuple[float, float, float]]] | None = None,
) -> list[tuple[OccupancyGrid, list[tuple[int, int, int]]]]:
    """
    Temporarily unblock pads for the given net.
    Returns restoration data: list of (grid, [(x, y, old_val)]).
    """
    restoration_data = []

    # Helper to unblock a circular region on given grids
    def unblock_circle(cx_world, cy_world, radius_mm, target_grids):
        for grid in target_grids:
            # Expansion MUST include inflation to bridge the 'moat'
            expansion = int(np.ceil((radius_mm + inflation_mm) / grid.cell_size)) + 1
            gx, gy = grid.world_to_grid(cx_world, cy_world)

            x_start = max(0, gx - expansion)
            x_end = min(grid.width_cells, gx + expansion + 1)
            y_start = max(0, gy - expansion)
            y_end = min(grid.height_cells, gy + expansion + 1)

            saved_cells = []
            effective_unblock_radius = radius_mm + inflation_mm - 0.01

            for y in range(y_start, y_end):
                for x in range(x_start, x_end):
                    val = grid.grid[y, x]
                    if val == -1:  # Only unblock static obstacles
                        wx, wy = grid.grid_to_world(x, y)
                        dist = ((wx - cx_world) ** 2 + (wy - cy_world) ** 2) ** 0.5
                        if dist <= effective_unblock_radius:
                            saved_cells.append((x, y, val))
                            grid.grid[y, x] = 0

            if saved_cells:
                restoration_data.append((grid, saved_cells))

    if pad_info and net_name in pad_info:
        pads = pad_info[net_name]
        for px, py, radius, layer in pads:
            # Determine target grids
            target_grids = []
            if layer in ["All", "all"] or "*.Cu" in layer or "Through" in layer:
                target_grids = list(grids.values())
            elif layer in grids:
                target_grids = [grids[layer]]

            unblock_circle(px, py, radius, target_grids)

    # Also unblock escape vias (which are effectively THT pads for this net)
    if escape_vias_map and net_name in escape_vias_map:
        for vx, vy, diameter in escape_vias_map[net_name]:
            # Escape vias span ALL layers
            target_grids = list(grids.values())
            unblock_circle(vx, vy, diameter / 2.0, target_grids)

    return restoration_data

    pads = pad_info[net_name]
    for px, py, radius, layer in pads:
        # Determine target grids
        target_grids = []
        if layer in ["All", "all"] or "*.Cu" in layer or "Through" in layer:
            target_grids = list(grids.values())
        elif layer in grids:
            target_grids = [grids[layer]]

        # Unblock identifying area
        for grid in target_grids:
            # Expansion MUST include inflation to bridge the 'moat'
            expansion = int(np.ceil((radius + inflation_mm) / grid.cell_size)) + 1
            cx, cy = grid.world_to_grid(px, py)

            x_start = max(0, cx - expansion)
            x_end = min(grid.width_cells, cx + expansion + 1)
            y_start = max(0, cy - expansion)
            y_end = min(grid.height_cells, cy + expansion + 1)

            saved_cells = []

            # Simpler: Only unblock if cell center is within (radius + inflation) of THIS pad.
            # This allows the router to cross the C-Space 'moat' to reach the pad center.
            # We subtract a tiny epsilon (0.01mm) to ensure we don't accidentally touch
            # the exact center of a neighboring pad in extreme fine-pitch cases.
            effective_unblock_radius = radius + inflation_mm - 0.01

            for y in range(y_start, y_end):
                for x in range(x_start, x_end):
                    val = grid.grid[y, x]
                    if val == -1:  # Only unblock static obstacles
                        # Geometric check: Is this cell center inside our surgical unblock zone?
                        wx, wy = grid.grid_to_world(x, y)
                        dist = ((wx - px) ** 2 + (wy - py) ** 2) ** 0.5
                        if dist <= effective_unblock_radius:
                            saved_cells.append((x, y, val))
                            grid.grid[y, x] = 0

            if saved_cells:
                restoration_data.append((grid, saved_cells))

    return restoration_data


def _restore_net_pads(restoration_data):
    """Restore grid state after routing."""
    for grid, cells in restoration_data:
        for x, y, val in cells:
            # Only restore if it's still 0 (free).
            # If it's > 0, the router claimed it, so we leave it.
            if grid.grid[y, x] == 0:
                grid.grid[y, x] = val


def _is_at_tht_pad(
    position: tuple[float, float],
    tht_locations: set[tuple[float, float]],
    tolerance: float = 1.0,
) -> bool:
    """
    Check if position is at a THT pad.

    Args:
        position: (x, y) position to check
        tht_locations: Pre-built set of THT pad positions
        tolerance: Position matching tolerance in mm

    Returns:
        True if position is within tolerance of a THT pad
    """
    if not tht_locations:
        return False

    x, y = position
    for tht_x, tht_y in tht_locations:
        dist = ((x - tht_x) ** 2 + (y - tht_y) ** 2) ** 0.5
        if dist <= tolerance:
            return True

    return False


def _find_access_node(
    grid: OccupancyGrid,
    pin_pos: tuple[float, float],
    net_id: int,
    search_radius_cells: int = 3,
) -> tuple[int, int] | None:
    """
    Find best grid access node for an off-grid pin position.

    Searches neighborhood for the closest grid point that is either free (0)
    or owned by the net (net_id).

    Args:
        grid: Occupancy grid
        pin_pos: (x, y) world coordinates of pin center
        net_id: Net ID (to allow passing through own obstacles)
        search_radius_cells: Radius to search around snapped grid point

    Returns:
        (x_grid, y_grid) of best access node, or None if no valid node found.
    """
    px, py = pin_pos
    cx, cy = grid.world_to_grid(px, py)

    best_node = None
    min_dist = float("inf")

    # Iterate neighborhood
    for dy in range(-search_radius_cells, search_radius_cells + 1):
        for dx in range(-search_radius_cells, search_radius_cells + 1):
            gx, gy = cx + dx, cy + dy

            if not (0 <= gx < grid.width_cells and 0 <= gy < grid.height_cells):
                continue

            # Check if grid point is free or owned by net
            # Note: We rely on _unblock_net_pads having cleared the area around the pin
            val = grid.grid[gy, gx]
            if val != 0 and val != net_id:
                continue

            # Calculate distance to exact pin position
            wx, wy = grid.grid_to_world(gx, gy)
            dist = ((wx - px) ** 2 + (wy - py) ** 2) ** 0.5

            if dist < min_dist:
                min_dist = dist
                best_node = (gx, gy)

    return best_node


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
    hv_grids: dict[str, OccupancyGrid] | None = None,
    enable_topological_ordering: bool = False,
    verbose: bool = False,
    all_layer_grids: dict[str, OccupancyGrid] | None = None,  # All 4 layers
) -> PathfindingResult:
    # Build standard grids dictionary
    # If all_layer_grids provided, use it. Otherwise build from grid + alternate_grid
    if all_layer_grids:
        all_grids = dict(all_layer_grids)
    else:
        all_grids = {grid.layer_name: grid}
        if alternate_grid:
            all_grids[alternate_grid.layer_name] = alternate_grid
    
    # Pre-process HV grids if provided
    if hv_grids:
        # Ensure HV grids have net mapping too
        pass  # Will be updated in loop below
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
    
    # Track oscillation: (net_a, net_b) -> count of times they ripped each other
    oscillation_tracker: dict[tuple[str, str], int] = {}
    competing_nets: set[str] = set()  # Nets that need negotiated routing

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

    # Phase 2: Update grids with net_id_to_name mapping and design_rules for differential pair support
    for grid_obj in all_grids.values():
        grid_obj.net_id_to_name = id_to_net
        grid_obj.design_rules = design_rules
        
    if hv_grids:
        for grid_obj in hv_grids.values():
            grid_obj.net_id_to_name = id_to_net
            grid_obj.design_rules = design_rules

    # Sort nets by routing scheduling priority
    net_order = _compute_net_order(
        channel_mapping, 
        pcb=pcb, 
        enable_topological_ordering=enable_topological_ordering
    )

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
    problem_nets = {"/k02", "/k04", "/k25", "/k24", "/k15", "I_SENSE", "SPI_MOSI", "SPI_MISO", "PWM_L"}

    reroute_queue: list[str] = []

    def attempt_route(
        net_name: str, depth: int = 0
    ) -> tuple[bool, str, list[str], tuple[float, float] | None]:
        """
        Recursive function to route with rip-up.

        Returns:
            (success, failure_reason, blocking_nets, congestion_region)
        """
        # NOTE: We DON'T block competing nets from routing!
        # With layer assignment, they should be able to route on their assigned layers.
        # We only prevent them from ripping up each other.
        
        # Adaptive depth limit
        max_depth = 5  # Low limit to prevent infinite loops
        if depth > max_depth:
            # Compute congestion region from waypoints for diagnostics
            channel_path = channel_mapping.channel_paths.get(net_name)
            region = None
            if channel_path and channel_path.waypoints:
                mid_idx = len(channel_path.waypoints) // 2
                region = channel_path.waypoints[mid_idx]
            return False, "rip_up_limit", [], region

        channel_path = channel_mapping.channel_paths[net_name]
        net_id = net_ids[net_name]
        
        # Grid Selection Strategy:
        # If net is ACMains, use the inflated HV grids (6.0mm clearance).
        # Otherwise use standard grids.
        current_grids = all_grids
        
        # Check Net Class
        net_rules = design_rules.get_rules_for_net(net_name)
        class_name = design_rules.net_class_assignments.get(net_name, "")
        # print(f"      DEBUG: Net {net_name} class='{class_name}', hv_grids_present={hv_grids is not None}")
        
        if hv_grids and class_name in ("ACMains", "HighVoltageIsolated"):
             # print(f"    Using HV Grids for {net_name} ({class_name})")
             current_grids = hv_grids

        # LAYER-LOCKED ROUTING (Professional PCB Design Practice)
        # If net has explicit layer constraint from design rules, use THAT layer
        # This enables true 4-layer routing with signals on inner layers
        layer_constraint = design_rules.get_layer_constraint(net_name)
        
        if layer_constraint is not None and layer_constraint in current_grids:
            # Use the constrained layer as primary
            primary_grid = current_grids[layer_constraint]
            # Force single-layer routing - no layer switching allowed
            active_alternate = None
        else:
            # Determine primary and alternate grid based on net's preference
            primary_grid = current_grids.get(channel_path.preferred_layer, grid)
            # Fallback if primary not found in current_grids (shouldn't happen if consistent)
            if not primary_grid and current_grids:
                 primary_grid = list(current_grids.values())[0]
            
            # Alternate grid is the one NOT preferred
            alt_layer = next((l for l in current_grids.keys() if l != channel_path.preferred_layer), None)
            active_alternate = current_grids.get(alt_layer)
            if not active_alternate and alternate_grid and current_grids is all_grids:
                 active_alternate = alternate_grid # fallback for standard case

        # Get net-specific routing rules
        net_rules = design_rules.get_rules_for_net(net_name)

        # Unblock pads for this net to allow A* to connect (Surgery is inflation-aware)
        base_inflation = (
            net_rules.trace_width_mm / 2.0
        ) + net_rules.clearance_mm
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
            
            # Handle rip-ups with per-net limit
            for ripped_id in ripped_ids:
                if ripped_id in id_to_net:
                    ripped_name = id_to_net[ripped_id]
                    if ripped_name in routed_paths:
                        # Track oscillation for diagnostics
                        pair_key = tuple(sorted([net_name, ripped_name]))
                        oscillation_tracker[pair_key] = oscillation_tracker.get(pair_key, 0) + 1
                        
                        if oscillation_tracker[pair_key] >= 3:
                            competing_nets.add(net_name)
                            competing_nets.add(ripped_name)
                            # Don't rip up - they'll keep fighting
                            continue
                        
                        # Check if ripped net has been ripped too many times
                        if ripup_counts.get(ripped_name, 0) >= 3:
                            # Don't rip up - let it stay
                            continue
                        
                        # Proceed with rip-up
                        ripped_rules = design_rules.get_rules_for_net(ripped_name)
                        ripped_path = routed_paths[ripped_name]
                        _unmark_route_blocked(
                            ripped_path,
                            all_grids,
                            trace_width=ripped_rules.trace_width_mm,
                            clearance=ripped_rules.clearance_mm,
                            net_id=ripped_id,
                        )
                        del routed_paths[ripped_name]
                        reroute_queue.append(ripped_name)
                        ripup_counts[ripped_name] = ripup_counts.get(ripped_name, 0) + 1

            # Mark new path with net-specific rules (layer-aware)
            routed_paths[net_name] = route_path
            _mark_route_blocked(
                route_path,
                all_grids,
                trace_width=net_rules.trace_width_mm,
                clearance=net_rules.clearance_mm,
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
        """Record a failure with all accumulated data and enhanced diagnostics."""
        channel_path = channel_mapping.channel_paths.get(net_name)
        pin_count = len(channel_path.waypoints) if channel_path else 0

        # Merge with previously recorded blockers
        all_blockers = list(blocker_history.get(net_name, set()))

        # ENHANCED DIAGNOSTICS (Phase 2)
        from temper_placer.router_v6.channel_state import (
            estimate_required_spacing,
            identify_blocking_components,
            compute_failure_confidence,
            ChannelState,
        )
        
        failed_at = region  # Use congestion region as failure location
        congested_channel = None
        suggested_spacing_mm = None
        blocking_components = None
        confidence = 0.0
        
        # Try to analyze failure if we have a location
        if region and grid:
            try:
                # Convert mm to grid coordinates
                gx = int((region[0] - grid.origin[0]) / grid.cell_size)
                gy = int((region[1] - grid.origin[1]) / grid.cell_size)
                
                # Analyze channel capacity at failure point
                # Count occupied cells in a small region around failure
                search_radius = 5  # cells
                occupied_count = 0
                total_cells = 0
                occupied_cells_map = {}
                
                for dx in range(-search_radius, search_radius + 1):
                    for dy in range(-search_radius, search_radius + 1):
                        cx, cy = gx + dx, gy + dy
                        if 0 <= cx < grid.width_cells and 0 <= cy < grid.height_cells:
                            total_cells += 1
                            cell_val = grid.grid[cy, cx]
                            if cell_val > 0:  # Occupied by a net
                                occupied_count += 1
                                # Try to get net name
                                if id_to_net and cell_val in id_to_net:
                                    occupied_cells_map[(cx, cy)] = id_to_net[cell_val]
                
                # Estimate channel capacity
                # Rough heuristic: 1 track per 2 cells width
                capacity = max(1, total_cells // 10)
                used = max(1, occupied_count // 10)
                
                # Create ChannelState
                nets_using = list(set(occupied_cells_map.values()))[:4]  # Top 4
                
                congested_channel = ChannelState(
                    channel_id=f"region_{region[0]:.1f}_{region[1]:.1f}",
                    capacity=capacity,
                    used=used,
                    nets_using=nets_using,
                    bounding_components=("unknown", "unknown"),  # Will identify below
                    position=region,
                    width_mm=search_radius * grid.cell_size * 2,
                )
                
                # Identify blocking components from occupied cells
                blocking_components = identify_blocking_components(
                    failure_grid_pos=(gx, gy),
                    occupied_cells=occupied_cells_map,
                    search_radius=search_radius,
                )
                
                # Estimate required spacing
                if congested_channel.used >= congested_channel.capacity:
                    tracks_needed = congested_channel.used + 1
                    suggested_spacing_mm = estimate_required_spacing(
                        tracks_needed=tracks_needed,
                        tracks_available=congested_channel.capacity,
                        trace_width_mm=design_rules.default_trace_width_mm,
                        clearance_mm=design_rules.default_clearance_mm,
                    )
                
                # Compute confidence
                confidence = compute_failure_confidence(
                    channel_utilization=congested_channel.utilization if congested_channel else None,
                    blocking_components_count=len(blocking_components) if blocking_components else 0,
                    has_exact_location=region is not None,
                    has_channel_data=congested_channel is not None,
                )
                
            except Exception as e:
                # If analysis fails, just use defaults
                # Silently continue with basic diagnostics
                pass

        failure_reports[net_name] = RoutingFailureReport(
            net_name=net_name,
            failure_reason=reason,
            blocking_nets=all_blockers,
            attempted_ripups=ripup_counts.get(net_name, 0),
            congestion_region=region,
            pin_count=pin_count,
            # Enhanced fields
            failed_at=failed_at,
            congested_channel=congested_channel,
            suggested_spacing_mm=suggested_spacing_mm,
            blocking_components=blocking_components,
            confidence=confidence,
        )

    # First pass: Route all routable nets (skip PLANE/unconnected)
    for i, net_name in enumerate(routable_nets):
        if net_name not in channel_mapping.channel_paths:
            continue
        success, reason, blockers, region = attempt_route(net_name)
        if not success:
            failed_nets.append(net_name)
            record_failure(net_name, reason, blockers, region)

    # Second pass: Process reroute queue with per-net limit
    max_reroute_total = 50  # Total iterations
    reroute_count = 0
    net_reroute_counts = {}
    
    while reroute_queue and reroute_count < max_reroute_total:
        net_name = reroute_queue.pop(0)
        reroute_count += 1
        
        # Per-net limit
        net_reroute_counts[net_name] = net_reroute_counts.get(net_name, 0) + 1
        if net_reroute_counts[net_name] > 3:
            # This net has been rerouted too many times - give up
            if net_name not in failed_nets:
                failed_nets.append(net_name)
                channel_path = channel_mapping.channel_paths.get(net_name)
                region = None
                if channel_path and channel_path.waypoints:
                    mid_idx = len(channel_path.waypoints) // 2
                    region = channel_path.waypoints[mid_idx]
                record_failure(net_name, "reroute_limit", [], region)
            continue
        
        success, reason, blockers, region = attempt_route(net_name, depth=1)
        if not success:
            if net_name not in failed_nets:
                failed_nets.append(net_name)
            record_failure(net_name, reason, blockers, region)
    
    # Mark remaining nets as failed
    for net_name in reroute_queue:
        if net_name not in failed_nets:
            failed_nets.append(net_name)
            channel_path = channel_mapping.channel_paths.get(net_name)
            region = None
            if channel_path and channel_path.waypoints:
                mid_idx = len(channel_path.waypoints) // 2
                region = channel_path.waypoints[mid_idx]
            record_failure(net_name, "queue_limit", [], region)

    # Report competing nets if any were detected
    if competing_nets:
        print(f"\n⚠️  Detected {len(competing_nets)} competing nets that need negotiated routing:")
        print(f"   {', '.join(sorted(competing_nets))}")
        sys.stdout.flush()
    
    print(f"  Sequential routing complete: {len(routed_paths)} routed, {len(failed_nets)} failed")
    sys.stdout.flush()
    
    return PathfindingResult(
        routed_paths=routed_paths,
        failed_nets=list(set(failed_nets)),
        failure_reports=failure_reports,
        net_ids=net_ids,
        competing_nets=competing_nets if competing_nets else None,
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
    # Get net_id for differential pair support
    net_id = net_ids.get(net_name, -1)

    # Try multilayer routing if alternate grid available
    if alternate_grid and tht_locations:
        path = _astar_route_multilayer(
            net_name,
            channel_path,
            grid,
            alternate_grid,
            tht_locations,
            use_theta_star,
            use_lazy_theta_star,
            net_id=net_id,
        )
    else:
        path = _astar_route(net_name, channel_path, grid, use_theta_star, use_lazy_theta_star, net_id=net_id)

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


def _identify_blocking_nets(channel_path, grids: list[OccupancyGrid]) -> set[int]:
    """Identify net IDs blocking the straight-line paths across all specified layers."""
    blockers = set()
    waypoints = channel_path.waypoints

    for i in range(len(waypoints) - 1):
        p1 = waypoints[i]
        p2 = waypoints[i + 1]

        # Check if segment is blocked on ANY of the grids
        for grid in grids:
            segment_blockers = grid.get_blocking_nets(p1, p2)
            blockers.update(segment_blockers)

    return blockers


def _compute_net_order(
    channel_mapping: ChannelMapping,
    pcb: any = None,
    enable_topological_ordering: bool = False
) -> list[str]:
    """
    Compute routing order for nets.

    Priority (highest to lowest):
    1. Power/HV/Critical nets (establish main arteries)
    2. Topological Constraints (nested nets)
    3. Heuristic Scores (pin density, area)
    """
    from temper_placer.router_v6.analysis.topological_ordering import TopologicalOrderer
    
    nets_data = {}
    if pcb:
        # Extract pad centers for the orderer
        pad_centers = _extract_pad_centers_per_net(pcb)
        for net_name in channel_mapping.channel_paths.keys():
            if net_name in pad_centers:
                # Store (x, y) coordinates
                nets_data[net_name] = [(p[0], p[1]) for p in pad_centers[net_name]]
    
    if enable_topological_ordering and pcb and nets_data:
        print("  Using Topological Net Ordering...")
        orderer = TopologicalOrderer()
        
        # 1. Automatic Constraint Detection (Nesting)
        auto_deps = orderer.detect_topological_constraints(nets_data)
        
        # 2. Conflict Analysis (Intersections)
        conflicts = orderer.detect_conflicts(nets_data)
        
        # 3. Compute final order
        all_deps = auto_deps + conflicts
        
        # Get board centroid for radial priority
        centroid = None
        if hasattr(pcb, "board") and pcb.board:
            bounds = pcb.board.get_bounds_array() # [xmin, ymin, xmax, ymax]
            centroid = ((bounds[0] + bounds[2]) / 2.0, (bounds[1] + bounds[3]) / 2.0)
            
        order, sccs = orderer.compute_order(nets_data, dependencies=all_deps, board_centroid=centroid)
        
        if sccs:
            print(f"  Warning: Found {len(sccs)} irreducible routing conflicts (SCCs)")
            for i, scc in enumerate(sccs[:3]):
                print(f"    SCC {i+1}: {', '.join(scc[:5])}...")
                
        # Fill in any nets missing from data (unconnected or single-pin)
        missing = [n for n in channel_mapping.channel_paths.keys() if n not in order]
        return order + missing
        
    # Standard Heuristic Fallback
    nets = list(channel_mapping.channel_paths.keys())

    # Nets that historically fail - give them priority
    problem_nets = {"/k02", "/k04", "/k25", "/k24", "/k15", "I_SENSE", "SPI_MOSI", "SPI_MISO", "PWM_L"}

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
    net_id: int = -1,
) -> RoutePath3D | None:
    """
    Route a single net with per-segment layer switching at THT pads.

    For multi-pin nets (>2 waypoints), uses MST-based routing for optimal
    wire length and reduced self-blocking.

    For each MST edge:
    1. Try routing on primary grid
    2. If it fails AND THT pads available, try alternate grid
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

    # Determine routing pairs: MST for multi-pin, sequential for 2-pin
    if len(waypoints) > 2:
        # Multi-pin net: use MST for optimal routing order
        from temper_placer.router_v6.steiner_tree import compute_mst_edges, compute_routing_order
        mst_edges = compute_mst_edges(waypoints)
        routing_pairs = compute_routing_order(mst_edges)
    else:
        # 2-pin net: simple direct connection
        routing_pairs = [(waypoints[0], waypoints[1])]

    detailed_segments = []  # (x, y, layer)
    via_positions = []
    forced_segments = 0

    for edge_idx, (start_world, goal_world) in enumerate(routing_pairs):

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
                    grid_to_use, start_grid, goal_grid, net_id=net_id
                )
            elif use_theta_star:
                segment_path = _astar_search_theta_star(
                    grid_to_use, start_grid, goal_grid, net_id=net_id
                )
            else:
                segment_path = _astar_search(start_grid, goal_grid, grid_to_use, net_id=net_id)

        # If primary failed and alternate available, try alternate layer
        # Allow layer switching when THT pads exist on the board - the router
        # assumes layer transitions happen at nearby THT pads (implicit vias)
        if not segment_path and alternate_grid and tht_locations:
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
                        grid_to_use, start_grid, goal_grid, net_id=net_id
                    )
                elif use_theta_star:
                    segment_path = _astar_search_theta_star(
                        grid_to_use, start_grid, goal_grid, net_id=net_id
                    )
                else:
                    segment_path = _astar_search(start_grid, goal_grid, grid_to_use, net_id=net_id)

        # Add segment to path
        if segment_path:
            # Found path!
            layer_name = grid_to_use.layer_name

            # Stitch: Add start_world if first segment
            if edge_idx == 0:
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
            if edge_idx == len(routing_pairs) - 1:
                detailed_segments.append((goal_world[0], goal_world[1], layer_name))

            continue

        # If we get here, segment failed
        forced_segments += 1
        # Fallback: add direct segment
        if edge_idx == 0:
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
    heuristic_weight: float = 1.0,
    net_id: int = -1,
) -> RoutePath | None:
    """
    Route a single net using A* or Theta* pathfinding.

    For multi-pin nets (>2 waypoints), uses MST-based routing instead of
    sequential chain routing for optimal wire length and reduced self-blocking.

    Args:
        net_name: Net to route
        channel_path: Channel path guidance
        grid: Occupancy grid
        use_theta_star: Use Theta* any-angle routing instead of standard A*
        heuristic_weight: A* heuristic multiplier (default 1.0)

    Returns:
        RoutePath or None if routing fails
    """
    # Get waypoints from channel path
    waypoints = channel_path.waypoints

    if not waypoints or len(waypoints) < 2:
        # Need at least 2 waypoints (start and end)
        return None

    # Determine routing pairs: MST for multi-pin, sequential for 2-pin
    if len(waypoints) > 2:
        # Multi-pin net: use MST for optimal routing order
        from temper_placer.router_v6.steiner_tree import compute_mst_edges, compute_routing_order
        mst_edges = compute_mst_edges(waypoints)
        routing_pairs = compute_routing_order(mst_edges)
    else:
        # 2-pin net: simple direct connection
        routing_pairs = [(waypoints[0], waypoints[1])]

    # Route each pair and collect all coordinates
    all_edge_coords = []  # List of coordinate lists, one per edge
    forced_segments = 0

    for edge_idx, (start_world, goal_world) in enumerate(routing_pairs):
        # Convert world coordinates to grid coordinates
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
                grid_path = _astar_search_lazy_theta_star(
                    grid, start_grid, goal_grid, net_id=-1, heuristic_weight=heuristic_weight
                )
            elif use_theta_star:
                grid_path = _astar_search_theta_star(grid, start_grid, goal_grid, net_id=-1)
            else:
                grid_path = _astar_search(start_grid, goal_grid, grid)

        edge_coords = []
        if grid_path:
            # Add start point exactly
            edge_coords.append(start_world)
            
            # Convert grid path back to world coordinates
            for grid_cell in grid_path:
                world_coord = grid.grid_to_world(grid_cell[0], grid_cell[1])
                # Avoid duplicate coordinates
                if not edge_coords or edge_coords[-1] != world_coord:
                    edge_coords.append(world_coord)
            
            # Add goal point exactly
            if edge_coords[-1] != goal_world:
                edge_coords.append(goal_world)
        else:
            # A* failed, fall back to direct line
            edge_coords = [start_world, goal_world]
            forced_segments += 1

        all_edge_coords.append(edge_coords)

    # Merge all edge coordinates into a single path
    # For tree structures, we traverse edges in order (center-out from MST ordering)
    detailed_coords = []
    seen_points = set()
    
    for edge_coords in all_edge_coords:
        for coord in edge_coords:
            # Use tuple for hashability, round for floating point comparison
            coord_key = (round(coord[0], 4), round(coord[1], 4))
            if coord_key not in seen_points:
                detailed_coords.append(coord)
                seen_points.add(coord_key)
            elif coord == edge_coords[-1]:
                # Always include endpoint to maintain connectivity
                detailed_coords.append(coord)

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
        path_length=path_length,
        forced_segment_count=forced_segments,
    )


def _astar_search(
    start: tuple[int, int],
    goal: tuple[int, int],
    grid: OccupancyGrid,
    net_id: int = -1,
) -> list[tuple[int, int]] | None:
    """
    A* search algorithm for pathfinding.

    Args:
        start: Start cell (x, y)
        goal: Goal cell (x, y)
        grid: Occupancy grid
        net_id: Net ID for differential-pair-aware routing

    Returns:
        List of cells or None if no path found
    """
    from heapq import heappop, heappush

    # A* frontier (priority queue)
    frontier = []
    heappush(frontier, (0, start))

    # Came from and cost tracking
    came_from = {start: None}
    cost_so_far = {start: 0}

    while frontier:
        _, current = heappop(frontier)

        if current == goal:
            # Reconstruct path
            path = []
            while current is not None:
                path.append(current)
                current = came_from[current]
            return list(reversed(path))

        # Explore neighbors (8-connected)
        x, y = current
        # Directions: Right, Down, Left, Up, Diagonals
        moves = [(1, 0), (0, 1), (-1, 0), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)]

        for dx, dy in moves:
            neighbor = (x + dx, y + dy)

            # Check if neighbor is valid and free (differential-pair-aware if net_id provided)
            if net_id > 0:
                if not grid.is_free_for_net(neighbor[0], neighbor[1], net_id):
                    continue
            else:
                if not grid.is_free(neighbor[0], neighbor[1]):
                    continue

            # Diagonal cost = 1.414, Cardinal = 1.0
            dist = 1.414 if dx != 0 and dy != 0 else 1.0

            # Congestion cost
            if grid.negotiated_mode:
                # PathFinder cost: (Base + History + Congestion) * Distance
                node_cost = grid.get_cost(neighbor[0], neighbor[1])
                move_cost = node_cost * dist
            else:
                move_cost = dist

            new_cost = cost_so_far[current] + move_cost

            if neighbor not in cost_so_far or new_cost < cost_so_far[neighbor]:
                cost_so_far[neighbor] = new_cost
                priority = new_cost + _heuristic(neighbor, goal)
                heappush(frontier, (priority, neighbor))
                came_from[neighbor] = current

    return None  # No path found


def _heuristic(a: tuple[int, int], b: tuple[int, int]) -> float:
    """Manhattan/Octile distance heuristic."""
    dx = abs(a[0] - b[0])
    dy = abs(a[1] - b[1])
    # Octile distance for 8-connected grid
    # Cost = max(dx, dy) + (sqrt(2)-1)*min(dx, dy) = max + 0.414*min
    return max(dx, dy) + 0.414 * min(dx, dy)


def _line_of_sight(
    p1: tuple[int, int], p2: tuple[int, int], grid: OccupancyGrid, net_id: int
) -> bool:
    """
    Check if there's an unobstructed diagonal line between two grid points.

    Uses Bresenham's line algorithm to check all cells along the path.

    Args:
        p1: Start grid position (x, y)
        p2: End grid position (x, y)
        grid: Occupancy grid
        net_id: Net ID (cells with this ID are allowed)

    Returns:
        True if line is clear
    """
    x0, y0 = p1
    x1, y1 = p2

    dx = abs(x1 - x0)
    dy = abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx - dy

    x, y = x0, y0

    while True:
        # Check if current cell is blocked
        if not (0 <= x < grid.width_cells and 0 <= y < grid.height_cells):
            return False

        cell_value = grid.grid[y, x]
        # Allow: free (0) or own net (net_id)
        if cell_value != 0 and cell_value != net_id:
            return False

        # Reached goal
        if x == x1 and y == y1:
            break

        # Bresenham step
        e2 = 2 * err
        if e2 > -dy:
            err -= dy
            x += sx
        if e2 < dx:
            err += dx
            y += sy

    return True


def _line_cost(p1: tuple[int, int], p2: tuple[int, int], grid: OccupancyGrid, net_id: int) -> float:
    """
    Calculate accumulated cost along a line segment.
    Returns float('inf') if blocked.
    """
    x0, y0 = p1
    x1, y1 = p2

    dx = abs(x1 - x0)
    dy = abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx - dy

    x, y = x0, y0
    total_cell_cost = 0.0
    count = 0

    while True:
        # Check bounds
        if not (0 <= x < grid.width_cells and 0 <= y < grid.height_cells):
            return float("inf")

        cell_value = grid.grid[y, x]
        # In negotiated mode, we check cost. In normal mode, we check blocking.
        if grid.negotiated_mode:
            # Check static obstacle
            if cell_value == -1:
                return float("inf")
            # Accumulate cost
            total_cell_cost += grid.get_cost(x, y)
        else:
            # Binary check
            if cell_value != 0 and cell_value != net_id:
                return float("inf")
            total_cell_cost += 1.0

        count += 1

        if x == x1 and y == y1:
            break

        e2 = 2 * err
        if e2 > -dy:
            err -= dy
            x += sx
        if e2 < dx:
            err += dx
            y += sy

    # Calculate geometric length
    length = ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5

    # Average cost per unit length * length
    if count == 0:
        return length  # Should not happen

    avg_cost = total_cell_cost / count
    return avg_cost * length


def _astar_search_lazy_theta_star(
    grid: OccupancyGrid,
    start_grid: tuple[int, int],
    goal_grid: tuple[int, int],
    net_id: int,
    came_from_init: dict | None = None,
    heuristic_weight: float = 1.2,
) -> list[tuple[int, int]] | None:
    """
    Lazy Theta* pathfinding.

    Optimizes Theta* by delaying the line-of-sight check until a node is expanded.
    This significantly reduces the number of geometric checks.

    Args:
        grid: Occupancy grid
        start_grid: Start position (grid coordinates)
        goal_grid: Goal position (grid coordinates)
        net_id: Net ID for unblocking own cells
        came_from_init: Optional initial came_from for warm-starting
        heuristic_weight: A* heuristic multiplier (1.0 = optimal, >1.0 = faster/greedier)

    Returns:
        Path as list of (x, y) grid cells, or None if no path
    """
    from heapq import heappush, heappop
    import math

    # Priority queue: (f_score, counter, current_pos)
    counter = 0
    open_set = []
    heappush(open_set, (0.0, counter, start_grid))

    came_from = came_from_init.copy() if came_from_init else {}
    g_score = {start_grid: 0.0}
    closed_set = set()

    import time

    start_time = time.time()
    # 5 seconds is enough for most nets; if it takes longer, it's likely stuck exploring open space
    timeout_seconds = 5.0

    def euclidean_dist(p1, p2):
        return math.sqrt((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2)

    def reconstruct_path(current):
        path = [current]
        while current in came_from:
            current = came_from[current]
            # Handle start node case (came_from[start] not in came_from)
            if current == start_grid:
                break
            path.append(current)
        path.reverse()
        return path

    while open_set:
        # Timeout check
        if (counter % 1000 == 0) and (time.time() - start_time > timeout_seconds):
            return None

        f_val, _, current = heappop(open_set)

        # DEBUG: Trace search
        if heuristic_weight == 0.0 and (counter < 50 or current == (10, 10) or current == (10, 2)):
            print(f"DEBUG: Expanding {current} g={g_score.get(current)} f={f_val}")

        if current in closed_set:
            continue

        # LAZY CHECK: Validate LOS only when expanding
        parent = came_from.get(current)
        if parent:
            if not _line_of_sight(parent, current, grid, net_id):
                # LOS Failed.
                # Standard Lazy Theta* strategy: find a valid parent from closed neighbors
                # This is "Vertex A adjustment" from the paper.
                # However, since we populate using optimistic parents, the 'current'
                # node might not have a valid parent in the closed set that reaches it
                # directly via LOS.
                # Simplified strategy: If LOS from parent fails, treat it as an A* node
                # (but we didn't store the A* parent).
                # Re-evaluate parent from neighbors in closed set.

                best_parent = None
                best_g = float("inf")

                # Check 8-connected neighbors
                cx, cy = current
                for dx, dy in [
                    (0, 1),
                    (1, 0),
                    (0, -1),
                    (-1, 0),
                    (1, 1),
                    (1, -1),
                    (-1, 1),
                    (-1, -1),
                ]:
                    nx, ny = cx + dx, cy + dy
                    neighbor = (nx, ny)

                    if neighbor in closed_set and neighbor in g_score:
                        # Cost is just distance (1 or 1.414)
                        step_cost = euclidean_dist(neighbor, current)
                        new_g = g_score[neighbor] + step_cost
                        if new_g < best_g:
                            best_g = new_g
                            best_parent = neighbor

                if best_parent:
                    came_from[current] = best_parent
                    g_score[current] = best_g
                    # Continue expansion with corrected parent
                else:
                    # Should not happen if we reached 'current'
                    continue

        if current == goal_grid:
            return reconstruct_path(current)

        closed_set.add(current)

        # Get 8-connected neighbors
        cx, cy = current
        neighbors = []
        for dx, dy in [(0, 1), (1, 0), (0, -1), (-1, 0), (1, 1), (1, -1), (-1, 1), (-1, -1)]:
            nx, ny = cx + dx, cy + dy
            if 0 <= nx < grid.width_cells and 0 <= ny < grid.height_cells:
                # Use differential-pair-aware free check if net_id provided
                if net_id > 0:
                    if grid.is_free_for_net(nx, ny, net_id):
                        neighbors.append((nx, ny))
                else:
                    cell_value = grid.grid[ny, nx]
                    if cell_value == 0 or cell_value == net_id:
                        neighbors.append((nx, ny))

        for neighbor in neighbors:
            if neighbor in closed_set:
                continue

            # LAZY OPTIMIZATION: Always assume LOS from parent(current) to neighbor
            # This makes the "parent" pointer jump multiple steps.
            # parent(neighbor) = parent(current)

            grandparent = came_from.get(current)

            # Path 1: Optimistic (grandparent -> neighbor)
            if grandparent:
                tentative_g_lazy = g_score[grandparent] + euclidean_dist(grandparent, neighbor)
                path_source_lazy = grandparent
            else:
                # Start node has no parent
                tentative_g_lazy = float("inf")
                path_source_lazy = None

            # Path 2: A* (current -> neighbor) - always valid if adjacent
            tentative_g_astar = g_score[current] + euclidean_dist(current, neighbor)

            # Choose best (usually optimistic)
            # Standard Lazy Theta* typically just picks the optimistic one if better.
            # But we must ensure g-values are consistent.

            if grandparent and tentative_g_lazy < tentative_g_astar:
                tentative_g = tentative_g_lazy
                path_source = path_source_lazy
            else:
                tentative_g = tentative_g_astar
                path_source = current

            if neighbor not in g_score or tentative_g < g_score[neighbor]:
                came_from[neighbor] = path_source
                g_score[neighbor] = tentative_g
                # Add heuristic weight to speed up search in open spaces
                f_score = tentative_g + heuristic_weight * euclidean_dist(neighbor, goal_grid)
                counter += 1
                heappush(open_set, (f_score, counter, neighbor))

    return None


def _astar_search_theta_star(
    grid: OccupancyGrid,
    start_grid: tuple[int, int],
    goal_grid: tuple[int, int],
    net_id: int,
    came_from_init: dict | None = None,
    heuristic_weight: float = 1.0,
) -> list[tuple[int, int]] | None:
    """
    Theta* pathfinding with any-angle paths.

    Args:
        heuristic_weight: A* heuristic multiplier.
    """
    from heapq import heappush, heappop
    import math

    # Priority queue: (f_score, counter, current_pos)
    counter = 0
    open_set = []
    heappush(open_set, (0.0, counter, start_grid))

    came_from = came_from_init.copy() if came_from_init else {}
    g_score = {start_grid: 0.0}
    closed_set = set()

    def euclidean_dist(p1, p2):
        return math.sqrt((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2)

    def reconstruct_path(current):
        path = [current]
        while current in came_from:
            current = came_from[current]
            path.append(current)
        path.reverse()
        return path

    while open_set:
        _, _, current = heappop(open_set)

        if current in closed_set:
            continue

        if current == goal_grid:
            return reconstruct_path(current)

        closed_set.add(current)

        # Get 8-connected neighbors
        cx, cy = current
        neighbors = []
        for dx, dy in [(0, 1), (1, 0), (0, -1), (-1, 0), (1, 1), (1, -1), (-1, 1), (-1, -1)]:
            nx, ny = cx + dx, cy + dy
            if 0 <= nx < grid.width_cells and 0 <= ny < grid.height_cells:
                # Use differential-pair-aware free check if net_id provided
                if net_id > 0:
                    if not grid.is_free_for_net(nx, ny, net_id):
                        continue
                else:
                    # Check occupancy (binary or cost is handled in line_cost, but fast check here?)
                    # Basic check
                    cell_val = grid.grid[ny, nx]
                    if grid.negotiated_mode:
                        if cell_val == -1:
                            continue
                    else:
                        if cell_val != 0 and cell_val != net_id:
                            continue
                neighbors.append((nx, ny))

        for neighbor in neighbors:
            if neighbor in closed_set:
                continue

            # Theta* Logic: Check path from Parent(Current) -> Neighbor
            parent = came_from.get(current)

            # 1. Try Shortcut (Parent -> Neighbor)
            shortcut_g = float("inf")
            if parent:
                cost = _line_cost(parent, neighbor, grid, net_id)
                if cost != float("inf"):
                    shortcut_g = g_score[parent] + cost

            # 2. Try Normal (Current -> Neighbor)
            # Edge cost
            dist = 1.414 if (neighbor[0] != current[0] and neighbor[1] != current[1]) else 1.0
            if grid.negotiated_mode:
                node_cost = grid.get_cost(neighbor[0], neighbor[1])
                step_cost = node_cost * dist
            else:
                step_cost = dist

            normal_g = g_score[current] + step_cost

            # Choose best
            if shortcut_g < normal_g:
                tentative_g = shortcut_g
                path_source = parent
            else:
                tentative_g = normal_g
                path_source = current

            if neighbor not in g_score or tentative_g < g_score[neighbor]:
                came_from[neighbor] = path_source
                g_score[neighbor] = tentative_g
                f_score = tentative_g + heuristic_weight * euclidean_dist(neighbor, goal_grid)
                counter += 1
                heappush(open_set, (f_score, counter, neighbor))

    return None  # No path found


def _astar_search_3d(
    start: RouteNode3D,
    goal: RouteNode3D,
    grids: dict[str, OccupancyGrid],
    via_cost: float = 10.0,
    via_diameter: float = 0.6,
    clearance: float = 0.2,
    net_id: int = 0,
) -> tuple[list[RouteNode3D], list[tuple[int, int]]] | None:
    """
    3D A* search with layer transitions (via insertion).

    Via insertion is a valid move with associated cost. This allows
    routing to escape congestion by switching layers.

    After path is found, vias are blocked on ALL layers they span.

    Args:
        start: Start node (x, y, layer)
        goal: Goal node (x, y, layer)
        grids: Dictionary of OccupancyGrid per layer
        via_cost: Cost multiplier for layer transitions (default 10x step)
        via_diameter: Via annular ring diameter in mm
        clearance: Via clearance in mm
        net_id: Net ID for blocking

    Returns:
        (path, via_positions) or None if no path found
        - path: List of RouteNode3D
        - via_positions: List of (x, y) where layer changes occur
    """
    from heapq import heappop, heappush

    # Validate layers exist
    if start.layer not in grids or goal.layer not in grids:
        return None

    # Available layers for transitions (dynamic from grids)
    # Prefer standard PCB layer order if possible
    standard_order = ["F.Cu", "In1.Cu", "In2.Cu", "B.Cu"]
    available_layers = [l for l in standard_order if l in grids]
    # Add any non-standard layers from grids
    for layer in grids.keys():
        if layer not in available_layers:
            available_layers.append(layer)

    # A* frontier: (priority, node)
    frontier = []
    heappush(frontier, (0, (start.x, start.y, start.layer)))

    # Tracking
    came_from: dict[tuple[int, int, str], tuple[int, int, str] | None] = {
        (start.x, start.y, start.layer): None
    }
    cost_so_far: dict[tuple[int, int, str], float] = {(start.x, start.y, start.layer): 0}

    goal_key = (goal.x, goal.y, goal.layer)

    while frontier:
        _, current_key = heappop(frontier)
        x, y, layer = current_key

        if current_key == goal_key:
            # Reconstruct path and find via positions
            path = []
            vias = []
            current = current_key
            prev_layer = None

            while current is not None:
                cx, cy, cl = current
                path.append(RouteNode3D(cx, cy, cl))

                # Detect layer transition
                if prev_layer is not None and prev_layer != cl:
                    vias.append((cx, cy))
                prev_layer = cl

                current = came_from[current]

            # Block vias on ALL layers (they span the full stackup)
            if vias and net_id > 0:
                sample_grid = next(iter(grids.values()))
                for via_gx, via_gy in vias:
                    via_wx, via_wy = sample_grid.grid_to_world(via_gx, via_gy)
                    for layer_grid in grids.values():
                        layer_grid.mark_via_blocked(via_wx, via_wy, via_diameter, clearance, net_id)

            return list(reversed(path)), vias

        grid = grids[layer]

        # Generate neighbors: 8-direction moves + layer transitions
        moves = []

        # Same-layer moves (8-connected)
        for dx, dy in [(1, 0), (0, 1), (-1, 0), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)]:
            nx, ny = x + dx, y + dy
            # Use differential-pair-aware free check if net_id available
            if net_id > 0:
                if grid.is_free_for_net(nx, ny, net_id):
                    move_cost = 1.414 if dx != 0 and dy != 0 else 1.0
                    moves.append(((nx, ny, layer), move_cost))
            else:
                if grid.is_free(nx, ny):
                    move_cost = 1.414 if dx != 0 and dy != 0 else 1.0
                    moves.append(((nx, ny, layer), move_cost))

        # Layer transition moves (via insertion)
        for other_layer in available_layers:
            if other_layer != layer:
                other_grid = grids[other_layer]
                # Can place via if current cell is free on other layer
                if net_id > 0:
                    if other_grid.is_free_for_net(x, y, net_id):
                        # Via cost discourages excessive transitions
                        moves.append(((x, y, other_layer), via_cost))
                else:
                    if other_grid.is_free(x, y):
                        # Via cost discourages excessive transitions
                        moves.append(((x, y, other_layer), via_cost))

        for neighbor_key, move_cost in moves:
            new_cost = cost_so_far[current_key] + move_cost

            if neighbor_key not in cost_so_far or new_cost < cost_so_far[neighbor_key]:
                cost_so_far[neighbor_key] = new_cost
                # Heuristic: 2D distance to goal
                heuristic = _heuristic((neighbor_key[0], neighbor_key[1]), (goal.x, goal.y))
                # Add layer mismatch penalty
                if neighbor_key[2] != goal.layer:
                    heuristic += via_cost  # Will need at least one more via

                priority = new_cost + heuristic
                heappush(frontier, (priority, neighbor_key))
                came_from[neighbor_key] = current_key

    return None  # No path found


def _route_segment_3d(
    start_world: tuple[float, float],
    goal_world: tuple[float, float],
    start_layer: str,
    goal_layer: str,
    grids: dict[str, OccupancyGrid],
    via_cost: float = 10.0,
) -> tuple[list[tuple[float, float, str]], list[tuple[float, float]]] | None:
    """
    Route a single segment using 3D A* with via insertion.

    IMPORTANT: Preserves exact start/goal positions (pad centers) in the final path.
    Only the bulk routing happens on-grid; fanout to pads is off-grid.

    Args:
        start_world: Start position in mm (x, y) - exact pad center
        goal_world: Goal position in mm (x, y) - exact pad center
        start_layer: Starting layer name
        goal_layer: Goal layer name
        grids: Dictionary of OccupancyGrid per layer
        via_cost: Cost for layer transitions

    Returns:
        (world_path, via_positions) or None
        - world_path: List of (x, y, layer) in ABSOLUTE board coordinates
        - via_positions: List of (x, y) where vias are placed
    """
    if not grids:
        return None

    # Get a grid for coordinate conversion
    sample_grid = next(iter(grids.values()))

    # Find nearest grid cells to start/goal (for bulk routing)
    start_grid = sample_grid.world_to_grid(start_world[0], start_world[1])
    goal_grid = sample_grid.world_to_grid(goal_world[0], goal_world[1])

    # Bounds check
    for layer, grid in grids.items():
        if not (0 <= start_grid[0] < grid.width_cells and 0 <= start_grid[1] < grid.height_cells):
            continue
        if not (0 <= goal_grid[0] < grid.width_cells and 0 <= goal_grid[1] < grid.height_cells):
            continue

    start_node = RouteNode3D(start_grid[0], start_grid[1], start_layer)
    goal_node = RouteNode3D(goal_grid[0], goal_grid[1], goal_layer)

    result = _astar_search_3d(start_node, goal_node, grids, via_cost)

    if result is None:
        return None

    path_nodes, via_grid_positions = result

    # Convert bulk path to world coordinates (grid-to-world conversion)
    bulk_path = []
    for node in path_nodes:
        grid = grids[node.layer]
        world_x, world_y = grid.grid_to_world(node.x, node.y)
        bulk_path.append((world_x, world_y, node.layer))

    # **KEY FIX**: Replace first and last points with exact pad positions
    # This ensures routes connect directly to pad centers, not grid-snapped approximations
    world_path = []

    if len(bulk_path) > 0:
        # Start with exact pad center
        world_path.append((start_world[0], start_world[1], start_layer))

        # Add bulk path (excluding first and last if they're the same as pads)
        # Keep middle segments
        if len(bulk_path) > 2:
            world_path.extend(bulk_path[1:-1])

        # End with exact pad center (if different from start)
        if len(bulk_path) == 1:
            # Single-cell path: just start and end at pads
            if (start_world[0], start_world[1]) != (goal_world[0], goal_world[1]):
                world_path.append((goal_world[0], goal_world[1], goal_layer))
        else:
            world_path.append((goal_world[0], goal_world[1], goal_layer))

    via_world_positions = []
    for gx, gy in via_grid_positions:
        wx, wy = sample_grid.grid_to_world(gx, gy)
        via_world_positions.append((wx, wy))

    return world_path, via_world_positions


def _mark_route_blocked(
    route_path: RoutePath | RoutePath3D,
    grids: dict[str, OccupancyGrid],
    trace_width: float,
    clearance: float,
    net_id: int,
) -> None:
    """Mark a path blocked on its respective layer grids."""
    if isinstance(route_path, RoutePath3D):
        # Mark each segment on its specific layer
        for i in range(len(route_path.segments) - 1):
            p1 = route_path.segments[i]
            p2 = route_path.segments[i + 1]

            # Use layer from segment if it matches, otherwise fallback
            layer = p1[2]
            if layer in grids:
                grids[layer].mark_segment_blocked(
                    (p1[0], p1[1]), (p2[0], p2[1]), trace_width, clearance, net_id
                )

        # Mark vias on ALL layers (assuming they span the stackup for now)
        for vx, vy in route_path.via_positions:
            for grid in grids.values():
                grid.mark_via_blocked(vx, vy, 0.6, clearance, net_id)  # 0.6mm via dia
    else:
        # Legacy single-layer behavior
        if route_path.layer_name in grids:
            grids[route_path.layer_name].mark_path_blocked(
                route_path.coordinates, trace_width, clearance, net_id
            )


def _unmark_route_blocked(
    route_path: RoutePath | RoutePath3D,
    grids: dict[str, OccupancyGrid],
    trace_width: float,
    clearance: float,
    net_id: int,
) -> None:
    """Unmark a path from its respective layer grids."""
    if isinstance(route_path, RoutePath3D):
        for i in range(len(route_path.segments) - 1):
            p1 = route_path.segments[i]
            p2 = route_path.segments[i + 1]
            layer = p1[2]
            if layer in grids:
                grids[layer].unmark_segment_blocked(
                    (p1[0], p1[1]), (p2[0], p2[1]), trace_width, clearance, net_id
                )

        # Unmark vias from all layers
        # (Assuming mark_via_blocked simply overwrites cells,
        # so we rely on net_id check inside unmark_point)
        for vx, vy in route_path.via_positions:
            for grid in grids.values():
                grid.unmark_path([(vx, vy), (vx, vy)], 0.6, clearance, net_id)
    else:
        if route_path.layer_name in grids:
            grids[route_path.layer_name].unmark_path(
                route_path.coordinates, trace_width, clearance, net_id
            )
