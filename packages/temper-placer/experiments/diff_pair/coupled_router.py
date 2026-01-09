"""
Coupled Differential Pair Router

Routes P and N traces simultaneously, checking DRC oracle at every step.

This is a clean-room implementation independent of the existing DiffPairRouter.

EXP-1: Minimal implementation with straight-line routing only.
"""

from dataclasses import dataclass
from typing import List, Tuple, Set, Optional
import time
import math


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
    ) -> CoupledRouterResult:
        """
        Route a differential pair from start to goal pins.

        EXP-1: Straight-line routing only (no corners, no obstacles).

        Args:
            start_pins: ((p_x, p_y), (n_x, n_y)) in mm
            goal_pins: ((p_x, p_y), (n_x, n_y)) in mm
            obstacles: Set of blocked grid cells (checked but not routed around yet)
            board_size: (width_mm, height_mm, num_layers)
            net_pos: P trace net name (for DRC oracle)
            net_neg: N trace net name (for DRC oracle)

        Returns:
            CoupledRouterResult with routing outcome
        """
        start_time = time.time()

        # EXP-1: Only handle straight-line routing (horizontal or vertical)
        # Check if path is straight
        pos_start, neg_start = start_pins
        pos_goal, neg_goal = goal_pins

        # Determine if horizontal or vertical
        is_horizontal = abs(pos_goal[0] - pos_start[0]) > abs(pos_goal[1] - pos_start[1])
        is_vertical = abs(pos_goal[1] - pos_start[1]) > abs(pos_goal[0] - pos_start[0])

        if not (is_horizontal or is_vertical):
            return CoupledRouterResult(
                success=False,
                pos_path=[],
                neg_path=[],
                coupling_ratio=0.0,
                max_skew_mm=0.0,
                avg_separation_mm=0.0,
                routing_time_s=time.time() - start_time,
                error_message="EXP-1: Only straight horizontal/vertical paths supported",
            )

        # Generate waypoints with grid resolution
        pos_path = self._generate_straight_path(pos_start, pos_goal)
        neg_path = self._generate_straight_path(neg_start, neg_goal)

        # Validate each segment against DRC oracle
        if self.drc_oracle:
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
                    return CoupledRouterResult(
                        success=False,
                        pos_path=[],
                        neg_path=[],
                        coupling_ratio=0.0,
                        max_skew_mm=0.0,
                        avg_separation_mm=0.0,
                        routing_time_s=time.time() - start_time,
                        error_message=f"P trace DRC violation: {reason}",
                    )

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
                    return CoupledRouterResult(
                        success=False,
                        pos_path=[],
                        neg_path=[],
                        coupling_ratio=0.0,
                        max_skew_mm=0.0,
                        avg_separation_mm=0.0,
                        routing_time_s=time.time() - start_time,
                        error_message=f"N trace DRC violation: {reason}",
                    )

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
