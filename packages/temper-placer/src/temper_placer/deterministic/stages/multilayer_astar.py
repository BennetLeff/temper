"""Multi-layer A* pathfinder for PCB routing.

This extends the basic A* algorithm to search across multiple copper layers,
automatically inserting vias when changing layers. This dramatically improves
routing completion rates on congested boards.
"""

import heapq
import math
from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Set, TYPE_CHECKING

if TYPE_CHECKING:
    from .clearance_grid import ClearanceGrid
    from temper_placer.routing.constraints.drc_oracle import DRCOracle


@dataclass
class RouteSegment:
    """A segment of a routed path."""

    start: Tuple[float, float]
    end: Tuple[float, float]
    layer: int


@dataclass
class MultiLayerPath:
    """Result of multi-layer pathfinding."""

    segments: List[RouteSegment]
    via_positions: List[Tuple[float, float, int, int]]  # (x, y, from_layer, to_layer)
    total_cost: float


@dataclass
class MultiLayerAStar:
    """A* pathfinder that can route across multiple layers using vias.

    State space is (row, col, layer) instead of just (row, col).
    Layer transitions are modeled as special neighbors with via cost.

    Parameters:
        grid: The ClearanceGrid for collision checking
        drc_oracle: Optional DRC oracle for proactive validation
        net_name: Name of the net being routed (for DRC checks)
        trace_width: Width of traces being routed
        via_cost: Extra cost for placing a via (discourages unnecessary layer changes)
        allowed_layers: List of layer indices that can be used for routing
        max_iterations: Maximum search iterations before giving up
    """

    grid: "ClearanceGrid"
    drc_oracle: Optional["DRCOracle"] = None
    net_name: str = ""
    trace_width: float = 0.25
    via_cost: float = 5.0  # Vias are expensive - prefer staying on same layer
    via_diameter: float = 0.6
    via_drill: float = 0.3
    allowed_layers: List[int] = field(
        default_factory=lambda: [0, 1, 2, 3]
    )  # All 4 layers by default
    max_iterations: int = 5000  # Reduced for faster feedback (was 50000)

    def __post_init__(self):
        self._net_id = self.grid.get_net_id(self.net_name) if self.net_name else 0

    def find_path(
        self,
        start: Tuple[float, float],
        end: Tuple[float, float],
        start_layer: int = 0,
        end_layer: int = -1,
    ) -> Optional[MultiLayerPath]:
        """Find path from start to end, potentially using multiple layers.

        Args:
            start: (x, y) start position in mm
            end: (x, y) end position in mm
            start_layer: Layer index to start from
            end_layer: Layer index to end at (-1 means any layer)

        Returns:
            MultiLayerPath with segments and via positions, or None if no path found.
        """
        if end_layer == -1:
            end_layer = start_layer

        # Validate layers
        if start_layer not in self.allowed_layers:
            # Try to find a path using allowed layers
            start_layer = self.allowed_layers[0] if self.allowed_layers else 0

        start_cell = self.grid._mm_to_cell(*start)
        end_cell = self.grid._mm_to_cell(*end)

        # Check bounds
        if not self._is_within_bounds(start_cell) or not self._is_within_bounds(end_cell):
            return None

        # A* with 3D state: (row, col, layer)
        # Priority: (f_score, tie_breaker, state)
        start_state = (start_cell[0], start_cell[1], start_layer)
        end_cells = self._get_end_cells(end_cell, end_layer)

        open_set = [(0, self._tie_breaker(start_state), start_state)]
        came_from = {}
        g_score = {start_state: 0}
        iterations = 0

        while open_set and iterations < self.max_iterations:
            iterations += 1
            _, _, current = heapq.heappop(open_set)

            # Check if we reached any valid end state
            if self._is_goal(current, end_cells, end_layer):
                return self._reconstruct_multilayer_path(came_from, current, start, end)

            for neighbor, cost in self._get_3d_neighbors(current):
                tentative_g = g_score[current] + cost

                if neighbor not in g_score or tentative_g < g_score[neighbor]:
                    came_from[neighbor] = current
                    g_score[neighbor] = tentative_g
                    f_score = tentative_g + self._heuristic_3d(neighbor, end_cell, end_layer)
                    heapq.heappush(open_set, (f_score, self._tie_breaker(neighbor), neighbor))

        if iterations >= self.max_iterations:
            print(
                f"WARNING: Multi-layer A* for {self.net_name} exceeded {self.max_iterations} iterations"
            )

        return None

    def _is_within_bounds(self, cell: Tuple[int, int]) -> bool:
        """Check if cell is within grid bounds."""
        row, col = cell
        return 0 <= row < self.grid.rows and 0 <= col < self.grid.cols

    def _is_valid_3d(self, state: Tuple[int, int, int]) -> bool:
        """Check if a 3D state (row, col, layer) is valid."""
        row, col, layer = state
        if not self._is_within_bounds((row, col)):
            return False
        if layer not in self.allowed_layers:
            return False
        if layer < 0 or layer >= self.grid.layer_count:
            return False

        # Convert state to mm for is_available check
        pos_mm = self._state_to_mm(state)
        return self.grid.is_available(pos_mm[0], pos_mm[1], layer, net_id=self._net_id)

    def _get_end_cells(
        self, end_cell: Tuple[int, int], end_layer: int
    ) -> Set[Tuple[int, int, int]]:
        """Get valid end states."""
        if end_layer == -1:
            # Any layer is acceptable
            return {(end_cell[0], end_cell[1], layer) for layer in self.allowed_layers}
        else:
            return {(end_cell[0], end_cell[1], end_layer)}

    def _is_goal(
        self, state: Tuple[int, int, int], end_cells: Set[Tuple[int, int, int]], end_layer: int
    ) -> bool:
        """Check if we've reached the goal.

        If end_layer is specified (not -1), the path MUST end on that layer.
        This ensures layer transitions actually occur when required.
        """
        row, col, layer = state
        if end_layer == -1:
            # Any layer at end position is OK
            return any((row, col) == (e[0], e[1]) for e in end_cells)
        # Specific layer required - must match exactly
        return (row, col, layer) in end_cells

    def _get_3d_neighbors(
        self, state: Tuple[int, int, int]
    ) -> List[Tuple[Tuple[int, int, int], float]]:
        """Get valid 3D neighbors including layer transitions."""
        row, col, layer = state
        neighbors = []

        # Same-layer moves (8-connected)
        same_layer_moves = [
            ((row - 1, col, layer), 1.0),  # up
            ((row, col + 1, layer), 1.0),  # right
            ((row + 1, col, layer), 1.0),  # down
            ((row, col - 1, layer), 1.0),  # left
            ((row - 1, col - 1, layer), 1.414),  # up-left
            ((row - 1, col + 1, layer), 1.414),  # up-right
            ((row + 1, col - 1, layer), 1.414),  # down-left
            ((row + 1, col + 1, layer), 1.414),  # down-right
        ]

        for neighbor_state, cost in same_layer_moves:
            if not self._is_valid_3d(neighbor_state):
                continue

            # DRC check if oracle available
            if self.drc_oracle:
                p1 = self._state_to_mm(state)
                p2 = self._state_to_mm(neighbor_state)
                valid, _ = self.drc_oracle.can_place_track_segment(
                    start=p1, end=p2, layer=layer, net=self.net_name, width=self.trace_width
                )
                if not valid:
                    continue

            neighbors.append((neighbor_state, cost))

        # Layer transitions (via placement)
        for target_layer in self.allowed_layers:
            if target_layer == layer:
                continue

            # Check if target layer is free at this position
            target_state = (row, col, target_layer)
            if not self._is_valid_3d(target_state):
                continue

            # Check via placement with DRC oracle
            if self.drc_oracle:
                via_pos = self._state_to_mm(state)
                sites = self.drc_oracle.get_valid_via_sites(
                    via_pos, search_radius=0.5, net=self.net_name
                )
                if not sites:
                    continue

            neighbors.append((target_state, self.via_cost))

        return neighbors

    def _state_to_mm(self, state: Tuple[int, int, int]) -> Tuple[float, float]:
        """Convert grid state to mm coordinates."""
        row, col, _ = state
        return (
            col * self.grid.cell_size_mm + self.grid.cell_size_mm / 2,
            row * self.grid.cell_size_mm + self.grid.cell_size_mm / 2,
        )

    def _heuristic_3d(
        self, state: Tuple[int, int, int], end_cell: Tuple[int, int], end_layer: int
    ) -> float:
        """3D heuristic: Euclidean distance + layer change penalty."""
        row, col, layer = state
        h = math.sqrt((row - end_cell[0]) ** 2 + (col - end_cell[1]) ** 2)

        # Add layer change penalty if we're not on the target layer
        if end_layer != -1 and layer != end_layer:
            h += self.via_cost

        return h

    def _tie_breaker(self, state: Tuple[int, int, int]) -> Tuple[int, int, int]:
        """Deterministic tie-breaker: prefer lower layer, then lower row, then lower col."""
        return state

    def _reconstruct_multilayer_path(
        self,
        came_from: dict,
        current: Tuple[int, int, int],
        start: Tuple[float, float],
        end: Tuple[float, float],
    ) -> MultiLayerPath:
        """Reconstruct path and identify layer transitions."""
        path_states = [current]
        while current in came_from:
            current = came_from[current]
            path_states.append(current)
        path_states.reverse()

        segments = []
        via_positions = []

        # Convert to segments, tracking layer transitions
        for i in range(len(path_states) - 1):
            s1 = path_states[i]
            s2 = path_states[i + 1]

            row1, col1, layer1 = s1
            row2, col2, layer2 = s2

            if layer1 != layer2:
                # Layer transition - record via position
                via_pos = self._state_to_mm(s1)
                via_positions.append((via_pos[0], via_pos[1], layer1, layer2))

                # Create landing segment on new layer if XY position changed
                # This connects the via to the next point on the target layer
                p2 = self._state_to_mm(s2)
                if via_pos != p2:
                    segments.append(RouteSegment(start=via_pos, end=p2, layer=layer2))
            else:
                # Same layer - add trace segment
                if i == 0:
                    p1 = start
                else:
                    p1 = self._state_to_mm(s1)

                if i == len(path_states) - 2:
                    p2 = end
                else:
                    p2 = self._state_to_mm(s2)

                segments.append(RouteSegment(start=p1, end=p2, layer=layer1))

        # Merge consecutive segments on same layer
        merged_segments = self._merge_segments(segments, start, end)

        # Calculate total cost
        total_cost = len(segments) + len(via_positions) * self.via_cost

        return MultiLayerPath(
            segments=merged_segments, via_positions=via_positions, total_cost=total_cost
        )

    def _merge_segments(
        self, segments: List[RouteSegment], start: Tuple[float, float], end: Tuple[float, float]
    ) -> List[RouteSegment]:
        """Merge consecutive segments on same layer into polylines."""
        if not segments:
            return []

        merged = []
        current_layer = segments[0].layer
        current_points = [segments[0].start]

        for seg in segments:
            if seg.layer == current_layer:
                current_points.append(seg.end)
            else:
                # Layer change - finalize current segment group
                if len(current_points) >= 2:
                    for i in range(len(current_points) - 1):
                        merged.append(
                            RouteSegment(
                                start=current_points[i],
                                end=current_points[i + 1],
                                layer=current_layer,
                            )
                        )
                current_layer = seg.layer
                current_points = [seg.start, seg.end]

        # Finalize last segment group
        if len(current_points) >= 2:
            for i in range(len(current_points) - 1):
                merged.append(
                    RouteSegment(
                        start=current_points[i], end=current_points[i + 1], layer=current_layer
                    )
                )

        return merged
