"""
Router V6 Stage 2.5: Build Occupancy Grid

Creates discretized routing grid for A* pathfinding.
Part of temper-8bj1 (Stage 2 - Channel Analysis)
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import numpy as np
from shapely import contains, points

from temper_placer.router_v6.routing_space import RoutingSpace


class CellState(Enum):
    """State of a grid cell."""

    FREE = 0  # Available for routing
    BLOCKED = 1  # Occupied by obstacle
    RESERVED = 2  # Reserved for specific net


@dataclass
class OccupancyGrid:
    """Discretized routing grid for pathfinding."""

    layer_name: str
    grid: np.ndarray  # 2D array of CellState values
    origin: tuple[float, float]  # (x, y) origin in mm
    cell_size: float  # Cell size in mm
    width_cells: int  # Grid width in cells
    height_cells: int  # Grid height in cells
    static_mask: np.ndarray | None = None  # Boolean mask of static obstacles (-1)

    @property
    def width_mm(self) -> float:
        """Grid width in mm."""
        return self.width_cells * self.cell_size

    @property
    def height_mm(self) -> float:
        """Grid height in mm."""
        return self.height_cells * self.cell_size

    def is_free(self, x_cell: int, y_cell: int) -> bool:
        """Check if a cell is free for routing."""
        if 0 <= x_cell < self.width_cells and 0 <= y_cell < self.height_cells:
            # 0 is Free
            return self.grid[y_cell, x_cell] == 0
        return False

    def is_blocked(self, x_cell: int, y_cell: int) -> bool:
        """Check if a cell is blocked."""
        if 0 <= x_cell < self.width_cells and 0 <= y_cell < self.height_cells:
            # != 0 is blocked (either static or dynamic)
            return self.grid[y_cell, x_cell] != 0
        return False

    def world_to_grid(self, x_mm: float, y_mm: float) -> tuple[int, int]:
        """Convert world coordinates (mm) to grid coordinates."""
        x_cell = int((x_mm - self.origin[0]) / self.cell_size)
        y_cell = int((y_mm - self.origin[1]) / self.cell_size)
        return (x_cell, y_cell)

    def grid_to_world(self, x_cell: int, y_cell: int) -> tuple[float, float]:
        """Convert grid coordinates to world coordinates (mm)."""
        x_mm = self.origin[0] + (x_cell + 0.5) * self.cell_size
        y_mm = self.origin[1] + (y_cell + 0.5) * self.cell_size
        return (x_mm, y_mm)

    @property
    def free_cell_count(self) -> int:
        """Count of free cells."""
        return int(np.sum(self.grid == CellState.FREE.value))

    @property
    def blocked_cell_count(self) -> int:
        """Count of blocked cells."""
        return int(np.sum(self.grid == CellState.BLOCKED.value))

    @property
    def occupancy_ratio(self) -> float:
        """Ratio of blocked cells to total cells."""
        total = self.width_cells * self.height_cells
        return self.blocked_cell_count / total if total > 0 else 0.0

    def downsample(self, factor: int = 2) -> OccupancyGrid:
        """Return a coarser grid with cells `factor`× larger.

        A coarse cell is blocked if any of its sub-cells are blocked.
        Used for coarse-to-fine A* routing (U4).
        """
        old_w, old_h = self.width_cells, self.height_cells
        new_w = max(1, old_w // factor)
        new_h = max(1, old_h // factor)
        new_grid = np.zeros((new_h, new_w), dtype=self.grid.dtype)
        for j in range(new_h):
            for i in range(new_w):
                patch = self.grid[
                    j * factor : min((j + 1) * factor, old_h),
                    i * factor : min((i + 1) * factor, old_w),
                ]
                new_grid[j, i] = CellState.BLOCKED.value if np.any(patch) else CellState.FREE.value
        return OccupancyGrid(
            layer_name=f"{self.layer_name}_coarse",
            grid=new_grid,
            origin=self.origin,
            cell_size=self.cell_size * factor,
            width_cells=new_w,
            height_cells=new_h,
        )

    def mark_path_blocked(
        self,
        path: list[tuple[float, float]],
        trace_width: float,
        clearance: float,
        net_id: int,
    ) -> None:
        """
        Mark cells occupied by a routed path (with clearance expansion).

        Args:
            path: List of (x, y) coordinates
            trace_width: Width of the trace in mm
            clearance: Required clearance in mm
            net_id: Unique positive integer ID for this net
        """
        # Calculate how many cells to block around center
        # width/2 + clearance gives blocking radius
        radius_mm = (trace_width / 2) + clearance
        expansion = int(np.ceil(radius_mm / self.cell_size))

        # Helper to mark a single point
        def mark_point(x_mm, y_mm):
            cx, cy = self.world_to_grid(x_mm, y_mm)

            x_start = max(0, cx - expansion)
            x_end = min(self.width_cells, cx + expansion + 1)
            y_start = max(0, cy - expansion)
            y_end = min(self.height_cells, cy + expansion + 1)

            # Use net_id to mark
            self.grid[y_start:y_end, x_start:x_end] = net_id

        # Mark all points in path
        if not path:
            return

        # Rasterize lines between points
        for i in range(len(path) - 1):
            p1 = path[i]
            p2 = path[i + 1]

            # Interpolate for smooth blocking if segment is long
            dist = ((p2[0] - p1[0]) ** 2 + (p2[1] - p1[1]) ** 2) ** 0.5
            steps = int(np.ceil(dist / (self.cell_size / 2)))  # 2x density for safety

            if steps > 0:
                for s in range(steps + 1):
                    t = s / steps
                    x = p1[0] + t * (p2[0] - p1[0])
                    y = p1[1] + t * (p2[1] - p1[1])
                    mark_point(x, y)

    def mark_segment_blocked(
        self,
        p1: tuple[float, float],
        p2: tuple[float, float],
        trace_width: float,
        clearance: float,
        net_id: int,
    ) -> None:
        """Mark a single segment blocked on THIS grid."""
        radius_mm = (trace_width / 2) + clearance
        expansion = int(np.ceil(radius_mm / self.cell_size))

        def mark_point(x_mm, y_mm):
            cx, cy = self.world_to_grid(x_mm, y_mm)
            x_start = max(0, cx - expansion)
            x_end = min(self.width_cells, cx + expansion + 1)
            y_start = max(0, cy - expansion)
            y_end = min(self.height_cells, cy + expansion + 1)
            self.grid[y_start:y_end, x_start:x_end] = net_id

        dist = ((p2[0] - p1[0]) ** 2 + (p2[1] - p1[1]) ** 2) ** 0.5
        steps = int(np.ceil(dist / (self.cell_size / 2)))

        if steps > 0:
            for s in range(steps + 1):
                t = s / steps
                x = p1[0] + t * (p2[0] - p1[0])
                y = p1[1] + t * (p2[1] - p1[1])
                mark_point(x, y)
        else:
            mark_point(p1[0], p1[1])

    def unmark_segment_blocked(
        self,
        p1: tuple[float, float],
        p2: tuple[float, float],
        trace_width: float,
        clearance: float,
        net_id: int,
    ) -> None:
        """Unmark a single segment from THIS grid."""
        radius_mm = (trace_width / 2) + clearance
        expansion = int(np.ceil(radius_mm / self.cell_size))

        def unmark_point(x_mm, y_mm):
            cx, cy = self.world_to_grid(x_mm, y_mm)
            x_start = max(0, cx - expansion)
            x_end = min(self.width_cells, cx + expansion + 1)
            y_start = max(0, cy - expansion)
            y_end = min(self.height_cells, cy + expansion + 1)
            region = self.grid[y_start:y_end, x_start:x_end]

            # Restore -1 if it was a static obstacle, otherwise set to 0
            if self.static_mask is not None:
                static_region = self.static_mask[y_start:y_end, x_start:x_end]
                # Identify cells that are currently our net
                net_mask = region == net_id
                # Set them to 0 (Free)
                region[net_mask] = 0
                # But if they were originally static, restore to -1
                region[static_region & net_mask] = -1
            else:
                region[region == net_id] = 0

        dist = ((p2[0] - p1[0]) ** 2 + (p2[1] - p1[1]) ** 2) ** 0.5
        steps = int(np.ceil(dist / (self.cell_size / 2)))

        if steps > 0:
            for s in range(steps + 1):
                t = s / steps
                x = p1[0] + t * (p2[0] - p1[0])
                y = p1[1] + t * (p2[1] - p1[1])
                unmark_point(x, y)
        else:
            unmark_point(p1[0], p1[1])

    def unmark_path(
        self,
        path: list[tuple[float, float]],
        trace_width: float,
        clearance: float,
        net_id: int,
    ) -> None:
        """
        Unmark cells occupied by a specific net.

        Only clears cells that are currently owned by net_id.
        Does NOT clear if another net has overwritten it (shouldn't happen in valid state)
        or if it's a static obstacle.
        """
        radius_mm = (trace_width / 2) + clearance
        expansion = int(np.ceil(radius_mm / self.cell_size))

        def unmark_point(x_mm, y_mm):
            cx, cy = self.world_to_grid(x_mm, y_mm)

            x_start = max(0, cx - expansion)
            x_end = min(self.width_cells, cx + expansion + 1)
            y_start = max(0, cy - expansion)
            y_end = min(self.height_cells, cy + expansion + 1)

            # Only clear cells equal to net_id
            region = self.grid[y_start:y_end, x_start:x_end]
            region[region == net_id] = 0  # Set back to Free.

        if not path:
            return

        for i in range(len(path) - 1):
            p1 = path[i]
            p2 = path[i + 1]
            dist = ((p2[0] - p1[0]) ** 2 + (p2[1] - p1[1]) ** 2) ** 0.5
            steps = int(np.ceil(dist / (self.cell_size / 2)))

            if steps > 0:
                for s in range(steps + 1):
                    t = s / steps
                    x = p1[0] + t * (p2[0] - p1[0])
                    y = p1[1] + t * (p2[1] - p1[1])
                    unmark_point(x, y)

    def get_blocking_nets(
        self,
        p1: tuple[float, float],
        p2: tuple[float, float],
    ) -> set[int]:
        """
        Identify which net IDs are blocking the line segment p1-p2.
        """
        blocking_ids = set()

        # Simple sampling along line
        dist = ((p2[0] - p1[0]) ** 2 + (p2[1] - p1[1]) ** 2) ** 0.5
        steps = int(np.ceil(dist / (self.cell_size / 2)))

        if steps > 0:
            for s in range(steps + 1):
                t = s / steps
                x = p1[0] + t * (p2[0] - p1[0])
                y = p1[1] + t * (p2[1] - p1[1])

                cx, cy = self.world_to_grid(x, y)
                if 0 <= cx < self.width_cells and 0 <= cy < self.height_cells:
                    val = self.grid[cy, cx]
                    if val > 0:  # Valid Net ID
                        blocking_ids.add(int(val))

        return blocking_ids

    def mark_via_blocked(
        self,
        x_mm: float,
        y_mm: float,
        via_diameter: float,
        clearance: float,
        net_id: int,
    ) -> None:
        """
        Mark cells blocked by a via (circular region).

        Vias block cells on the layer with their annular ring + clearance.

        Args:
            x_mm: Via center X in mm
            y_mm: Via center Y in mm
            via_diameter: Via annular ring diameter in mm
            clearance: Required clearance in mm
            net_id: Net ID owning this via
        """
        radius_mm = (via_diameter / 2) + clearance
        expansion = int(np.ceil(radius_mm / self.cell_size))

        cx, cy = self.world_to_grid(x_mm, y_mm)

        x_start = max(0, cx - expansion)
        x_end = min(self.width_cells, cx + expansion + 1)
        y_start = max(0, cy - expansion)
        y_end = min(self.height_cells, cy + expansion + 1)

        # Mark circular region
        for y in range(y_start, y_end):
            for x in range(x_start, x_end):
                # Check if within circular radius
                dist = ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5 * self.cell_size
                if dist <= radius_mm:
                    self.grid[y, x] = net_id


def mark_path_blocked_3d(
    grids: dict[str, "OccupancyGrid"],
    path_3d: list[tuple[float, float, str]],
    trace_width: float,
    clearance: float,
    net_id: int,
) -> None:
    """
    Mark a 3D path on per-layer grids.

    Each segment is marked on the grid corresponding to its layer.

    Args:
        grids: Dictionary of OccupancyGrid per layer
        path_3d: List of (x, y, layer) coordinates
        trace_width: Trace width in mm
        clearance: Clearance in mm
        net_id: Net ID for blocking
    """
    if len(path_3d) < 2:
        return

    # Group consecutive points by layer
    for i in range(len(path_3d) - 1):
        x1, y1, layer1 = path_3d[i]
        x2, y2, layer2 = path_3d[i + 1]

        # Mark on starting layer's grid
        if layer1 in grids:
            segment = [(x1, y1), (x2, y2)]
            grids[layer1].mark_path_blocked(segment, trace_width, clearance, net_id)


def build_occupancy_grid(
    routing_space: RoutingSpace,
    cell_size: float = 0.1,
    margin: float = 2.0,
    inflation_mm: float = 0.0,
) -> OccupancyGrid:
    """
    Build occupancy grid from routing space with C-Space inflation.

    Args:
        routing_space: Routing space from Stage 2.2
        cell_size: Grid cell size in mm (default 0.1mm)
        margin: Margin around routing area in mm
        inflation_mm: Buffer to erode free area by (for C-Space)

    Returns:
        OccupancyGrid with blocked cells marked
    """
    # Get board bounds from routing space
    x_min, y_min, x_max, y_max = routing_space.available_area.bounds

    # Add margin
    x_min -= margin
    y_min -= margin
    x_max += margin
    y_max += margin

    # Calculate grid dimensions
    width_mm = x_max - x_min
    height_mm = y_max - y_min

    width_cells = max(1, int(np.ceil(width_mm / cell_size)))
    height_cells = max(1, int(np.ceil(height_mm / cell_size)))

    # Initialize grid as all blocked (static obstacle)
    grid = np.full((height_cells, width_cells), -1, dtype=np.int16)

    # Use eroded area if inflation requested
    check_area = routing_space.available_area
    if inflation_mm > 0.1:  # Threshold to avoid tiny/empty buffers
        # Erode the available area (which is dilation of obstacles)
        check_area = routing_space.available_area.buffer(-inflation_mm, quad_segs=4)

    # Vectorized grid construction
    # 1. Create coordinate grids
    x_indices = np.arange(width_cells)
    y_indices = np.arange(height_cells)
    xx_idx, yy_idx = np.meshgrid(x_indices, y_indices)

    # 2. Convert to world coordinates
    xx_world = x_min + (xx_idx + 0.5) * cell_size
    yy_world = y_min + (yy_idx + 0.5) * cell_size

    # 3. Create Shapely points in batch
    # Flatten for vectorization
    flat_x = xx_world.ravel()
    flat_y = yy_world.ravel()
    batch_points = points(flat_x, flat_y)

    # 4. Check containment in batch
    # Note: check_area is a Polygon/MultiPolygon. contains() supports array input.
    mask_flat = contains(check_area, batch_points)

    # 5. Reshape and update grid
    mask = mask_flat.reshape(height_cells, width_cells)

    # Set Free (0) where mask is True (contained in available area)
    # The grid was initialized to -1 (Blocked)
    grid[mask] = 0

    # Record which cells were static obstacles (-1) before routing
    static_mask = grid == -1

    return OccupancyGrid(
        layer_name=routing_space.layer_name,
        grid=grid,
        origin=(x_min, y_min),
        cell_size=cell_size,
        width_cells=width_cells,
        height_cells=height_cells,
        static_mask=static_mask,
    )
