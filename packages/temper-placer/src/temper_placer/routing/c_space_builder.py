
import cv2
import numpy as np
from dataclasses import dataclass
from typing import Tuple, List, Optional
from temper_placer.routing.constraints.spatial_index import Pad, Track, Via
from temper_placer.routing.constraints.geometry import Point

@dataclass
class CSpaceConfig:
    """Configuration for C-Space generation."""
    resolution_mm: float = 0.1  # Grid cell size in mm
    num_layers: int = 4  # Total copper layers

@dataclass
class CSpaceGrid:
    """Result of C-Space generation."""
    grid: np.ndarray  # Boolean grid (True=Blocked)
    origin: Tuple[float, float]
    resolution: float
    # Metadata for caching
    clearance: float
    trace_width: float

class CSpaceBuilder:
    """
    Builds Configuration Space (C-Space) grids from PCB geometry.
    
    The C-Space represents the free space available for routing a trace of a specific width
    with specific clearance requirements. It inflates all obstacles by:
        Inflation Radius = Clearance + (Trace Width / 2)
    """
    
    def __init__(self, width_mm: float, height_mm: float, origin: Tuple[float, float] = (0.0, 0.0), config: CSpaceConfig = None):
        """
        Initialize C-Space Builder.
        
        Args:
            width_mm: Board width in mm
            height_mm: Board height in mm
            origin: Board origin (x, y) in mm
            config: Configuration object
        """
        self.config = config or CSpaceConfig()
        self.origin = origin
        
        # Calculate grid dimensions + 1 for boundary safety
        self.grid_w = int(np.ceil(width_mm / self.config.resolution_mm)) + 1
        self.grid_h = int(np.ceil(height_mm / self.config.resolution_mm)) + 1
        self.num_layers = self.config.num_layers
        
        self.resolution = self.config.resolution_mm
        
        # Internal storage of static geometry
        self.pads: List[Pad] = []
        self.pads_by_net: dict[str, List[Pad]] = {}
        self.tracks: List[Track] = []
        self.vias: List[Via] = []

    def extract_obstacles_from_board(self, board) -> None:
        """
        Extract pads, tracks, and vias from a KiCad board object.
        This adapts external board objects to internal geometry types.
        """
        # Note: This mirrors internal_route.py's extraction logic but we store it here
        # for repeated rasterization with different radii.
        
        # 1. Pads
        for fp in board.footprints:
            # Absolute Transform Logic (From internal_route.py fix)
            if fp.position:
                fp_x, fp_y = fp.position.X, fp.position.Y
                fp_angle = fp.position.angle if fp.position.angle is not None else 0.0
            else:
                fp_x, fp_y, fp_angle = 0.0, 0.0, 0.0
                
            for pad in fp.pads:
                # Relative to Abs
                rel_x, rel_y = pad.position.X, pad.position.Y
                
                # Rotation
                import math
                rad = math.radians(fp_angle)
                cos_a, sin_a = math.cos(rad), math.sin(rad)
                rot_x = rel_x * cos_a - rel_y * sin_a
                rot_y = rel_x * sin_a + rel_y * cos_a
                abs_x = fp_x + rot_x
                abs_y = fp_y + rot_y
                
                # Absolute Rotation
                pad_rel_angle = pad.position.angle if pad.position.angle is not None else 0.0
                pad_abs_angle = fp_angle + pad_rel_angle
                
                # Sum Net Name
                net_name = pad.net.name if pad.net and hasattr(pad.net, "name") else str(pad.net)
                
                # Determine Layer
                # Default to All Layers (-1)
                layer_id = -1 
                if pad.layers:
                    if "*.Cu" in pad.layers:
                        layer_id = -1
                    elif "F.Cu" in pad.layers:
                        layer_id = 0
                    elif "B.Cu" in pad.layers:
                        layer_id = self.num_layers - 1
                    elif "In1.Cu" in pad.layers and self.num_layers > 2:
                        layer_id = 1
                    elif "In2.Cu" in pad.layers and self.num_layers > 3:
                        layer_id = 2
                
                # Store as internal Pad
                p = Pad(
                    center=Point(abs_x, abs_y),
                    size=(pad.size.X, pad.size.Y),
                    shape="circle" if pad.shape == "circle" else "rect",
                    rotation=pad_abs_angle,
                    net=net_name,
                    layer=layer_id
                )
                self.pads.append(p)
                if net_name not in self.pads_by_net:
                    self.pads_by_net[net_name] = []
                self.pads_by_net[net_name].append(p)
                
        # 2. Tracks/Vias (Pre-existing/Fanouts)
        # Assuming we treat them as obstacles unless they belong to the same net
        # (Router handles same-net exclusion separately, but builder generates base map)
        
        # (Skipping track extraction for now - C-Space usually built from Pads + Keepouts)
        # If we need incremental routing, we pass routed tracks as dynamic obstacles.

    def build_grid(self, clearance: float, trace_width: float, exclude_nets: set[str] = None) -> np.ndarray:
        """
        Generate a boolean grid where True = Blocked, False = Free.
        
        Args:
            clearance: Required clearance distance (mm)
            trace_width: Width of the trace being routed (mm)
            exclude_nets: Set of net names to IGNORE (i.e. don't block). 
                          Usually contains the net currently being routed.
        
        Returns:
            np.ndarray: Boolean grid (H, W, NumLayers)
        """
        exclude_nets = exclude_nets or set()
        
        # Initialize 3D grid (0 = Free)
        # Using boolean array to save space, will match MazeRouter (H, W, L) expectation
        # Note: MazeRouter uses [x, y, z] -> [width, height, layers]
        # But numpy uses [row, col] -> [y, x]. 
        # CSpaceBuilder uses Grid(H, W) usually.
        # Let's align on (H, W, L).
        grid_3d = np.zeros((self.grid_w, self.grid_h, self.num_layers), dtype=bool)
        
        # Total inflation radius
        # The center of the routing track cannot come closer than (clearance + width/2) to the obstacle edge.
        # So we inflate obstacles by this amount.
        inflation_mm = clearance + (trace_width / 2.0)
        inflation_px = int(np.ceil(inflation_mm / self.resolution))
        
        # Use uint8 buffers for drawing (OpenCV works on 2D)
        layer_buffers = [np.zeros((self.grid_h, self.grid_w), dtype=np.uint8) for _ in range(self.num_layers)]
        
        # Rasterize Pads
        for pad in self.pads:
            if pad.net in exclude_nets:
                continue
            
            # Determine target layers
            target_layers = []
            if pad.layer == -1:
                target_layers = list(range(self.num_layers))
            elif 0 <= pad.layer < self.num_layers:
                target_layers = [pad.layer]
            
            for lid in target_layers:
                self._draw_pad(layer_buffers[lid], pad, inflation_px, color=255)
                
        # Fill 3D Grid
        for lid in range(self.num_layers):
            # Transpose buffer (H, W) -> (W, H) to match [x, y]
            grid_3d[:, :, lid] = (layer_buffers[lid].T > 0)
            
        return grid_3d

    def unblock_pads(self, grid: np.ndarray, pads: List[Pad], clearance: float, trace_width: float) -> None:
        """
        Unblock specific pads from the grid (set to Free/False).
        Used for dynamic subtraction from cached base grids.
        """
        inflation_mm = clearance + (trace_width / 2.0)
        inflation_px = int(np.ceil(inflation_mm / self.resolution))
        
        # Grid is 3D bool (H, W, L)
        # Create temp mask for each layer? Or one shared mask if pads allow?
        # Pads have specific layers.
        
        layer_buffers = [np.zeros((self.grid_h, self.grid_w), dtype=np.uint8) for _ in range(self.num_layers)]
        
        for pad in pads:
            target_layers = []
            if pad.layer == -1:
                target_layers = list(range(self.num_layers))
            elif 0 <= pad.layer < self.num_layers:
                target_layers = [pad.layer]
            
            for lid in target_layers:
                self._draw_pad(layer_buffers[lid], pad, inflation_px, color=255)
        
        # Apply masks
        for lid in range(self.num_layers):
            mask = layer_buffers[lid]
            # Where mask is 255, set grid to False
            if np.any(mask):
                # Slice grid for this layer
                # grid is [x, y, layer] (W, H). mask is [row, col] (H, W).
                # Transpose mask to match grid.
                grid[:, :, lid][mask.T > 0] = False

    def _draw_pad(self, grid: np.ndarray, pad: Pad, inflation_px: int, color: int):
        """Helper to draw a single pad."""
        # Convert world to grid coords
        cx = int((pad.center.x - self.origin[0]) / self.resolution)
        cy = int((pad.center.y - self.origin[1]) / self.resolution)
        
        # Pad dimensions in pixels
        w_px = int(np.ceil(pad.size[0] / self.resolution))
        h_px = int(np.ceil(pad.size[1] / self.resolution))
        
        if pad.shape == "circle":
            radius_px = int(np.ceil(max(pad.size) / 2 / self.resolution)) + inflation_px
            cv2.circle(grid, (cx, cy), radius_px, color, -1)
        else: # Rect / RoundRect / Oval -> Treat as Rotated Rect
            # Create Rotated Rect points
            rect = ((cx, cy), (w_px + 2*inflation_px, h_px + 2*inflation_px), pad.rotation)
            box = cv2.boxPoints(rect)
            box = np.intp(box)
            cv2.drawContours(grid, [box], 0, color, -1)

    def visualize(self, grid: np.ndarray, filename: str = "cspace_debug.png"):
        """Debug helper to save grid as image."""
        cv2.imwrite(filename, (grid * 255).astype(np.uint8))

@dataclass
class CacheStats:
    """Statistics for C-Space Cache."""
    hits: int = 0
    misses: int = 0
    size_mb: float = 0.0

class CSpaceCache:
    """
    Caches C-Space grids to avoid re-rasterizing for every net.
    Groups nets with identical (clearance, width) requirements.
    """
    def __init__(self, builder: CSpaceBuilder):
        self.builder = builder
        self._cache = {} # Key: (clearance, width, exclude_net_tuple) -> CSpaceGrid
        self.stats = CacheStats()

    def get_grid(self, clearance: float, trace_width: float, exclude_nets: set[str] = None) -> CSpaceGrid:
        """
        Get C-Space grid for specific routing requirements.
        uses 'Base Grid' strategy: Cache fully blocked grid, then subtract own pads.
        """
        exclude_nets = exclude_nets or set()
        
        # Key for Base Grid (Geometry Only)
        # We don't include exclude_nets in the key anymore!
        base_key = (round(clearance, 4), round(trace_width, 4))
        
        if base_key in self._cache:
            self.stats.hits += 1
            base_c_space = self._cache[base_key]
        else:
            self.stats.misses += 1
            # Build Base Grid (Block EVERYTHING)
            raw_base_grid = self.builder.build_grid(clearance, trace_width, exclude_nets=set())
            
            base_c_space = CSpaceGrid(
                grid=raw_base_grid,
                origin=self.builder.origin,
                resolution=self.builder.resolution,
                clearance=clearance,
                trace_width=trace_width
            )
            self._cache[base_key] = base_c_space
            self.stats.size_mb += raw_base_grid.nbytes / 1024 / 1024
            
        # Now create specific grid for this request
        # 1. Copy Base Grid
        # Deep copy the numpy array!
        final_grid_map = base_c_space.grid.copy()
        
        # 2. Unblock pads for excluded nets
        pads_to_unblock = []
        for net in exclude_nets:
            if net in self.builder.pads_by_net:
                pads_to_unblock.extend(self.builder.pads_by_net[net])
                
        if pads_to_unblock:
            self.builder.unblock_pads(final_grid_map, pads_to_unblock, clearance, trace_width)
            
        return CSpaceGrid(
            grid=final_grid_map,
            origin=self.builder.origin,
            resolution=self.builder.resolution,
            clearance=clearance,
            trace_width=trace_width
        )

class SoftCSpaceBuilder(CSpaceBuilder):
    """
    Extensions for Soft C-Space (Gradient Cost Fields).
    """
    def build_cost_grid(self, net_class: str, exclude_nets: set[str] = None) -> np.ndarray:
        """
        Build a gradient cost field where cost increases closer to obstacles.
        Used to guide the router to the center of channels (maximum clearance).
        """
        # 1. Build hard binary grid (all obstacles)
        # Use minimal clearance for the binary mask to maximize available gradient space
        # Or just use the obstacles themselves (clearance=0) + TraceWidth/2?
        # Ideally, we want distance from *actual copper* (pads).
        
        # Determine strict blocking radius for this net class
        # But for soft field, we start from the *geometry*.
        
    def build_cost_grid(self, net_class: str, exclude_nets: set[str] = None) -> np.ndarray:
        """
        Build a 3D gradient cost field.
        """
        # 1. Build hard binary grid (3D)
        base_grid_3d = self.build_grid(clearance=0.0, trace_width=0.0, exclude_nets=exclude_nets)
        
        # Output 3D cost grid
        cost_grid_3d = np.zeros_like(base_grid_3d, dtype=np.float32)
        
        max_cost = 50.0
        decay_constant = self.resolution # 1mm decay scaling
        
        # Process each layer
        for lid in range(self.num_layers):
            # layer_binary is (W, H) (from build_grid)
            layer_binary = base_grid_3d[:, :, lid]
            
            # Invert for distance transform
            # Obstacles=0, Free=1. Need (H, W) for OpenCV.
            # So TRANSPOSE layer_binary.
            binary_img = (~layer_binary.T).astype(np.uint8)
            
            # Distance Transform (returns H, W)
            dist = cv2.distanceTransform(binary_img, cv2.DIST_L2, 5)
            
            # Cost Function
            layer_cost = max_cost * np.exp(-dist * decay_constant)
            
            # Store back (Transpose to W, H)
            cost_grid_3d[:, :, lid] = layer_cost.T
            
        return cost_grid_3d

