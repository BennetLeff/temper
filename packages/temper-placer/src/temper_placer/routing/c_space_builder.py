"""
C-Space Builder: Configuration Space Rasterization for Routing.

This module implements the robotics-standard approach to motion planning:
inflate obstacles by the "fatal radius" (trace_width/2 + clearance) and route
a dimensionless point through the resulting configuration space.

Uses OpenCV for fast rasterization (C++ backend) instead of pure Python loops.

Part of temper-v6u3: C-Space Builder: OpenCV Rasterization
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

try:
    import cv2
    HAS_OPENCV = True
except ImportError:
    HAS_OPENCV = False

try:
    from shapely.geometry import Polygon, MultiPolygon, box
    from shapely.ops import unary_union
    from shapely.affinity import translate
    HAS_SHAPELY = True
except ImportError:
    HAS_SHAPELY = False

if TYPE_CHECKING:
    from kiutils.board import Board as KiBoard
    from temper_placer.core.design_rules import DesignRules


@dataclass
class CSpaceConfig:
    """Configuration for C-Space grid generation."""
    
    resolution_mm: float = 0.1  # Grid cell size in mm
    default_trace_width: float = 0.2  # Default trace width in mm
    default_clearance: float = 0.2  # Default clearance in mm
    
    # Net class overrides
    power_trace_width: float = 2.0
    power_clearance: float = 0.3
    hv_trace_width: float = 1.0
    hv_clearance: float = 2.0  # Creepage requirement


@dataclass
class CSpaceGrid:
    """Result of C-Space rasterization."""
    
    grid: np.ndarray  # Binary grid: 0=free, 255=blocked
    origin: tuple[float, float]  # World origin (mm)
    resolution: float  # mm per pixel
    trace_width: float  # Trace width used for inflation
    clearance: float  # Clearance used for inflation
    
    @property
    def width_px(self) -> int:
        return self.grid.shape[1]
    
    @property
    def height_px(self) -> int:
        return self.grid.shape[0]
    
    @property
    def width_mm(self) -> float:
        return self.width_px * self.resolution
    
    @property
    def height_mm(self) -> float:
        return self.height_px * self.resolution
    
    def world_to_pixel(self, x_mm: float, y_mm: float) -> tuple[int, int]:
        """Convert world coordinates to pixel indices."""
        px = int((x_mm - self.origin[0]) / self.resolution)
        py = int((y_mm - self.origin[1]) / self.resolution)
        # Clamp to grid bounds
        px = max(0, min(px, self.width_px - 1))
        py = max(0, min(py, self.height_px - 1))
        return px, py
    
    def pixel_to_world(self, px: int, py: int) -> tuple[float, float]:
        """Convert pixel indices to world coordinates (cell center)."""
        x_mm = px * self.resolution + self.origin[0] + self.resolution / 2
        y_mm = py * self.resolution + self.origin[1] + self.resolution / 2
        return x_mm, y_mm
    
    def is_free(self, x_mm: float, y_mm: float) -> bool:
        """Check if a world coordinate is in free space."""
        px, py = self.world_to_pixel(x_mm, y_mm)
        return self.grid[py, px] == 0  # Note: numpy is row-major (y, x)
    
    def save_debug_image(self, path: Path) -> None:
        """Save grid as image for debugging."""
        if HAS_OPENCV:
            cv2.imwrite(str(path), self.grid)


class CSpaceBuilder:
    """Builds Configuration Space grids using OpenCV rasterization.
    
    The C-Space approach inflates every obstacle by the "fatal radius":
        fatal_radius = trace_width/2 + clearance
    
    A dimensionless point can then be routed through the resulting grid.
    Any path found is guaranteed to be DRC-valid (no clearance violations).
    """
    
    def __init__(
        self,
        width_mm: float,
        height_mm: float,
        origin: tuple[float, float] = (0.0, 0.0),
        config: CSpaceConfig | None = None,
    ):
        if not HAS_OPENCV:
            raise ImportError("OpenCV (cv2) is required for C-Space rasterization")
        if not HAS_SHAPELY:
            raise ImportError("Shapely is required for polygon inflation")
        
        self.config = config or CSpaceConfig()
        self.origin = origin
        self.width_mm = width_mm
        self.height_mm = height_mm
        
        # Compute grid dimensions
        self.width_px = int(math.ceil(width_mm / self.config.resolution_mm))
        self.height_px = int(math.ceil(height_mm / self.config.resolution_mm))
        
        # Cache for obstacle polygons
        self._obstacles: list[Polygon] = []
        self._obstacle_nets: list[str] = []  # Net name for each obstacle
    
    def add_obstacle(self, polygon: Polygon, net: str = "") -> None:
        """Add an obstacle polygon to the configuration space.
        
        Args:
            polygon: Shapely polygon representing the obstacle
            net: Net name (used to exclude same-net obstacles during routing)
        """
        if polygon.is_valid and not polygon.is_empty:
            self._obstacles.append(polygon)
            self._obstacle_nets.append(net)
    
    def add_pad(
        self,
        center_x: float,
        center_y: float,
        width: float,
        height: float,
        net: str = "",
    ) -> None:
        """Add a rectangular pad as an obstacle.
        
        Args:
            center_x, center_y: Pad center in mm
            width, height: Pad dimensions in mm
            net: Net name
        """
        half_w = width / 2
        half_h = height / 2
        polygon = box(
            center_x - half_w,
            center_y - half_h,
            center_x + half_w,
            center_y + half_h,
        )
        self.add_obstacle(polygon, net)
    
    def add_component_outline(
        self,
        center_x: float,
        center_y: float,
        width: float,
        height: float,
    ) -> None:
        """Add a component keepout zone.
        
        Args:
            center_x, center_y: Component center in mm
            width, height: Component dimensions in mm
        """
        half_w = width / 2
        half_h = height / 2
        polygon = box(
            center_x - half_w,
            center_y - half_h,
            center_x + half_w,
            center_y + half_h,
        )
        self.add_obstacle(polygon, net="__component__")
    
    def extract_obstacles_from_board(self, board: "KiBoard") -> None:
        """Extract all pad and component obstacles from a KiCad board.
        
        Args:
            board: kiutils Board object
        """
        for fp in board.footprints:
            fp_x = fp.position.X
            fp_y = fp.position.Y
            
            # Add component outline as keepout
            # Estimate bounds from pads if no explicit outline
            if fp.pads:
                min_x = min(p.position.X for p in fp.pads) - 0.5
                max_x = max(p.position.X for p in fp.pads) + 0.5
                min_y = min(p.position.Y for p in fp.pads) - 0.5
                max_y = max(p.position.Y for p in fp.pads) + 0.5
                width = max_x - min_x
                height = max_y - min_y
                center_x = fp_x + (min_x + max_x) / 2
                center_y = fp_y + (min_y + max_y) / 2
                self.add_component_outline(center_x, center_y, width, height)
            
            # Add pads
            for pad in fp.pads:
                abs_x = fp_x + pad.position.X
                abs_y = fp_y + pad.position.Y
                pad_w = pad.size.X if hasattr(pad.size, 'X') else 1.0
                pad_h = pad.size.Y if hasattr(pad.size, 'Y') else 1.0
                
                # Get net name
                net_name = ""
                if hasattr(pad, 'net') and pad.net:
                    if hasattr(pad.net, 'name'):
                        net_name = pad.net.name
                    elif hasattr(pad.net, 'number'):
                        # Look up net name from board
                        for net in board.nets:
                            if net.number == pad.net.number:
                                net_name = net.name
                                break
                
                self.add_pad(abs_x, abs_y, pad_w, pad_h, net_name)
    
    def build_c_space_grid(
        self,
        trace_width: float | None = None,
        clearance: float | None = None,
        exclude_nets: set[str] | None = None,
    ) -> CSpaceGrid:
        """Build the binary C-Space grid.
        
        Args:
            trace_width: Trace width in mm (uses config default if None)
            clearance: Required clearance in mm (uses config default if None)
            exclude_nets: Set of net names to exclude from obstacles
                         (used when routing a specific net that shouldn't
                         block its own pads)
        
        Returns:
            CSpaceGrid with binary occupancy (0=free, 255=blocked)
        """
        trace_width = trace_width or self.config.default_trace_width
        clearance = clearance or self.config.default_clearance
        exclude_nets = exclude_nets or set()
        
        # Calculate fatal radius
        fatal_radius = (trace_width / 2) + clearance
        
        # Filter obstacles (exclude same-net)
        filtered_obstacles = [
            obs for obs, net in zip(self._obstacles, self._obstacle_nets)
            if net not in exclude_nets
        ]
        
        if not filtered_obstacles:
            # No obstacles - return empty grid
            grid = np.zeros((self.height_px, self.width_px), dtype=np.uint8)
            return CSpaceGrid(
                grid=grid,
                origin=self.origin,
                resolution=self.config.resolution_mm,
                trace_width=trace_width,
                clearance=clearance,
            )
        
        # Inflate obstacles using Shapely buffer
        inflated = []
        for obs in filtered_obstacles:
            try:
                buffered = obs.buffer(fatal_radius, quad_segs=8)
                if not buffered.is_empty:
                    inflated.append(buffered)
            except Exception:
                # Skip invalid geometry
                pass
        
        if not inflated:
            grid = np.zeros((self.height_px, self.width_px), dtype=np.uint8)
            return CSpaceGrid(
                grid=grid,
                origin=self.origin,
                resolution=self.config.resolution_mm,
                trace_width=trace_width,
                clearance=clearance,
            )
        
        # Merge all inflated obstacles
        merged = unary_union(inflated)
        
        # Convert to pixel polygons
        pixel_polys = self._shapely_to_pixel_coords(merged)
        
        # Rasterize with OpenCV (runs in C++)
        grid = np.zeros((self.height_px, self.width_px), dtype=np.uint8)
        if pixel_polys:
            cv2.fillPoly(grid, pixel_polys, color=255)
        
        return CSpaceGrid(
            grid=grid,
            origin=self.origin,
            resolution=self.config.resolution_mm,
            trace_width=trace_width,
            clearance=clearance,
        )
    
    def _shapely_to_pixel_coords(
        self,
        geometry: Polygon | MultiPolygon,
    ) -> list[np.ndarray]:
        """Convert Shapely geometry to OpenCV polygon format.
        
        Args:
            geometry: Shapely Polygon or MultiPolygon
            
        Returns:
            List of numpy arrays, each shape (N, 1, 2) with int32 coords
        """
        result = []
        
        if isinstance(geometry, MultiPolygon):
            for poly in geometry.geoms:
                result.extend(self._polygon_to_pixel_array(poly))
        elif isinstance(geometry, Polygon):
            result.extend(self._polygon_to_pixel_array(geometry))
        
        return result
    
    def _polygon_to_pixel_array(self, polygon: Polygon) -> list[np.ndarray]:
        """Convert a single polygon (with holes) to OpenCV format."""
        result = []
        
        # Exterior ring
        if polygon.exterior:
            coords = list(polygon.exterior.coords)
            pixel_coords = [
                self._world_to_pixel(x, y) for x, y in coords
            ]
            arr = np.array(pixel_coords, dtype=np.int32).reshape(-1, 1, 2)
            result.append(arr)
        
        # Interior rings (holes) - OpenCV handles these specially
        # For simplicity, we skip holes in the initial implementation
        # They would be handled by drawing with color=0 after fillPoly
        
        return result
    
    def _world_to_pixel(self, x_mm: float, y_mm: float) -> tuple[int, int]:
        """Convert world coordinates to pixel indices."""
        px = int((x_mm - self.origin[0]) / self.config.resolution_mm)
        py = int((y_mm - self.origin[1]) / self.config.resolution_mm)
        # Clamp to grid bounds
        px = max(0, min(px, self.width_px - 1))
        py = max(0, min(py, self.height_px - 1))
        return px, py


class SoftCSpaceBuilder(CSpaceBuilder):
    """Extends CSpaceBuilder to generate gradient cost fields for HV/LV separation.
    
    Instead of a binary grid, this produces a float32 grid where:
    - Blocked areas (hard obstacles) have cost = infinity
    - Preferred clearance zones (soft obstacles) have high cost (e.g. 50.0)
    - Free space has cost = 1.0
    """

    NET_CLASS_RULES = {
        "MAINS": {"fatal": 1.5, "preferred": 4.5},
        "DC_BUS": {"fatal": 1.0, "preferred": 3.0},
        "LOGIC": {"fatal": 0.3, "preferred": 0.3},
    }

    def build_cost_grid(
        self,
        net_class: str = "LOGIC",
        exclude_nets: set[str] | None = None,
    ) -> np.ndarray:
        """Build a cost grid for the given net class.
        
        Args:
            net_class: Net class of the net being routed
            exclude_nets: Nets to exclude from obstacles
            
        Returns:
            np.ndarray of shape (height_px, width_px) with float32 costs
        """
        # 1. Initialize with unit cost
        grid = np.ones((self.height_px, self.width_px), dtype=np.float32)

        # 2. Hard obstacles (infinite cost)
        # We need to find obstacles that are NOT in the same class OR are from different nets
        # Actually, for safety, HV and LV should be separated.
        # If we are routing an LV net, HV obstacles should have a large soft radius.
        
        # Get rules for current net
        rules = self.NET_CLASS_RULES.get(net_class, self.NET_CLASS_RULES["LOGIC"])
        hard_radius = rules["fatal"]
        
        # Build hard obstacle mask
        c_space = self.build_c_space_grid(
            trace_width=0.0,  # Inflation handled by hard_radius
            clearance=hard_radius,
            exclude_nets=exclude_nets
        )
        grid[c_space.grid > 0] = np.inf
        
        # 3. Preferred clearance halo (high cost) for HV/LV separation
        # If we are LOGIC, we want to stay away from HV/MAINS/DC_BUS obstacles
        if net_class == "LOGIC":
            for other_class in ["MAINS", "DC_BUS"]:
                other_rules = self.NET_CLASS_RULES[other_class]
                soft_radius = other_rules["preferred"]
                
                # Find obstacles belonging to the other class
                # We need a way to know which obstacle belongs to which net/class
                # For now, let's assume we can filter them.
                # I'll update add_obstacle to take a class or use net name patterns.
                
                other_obstacles = [
                    obs for obs, net in zip(self._obstacles, self._obstacle_nets)
                    if self._is_net_in_class(net, other_class) and net not in (exclude_nets or set())
                ]
                
                if other_obstacles:
                    soft_mask = self._rasterize_inflated(other_obstacles, soft_radius)
                    # Apply high cost to soft zone (where it's not already infinite)
                    soft_zone = (soft_mask > 0) & (grid != np.inf)
                    grid[soft_zone] = 50.0
        
        # Conversely, if we are HV, we want to stay away from LOGIC
        elif net_class in ["MAINS", "DC_BUS"]:
            soft_radius = rules["preferred"]
            
            # Stay away from LOGIC obstacles
            logic_obstacles = [
                obs for obs, net in zip(self._obstacles, self._obstacle_nets)
                if self._is_net_in_class(net, "LOGIC") and net not in (exclude_nets or set())
            ]
            
            if logic_obstacles:
                soft_mask = self._rasterize_inflated(logic_obstacles, soft_radius)
                soft_zone = (soft_mask > 0) & (grid != np.inf)
                grid[soft_zone] = 50.0

        return grid

    def _is_net_in_class(self, net_name: str, net_class: str) -> bool:
        """Heuristic to determine net class from name."""
        name = net_name.upper()
        if net_class == "MAINS":
            return any(x in name for x in ["AC_L", "AC_N", "MAINS", "LINE", "NEUTRAL"])
        if net_class == "DC_BUS":
            return any(x in name for x in ["DC_BUS", "VBUS", "V+", "PGND"])
        if net_class == "LOGIC":
            return not (self._is_net_in_class(net_name, "MAINS") or self._is_net_in_class(net_name, "DC_BUS"))
        return False

    def _rasterize_inflated(self, obstacles: list[Polygon], radius: float) -> np.ndarray:
        """Rasterize obstacles inflated by radius using cv2.dilate."""
        # Convert Shapely to OpenCV polygons
        merged = unary_union(obstacles)
        pixel_polys = self._shapely_to_pixel_coords(merged)
        
        # Draw base obstacles
        base = np.zeros((self.height_px, self.width_px), dtype=np.uint8)
        if pixel_polys:
            cv2.fillPoly(base, pixel_polys, 255)
        
        # Dilate to create halo
        kernel_size = int(round(radius / self.config.resolution_mm * 2)) + 1
        if kernel_size <= 1:
            return base
            
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
        return cv2.dilate(base, kernel)

    def save_heatmap(self, grid: np.ndarray, path: Path) -> None:
        """Save cost grid as a heatmap image for verification.
        
        Args:
            grid: Cost grid (float32)
            path: Output file path
        """
        if not HAS_OPENCV:
            return
            
        # Normalize for visualization
        # Map inf to 255 (red), soft zone to 128 (yellow), free to 0 (blue)
        # Using a simple grayscale for now: inf=255, others scaled
        vis = np.zeros_like(grid, dtype=np.uint8)
        vis[grid == np.inf] = 255
        vis[grid == 50.0] = 128
        vis[grid == 1.0] = 0
        
        # Apply a colormap for better visibility
        heatmap = cv2.applyColorMap(vis, cv2.COLORMAP_JET)
        cv2.imwrite(str(path), heatmap)


@dataclass
class CacheStats:
    """Statistics for C-Space cache performance tracking.
    
    Used to verify cache efficiency during routing. The acceptance criterion
    for temper-3028 is >95% hit rate during typical routing operations.
    """
    
    hits: int = 0
    misses: int = 0
    
    @property
    def hit_rate(self) -> float:
        """Cache hit rate as a fraction (0.0 to 1.0)."""
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0
    
    def reset(self) -> None:
        """Reset statistics."""
        self.hits = 0
        self.misses = 0


class CSpaceCache:
    """Cache of C-Space grids for different trace width/clearance combinations.
    
    Different net classes require different inflations:
    - Power traces (2mm) need more inflation than signal traces (0.15mm)
    - HV traces need creepage-aware inflation (2mm+)
    
    This cache pre-computes grids for common configurations.
    
    Net Class Mapping (temper-3028):
    
    | Net Class | Trace Width | Clearance | Fatal Radius |
    |-----------|-------------|-----------|--------------|
    | Power     | 2.0mm       | 0.3mm     | 1.3mm        |
    | Signal    | 0.2mm       | 0.2mm     | 0.3mm        |
    | HV        | 1.0mm       | 2.0mm     | 2.5mm        |
    """
    
    def __init__(self, builder: CSpaceBuilder):
        self.builder = builder
        self._cache: dict[tuple[float, float, frozenset[str]], CSpaceGrid] = {}
        self.stats = CacheStats()
    
    def get_grid(
        self,
        trace_width: float,
        clearance: float,
        exclude_nets: set[str] | None = None,
    ) -> CSpaceGrid:
        """Get or compute C-Space grid for given parameters.
        
        Args:
            trace_width: Trace width in mm
            clearance: Required clearance in mm
            exclude_nets: Nets to exclude from obstacles
            
        Returns:
            Cached or newly computed CSpaceGrid
        """
        # Round to 3 decimal places for cache key
        key = (
            round(trace_width, 3),
            round(clearance, 3),
            frozenset(exclude_nets or set()),
        )
        
        if key not in self._cache:
            self.stats.misses += 1
            self._cache[key] = self.builder.build_c_space_grid(
                trace_width=trace_width,
                clearance=clearance,
                exclude_nets=exclude_nets,
            )
        else:
            self.stats.hits += 1
        
        return self._cache[key]
    
    def get_grid_for_net(
        self,
        net_name: str,
        design_rules: "DesignRules",
        net_class: str | None = None,
        exclude_nets: set[str] | None = None,
    ) -> CSpaceGrid:
        """Get C-Space grid appropriate for routing a specific net.
        
        Looks up trace_width and clearance from design rules based on
        net name/class, then delegates to get_grid(). This is the primary
        interface for net-class-aware routing (temper-3028).
        
        Args:
            net_name: Name of the net being routed
            design_rules: DesignRules containing net class definitions
            net_class: Optional explicit net class override
            exclude_nets: Nets to exclude from obstacles (typically {net_name})
            
        Returns:
            CSpaceGrid with appropriate inflation for this net's class
            
        Example:
            >>> from temper_placer.core.design_rules import create_temper_design_rules
            >>> rules = create_temper_design_rules()
            >>> grid = cache.get_grid_for_net("VCC", rules)  # Uses Power class
            >>> grid.trace_width
            1.0
        """
        rules = design_rules.get_rules_for_net(net_name, net_class)
        return self.get_grid(
            trace_width=rules.trace_width,
            clearance=rules.clearance,
            exclude_nets=exclude_nets,
        )
    
    def clear(self) -> None:
        """Clear the cache and reset statistics."""
        self._cache.clear()
        self.stats.reset()
    
    @property
    def cache_size(self) -> int:
        """Number of cached grids."""
        return len(self._cache)
    
    def memory_usage_mb(self) -> float:
        """Estimate memory usage of cached grids in MB."""
        total_bytes = sum(
            grid.grid.nbytes for grid in self._cache.values()
        )
        return total_bytes / (1024 * 1024)
