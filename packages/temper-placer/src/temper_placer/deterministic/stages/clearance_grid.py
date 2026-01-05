import numpy as np
from dataclasses import dataclass
from ..state import BoardState
from .base import Stage

@dataclass
class ClearanceGrid:
    '''Multi-layer 2D grid tracking blocked and available cells for routing.'''
    
    width_mm: float
    height_mm: float
    cell_size_mm: float
    layer_count: int = 2  # Default to 2-layer for backward compatibility
    
    def __post_init__(self):
        self.cols = int(self.width_mm / self.cell_size_mm)
        self.rows = int(self.height_mm / self.cell_size_mm)
        # Create separate 2D grid for each layer
        # 0 = available, 1 = blocked
        self._grids = [np.zeros((self.rows, self.cols), dtype=np.uint8) for _ in range(self.layer_count)]
    
    def _mm_to_cell(self, x_mm: float, y_mm: float) -> tuple[int, int]:
        '''Convert mm coordinates to grid cell indices.'''
        col = int(x_mm / self.cell_size_mm)
        row = int(y_mm / self.cell_size_mm)
        return (row, col)
    
    def is_available(self, x_mm: float, y_mm: float, layer: int = 0) -> bool:
        '''Check if a position is available for routing on specified layer.'''
        if layer < 0 or layer >= self.layer_count:
            return False
        row, col = self._mm_to_cell(x_mm, y_mm)
        if 0 <= row < self.rows and 0 <= col < self.cols:
            return self._grids[layer][row, col] == 0
        return False  # Out of bounds = blocked
    
    def block_circle(self, center: tuple[float, float], 
                     radius_mm: float, clearance_mm: float, layer: int = 0):
        '''Block cells within radius + clearance of center on specified layer.'''
        if layer < 0 or layer >= self.layer_count:
            return
        total_radius = radius_mm + clearance_mm
        cx, cy = center
        
        # Calculate bounding box in grid coordinates
        min_col = max(0, int((cx - total_radius) / self.cell_size_mm))
        max_col = min(self.cols, int((cx + total_radius) / self.cell_size_mm) + 1)
        min_row = max(0, int((cy - total_radius) / self.cell_size_mm))
        max_row = min(self.rows, int((cy + total_radius) / self.cell_size_mm) + 1)
        
        # Mark cells within radius on specified layer
        for row in range(min_row, max_row):
            for col in range(min_col, max_col):
                cell_x = col * self.cell_size_mm + self.cell_size_mm / 2
                cell_y = row * self.cell_size_mm + self.cell_size_mm / 2
                dist = ((cell_x - cx)**2 + (cell_y - cy)**2)**0.5
                if dist <= total_radius:
                    self._grids[layer][row, col] = 1

    def block_trace(self, path: list[tuple[float, float]], 
                    width_mm: float, clearance_mm: float, layer: int = 0):
        '''Block cells along a trace path with given width and clearance on specified layer.'''
        if not path:
            return
            
        # Treat as a series of connected circles and rectangles
        # For simplicity, we can block a circle at each point and along each segment
        for i in range(len(path)):
            # Block circle at current point
            self.block_circle(path[i], width_mm / 2.0, clearance_mm, layer)
            
            if i < len(path) - 1:
                # Block segment between path[i] and path[i+1]
                self._block_segment(path[i], path[i+1], width_mm, clearance_mm, layer)

    def _block_segment(self, start: tuple[float, float], end: tuple[float, float],
                       width_mm: float, clearance_mm: float, layer: int = 0):
        '''Block cells along a straight segment on specified layer.'''
        if layer < 0 or layer >= self.layer_count:
            return
        total_radius = width_mm / 2.0 + clearance_mm
        x1, y1 = start
        x2, y2 = end
        
        # Calculate segment bounding box
        min_x = min(x1, x2) - total_radius
        max_x = max(x1, x2) + total_radius
        min_y = min(y1, y2) - total_radius
        max_y = max(y1, y2) + total_radius
        
        min_col = max(0, int(min_x / self.cell_size_mm))
        max_col = min(self.cols, int(max_x / self.cell_size_mm) + 1)
        min_row = max(0, int(min_y / self.cell_size_mm))
        max_row = min(self.rows, int(max_y / self.cell_size_mm) + 1)
        
        # Segment vector
        dx = x2 - x1
        dy = y2 - y1
        L2 = dx*dx + dy*dy
        
        if L2 == 0:
            return
            
        for row in range(min_row, max_row):
            for col in range(min_col, max_col):
                cell_x = col * self.cell_size_mm + self.cell_size_mm / 2
                cell_y = row * self.cell_size_mm + self.cell_size_mm / 2
                
                # Projection of point (cell_x, cell_y) onto segment
                t = ((cell_x - x1) * dx + (cell_y - y1) * dy) / L2
                t = max(0, min(1, t))
                
                proj_x = x1 + t * dx
                proj_y = y1 + t * dy
                
                dist = ((cell_x - proj_x)**2 + (cell_y - proj_y)**2)**0.5
                if dist <= total_radius:
                    self._grids[layer][row, col] = 1

    def unblock_circle(self, center: tuple[float, float], 
                       radius_mm: float, layer: int = 0):
        '''Unblock cells within radius of center on specified layer.'''
        if layer < 0 or layer >= self.layer_count:
            return
        cx, cy = center
        
        # Calculate bounding box in grid coordinates
        min_col = max(0, int((cx - radius_mm) / self.cell_size_mm))
        max_col = min(self.cols, int((cx + radius_mm) / self.cell_size_mm) + 1)
        min_row = max(0, int((cy - radius_mm) / self.cell_size_mm))
        max_row = min(self.rows, int((cy + radius_mm) / self.cell_size_mm) + 1)
        
        # Mark cells as available
        for row in range(min_row, max_row):
            for col in range(min_col, max_col):
                cell_x = col * self.cell_size_mm + self.cell_size_mm / 2
                cell_y = row * self.cell_size_mm + self.cell_size_mm / 2
                dist = ((cell_x - cx)**2 + (cell_y - cy)**2)**0.5
                if dist <= radius_mm:
                    self._grids[layer][row, col] = 0
    
    @property
    def blocked_count(self) -> int:
        '''Total blocked cells across all layers.'''
        return int(sum(np.sum(grid) for grid in self._grids))
    
    def blocked_count_on_layer(self, layer: int) -> int:
        '''Blocked cells on specific layer.'''
        if layer < 0 or layer >= self.layer_count:
            return 0
        return int(np.sum(self._grids[layer]))
    
    @property
    def blocked_cells(self) -> frozenset:
        '''Return frozenset of blocked (row, col, layer) tuples across all layers.'''
        blocked = []
        for layer_idx, grid in enumerate(self._grids):
            rows, cols = np.where(grid == 1)
            blocked.extend([(r, c, layer_idx) for r, c in zip(rows.tolist(), cols.tolist())])
        return frozenset(blocked)
    
    def blocked_cells_on_layer(self, layer: int) -> frozenset:
        '''Return frozenset of blocked (row, col) tuples on specific layer.'''
        if layer < 0 or layer >= self.layer_count:
            return frozenset()
        rows, cols = np.where(self._grids[layer] == 1)
        return frozenset(zip(rows.tolist(), cols.tolist()))

class ClearanceGridStage(Stage):

    def __init__(self, cell_size_mm: float = 0.5, layer_count: int = 2, pad_sizes: dict = None):
        self.cell_size_mm = cell_size_mm
        self.layer_count = layer_count
        self.pad_sizes = pad_sizes or {}



    @property

    def name(self) -> str:

        return "clearance_grid"

    

    def run(self, state: BoardState) -> BoardState:

        if not state.board:

            return state

            

        grid = ClearanceGrid(

            width_mm=state.board.width,

            height_mm=state.board.height,

            cell_size_mm=self.cell_size_mm,
            
            layer_count=self.layer_count

        )

        

        # Build placement map from BoardState
        placements_dict = dict(state.placements) if state.placements else {}
        
        # Use injected pad sizes
        pad_sizes = self.pad_sizes
        
        # Block pads if netlist exists
        if state.netlist:
            comp_refs = [c.ref for c in state.netlist.components]
            print(f"DEBUG: ClearanceGrid processing {len(comp_refs)} components: {comp_refs[:10]}...")
            if 'U_GATE' in comp_refs:
                 print("DEBUG: U_GATE is present in netlist components.")
            else:
                 print("DEBUG: U_GATE is NOT in netlist components!")

            for component in state.netlist.components:
                # Use placement from BoardState if available, otherwise initial
                pos = placements_dict.get(component.ref, component.initial_position)
                
                if pos is None:
                    continue  # Skip if no position available

                if 'GATE' in component.ref:
                    print(f"DEBUG: Found {component.ref} with {len(component.pins)} pins")

                for pin in component.pins:
                    pin_pos = (pos[0] + pin.position[0], pos[1] + pin.position[1])
                    
                    target_layers = []
                    # Default to all layers if unknown or THT
                    pin_layer = getattr(pin, 'layer', 'F.Cu')
                    
                    if pin_layer == 'F.Cu':
                        target_layers = [0]
                    elif pin_layer == 'B.Cu':
                        target_layers = [grid.layer_count - 1]
                    elif pin_layer == 'In1.Cu' and grid.layer_count > 1:
                        target_layers = [1]
                    elif pin_layer == 'In2.Cu' and grid.layer_count > 2:
                        target_layers = [2]
                    else:
                        # *.Cu, Multi-layer, or unknown -> Block all
                        target_layers = range(grid.layer_count)
                    
                    # Lookup actual pad size
                    pad_radius = 0.5
                    pad_key = (component.ref, pin.name)
                    real_pad = pad_sizes.get(pad_key)
                    
                    if real_pad:
                        # Use circumscribed radius approximation or max dim
                        pad_radius = max(real_pad.size.X, real_pad.size.Y) / 2.0
                        # Use circumscribed radius approximation or max dim
                        pad_radius = max(real_pad.size.X, real_pad.size.Y) / 2.0
                    
                    # Block pads on target layers with INFLATED clearance
                    # to account for trace width (0.25mm) and mask expansion (0.1mm for SMD, 0.15mm for PTH)
                    # Effective Clearing = PadRadius + ElecClearance + TraceHalfWidth + MaskMargin
                    
                    elec_clearance = 0.2
                    trace_half_width = 0.125
                    mask_expansion = getattr(pin, 'mask_expansion', 0.1)
                    
                    effective_clearance = elec_clearance + trace_half_width + mask_expansion
                    
                    for layer_idx in target_layers:
                        if layer_idx < grid.layer_count:
                            grid.block_circle(pin_pos, radius_mm=pad_radius, clearance_mm=effective_clearance, layer=layer_idx)

                    

        from dataclasses import replace

        return replace(state, grid=grid)
