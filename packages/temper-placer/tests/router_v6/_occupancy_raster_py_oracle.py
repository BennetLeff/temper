"""Pinned Python oracle for ``router_v6/occupancy_grid.py`` (Wave-4 router_v6
grid rasterization cluster).

DO NOT EDIT -- THIS IS THE REFERENCE.
======================================
Every executable statement below (the ``CellState`` enum and the
``_OracleOccupancyGrid`` class body) is a **verbatim** ``git show``
extraction from commit ``28366722f3f1c905877f1dc08533ac18d3d8825b``
(``origin/main``, 2026-08-06) of ``temper_placer/router_v6/occupancy_grid.py``,
lines 27-386 (the ``CellState`` enum through the end of ``mark_via_blocked``).

The ONLY change from the ``git show`` text is a single mechanical
find-and-replace of the identifier ``OccupancyGrid`` -> ``_OracleOccupancyGrid``
(3 occurrences: the class declaration, the ``downsample`` return-type
annotation, and the ``downsample`` constructor call) so this class can be
instantiated standalone, side by side with the real (now Rust-backed)
``OccupancyGrid``, without colliding on the class name. Nothing else has
been reformatted, cleaned up, or "fixed" by this file.
``test_oracle_is_verbatim_copy`` (in the differential test module)
re-extracts the same commit/line-range via ``git show``, applies the same
single rename, and compares the result to this file's text character for
character.

Migrated kernels (this Wave-4 slice) and their oracle methods below:
  - ``mark_path_blocked`` / ``mark_segment_blocked`` (rectangular blocking,
    line-interpolated)
  - ``unmark_segment_blocked`` / ``unmark_path`` (rectangular clearing,
    line-interpolated; note the two are NOT symmetric -- only
    ``unmark_segment_blocked`` restores the ``static_mask`` sentinel)
  - ``get_blocking_nets`` (read-only sampling along a segment)
  - ``mark_via_blocked`` (circular blocking, per-cell integer-distance
    formula)
  - ``downsample`` (block-reduce max-pool, OR-of-nonzero over sub-blocks)

NOT migrated (glue / library-dependent -- see the differential module's
docstring and the crate's VERIFICATION.md for the reasoning):
  - ``build_occupancy_grid`` (Shapely/GEOS polygon containment + erosion --
    refused, see below)
  - ``world_to_grid`` / ``grid_to_world`` (trivial arithmetic; inlined into
    the migrated kernels' own bit-exact coordinate conversion instead of
    being ported as a standalone entry point)
  - ``is_free`` / ``is_blocked`` / ``free_cell_count`` / ``blocked_cell_count``
    / ``occupancy_ratio`` / ``width_mm`` / ``height_mm`` (trivial property
    accessors, already vectorized numpy or O(1))
  - ``mark_path_blocked_3d`` (thin per-layer dispatch loop; calls the
    now-Rust-backed ``mark_path_blocked``)
  - ``OccupancyGridStage`` / ``validate_occupancy_grid`` (stage
    orchestration / validation glue)
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

import numpy as np


class CellState(Enum):
    """State of a grid cell."""

    FREE = 0  # Available for routing
    BLOCKED = 1  # Occupied by obstacle
    RESERVED = 2  # Reserved for specific net


@dataclass
class _OracleOccupancyGrid:
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
        """Count of blocked cells (including static obstacles)."""
        # CellState.BLOCKED (1) covers dynamic obstacles; cells with -1
        # (the static_mask sentinel for board outline, keepouts, etc.) are
        # also impassable and should count toward the blocked total so
        # free + blocked == total_cells.
        blocked = int(np.sum(self.grid == CellState.BLOCKED.value))
        static = int(np.sum(self.grid == -1))
        return blocked + static

    @property
    def occupancy_ratio(self) -> float:
        """Ratio of blocked cells to total cells."""
        total = self.width_cells * self.height_cells
        return self.blocked_cell_count / total if total > 0 else 0.0

    def downsample(self, factor: int = 2) -> _OracleOccupancyGrid:
        """Return a coarser grid with cells `factor`× larger.

        A coarse cell is blocked if any of its sub-cells are blocked.
        Used for coarse-to-fine A* routing (U4).

        Vectorized block-reduce via reshape + np.any over factor axes.
        When the fine dimensions are not evenly divisible by ``factor``,
        the grid is padded with BLOCKED cells before pooling (conservative).
        """
        old_h, old_w = self.height_cells, self.width_cells
        new_h = max(1, math.ceil(old_h / factor))
        new_w = max(1, math.ceil(old_w / factor))

        pad_h = new_h * factor - old_h
        pad_w = new_w * factor - old_w

        arr = self.grid
        if pad_h > 0 or pad_w > 0:
            arr = np.pad(
                arr,
                ((0, pad_h), (0, pad_w)),
                mode="constant",
                constant_values=CellState.BLOCKED.value,
            )

        reshaped = arr.reshape(new_h, factor, new_w, factor)
        # max-pool: any blocked sub-cell => blocked coarse cell
        blocked = np.any(reshaped, axis=(1, 3))
        new_grid = np.where(blocked, CellState.BLOCKED.value, CellState.FREE.value).astype(
            self.grid.dtype
        )
        return _OracleOccupancyGrid(
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


