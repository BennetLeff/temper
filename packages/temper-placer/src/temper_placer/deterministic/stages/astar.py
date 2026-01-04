import heapq
import math
from dataclasses import dataclass
from typing import List, Tuple, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .clearance_grid import ClearanceGrid

@dataclass
class DeterministicAStar:
    '''A* pathfinder with deterministic tie-breaking.'''
    
    grid: 'ClearanceGrid'
    
    def find_path(self, start: Tuple[float, float], 
                  end: Tuple[float, float]) -> Optional[List[Tuple[float, float]]]:
        '''Find shortest path from start to end, or None if impossible.'''
        
        start_cell = self.grid._mm_to_cell(*start)
        end_cell = self.grid._mm_to_cell(*end)
        
        # Check start/end are valid
        if not self._is_valid(start_cell) or not self._is_valid(end_cell):
            return None
        
        # A* with deterministic tie-breaking
        # Priority: (f_score, tie_breaker, cell)
        # tie_breaker ensures deterministic ordering for equal f_scores
        open_set = [(0, self._tie_breaker(start_cell), start_cell)]
        came_from = {}
        g_score = {start_cell: 0}
        
        while open_set:
            _, _, current = heapq.heappop(open_set)
            
            if current == end_cell:
                return self._reconstruct_path(came_from, current, start, end)
            
            for neighbor, cost in self._get_neighbors(current):
                tentative_g = g_score[current] + cost
                
                if neighbor not in g_score or tentative_g < g_score[neighbor]:
                    came_from[neighbor] = current
                    g_score[neighbor] = tentative_g
                    f_score = tentative_g + self._heuristic(neighbor, end_cell)
                    heapq.heappush(open_set, 
                        (f_score, self._tie_breaker(neighbor), neighbor))
        
        return None  # No path found
    
    def _is_valid(self, cell: Tuple[int, int]) -> bool:
        '''Check if cell is within bounds and not blocked.'''
        row, col = cell
        if row < 0 or row >= self.grid.rows:
            return False
        if col < 0 or col >= self.grid.cols:
            return False
        return self.grid._grid[row, col] == 0
    
    def _get_neighbors(self, cell: Tuple[int, int]) -> List[Tuple[Tuple[int, int], float]]:
        '''Get valid neighbors (8-connected for determinism).'''
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
        return [(c, cost) for c, cost in candidates if self._is_valid(c)]
    
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