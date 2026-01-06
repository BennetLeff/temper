import heapq
import math
from dataclasses import dataclass
from typing import List, Tuple, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .clearance_grid import ClearanceGrid
    from temper_placer.routing.constraints.drc_oracle import DRCOracle

@dataclass
class DeterministicAStar:
    '''A* pathfinder with deterministic tie-breaking for multi-layer boards.'''

    grid: 'ClearanceGrid'
    drc_oracle: Optional['DRCOracle'] = None
    net_name: str = ""
    trace_width: float = 0.25
    max_iterations: int = 2000  # Reduced for faster feedback (was 10000)
    relaxed_retry: bool = True    # Retry with neckdown if strict search fails

    def __post_init__(self):
        self._net_id = self.grid.get_net_id(self.net_name) if self.net_name else 0

    def find_path(self, start: Tuple[float, float],
                  end: Tuple[float, float],
                  layer: int = 0) -> Optional[List[Tuple[float, float]]]:
        '''Find shortest path from start to end on specified layer, or None if impossible.'''

        # Try strict search first
        path = self._search(start, end, layer, relaxed=False)
        if path:
            return path

        # If failed and relaxed retry enabled, try with neckdown clearances
        if self.relaxed_retry and self.drc_oracle:
            path = self._search(start, end, layer, relaxed=True)
            if path:
                return path

        return None  # No path found even with relaxed constraints

    def _search(self, start: Tuple[float, float],
                end: Tuple[float, float],
                layer: int,
                relaxed: bool = False) -> Optional[List[Tuple[float, float]]]:
        '''Internal A* search with optional relaxed constraints.'''
        start_cell = self.grid._mm_to_cell(*start)
        end_cell = self.grid._mm_to_cell(*end)

        # Check start/end are valid on specified layer
        if not self._is_valid(start_cell, layer) or not self._is_valid(end_cell, layer):
            return None

        # A* with deterministic tie-breaking
        # Priority: (f_score, tie_breaker, cell)
        open_set = [(0, self._tie_breaker(start_cell), start_cell)]
        came_from = {}
        g_score = {start_cell: 0}
        iterations = 0

        while open_set and iterations < self.max_iterations:
            iterations += 1
            _, _, current = heapq.heappop(open_set)

            if current == end_cell:
                return self._reconstruct_path(came_from, current, start, end)

            for neighbor, cost in self._get_neighbors(current, layer, relaxed=relaxed):
                tentative_g = g_score[current] + cost

                if neighbor not in g_score or tentative_g < g_score[neighbor]:
                    came_from[neighbor] = current
                    g_score[neighbor] = tentative_g
                    f_score = tentative_g + self._heuristic(neighbor, end_cell)
                    heapq.heappush(open_set,
                        (f_score, self._tie_breaker(neighbor), neighbor))

        if iterations >= self.max_iterations:
            print(f"WARNING: A* search for {self.net_name} exceeded {self.max_iterations} iterations")

        return None  # No path found
    
    def _is_valid(self, cell: Tuple[int, int], layer: int = 0) -> bool:
        '''Check if cell is within bounds and not blocked on specified layer.'''
        row, col = cell
        if row < 0 or row >= self.grid.rows:
            return False
        if col < 0 or col >= self.grid.cols:
            return False
        if layer < 0 or layer >= self.grid.layer_count:
            return False
        
        # Convert cell to mm for is_available check
        x_mm = col * self.grid.cell_size_mm + self.grid.cell_size_mm / 2
        y_mm = row * self.grid.cell_size_mm + self.grid.cell_size_mm / 2
        
        return self.grid.is_available(x_mm, y_mm, layer, net_id=self._net_id)
    
    def _get_neighbors(self, cell: Tuple[int, int], layer: int = 0, relaxed: bool = False) -> List[Tuple[Tuple[int, int], float]]:
        '''Get valid neighbors on specified layer (8-connected for determinism).'''
        row, col = cell
        # Fixed order for determinism
        candidates = [
            ((row - 1, col), 1.0),      # up
            ((row, col + 1), 1.0),      # right
            ((row + 1, col), 1.0),      # down
            ((row, col - 1), 1.0),      # left
            ((row - 1, col - 1), 1.414), # up-left
            ((row - 1, col + 1), 1.414), # up-right
            ((row + 1, col - 1), 1.414), # down-left
            ((row + 1, col + 1), 1.414), # down-right
        ]

        valid_neighbors = []
        for neighbor, cost in candidates:
            if not self._is_valid(neighbor, layer):
                continue

            # If oracle is present, perform proactive DRC check
            if self.drc_oracle:
                # Convert cells back to mm for oracle
                p1 = (col * self.grid.cell_size_mm + self.grid.cell_size_mm / 2,
                      row * self.grid.cell_size_mm + self.grid.cell_size_mm / 2)
                p2 = (neighbor[1] * self.grid.cell_size_mm + self.grid.cell_size_mm / 2,
                      neighbor[0] * self.grid.cell_size_mm + self.grid.cell_size_mm / 2)

                valid, _ = self.drc_oracle.can_place_track_segment(
                    start=p1,
                    end=p2,
                    layer=layer,
                    net=self.net_name,
                    width=self.trace_width,
                    neckdown=relaxed  # Use relaxed clearances if in relaxed mode
                )
                if not valid:
                    continue

            valid_neighbors.append((neighbor, cost))

        return valid_neighbors
    
    def _heuristic(self, a: Tuple[int, int], b: Tuple[int, int]) -> float:
        '''Euclidean distance heuristic.'''
        return math.sqrt((a[0] - b[0])**2 + (a[1] - b[1])**2)
    
    def _tie_breaker(self, cell: Tuple[int, int]) -> Tuple[int, int]:
        '''Deterministic tie-breaker: prefer lower row, then lower col.'''
        return cell  # Tuple comparison is deterministic
    
    def _reconstruct_path(self, came_from: dict, 
                          current: Tuple[int, int],
                          start: Tuple[float, float],
                          end: Tuple[float, float]) -> List[Tuple[float, float]]:
        '''Reconstruct path and convert to mm coordinates.'''
        path_cells = [current]
        while current in came_from:
            current = came_from[current]
            path_cells.append(current)
        path_cells.reverse()
        
        # Convert to mm
        # Note: We replace the first and last cells with the exact start/end coords
        # to avoid grid discretization artifacts at endpoints.
        path = []
        for i, (row, col) in enumerate(path_cells):
            if i == 0:
                path.append(start)
            elif i == len(path_cells) - 1:
                path.append(end)
            else:
                path.append((
                    col * self.grid.cell_size_mm + self.grid.cell_size_mm / 2,
                    row * self.grid.cell_size_mm + self.grid.cell_size_mm / 2
                ))
        return path