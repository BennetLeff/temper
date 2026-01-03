
from dataclasses import dataclass

import cv2
import numpy as np

from temper_placer.core.design_rules import NetClassRules
from temper_placer.routing.constraints.geometry import Point
from temper_placer.routing.constraints.spatial_index import Pad, Track, Via


@dataclass
class CSpaceConfig:
    """Configuration for C-Space generation."""
    resolution_mm: float = 0.1  # Grid cell size in mm
    num_layers: int = 4  # Total copper layers

@dataclass
class CSpaceGrid:
    """Result of C-Space generation."""
    grid: np.ndarray  # Boolean grid (True=Blocked)
    origin: tuple[float, float]
    resolution: float
    # Metadata for caching
    clearance: float
    trace_width: float

    def pixel_to_world(self, x_px: int, y_px: int) -> tuple[float, float]:
        """Convert grid pixel coordinates to world coordinates (mm)."""
        return (
            self.origin[0] + x_px * self.resolution,
            self.origin[1] + y_px * self.resolution
        )

    def world_to_pixel(self, x_mm: float, y_mm: float) -> tuple[int, int]:
        """Convert world coordinates (mm) to grid pixel coordinates."""
        return (
            int(np.round((x_mm - self.origin[0]) / self.resolution)),
            int(np.round((y_mm - self.origin[1]) / self.resolution))
        )

class CSpaceBuilder:
    """
    Builds Configuration Space (C-Space) grids from PCB geometry.

    The C-Space represents the free space available for routing a trace of a specific width
    with specific clearance requirements. It inflates all obstacles by:
        Inflation Radius = Clearance + (Trace Width / 2)
    """

    def __init__(self, width_mm: float, height_mm: float, origin: tuple[float, float] = (0.0, 0.0), config: CSpaceConfig = None):
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
        self.width_mm = width_mm
        self.height_mm = height_mm

        # Calculate grid dimensions + 1 for boundary safety
        self.grid_w = int(np.ceil(width_mm / self.config.resolution_mm)) + 1
        self.grid_h = int(np.ceil(height_mm / self.config.resolution_mm)) + 1
        self.num_layers = self.config.num_layers

        self.resolution = self.config.resolution_mm

        # Internal storage of static geometry
        self.pads: list[Pad] = []
        self.pads_by_net: dict[str, list[Pad]] = {}
        self.tracks: list[Track] = []
        self.vias: list[Via] = []

    def update_resolution(self, resolution_mm: float) -> None:
        """Update the grid resolution and re-calculate dimensions."""
        self.config.resolution_mm = resolution_mm
        self.resolution = resolution_mm
        self.grid_w = int(np.ceil(self.width_mm / resolution_mm)) + 1
        self.grid_h = int(np.ceil(self.height_mm / resolution_mm)) + 1

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

        # 2. Tracks (existing routed segments)
        # These are critical to avoid shorts with new routes
        if hasattr(board, "traceItems"):
            for item in board.traceItems:
                # Track segments
                if hasattr(item, "start") and hasattr(item, "end"):
                    # Determine layer ID
                    layer_id = self._layer_name_to_id(
                        item.layer if hasattr(item, "layer") else "F.Cu"
                    )
                    
                    # Resolve Net Name (item.net is an object in kiutils)
                    net_name = ""
                    if hasattr(item, "net") and item.net:
                        net_name = item.net.name if hasattr(item.net, "name") else str(item.net)

                    track = Track(
                        start=Point(item.start.X, item.start.Y),
                        end=Point(item.end.X, item.end.Y),
                        width=item.width if hasattr(item, "width") else 0.2,
                        net=net_name,
                        layer=layer_id,
                    )
                    self.tracks.append(track)

                # Vias (punch through all layers)
                elif hasattr(item, "position") and hasattr(item, "size"):
                    # Resolve Net Name
                    net_name = ""
                    if hasattr(item, "net") and item.net:
                        net_name = item.net.name if hasattr(item.net, "name") else str(item.net)

                    via = Via(
                        center=Point(item.position.X, item.position.Y),
                        diameter=item.size if hasattr(item, "size") else 0.6,
                        drill=item.drill if hasattr(item, "drill") else 0.3,
                        net=net_name,
                    )
                    self.vias.append(via)

        print(f"CSpace: Extracted {len(self.pads)} pads, {len(self.tracks)} tracks, {len(self.vias)} vias")

    def _layer_name_to_id(self, layer_name: str) -> int:
        """Convert KiCad layer name to internal layer ID."""
        if layer_name == 'F.Cu':
            return 0
        elif layer_name == 'In1.Cu':
            return 1 if self.num_layers > 2 else 0
        elif layer_name == 'In2.Cu':
            return 2 if self.num_layers > 3 else 0
        elif layer_name == 'B.Cu':
            return self.num_layers - 1
        return 0

    def build_raw_obstacle_grid(
        self, inflation_mm: float = 0.0, exclude_nets: set[str] = None
    ) -> np.ndarray:
        """Generate a boolean grid of obstacles with uniform inflation.

        Args:
            inflation_mm: Total inflation radius in mm
            exclude_nets: Nets to ignore

        Returns:
            np.ndarray: Boolean grid (W, H, NumLayers)
        """
        exclude_nets = exclude_nets or set()
        grid_3d = np.zeros((self.grid_w, self.grid_h, self.num_layers), dtype=bool)
        inflation_px = int(np.ceil(inflation_mm / self.resolution))

        layer_buffers = [
            np.zeros((self.grid_h, self.grid_w), dtype=np.uint8) for _ in range(self.num_layers)
        ]

        for pad in self.pads:
            if pad.net in exclude_nets:
                continue
            target_layers = (
                list(range(self.num_layers)) if pad.layer == -1 else [pad.layer]
            )
            for lid in target_layers:
                if 0 <= lid < self.num_layers:
                    self._draw_pad(layer_buffers[lid], pad, inflation_px, color=255)

        for track in self.tracks:
            if track.net in exclude_nets:
                continue
            target_layers = (
                list(range(self.num_layers)) if track.layer == -1 else [track.layer]
            )
            for lid in target_layers:
                if 0 <= lid < self.num_layers:
                    self._draw_track(layer_buffers[lid], track, inflation_px, color=255)

        for via in self.vias:
            if via.net in exclude_nets:
                continue
            for lid in range(self.num_layers):
                self._draw_via(layer_buffers[lid], via, inflation_px, color=255)

        for lid in range(self.num_layers):
            grid_3d[:, :, lid] = layer_buffers[lid].T > 0

        return grid_3d

    def build_grid(
        self, clearance: float, trace_width: float, class_name: str = "Default", exclude_nets: set[str] = None
    ) -> np.ndarray:
        """
        Generate a boolean grid where True = Blocked, False = Free.

        Args:
            clearance: Minimum clearance to maintain from obstacles
            trace_width: Trace width being routed
            class_name: Net class name (for zone awareness)
            exclude_nets: Set of net names to IGNORE (i.e. don't block).
                          Usually contains the net currently being routed.

        Returns:
            np.ndarray: Boolean grid (W, H, NumLayers)
        """
        exclude_nets = exclude_nets or set()

        # Initialize 3D grid (0 = Free)
        grid_3d = np.zeros((self.grid_w, self.grid_h, self.num_layers), dtype=bool)

        # Use uint8 buffers for drawing (OpenCV works on 2D)
        layer_buffers = [
            np.zeros((self.grid_h, self.grid_w), dtype=np.uint8) for _ in range(self.num_layers)
        ]

        # Rasterize Pads
        clearance_samples = []  # Debug: track clearance values
        for pad in self.pads:
            if pad.net in exclude_nets:
                continue

            # Check if this is a zone that should NOT block this class
            if pad.net.startswith("ZONE_"):
                # My Zone Bleeding fix logic: If net_name (class) is in zone's allowed classes, don't block.
                # Wait, I need to know the zone's allowed classes here.
                # Actually, in c_space_pipeline.py, I already added zones as obstacles ONLY if they don't match the class.
                pass

            inflation_mm = clearance + (trace_width / 2.0)
            inflation_px = int(np.ceil(inflation_mm / self.resolution))

            # Determine target layers
            target_layers = []
            if pad.layer == -1:
                target_layers = list(range(self.num_layers))
            elif 0 <= pad.layer < self.num_layers:
                target_layers = [pad.layer]

            for lid in target_layers:
                self._draw_pad(layer_buffers[lid], pad, inflation_px, color=255)

        # Rasterize Tracks (line segments)
        for track in self.tracks:
            if track.net in exclude_nets:
                continue

            # Dynamic Clearance
            clearance = matrix.get_clearance(net_name, track.net, track.start.x, track.start.y)
            inflation_mm = clearance + (trace_width / 2.0)
            inflation_px = int(np.ceil(inflation_mm / self.resolution))

            # Track layer
            target_layers = []
            if track.layer == -1:
                target_layers = list(range(self.num_layers))
            elif 0 <= track.layer < self.num_layers:
                target_layers = [track.layer]

            for lid in target_layers:
                self._draw_track(layer_buffers[lid], track, inflation_px, color=255)

        # Rasterize Vias (circles punching through all layers)
        for via in self.vias:
            if via.net in exclude_nets:
                continue

            # Dynamic Clearance
            clearance = matrix.get_clearance(net_name, via.net, via.center.x, via.center.y)
            inflation_mm = clearance + (trace_width / 2.0)
            inflation_px = int(np.ceil(inflation_mm / self.resolution))

            # Vias punch through all layers
            for lid in range(self.num_layers):
                self._draw_via(layer_buffers[lid], via, inflation_px, color=255)

        # Fill 3D Grid
        for lid in range(self.num_layers):
            grid_3d[:, :, lid] = layer_buffers[lid].T > 0

        return grid_3d

    def build_grid_zone_aware(
        self, matrix: "ClearanceMatrix", net_name: str, exclude_nets: set[str] = None
    ) -> np.ndarray:
        """Generate a zone-aware boolean C-Space grid.

        Now simply calls build_grid which implements dynamic spatial clearance.

        Args:
            matrix: ClearanceMatrix containing ZoneManager
            net_name: Name of net being routed
            exclude_nets: Nets to ignore

        Returns:
            np.ndarray: Boolean grid (W, H, NumLayers)
        """
        return self.build_grid(matrix, net_name, exclude_nets)

    def _create_zone_mask(self, polygon: list[tuple[float, float]]) -> np.ndarray:
        """Create a 2D binary mask from a polygon.

        Args:
            polygon: List of (x, y) coordinates in mm

        Returns:
            np.ndarray: uint8 mask (H, W) where 255 = inside
        """
        mask = np.zeros((self.grid_h, self.grid_w), dtype=np.uint8)

        # Convert mm to grid pixels
        pts = []
        for x, y in polygon:
            px = int(np.round((x - self.origin[0]) / self.resolution))
            py = int(np.round((y - self.origin[1]) / self.resolution))
            pts.append([px, py])

        pts_arr = np.array([pts], dtype=np.int32)
        cv2.fillPoly(mask, pts_arr, 255)

        return mask

    def _draw_track(self, buf: np.ndarray, track: 'Track', inflation_px: int, color: int):
        """Rasterize a track segment as a thick line."""
        # Convert mm to grid pixels
        x1 = int((track.start.x - self.origin[0]) / self.resolution)
        y1 = int((track.start.y - self.origin[1]) / self.resolution)
        x2 = int((track.end.x - self.origin[0]) / self.resolution)
        y2 = int((track.end.y - self.origin[1]) / self.resolution)

        # Track half-width in pixels (inflate by track width too)
        track_radius_px = int(np.ceil(track.width / 2.0 / self.resolution)) + inflation_px

        # Draw thick line
        cv2.line(buf, (x1, y1), (x2, y2), color, thickness=track_radius_px * 2)

    def _draw_via(self, buf: np.ndarray, via: 'Via', inflation_px: int, color: int):
        """Rasterize a via as a filled circle."""
        # Convert mm to grid pixels
        cx = int((via.center.x - self.origin[0]) / self.resolution)
        cy = int((via.center.y - self.origin[1]) / self.resolution)

        # Via radius in pixels (use outer diameter for obstacle)
        via_radius_px = int(np.ceil(via.diameter / 2.0 / self.resolution)) + inflation_px

        # Draw filled circle
        cv2.circle(buf, (cx, cy), via_radius_px, color, thickness=-1)

    def unblock_pads(self, grid: np.ndarray, pads: list[Pad], clearance: float, trace_width: float) -> None:
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

    def clear(self) -> None:
        """Clear the cache."""
        self._cache = {}
        self.stats = CacheStats()

    def get_grid(self, class_name: str, clearance: float, trace_width: float, exclude_nets: set[str] = None) -> CSpaceGrid:
        """
        Get C-Space grid for specific routing requirements.
        uses 'Base Grid' strategy: Cache fully blocked grid, then subtract own pads.
        """
        exclude_nets = exclude_nets or set()

        # Key for Base Grid (Geometry Only)
        # We don't include exclude_nets in the key anymore!
        base_key = (class_name, round(clearance, 4), round(trace_width, 4))

        if base_key in self._cache:
            self.stats.hits += 1
            base_c_space = self._cache[base_key]
        else:
            self.stats.misses += 1
            # Build Base Grid (Block EVERYTHING)
            raw_base_grid = self.builder.build_grid(clearance, trace_width, class_name=class_name, exclude_nets=set())

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
        # 1. Build hard binary grid (3D) using raw obstacles (no extra inflation)
        base_grid_3d = self.build_raw_obstacle_grid(inflation_mm=0.0, exclude_nets=exclude_nets)

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

