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
    layer_count: int = 2
    
    def __post_init__(self):
        self.cols = int(self.width_mm / self.cell_size_mm)
        self.rows = int(self.height_mm / self.cell_size_mm)
        # 0 = free, -1 = multiple nets (restricted), -2 = obstacle, >0 = net ID
        self._trace_net_ids = [np.zeros((self.rows, self.cols), dtype=np.int32) for _ in range(self.layer_count)]
        self._pad_net_ids = [np.zeros((self.rows, self.cols), dtype=np.int32) for _ in range(self.layer_count)]
        # Map net names to IDs
        self._net_to_id = {}
        self._id_to_net = {}
        self._next_net_id = 1

    def get_net_id(self, net_name: str) -> int:
        '''Get or create unique integer ID for a net name.'''
        if not net_name:
            return 0
        if net_name not in self._net_to_id:
            self._net_to_id[net_name] = self._next_net_id
            self._id_to_net[self._next_net_id] = net_name
            self._next_net_id += 1
        return self._net_to_id[net_name]

    def _mm_to_cell(self, x_mm: float, y_mm: float) -> tuple[int, int]:
        '''Convert mm coordinates to grid cell indices.'''
        col = int(x_mm / self.cell_size_mm)
        row = int(y_mm / self.cell_size_mm)
        return (row, col)
    
    def is_available(self, x_mm: float, y_mm: float, layer: int = 0, net_name: str = None, net_id: int = None) -> bool:
        '''Check if a position is available for routing on specified layer.'''
        if layer < 0 or layer >= self.layer_count:
            return False
        row, col = self._mm_to_cell(x_mm, y_mm)
        if 0 <= row < self.rows and 0 <= col < self.cols:
            if net_id is None and net_name:
                net_id = self.get_net_id(net_name)
            
            # Check traces
            t_id = self._trace_net_ids[layer][row, col]
            if t_id != 0 and t_id != net_id:
                return False
            
            # Check pads
            p_id = self._pad_net_ids[layer][row, col]
            if p_id != 0 and p_id != net_id:
                return False
            
            return True
        return False  # Out of bounds = blocked
    
    def block_circle(self, center: tuple[float, float], 
                     radius_mm: float, clearance_mm: float, layer: int = 0, 
                     net_name: str = None, is_pad: bool = True):
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
        
        if net_name:
            net_id = self.get_net_id(net_name)
        else:
            net_id = -2 # Generic obstacle

        target_grid = self._pad_net_ids[layer] if is_pad else self._trace_net_ids[layer]

        # Mark cells
        for row in range(min_row, max_row):
            for col in range(min_col, max_col):
                cell_x = col * self.cell_size_mm + self.cell_size_mm / 2
                cell_y = row * self.cell_size_mm + self.cell_size_mm / 2
                dist = ((cell_x - cx)**2 + (cell_y - cy)**2)**0.5
                if dist <= total_radius:
                    curr = target_grid[row, col]
                    if curr == 0:
                        target_grid[row, col] = net_id
                    elif curr != net_id:
                        target_grid[row, col] = -1 # Multiple nets/Conflict

    def block_trace(self, path: list[tuple[float, float]], 
                    width_mm: float, clearance_mm: float, layer: int = 0, net_name: str = None):
        '''Block cells along a trace path with given width and clearance on specified layer.'''
        if not path:
            return
            
        # Treat as a series of connected circles and rectangles
        for i in range(len(path)):
            # Block circle at current point
            self.block_circle(path[i], width_mm / 2.0, clearance_mm, layer, net_name=net_name, is_pad=False)
            
            if i < len(path) - 1:
                # Block segment between path[i] and path[i+1]
                self._block_segment(path[i], path[i+1], width_mm, clearance_mm, layer, net_name=net_name)

    def _block_segment(self, start: tuple[float, float], end: tuple[float, float],
                       width_mm: float, clearance_mm: float, layer: int = 0, net_name: str = None):
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
            
        if net_name:
            net_id = self.get_net_id(net_name)
        else:
            net_id = -2

        target_grid = self._trace_net_ids[layer]

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
                    curr = target_grid[row, col]
                    if curr == 0:
                        target_grid[row, col] = net_id
                    elif curr != net_id:
                        target_grid[row, col] = -1

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
        
        # Mark cells as available in both grids
        for row in range(min_row, max_row):
            for col in range(min_col, max_col):
                cell_x = col * self.cell_size_mm + self.cell_size_mm / 2
                cell_y = row * self.cell_size_mm + self.cell_size_mm / 2
                dist = ((cell_x - cx)**2 + (cell_y - cy)**2)**0.5
                if dist <= radius_mm:
                    self._trace_net_ids[layer][row, col] = 0
                    self._pad_net_ids[layer][row, col] = 0
    
    @property
    def blocked_count(self) -> int:
        '''Total blocked cells across all layers.'''
        count = 0
        for l in range(self.layer_count):
            count += np.sum(self._trace_net_ids[l] != 0)
            count += np.sum(self._pad_net_ids[l] != 0)
        return int(count)
    
    def blocked_count_on_layer(self, layer: int) -> int:
        '''Blocked cells on specific layer.'''
        if layer < 0 or layer >= self.layer_count:
            return 0
        return int(np.sum(self._trace_net_ids[layer] != 0) + np.sum(self._pad_net_ids[layer] != 0))
    
    @property
    def blocked_cells(self) -> frozenset:
        '''Return frozenset of blocked (row, col, layer) tuples across all layers.'''
        blocked = []
        for layer_idx in range(self.layer_count):
            rows, cols = np.where((self._trace_net_ids[layer_idx] != 0) | (self._pad_net_ids[layer_idx] != 0))
            blocked.extend([(r, c, layer_idx) for r, c in zip(rows.tolist(), cols.tolist())])
        return frozenset(blocked)
    
    def blocked_cells_on_layer(self, layer: int) -> frozenset:
        '''Return frozenset of blocked (row, col) tuples on specific layer.'''
        if layer < 0 or layer >= self.layer_count:
            return frozenset()
        rows, cols = np.where((self._trace_net_ids[layer] != 0) | (self._pad_net_ids[layer] != 0))
        return frozenset(zip(rows.tolist(), cols.tolist()))

class ClearanceGridStage(Stage):

    def __init__(self, cell_size_mm: float = 0.5, layer_count: int = 2, pad_sizes: dict = None,
                 max_clearance_mm: float = 2.5, net_class_clearances: dict[str, float] = None):
        """Initialize clearance grid stage.

        Args:
            cell_size_mm: Grid cell size in mm
            layer_count: Number of copper layers
            pad_sizes: Optional dict of pad sizes
            max_clearance_mm: Maximum clearance to use for blocking (fallback if net class not found)
            net_class_clearances: Optional mapping of net class name to clearance in mm
        """
        self.cell_size_mm = cell_size_mm
        self.layer_count = layer_count
        self.pad_sizes = pad_sizes or {}
        self.max_clearance_mm = max_clearance_mm
        self.net_class_clearances = net_class_clearances or {}

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

        # Block pads from OTHER nets with net-class aware clearance buffer.
        # This allows routing TO target pads while avoiding shorts.
        # Pads are blocked with inflated radius = pad_r + clearance + trace_width/2 + mask

        if state.netlist:
            placements_dict = dict(state.placements) if state.placements else {}

            # Build net->pads mapping for selective unblocking
            net_pads = {}
            for component in state.netlist.components:
                pos = placements_dict.get(component.ref, component.initial_position)
                if pos is None:
                    continue

                for pin in component.pins:
                    pin_pos = (pos[0] + pin.position[0], pos[1] + pin.position[1])
                    pad_radius = 0.5
                    pad_key = (component.ref, pin.name)
                    if pad_key in self.pad_sizes:
                        real_pad = self.pad_sizes[pad_key]
                        pad_radius = max(real_pad.size.X, real_pad.size.Y) / 2.0

                    # Store pad info
                    net = pin.net or ''
                    if net not in net_pads:
                        net_pads[net] = []

                    # Determine target layers
                    if pin.is_pth or pin.layer == 'all':
                        target_layers = list(range(grid.layer_count))
                    elif pin.layer == 'F.Cu':
                        target_layers = [0]
                    elif pin.layer == 'B.Cu':
                        target_layers = [grid.layer_count - 1]
                    elif pin.layer == 'In1.Cu' and grid.layer_count > 1:
                        target_layers = [1]
                    elif pin.layer == 'In2.Cu' and grid.layer_count > 2:
                        target_layers = [2]
                    else:
                        target_layers = list(range(grid.layer_count))

                    net_pads[net].append({
                        'pos': pin_pos,
                        'radius': pad_radius,
                        'layers': target_layers,
                        'is_pth': pin.is_pth
                    })

            # Block all pads with per-net-class clearance
            for net_name, pads in net_pads.items():
                # Look up clearance for this net
                clearance = self.max_clearance_mm
                if net_name:
                    try:
                        net_obj = state.netlist.get_net(net_name)
                        net_class = net_obj.net_class
                        clearance = self.net_class_clearances.get(net_class, self.max_clearance_mm)
                    except (KeyError, ValueError):
                        pass

                for pad in pads:
                    for layer_idx in pad['layers']:
                        if layer_idx < grid.layer_count:
                            grid.block_circle(
                                pad['pos'],
                                radius_mm=pad['radius'],
                                clearance_mm=clearance,
                                layer=layer_idx,
                                net_name=net_name
                            )

        from dataclasses import replace

        return replace(state, grid=grid)
