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


@dataclass
class RoutePath:
    """A routed path for a net."""

    net_name: str
    coordinates: list[tuple[float, float]]  # (x, y) path coordinates
    layer_name: str
    path_length: float  # Total length in mm

    @property
    def segment_count(self) -> int:
        """Number of segments in path."""
        return max(0, len(self.coordinates) - 1)


@dataclass
class PathfindingResult:
    """Result of A* pathfinding."""

    routed_paths: dict[str, RoutePath]  # net_name -> RoutePath
    failed_nets: list[str]  # Nets that failed to route

    @property
    def success_count(self) -> int:
        """Number of successfully routed nets."""
        return len(self.routed_paths)

    @property
    def failure_count(self) -> int:
        """Number of failed nets."""
        return len(self.failed_nets)

    def get_path(self, net_name: str) -> RoutePath | None:
        """Get routed path for a specific net."""
        return self.routed_paths.get(net_name)


def run_astar_pathfinding(
    channel_mapping: ChannelMapping,
    grid: OccupancyGrid,
    design_rules: DesignRules,
) -> PathfindingResult:
    """
    Run A* pathfinding to generate routing paths.

    Uses the channel mapping as guidance and the occupancy grid
    for obstacle avoidance to find actual geometric paths.

    Args:
        channel_mapping: Channel paths from Stage 4.1
        grid: Occupancy grid from Stage 2.5
        design_rules: PCB design rules for width/clearance

    Returns:
        PathfindingResult with routed paths
    """
    routed_paths = {}
    failed_nets = []

    # Sort nets by routing scheduling priority
    net_order = _compute_net_order(channel_mapping)

    for net_name in net_order:
        channel_path = channel_mapping.channel_paths.get(net_name)
        if not channel_path:
            continue
            
        # Try to route this net using A*
        route_path = _astar_route(net_name, channel_path, grid)

        if route_path:
            routed_paths[net_name] = route_path
            
            # KEY: Update grid to mark path as blocked for subsequent nets
            grid.mark_path_blocked(
                route_path.coordinates,
                trace_width=design_rules.default_trace_width_mm,
                clearance=design_rules.default_clearance_mm,
            )
        else:
            failed_nets.append(net_name)

    return PathfindingResult(
        routed_paths=routed_paths,
        failed_nets=failed_nets,
    )


def _compute_net_order(channel_mapping: ChannelMapping) -> list[str]:
    """
    Compute routing order for nets.
    
    Priority:
    1. Power/HV/Critical nets (inferred from name)
    2. Shortest paths first (easier to fit)
    """
    nets = list(channel_mapping.channel_paths.keys())
    
    def priority_key(net_name: str):
        path = channel_mapping.channel_paths[net_name]
        
        # Priority 1: Critical nets
        name_upper = net_name.upper()
        # "GND", "VCC", "5V", "3V3", "HV", "AC"
        is_power = any(x in name_upper for x in ["GND", "VCC", "HV", "AC_", "+"])
        
        # Priority 2: Length (shortest first)
        length = path.total_length
        
        # Tuple comparison: False < True, so use not is_power to put power first
        return (not is_power, length)
        
    return sorted(nets, key=priority_key)


def _astar_route(
    net_name: str,
    channel_path,
    grid: OccupancyGrid,
) -> RoutePath | None:
    """
    Route a single net using A* pathfinding.

    Args:
        net_name: Net to route
        channel_path: Channel path guidance
        grid: Occupancy grid

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
    
    for i in range(len(waypoints) - 1):
        start_world = waypoints[i]
        goal_world = waypoints[i + 1]
        
        # Convert world coordinates to grid coordinates
        start_grid = grid.world_to_grid(start_world[0], start_world[1])
        goal_grid = grid.world_to_grid(goal_world[0], goal_world[1])
        
        # Check if coordinates are within grid bounds
        start_valid = (0 <= start_grid[0] < grid.width_cells and 
                      0 <= start_grid[1] < grid.height_cells)
        goal_valid = (0 <= goal_grid[0] < grid.width_cells and 
                     0 <= goal_grid[1] < grid.height_cells)
        
        if not start_valid or not goal_valid:
            # Coordinates out of bounds, use direct line
            if i == 0:
                detailed_coords.append(start_world)
            detailed_coords.append(goal_world)
            continue
        
        # Run A* search between waypoints
        grid_path = _astar_search(start_grid, goal_grid, grid)
        
        if grid_path:
            # Convert grid path back to world coordinates
            for grid_cell in grid_path:
                world_coord = grid.grid_to_world(grid_cell[0], grid_cell[1])
                # Avoid duplicate coordinates
                if not detailed_coords or detailed_coords[-1] != world_coord:
                    detailed_coords.append(world_coord)
        else:
            # A* failed, fall back to direct line
            if i == 0:
                detailed_coords.append(start_world)
            detailed_coords.append(goal_world)
    
    # Ensure we have at least start and end
    if not detailed_coords:
        detailed_coords = waypoints

    # Calculate total path length
    path_length = 0.0
    for i in range(len(detailed_coords) - 1):
        x1, y1 = detailed_coords[i]
        x2, y2 = detailed_coords[i + 1]
        dx = x2 - x1
        dy = y2 - y1
        path_length += (dx**2 + dy**2)**0.5

    return RoutePath(
        net_name=net_name,
        coordinates=detailed_coords,
        layer_name=grid.layer_name,
        path_length=path_length,
    )


def _astar_search(
    start: tuple[int, int],
    goal: tuple[int, int],
    grid: OccupancyGrid,
) -> list[tuple[int, int]] | None:
    """
    A* search algorithm for pathfinding.

    Args:
        start: Start cell (x, y)
        goal: Goal cell (x, y)
        grid: Occupancy grid

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
        moves = [
            (1, 0), (0, 1), (-1, 0), (0, -1),
            (1, 1), (1, -1), (-1, 1), (-1, -1)
        ]
        
        for dx, dy in moves:
            neighbor = (x + dx, y + dy)

            # Check if neighbor is valid and free
            if not grid.is_free(neighbor[0], neighbor[1]):
                continue
            
            # Diagonal cost = 1.414, Cardinal = 1.0
            move_cost = 1.414 if dx != 0 and dy != 0 else 1.0
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
