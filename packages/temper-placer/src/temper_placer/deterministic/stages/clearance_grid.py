import numpy as np
from dataclasses import dataclass
from ..state import BoardState
from .base import Stage

@dataclass
class ClearanceGrid:
    '''2D grid tracking blocked and available cells for routing.'''
    
    width_mm: float
    height_mm: float
    cell_size_mm: float
    
    def __post_init__(self):
        self.cols = int(self.width_mm / self.cell_size_mm)
        self.rows = int(self.height_mm / self.cell_size_mm)
        # 0 = available, 1 = blocked
        self._grid = np.zeros((self.rows, self.cols), dtype=np.uint8)
    
    def _mm_to_cell(self, x_mm: float, y_mm: float) -> tuple[int, int]:
        '''Convert mm coordinates to grid cell indices.'''
        col = int(x_mm / self.cell_size_mm)
        row = int(y_mm / self.cell_size_mm)
        return (row, col)
    
    def is_available(self, x_mm: float, y_mm: float) -> bool:
        '''Check if a position is available for routing.'''
        row, col = self._mm_to_cell(x_mm, y_mm)
        if 0 <= row < self.rows and 0 <= col < self.cols:
            return self._grid[row, col] == 0
        return False  # Out of bounds = blocked
    
    def block_circle(self, center: tuple[float, float], 
                     radius_mm: float, clearance_mm: float):
        '''Block cells within radius + clearance of center.'''
        total_radius = radius_mm + clearance_mm
        cx, cy = center
        
        # Calculate bounding box in grid coordinates
        min_col = max(0, int((cx - total_radius) / self.cell_size_mm))
        max_col = min(self.cols, int((cx + total_radius) / self.cell_size_mm) + 1)
        min_row = max(0, int((cy - total_radius) / self.cell_size_mm))
        max_row = min(self.rows, int((cy + total_radius) / self.cell_size_mm) + 1)
        
        # Mark cells within radius
        for row in range(min_row, max_row):
            for col in range(min_col, max_col):
                cell_x = col * self.cell_size_mm + self.cell_size_mm / 2
                cell_y = row * self.cell_size_mm + self.cell_size_mm / 2
                dist = ((cell_x - cx)**2 + (cell_y - cy)**2)**0.5
                if dist <= total_radius:
                    self._grid[row, col] = 1
    
    @property
    def blocked_count(self) -> int:
        return int(np.sum(self._grid))
    
    @property
    def blocked_cells(self) -> frozenset:
        '''Return frozenset of blocked (row, col) tuples.'''
        rows, cols = np.where(self._grid == 1)
        return frozenset(zip(rows.tolist(), cols.tolist()))

class ClearanceGridStage(Stage):
    @property
    def name(self) -> str:
        return "clearance_grid"
    
    def run(self, state: BoardState) -> BoardState:
        return state