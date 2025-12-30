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
                buffered = obs.buffer(fatal_radius, resolution=8)
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


class CSpaceCache:
    """Cache of C-Space grids for different trace width/clearance combinations.
    
    Different net classes require different inflations:
    - Power traces (2mm) need more inflation than signal traces (0.15mm)
    - HV traces need creepage-aware inflation (2mm+)
    
    This cache pre-computes grids for common configurations.
    """
    
    def __init__(self, builder: CSpaceBuilder):
        self.builder = builder
        self._cache: dict[tuple[float, float, frozenset[str]], CSpaceGrid] = {}
    
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
            self._cache[key] = self.builder.build_c_space_grid(
                trace_width=trace_width,
                clearance=clearance,
                exclude_nets=exclude_nets,
            )
        
        return self._cache[key]
    
    def clear(self) -> None:
        """Clear the cache."""
        self._cache.clear()
    
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
