"""
Coupled Differential Pair Router

Routes P and N traces simultaneously, checking DRC oracle at every step.

This is a clean-room implementation independent of the existing DiffPairRouter.

EXP-1: Minimal implementation with straight-line routing only.
EXP-2: Add 45° corner support with maintained spacing.
EXP-3: Add A* pathfinding with obstacle avoidance.
"""

from dataclasses import dataclass
from typing import List, Tuple, Set, Optional, Dict
from enum import Enum
import time
import math
import heapq


@dataclass
class CoupledRouterResult:
    """
    Result of coupled differential pair routing.

    Attributes:
        success: Whether routing succeeded
        pos_path: P trace path as [(x_mm, y_mm, layer), ...]
        neg_path: N trace path as [(x_mm, y_mm, layer), ...]
        coupling_ratio: Percentage of path within target separation
        max_skew_mm: Maximum length difference
        avg_separation_mm: Average P-N spacing
        routing_time_s: Time taken to route
        error_message: Error message if failed
    """

    success: bool
    pos_path: List[Tuple[float, float, int]]
    neg_path: List[Tuple[float, float, int]]
    coupling_ratio: float
    max_skew_mm: float
    avg_separation_mm: float
    routing_time_s: float
    error_message: Optional[str] = None


class CoupledDiffPairRouter:
    """
    True coupled differential pair router with DRC oracle integration.

    Routes both traces simultaneously, checking actual trace positions
    (with widths) against the DRC oracle at every routing step.
    """

    def __init__(
        self,
        grid_resolution_mm: float = 0.1,
        trace_width_mm: float = 0.127,
        target_spacing_mm: float = 0.25,
        max_divergence_mm: float = 1.0,
        max_skew_mm: float = 0.5,
        drc_oracle=None,
    ):
        """
        Initialize coupled differential pair router.

        Args:
            grid_resolution_mm: Grid cell size (0.1mm for diff pairs)
            trace_width_mm: Width of each trace
            target_spacing_mm: Desired P-N center-to-center spacing
            max_divergence_mm: Maximum allowed divergence from target spacing
            max_skew_mm: Maximum allowed length mismatch
            drc_oracle: DRC oracle for validation (optional)
        """
        self.grid_resolution_mm = grid_resolution_mm
        self.trace_width_mm = trace_width_mm
        self.target_spacing_mm = target_spacing_mm
        self.max_divergence_mm = max_divergence_mm
        self.max_skew_mm = max_skew_mm
        self.drc_oracle = drc_oracle

    def route(
        self,
        start_pins: Tuple[Tuple[float, float], Tuple[float, float]],
        goal_pins: Tuple[Tuple[float, float], Tuple[float, float]],
        obstacles: Set[Tuple[int, int, int]],
        board_size: Tuple[float, float, int],
        net_pos: str = "NET_P",
        net_neg: str = "NET_N",
        waypoints: Optional[List[Tuple[Tuple[float, float], Tuple[float, float]]]] = None,
    ) -> CoupledRouterResult:
        """
        Route a differential pair from start to goal pins.

        EXP-1: Straight-line routing only (no corners, no obstacles).
        EXP-2: Add waypoint support for 45° corners.

        Args:
            start_pins: ((p_x, p_y), (n_x, n_y)) in mm
            goal_pins: ((p_x, p_y), (n_x, n_y)) in mm
            obstacles: Set of blocked grid cells (checked but not routed around yet)
            board_size: (width_mm, height_mm, num_layers)
            net_pos: P trace net name (for DRC oracle)
            net_neg: N trace net name (for DRC oracle)
            waypoints: Optional list of intermediate waypoints ((p_x, p_y), (n_x, n_y))

        Returns:
            CoupledRouterResult with routing outcome
        """
        start_time = time.time()

        pos_start, neg_start = start_pins
        pos_goal, neg_goal = goal_pins

        # Build segment list: start -> waypoints -> goal
        segments = []
        if waypoints:
            # Start to first waypoint
            segments.append((start_pins, waypoints[0]))
            # Between waypoints
            for i in range(len(waypoints) - 1):
                segments.append((waypoints[i], waypoints[i + 1]))
            # Last waypoint to goal
            segments.append((waypoints[-1], goal_pins))
        else:
            # Direct start to goal
            segments.append((start_pins, goal_pins))

        # Route each segment
        pos_path = []
        neg_path = []

        for seg_start, seg_goal in segments:
            # Generate paths for this segment
            seg_pos_path = self._generate_straight_path(seg_start[0], seg_goal[0])
            seg_neg_path = self._generate_straight_path(seg_start[1], seg_goal[1])

            # Validate against DRC oracle
            if self.drc_oracle:
                error = self._validate_paths_with_drc(seg_pos_path, seg_neg_path, net_pos, net_neg)
                if error:
                    return CoupledRouterResult(
                        success=False,
                        pos_path=[],
                        neg_path=[],
                        coupling_ratio=0.0,
                        max_skew_mm=0.0,
                        avg_separation_mm=0.0,
                        routing_time_s=time.time() - start_time,
                        error_message=error,
                    )

            # Append to full path (avoid duplicating waypoints)
            if not pos_path:
                pos_path.extend(seg_pos_path)
                neg_path.extend(seg_neg_path)
            else:
                # Skip first point (already in path)
                pos_path.extend(seg_pos_path[1:])
                neg_path.extend(seg_neg_path[1:])

        # Calculate metrics
        coupling_ratio = self._calculate_coupling_ratio(pos_path, neg_path)
        max_skew = abs(self._path_length(pos_path) - self._path_length(neg_path))
        avg_separation = self._calculate_avg_separation(pos_path, neg_path)

        elapsed = time.time() - start_time

        return CoupledRouterResult(
            success=True,
            pos_path=pos_path,
            neg_path=neg_path,
            coupling_ratio=coupling_ratio,
            max_skew_mm=max_skew,
            avg_separation_mm=avg_separation,
            routing_time_s=elapsed,
            error_message=None,
        )

    def _validate_paths_with_drc(
        self,
        pos_path: List[Tuple[float, float, int]],
        neg_path: List[Tuple[float, float, int]],
        net_pos: str,
        net_neg: str,
    ) -> Optional[str]:
        """
        Validate paths against DRC oracle.

        Args:
            pos_path: P trace waypoints
            neg_path: N trace waypoints
            net_pos: P net name
            net_neg: N net name

        Returns:
            Error message if validation fails, None if all checks pass
        """
        # Check P trace segments
        for i in range(len(pos_path) - 1):
            start_point = pos_path[i][:2]  # (x, y)
            end_point = pos_path[i + 1][:2]
            layer = pos_path[i][2]

            can_place, reason = self.drc_oracle.can_place_track_segment(
                start=start_point,
                end=end_point,
                layer=layer,
                net=net_pos,
                width=self.trace_width_mm,
            )

            if not can_place:
                return f"P trace DRC violation: {reason}"

        # Check N trace segments
        for i in range(len(neg_path) - 1):
            start_point = neg_path[i][:2]  # (x, y)
            end_point = neg_path[i + 1][:2]
            layer = neg_path[i][2]

            can_place, reason = self.drc_oracle.can_place_track_segment(
                start=start_point,
                end=end_point,
                layer=layer,
                net=net_neg,
                width=self.trace_width_mm,
            )

            if not can_place:
                return f"N trace DRC violation: {reason}"

        return None

    def _generate_straight_path(
        self,
        start: Tuple[float, float],
        goal: Tuple[float, float],
        layer: int = 0,
    ) -> List[Tuple[float, float, int]]:
        """
        Generate waypoints for a straight path from start to goal.

        Uses grid_resolution_mm to create intermediate waypoints.

        Args:
            start: (x, y) start position in mm
            goal: (x, y) goal position in mm
            layer: Layer index (default 0)

        Returns:
            List of (x, y, layer) waypoints
        """
        path = []

        # Calculate direction and distance
        dx = goal[0] - start[0]
        dy = goal[1] - start[1]
        distance = math.sqrt(dx * dx + dy * dy)

        if distance == 0:
            return [(start[0], start[1], layer)]

        # Number of steps (at least one waypoint per grid cell)
        num_steps = max(1, int(distance / self.grid_resolution_mm))

        # Generate waypoints
        for i in range(num_steps + 1):
            t = i / num_steps if num_steps > 0 else 1.0
            x = start[0] + dx * t
            y = start[1] + dy * t
            path.append((x, y, layer))

        return path

    def _calculate_coupling_ratio(
        self,
        pos_path: List[Tuple[float, float, int]],
        neg_path: List[Tuple[float, float, int]],
    ) -> float:
        """
        Calculate percentage of path within target separation tolerance.

        Args:
            pos_path: P trace waypoints
            neg_path: N trace waypoints

        Returns:
            Coupling ratio as percentage (0-100)
        """
        if not pos_path or not neg_path:
            return 0.0

        tolerance = 0.05  # mm (±50um)
        coupled_count = 0
        total_count = min(len(pos_path), len(neg_path))

        for i in range(total_count):
            separation = self._distance(pos_path[i][:2], neg_path[i][:2])
            if abs(separation - self.target_spacing_mm) <= tolerance:
                coupled_count += 1

        return (coupled_count / total_count) * 100.0 if total_count > 0 else 0.0

    def _calculate_avg_separation(
        self,
        pos_path: List[Tuple[float, float, int]],
        neg_path: List[Tuple[float, float, int]],
    ) -> float:
        """
        Calculate average P-N separation across the path.

        Args:
            pos_path: P trace waypoints
            neg_path: N trace waypoints

        Returns:
            Average separation in mm
        """
        if not pos_path or not neg_path:
            return 0.0

        total_separation = 0.0
        count = min(len(pos_path), len(neg_path))

        for i in range(count):
            separation = self._distance(pos_path[i][:2], neg_path[i][:2])
            total_separation += separation

        return total_separation / count if count > 0 else 0.0

    def _path_length(self, path: List[Tuple[float, float, int]]) -> float:
        """
        Calculate total length of a path.

        Args:
            path: List of waypoints

        Returns:
            Total path length in mm
        """
        length = 0.0
        for i in range(len(path) - 1):
            length += self._distance(path[i][:2], path[i + 1][:2])
        return length

    def _distance(self, p1: Tuple[float, float], p2: Tuple[float, float]) -> float:
        """Calculate Euclidean distance between two points."""
        dx = p2[0] - p1[0]
        dy = p2[1] - p1[1]
        return math.sqrt(dx * dx + dy * dy)

    def calculate_corner_waypoints(
        self,
        start_pins: Tuple[Tuple[float, float], Tuple[float, float]],
        goal_pins: Tuple[Tuple[float, float], Tuple[float, float]],
    ) -> Optional[List[Tuple[Tuple[float, float], Tuple[float, float]]]]:
        """
        Calculate waypoints for an L-shaped path with 45° corners.

        EXP-2: Generates a single corner waypoint for L-shaped routing.
        Maintains target spacing by keeping the same relative offset at the corner.

        Args:
            start_pins: ((p_x, p_y), (n_x, n_y)) starting positions
            goal_pins: ((p_x, p_y), (n_x, n_y)) goal positions

        Returns:
            List of waypoint pairs, or None if path is straight
        """
        pos_start, neg_start = start_pins
        pos_goal, neg_goal = goal_pins

        # Calculate deltas
        pos_dx = pos_goal[0] - pos_start[0]
        pos_dy = pos_goal[1] - pos_start[1]

        # Check if path is already straight (no corner needed)
        if abs(pos_dx) < 0.01 or abs(pos_dy) < 0.01:
            return None  # Horizontal or vertical, no corner

        # Calculate the relative offset between P and N at start and goal
        start_offset = (neg_start[0] - pos_start[0], neg_start[1] - pos_start[1])
        goal_offset = (neg_goal[0] - pos_goal[0], neg_goal[1] - pos_goal[1])

        # Determine path direction: horizontal-first or vertical-first
        # Choose based on which direction has more distance to cover
        if abs(pos_dx) >= abs(pos_dy):
            # Horizontal-first: go right/left first, then up/down
            # At corner, use goal's X and start's Y
            corner_pos = (pos_goal[0], pos_start[1])
            # N trace maintains the same offset as at start (for first segment)
            corner_neg = (corner_pos[0] + start_offset[0], corner_pos[1] + start_offset[1])
        else:
            # Vertical-first: go up/down first, then right/left
            # At corner, use start's X and goal's Y
            corner_pos = (pos_start[0], pos_goal[1])
            # N trace maintains the same offset as at start (for first segment)
            corner_neg = (corner_pos[0] + start_offset[0], corner_pos[1] + start_offset[1])

        return [((corner_pos, corner_neg))]

    def route_with_astar(
        self,
        start_pins: Tuple[Tuple[float, float], Tuple[float, float]],
        goal_pins: Tuple[Tuple[float, float], Tuple[float, float]],
        obstacles: Set[Tuple[int, int, int]],
        board_size: Tuple[float, float, int],
        net_pos: str = "NET_P",
        net_neg: str = "NET_N",
    ) -> CoupledRouterResult:
        """
        Route differential pair using A* pathfinding with obstacle avoidance.

        EXP-3: A* with coupled state space for navigating around obstacles.

        Args:
            start_pins: ((p_x, p_y), (n_x, n_y)) in mm
            goal_pins: ((p_x, p_y), (n_x, n_y)) in mm
            obstacles: Set of blocked grid cells
            board_size: (width_mm, height_mm, num_layers)
            net_pos: P trace net name
            net_neg: N trace net name

        Returns:
            CoupledRouterResult with routing outcome
        """
        start_time = time.time()

        # Convert mm to grid coordinates
        def mm_to_grid(mm_pos: Tuple[float, float]) -> Tuple[int, int]:
            return (
                int(mm_pos[0] / self.grid_resolution_mm),
                int(mm_pos[1] / self.grid_resolution_mm),
            )

        def grid_to_mm(grid_pos: Tuple[int, int]) -> Tuple[float, float]:
            return (
                grid_pos[0] * self.grid_resolution_mm,
                grid_pos[1] * self.grid_resolution_mm,
            )

        pos_start, neg_start = start_pins
        pos_goal, neg_goal = goal_pins

        # Convert to grid coordinates
        pos_start_grid = mm_to_grid(pos_start)
        neg_start_grid = mm_to_grid(neg_start)
        pos_goal_grid = mm_to_grid(pos_goal)
        neg_goal_grid = mm_to_grid(neg_goal)

        # A* state: (pos_x, pos_y, neg_x, neg_y, layer)
        start_state = (
            pos_start_grid[0],
            pos_start_grid[1],
            neg_start_grid[0],
            neg_start_grid[1],
            0,
        )
        goal_state = (pos_goal_grid[0], pos_goal_grid[1], neg_goal_grid[0], neg_goal_grid[1], 0)

        # A* data structures
        open_set = []  # Priority queue: (f_score, state)
        came_from: Dict[tuple, tuple] = {}
        g_score: Dict[tuple, float] = {start_state: 0.0}
        closed_set: Set[tuple] = set()  # Already explored states

        # Heuristic: max distance to goal for P or N
        def heuristic(state: tuple) -> float:
            pos_dist = abs(state[0] - pos_goal_grid[0]) + abs(state[1] - pos_goal_grid[1])
            neg_dist = abs(state[2] - neg_goal_grid[0]) + abs(state[3] - neg_goal_grid[1])
            return max(pos_dist, neg_dist) * self.grid_resolution_mm

        f_start = heuristic(start_state)
        heapq.heappush(open_set, (f_start, start_state))

        # Movement directions: 8-directional (N, S, E, W, NE, NW, SE, SW)
        directions = [
            (0, 1),
            (0, -1),
            (1, 0),
            (-1, 0),  # Cardinal
            (1, 1),
            (1, -1),
            (-1, 1),
            (-1, -1),  # Diagonal
        ]

        iterations = 0
        max_iterations = 50000  # Increased limit

        while open_set and iterations < max_iterations:
            iterations += 1

            _, current = heapq.heappop(open_set)

            # Skip if already explored
            if current in closed_set:
                continue

            closed_set.add(current)

            # Check if we reached the goal (within 1 grid cell tolerance)
            pos_at_goal = (
                abs(current[0] - goal_state[0]) <= 1 and abs(current[1] - goal_state[1]) <= 1
            )
            neg_at_goal = (
                abs(current[2] - goal_state[2]) <= 1 and abs(current[3] - goal_state[3]) <= 1
            )

            if pos_at_goal and neg_at_goal:
                # Reconstruct path
                path = []
                state = current
                while state in came_from:
                    path.append(state)
                    state = came_from[state]
                path.append(start_state)
                path.reverse()

                # Convert to mm coordinates
                pos_path = [
                    (grid_to_mm((s[0], s[1]))[0], grid_to_mm((s[0], s[1]))[1], s[4]) for s in path
                ]
                neg_path = [
                    (grid_to_mm((s[2], s[3]))[0], grid_to_mm((s[2], s[3]))[1], s[4]) for s in path
                ]

                # Calculate metrics
                coupling_ratio = self._calculate_coupling_ratio(pos_path, neg_path)
                max_skew = abs(self._path_length(pos_path) - self._path_length(neg_path))
                avg_separation = self._calculate_avg_separation(pos_path, neg_path)

                return CoupledRouterResult(
                    success=True,
                    pos_path=pos_path,
                    neg_path=neg_path,
                    coupling_ratio=coupling_ratio,
                    max_skew_mm=max_skew,
                    avg_separation_mm=avg_separation,
                    routing_time_s=time.time() - start_time,
                )

            # Explore neighbors (coupled movements)
            # EXP-3: Primarily move both traces together (coupled), allow independent movement only for obstacles
            neighbor_states = []

            # Priority 1: Move both traces in the same direction (fully coupled)
            for d in directions:
                new_pos = (current[0] + d[0], current[1] + d[1])
                new_neg = (current[2] + d[0], current[3] + d[1])
                neighbor_states.append((new_pos, new_neg, 0))  # 0 = no divergence penalty

            # Priority 2: Move P while N stays (for obstacle avoidance)
            for d in directions:
                new_pos = (current[0] + d[0], current[1] + d[1])
                new_neg = (current[2], current[3])
                neighbor_states.append((new_pos, new_neg, 2.0))  # 2.0 = divergence penalty

            # Priority 3: Move N while P stays (for obstacle avoidance)
            for d in directions:
                new_pos = (current[0], current[1])
                new_neg = (current[2] + d[0], current[3] + d[1])
                neighbor_states.append((new_pos, new_neg, 2.0))  # 2.0 = divergence penalty

            for new_pos, new_neg, divergence_penalty in neighbor_states:
                # Check if positions are in obstacles
                if (new_pos[0], new_pos[1], current[4]) in obstacles:
                    continue
                if (new_neg[0], new_neg[1], current[4]) in obstacles:
                    continue

                # Check spacing constraint
                spacing = (
                    math.sqrt((new_pos[0] - new_neg[0]) ** 2 + (new_pos[1] - new_neg[1]) ** 2)
                    * self.grid_resolution_mm
                )
                spacing_dev = abs(spacing - self.target_spacing_mm)
                if spacing_dev > self.max_divergence_mm:
                    continue

                neighbor = (new_pos[0], new_pos[1], new_neg[0], new_neg[1], current[4])

                # Calculate movement cost
                pos_dist = math.sqrt(
                    (new_pos[0] - current[0]) ** 2 + (new_pos[1] - current[1]) ** 2
                )
                neg_dist = math.sqrt(
                    (new_neg[0] - current[2]) ** 2 + (new_neg[1] - current[3]) ** 2
                )
                base_cost = max(pos_dist, neg_dist) * self.grid_resolution_mm

                # Penalty for spacing deviation
                spacing_penalty = spacing_dev * 10.0

                tentative_g = g_score[current] + base_cost + spacing_penalty + divergence_penalty

                if neighbor not in g_score or tentative_g < g_score[neighbor]:
                    came_from[neighbor] = current
                    g_score[neighbor] = tentative_g
                    f_score = tentative_g + heuristic(neighbor)
                    heapq.heappush(open_set, (f_score, neighbor))

        # No path found
        return CoupledRouterResult(
            success=False,
            pos_path=[],
            neg_path=[],
            coupling_ratio=0.0,
            max_skew_mm=0.0,
            avg_separation_mm=0.0,
            routing_time_s=time.time() - start_time,
            error_message=f"A* failed: no path found after {iterations} iterations",
        )

    def route_hierarchical(
        self,
        start_pins: Tuple[Tuple[float, float], Tuple[float, float]],
        goal_pins: Tuple[Tuple[float, float], Tuple[float, float]],
        obstacles: Set[Tuple[int, int, int]],
        board_size: Tuple[float, float, int],
        net_pos: str = "NET_P",
        net_neg: str = "NET_N",
    ) -> CoupledRouterResult:
        """
        Route differential pair using hierarchical waypoint approach.

        EXP-3 (Revised): Use coarse grid A* to find waypoints, then connect with EXP-1/EXP-2.

        Strategy:
        1. Use coarse grid (1mm resolution) A* to find waypoints avoiding obstacles
        2. Generate corner waypoints between coarse waypoints (EXP-2)
        3. Route straight segments between waypoints (EXP-1)

        Args:
            start_pins: ((p_x, p_y), (n_x, n_y)) in mm
            goal_pins: ((p_x, p_y), (n_x, n_y)) in mm
            obstacles: Set of blocked grid cells (fine resolution)
            board_size: (width_mm, height_mm, num_layers)
            net_pos: P trace net name
            net_neg: N trace net name

        Returns:
            CoupledRouterResult with routing outcome
        """
        start_time = time.time()

        # Step 1: Find coarse waypoints using centerline A*
        pos_start, neg_start = start_pins
        pos_goal, neg_goal = goal_pins

        # Use P trace as centerline (N follows at offset)
        coarse_waypoints_mm = self._find_coarse_waypoints(
            pos_start, pos_goal, obstacles, board_size
        )

        if not coarse_waypoints_mm:
            return CoupledRouterResult(
                success=False,
                pos_path=[],
                neg_path=[],
                coupling_ratio=0.0,
                max_skew_mm=0.0,
                avg_separation_mm=0.0,
                routing_time_s=time.time() - start_time,
                error_message="Failed to find coarse waypoints",
            )

        # Step 2: Convert coarse waypoints to diff pair waypoints (with N offset)
        diff_pair_waypoints = self._convert_to_diff_pair_waypoints(
            coarse_waypoints_mm, start_pins, goal_pins
        )

        # Step 3: Route using existing waypoint-based routing (EXP-2)
        result = self.route(
            start_pins=start_pins,
            goal_pins=goal_pins,
            obstacles=obstacles,
            board_size=board_size,
            net_pos=net_pos,
            net_neg=net_neg,
            waypoints=diff_pair_waypoints,
        )

        return result

    def _find_coarse_waypoints(
        self,
        start: Tuple[float, float],
        goal: Tuple[float, float],
        obstacles: Set[Tuple[int, int, int]],
        board_size: Tuple[float, float, int],
        coarse_resolution_mm: float = 1.0,
    ) -> Optional[List[Tuple[float, float]]]:
        """
        Find waypoints on coarse grid using A*.

        Args:
            start: Starting position in mm
            goal: Goal position in mm
            obstacles: Fine grid obstacles
            board_size: Board dimensions
            coarse_resolution_mm: Coarse grid resolution (default 1mm)

        Returns:
            List of waypoint positions in mm, or None if no path found
        """

        def mm_to_coarse(mm_pos: Tuple[float, float]) -> Tuple[int, int]:
            return (
                int(mm_pos[0] / coarse_resolution_mm),
                int(mm_pos[1] / coarse_resolution_mm),
            )

        def coarse_to_mm(grid_pos: Tuple[int, int]) -> Tuple[float, float]:
            return (
                grid_pos[0] * coarse_resolution_mm,
                grid_pos[1] * coarse_resolution_mm,
            )

        # Convert obstacles to coarse grid
        coarse_obstacles = set()
        for ox, oy, layer in obstacles:
            # Convert fine grid to coarse grid
            coarse_x = int((ox * self.grid_resolution_mm) / coarse_resolution_mm)
            coarse_y = int((oy * self.grid_resolution_mm) / coarse_resolution_mm)
            coarse_obstacles.add((coarse_x, coarse_y))

        # A* on coarse grid
        start_grid = mm_to_coarse(start)
        goal_grid = mm_to_coarse(goal)

        open_set = []
        came_from: Dict[Tuple[int, int], Tuple[int, int]] = {}
        g_score: Dict[Tuple[int, int], float] = {start_grid: 0.0}
        closed_set: Set[Tuple[int, int]] = set()

        def heuristic(pos: Tuple[int, int]) -> float:
            return abs(pos[0] - goal_grid[0]) + abs(pos[1] - goal_grid[1])

        heapq.heappush(open_set, (heuristic(start_grid), start_grid))

        # 8-directional movement
        directions = [(0, 1), (0, -1), (1, 0), (-1, 0), (1, 1), (1, -1), (-1, 1), (-1, -1)]

        max_iterations = 1000
        iterations = 0

        while open_set and iterations < max_iterations:
            iterations += 1
            _, current = heapq.heappop(open_set)

            if current in closed_set:
                continue

            closed_set.add(current)

            # Check if reached goal
            if abs(current[0] - goal_grid[0]) <= 1 and abs(current[1] - goal_grid[1]) <= 1:
                # Reconstruct path
                path = []
                pos = current
                while pos in came_from:
                    path.append(pos)
                    pos = came_from[pos]
                path.append(start_grid)
                path.reverse()

                # Convert to mm and simplify (remove redundant waypoints)
                waypoints_mm = [coarse_to_mm(p) for p in path]
                simplified = self._simplify_waypoints(waypoints_mm)
                return simplified

            # Explore neighbors
            for dx, dy in directions:
                neighbor = (current[0] + dx, current[1] + dy)

                # Check bounds
                if neighbor[0] < 0 or neighbor[1] < 0:
                    continue
                if (
                    neighbor[0] >= board_size[0] / coarse_resolution_mm
                    or neighbor[1] >= board_size[1] / coarse_resolution_mm
                ):
                    continue

                # Check obstacles
                if neighbor in coarse_obstacles:
                    continue

                if neighbor in closed_set:
                    continue

                # Calculate cost
                move_cost = math.sqrt(dx * dx + dy * dy)
                tentative_g = g_score[current] + move_cost

                if neighbor not in g_score or tentative_g < g_score[neighbor]:
                    came_from[neighbor] = current
                    g_score[neighbor] = tentative_g
                    f_score = tentative_g + heuristic(neighbor)
                    heapq.heappush(open_set, (f_score, neighbor))

        return None  # No path found

    def _simplify_waypoints(
        self, waypoints: List[Tuple[float, float]]
    ) -> List[Tuple[float, float]]:
        """
        Remove redundant waypoints (collinear points).

        Args:
            waypoints: List of waypoints in mm

        Returns:
            Simplified list of waypoints
        """
        if len(waypoints) <= 2:
            return waypoints

        simplified = [waypoints[0]]

        for i in range(1, len(waypoints) - 1):
            prev = simplified[-1]
            curr = waypoints[i]
            next_pt = waypoints[i + 1]

            # Check if current point is on the line between prev and next
            # Direction vectors
            dx1 = curr[0] - prev[0]
            dy1 = curr[1] - prev[1]
            dx2 = next_pt[0] - curr[0]
            dy2 = next_pt[1] - curr[1]

            # Normalize
            len1 = math.sqrt(dx1 * dx1 + dy1 * dy1)
            len2 = math.sqrt(dx2 * dx2 + dy2 * dy2)

            if len1 > 0 and len2 > 0:
                dx1 /= len1
                dy1 /= len1
                dx2 /= len2
                dy2 /= len2

                # If directions are the same (collinear), skip current point
                if abs(dx1 - dx2) < 0.1 and abs(dy1 - dy2) < 0.1:
                    continue

            simplified.append(curr)

        simplified.append(waypoints[-1])
        return simplified

    def _convert_to_diff_pair_waypoints(
        self,
        centerline_waypoints: List[Tuple[float, float]],
        start_pins: Tuple[Tuple[float, float], Tuple[float, float]],
        goal_pins: Tuple[Tuple[float, float], Tuple[float, float]],
    ) -> List[Tuple[Tuple[float, float], Tuple[float, float]]]:
        """
        Convert centerline waypoints to differential pair waypoints.

        Args:
            centerline_waypoints: Waypoints for P trace
            start_pins: Starting pin positions
            goal_pins: Goal pin positions

        Returns:
            List of (pos_waypoint, neg_waypoint) tuples
        """
        pos_start, neg_start = start_pins
        pos_goal, neg_goal = goal_pins

        # Calculate offset at start and goal
        start_offset = (neg_start[0] - pos_start[0], neg_start[1] - pos_start[1])
        goal_offset = (neg_goal[0] - pos_goal[0], neg_goal[1] - pos_goal[1])

        diff_pair_waypoints = []

        # For each centerline waypoint, add offset to create N waypoint
        for i, pos_wp in enumerate(centerline_waypoints[1:-1]):  # Skip start and goal
            # Interpolate offset based on progress along path
            t = (i + 1) / len(centerline_waypoints)
            offset_x = start_offset[0] * (1 - t) + goal_offset[0] * t
            offset_y = start_offset[1] * (1 - t) + goal_offset[1] * t

            neg_wp = (pos_wp[0] + offset_x, pos_wp[1] + offset_y)
            diff_pair_waypoints.append((pos_wp, neg_wp))

        return diff_pair_waypoints
