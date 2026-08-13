"""
Router V6 Stage 2.5: Build Occupancy Grid

Creates discretized routing grid for A* pathfinding.
Part of temper-8bj1 (Stage 2 - Channel Analysis)

Wave 4 migration note: the rasterisation kernels of ``OccupancyGrid``
(``mark_path_blocked``, ``mark_segment_blocked``, ``unmark_segment_blocked``,
``unmark_path``, ``get_blocking_nets``, ``mark_via_blocked``, ``downsample``)
now delegate to ``temper_geometry``'s ``occupancy_raster`` kernels
(``packages/temper-geometry/src/occupancy_raster.rs``); this module keeps
its original public API. ``build_occupancy_grid`` was NOT migrated: its hot
path is ``shapely.contains()`` (GEOS) over points sampled inside a polygon
produced by GEOS buffer-erosion -- opaque library behaviour with no
accessible bit-exact Rust equivalent, so it stays Python. See
``packages/temper-geometry/VERIFICATION.md`` for the full writeup.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from enum import Enum

import numpy as np
import temper_geometry as _tg
from shapely import contains, points

from temper_placer.deterministic.stages.base import Stage
from temper_placer.deterministic.state import BoardState
from temper_placer.router_v6.routing_space import RoutingSpace
from temper_placer.router_v6.stage0_data import ParsedPCB
from temper_placer.router_v6.stage_validators import (
    StageDRCFailure,
    register_validator,
)

logger = logging.getLogger(__name__)


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

    def downsample(self, factor: int = 2) -> OccupancyGrid:
        """Return a coarser grid with cells `factor`× larger.

        A coarse cell is blocked if any of its sub-cells are blocked.
        Used for coarse-to-fine A* routing (U4).

        The block-reduce OR-pool is computed by
        ``temper_geometry.downsample_or_blocks_py`` (Wave 4). "Blocked" is
        "nonzero" for whatever dtype ``self.grid`` carries (production is
        always ``int8``, but this method also runs against ``int16`` test
        fixtures -- see the differential's dtype-tolerance test) --
        converted to a dtype-agnostic ``uint8`` mask before crossing the
        Rust boundary so the kernel never needs to know the grid's dtype.
        When the fine dimensions are not evenly divisible by ``factor``,
        out-of-bounds sub-cells are treated as BLOCKED (conservative),
        matching the pre-migration ``np.pad(..., constant_values=BLOCKED)``.
        """
        old_h, old_w = self.height_cells, self.width_cells
        mask_u8 = (self.grid != 0).astype(np.uint8)
        raw, new_h, new_w = _tg.downsample_or_blocks_py(mask_u8, old_h, old_w, factor)
        coarse_blocked = np.frombuffer(raw, dtype=np.uint8).reshape(new_h, new_w)
        new_grid = np.where(
            coarse_blocked != 0, CellState.BLOCKED.value, CellState.FREE.value
        ).astype(self.grid.dtype)
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
        _tg.mark_path_rect_into_grid_py(
            self.grid,
            path,
            trace_width,
            clearance,
            self.origin[0],
            self.origin[1],
            self.cell_size,
            net_id,
        )

    def mark_segment_blocked(
        self,
        p1: tuple[float, float],
        p2: tuple[float, float],
        trace_width: float,
        clearance: float,
        net_id: int,
    ) -> None:
        """Mark a single segment blocked on THIS grid."""
        _tg.mark_segment_rect_into_grid_py(
            self.grid,
            p1[0],
            p1[1],
            p2[0],
            p2[1],
            trace_width,
            clearance,
            self.origin[0],
            self.origin[1],
            self.cell_size,
            net_id,
        )

    def unmark_segment_blocked(
        self,
        p1: tuple[float, float],
        p2: tuple[float, float],
        trace_width: float,
        clearance: float,
        net_id: int,
    ) -> None:
        """Unmark a single segment from THIS grid."""
        static_u8 = self.static_mask.view(np.uint8) if self.static_mask is not None else None
        _tg.unmark_segment_rect_into_grid_py(
            self.grid,
            static_u8,
            p1[0],
            p1[1],
            p2[0],
            p2[1],
            trace_width,
            clearance,
            self.origin[0],
            self.origin[1],
            self.cell_size,
            net_id,
        )

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

        Note: unlike ``unmark_segment_blocked``, this does NOT consult
        ``static_mask`` -- a real asymmetry in the pre-migration
        implementation, preserved here rather than "fixed".
        """
        _tg.unmark_path_rect_into_grid_py(
            self.grid,
            path,
            trace_width,
            clearance,
            self.origin[0],
            self.origin[1],
            self.cell_size,
            net_id,
        )

    def get_blocking_nets(
        self,
        p1: tuple[float, float],
        p2: tuple[float, float],
    ) -> set[int]:
        """
        Identify which net IDs are blocking the line segment p1-p2.
        """
        ids = _tg.blocking_net_ids_py(
            self.grid,
            p1[0],
            p1[1],
            p2[0],
            p2[1],
            self.origin[0],
            self.origin[1],
            self.cell_size,
        )
        return set(ids)

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
        _tg.mark_via_circle_into_grid_py(
            self.grid,
            x_mm,
            y_mm,
            via_diameter,
            clearance,
            self.origin[0],
            self.origin[1],
            self.cell_size,
            net_id,
        )


def mark_path_blocked_3d(
    grids: dict[str, OccupancyGrid],
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
    grid = np.full((height_cells, width_cells), -1, dtype=np.int8)

    # Use eroded area if inflation requested.
    #
    # This guard used to read ``if inflation_mm > 0.1``, commented "Threshold
    # to avoid tiny/empty buffers". That is a MAGNITUDE proxy for two distinct
    # hazards, and it is measurably a bad proxy for both (all figures from the
    # #1082 placed board's four production routing spaces, see
    # docs/evidence/2026-08-12-clearance-floor-reland.md):
    #
    #   "tiny"  -- does not exist. ``buffer(-1e-9)`` over all four layers costs
    #              0.042s, returns valid non-empty geometry, and loses
    #              0.000000% of the area. There is no cost to guard against, so
    #              the threshold bought nothing on this side.
    #   "empty" -- is real, but lives two orders of magnitude away: the first
    #              layer to erode to EMPTY is F.Cu at inflation 10mm, In1/In2
    #              at 50mm. A 0.1mm threshold is 100x too small to catch it.
    #
    # What the threshold DID do is silently switch the C-space off at exactly
    # the value production passes. ``OccupancyGridStage`` passes
    # ``default_trace_width_mm / 2``, and once that was corrected 0.25 -> 0.20
    # (the clearance-floor fix) it became exactly 0.100 -- and ``0.1 > 0.1`` is
    # False. Measured: the erosion was skipped entirely and 94,991 cells across
    # the four layers that were reserved before became free, all of them the
    # ring hugging an obstacle boundary. The DRC consequence was 191 clearance
    # violations at ``actual 0.0000 mm`` on board C.
    #
    # So the predicate is the semantic one -- ANY positive inflation is a real
    # reservation and gets applied -- and the empty case is handled by looking
    # at the RESULT instead of guessing from the input. An empty erosion is
    # kept, not discarded: it means no trace of this width fits on this layer
    # at all, and blocking the layer is the true answer. Falling back to the
    # un-eroded area there would emit copper that violates by construction,
    # which is the whole defect class this fix belongs to. It is logged so the
    # cause is visible rather than surfacing as mass A* failure.
    check_area = routing_space.available_area
    if inflation_mm > 0:
        # Erode the available area (which is dilation of obstacles)
        check_area = routing_space.available_area.buffer(-inflation_mm, quad_segs=4)
        if check_area.is_empty:
            logger.warning(
                "C-space erosion emptied layer %s at inflation_mm=%r: no trace "
                "of this width fits anywhere on the layer, so every cell is "
                "blocked. This is a real geometric result, not a grid bug.",
                routing_space.layer_name,
                inflation_mm,
            )

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


class OccupancyGridStage(Stage):
    """Stage 2.5: Build occupancy grids from routing spaces."""

    @property
    def name(self) -> str:
        return "OccupancyGrid"

    def run(self, state: BoardState) -> BoardState:
        assert state._parsed_pcb is not None
        pcb: ParsedPCB = state._parsed_pcb
        base_inflation = pcb.design_rules.default_trace_width_mm / 2.0

        occupancy_grids: dict[str, OccupancyGrid] = {}
        for layer_name, routing_space in state.routing_spaces.items():  # type: ignore[union-attr]
            grid = build_occupancy_grid(routing_space, inflation_mm=base_inflation)
            occupancy_grids[layer_name] = grid
        return replace(state, occupancy_grids=occupancy_grids)


@register_validator("OccupancyGrid")
def validate_occupancy_grid(state: BoardState) -> list[StageDRCFailure]:
    """Validate occupancy grid invariants."""
    failures: list[StageDRCFailure] = []
    if state.occupancy_grids is None:
        failures.append(
            StageDRCFailure(
                field="occupancy_grids",
                value=None,
                reason="Occupancy grids not computed",
                stage="OccupancyGrid",
            )
        )
        return failures

    for layer_name, grid in state.occupancy_grids.items():
        if grid.width_cells <= 0 or grid.height_cells <= 0:
            failures.append(
                StageDRCFailure(
                    field="occupancy_grids",
                    value=layer_name,
                    reason="Non-positive grid dimensions: "
                    + repr((grid.width_cells, grid.height_cells)),
                    stage="OccupancyGrid",
                )
            )

    return failures
