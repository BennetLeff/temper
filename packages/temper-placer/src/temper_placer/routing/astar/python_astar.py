"""Pure Python implementation of multi-layer A* pathfinder for PCB routing.

DEPRECATED: This is the reference Python implementation kept for debugging and validation.
For production use, the Cython implementation provides 50-100x speedup.
Activate with: TEMPER_USE_CYTHON_ASTAR=0
"""

import heapq
import math
import warnings
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from temper_placer.core.units import Millimeters
from temper_placer.routing.iteration_budget import (
    CongestionLevel,
    IterationBudget,
    RoutingContext,
)

from .types import MultiLayerPath, RouteSegment

if TYPE_CHECKING:
    from temper_placer.deterministic.stages.clearance_grid import ClearanceGrid
    from temper_placer.routing.adaptive_congestion import CongestionDetector
    from temper_placer.routing.constraints.drc_oracle import DRCOracle


warnings.warn(
    "python_astar is deprecated and provided only for debugging. "
    "Use TEMPER_USE_CYTHON_ASTAR=1 for 50-100x faster Cython implementation.",
    DeprecationWarning,
    stacklevel=2,
)


OCTILE_DIAG = math.sqrt(2) - 1
_CARDINAL_COST = 1.0
_DIAGONAL_COST = math.sqrt(2)
_SAME_LAYER_DELTAS: tuple[tuple[int, int, float], ...] = (
    (-1, 0, _CARDINAL_COST), (0, 1, _CARDINAL_COST),
    (1, 0, _CARDINAL_COST), (0, -1, _CARDINAL_COST),
    (-1, -1, _DIAGONAL_COST), (-1, 1, _DIAGONAL_COST),
    (1, -1, _DIAGONAL_COST), (1, 1, _DIAGONAL_COST),
)
_CONGESTION_ORDER: dict[CongestionLevel, int] = {
    CongestionLevel.LOW: 0,
    CongestionLevel.MEDIUM: 1,
    CongestionLevel.HIGH: 2,
    CongestionLevel.EXTREME: 3,
}


@dataclass
class MultiLayerAStar:
    """A* pathfinder that can route across multiple layers using vias.

    State space is (row, col, layer) instead of just (row, col).
    Layer transitions are modeled as special neighbors with via cost.
    """

    grid: "ClearanceGrid"
    drc_oracle: "DRCOracle | None" = None
    net_name: str = ""
    net_class: str = "Signal"
    trace_width: float = 0.25
    via_cost: float = 5.0  # Vias are expensive - prefer staying on same layer
    via_diameter: float = 0.6
    via_drill: float = 0.3
    allowed_layers: list[int] = field(
        default_factory=lambda: [0, 1, 2, 3]
    )
    max_iterations: int = 15000  # DEPRECATED: use adaptive budget instead
    congestion_detector: "CongestionDetector | None" = None
    use_adaptive_budget: bool = True
    base_iterations_per_cell: int = 100
    iterations_per_cell: int = 100  # DEPRECATED
    min_iterations: int = 5000
    max_iterations_cap: int = 200000  # DEPRECATED

    def __post_init__(self):
        self._net_id = self.grid.get_net_id(self.net_name) if self.net_name else 0
        self.last_iterations = 0
        self.last_iteration_limit = 0
        self.last_timeout = False
        self.last_congestion_level = CongestionLevel.LOW

    def _estimate_iterations(self, start_cell: tuple[int, int], end_cell: tuple[int, int]) -> int:
        """Estimate max iterations based on distance and search complexity."""
        start_mm = (
            Millimeters(start_cell[1] * self.grid.cell_size_mm),
            Millimeters(start_cell[0] * self.grid.cell_size_mm),
        )
        end_mm = (
            Millimeters(end_cell[1] * self.grid.cell_size_mm),
            Millimeters(end_cell[0] * self.grid.cell_size_mm),
        )

        if self.use_adaptive_budget:
            congestion_level = CongestionLevel.LOW
            if self.congestion_detector:
                congestion_start = self.congestion_detector.detect_congestion(
                    point=start_mm, radius=Millimeters(5.0)
                )
                congestion_end = self.congestion_detector.detect_congestion(
                    point=end_mm, radius=Millimeters(5.0)
                )
                if _CONGESTION_ORDER[congestion_end] > _CONGESTION_ORDER[congestion_start]:
                    congestion_level = congestion_end
                else:
                    congestion_level = congestion_start

            self.last_congestion_level = congestion_level

            context = RoutingContext(
                net_name=self.net_name,
                start=start_mm,
                end=end_mm,
                allowed_layers=tuple(self.allowed_layers),
                net_class=self.net_class,
            )

            budget = IterationBudget.calculate(
                context=context,
                congestion=congestion_level,
                base_iterations_per_cell=self.base_iterations_per_cell,
            )
            return budget.max_iterations

        # Legacy distance-based fallback (kept for backward compatibility)
        if self.max_iterations > 200000:
            return self.max_iterations

        dr = abs(start_cell[0] - end_cell[0])
        dc = abs(start_cell[1] - end_cell[1])
        octile_dist = max(dr, dc) + OCTILE_DIAG * min(dr, dc)
        layer_factor = 1.0 + 0.3 * (len(self.allowed_layers) - 1)
        congestion_factor = 2.0
        estimated = int(
            self.iterations_per_cell * octile_dist * layer_factor * congestion_factor
        )
        return max(self.min_iterations, min(estimated, self.max_iterations_cap))

    def find_path(
        self,
        start: tuple[float, float],
        end: tuple[float, float],
        start_layer: int = 0,
        end_layer: int = -1,
    ) -> "MultiLayerPath | None":
        """Find path from start to end, potentially using multiple layers."""
        if start_layer not in self.allowed_layers:
            start_layer = self.allowed_layers[0] if self.allowed_layers else 0

        start_cell = self.grid._mm_to_cell(*start)
        end_cell = self.grid._mm_to_cell(*end)

        if not self._is_within_bounds(start_cell) or not self._is_within_bounds(end_cell):
            self.last_iterations = 0
            self.last_iteration_limit = 0
            self.last_timeout = False
            return None

        adaptive_limit = self._estimate_iterations(start_cell, end_cell)
        self.last_iteration_limit = adaptive_limit

        # Determine which layers are blocked at the goal (heuristic optimization)
        end_blocked_layers: set[int] | None = None
        if end_layer == -1:
            end_blocked_layers = {
                layer
                for layer in self.allowed_layers
                if not self._is_valid_3d((end_cell[0], end_cell[1], layer))
            }
            if not end_blocked_layers or len(end_blocked_layers) == len(self.allowed_layers):
                end_blocked_layers = None

        start_state = (start_cell[0], start_cell[1], start_layer)
        end_cells = self._get_end_cells(end_cell, end_layer)

        open_set = [(0, start_state)]
        came_from: dict = {}
        g_score: dict[tuple[int, int, int], float] = {start_state: 0}
        iterations = 0

        while open_set and iterations < adaptive_limit:
            iterations += 1
            _, current = heapq.heappop(open_set)

            if self._is_goal(current, end_cells, end_layer, end_cell):
                self.last_iterations = iterations
                self.last_timeout = False
                return self._reconstruct_multilayer_path(came_from, current, start, end)

            for neighbor, cost in self._get_3d_neighbors(current):
                tentative_g = g_score[current] + cost

                if neighbor not in g_score or tentative_g < g_score[neighbor]:
                    came_from[neighbor] = current
                    g_score[neighbor] = tentative_g
                    f_score = tentative_g + self._heuristic_3d(
                        neighbor, end_cell, end_layer, end_blocked_layers
                    )
                    heapq.heappush(open_set, (f_score, neighbor))

        self.last_iterations = iterations
        self.last_timeout = iterations >= adaptive_limit

        if self.last_timeout:
            dr = abs(start_cell[0] - end_cell[0])
            dc = abs(start_cell[1] - end_cell[1])
            dist_cells = max(dr, dc) + OCTILE_DIAG * min(dr, dc)
            congestion_str = (
                f", congestion={self.last_congestion_level.value}"
                if self.use_adaptive_budget
                else ""
            )
            print(
                f"WARNING: Multi-layer A* for {self.net_name} exceeded {adaptive_limit} iterations "
                f"(dist={dist_cells:.0f} cells, layers={len(self.allowed_layers)}{congestion_str})"
            )

        return None

    def _is_within_bounds(self, cell: tuple[int, int]) -> bool:
        row, col = cell
        return 0 <= row < self.grid.rows and 0 <= col < self.grid.cols

    def _is_valid_3d(self, state: tuple[int, int, int]) -> bool:
        row, col, layer = state
        if not self._is_within_bounds((row, col)):
            return False
        if layer not in self.allowed_layers or layer < 0 or layer >= self.grid.layer_count:
            return False
        pos_mm = self._state_to_mm(state)
        return self.grid.is_available(pos_mm[0], pos_mm[1], layer, net_id=self._net_id)

    def _get_end_cells(
        self, end_cell: tuple[int, int], end_layer: int
    ) -> set[tuple[int, int, int]]:
        if end_layer == -1:
            return {(end_cell[0], end_cell[1], layer) for layer in self.allowed_layers}
        return {(end_cell[0], end_cell[1], end_layer)}

    def _is_goal(
        self,
        state: tuple[int, int, int],
        end_cells: set[tuple[int, int, int]],
        end_layer: int,
        end_cell: tuple[int, int] | None = None,
    ) -> bool:
        row, col, layer = state
        if end_layer == -1:
            assert end_cell is not None
            return row == end_cell[0] and col == end_cell[1]
        return (row, col, layer) in end_cells

    def _get_3d_neighbors(
        self, state: tuple[int, int, int]
    ) -> list[tuple[tuple[int, int, int], float]]:
        row, col, layer = state
        neighbors: list[tuple[tuple[int, int, int], float]] = []

        state_mm = self._state_to_mm(state)

        # Same-layer moves (8-connected)
        for dr, dc, cost in _SAME_LAYER_DELTAS:
            neighbor_state = (row + dr, col + dc, layer)
            if not self._is_valid_3d(neighbor_state):
                continue
            if self.drc_oracle:
                p2 = self._state_to_mm(neighbor_state)
                valid, _ = self.drc_oracle.can_place_track_segment(
                    start=state_mm, end=p2, layer=layer, net=self.net_name, width=self.trace_width
                )
                if not valid:
                    continue
            neighbors.append((neighbor_state, cost))

        # Layer transitions (via placement)
        via_sites_available = True
        if self.drc_oracle:
            sites = self.drc_oracle.get_valid_via_sites(
                state_mm, search_radius=0.5, net=self.net_name
            )
            via_sites_available = bool(sites)

        if not via_sites_available:
            return neighbors

        for target_layer in self.allowed_layers:
            if target_layer == layer:
                continue
            target_state = (row, col, target_layer)
            if self._is_valid_3d(target_state):
                neighbors.append((target_state, self.via_cost))

        return neighbors

    def _state_to_mm(self, state: tuple[int, int, int]) -> tuple[float, float]:
        row, col, _ = state
        cs = self.grid.cell_size_mm
        return (col * cs + cs / 2, row * cs + cs / 2)

    def _heuristic_3d(
        self,
        state: tuple[int, int, int],
        end_cell: tuple[int, int],
        end_layer: int,
        end_blocked_layers: set[int] | None = None,
    ) -> float:
        """3D heuristic: octile distance + layer change penalty when needed."""
        row, col, layer = state

        dr = abs(row - end_cell[0])
        dc = abs(col - end_cell[1])
        h = max(dr, dc) + OCTILE_DIAG * min(dr, dc)

        if end_layer != -1 and layer != end_layer or end_blocked_layers and layer in end_blocked_layers:
            h += self.via_cost

        return h

    def _reconstruct_multilayer_path(
        self,
        came_from: dict,
        current: tuple[int, int, int],
        start: tuple[float, float],
        end: tuple[float, float],
    ) -> MultiLayerPath:
        path_states = [current]
        while current in came_from:
            current = came_from[current]
            path_states.append(current)
        path_states.reverse()

        segments: list[RouteSegment] = []
        via_positions: list[tuple[float, float, int, int]] = []

        for i in range(len(path_states) - 1):
            s1 = path_states[i]
            s2 = path_states[i + 1]
            layer1 = s1[2]
            layer2 = s2[2]

            if layer1 != layer2:
                via_pos = self._state_to_mm(s1)
                via_positions.append((via_pos[0], via_pos[1], layer1, layer2))
                p2 = self._state_to_mm(s2)
                if via_pos != p2:
                    segments.append(RouteSegment(start=via_pos, end=p2, layer=layer2))
            else:
                p1 = start if i == 0 else self._state_to_mm(s1)
                p2 = end if i == len(path_states) - 2 else self._state_to_mm(s2)
                segments.append(RouteSegment(start=p1, end=p2, layer=layer1))

        merged_segments = self._merge_segments(segments)

        total_cost = len(merged_segments) + len(via_positions) * self.via_cost

        return MultiLayerPath(
            segments=merged_segments, via_positions=via_positions, total_cost=total_cost
        )

    def _merge_segments(self, segments: list[RouteSegment]) -> list[RouteSegment]:
        if not segments:
            return []

        merged: list[RouteSegment] = []
        current_layer = segments[0].layer
        current_points: list[tuple[float, float]] = [segments[0].start]

        for seg in segments:
            if seg.layer == current_layer:
                current_points.append(seg.end)
            else:
                if len(current_points) >= 2:
                    for a, b in zip(current_points, current_points[1:]):
                        merged.append(RouteSegment(start=a, end=b, layer=current_layer))
                current_layer = seg.layer
                current_points = [seg.start, seg.end]

        if len(current_points) >= 2:
            for a, b in zip(current_points, current_points[1:]):
                merged.append(RouteSegment(start=a, end=b, layer=current_layer))

        return merged


def find_path(
    grid: "ClearanceGrid",
    start_pos: tuple[float, float],
    end_pos: tuple[float, float],
    net_id: int,
    config: dict,
    start_layer: int = 0,
    end_layer: int = -1,
    drc_oracle: "DRCOracle | None" = None,
    net_name: str | None = None,
    via_diameter: float = 0.6,
) -> "MultiLayerPath | None":
    """Convenience function for calling MultiLayerAStar.find_path().

    This function signature matches the Cython implementation.
    """
    use_adaptive = True
    max_iters = 15000

    if config and "max_iterations" in config:
        max_iters = config["max_iterations"]
        use_adaptive = False  # Trust the caller's limit

    astar = MultiLayerAStar(
        grid=grid,
        drc_oracle=drc_oracle,
        net_name=net_name or f"net_{net_id}",
        via_diameter=via_diameter,
        max_iterations=max_iters,
        use_adaptive_budget=use_adaptive,
    )
    return astar.find_path(start_pos, end_pos, start_layer, end_layer)
