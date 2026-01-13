"""Bidirectional A* pathfinder for long-distance PCB routing.

This implements dual-frontier A* search which explores from both start and goal
simultaneously. When the frontiers meet, we reconstruct the path by stitching
the forward and backward paths together.

Performance: O(2 * b^(d/2)) vs unidirectional O(b^d)
- For 50-cell routes: ~100x faster
- Typical speedup: 10-100x for routes >30 cells

Use cases:
- High-voltage nets that span long distances (45-50 cells)
- Power rails crossing the board
- Any net where unidirectional A* times out (>5000 iterations)
"""

import heapq
import math
from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Dict, Set

from temper_placer.routing.astar import RouteSegment, MultiLayerPath
from .clearance_grid import ClearanceGrid
from temper_placer.routing.constraints.drc_oracle import DRCOracle


@dataclass
class BidirectionalAStar:
    """Dual-frontier A* for long-distance routing.
    
    Searches from both start and goal simultaneously, meeting in the middle.
    This reduces the search space exponentially for long routes.
    
    Parameters:
        grid: ClearanceGrid for collision detection
        drc_oracle: Optional DRC oracle for validation
        net_name: Name of net being routed
        trace_width: Trace width in mm
        via_cost: Cost penalty for layer changes
        via_diameter: Via pad diameter in mm
        via_drill: Via drill diameter in mm
        allowed_layers: Layers available for routing
        max_iterations: Maximum combined iterations (both frontiers)
    """
    
    grid: ClearanceGrid
    drc_oracle: Optional[DRCOracle] = None
    net_name: str = ""
    trace_width: float = 0.25
    via_cost: float = 5.0
    via_diameter: float = 0.6
    via_drill: float = 0.3
    allowed_layers: List[int] = field(default_factory=lambda: [0, 1, 2, 3])
    max_iterations: int = 200000  # Increased for Experiment B (was 10000)
    
    def __post_init__(self):
        self._net_id = self.grid.get_net_id(self.net_name) if self.net_name else 0
        # Search stats
        self.last_fwd_iterations = 0
        self.last_bwd_iterations = 0
        self.last_meeting_point = None
        self.last_timeout = False
    
    def find_path(
        self,
        start: Tuple[float, float],
        end: Tuple[float, float],
        start_layer: int = 0,
        end_layer: int = 0,
    ) -> Optional[MultiLayerPath]:
        """Find path using bidirectional search.
        
        Args:
            start: (x, y) start position in mm
            end: (x, y) goal position in mm
            start_layer: Starting layer index
            end_layer: Goal layer index
            
        Returns:
            MultiLayerPath if found, None otherwise
        """
        # Convert to grid cells
        start_cell = self.grid._mm_to_cell(*start)
        end_cell = self.grid._mm_to_cell(*end)
        
        # Validate bounds
        if not self._is_within_bounds(start_cell) or not self._is_within_bounds(end_cell):
            return None
        
        # Initialize forward frontier (from start)
        start_state = (start_cell[0], start_cell[1], start_layer)
        fwd_open = [(0, 0, start_state)]  # (f_score, tie_breaker, state)
        fwd_closed = {}  # state -> (g_score, parent_state)
        fwd_g_score = {start_state: 0}
        
        # Initialize backward frontier (from goal)
        end_state = (end_cell[0], end_cell[1], end_layer)
        bwd_open = [(0, 0, end_state)]
        bwd_closed = {}
        bwd_g_score = {end_state: 0}
        
        # Search stats
        fwd_iterations = 0
        bwd_iterations = 0
        
        # Alternate between expanding forward and backward
        while fwd_open and bwd_open and (fwd_iterations + bwd_iterations) < self.max_iterations:
            # Expand forward frontier
            if fwd_open:
                fwd_iterations += 1
                _, _, current_fwd = heapq.heappop(fwd_open)
                
                # Check if backward frontier reached this state
                if current_fwd in bwd_closed:
                    self.last_fwd_iterations = fwd_iterations
                    self.last_bwd_iterations = bwd_iterations
                    self.last_meeting_point = current_fwd
                    self.last_timeout = False
                    return self._reconstruct_bidirectional_path(
                        current_fwd, fwd_closed, bwd_closed, start, end
                    )
                
                # Mark as explored
                fwd_closed[current_fwd] = (fwd_g_score[current_fwd], None)
                
                # Expand neighbors
                for neighbor, cost in self._get_neighbors(current_fwd):
                    tentative_g = fwd_g_score[current_fwd] + cost
                    
                    if neighbor not in fwd_g_score or tentative_g < fwd_g_score[neighbor]:
                        fwd_g_score[neighbor] = tentative_g
                        # Heuristic: distance to goal
                        h = self._heuristic(neighbor, end_cell, end_layer)
                        f = tentative_g + h
                        heapq.heappush(fwd_open, (f, fwd_iterations, neighbor))
                        fwd_closed[neighbor] = (tentative_g, current_fwd)
                        
                        # Check if backward already explored this
                        if neighbor in bwd_closed:
                            self.last_fwd_iterations = fwd_iterations
                            self.last_bwd_iterations = bwd_iterations
                            self.last_meeting_point = neighbor
                            self.last_timeout = False
                            return self._reconstruct_bidirectional_path(
                                neighbor, fwd_closed, bwd_closed, start, end
                            )
            
            # Expand backward frontier
            if bwd_open:
                bwd_iterations += 1
                _, _, current_bwd = heapq.heappop(bwd_open)
                
                # Check if forward frontier reached this state
                if current_bwd in fwd_closed:
                    self.last_fwd_iterations = fwd_iterations
                    self.last_bwd_iterations = bwd_iterations
                    self.last_meeting_point = current_bwd
                    self.last_timeout = False
                    return self._reconstruct_bidirectional_path(
                        current_bwd, fwd_closed, bwd_closed, start, end
                    )
                
                # Mark as explored
                bwd_closed[current_bwd] = (bwd_g_score[current_bwd], None)
                
                # Expand neighbors
                for neighbor, cost in self._get_neighbors(current_bwd):
                    tentative_g = bwd_g_score[current_bwd] + cost
                    
                    if neighbor not in bwd_g_score or tentative_g < bwd_g_score[neighbor]:
                        bwd_g_score[neighbor] = tentative_g
                        # Heuristic: distance to start
                        h = self._heuristic(neighbor, start_cell, start_layer)
                        f = tentative_g + h
                        heapq.heappush(bwd_open, (f, bwd_iterations, neighbor))
                        bwd_closed[neighbor] = (tentative_g, current_bwd)
                        
                        # Check if forward already explored this
                        if neighbor in fwd_closed:
                            self.last_fwd_iterations = fwd_iterations
                            self.last_bwd_iterations = bwd_iterations
                            self.last_meeting_point = neighbor
                            self.last_timeout = False
                            return self._reconstruct_bidirectional_path(
                                neighbor, fwd_closed, bwd_closed, start, end
                            )
        
        # Timeout or no path
        self.last_fwd_iterations = fwd_iterations
        self.last_bwd_iterations = bwd_iterations
        self.last_timeout = (fwd_iterations + bwd_iterations) >= self.max_iterations
        return None
    
    def _get_neighbors(self, state: Tuple[int, int, int]) -> List[Tuple[Tuple[int, int, int], float]]:
        """Get valid neighboring states with costs.
        
        Returns:
            List of (neighbor_state, cost) tuples
        """
        row, col, layer = state
        neighbors = []
        
        # 8-connected grid on same layer
        for dr in [-1, 0, 1]:
            for dc in [-1, 0, 1]:
                if dr == 0 and dc == 0:
                    continue
                
                new_row, new_col = row + dr, col + dc
                new_state = (new_row, new_col, layer)
                
                if self._is_valid_state(new_state):
                    # If oracle is present, perform proactive DRC check
                    if self.drc_oracle:
                        # Convert cells to mm with centering offset for oracle
                        p1 = (
                            col * self.grid.cell_size_mm + self.grid.cell_size_mm / 2,
                            row * self.grid.cell_size_mm + self.grid.cell_size_mm / 2,
                        )
                        p2 = (
                            new_col * self.grid.cell_size_mm + self.grid.cell_size_mm / 2,
                            new_row * self.grid.cell_size_mm + self.grid.cell_size_mm / 2,
                        )

                        valid, _ = self.drc_oracle.can_place_track_segment(
                            start=p1,
                            end=p2,
                            layer=layer,
                            net=self.net_name,
                            width=self.trace_width,
                        )
                        if not valid:
                            continue

                    # Diagonal moves cost sqrt(2), cardinal moves cost 1
                    cost = 1.414 if (dr != 0 and dc != 0) else 1.0
                    neighbors.append((new_state, cost))
        
        # Layer transitions (vias)
        for target_layer in self.allowed_layers:
            if target_layer == layer:
                continue
            
            target_state = (row, col, target_layer)
            if self._is_valid_state(target_state):
                # Check via placement with DRC oracle
                if self.drc_oracle:
                    via_pos = (
                        col * self.grid.cell_size_mm + self.grid.cell_size_mm / 2,
                        row * self.grid.cell_size_mm + self.grid.cell_size_mm / 2,
                    )
                    valid, _ = self.drc_oracle.can_place_via(
                        position=via_pos,
                        diameter=self.via_diameter,
                        net=self.net_name,
                    )
                    if not valid:
                        continue

                neighbors.append((target_state, self.via_cost))
        
        return neighbors
    
    def _is_valid_state(self, state: Tuple[int, int, int]) -> bool:
        """Check if state is within bounds and not blocked."""
        row, col, layer = state
        
        if not self._is_within_bounds((row, col)):
            return False
        
        if layer not in self.allowed_layers:
            return False
        
        # Convert to mm for grid check
        x_mm = col * self.grid.cell_size_mm + self.grid.cell_size_mm / 2
        y_mm = row * self.grid.cell_size_mm + self.grid.cell_size_mm / 2
        
        return self.grid.is_available(x_mm, y_mm, layer, net_name=self.net_name)
    
    def _is_within_bounds(self, cell: Tuple[int, int]) -> bool:
        """Check if cell is within grid bounds."""
        row, col = cell
        return 0 <= row < self.grid.rows and 0 <= col < self.grid.cols
    
    def _heuristic(self, state: Tuple[int, int, int], goal_cell: Tuple[int, int], goal_layer: int) -> float:
        """Compute heuristic (octile distance + layer change penalty)."""
        row, col, layer = state
        goal_row, goal_col = goal_cell
        
        dr = abs(row - goal_row)
        dc = abs(col - goal_col)
        
        # Octile distance: max(dr, dc) + (sqrt(2)-1) * min(dr, dc)
        h = max(dr, dc) + 0.414 * min(dr, dc)
        
        # Add layer change penalty if needed
        if layer != goal_layer:
            h += self.via_cost
        
        return h
    
    def _reconstruct_bidirectional_path(
        self,
        meeting_point: Tuple[int, int, int],
        fwd_closed: Dict,
        bwd_closed: Dict,
        start_mm: Tuple[float, float],
        end_mm: Tuple[float, float],
    ) -> MultiLayerPath:
        """Reconstruct path by stitching forward and backward paths.
        
        Args:
            meeting_point: State where frontiers met
            fwd_closed: Forward closed set with parent pointers
            bwd_closed: Backward closed set with parent pointers
            start_mm: Start position in mm
            end_mm: End position in mm
            
        Returns:
            MultiLayerPath with complete route
        """
        # Reconstruct forward path (start -> meeting_point)
        fwd_path = []
        current = meeting_point
        while current in fwd_closed:
            fwd_path.append(current)
            _, parent = fwd_closed[current]
            if parent is None:
                break
            current = parent
        fwd_path.reverse()
        
        # Reconstruct backward path (meeting_point -> end)
        bwd_path = []
        current = meeting_point
        while current in bwd_closed:
            _, parent = bwd_closed[current]
            if parent is None:
                break
            bwd_path.append(parent)
            current = parent
        
        # Combine paths
        full_path = fwd_path + bwd_path
        
        # Convert to segments and vias
        segments = []
        via_positions = []
        total_cost = 0.0
        
        for i in range(len(full_path) - 1):
            row1, col1, layer1 = full_path[i]
            row2, col2, layer2 = full_path[i + 1]
            
            # Convert to mm with centering offset
            # Snap first and last points to exact mm coordinates to avoid dangling tracks
            if i == 0:
                p1 = start_mm
            else:
                p1 = (
                    col1 * self.grid.cell_size_mm + self.grid.cell_size_mm / 2,
                    row1 * self.grid.cell_size_mm + self.grid.cell_size_mm / 2,
                )
                
            if i == len(full_path) - 2:
                p2 = end_mm
            else:
                p2 = (
                    col2 * self.grid.cell_size_mm + self.grid.cell_size_mm / 2,
                    row2 * self.grid.cell_size_mm + self.grid.cell_size_mm / 2,
                )
            
            if layer1 == layer2:
                # Same layer - trace segment
                distance = math.sqrt((p2[0] - p1[0])**2 + (p2[1] - p1[1])**2)
                total_cost += distance
                segments.append(RouteSegment(
                    start=p1,
                    end=p2,
                    layer=layer1,
                ))
            else:
                # Layer change - via
                total_cost += self.via_cost
                via_positions.append((p1[0], p1[1], layer1, layer2))
        
        return MultiLayerPath(
            segments=segments,
            via_positions=via_positions,
            total_cost=total_cost,
        )
