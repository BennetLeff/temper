"""
Router V6 Stage 2.5: Build Occupancy Grid

Creates discretized routing grid for A* pathfinding.
Part of temper-8bj1 (Stage 2 - Channel Analysis)
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import numpy as np
from shapely import contains, points

from temper_placer.router_v6.routing_space import RoutingSpace


class CellState(Enum):
    """State of a grid cell."""

    FREE = 0  # Available for routing
    BLOCKED = 1  # Occupied by obstacle
    RESERVED = 2  # Reserved for specific net


@dataclass
class OccupancyGrid:
    """Discretized routing grid for pathfinding."""

    layer_name: str
    grid: np.ndarray  # 2D array of CellState values
    origin: tuple[float, float]  # (x, y) origin in mm
    cell_size: float  # Cell size in mm
    width_cells: int  # Grid width in cells
    height_cells: int  # Grid height in cells
    static_mask: np.ndarray | None = None  # Boolean mask of static obstacles (-1)

    # PathFinder Congestion Fields
    congestion_cost: np.ndarray | None = None  # Persistent history cost
    usage_count: np.ndarray | None = None  # Current iteration usage count
    negotiated_mode: bool = False  # If True, allow overlaps
    base_cost: float = 1.0  # Base traversal cost (higher = avoid this layer)

    # Differential Pair Support (Phase 2)
    net_id_to_name: dict[int, str] | None = None  # Maps net_id -> net_name
    design_rules: "DesignRules | None" = None  # For pair-aware clearance checking

    # Phase 2.1: Trace geometry for distance calculation
    # Maps net_id -> list of (p1, p2, trace_width) tuples
    trace_segments: dict[int, list[tuple[tuple[float, float], tuple[float, float], float]]] | None = None

    def __post_init__(self):
        # Initialize congestion arrays if not provided
        if self.congestion_cost is None:
            # Use float64 to prevent overflow/precision loss with exponential history
            self.congestion_cost = np.zeros((self.height_cells, self.width_cells), dtype=np.float64)
        if self.usage_count is None:
            self.usage_count = np.zeros((self.height_cells, self.width_cells), dtype=np.int16)
        if self.trace_segments is None:
            self.trace_segments = {}

    @property
    def width_mm(self) -> float:
        """Grid width in mm."""
        return self.width_cells * self.cell_size

    @property
    def height_mm(self) -> float:
        """Grid height in mm."""
        return self.height_cells * self.cell_size

    def is_free(self, x_cell: int, y_cell: int) -> bool:
        """Check if a cell is free for routing."""
        if 0 <= x_cell < self.width_cells and 0 <= y_cell < self.height_cells:
            val = self.grid[y_cell, x_cell]
            # In negotiated mode, allow overlap (usage > 0) but respect static obstacles (-1)
            if self.negotiated_mode:
                return val != -1
            # Normal mode: 0 is Free
            return val == 0
        return False

    def is_free_for_net(self, x_cell: int, y_cell: int, net_id: int) -> bool:
        """
        Check if a cell is free for a specific net (differential-pair-aware).

        For differential pairs, allows routing through cells occupied by pair mate
        if within the pair gap distance.

        Args:
            x_cell: X grid coordinate
            y_cell: Y grid coordinate
            net_id: Net ID attempting to route

        Returns:
            True if cell is routable for this net
        """
        if not (0 <= x_cell < self.width_cells and 0 <= y_cell < self.height_cells):
            return False

        cell_value = self.grid[y_cell, x_cell]

        # Static obstacle
        if cell_value == -1:
            return False

        # Free cell
        if cell_value == 0:
            return True

        # Own net
        if cell_value == net_id:
            return True

        # Negotiated mode: allow overlaps
        if self.negotiated_mode:
            return True

        # Occupied by different net - check if it's our differential pair mate
        if self.net_id_to_name and self.design_rules:
            current_net = self.net_id_to_name.get(net_id)
            blocking_net = self.net_id_to_name.get(cell_value)

            if current_net and blocking_net:
                is_pair, pair_gap = self.design_rules.are_differential_pair(current_net, blocking_net)

                if is_pair and pair_gap is not None:
                    # Phase 2.2: Edge-to-edge distance validation for differential pairs
                    # Calculate edge-to-edge distance accounting for trace widths
                    distance = self._distance_to_trace(x_cell, y_cell, cell_value, net_id)

                    # Allow routing only if edge-to-edge distance >= pair_gap
                    # This enforces minimum spacing between differential pair traces
                    return distance >= pair_gap

        # Blocked by other net
        return False

    def is_blocked(self, x_cell: int, y_cell: int) -> bool:
        """Check if a cell is blocked."""
        if 0 <= x_cell < self.width_cells and 0 <= y_cell < self.height_cells:
            # != 0 is blocked (either static or dynamic)
            return self.grid[y_cell, x_cell] != 0
        return False

    def check_clearance(self, x_cell: int, y_cell: int, current_net_id: int) -> float:
        """
        Get required clearance at this cell for the current net.

        For differential pairs, returns reduced clearance (pair_gap) between pair mates.
        For other nets, returns normal clearance from design rules.

        Args:
            x_cell: X grid coordinate
            y_cell: Y grid coordinate
            current_net_id: Net ID attempting to route through this cell

        Returns:
            Required clearance in mm (0.0 if cell is free)
        """
        # Check bounds
        if not (0 <= x_cell < self.width_cells and 0 <= y_cell < self.height_cells):
            return float("inf")  # Out of bounds

        # Check if cell is free
        blocking_net_id = self.grid[y_cell, x_cell]
        if blocking_net_id <= 0:
            return 0.0  # Free cell or static obstacle

        # If no net mapping or design rules, use default behavior
        if not self.net_id_to_name or not self.design_rules:
            # Fallback: return default clearance
            if self.design_rules:
                return self.design_rules.default_clearance_mm
            return 0.2  # Hardcoded fallback

        # Get net names
        current_net = self.net_id_to_name.get(current_net_id)
        blocking_net = self.net_id_to_name.get(blocking_net_id)

        if not current_net or not blocking_net:
            # Unknown net, use default clearance
            return self.design_rules.default_clearance_mm

        # Check if this is a differential pair
        is_pair, pair_gap = self.design_rules.are_differential_pair(current_net, blocking_net)

        if is_pair and pair_gap is not None:
            # Use pair gap for differential pair mate
            return pair_gap
        else:
            # Use normal clearance from blocking net's rules
            blocking_rules = self.design_rules.get_rules_for_net(blocking_net)
            return blocking_rules.clearance_mm

    def _distance_to_segment(
        self, px: float, py: float, p1: tuple[float, float], p2: tuple[float, float]
    ) -> float:
        """
        Calculate minimum distance from point (px, py) to line segment (p1, p2).

        Returns:
            Distance in mm from point to nearest point on segment
        """
        x1, y1 = p1
        x2, y2 = p2

        # Vector from p1 to p2
        dx = x2 - x1
        dy = y2 - y1

        # Length squared of segment
        length_sq = dx * dx + dy * dy

        if length_sq == 0:
            # Segment is a point
            return ((px - x1) ** 2 + (py - y1) ** 2) ** 0.5

        # Project point onto line (parametric t in [0, 1] for segment)
        t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / length_sq))

        # Nearest point on segment
        nearest_x = x1 + t * dx
        nearest_y = y1 + t * dy

        # Distance from point to nearest point on segment
        return ((px - nearest_x) ** 2 + (py - nearest_y) ** 2) ** 0.5

    def _distance_to_trace(self, x_cell: int, y_cell: int, blocking_net_id: int, current_net_id: int) -> float:
        """
        Calculate edge-to-edge distance from cell to nearest trace segment of given net.

        Phase 2.2: Accounts for trace widths to compute edge-to-edge distance instead of
        center-to-center distance.

        Args:
            x_cell: X grid coordinate
            y_cell: Y grid coordinate
            blocking_net_id: Net ID of the trace we're measuring distance to
            current_net_id: Net ID attempting to route (for determining its trace width)

        Returns:
            Edge-to-edge distance in mm from current net's trace edge to blocking net's trace edge
        """
        if not self.trace_segments or blocking_net_id not in self.trace_segments:
            return float("inf")

        # Convert cell to world coordinates (cell center)
        px = self.origin[0] + (x_cell + 0.5) * self.cell_size
        py = self.origin[1] + (y_cell + 0.5) * self.cell_size

        # Find minimum center-to-center distance to any segment of blocking net
        min_center_dist = float("inf")
        blocking_trace_width = 0.0

        for p1, p2, trace_width in self.trace_segments[blocking_net_id]:
            dist = self._distance_to_segment(px, py, p1, p2)
            if dist < min_center_dist:
                min_center_dist = dist
                blocking_trace_width = trace_width

        if min_center_dist == float("inf"):
            return float("inf")

        # Get current net's trace width
        current_trace_width = 0.0
        if self.design_rules and self.net_id_to_name:
            current_net_name = self.net_id_to_name.get(current_net_id)
            if current_net_name:
                rules = self.design_rules.get_rules_for_net(current_net_name)
                current_trace_width = rules.trace_width_mm

        # Convert center-to-center distance to edge-to-edge distance
        # Edge-to-edge = center-to-center - (width1/2 + width2/2)
        edge_to_edge_dist = min_center_dist - (blocking_trace_width / 2.0) - (current_trace_width / 2.0)

        return max(0.0, edge_to_edge_dist)  # Distance can't be negative

    def add_usage(self, x: int, y: int) -> None:
        """Increment usage count for a cell."""
        if 0 <= x < self.width_cells and 0 <= y < self.height_cells:
            if self.usage_count is not None:
                self.usage_count[y, x] += 1

    def remove_usage(self, x: int, y: int) -> None:
        """Decrement usage count for a cell."""
        if 0 <= x < self.width_cells and 0 <= y < self.height_cells:
            if self.usage_count is not None:
                self.usage_count[y, x] = max(0, self.usage_count[y, x] - 1)

    def update_history_cost(self, history_factor: float = 0.5) -> None:
        """
        Update persistent history cost based on current congestion.
        PathFinder Logic: h(n) = h(n) + usage(n) * h_fac if congested.
        """
        if self.congestion_cost is None or self.usage_count is None:
            return

        # Capacity is 1 (binary grid). Usage > 1 means congestion.
        # However, for variable width nets, usage is just a count.
        # If we allow sharing (during negotiation), any usage > 1 is bad?
        # Yes, standard PathFinder assumes capacity=1 per resource node.

        # Identify congested cells (usage > 1)
        congested_mask = self.usage_count > 1

        # Increase history cost
        # Vectorized update
        self.congestion_cost[congested_mask] += self.usage_count[congested_mask] * history_factor
        if np.any(congested_mask):
            print(
                f"DEBUG: Updated {np.sum(congested_mask)} congested cells. Max cost: {np.max(self.congestion_cost)}"
            )

    def get_cost(self, x: int, y: int, current_congestion_penalty: float = 1.0) -> float:
        """
        Get total cost of a cell for pathfinding.
        Cost = Base + (Usage * Penalty) + History
        """
        if not (0 <= x < self.width_cells and 0 <= y < self.height_cells):
            return float("inf")

        # Base cost (Layer Bias)
        cost = self.base_cost

        if self.usage_count is not None:
            usage = self.usage_count[y, x]
            cost += usage * current_congestion_penalty

        if self.congestion_cost is not None:
            cost += self.congestion_cost[y, x]

        return cost

    def world_to_grid(self, x_mm: float, y_mm: float) -> tuple[int, int]:
        """Convert world coordinates (mm) to grid coordinates."""
        x_cell = int((x_mm - self.origin[0]) / self.cell_size)
        y_cell = int((y_mm - self.origin[1]) / self.cell_size)
        return (x_cell, y_cell)

    def grid_to_world(self, x_cell: int, y_cell: int) -> tuple[float, float]:
        """Convert grid coordinates to world coordinates (mm)."""
        x_mm = self.origin[0] + (x_cell + 0.5) * self.cell_size
        y_mm = self.origin[1] + (y_cell + 0.5) * self.cell_size
        return (x_mm, y_mm)

    @property
    def free_cell_count(self) -> int:
        """Count of free cells."""
        return int(np.sum(self.grid == CellState.FREE.value))

    @property
    def blocked_cell_count(self) -> int:
        """Count of blocked cells."""
        return int(np.sum(self.grid == CellState.BLOCKED.value))

    @property
    def occupancy_ratio(self) -> float:
        """Ratio of blocked cells to total cells."""
        total = self.width_cells * self.height_cells
        return self.blocked_cell_count / total if total > 0 else 0.0

    def mark_path_blocked(
        self,
        path: list[tuple[float, float]],
        trace_width: float,
        clearance: float,
        net_id: int,
    ) -> None:
        """
        Mark cells occupied by a routed path (with clearance expansion).

        Args:
            path: List of (x, y) coordinates
            trace_width: Width of the trace in mm
            clearance: Required clearance in mm
            net_id: Unique positive integer ID for this net
        """
        # Calculate how many cells to block around center
        # Correct C-Space: width + clearance (accounts for both trace radii + gap)
        radius_mm = trace_width + clearance
        expansion = int(np.ceil(radius_mm / self.cell_size))

        # Helper to mark a single point with circular blocking
        def mark_point(x_mm, y_mm):
            cx, cy = self.world_to_grid(x_mm, y_mm)

            x_start = max(0, cx - expansion)
            x_end = min(self.width_cells, cx + expansion + 1)
            y_start = max(0, cy - expansion)
            y_end = min(self.height_cells, cy + expansion + 1)

            # Use circular distance check to avoid over-blocking in diagonal directions
            for y in range(y_start, y_end):
                for x in range(x_start, x_end):
                    dist = ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5 * self.cell_size
                    if dist <= radius_mm:
                        self.grid[y, x] = net_id
                        # Update usage count for PathFinder
                        if self.negotiated_mode and self.usage_count is not None:
                            self.usage_count[y, x] += 1

        # Mark all points in path
        if not path:
            return

        # Phase 2.1: Store segments for distance calculation
        if self.trace_segments is not None:
            if net_id not in self.trace_segments:
                self.trace_segments[net_id] = []

        # Rasterize lines between points
        for i in range(len(path) - 1):
            p1 = path[i]
            p2 = path[i + 1]

            # Phase 2.1: Store this segment with trace width
            if self.trace_segments is not None and net_id in self.trace_segments:
                self.trace_segments[net_id].append((p1, p2, trace_width))

            # Interpolate for smooth blocking if segment is long
            dist = ((p2[0] - p1[0]) ** 2 + (p2[1] - p1[1]) ** 2) ** 0.5
            steps = int(np.ceil(dist / (self.cell_size / 2)))  # 2x density for safety

            if steps > 0:
                for s in range(steps + 1):
                    t = s / steps
                    x = p1[0] + t * (p2[0] - p1[0])
                    y = p1[1] + t * (p2[1] - p1[1])
                    mark_point(x, y)

    def mark_segment_blocked(
        self,
        p1: tuple[float, float],
        p2: tuple[float, float],
        trace_width: float,
        clearance: float,
        net_id: int,
    ) -> None:
        """Mark a single segment blocked on THIS grid."""
        # Phase 2.1: Store segment geometry with trace width for distance calculation
        if self.trace_segments is not None:
            if net_id not in self.trace_segments:
                self.trace_segments[net_id] = []
            self.trace_segments[net_id].append((p1, p2, trace_width))

        radius_mm = trace_width + clearance
        expansion = int(np.ceil(radius_mm / self.cell_size))

        def mark_point(x_mm, y_mm):
            cx, cy = self.world_to_grid(x_mm, y_mm)
            x_start = max(0, cx - expansion)
            x_end = min(self.width_cells, cx + expansion + 1)
            y_start = max(0, cy - expansion)
            y_end = min(self.height_cells, cy + expansion + 1)

            # Use circular distance check
            for y in range(y_start, y_end):
                for x in range(x_start, x_end):
                    dist = ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5 * self.cell_size
                    if dist <= radius_mm:
                        self.grid[y, x] = net_id

        dist = ((p2[0] - p1[0]) ** 2 + (p2[1] - p1[1]) ** 2) ** 0.5
        steps = int(np.ceil(dist / (self.cell_size / 2)))

        if steps > 0:
            for s in range(steps + 1):
                t = s / steps
                x = p1[0] + t * (p2[0] - p1[0])
                y = p1[1] + t * (p2[1] - p1[1])
                mark_point(x, y)
        else:
            mark_point(p1[0], p1[1])

    def unmark_segment_blocked(
        self,
        p1: tuple[float, float],
        p2: tuple[float, float],
        trace_width: float,
        clearance: float,
        net_id: int,
    ) -> None:
        """Unmark a single segment from THIS grid."""
        # Phase 2.1: Remove segment geometry (match by p1, p2 only, ignoring trace_width)
        if self.trace_segments is not None and net_id in self.trace_segments:
            self.trace_segments[net_id] = [
                seg for seg in self.trace_segments[net_id]
                if not (seg[0] == p1 and seg[1] == p2)
            ]
            if not self.trace_segments[net_id]:
                del self.trace_segments[net_id]

        radius_mm = trace_width + clearance
        expansion = int(np.ceil(radius_mm / self.cell_size))

        def unmark_point(x_mm, y_mm):
            cx, cy = self.world_to_grid(x_mm, y_mm)
            x_start = max(0, cx - expansion)
            x_end = min(self.width_cells, cx + expansion + 1)
            y_start = max(0, cy - expansion)
            y_end = min(self.height_cells, cy + expansion + 1)

            # Use circular distance check
            for y in range(y_start, y_end):
                for x in range(x_start, x_end):
                    dist = ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5 * self.cell_size
                    if dist <= radius_mm:
                        if self.grid[y, x] == net_id:
                            # Restore -1 if it was a static obstacle, otherwise set to 0
                            if self.static_mask is not None and self.static_mask[y, x]:
                                self.grid[y, x] = -1
                            else:
                                self.grid[y, x] = 0

        dist = ((p2[0] - p1[0]) ** 2 + (p2[1] - p1[1]) ** 2) ** 0.5
        steps = int(np.ceil(dist / (self.cell_size / 2)))

        if steps > 0:
            for s in range(steps + 1):
                t = s / steps
                x = p1[0] + t * (p2[0] - p1[0])
                y = p1[1] + t * (p2[1] - p1[1])
                unmark_point(x, y)
        else:
            unmark_point(p1[0], p1[1])

    def unmark_path(
        self,
        path: list[tuple[float, float]],
        trace_width: float,
        clearance: float,
        net_id: int,
    ) -> None:
        """
        Unmark cells occupied by a specific net.

        Only clears cells that are currently owned by net_id.
        Does NOT clear if another net has overwritten it (shouldn't happen in valid state)
        or if it's a static obstacle.
        """
        radius_mm = trace_width + clearance
        expansion = int(np.ceil(radius_mm / self.cell_size))

        def unmark_point(x_mm, y_mm):
            cx, cy = self.world_to_grid(x_mm, y_mm)

            x_start = max(0, cx - expansion)
            x_end = min(self.width_cells, cx + expansion + 1)
            y_start = max(0, cy - expansion)
            y_end = min(self.height_cells, cy + expansion + 1)

            # Use circular distance check
            for y in range(y_start, y_end):
                for x in range(x_start, x_end):
                    dist = ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5 * self.cell_size
                    if dist <= radius_mm and self.grid[y, x] == net_id:
                        self.grid[y, x] = 0  # Set back to Free

        if not path:
            return

        # Phase 2.1: Remove segments from trace_segments
        if self.trace_segments is not None and net_id in self.trace_segments:
            # Remove all segments for this path (match by p1, p2 only, ignoring trace_width)
            for i in range(len(path) - 1):
                p1 = path[i]
                p2 = path[i + 1]
                # Find and remove segment matching p1, p2 (regardless of trace_width)
                self.trace_segments[net_id] = [
                    seg for seg in self.trace_segments[net_id]
                    if not (seg[0] == p1 and seg[1] == p2)
                ]

            # Clean up empty lists
            if net_id in self.trace_segments and not self.trace_segments[net_id]:
                del self.trace_segments[net_id]

        for i in range(len(path) - 1):
            p1 = path[i]
            p2 = path[i + 1]
            dist = ((p2[0] - p1[0]) ** 2 + (p2[1] - p1[1]) ** 2) ** 0.5
            steps = int(np.ceil(dist / (self.cell_size / 2)))

            if steps > 0:
                for s in range(steps + 1):
                    t = s / steps
                    x = p1[0] + t * (p2[0] - p1[0])
                    y = p1[1] + t * (p2[1] - p1[1])
                    unmark_point(x, y)

    def get_blocking_nets(
        self,
        p1: tuple[float, float],
        p2: tuple[float, float],
    ) -> set[int]:
        """
        Identify which net IDs are blocking the line segment p1-p2.
        """
        blocking_ids = set()

        # Simple sampling along line
        dist = ((p2[0] - p1[0]) ** 2 + (p2[1] - p1[1]) ** 2) ** 0.5
        steps = int(np.ceil(dist / (self.cell_size / 2)))

        if steps > 0:
            for s in range(steps + 1):
                t = s / steps
                x = p1[0] + t * (p2[0] - p1[0])
                y = p1[1] + t * (p2[1] - p1[1])

                cx, cy = self.world_to_grid(x, y)
                if 0 <= cx < self.width_cells and 0 <= cy < self.height_cells:
                    val = self.grid[cy, cx]
                    if val > 0:  # Valid Net ID
                        blocking_ids.add(int(val))

        return blocking_ids

    def mark_via_blocked(
        self,
        x_mm: float,
        y_mm: float,
        via_diameter: float,
        clearance: float,
        net_id: int,
    ) -> None:
        """
        Mark cells blocked by a via (circular region).

        Vias block cells on the layer with their annular ring + clearance.

        Args:
            x_mm: Via center X in mm
            y_mm: Via center Y in mm
            via_diameter: Via annular ring diameter in mm
            clearance: Required clearance in mm
            net_id: Net ID owning this via
        """
        # Correct C-Space: via_diameter + clearance (accounts for both via and trace radii)
        radius_mm = via_diameter + clearance
        expansion = int(np.ceil(radius_mm / self.cell_size))

        cx, cy = self.world_to_grid(x_mm, y_mm)

        x_start = max(0, cx - expansion)
        x_end = min(self.width_cells, cx + expansion + 1)
        y_start = max(0, cy - expansion)
        y_end = min(self.height_cells, cy + expansion + 1)

        # Mark circular region
        for y in range(y_start, y_end):
            for x in range(x_start, x_end):
                # Check if within circular radius
                dist = ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5 * self.cell_size
                if dist <= radius_mm:
                    self.grid[y, x] = net_id


def mark_path_blocked_3d(
    grids: dict[str, "OccupancyGrid"],
    path_3d: list[tuple[float, float, str]],
    trace_width: float,
    clearance: float,
    net_id: int,
) -> None:
    """
    Mark a 3D path on per-layer grids.

    Each segment is marked on the grid corresponding to its layer.

    Args:
        grids: Dictionary of OccupancyGrid per layer
        path_3d: List of (x, y, layer) coordinates
        trace_width: Trace width in mm
        clearance: Clearance in mm
        net_id: Net ID for blocking
    """
    if len(path_3d) < 2:
        return

    # Group consecutive points by layer
    for i in range(len(path_3d) - 1):
        x1, y1, layer1 = path_3d[i]
        x2, y2, layer2 = path_3d[i + 1]

        # Mark on starting layer's grid
        if layer1 in grids:
            segment = [(x1, y1), (x2, y2)]
            grids[layer1].mark_path_blocked(segment, trace_width, clearance, net_id)


def build_occupancy_grid(
    routing_space: RoutingSpace,
    cell_size: float = 0.1,
    margin: float = 2.0,
    inflation_mm: float = 0.0,
) -> OccupancyGrid:
    """
    Build occupancy grid from routing space with C-Space inflation.

    Args:
        routing_space: Routing space from Stage 2.2
        cell_size: Grid cell size in mm (default 0.1mm)
        margin: Margin around routing area in mm
        inflation_mm: Buffer to erode free area by (for C-Space)

    Returns:
        OccupancyGrid with blocked cells marked
    """
    # Get board bounds from routing space
    x_min, y_min, x_max, y_max = routing_space.available_area.bounds

    # Add margin
    x_min -= margin
    y_min -= margin
    x_max += margin
    y_max += margin

    # Calculate grid dimensions
    width_mm = x_max - x_min
    height_mm = y_max - y_min

    width_cells = max(1, int(np.ceil(width_mm / cell_size)))
    height_cells = max(1, int(np.ceil(height_mm / cell_size)))

    # Initialize grid as all blocked (static obstacle)
    grid = np.full((height_cells, width_cells), -1, dtype=np.int16)

    # Use eroded area if inflation requested
    check_area = routing_space.available_area
    if inflation_mm > 0.1:  # Threshold to avoid tiny/empty buffers
        # Erode the available area (which is dilation of obstacles)
        check_area = routing_space.available_area.buffer(-inflation_mm, quad_segs=4)

    # Vectorized grid construction
    # 1. Create coordinate grids
    x_indices = np.arange(width_cells)
    y_indices = np.arange(height_cells)
    xx_idx, yy_idx = np.meshgrid(x_indices, y_indices)

    # 2. Convert to world coordinates
    xx_world = x_min + (xx_idx + 0.5) * cell_size
    yy_world = y_min + (yy_idx + 0.5) * cell_size

    # 3. Create Shapely points in batch
    # Flatten for vectorization
    flat_x = xx_world.ravel()
    flat_y = yy_world.ravel()
    batch_points = points(flat_x, flat_y)

    # 4. Check containment in batch
    # Note: check_area is a Polygon/MultiPolygon. contains() supports array input.
    mask_flat = contains(check_area, batch_points)

    # 5. Reshape and update grid
    mask = mask_flat.reshape(height_cells, width_cells)

    # Set Free (0) where mask is True (contained in available area)
    # The grid was initialized to -1 (Blocked)
    grid[mask] = 0

    # Record which cells were static obstacles (-1) before routing
    static_mask = grid == -1

    return OccupancyGrid(
        layer_name=routing_space.layer_name,
        grid=grid,
        origin=(x_min, y_min),
        cell_size=cell_size,
        width_cells=width_cells,
        height_cells=height_cells,
        static_mask=static_mask,
    )
