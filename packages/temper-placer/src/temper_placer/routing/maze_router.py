"""
Simplified maze router for PCB routing verification (temper-wna.4).

This module implements A* pathfinding on a grid to verify routing feasibility.
It is used to VERIFY that paths exist, not for production-quality routing.
The router helps detect placements that cannot be routed.

Features:
- Grid-based occupancy map
- A* pathfinding for single nets
- Sequential routing in priority order
- Via support for layer transitions
- Rip-up and Reroute (RRR) support for conflict resolution
"""

import heapq
import logging
import math
import random
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import jax.numpy as jnp
import numpy as np
from jax import Array

from temper_placer.core.board import Board
from temper_placer.core.netlist import Component, Netlist
from temper_placer.routing.fast_router import (
    HAS_NUMBA,
    compute_distance_map_numba,
    dilate_grid_numba,
    find_path_astar_numba,
    find_path_astar_numba_adaptive,
)
from temper_placer.routing.layer_assignment import Layer, LayerAssignment
from temper_placer.io.export_types import TraceVia
from temper_placer.routing.via_array import calculate_via_array, should_use_via_array
from temper_placer.routing.safety_distances import (
    calculate_safety_distances,
    calculate_safety_distances,
    get_hv_lv_separation,
    is_high_voltage,
)
from temper_placer.routing.grid import GridConverter
from temper_placer.routing.difficulty import (
    compute_proximity_difficulty,
    compute_density_difficulty,
    get_cell_difficulty,
    compute_density_map,
    compute_local_density,
)
from temper_placer.routing.heuristics import GridCell

if TYPE_CHECKING:
    from temper_placer.core.board import LayerStackup
    from temper_placer.core.bus_cohort import BusCohortConstraint
    from temper_placer.core.netlist import Netlist
    from temper_placer.routing.constraints import DRCOracle
    from temper_placer.routing.layer_assignment import LayerAssignment
    from temper_placer.core.net_graph import NetGraph
    from temper_placer.core.design_rules import DesignRules, NetClassRules
    from temper_placer.routing.post_processing.funnel_smoother import Point
    from temper_placer.routing.post_processing.nudger import GeometricNudger
    from temper_placer.routing.post_processing.trace_ballooner import TraceBallooner
    from temper_placer.routing.post_processing.via_optimizer import ViaOptimizer
    from temper_placer.routing.post_processing.pipeline import PostProcessConfig, PostProcessingPipeline, PostProcessingResult
logger = logging.getLogger(__name__)


@dataclass
class ProfileStats:
    """Detailed performance profiling stats."""

    prepare_costs_ms: float = 0.0
    rip_up_ms: float = 0.0
    astar_total_ms: float = 0.0
    analyze_conflicts_ms: float = 0.0
    conflict_analysis_ms: float = 0.0
    numba_calls: int = 0
    python_calls: int = 0
    numba_time_ms: float = 0.0
    python_time_ms: float = 0.0
    dist_map_ms: float = 0.0
    dist_map_calls: int = 0
    dist_map_cache_hits: int = 0


@dataclass
class RoutingStats:
    """Statistics collected during routing."""

    total_time_ms: float = 0.0
    nets_routed: int = 0
    nets_failed: int = 0
    avg_time_per_net_ms: float = 0.0
    max_time_per_net_ms: float = 0.0
    total_astar_iterations: int = 0
    avg_iterations_per_path: float = 0.0
    profile: ProfileStats = field(default_factory=ProfileStats)


@dataclass
class RoutePath:
    """Result of routing a single net."""

    net: str
    cells: list[GridCell]
    length: float
    via_count: int
    success: bool
    cell_size: float = 0.2  # Grid cell size in mm used for this path
    difficulty: float = 0.0
    cell_difficulties: list[float] = field(default_factory=list)
    failure_reason: str | None = None
    smooth_points: list["Point"] = field(
        default_factory=list
    )  # World coordinates (mm) after smoothing

    # Trace geometry (from design rules)
    trace_width: float = 0.2  # Actual trace width used (mm)
    via_diameter: float = 0.6  # Via pad diameter (mm)
    via_drill: float = 0.3  # Via drill diameter (mm)

    # For advanced features like Via Arrays
    explicit_vias: list["TraceVia"] = field(default_factory=list)


@dataclass
class NetMetrics:
    """Metrics for net ordering heuristic."""

    net_name: str
    pin_count: int
    bounding_box_area: float
    estimated_wirelength: float
    is_power: bool
    is_ground: bool


@dataclass
class RoutingProgress:
    """Per-iteration routing metrics for progress tracking."""

    iteration: int
    total_iterations: int
    p_scale: float
    # Conflict breakdown
    total_conflicts: int
    overlap_conflicts: int  # cells with exactly 2 nets
    bottleneck_conflicts: int  # cells with 3+ nets (severe)
    # Routing metrics
    nets_routed: int
    nets_failed: int
    avg_path_length: float
    total_vias: int
    # Performance
    iteration_time_ms: float
    nets_per_second: float
    # Nets involved in conflicts
    conflicted_nets: list[str]


@dataclass
class NetStatus:
    """Convergence status for a single net."""

    net_name: str
    path_hash: int  # hash of current route for change detection
    conflict_free_count: int  # consecutive conflict-free iterations
    converged: bool  # True if stable for threshold iterations


# Net Class IDs for Creepage
CLASS_DEFAULT = 0
CLASS_HV = 1  # High Voltage (requires large creepage)
CLASS_LV = 2  # Low Voltage (requires small clearance)


class MazeRouter:
    """Grid-based maze router using A* pathfinding."""

    def __init__(
        self,
        grid_size: tuple[int, int],
        cell_size_mm: float = 1.0,
        num_layers: int = 1,
        origin: tuple[float, float] = (0.0, 0.0),
        via_cost: float = 1.0,
        layer_stackup: "LayerStackup | None" = None,
        soft_blocking: bool = False,
        congestion_via_discount: float = 0.1,
        layer_balance_weight: float = 0.5,
        min_clearance: float = 0.0,
        drc_oracle: "DRCOracle | None" = None,
        strict_mode: bool = False,
        design_rules: "DesignRules | None" = None,
        wrong_way_penalty: float = 2.0,
    ):
        self.grid_size = grid_size
        self.cell_size = cell_size_mm
        self.num_layers = num_layers
        self.origin = origin
        self.via_cost = via_cost
        self.wrong_way_penalty = wrong_way_penalty
        # soft_blocking determines how the router handles occupied cells (net overlaps):
        # - False (Strict): Occupied cells are impassable. Guarantees 0 tracks_crossing DRC errors.
        # - True (RRR/Negotiated): Occupied cells are passable at high cost.
        #   Allows Rip-up and Reroute to resolve conflicts over multiple iterations.
        self.soft_blocking = soft_blocking
        self.congestion_via_discount = (
            congestion_via_discount  # Via cost multiplier in congested areas
        )
        self.min_clearance = min_clearance
        self.design_rules = design_rules
        self._adaptive_unblocking_enabled = True # Enabled by default for retry recovery

        # Zone-aware clearance matrix (temper-d6kv.3)
        self.clearance_matrix: "ClearanceMatrix | None" = None

        if layer_stackup is None:
            from temper_placer.core.board import LayerStackup

            if num_layers == 2:
                self.layer_stackup = LayerStackup.default_2layer()
            else:
                self.layer_stackup = LayerStackup.default_4layer()
        else:
            self.layer_stackup = layer_stackup

        # Occupancy grid: 0=free, -1=blocked, 2=routed
        # Using numpy for mutable in-place updates (faster than JAX .at[].set())
        self.occupancy = np.zeros((grid_size[0], grid_size[1], num_layers), dtype=np.int32)
        # Class grid: 0=none, 1=HV, 2=LV (for creepage checks)
        self.class_grid = np.zeros((grid_size[0], grid_size[1], num_layers), dtype=np.int8)
        # RRR structures
        self.net_occupancy: dict[tuple[int, int, int], set[str]] = {}
        self.routed_paths: dict[str, RoutePath] = {}
        self.present_congestion = np.zeros(
            (grid_size[0], grid_size[1], num_layers), dtype=np.float32
        )
        self.history_cost = np.ones((grid_size[0], grid_size[1], num_layers), dtype=np.float32)

        # DRC-1: Cell ownership for net isolation (prevents shorts between nets)
        # Each cell is owned by exactly ONE net (first-come-first-served in strict mode)
        self.cell_owner: dict[tuple[int, int, int], str] = {}
        # owner_grid uses integer IDs for Numba compatibility (0=none, >0=net_id)
        self.owner_grid = np.zeros((grid_size[0], grid_size[1], num_layers), dtype=np.int32)
        self.net_to_id: dict[str, int] = {}
        self._next_net_id = 1

        # Post-processing cache
        self.optimized_geometry: "PCBGeometry | None" = None
        self.post_processing_metrics: dict[str, Any] = {}

        # Zone-aware clearance grid (temper-d6kv.2)
        # Stores the required clearance for each cell based on zone context
        # Initialized to default, updated per-net during routing via _precompute_clearance_grid()
        self.clearance_grid = np.full(
            (grid_size[0], grid_size[1], num_layers), fill_value=min_clearance, dtype=np.float32
        )

        self._component_positions: Array | None = None
        self.stats = RoutingStats()

        # Layer balancing
        self.layer_balance_weight = layer_balance_weight
        self.layer_usage_count = np.zeros(num_layers, dtype=np.int32)  # Track cells used per layer

        # Net convergence tracking for early termination
        self._net_status: dict[str, NetStatus] = {}

        # Numba optimization arrays (numpy views for JIT access)
        self._history_np: np.ndarray | None = None
        self._congestion_np: np.ndarray | None = None
        self._occupancy_np: np.ndarray | None = None
        self._soft_c_space_np: np.ndarray | None = None

        # DRC Oracle integration (temper-mado)
        self.drc_oracle = drc_oracle
        self.strict_mode = strict_mode
        self._current_net = None  # Set during route_net for DRC queries

        # Store default trace width for occupancy inflation (temper-z87d)
        self._default_trace_width_mm = 0.25  # Will be updated per-net

        # Soft C-Space cost field (HV/LV separation)
        self.soft_c_space: np.ndarray | None = None
        self._soft_c_space_np: np.ndarray | None = None

        # Hard C-Space grid (Binary blocking for static obstacles)
        self.c_space_grid: np.ndarray | None = None
        self._c_space_grid_np: np.ndarray | None = None

        # Initialize neckdown mask (cells where finer traces are allowed)
        self.neckdown_mask = np.zeros(grid_size + (num_layers,), dtype=bool)

        # Pad net mapping for track-through-pad prevention (temper-hdu8)
        self._pad_net_map: dict[tuple[int, int, int], str] = {}  # (gx, gy, layer) -> net

        # Pre-computed density map for O(1) cell difficulty lookup (temper-qjlk)
        self._density_map: np.ndarray | None = None

        # Net ID mapping for congestion tracking (temper-b577)
        self.net_to_id: dict[str, int] = {}
        self._next_net_id: int = 0

        # Grid converter for coordinate transformations (temper-mr01.7)
        self.grid_converter = GridConverter(
            grid_size=grid_size,
            cell_size=cell_size_mm,
            origin=origin,
        )

    def _get_net_id(self, net_name: str) -> int:
        """Get or create a unique integer ID for a net."""
        if net_name not in self.net_to_id:
            self.net_to_id[net_name] = self._next_net_id
            self._next_net_id += 1
        return self.net_to_id[net_name]

    def _get_inflated_cells(
        self,
        x: int,
        y: int,
        layer: int,
        width_mm: float = None,
        clearance_mm: float = None,
        all_layers: bool = False,
    ) -> list[tuple[int, int, int]]:
        """Get all cells that a shape at (x,y) with given width/clearance would occupy.

        This accounts for actual copper footprint plus clearance.

        Updated for temper-d6kv.3: Now reads from zone-aware clearance_grid when
        clearance_mm is None, enabling spatially-varying clearance requirements.

        Args:
            x, y, layer: Center cell
            width_mm: Shape width/diameter in mm (uses default trace width if None)
            clearance_mm: Minimum clearance in mm (if None, uses clearance_grid if available,
                         otherwise falls back to self.min_clearance)
            all_layers: If True, return cells for all layers at these (x, y) coordinates.

        Returns:
            List of (x, y, layer) tuples for all affected cells
        """
        width = width_mm if width_mm is not None else self._default_trace_width_mm

        # Zone-aware clearance (temper-d6kv.3): Read from grid when available
        if clearance_mm is not None:
            # Explicit clearance provided - use it
            clearance = clearance_mm
        elif hasattr(self, "clearance_grid") and self.clearance_grid is not None:
            # Use zone-aware clearance from precomputed grid
            # Bounds-check the grid access
            if 0 <= x < self.grid_size[0] and 0 <= y < self.grid_size[1]:
                clearance = float(self.clearance_grid[x, y, layer])
            else:
                clearance = self.min_clearance
        else:
            # No zone awareness - use default
            clearance = self.min_clearance

        # Inflation radius in cells: shape extends width/2 + clearance from center
        required_radius_mm = (width / 2.0) + clearance
        radius_cells = int(np.ceil(required_radius_mm / self.cell_size))

        cells = []
        layers = range(self.num_layers) if all_layers else [layer]

        for dx in range(-radius_cells, radius_cells + 1):
            for dy in range(-radius_cells, radius_cells + 1):
                nx, ny = x + dx, y + dy
                # Bounds check
                if 0 <= nx < self.grid_size[0] and 0 <= ny < self.grid_size[1]:
                    for l in layers:
                        cells.append((nx, ny, l))
        return cells

    @classmethod
    def from_board(
        cls,
        board: Board,
        cell_size_mm: float = 1.0,
        num_layers: int | None = None,
        via_cost: float = 1.0,
        soft_blocking: bool = False,
        congestion_via_discount: float = 0.1,
        min_clearance: float = 0.0,
        drc_oracle: "DRCOracle | None" = None,
        strict_mode: bool = False,
        design_rules: "DesignRules | None" = None,
        wrong_way_penalty: float = 2.0,
    ) -> "MazeRouter":
        # Infer num_layers from stackup if not specified
        if num_layers is None:
            if board.layer_stackup:
                num_layers = len(board.layer_stackup.layers)
            else:
                num_layers = 1

        width_cells = int(math.ceil(board.width / cell_size_mm))
        height_cells = int(math.ceil(board.height / cell_size_mm))

        # Parse clearance matrix from board for zone-aware routing (temper-d6kv.3)
        clearance_matrix = None
        try:
            from temper_placer.routing.constraints.design_rules import ClearanceMatrix

            clearance_matrix = ClearanceMatrix.parse(board)
        except Exception as e:
            # Clearance matrix parsing is optional - router works without it
            import logging

            logging.warning(f"Could not parse ClearanceMatrix: {e}")

        router = cls(
            grid_size=(width_cells, height_cells),
            cell_size_mm=cell_size_mm,
            num_layers=num_layers,
            origin=board.origin,
            via_cost=via_cost,
            layer_stackup=getattr(board, "layer_stackup", None),
            soft_blocking=soft_blocking,
            congestion_via_discount=congestion_via_discount,
            min_clearance=min_clearance,
            drc_oracle=drc_oracle,
            strict_mode=strict_mode,
            design_rules=design_rules,
            wrong_way_penalty=wrong_way_penalty,
        )

        # Assign clearance matrix after construction
        router.clearance_matrix = clearance_matrix

        return router

    def resize_grid(self, new_cell_size_mm: float) -> None:
        """Resize the routing grid to a new resolution.

        Preserves existing occupancy markings by mapping them to the new grid scale.
        This allows routing high-density parts on a fine grid and then switching
         to a coarser grid for standard nets to maintain performance.
        """
        if abs(self.cell_size - new_cell_size_mm) < 1e-6:
            return

        old_occupancy = self.occupancy
        old_cell_size = self.cell_size
        old_grid_size = self.grid_size

        # 1. Calculate new grid size matching board dimensions
        width_mm = old_grid_size[0] * old_cell_size
        height_mm = old_grid_size[1] * old_cell_size
        new_grid_size = (
            int(math.ceil(width_mm / new_cell_size_mm)),
            int(math.ceil(height_mm / new_cell_size_mm)),
        )

        logger.info(
            f"Resizing MazeRouter grid: {old_cell_size}mm ({old_grid_size[0]}x{old_grid_size[1]}) -> "
            f"{new_cell_size_mm}mm ({new_grid_size[0]}x{new_grid_size[1]})"
        )

        # 2. Re-initialize all grid and state structures
        old_cell_size = self.cell_size
        old_occupancy = self.occupancy
        old_owner_grid = self.owner_grid
        old_class_grid = self.class_grid
        old_pad_net_map = self._pad_net_map
        old_cell_owner = self.cell_owner
        old_net_occupancy = self.net_occupancy
        old_gc = self.grid_converter

        self.occupancy = np.zeros((*new_grid_size, self.num_layers), dtype=np.int32)
        self.owner_grid = np.zeros((*new_grid_size, self.num_layers), dtype=np.int32)
        self.class_grid = np.zeros((*new_grid_size, self.num_layers), dtype=np.int8)
        self.present_congestion = np.zeros((*new_grid_size, self.num_layers), dtype=np.float32)
        self.history_cost = np.ones((*new_grid_size, self.num_layers), dtype=np.float32)

        self.cell_owner = {}
        self.net_occupancy = {}
        self._pad_net_map = {}

        self.grid_size = new_grid_size
        self.cell_size = new_cell_size_mm

        # Update GridConverter (crucial for _world_to_grid consistency)
        self.grid_converter = GridConverter(
            grid_size=new_grid_size,
            cell_size=new_cell_size_mm,
            origin=self.origin,
        )

        # Reset A* acceleration views
        self._history_np = None
        self._congestion_np = None
        self._occupancy_np = None
        self._owner_np = None

        # 3. Map old occupancy to new grid
        factor = old_cell_size / new_cell_size_mm

        # Use simple mapping for now. For Fine -> Coarse, this is effectively Max-Pooling.
        indices = np.where(old_occupancy != 0)
        for x, y, l in zip(*indices):
            val = old_occupancy[x, y, l]

            if factor < 1.0:  # Downsampling (Fine -> Coarse) e.g. 0.05 -> 0.2 (0.25)
                # Map old index to new index
                # We want to be conservative. If ANY fine cell is blocked (-1), the coarse cell is blocked.

                # Check for empty slice issues with simple multiplication
                # Correct approach: Calculate range in new grid that overlaps with old cell
                # But since we iterate old cells, each old cell maps to exactly ONE new cell (center to center)
                nx = int((x + 0.5) * factor)
                ny = int((y + 0.5) * factor)

                if 0 <= nx < new_grid_size[0] and 0 <= ny < new_grid_size[1]:
                    n_key = (nx, ny, l)
                    current_val = self.occupancy[nx, ny, l]

                    # Priority: Blocked (-1) > Trace/Soft (2) > Empty (0)
                    if val == -1:
                        self.occupancy[nx, ny, l] = -1
                        # Migrate pad mapping if it was a pad
                        if (x, y, l) in old_pad_net_map:
                            self._pad_net_map[n_key] = old_pad_net_map[(x, y, l)]
                    elif val == 2:
                        if current_val != -1:
                            self.occupancy[nx, ny, l] = 2
                        
                        # Migrate ownership and class info
                        self.owner_grid[nx, ny, l] = old_owner_grid[x, y, l]
                        self.class_grid[nx, ny, l] = old_class_grid[x, y, l]
                        
                        if (x, y, l) in old_cell_owner:
                            self.cell_owner[n_key] = old_cell_owner[(x, y, l)]
                        if (x, y, l) in old_net_occupancy:
                            if n_key not in self.net_occupancy:
                                self.net_occupancy[n_key] = set()
                            self.net_occupancy[n_key].update(old_net_occupancy[(x, y, l)])

            else:  # Upsampling (Coarse -> Fine) e.g. 0.2 -> 0.05 (4.0)
                # Fill the region in the new grid
                nx_s = int(x * factor)
                nx_e = int((x + 1) * factor)
                ny_s = int(y * factor)
                ny_e = int((y + 1) * factor)

                self.occupancy[nx_s:nx_e, ny_s:ny_e, l] = val
                self.owner_grid[nx_s:nx_e, ny_s:ny_e, l] = old_owner_grid[x, y, l]
                self.class_grid[nx_s:nx_e, ny_s:ny_e, l] = old_class_grid[x, y, l]

                # Map dictionaries to the center cell of the new region
                cx = (nx_s + nx_e) // 2
                cy = (ny_s + ny_e) // 2
                n_key = (cx, cy, l)
                
                if (x, y, l) in old_pad_net_map:
                    self._pad_net_map[n_key] = old_pad_net_map[(x, y, l)]
                if (x, y, l) in old_cell_owner:
                    self.cell_owner[n_key] = old_cell_owner[(x, y, l)]
                if (x, y, l) in old_net_occupancy:
                    self.net_occupancy[n_key] = old_net_occupancy[(x, y, l)].copy()

        # 4. Scale routed_paths to new grid resolution
        # This is critical for RRR and rip-up to work in the new resolution.
        new_routed_paths = {}
        for net_name, path in self.routed_paths.items():
            new_cells = []
            seen_cells = set()
            for cell in path.cells:
                # Convert grid-coords back to world-coords, then to NEW grid-coords
                wx, wy = old_gc.grid_to_world(cell.x, cell.y)
                nx, ny = self.grid_converter.world_to_grid(wx, wy)
                
                new_key = (nx, ny, cell.layer)
                if new_key not in seen_cells:
                    new_cells.append(GridCell(nx, ny, cell.layer))
                    seen_cells.add(new_key)
            
            # Update path object with scaled cells and new grid resolution context
            path.cells = new_cells
            path.cell_size = new_cell_size_mm
            new_routed_paths[net_name] = path
            
        self.routed_paths = new_routed_paths

        # Sync congestion to reflect occupied cells
        self.present_congestion[self.occupancy != 0] = 1.0

    def rip_up_net(self, net_name: str) -> None:
        """Remove a net from the grid, ensuring full clearance zone removal."""
        if net_name not in self.routed_paths:
            return
        
        path = self.routed_paths[net_name]
        
        # Determine net class for correct inflation (mirroring _mark_path_occupied)
        required_clearance = self.min_clearance
        if self.design_rules:
            rules = self.design_rules.get_rules_for_net(net_name)
            required_clearance = rules.clearance

        # Identify Via locations
        via_coords = set()
        for i in range(1, len(path.cells)):
            c1, c2 = path.cells[i - 1], path.cells[i]
            if c1.layer != c2.layer:
                via_coords.add((c1.x, c1.y))
        for via in path.explicit_vias:
            gx, gy = self._world_to_grid(via.x, via.y)
            via_coords.add((gx, gy))

        unique_cells = set(path.cells)
        for cell in unique_cells:
            is_via = (cell.x, cell.y) in via_coords
            width = path.via_diameter if is_via else path.trace_width
            
            # Mirror the inflation logic used in _mark_path_occupied
            affected = self._get_inflated_cells(
                cell.x,
                cell.y,
                cell.layer,
                width_mm=width,
                clearance_mm=required_clearance,
                all_layers=is_via,
            )
            
            for ax, ay, al in affected:
                key = (ax, ay, al)
                if key in self.net_occupancy and net_name in self.net_occupancy[key]:
                    self.net_occupancy[key].remove(net_name)
                    
                    if not self.net_occupancy[key]:
                        # Grid state cleaning
                        if self.occupancy[ax, ay, al] == 2:
                            self.occupancy[ax, ay, al] = 0
                        self.class_grid[ax, ay, al] = CLASS_DEFAULT
                        self.owner_grid[ax, ay, al] = 0
                        if key in self.cell_owner:
                            del self.cell_owner[key]
                        del self.net_occupancy[key]
                    
                    # Decrement congestion map
                    self.present_congestion[ax, ay, al] = max(
                        0.0, self.present_congestion[ax, ay, al] - 1.0
                    )
        
        del self.routed_paths[net_name]

    def register_pre_routes(self, pre_routes: list["EscapePreRoute"]) -> None:
        """Register pre-routed escape traces that will be treated as fixed.

        These pre-routes are:
        1. Marked as occupied in the grid
        2. Not rip-up during RRR iterations (unless explicitly requested)
        3. Used as starting points for further routing

        Args:
            pre_routes: List of EscapePreRoute objects representing fixed escape traces
        """
        from temper_placer.routing.fanout import EscapePreRoute

        for pre_route in pre_routes:
            if not isinstance(pre_route, EscapePreRoute):
                continue

            net_name = pre_route.net_name
            cells = pre_route.to_grid_cells(self)

            for cell in cells:
                ax, ay, al = cell
                if 0 <= ax < self.grid_size[0] and 0 <= ay < self.grid_size[1]:
                    self.occupancy[ax, ay, al] = 2
                    self.present_congestion[ax, ay, al] += 1.0
                    key = (ax, ay, al)
                    if key not in self.net_occupancy:
                        self.net_occupancy[key] = set()
                    self.net_occupancy[key].add(net_name)
                    # DRC-1: Register ownership
                    self.cell_owner[(ax, ay, al)] = net_name

            if net_name not in self.routed_paths:
                self.routed_paths[net_name] = RoutePath(
                    net=net_name,
                    cells=[GridCell(c[0], c[1], c[2]) for c in cells],
                    length=len(cells),
                    via_count=0,
                    success=True,
                    cell_size=self.cell_size,
                )
            else:
                existing = self.routed_paths[net_name]
                existing.cells.extend(GridCell(c[0], c[1], c[2]) for c in cells)
                existing.length = len(existing.cells)

    def _get_cell_difficulty(self, cell: GridCell) -> float:
        """Compute difficulty score for a cell (temper-t3ek.2).

        Difficulty increases if:
        - Cell is adjacent to blocked cells (proximity to components)
        - Cell is in a high-density area
        """
        difficulty = 0.0

        # Proximity to blocked cells (components)
        for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
            nx, ny = cell.x + dx, cell.y + dy
            if (
                0 <= nx < self.grid_size[0]
                and 0 <= ny < self.grid_size[1]
                and int(self.occupancy[nx, ny, cell.layer]) == -1
            ):
                difficulty += 0.5

        # Use pre-computed density map for O(1) lookup (temper-qjlk)
        if self._density_map is not None:
            density = float(self._density_map[cell.x, cell.y, cell.layer])
        else:
            world_x = cell.x * self.cell_size + self.origin[0]
            world_y = cell.y * self.cell_size + self.origin[1]
            density = self._compute_local_density(world_x, world_y)

        difficulty += density * 1.0

        return difficulty

    def _get_neighbor_cost(
        self,
        current: GridCell,
        neighbor: GridCell,
        cost_map: Array | None = None,
        p_scale: float = 1.0,
    ) -> float:
        """Compute cost to move from current to neighbor cell.

        Uses cached numpy arrays when available for faster indexing.
        Supports soft blocking (negotiated congestion) and dynamic via cost.
        """
        from temper_placer.routing.cost import compute_neighbor_cost

        diff = self._get_cell_difficulty(neighbor)

        total_cost = compute_neighbor_cost(
            current=current,
            neighbor=neighbor,
            history_np=self._history_np,
            history=self.history_cost if self._history_np is None else None,
            congestion_np=self._congestion_np,
            congestion=self.present_congestion if self._congestion_np is None else None,
            occupancy_np=self._occupancy_np,
            occupancy=self.occupancy if self._occupancy_np is None else None,
            soft_c_space_np=self._soft_c_space_np,
            soft_c_space=self.soft_c_space if self._soft_c_space_np is None else None,
            c_space_grid_np=self._c_space_grid_np,
            cell_owner=self.cell_owner,
            current_net=self._current_net,
            layer_usage=self.layer_usage_count,
            cost_map=cost_map,
            assignment=getattr(self, "_current_assignment", None),
            difficulty=diff,
            via_cost=self.via_cost,
            wrong_way_penalty=self.wrong_way_penalty,
            layer_balance_weight=self.layer_balance_weight,
            congestion_via_discount=self.congestion_via_discount,
            soft_blocking=self.soft_blocking,
            p_scale=p_scale,
        )

        if total_cost >= 1e9:
            return total_cost

        # PROFESSIONAL LAYER COST SYSTEM (temper-b577)
        # Apply net-specific layer cost multipliers after base cost calculation
        if hasattr(self, "_current_net_rules") and self._current_net_rules:
            layer_cost_mult = self.get_layer_cost(self._current_net_rules, neighbor.layer)
            total_cost *= layer_cost_mult

        return total_cost

    def _prepare_cost_arrays(self) -> None:
        """Prepare cached NumPy arrays for Numba routing."""
        # Sync occupancy to NumPy if it changed or hasn't been created
        # Note: We always re-create or sync to ensure it's up to date
        self._occupancy_np = np.array(self.occupancy, dtype=np.int32)
        self._history_np = np.array(self.history_cost, dtype=np.float32)
        self._congestion_np = np.array(self.present_congestion, dtype=np.float32)

        if hasattr(self, "soft_c_space") and self.soft_c_space is not None:
            self._soft_c_space_np = np.array(self.soft_c_space, dtype=np.float32)
        else:
            self._soft_c_space_np = None

    def _clear_cost_arrays(self) -> None:
        """Clear cached numpy arrays after path finding."""
        self._history_np = None
        self._congestion_np = None
        self._occupancy_np = None
        self._soft_c_space_np = None
        self._c_space_grid_np = None

    def _world_to_grid(self, x: float, y: float) -> tuple[int, int]:
        """Convert world coordinates to grid cell indices.

        Delegates to GridConverter for consistent behavior.
        Uses rounding for nearest-cell mapping.
        """
        return self.grid_converter.world_to_grid(x, y)

    def update_congestion_costs(self, history_increment: float = 1.0) -> None:
        """Update history costs for cells that have conflicts."""
        contested = self.present_congestion > 1.0
        self.history_cost = self.history_cost + contested.astype(np.float32) * history_increment

    def decay_history_costs(self, decay_factor: float = 0.9) -> None:
        """Slowly decay history costs to avoid getting trapped in local minima."""
        self.history_cost = self.history_cost * decay_factor
        # Keep base at 1.0
        np.maximum(self.history_cost, 1.0, out=self.history_cost)

    def generate_cost_map(self, strategy: "RoutingStrategy") -> Array:
        from temper_placer.routing.bridge.types import RoutingStrategy

        if strategy == RoutingStrategy.EDGE_HUG:
            x, y = jnp.arange(self.grid_size[0]), jnp.arange(self.grid_size[1])
            X, Y = jnp.meshgrid(x, y, indexing="ij")
            dist_edge = jnp.minimum(
                jnp.minimum(X, self.grid_size[0] - 1 - X), jnp.minimum(Y, self.grid_size[1] - 1 - Y)
            )
            return 1.0 + dist_edge * 10.0
        return jnp.ones(self.grid_size, dtype=jnp.float32)

    def block_rect(self, x: int, y: int, width: int, height: int, layer: int = 0) -> None:
        xs, ys = max(0, x), max(0, y)
        xe, ye = min(x + width, self.grid_size[0]), min(y + height, self.grid_size[1])
        if layer == -1:
            for l in range(self.num_layers):
                self.occupancy[xs:xe, ys:ye, l] = -1
        else:
            self.occupancy[xs:xe, ys:ye, layer] = -1

    def block_board_features(self, board: Board) -> None:
        """Block keepouts and mounting holes defined in the board.

        Args:
            board: Board object containing feature definitions
        """
        # Block keepouts (rectangles)
        for x_min, y_min, x_max, y_max in board.keepouts:
            # Convert to grid coordinates
            gx_min = int(math.floor((x_min - self.origin[0]) / self.cell_size))
            gy_min = int(math.floor((y_min - self.origin[1]) / self.cell_size))
            gx_max = int(math.ceil((x_max - self.origin[0]) / self.cell_size))
            gy_max = int(math.ceil((y_max - self.origin[1]) / self.cell_size))

            w = gx_max - gx_min
            h = gy_max - gy_min

            self.block_rect(gx_min, gy_min, w, h, layer=-1)  # Block on all layers

        # Block mounting holes (circles)
        if not board.mounting_holes:
            return

        for hole in board.mounting_holes:
            hx, hy = hole.position
            radius = hole.keepout_radius

            # Determine bounding box of the circle in grid
            gx_min = int(math.floor((hx - radius - self.origin[0]) / self.cell_size))
            gy_min = int(math.floor((hy - radius - self.origin[1]) / self.cell_size))
            gx_max = int(math.ceil((hx + radius - self.origin[0]) / self.cell_size))
            gy_max = int(math.ceil((hy + radius - self.origin[1]) / self.cell_size))

            radius_sq = radius**2

            # Iterate over bounding box
            for gx in range(gx_min, gx_max + 1):
                for gy in range(gy_min, gy_max + 1):
                    # Check if cell is within grid bounds
                    if 0 <= gx < self.grid_size[0] and 0 <= gy < self.grid_size[1]:
                        # Calculate world coordinates of cell center
                        wx = gx * self.cell_size + self.origin[0]
                        wy = gy * self.cell_size + self.origin[1]

                        # Check distance to hole center
                        dist_sq = (wx - hx) ** 2 + (wy - hy) ** 2
                        if dist_sq <= radius_sq:
                            # Block on all layers
                            self.occupancy[gx, gy, :] = -1

    def block_components(
        self,
        components: list[Component],
        positions: Array,
        margin: float = 0.5,
        layer_specific: bool = False,
        escape_length: int | None = None,
    ) -> None:
        self._component_positions = positions
        self._compute_density_map()

        if len(components) == 0:
            return

        pos_array = np.asarray(positions)
        n_comps = len(components)

        cx = pos_array[:, 0]
        cy = pos_array[:, 1]

        half_widths = np.array([comp.bounds[0] / 2 + margin for comp in components])
        half_heights = np.array([comp.bounds[1] / 2 + margin for comp in components])

        x_min = np.floor((cx - half_widths - self.origin[0]) / self.cell_size).astype(int)
        x_max = np.ceil((cx + half_widths - self.origin[0]) / self.cell_size).astype(int)
        y_min = np.floor((cy - half_heights - self.origin[1]) / self.cell_size).astype(int)
        y_max = np.ceil((cy + half_heights - self.origin[1]) / self.cell_size).astype(int)

        widths = x_max - x_min
        heights = y_max - y_min

        layer = 0 if layer_specific else -1

        for i in range(n_comps):
            self.block_rect(
                int(x_min[i]), int(y_min[i]), int(widths[i]), int(heights[i]), layer=layer
            )

        for i, comp in enumerate(components):
            self._create_pin_escape_routes(
                comp, float(positions[i, 0]), float(positions[i, 1]), escape_length
            )

    def _compute_grid_safe_margin(
        self,
        required_clearance: float = 0.2,
        trace_width: float = 0.2,
    ) -> float:
        """Compute margin needed to prevent grid-geometry DRC violations.

        The grid router thinks in "squares", but DRC checks actual geometry.
        A cell marked as "free" could still cause violations if a trace
        centered in that cell passes too close to a pad.

        The safe margin is:
            required_clearance + (trace_width / 2) + (cell_size / 2)

        The cell_size/2 term accounts for worst-case trace placement within
        a cell (trace centered at cell center, pad edge at cell boundary).

        Args:
            required_clearance: DRC clearance rule in mm (default 0.2mm)
            trace_width: Expected trace width in mm (default 0.2mm)

        Returns:
            Margin in mm to apply around pads for blocking
        """
        return required_clearance + (trace_width / 2)

    def _get_class_id(self, rules: "NetClassRules | None") -> int:
        """Get integer class ID for creepage checks."""
        if not rules:
            return CLASS_DEFAULT

        # DEBUG
        print(
            f"DEBUG_CLASS: Name={rules.name} V={getattr(rules, 'voltage_v', 'N/A')} Cr={getattr(rules, 'creepage_mm', 'N/A')}"
        )

        # Check explicit voltage if available
        if hasattr(rules, "voltage_v") and is_high_voltage(rules.voltage_v):
            return CLASS_HV

        # Fallback: If creepage is significantly larger than standard clearance, treat as HV
        if rules.creepage_mm > 2.0:
            return CLASS_HV

        return CLASS_LV

    def _check_class_clearance(self, cx: int, cy: int, cl: int, current_class: int) -> bool:
        """Check if cell (cx, cy, cl) violates clearance with other classes.

        Checks a radius around the cell for incompatible net classes.
        Returns True if SAFE, False if VIOLATION.
        """
        if current_class == CLASS_DEFAULT:
            return True

        # Optimization: Check center cell first (most likely conflict)
        obs_class = self.class_grid[cx, cy, cl]
        if obs_class != 0 and obs_class != current_class:
            req_sep = self._get_asymmetric_clearance(current_class, obs_class)
            # Distance is 0 (we are on top of it)
            if 0 < req_sep:
                return False

        # Scan radius for HV/LV isolation
        # We only scan if we are HV (scanning for LV) or LV (scanning for HV)
        # to save performance.
        if current_class == CLASS_DEFAULT:
            return True

        # Determine max search radius based on class
        # HV needs 8mm isolation from LV
        # LV needs 8mm isolation from HV
        # We assume max required separation is 8.0mm
        # TODO: Optimize this to not scan empty space if possible

        # For Python implementation, we limit radius to 2mm for performance
        # Numba implementation will handle full radius
        search_radius_mm = 8.0
        radius_cells = int(math.ceil(search_radius_mm / self.cell_size))

        grid_w, grid_h = self.grid_size

        for dx in range(-radius_cells, radius_cells + 1):
            for dy in range(-radius_cells, radius_cells + 1):
                nx, ny = cx + dx, cy + dy
                if 0 <= nx < grid_w and 0 <= ny < grid_h:
                    obs_class = self.class_grid[nx, ny, cl]
                    if obs_class != 0 and obs_class != current_class:
                        req_sep = self._get_asymmetric_clearance(current_class, obs_class)
                        dist_mm = math.sqrt(dx * dx + dy * dy) * self.cell_size

                        # If distance is less than required, we have a violation
                        if dist_mm < req_sep:
                            return False

        return True

    def _get_asymmetric_clearance(self, current_class: int, obstacle_class: int) -> float:
        """Get required clearance between two net classes.

        Enforces reinforced isolation (8.0mm) between High Voltage and Low Voltage
        domains, and standard clearance (0.2mm) otherwise.

        Args:
            current_class: Class ID of the net being routed.
            obstacle_class: Class ID of the cell being checked.

        Returns:
            Required clearance in mm.
        """
        # CLASS_HV = 1, CLASS_LV = 2, CLASS_DEFAULT = 0

        # reinforced isolation: HV to anything else (LV or Default)
        if (current_class == CLASS_HV and obstacle_class != CLASS_HV) or (
            current_class != CLASS_HV and obstacle_class == CLASS_HV
        ):
            return 8.0  # mm (Reinforced isolation per IEC 60335)

        # basic isolation: HV to HV
        if current_class == CLASS_HV and obstacle_class == CLASS_HV:
            return 2.5  # mm (Basic isolation for 400V)

        # standard clearance for non-HV nets
        return self.min_clearance

    def _precompute_clearance_grid(
        self,
        net_name: str,
        clearance_matrix: "ClearanceMatrix | None" = None,
    ) -> None:
        """Precompute zone-aware per-cell clearance requirements for routing this net.

        This method populates self.clearance_grid with the maximum required clearance
        at each cell, accounting for:
        1. Base clearance between net classes
        2. Zone-specific clearance overrides (e.g., 3.0mm in HV zones)

        The clearance grid is consumed by the A* pathfinder to make zone-aware routing
        decisions without requiring per-cell function calls (Numba compatible).

        Args:
            net_name: The net being routed
            clearance_matrix: Optional clearance matrix with zone manager.
                             If None, uses default clearance everywhere.

        Performance: O(grid_cells) - called once per net before routing.
        Memory: Reuses existing self.clearance_grid array (no allocation).

        Related: temper-d6kv.2, temper-d6kv.3 (zone-aware routing integration)
        """
        if clearance_matrix is None or clearance_matrix.zone_manager is None:
            # No zone awareness - use default clearance everywhere
            self.clearance_grid.fill(self.min_clearance)
            return

        # Get all other nets that are already routed (have traces on grid)
        routed_nets = list(self.routed_paths.keys())

        if not routed_nets:
            # First net - use default clearance
            self.clearance_grid.fill(self.min_clearance)
            return

        # For each cell, compute max clearance required against all routed nets
        # This is conservative but correct - we ensure clearance to ANY existing trace
        for layer in range(self.num_layers):
            for x in range(self.grid_size[0]):
                for y in range(self.grid_size[1]):
                    # Skip if cell is empty (no trace to clear from)
                    if self.occupancy[x, y, layer] == 0:
                        self.clearance_grid[x, y, layer] = self.min_clearance
                        continue

                    # Cell has a trace - compute clearance requirement
                    # Convert grid coordinates to world coordinates (mm)
                    world_x = self.origin[0] + (x + 0.5) * self.cell_size
                    world_y = self.origin[1] + (y + 0.5) * self.cell_size

                    # Find max clearance needed between current net and any routed net
                    max_clearance = self.min_clearance
                    for other_net in routed_nets:
                        if other_net == net_name:
                            continue  # Same net doesn't need clearance

                        # Query zone-aware clearance
                        clearance = clearance_matrix.get_clearance(
                            net_name, other_net, world_x, world_y
                        )
                        max_clearance = max(max_clearance, clearance)

                    self.clearance_grid[x, y, layer] = max_clearance

    def block_zones(
        self,
        zones: list,
        clearance: float = 0.0,
        layer_map: dict[str, int] | None = None,
    ) -> None:
        """Block grid cells occupied by zones.

        Uses OpenCV for efficient rasterization and dilation.

        Args:
            zones: List of kiutils Zone objects
            clearance: Clearance distance in mm
            layer_map: Map of layer names to indices
        """
        try:
            import cv2
        except ImportError:
            logging.warning("OpenCV not found, cannot block zones.")
            return

        if layer_map is None:
            # Default simple mapping
            layer_map = {"F.Cu": 0, "B.Cu": self.num_layers - 1}
            if self.num_layers == 4:
                layer_map.update({"In1.Cu": 1, "In2.Cu": 2})

        # Calculate kernel size for dilation (inflation)
        # We dilate the mask to account for clearance + potential aliasing
        kernel_size = 0
        if clearance > 0:
            kernel_size = int(math.ceil(clearance / self.cell_size))

        for zone in zones:
            # Handle layer mapping
            target_layers = []
            if hasattr(zone, "layers"):
                for lname in zone.layers:
                    if lname in layer_map:
                        l_idx = layer_map[lname]
                        if 0 <= l_idx < self.num_layers:
                            target_layers.append(l_idx)
            elif hasattr(zone, "layer"):  # Handle legacy/singular
                if zone.layer in layer_map:
                    l_idx = layer_map[zone.layer]
                    if 0 <= l_idx < self.num_layers:
                        target_layers.append(l_idx)

            if not target_layers:
                continue

            # Determine polygon source
            polys_to_process = []
            is_kiutils = False

            if hasattr(zone, "polygons") and zone.polygons:
                polys_to_process = zone.polygons
                is_kiutils = True
            elif hasattr(zone, "polygon") and zone.polygon:
                # temper_placer Zone has single polygon list of tuples
                polys_to_process = [zone.polygon]
                is_kiutils = False

            for poly in polys_to_process:
                # Convert coordinates to grid pixels
                pts = []

                # Get coordinates iterable
                coords = poly.coordinates if is_kiutils else poly

                for pos in coords:
                    if is_kiutils:
                        # kiutils Position object
                        x, y = pos.X, pos.Y
                    else:
                        # tuple or list
                        x, y = pos[0], pos[1]

                    gx = int((x - self.origin[0]) / self.cell_size)
                    gy = int((y - self.origin[1]) / self.cell_size)
                    pts.append([gx, gy])

                if not pts:
                    continue

                pts_np = np.array(pts, dtype=np.int32)
                pts_np = pts_np.reshape((-1, 1, 2))

                # Create mask (H, W) -> (Y, X)
                mask = np.zeros((self.grid_size[1], self.grid_size[0]), dtype=np.uint8)

                # Fill polygon
                cv2.fillPoly(mask, [pts_np], color=255)

                # Dilate map if clearance needed
                if kernel_size > 0:
                    # Kernel diameter = 2*r + 1
                    k_dim = kernel_size * 2 + 1
                    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k_dim, k_dim))
                    mask = cv2.dilate(mask, kernel)

                # Transpose mask to (X, Y) to match occupancy
                mask_t = mask.T

                # Apply to all relevant layers
                # Indices where mask is set
                blocked_indices = mask_t > 0

                for l_idx in target_layers:
                    self.occupancy[blocked_indices, l_idx] = -1

    def block_pads(
        self,
        components: list[Component],
        positions: Array,
        netlist: "Netlist",
        margin: float | None = None,
        trace_width: float = 0.2,
        clearance: float = 0.2,
        rotations: Array | None = None,
        sides: Array | None = None,
    ) -> None:
        """Block grid cells containing pads to prevent track-through-pad violations.

        Each pad is blocked for all nets EXCEPT its own net. This allows pins
        to be routed to but prevents foreign tracks from crossing through.

        Args:
            components: List of components
            positions: Component positions (N, 2)
            netlist: Netlist for net lookups
            margin: Extra margin around pads in mm (if None, computed from trace_width/clearance)
            trace_width: Expected trace width for margin calculation
            clearance: Required DRC clearance for margin calculation

        Note: This should be called AFTER block_components but BEFORE routing.
        Part of temper-hdu8.
        """
        # Compute grid-safe margin if not explicitly provided
        if margin is None:
            margin = self._compute_grid_safe_margin(clearance, trace_width)

        # Store component positions for density map (temper-qjlk)
        self._component_positions = positions

        # Pre-compute density map for O(1) cell difficulty lookup
        self._compute_density_map()

        # Build net-to-pad mapping
        self._pad_net_map: dict[tuple[int, int, int], str] = {}  # (gx, gy, layer) -> net

        for i, comp in enumerate(components):
            cx, cy = float(positions[i, 0]), float(positions[i, 1])

            # Get rotation and side
            rot_idx = int(rotations[i]) if rotations is not None else (comp.initial_rotation or 0)
            side_idx = int(sides[i]) if sides is not None else (comp.initial_side or 0)

            rot_rad = rot_idx * (math.pi / 2)

            for pin in comp.pins:
                px, py = pin.absolute_position((cx, cy), rot_rad, side_idx)

                # Get pad size (default to 1mm if not specified)
                pad_w = getattr(pin, "width", 1.0)
                pad_h = getattr(pin, "height", 1.0)

                # Convert to grid coordinates for blocking
                # Convert to grid coordinates for blocking
                # Use ceil/floor to strictly block only cells whose centers are within the forbidden zone
                min_x_mm = px - pad_w / 2 - margin
                min_y_mm = py - pad_h / 2 - margin
                max_x_mm = px + pad_w / 2 + margin
                max_y_mm = py + pad_h / 2 + margin

                gx_min_block = int(math.floor((min_x_mm - self.origin[0]) / self.cell_size))
                gy_min_block = int(math.floor((min_y_mm - self.origin[1]) / self.cell_size))
                gx_max_block = int(math.ceil((max_x_mm - self.origin[0]) / self.cell_size)) - 1
                gy_max_block = int(math.ceil((max_y_mm - self.origin[1]) / self.cell_size)) - 1

                # Expand for Neckdown Zone (1.0mm expansion beyond pad+margin)
                neck_margin_mm = 1.0
                gx_min_neck, gy_min_neck = self._world_to_grid(
                    px - pad_w / 2 - margin - neck_margin_mm,
                    py - pad_h / 2 - margin - neck_margin_mm,
                )
                gx_max_neck, gy_max_neck = self._world_to_grid(
                    px + pad_w / 2 + margin + neck_margin_mm,
                    py + pad_h / 2 + margin + neck_margin_mm,
                )

                # Apply Neckdown Mask using vectorized slicing
                neck_margin_mm = 1.0
                gx_min_neck, gy_min_neck = self._world_to_grid(
                    px - pad_w / 2 - margin - neck_margin_mm,
                    py - pad_h / 2 - margin - neck_margin_mm,
                )
                gx_max_neck, gy_max_neck = self._world_to_grid(
                    px + pad_w / 2 + margin + neck_margin_mm,
                    py + pad_h / 2 + margin + neck_margin_mm,
                )

                x_neck_start = max(0, gx_min_neck)
                x_neck_end = min(self.grid_size[0], gx_max_neck + 1)
                y_neck_start = max(0, gy_min_neck)
                y_neck_end = min(self.grid_size[1], gy_max_neck + 1)

                if x_neck_start < x_neck_end and y_neck_start < y_neck_end:
                    self.neckdown_mask[x_neck_start:x_neck_end, y_neck_start:y_neck_end, :] = True

                # Get net name for this pin
                net_name = pin.net if hasattr(pin, "net") else ""

                # Determine which layers to block
                # Through-hole blocks all layers, SMD blocks only its side
                if pin.shape == "thru_hole":
                    block_layers = list(range(self.num_layers))
                else:
                    # Top side = layer 0, Bottom side = last layer
                    target_layer = 0 if side_idx == 0 else (self.num_layers - 1)
                    block_layers = [target_layer]

                # Determine net class for blocking
                class_id = CLASS_DEFAULT
                if self.design_rules and net_name:
                    rules = self.design_rules.get_rules_for_net(net_name)
                    class_id = self._get_class_id(rules)

                # Block cells and record ownership using vectorized operations
                gx_start = max(0, gx_min_block)
                gx_end = min(self.grid_size[0], gx_max_block + 1)
                gy_start = max(0, gy_min_block)
                gy_end = min(self.grid_size[1], gy_max_block + 1)

                for layer in block_layers:
                    for gx in range(gx_start, gx_end):
                        for gy in range(gy_start, gy_end):
                            key = (gx, gy, layer)
                            if key not in self._pad_net_map:
                                self._pad_net_map[key] = net_name
                                if self.occupancy[gx, gy, layer] != -1:
                                    self.occupancy[gx, gy, layer] = -1
                                    self.class_grid[gx, gy, layer] = class_id
                                
                                # Register in net_occupancy for conflict detection (Short Detection)
                                if net_name:
                                    if key not in self.net_occupancy:
                                        self.net_occupancy[key] = set()
                                    self.net_occupancy[key].add(net_name)

        print(f"DEBUG: Blocked {len(self._pad_net_map)} grid cells for pads")

    def _compute_local_density(self, x: float, y: float, radius: float = 10.0) -> float:
        if self._component_positions is None or not len(self._component_positions):
            return 0.0
        point = jnp.array([x, y])
        distances = jnp.sqrt(jnp.sum((self._component_positions - point) ** 2, axis=1))
        count = int(jnp.sum(distances <= radius))
        return float(jnp.clip(count / (jnp.pi * radius**2 / 100.0), 0.0, 1.0))

    def _compute_density_map(self, radius_mm: float = 10.0) -> None:
        """Pre-compute component density for all grid cells.

        This converts _get_cell_difficulty from O(VisitedCells * NumComponents)
        to O(1) array lookup. Uses vectorized NumPy operations for speed.

        Args:
            radius_mm: Radius in mm for density calculation (default 10mm)
        """
        if self._component_positions is None or len(self._component_positions) == 0:
            self._density_map = np.zeros(self.grid_size + (self.num_layers,), dtype=np.float32)
            return

        radius_cells_sq = (radius_mm / self.cell_size) ** 2

        t0 = time.perf_counter()
        # Vectorized density computation
        # Create meshgrid of world coordinates
        x_coords = np.arange(self.grid_size[0]) * self.cell_size + self.origin[0]
        y_coords = np.arange(self.grid_size[1]) * self.cell_size + self.origin[1]
        X, Y = np.meshgrid(x_coords, y_coords, indexing="ij")  # (W, H)

        comp_array = np.asarray(self._component_positions)  # (N, 2)
        cx = comp_array[:, 0]
        cy = comp_array[:, 1]

        density_map_2d = np.zeros(self.grid_size, dtype=np.float32)

        # Loop over components (N) and vectorize over grid (W*H)
        # This is memory efficient and much faster than nested loops over grid
        for i in range(len(cx)):
            dists_sq = (X - cx[i]) ** 2 + (Y - cy[i]) ** 2
            density_map_2d += (dists_sq <= radius_cells_sq).astype(np.float32)

        # Normalize and clip (Match Python behavior)
        density_map_2d = np.clip(density_map_2d / (np.pi * radius_mm**2 / 100.0), 0.0, 1.0)

        # Expand to 3D by repeating across layers
        self._density_map = np.repeat(density_map_2d[:, :, np.newaxis], self.num_layers, axis=2)

        logger.debug(f"Pre-computed density map: {self.grid_size} x {self.num_layers}")

    def _compute_escape_length(
        self, pin_x: float, pin_y: float, comp: Component | None = None
    ) -> int:
        density = self._compute_local_density(pin_x, pin_y)
        min_mm = max(comp.width, comp.height) / 2 + 1.0 if comp else 2.0
        base = int(math.ceil(min_mm / self.cell_size))
        if density < 0.3:
            return base + int(2.0 / self.cell_size)
        return base + (0 if density > 0.7 else int(1.0 / self.cell_size))

    def _get_primary_escape_direction(self, pin_offset: tuple[float, float]) -> tuple[int, int]:
        dx, dy = pin_offset
        return (1 if dx >= 0 else -1, 0) if abs(dx) >= abs(dy) else (0, 1 if dy >= 0 else -1)

    def _try_escape_route(
        self, pin_x: float, pin_y: float, step_x: int, step_y: int, escape_length: int
    ) -> bool:
        gx, gy = self._world_to_grid(pin_x, pin_y)

        end_x = gx + (escape_length - 1) * step_x
        end_y = gy + (escape_length - 1) * step_y

        if not (0 <= gx < self.grid_size[0] and 0 <= gy < self.grid_size[1]):
            return False
        if not (0 <= end_x < self.grid_size[0] and 0 <= end_y < self.grid_size[1]):
            return False

        steps = np.arange(escape_length)
        xs = gx + steps * step_x
        ys = gy + steps * step_y

        self.occupancy[xs, ys, :] = 0
        return True

    def _create_pin_escape_routes(
        self, comp: Component, cx: float, cy: float, escape_length: int | None = None
    ) -> None:
        for pin in comp.pins:
            px, py = cx + pin.position[0], cy + pin.position[1]
            elen = (
                escape_length
                if escape_length is not None
                else self._compute_escape_length(px, py, comp)
            )
            sx, sy = self._get_primary_escape_direction(pin.position)
            for dx, dy in [(sx, sy), (sy, -sx), (-sy, sx)]:
                if self._try_escape_route(px, py, dx, dy, elen):
                    break

    def _register_routed_path(
        self, cells: list[GridCell], net_name: str, rules: "NetClassRules | None" = None
    ) -> None:
        """Register routed geometry with DRCOracle for real-time clearance checks.

        Converts grid cells to Track/Via objects and registers them so subsequent
        nets are checked against this geometry.

        Args:
            cells: List of grid cells forming the path
            net_name: Net name for the routed path
            rules: Net class rules for the net
        """
        if self.drc_oracle is None or len(cells) < 2:
            return

        from temper_placer.routing.constraints import Track, Via
        from temper_placer.routing.constraints.geometry import Point

        new_tracks = []
        new_vias = []

        # Determine geometry from rules or defaults
        if rules:
            base_track_width = rules.trace_width
            via_diameter = rules.via_diameter
            via_drill = rules.via_drill
            # Neckdown zones use dynamically computed narrow width
            neckdown_width = max(0.1, base_track_width - 0.05)
        else:
            # Standardize on 0.2mm (8 mil) trace width
            # This allows 0.2mm clearance on 0.4mm grid spacing (0.4 - 0.2 = 0.2 clearance)
            # 0.25mm width would fail (0.4 - 0.25 = 0.15 clearance)
            base_track_width = 0.2
            via_diameter = 0.8
            via_drill = 0.4
            neckdown_width = 0.15

        for i in range(1, len(cells)):
            c1, c2 = cells[i - 1], cells[i]

            # Layer transition = via
            if c1.layer != c2.layer:
                wx = c2.x * self.cell_size + self.origin[0]
                wy = c2.y * self.cell_size + self.origin[1]
                via = Via(
                    center=Point(wx, wy),
                    diameter=via_diameter,
                    drill=via_drill,
                    net=net_name,
                )
                new_vias.append(via)
            else:
                # Same layer = track segment
                start_x = c1.x * self.cell_size + self.origin[0]
                start_y = c1.y * self.cell_size + self.origin[1]
                end_x = c2.x * self.cell_size + self.origin[0]
                end_y = c2.y * self.cell_size + self.origin[1]

                # Determine track width based on neckdown mask
                is_neckdown = (
                    self.neckdown_mask[c1.x, c1.y, c1.layer]
                    or self.neckdown_mask[c2.x, c2.y, c2.layer]
                )
                track_width = neckdown_width if is_neckdown else base_track_width

                track = Track(
                    start=Point(start_x, start_y),
                    end=Point(end_x, end_y),
                    width=track_width,
                    layer=c1.layer,
                    net=net_name,
                )
                new_tracks.append(track)

        # Batch register to rebuild index only once
        if new_tracks:
            self.drc_oracle.register_tracks(new_tracks)
        if new_vias:
            self.drc_oracle.register_vias(new_vias)

    def _heuristic(self, a: GridCell, b: GridCell) -> float:
        return abs(a.x - b.x) + abs(a.y - b.y) + abs(a.layer - b.layer) * 2

    def _compute_distance_map(self, target: GridCell, _layer: int = 0) -> np.ndarray:
        """Precompute obstacle-aware distance map via BFS from target.

        The distance map gives the true shortest path distance from any cell
        to the target, accounting for obstacles. This provides a tight
        (yet still admissible) heuristic for A*.

        Uses Numba-accelerated BFS when available (~50-100x faster).

        Args:
            target: Target grid cell
            layer: Layer to compute distances on

        Returns:
            3D array of distances (same shape as occupancy grid)
        """
        # Check cache
        cache_key = (target.x, target.y, target.layer)
        if hasattr(self, "_distance_map_cache") and cache_key in self._distance_map_cache:
            self.stats.profile.dist_map_cache_hits += 1
            return self._distance_map_cache[cache_key]

        t_dist = time.perf_counter()
        self.stats.profile.dist_map_calls += 1

        # Use Numba-accelerated BFS when available
        if HAS_NUMBA:
            # Use cached contiguous occupancy if available, otherwise convert
            if self._occupancy_np is not None:
                occ = self._occupancy_np
            else:
                occ = np.ascontiguousarray(self.occupancy, dtype=np.int32)
            dist_map = compute_distance_map_numba(
                target.x,
                target.y,
                target.layer,
                self.grid_size[0],
                self.grid_size[1],
                self.num_layers,
                occ,
            )
        else:
            # Fallback to pure Python BFS
            dist_map = np.full(
                (self.grid_size[0], self.grid_size[1], self.num_layers),
                float("inf"),
                dtype=np.float32,
            )
            from collections import deque

            queue = deque([target])
            dist_map[target.x, target.y, target.layer] = 0.0

            while queue:
                cell = queue.popleft()
                current_dist = dist_map[cell.x, cell.y, cell.layer]

                for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
                    nx, ny = cell.x + dx, cell.y + dy

                    if not (0 <= nx < self.grid_size[0] and 0 <= ny < self.grid_size[1]):
                        continue

                    if self.occupancy[nx, ny, cell.layer] == -1:
                        continue

                    new_dist = current_dist + 1.0
                    if new_dist < dist_map[nx, ny, cell.layer]:
                        dist_map[nx, ny, cell.layer] = new_dist
                        queue.append(GridCell(nx, ny, cell.layer))

        self.stats.profile.dist_map_ms += (time.perf_counter() - t_dist) * 1000.0

        # Cache the result
        if not hasattr(self, "_distance_map_cache"):
            self._distance_map_cache = {}
        self._distance_map_cache[cache_key] = dist_map

        return dist_map

    def _clear_distance_map_cache(self) -> None:
        """Clear distance map cache (call when occupancy changes)."""
        if hasattr(self, "_distance_map_cache"):
            self._distance_map_cache.clear()

    def find_path_rrr_adaptive(
        self,
        start: tuple[int, int],
        end: tuple[int, int],
        layer: int = 0,
        allow_layer_change: bool = False,
        allowed_layers: list[int] | None = None,
        cost_map: Array | None = None,
        p_scale: float = 1.0,
        current_class_id: int = 0,
        current_net_id: int = 0,
    ) -> list[GridCell] | None:
        """Find path using A* with adaptive (distance map) heuristic.

        Uses precomputed distance map as heuristic instead of Manhattan distance.
        This provides a tighter bound and reduces A* search iterations.
        Uses Numba-accelerated pathfinding when available for 10x+ speedup.

        Args:
            start, end: Grid coordinates
            layer: Starting layer
            allow_layer_change: Allow vias
            allowed_layers: Layers that can be used
            cost_map: Optional routing cost map
            p_scale: Congestion penalty scale
            current_class_id: Net class ID for clearance checking

        Returns:
            Path as list of GridCells, or None if no path exists
        """
        if int(self.occupancy[start[0], start[1], layer]) == -1:
            return None
        if int(self.occupancy[end[0], end[1], layer]) == -1:
            for l in range(self.num_layers):
                if int(self.occupancy[end[0], end[1], l]) != -1:
                    layer = l
                    break
            else:
                return None

        self._prepare_cost_arrays()

        try:
            dist_map = self._compute_distance_map(GridCell(end[0], end[1], layer), _layer=layer)

            if HAS_NUMBA and self._history_np is not None and self._congestion_np is not None:
                # Convert allowed_layers to boolean mask for Numba
                allowed_mask = None
                if allowed_layers is not None:
                    allowed_mask = np.zeros(self.num_layers, dtype=np.bool_)
                    for l in allowed_layers:
                        if 0 <= l < self.num_layers:
                            allowed_mask[l] = True

                # Determine primary layer for penalty
                primary_idx = -1
                if hasattr(self, "_current_assignment") and self._current_assignment:
                    primary_idx = self._current_assignment.primary_layer.value - 1

                result = find_path_astar_numba_adaptive(
                    start[0],
                    start[1],
                    layer,
                    end[0],
                    end[1],
                    layer,
                    self.grid_size[0],
                    self.grid_size[1],
                    self.num_layers,
                    self._occupancy_np,
                    self._history_np,
                    self._congestion_np,
                    self.via_cost,
                    p_scale,
                    dist_map,
                    cost_map=None,
                    clearance_mask=None,
                    soft_blocking=self.soft_blocking,
                    soft_c_space=self._soft_c_space_np,
                    tap_mask=None,
                    guide_map=None,
                    guide_bias=0.0,
                    class_grid=self.class_grid,
                    current_class_id=current_class_id,
                    min_clearance=self.min_clearance,
                    cell_size=self.cell_size,
                    allowed_layers_mask=allowed_mask,
                    primary_layer_idx=primary_idx,
                    layer_penalty=5.0,
                    owner_grid=self.owner_grid,
                    current_net_id=current_net_id,
                )

                if result:
                    path = [GridCell(x, y, l) for x, y, l in result]
                    return path
                return None

        except Exception as e:
            logger.warning(f"Numba A* failed, falling back to Python: {e}")

        finally:
            self._clear_cost_arrays()

        return self._find_path_python_adaptive(
            start,
            end,
            layer,
            allow_layer_change,
            allowed_layers,
            cost_map,
            p_scale,
            dist_map,
            current_class_id=current_class_id,
            current_net_id=current_net_id,
        )

    def _find_path_python_adaptive(
        self,
        start: tuple[int, int],
        end: tuple[int, int],
        layer: int = 0,
        allow_layer_change: bool = False,
        allowed_layers: list[int] | None = None,
        cost_map: Array | None = None,
        p_scale: float = 1.0,
        dist_map: np.ndarray | None = None,
        current_class_id: int = 0,
        current_net_id: int = 0,
    ) -> list[GridCell] | None:
        """Python fallback for adaptive pathfinding when Numba is unavailable."""
        start_cell = GridCell(start[0], start[1], layer)
        end_cell = GridCell(end[0], end[1], layer)

        open_set = [(0.0, 0, start_cell, 0.0)]
        counter = 0
        came_from = {}
        g_score = {start_cell: 0.0}
        visited = set()

        while open_set:
            _, _, current, current_g = heapq.heappop(open_set)
            self.stats.total_astar_iterations += 1

            if current in visited:
                continue
            visited.add(current)

            if current.x == end_cell.x and current.y == end_cell.y:
                path = [current]
                while current in came_from:
                    current = came_from[current]
                    path.append(current)
                path.reverse()
                return path

            for neighbor in self._get_neighbors(current, allow_layer_change, allowed_layers):
                if neighbor in visited:
                    continue

                # Class Clearance Check (temper-kmbw)
                # Ensure we don't violate HV/LV separation
                if not self._check_class_clearance(
                    neighbor.x, neighbor.y, neighbor.layer, current_class_id
                ):
                    continue

                move_cost = self._get_neighbor_cost(current, neighbor, cost_map, p_scale=p_scale)
                tentative_g = current_g + move_cost

                if neighbor not in g_score or tentative_g < g_score[neighbor]:
                    came_from[neighbor] = current
                    g_score[neighbor] = tentative_g

                    if dist_map is not None:
                        h_score = float(dist_map[neighbor.x, neighbor.y, neighbor.layer])
                        if h_score == float("inf"):
                            h_score = self._heuristic(neighbor, end_cell)
                    else:
                        h_score = self._heuristic(neighbor, end_cell)

                    f_score = tentative_g + h_score
                    counter += 1
                    heapq.heappush(open_set, (f_score, counter, neighbor, tentative_g))

        return None

    def route_net_adaptive(
        self,
        net_name: str,
        pin_positions: list[tuple[float, float]],
        assignment: "LayerAssignment",
        cost_map: Array | None = None,
        p_scale: float = 1.0,
    ) -> RoutePath:
        """Route a net using adaptive A* heuristic.

        Uses distance map heuristic for more efficient pathfinding.

        Args:
            net_name: Net name
            pin_positions: Pin positions in world coordinates
            assignment: Layer assignment
            cost_map: Optional cost map
            p_scale: Congestion scale

        Returns:
            RoutePath with routing result
        """
        from temper_placer.routing.layer_assignment import Layer

        if len(pin_positions) < 2:
            res = RoutePath(
                net=net_name,
                cells=[],
                length=0.0,
                via_count=0,
                success=True,
                difficulty=0.0,
                cell_difficulties=[],
            )
            self.routed_paths[net_name] = res
            return res

        layer = 0 if not assignment or assignment.primary_layer == Layer.L1_TOP else 1
        allow_via = len(assignment.allowed_layers) > 1 if assignment else True
        grid_pins = [self._world_to_grid(x, y) for x, y in pin_positions]

        # Determine net IDs for isolation (prevents same-layer crossing)
        current_net_id = self._get_net_id(net_name)

        # Determine net class for blocking/clearance
        current_class_id = CLASS_DEFAULT
        if self.design_rules:
            rules = self.design_rules.get_rules_for_net(net_name)
            current_class_id = self._get_class_id(rules)

        # Temporarily unblock pin locations
        original_occupancy = []
        for gx, gy in grid_pins:
            for l in range(self.num_layers):
                if self.occupancy[gx, gy, l] == -1:
                    original_occupancy.append((gx, gy, l, -1))
                    self.occupancy[gx, gy, l] = 0

        all_cells, total_vias, start_grid = [], 0, grid_pins[0]
        total_difficulty = 0.0
        cell_difficulties: list[float] = []

        for i in range(1, len(grid_pins)):
            # Use adaptive pathfinding
            path = self.find_path_rrr_adaptive(
                start_grid,
                grid_pins[i],
                layer,
                allow_via,
                cost_map=cost_map,
                p_scale=p_scale,
                current_class_id=current_class_id,
                current_net_id=current_net_id,
            )

            if path is None:
                # Restore occupancy on failure
                for gx, gy, l, v in original_occupancy:
                    self.occupancy[gx, gy, l] = v
                res = RoutePath(
                    net=net_name,
                    cells=all_cells,
                    length=float(len(all_cells)),
                    via_count=total_vias,
                    success=False,
                    cell_size=self.cell_size,
                    difficulty=total_difficulty,
                    cell_difficulties=cell_difficulties,
                    failure_reason=f"No path from {start_grid} to {grid_pins[i]}",
                )
                self.routed_paths[net_name] = res
                return res

            # Count vias and accumulate difficulty
            for j in range(1, len(path)):
                if path[j].layer != path[j - 1].layer:
                    total_vias += 1

                d = self._get_cell_difficulty(path[j])
                total_difficulty += d
                cell_difficulties.append(d)

            if all_cells:
                path = path[1:]
            all_cells.extend(path)

        # Restore original occupancy
        for gx, gy, l, v in original_occupancy:
            self.occupancy[gx, gy, l] = v

        res = RoutePath(
            net=net_name,
            cells=all_cells,  # Ordered path for simplification
            length=float(len(all_cells)),
            via_count=total_vias,
            success=True,
            cell_size=self.cell_size,
            difficulty=total_difficulty,
            cell_difficulties=cell_difficulties,
        )
        self._mark_path_occupied(net_name, res)
        self.routed_paths[net_name] = res
        return res

    def get_layer_cost(self, net_rules, layer_idx):
        """Get cost multiplier for routing on a specific layer based on net class rules."""
        if not net_rules:
            return 1.0 if layer_idx in [0, self.num_layers - 1] else 2.0
        if net_rules.layer_costs and hasattr(self, "layer_stackup"):
            if 0 <= layer_idx < len(self.layer_stackup.layers):
                layer_name = self.layer_stackup.layers[layer_idx].name
                if layer_name in net_rules.layer_costs:
                    return net_rules.layer_costs[layer_name]
        if net_rules.routing_strategy:
            strategy = net_rules.routing_strategy
            if strategy == "plane_preferred":
                if hasattr(self, "layer_stackup") and self.layer_stackup.is_plane_layer(layer_idx):
                    return 0.1
                return 10.0
            elif strategy == "plane_required":
                if hasattr(self, "layer_stackup") and self.layer_stackup.is_plane_layer(layer_idx):
                    return 0.1
                return 50.0 if layer_idx in [0, self.num_layers - 1] else 100.0
            elif strategy in ("surface_only", "top_layer_only"):
                return 1.0 if layer_idx in [0, self.num_layers - 1] else 100.0
            elif strategy == "wide_trace":
                return 1.0
        return 1.0 if layer_idx in [0, self.num_layers - 1] else 2.0

    def _get_neighbors(
        self,
        cell: GridCell,
        allow_layer_change: bool = False,
        allowed_layers: list[int] | None = None,
    ) -> list[GridCell]:
        neighbors = []
        layers = allowed_layers if allowed_layers is not None else list(range(self.num_layers))

        is_plane = self.layer_stackup.is_plane_layer(cell.layer)
        allow_horizontal = not is_plane or cell.layer in layers

        if allow_horizontal:
            for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
                nx, ny = cell.x + dx, cell.y + dy
                if (
                    0 <= nx < self.grid_size[0]
                    and 0 <= ny < self.grid_size[1]
                    and cell.layer in layers
                ):
                    occ = int(self.occupancy[nx, ny, cell.layer])
                    # Cell is impassable if:
                    # 1. It's a hard obstacle (-1)
                    # 2. It's occupied (2) and we are in strict mode (not soft_blocking)
                    if occ == -1:
                        continue
                    if occ == 2 and not self.soft_blocking:
                        continue

                    neighbors.append(GridCell(nx, ny, cell.layer))
        if allow_layer_change and self.num_layers > 1:
            for nl in layers:
                # Skip invalid layer indices
                if nl < 0 or nl >= self.num_layers:
                    continue
                if nl != cell.layer:
                    occ = int(self.occupancy[cell.x, cell.y, nl])
                    if occ == -1:
                        continue
                    if occ == 2 and not self.soft_blocking:
                        continue
                    neighbors.append(GridCell(cell.x, cell.y, nl))
        return neighbors

    def find_path(
        self,
        start: tuple[int, int],
        end: tuple[int, int],
        layer: int = 0,
        allow_layer_change: bool = False,
        allowed_layers: list[int] | None = None,
        cost_map: Array | None = None,
    ) -> list[GridCell] | None:
        return self.find_path_rrr(
            start, end, layer, allow_layer_change, allowed_layers, cost_map, p_scale=1.0
        )

    def _find_escape_point(
        self, pin_pos: tuple[float, float], radius: int = 5, layer: int = 0
    ) -> tuple[int, int] | None:
        """Find nearest unblocked grid cell from a pin position using BFS.

        Args:
            pin_pos: World coordinates (x, y) of the pin
            radius: Maximum search radius in grid cells
            layer: Layer to search on

        Returns:
            Grid coordinates (gx, gy) of escape point, or None if trapped
        """
        pin_gx, pin_gy = self._world_to_grid(*pin_pos)
        pin_gx, pin_gy = self._world_to_grid(*pin_pos)

        # If pin cell is already free, verify it's not trapped
        # A cell is trapped if all its neighbors are blocked
        is_trapped = True
        if self.occupancy[pin_gx, pin_gy, layer] != -1:
            for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
                nx, ny = pin_gx + dx, pin_gy + dy
                if 0 <= nx < self.grid_size[0] and 0 <= ny < self.grid_size[1]:
                    if self.occupancy[nx, ny, layer] != -1:
                        is_trapped = False
                        break

        if not is_trapped:
            return (pin_gx, pin_gy)

        # BFS to find closest free cell

        from collections import deque

        queue = deque([(pin_gx, pin_gy, 0)])  # (x, y, distance)
        visited = {(pin_gx, pin_gy)}

        while queue:
            gx, gy, dist = queue.popleft()

            # Check if we've exceeded search radius
            if dist > radius:
                break

            # Check all 4 neighbors
            for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
                nx, ny = gx + dx, gy + dy

                # Bounds check
                if not (0 <= nx < self.grid_size[0] and 0 <= ny < self.grid_size[1]):
                    continue

                # Skip if already visited
                if (nx, ny) in visited:
                    continue
                visited.add((nx, ny))

                # Check if this cell is free
                if self.occupancy[nx, ny, layer] != -1:
                    return (nx, ny)

                # Add to queue for further exploration
                queue.append((nx, ny, dist + 1))

        # No escape point found within radius
        return None

    def route_net_rrr(
        self,
        net_name: str,
        pin_positions: list[tuple[float, float]],
        assignment: "LayerAssignment",
        cost_map: Array | None = None,
        p_scale: float = 1.0,
        pin_sides: list[int] | None = None,
        trace_width_mm: float | None = None,
        clearance_mm: float | None = None,
    ) -> RoutePath:
        """Route a net using Rip-up and Reroute (RRR) logic.

        This is the core routing function for a single net, used by RRR iterations.
        It handles temporary unblocking of pin locations and marking the path.

        Args:
            net_name: Name of the net to route.
            pin_positions: List of (x, y) world coordinates for the pins.
            assignment: Layer assignment for the net.
            cost_map: Optional cost map for routing strategy.
            p_scale: Congestion penalty scale factor.
            pin_sides: Optional list of pin sides (0 for top, 1 for bottom) for each pin.
                       Used to determine the initial layer for routing from a pin.
            trace_width_mm: Specific trace width for this net. If None, uses default.
            clearance_mm: Specific clearance for this net. If None, uses default.

        Returns:
            RoutePath object detailing the routing result.
        """
        from temper_placer.routing.layer_assignment import Layer
        print(f"DEBUG: route_net_rrr called for {net_name} ({len(pin_positions)} pins)", flush=True)

        if len(pin_positions) < 2:
            # Single-pin or empty nets don't need routing
            res = RoutePath(
                net=net_name,
                cells=[],
                length=0.0,
                via_count=0,
                success=True,
                difficulty=0.0,
                cell_difficulties=[],
            )
            self.routed_paths[net_name] = res
            return res

        # Set current net for DRC oracle queries
        self._current_net = net_name
        self._current_assignment = assignment
        self._default_trace_width_mm = trace_width_mm if trace_width_mm is not None else 0.2
        self.min_clearance = clearance_mm if clearance_mm is not None else 0.2

        # Determine starting layer for routing
        # If pin_sides are provided, use the side of the first pin.
        # Otherwise, use the primary layer from assignment or default to L1_TOP (layer 0).
        start_layer = 0
        if pin_sides and len(pin_sides) > 0:
            start_layer = 0 if pin_sides[0] == 0 else (self.num_layers - 1)
        elif assignment:
            start_layer = assignment.primary_layer.value - 1

        allow_via = len(assignment.allowed_layers) > 1 if assignment else True
        allowed_layers_indices = (
            [l.value - 1 for l in assignment.allowed_layers] if assignment else None
        )

        grid_pins = [self._world_to_grid(x, y) for x, y in pin_positions]

        # ADAPTIVE UNBLOCKING LOOP
        # Try progressively larger unblocking radii to escape dense pin fields
        base_unblock_radius = max(5, int(2.0 / self.cell_size))
        retry_factors = [1.0, 2.0, 3.0]
        
        start_layer_initial = start_layer # Keep base start layer

        # Variables to store the best successful route across attempts
        best_route_path: RoutePath | None = None
        best_difficulty = float('inf')

        for attempt_idx, radius_factor in enumerate(retry_factors):
            unblock_radius = int(base_unblock_radius * radius_factor)
            
            # Reset accumulation variables for this attempt
            final_all_cells = []
            final_total_vias = 0
            final_total_difficulty = 0.0
            final_cell_difficulties = []
            final_success = True
            last_failure_reason = None
            
            # Temporarily unblock pin locations and any cells owned by this net
            original_occupancy_and_ownership = []

            for px, py in grid_pins:
                for dx in range(-unblock_radius, unblock_radius + 1):
                    for dy in range(-unblock_radius, unblock_radius + 1):
                        gx, gy = px + dx, py + dy
                        if not (0 <= gx < self.grid_size[0] and 0 <= gy < self.grid_size[1]):
                            continue

                        for l in range(self.num_layers):
                            key = (gx, gy, l)
                            owner = self.cell_owner.get(key)
                            was_in_net_occ = (
                                key in self.net_occupancy and net_name in self.net_occupancy[key]
                            )

                            # 1. Always unblock OWN pad (-1) OR OWN trace (from net_occupancy)
                            is_own_pad = (key in self._pad_net_map and self._pad_net_map[key] == net_name)
                            is_own_trace = (key in self.net_occupancy and net_name in self.net_occupancy[key])
                            
                            # 2. Semi-Strict: Allow own pads OR Courtyard (-1 but not in map).
                            # Since _pad_net_map is now populated, 'key not in _pad_net_map' means Component Body/Courtyard.
                            # We ALLOW routing through courtyard to escape (unless hard blocked), but FORBID neighbor pads.
                            is_courtyard = (self.occupancy[gx, gy, l] == -1 and key not in self._pad_net_map)

                            if is_own_pad or is_own_trace or is_courtyard:
                                original_occupancy_and_ownership.append(
                                    (
                                        key, 
                                        int(self.occupancy[gx, gy, l]), 
                                        self.class_grid[gx, gy, l], 
                                        owner, 
                                        was_in_net_occ,
                                        float(self.present_congestion[gx, gy, l])
                                    )
                                )
                                self.occupancy[gx, gy, l] = 0
                                self.class_grid[gx, gy, l] = CLASS_DEFAULT
                                
                                if is_neighbor_pad and not is_own_pad:
                                    self.present_congestion[gx, gy, l] += 10.0

                            # Also unblock any cells that were part of this net's previous route
                            if was_in_net_occ:
                                if (
                                    len(original_occupancy_and_ownership) > 0
                                    and original_occupancy_and_ownership[-1][0] == key
                                ):
                                    pass
                                else:
                                    original_occupancy_and_ownership.append(
                                        (
                                            key,
                                            int(self.occupancy[gx, gy, l]),
                                            self.class_grid[gx, gy, l],
                                            owner,
                                            was_in_net_occ,
                                            float(self.present_congestion[gx, gy, l])
                                        )
                                    )

                                if net_name in self.net_occupancy[key]:
                                    self.net_occupancy[key].remove(net_name)

                                if not self.net_occupancy[key]:
                                    if self.occupancy[gx, gy, l] != -1:
                                        self.occupancy[gx, gy, l] = 0
                                    del self.net_occupancy[key]
                                    if key in self.cell_owner:
                                        del self.cell_owner[key]

                                self.present_congestion[gx, gy, l] = max(
                                    0.0, self.present_congestion[gx, gy, l] - 1.0
                                )

            # Route point-to-point connections
            current_start_grid = grid_pins[0]
            current_start_layer = start_layer_initial

            for i in range(1, len(grid_pins)):
                target_grid = grid_pins[i]
                target_layer = start_layer  # Default to same layer as start

                if pin_sides and i < len(pin_sides):
                    target_layer = 0 if pin_sides[i] == 0 else (self.num_layers - 1)

                routing_start = current_start_grid
                routing_end = target_grid
                path_prefix = []
                path_suffix = []

                s_cell = GridCell(current_start_grid[0], current_start_grid[1], current_start_layer)
                t_cell = GridCell(target_grid[0], target_grid[1], target_layer)

                escape_rad = min(unblock_radius, 7)
                
                # Try to find escape points
                esc = self._compute_escape_point(s_cell, t_cell, escape_rad)
                if esc:
                    routing_start = (esc.x, esc.y)
                    path_prefix = self._get_line_path(s_cell, esc)

                esc = self._compute_escape_point(t_cell, s_cell, escape_rad)
                if esc:
                    routing_end = (esc.x, esc.y)
                    path_suffix = self._get_line_path(esc, t_cell)

                start_layer_for_search = current_start_layer
                if path_prefix:
                    # p[-1] is the escape cell, so use its layer
                    start_layer_for_search = path_prefix[-1].layer

                path = self.find_path_rrr_adaptive(
                    routing_start,
                    routing_end,
                    start_layer_for_search,
                    allow_via,
                    allowed_layers_indices,
                    cost_map=cost_map,
                    p_scale=p_scale,
                )

                if path is not None:
                    # Splice paths
                    if path_prefix:
                        # Remove duplicate connection point
                        if path and path[0] == path_prefix[-1]:
                            path = path[1:]
                        path = path_prefix + path
                    if path_suffix:
                        if path and path[-1] == path_suffix[0]:
                            path_suffix = path_suffix[1:]
                        path = path + path_suffix

                if path is None:
                    final_success = False
                    
                    # DIAGNOSIS: Deep dive into failure reason
                    s_occ = int(self.occupancy[routing_start[0], routing_start[1], start_layer_for_search])
                    nb_blocked = 0
                    nb_total = 0
                    for dx, dy in [(0,1),(0,-1),(1,0),(-1,0)]:
                        nx, ny = routing_start[0]+dx, routing_start[1]+dy
                        if 0 <= nx < self.grid_size[0] and 0 <= ny < self.grid_size[1]:
                            occ = int(self.occupancy[nx, ny, start_layer_for_search])
                            is_blocked = (occ == -1) or (occ == 2 and not self.soft_blocking)
                            if is_blocked:
                                nb_blocked += 1
                            nb_total += 1
                    
                    reason = f"No path {routing_start}(L{start_layer_for_search})->{routing_end}. "
                    reason += f"StartOcc={s_occ}, StartTrapped={nb_blocked}/{nb_total}. "
                    reason += f"UnblockRad={unblock_radius} (Factor={radius_factor})."
                    if attempt_idx == len(retry_factors) - 1:
                        print(f"DEBUG: {net_name} FAILED seg {i} (Final Attempt): {reason}")
                    last_failure_reason = reason
                    break

            # Accumulate path details
            for j in range(len(path)):
                cell = path[j]
                if j > 0 and path[j].layer != path[j - 1].layer:
                    final_total_vias += 1
                d = self._get_cell_difficulty(cell)
                final_total_difficulty += d
                final_cell_difficulties.append(d)

            if final_all_cells:
                if path and final_all_cells[-1] == path[0]:
                    final_all_cells.extend(path[1:])
                else:
                    final_all_cells.extend(path)
            else:
                final_all_cells.extend(path)
            
            # Update start for next segment
            current_start_grid = (path[-1].x, path[-1].y)
            current_start_layer = path[-1].layer
        
            # Restore occupancy to original state
            self._restore_occupancy_and_ownership(original_occupancy_and_ownership)
            
            if final_success:
                if attempt_idx > 0:
                    print(f"DEBUG: {net_name} recovered with unblock_radius factor {radius_factor}x")
                break # Success! Exit retry loop

        # Clear current net
        self._current_net = None
        self._default_trace_width_mm = 0.2  # Reset to default
        self.min_clearance = 0.2  # Reset to default

        if final_success:
            res = RoutePath(
                net=net_name,
                cells=final_all_cells,
                length=len(final_all_cells) * self.cell_size,
                via_count=final_total_vias,
                success=True,
                cell_size=self.cell_size,
                difficulty=final_total_difficulty,
                cell_difficulties=final_cell_difficulties,
                trace_width=self._default_trace_width_mm,
            )
            # Mark cells as occupied
            self._mark_path_occupied(net_name, res)
            self.routed_paths[net_name] = res
            return res
        else:
            res = RoutePath(
                net=net_name,
                cells=[],
                length=0.0,
                via_count=0,
                success=False,
                cell_size=self.cell_size,
                difficulty=0.0,
                cell_difficulties=[],
                failure_reason=last_failure_reason,
            )
            self.routed_paths[net_name] = res
            return res

    def _mark_path_occupied(self, net_name: str, path: RoutePath) -> None:
        """Marks the cells of a routed path as occupied.

        Detects vias automatically from layer transitions and blocks all layers
        at via locations to ensure DRC compliance for PTH vias.
        """
        # 1. Determine net and class IDs
        net_id = self._get_net_id(net_name)
        class_id = CLASS_DEFAULT
        required_clearance = self.min_clearance
        
        if self.design_rules:
            rules = self.design_rules.get_rules_for_net(net_name)
            class_id = self._get_class_id(rules)
            required_clearance = rules.clearance

        # 2. Identify Via locations (ordered path transitions)
        via_coords = set()
        for i in range(1, len(path.cells)):
            c1, c2 = path.cells[i - 1], path.cells[i]
            if c1.layer != c2.layer:
                via_coords.add((c1.x, c1.y))

        # 3. Add any explicitly requested via objects
        for via in path.explicit_vias:
            gx, gy = self._world_to_grid(via.x, via.y)
            via_coords.add((gx, gy))

        # 4. Mark occupancy
        unique_cells = set(path.cells)
        for cell in unique_cells:
            # Detect if this coordinate is a via
            is_via = (cell.x, cell.y) in via_coords
            width = path.via_diameter if is_via else path.trace_width

            # For vias, block ALL layers. For traces, block ONLY the current layer.
            # (Assuming PTH vias by default, which is the current state)
            affected = self._get_inflated_cells(
                cell.x,
                cell.y,
                cell.layer,
                width_mm=width,
                clearance_mm=required_clearance,
                all_layers=is_via,
            )

            for ax, ay, al in affected:
                # Only mark as occupied if not a hard block (-1)
                # Hard blocks should remain -1 as they represent obstacles
                if self.occupancy[ax, ay, al] != -1:
                    self.occupancy[ax, ay, al] = 2  # Mark as occupied by net
                    self.class_grid[ax, ay, al] = class_id  # Set net class
                    self.owner_grid[ax, ay, al] = net_id  # Set owner

                    if (ax, ay, al) not in self.net_occupancy:
                        self.net_occupancy[(ax, ay, al)] = set()
                    self.net_occupancy[(ax, ay, al)].add(net_name)

                    # Also update cell_owner map for conflict checking
                    self.cell_owner[(ax, ay, al)] = net_name

                    # Update congestion map (permanent penalty for occupied cells)
                    self.present_congestion[ax, ay, al] += 1.0

    def _compute_escape_point(
        self, start_cell: GridCell, target: GridCell, radius: int
    ) -> GridCell | None:
        """Finds the best escape point from a pin location.

        Prefers orthogonal directions towards the target.
        """
        best_cell = None
        best_score = -float("inf")

        # Directions: Orthogonal first, then Diagonal
        directions = [(0, 1), (0, -1), (1, 0), (-1, 0), (1, 1), (1, -1), (-1, 1), (-1, -1)]

        for dx, dy in directions:
            # Try to escape at 'radius' distance
            nx, ny = start_cell.x + dx * radius, start_cell.y + dy * radius

            if not (0 <= nx < self.grid_size[0] and 0 <= ny < self.grid_size[1]):
                continue

            nl = start_cell.layer

            # Check if this cell is strictly valid (0 or 2)
            if self.occupancy[nx, ny, nl] == -1:
                # Try closer?
                valid = False
                for r in range(radius - 1, 0, -1):
                    tx, ty = start_cell.x + dx * r, start_cell.y + dy * r
                    if (
                        0 <= tx < self.grid_size[0] and 0 <= ty < self.grid_size[1]
                    ) and self.occupancy[tx, ty, nl] != -1:
                        nx, ny = tx, ty
                        valid = True
                        break
                if not valid:
                    continue

            # Score: align with target + preference for orthogonal
            # Dot product with direction to target
            vec_x, vec_y = target.x - start_cell.x, target.y - start_cell.y
            dist = math.sqrt(vec_x**2 + vec_y**2) + 1e-6
            dot = (vec_x * dx + vec_y * dy) / dist

            is_ortho = dx == 0 or dy == 0
            score = dot + (1.0 if is_ortho else 0.0)

            if score > best_score:
                best_score = score
                best_cell = GridCell(nx, ny, nl)

        return best_cell

    def _get_line_path(self, start: GridCell, end: GridCell) -> list[GridCell]:
        """Returns a rasterized line path between start and end (Bresenham)."""
        x1, y1 = start.x, start.y
        x2, y2 = end.x, end.y
        points = []

        dx = abs(x2 - x1)
        dy = abs(y2 - y1)
        sx = 1 if x1 < x2 else -1
        sy = 1 if y1 < y2 else -1
        err = dx - dy

        while True:
            points.append(GridCell(x1, y1, start.layer))
            if x1 == x2 and y1 == y2:
                break
            e2 = 2 * err
            if e2 > -dy:
                err -= dy
                x1 += sx
            if e2 < dx:
                err += dx
                y1 += sy

        return points

    def _resolve_net_pins(
        self, net_name: str, netlist: Netlist, positions: Array
    ) -> dict[str, tuple[float, float, int, float]]:
        """Resolve pin names to absolute positions and attributes."""
        comp_by_ref = {c.ref: (i, c) for i, c in enumerate(netlist.components)}
        net = next((n for n in netlist.nets if n.name == net_name), None)
        pin_map = {}

        if not net:
            return {}

        for comp_ref, pin_name in net.pins:
            if comp_ref in comp_by_ref:
                comp_idx, comp = comp_by_ref[comp_ref]
                cx, cy = float(positions[comp_idx, 0]), float(positions[comp_idx, 1])
                rot_rad = math.radians((comp.initial_rotation or 0) * 90)
                side_idx = int(comp.initial_side or 0)

                for pin in comp.pins:
                    if pin.name == pin_name or pin.number == pin_name:
                        px, py = pin.absolute_position((cx, cy), rot_rad, side_idx)

                        # Generate keys
                        keys = [
                            f"{comp_ref}.{pin.name}",
                            f"{comp_ref}-{pin.name}",
                            f"{comp_ref}.{pin.number}",
                            f"{comp_ref}-{pin.number}",
                        ]

                        val = (
                            px,
                            py,
                            side_idx,
                            getattr(pin, "width", 1.0),
                        )  # Store width just in case
                        for k in keys:
                            pin_map[k] = val

                        # Also store generic "Comp" key if only 1 pin? No, ambiguous.
                        # print(f"DEBUG: Mapped {keys} -> {px},{py}")
                        break
        return pin_map

    def route_net_topology(
        self,
        net_name: str,
        graph: "NetGraph",
        netlist: Netlist,
        positions: Array,
        assignment: "LayerAssignment",
        cost_map: Array | None,
        p_scale: float,
    ) -> RoutePath:
        """Route a net using explicit topology constraints (SubNetEdges)."""
        pin_map = self._resolve_net_pins(net_name, netlist, positions)

        # Sort edges by priority (highest first)
        sorted_edges = sorted(graph.edges, key=lambda e: e.priority, reverse=True)

        combined_cells = []
        combined_vias = 0
        combined_difficulty = 0.0
        combined_cell_difficulties = []
        all_success = True
        failure_reason = ""

        route_cache = {}  # edge -> path

        for edge in sorted_edges:
            start_key = edge.source_pin
            end_key = edge.sink_pin

            # 1. Resolve coordinates
            if start_key not in pin_map or end_key not in pin_map:
                print(f"WARNING: Missing pin position for edge {start_key}->{end_key}")
                all_success = False
                failure_reason = f"Missing pin {start_key} or {end_key}"
                break

            start_info = pin_map[start_key]
            end_info = pin_map[end_key]

            p1 = (start_info[0], start_info[1])
            p2 = (end_info[0], end_info[1])
            sides = [start_info[2], end_info[2]]

            # 2. Determine Rules
            width = edge.trace_width_mm
            clearance = edge.clearance_mm

            # 3. Route Segment
            # We call route_net_rrr as a helper for P2P routing
            # It will utilize the occupancy grid.
            # IMPORTANT: Previous segments must be marked in occupancy for them to be obstacles/connectable?
            # Actually, if we want them to be Connectable, they must be marked as THIS net.
            # self._mark_path_occupied handles that.

            # Note: route_net_rrr clears the distance map cache.
            # This is fine as long as occupancy is updated.

            sub_path = self.route_net_rrr(
                net_name,
                [p1, p2],
                assignment,
                cost_map,
                p_scale,
                pin_sides=sides,
                trace_width_mm=width,
                clearance_mm=clearance,
            )

            if not sub_path.success:
                all_success = False
                failure_reason = f"Segment {start_key}->{end_key} failed: {sub_path.failure_reason}"
                break

            # 4. Integrate Result
            # Mark occupancy immediately so next segments can see it
            # This is already handled by route_net_rrr internally.
            # We just need to accumulate the path data.

            combined_cells.extend(sub_path.cells)
            combined_vias += sub_path.via_count
            combined_difficulty += sub_path.difficulty
            combined_cell_difficulties.extend(sub_path.cell_difficulties)

        if all_success:
            # Final path object for the entire net
            final_path = RoutePath(
                net=net_name,
                cells=combined_cells,
                length=len(combined_cells) * self.cell_size,
                via_count=combined_vias,
                success=True,
                difficulty=combined_difficulty,
                cell_difficulties=combined_cell_difficulties,
                trace_width=width,  # Use the last segment's width as a representative
            )
            self.routed_paths[net_name] = final_path
            return final_path
        else:
            # If any segment failed, the whole net fails
            final_path = RoutePath(
                net=net_name,
                cells=[],
                length=0.0,
                via_count=0,
                success=False,
                difficulty=0.0,
                cell_difficulties=[],
                failure_reason=failure_reason,
            )
            self.routed_paths[net_name] = final_path
            return final_path

    def route_net_with_escape(
        self,
        net_name: str,
        pin_positions: list[tuple[float, float]],
        assignment: "LayerAssignment",
        cost_map: Array | None = None,
        p_scale: float = 1.0,
    ) -> RoutePath:
        """Route net with both MST topology and pin escape.

        Combines two optimizations:
        1. Pin escape (find unblocked cells for pins)
        2. MST routing (optimal topology for multi-pin nets)

        Args:
            net_name: Name of the net
            pin_positions: List of pin positions in world coordinates
            assignment: Layer assignment for the net
            cost_map: Optional cost map
            p_scale: Congestion penalty scale

        Returns:
            RoutePath with routing result
        """
        from temper_placer.routing.layer_assignment import Layer

        if len(pin_positions) < 2:
            res = RoutePath(
                net=net_name,
                cells=[],
                length=0.0,
                via_count=0,
                success=True,
                difficulty=0.0,
                cell_difficulties=[],
            )
            self.routed_paths[net_name] = res
            return res

        layer = 0 if not assignment or assignment.primary_layer == Layer.L1_TOP else 1

        # Stage 1: Find escape points for all pins
        escape_points = []
        for pin_pos in pin_positions:
            escape_pt = self._find_escape_point(pin_pos, radius=10, layer=layer)
            if escape_pt is None:
                res = RoutePath(
                    net=net_name,
                    cells=[],
                    length=0.0,
                    via_count=0,
                    success=False,
                    difficulty=0.0,
                    cell_difficulties=[],
                    failure_reason="pin_blocked",
                )
                self.routed_paths[net_name] = res
                return res
            escape_points.append(escape_pt)

        # Stage 2: Route using MST topology
        escape_world_coords = [
            (gx * self.cell_size + self.origin[0], gy * self.cell_size + self.origin[1])
            for gx, gy in escape_points
        ]

        return self.route_net_mst(net_name, escape_world_coords, assignment, cost_map, p_scale)

    def route_net(
        self,
        net_name: str,
        pin_positions: list[tuple[float, float]],
        assignment: "LayerAssignment",
        cost_map: Array | None = None,
        pin_sides: list[int] | None = None,
    ) -> RoutePath:
        return self.route_net_rrr(
            net_name, pin_positions, assignment, cost_map, p_scale=1.0, pin_sides=pin_sides
        )

    def rrr_route_all_nets(
        self,
        netlist: Netlist,
        positions: Array,
        net_order: list[str],
        assignments: dict[str, "LayerAssignment"],
        cost_maps: dict[str, Array] | None = None,
        max_iterations: int = 20,
        history_increment: float = 1.0,
        history_decay: float = 0.9,
        p_scale_start: float = 1.0,
        p_scale_step: float = 2.0,
        progress_callback: Callable[[RoutingProgress], None] | None = None,
        incremental: bool = True,
        validate_final: bool = False,
        pin_positions_overrides: dict[str, list[tuple[float, float]]] | None = None,
        component_margin: float = 0.5,
        soft_c_spaces: dict[str, np.ndarray] | None = None,
    ) -> dict[str, RoutePath]:
        """Route all nets using iterative Rip-up and Reroute (RRR)."""
        from tqdm import tqdm  # Import here to avoid dependency issues if not installed

        start_time = time.perf_counter()
        # On multi-layer boards (>2), only block the component layer (usually Top)
        # to allow routing on inner/bottom layers.
        self.block_components(
            netlist.components,
            positions,
            margin=component_margin,
            layer_specific=(self.num_layers > 2),
        )
        # Block pads and register ownership (Critical for Surgical Unblocking)
        # Reverting to default margin (None -> Computed Safe) to prevent conflicts.
        # Strict Unblocking handles the courtyard access now.
        self.block_pads(netlist.components, positions, netlist)
        
        net_by_name = {n.name: n for n in netlist.nets}
        comp_by_ref = {c.ref: (i, c) for i, c in enumerate(netlist.components)}
        all_pin_positions = {}
        all_pin_sides = {}
        for net_name in net_order:
            if pin_positions_overrides and net_name in pin_positions_overrides:
                all_pin_positions[net_name] = pin_positions_overrides[net_name]
                all_pin_sides[net_name] = [0] * len(pin_positions_overrides[net_name])
                continue

            if net_name not in net_by_name:
                continue
            net = net_by_name[net_name]
            pin_positions = []
            pin_sides = []
            for comp_ref, pin_name in net.pins:
                if comp_ref in comp_by_ref:
                    comp_idx, comp = comp_by_ref[comp_ref]
                    for pin in comp.pins:
                        if pin.name == pin_name or pin.number == pin_name:
                            side = comp.initial_side or 0
                            pin_positions.append(
                                pin.absolute_position(
                                    tuple(positions[comp_idx]),
                                    math.radians((comp.initial_rotation or 0) * 90),
                                    side=side,
                                )
                            )
                            pin_sides.append(side)
                            break
            all_pin_positions[net_name] = pin_positions
            all_pin_sides[net_name] = pin_sides

        progress_history: list[RoutingProgress] = []
        forced_reroute: set[str] = set()  # Nets to force reroute next iteration
        is_cleanup_pass = False

        # RRR loop
        self.soft_blocking = True
        # DRC-3: Best State Tracking
        best_conflicts = float("inf")
        best_state = None
        best_iteration = -1

        for iteration in range(max_iterations):
            iter_start = time.perf_counter()
            p_scale = p_scale_start + iteration * p_scale_step

            # Determine which nets to route this iteration
            if iteration == 0 or not incremental:
                nets_to_route = [n for n in net_order if n in all_pin_positions]
            else:
                # Only reroute nets involved in conflicts + forced reroute (blockers)
                # Shuffle order to break symmetry and explore different solutions
                conflicted = set(self._get_conflicted_nets())
                conflicted.update(forced_reroute)  # Add blocking nets from previous iteration
                nets_to_route = list(conflicted)
                random.shuffle(nets_to_route)
                forced_reroute.clear()  # Reset for this iteration

            if iteration == max_iterations - 1:
                is_cleanup_pass = True
            
            if is_cleanup_pass:
                self.soft_blocking = False
                print(f"  Final strict pass iteration {iteration + 1}/{max_iterations}")
            else:
                print(f"  RRR Iteration {iteration + 1}/{max_iterations} (p_scale={p_scale:.1f})")

            # Track failed routes and their blockers
            failed_nets: list[str] = []
            blocking_nets_to_add: set[str] = set()

            # Route nets with progress bar
            with tqdm(total=len(nets_to_route), desc=f"Iter {iteration + 1}", unit="net") as pbar:
                processed_nets = set()
                for net_name in nets_to_route:
                    if net_name in processed_nets:
                        pbar.update(1)
                        continue

                    if net_name not in all_pin_positions:
                        pbar.update(1)
                        continue

                    # Check if net is part of a bus
                    bus = None
                    # DISABLED: Bus routing is experimental and causes failures in dense areas.
                    # Use robust route_net_rrr instead.
                    # bus = (
                    #    self.design_rules.get_bus_cohort_for_net(net_name)
                    #    if self.design_rules
                    #    else None
                    # )
                    if bus:
                        # Route entire bus
                        self.route_bus_cohort(
                            bus, all_pin_positions, assignments, cost_maps, p_scale=p_scale
                        )
                        for bn in bus.nets:
                            processed_nets.add(bn)
                        pbar.update(1)  # Note: progress bar might be slightly off if bus has N nets
                        continue

                    processed_nets.add(net_name)
                    if net_name not in all_pin_positions:
                        pbar.update(1)
                        continue

                    t_rip = time.perf_counter()
                    self.rip_up_net(net_name)
                    self.stats.profile.rip_up_ms += (time.perf_counter() - t_rip) * 1000.0

                    # Apply routing strategy (temper-b577)
                    net_rules = (
                        self.design_rules.get_rules_for_net(net_name) if self.design_rules else None
                    )
                    assignment = assignments.get(net_name)

                    original_via_cost = self.via_cost
                    if net_rules:
                        # Determine multiplier
                        multiplier = net_rules.via_cost_multiplier
                        if net_rules.routing_strategy == "wide_trace" and multiplier == 1.0:
                            multiplier = 10.0

                        if multiplier != 1.0:
                            self.via_cost *= multiplier

                    # Apply routing strategy layer filtering (temper-b577.1)
                    if net_rules and net_rules.routing_strategy:
                        strategy = net_rules.routing_strategy

                        plane_layer_indices = [
                            i
                            for i in range(self.num_layers)
                            if self.layer_stackup.is_plane_layer(i)
                        ]

                        if (
                            strategy in ("plane_preferred", "plane_required")
                            and plane_layer_indices
                        ):
                            # Restrict to plane layers (usually L2/L3)
                            layer_map_inv = {
                                0: Layer.L1_TOP,
                                1: Layer.L2_GND if self.num_layers > 2 else Layer.L4_BOT,
                                2: Layer.L3_PWR,
                                3: Layer.L4_BOT if self.num_layers > 2 else 1,  # fallback
                            }
                            plane_layers = {
                                layer_map_inv[i] for i in plane_layer_indices if i in layer_map_inv
                            }

                            if plane_layers:
                                # For plane_required, we MUST allow Top layer if pins are on Top
                                # But we want traces to stay on planes.
                                # So we allow Top but discourage it via primary_layer.
                                allowed = plane_layers.copy()
                                allowed.add(Layer.L1_TOP)
                                allowed.add(Layer.L4_BOT)

                                # Override assignment for this specific route
                                assignment = LayerAssignment(
                                    net=net_name,
                                    primary_layer=list(plane_layers)[0],
                                    allowed_layers=allowed,
                                    vias_required=True,
                                    reason=f"Routing strategy: {strategy}",
                                )

                        elif strategy == "top_layer_only":
                            assignment = LayerAssignment(
                                net=net_name,
                                primary_layer=Layer.L1_TOP,
                                allowed_layers={Layer.L1_TOP},
                                vias_required=False,
                                reason="Routing strategy: top_layer_only",
                            )

                        elif strategy == "bottom_layer_only":
                            target_layer = Layer.L4_BOT if self.num_layers > 1 else Layer.L1_TOP
                            allowed = (
                                {Layer.L1_TOP, target_layer}
                                if self.num_layers > 1
                                else {Layer.L1_TOP}
                            )
                            assignment = LayerAssignment(
                                net=net_name,
                                primary_layer=target_layer,
                                allowed_layers=allowed,
                                vias_required=True if self.num_layers > 1 else False,
                                reason="Routing strategy: bottom_layer_only",
                            )

                    # Check for explicit topology
                    topology = None
                    if self.design_rules and net_name in self.design_rules.net_topologies:
                        topology = self.design_rules.net_topologies[net_name]

                    try:
                        # Precompute zone-aware clearance grid for this net (temper-d6kv.3)
                        if self.clearance_matrix:
                            self._precompute_clearance_grid(net_name, self.clearance_matrix)

                        # Apply per-net soft C-Space if provided
                        if soft_c_spaces and net_name in soft_c_spaces:
                            self.soft_c_space = soft_c_spaces[net_name]

                        if topology:
                            result = self.route_net_topology(
                                net_name,
                                topology,
                                netlist,
                                positions,
                                assignment,
                                cost_maps.get(net_name) if cost_maps else None,
                                p_scale=p_scale,
                            )
                        else:
                            # Use MST router by default for better multi-pin support and via arrays
                            result = self.route_net_mst(
                                net_name,
                                all_pin_positions[net_name],
                                assignment,
                                cost_map=cost_maps.get(net_name) if cost_maps else None,
                                p_scale=p_scale,
                                pin_sides=all_pin_sides.get(net_name),
                            )
                    finally:
                        self.via_cost = original_via_cost

                    # Ensure result is always stored
                    self.routed_paths[net_name] = result

                    # Fallback: If blocked, try escape routing
                    if not result.success and "blocked" in str(result.failure_reason).lower():
                        # print(f"    Fallback to Escape Routing for {net_name}...")
                        result = self.route_net_with_escape(
                            net_name,
                            all_pin_positions[net_name],
                            assignments.get(net_name),
                            cost_maps.get(net_name) if cost_maps else None,
                            p_scale=p_scale,
                        )
                        # result is already stored above, but we update it with escape result
                        self.routed_paths[net_name] = result

                    # If route failed, find blocking nets
                    if not result.success:
                        failed_nets.append(net_name)
                        pins = all_pin_positions[net_name]
                        if len(pins) >= 2:
                            blockers = self._find_blocking_nets(pins[0], pins[1])
                            blocking_nets_to_add.update(blockers)
                        # Ensure we retry this net next time
                        blocking_nets_to_add.add(net_name)

                    pbar.update(1)

            # Add blocking nets to next iteration's reroute list
            if blocking_nets_to_add:
                forced_reroute.update(blocking_nets_to_add)
                print(
                    f"    Found {len(blocking_nets_to_add)} blocking nets: {', '.join(list(blocking_nets_to_add)[:3])}{'...' if len(blocking_nets_to_add) > 3 else ''}"
                )

            # Analyze conflicts (computed once, reused for status update)
            t_conf = time.perf_counter()
            overlap_conflicts, bottleneck_conflicts, conflicted_nets = self._analyze_conflicts()
            self.stats.profile.analyze_conflicts_ms += (time.perf_counter() - t_conf) * 1000.0
            total_conflicts = overlap_conflicts + bottleneck_conflicts
            conflicted_set = set(conflicted_nets)  # For O(1) lookups

            # Update convergence status for all routed nets (using cached set)
            for net_name in nets_to_route:
                if net_name in self.routed_paths:
                    result = self.routed_paths[net_name]
                    is_conflicted = net_name in conflicted_set if result.success else True
                    self._update_net_status(net_name, result, is_conflicted)

            # Calculate metrics
            iter_time_ms = (time.perf_counter() - iter_start) * 1000.0
            nets_routed = sum(1 for r in self.routed_paths.values() if r.success)
            nets_failed = len(self.routed_paths) - nets_routed
            total_vias = sum(r.via_count for r in self.routed_paths.values())
            total_length = sum(r.length for r in self.routed_paths.values())
            avg_length = total_length / max(1, len(self.routed_paths))
            nets_per_sec = len(nets_to_route) / max(0.001, iter_time_ms / 1000.0)

            progress = RoutingProgress(
                iteration=iteration + 1,
                total_iterations=max_iterations,
                p_scale=p_scale,
                total_conflicts=total_conflicts,
                overlap_conflicts=overlap_conflicts,
                bottleneck_conflicts=bottleneck_conflicts,
                nets_routed=nets_routed,
                nets_failed=nets_failed,
                avg_path_length=avg_length,
                total_vias=total_vias,
                iteration_time_ms=iter_time_ms,
                nets_per_second=nets_per_sec,
                conflicted_nets=conflicted_nets,
            )
            progress_history.append(progress)

            if progress_callback:
                progress_callback(progress)

            # DRC-3: Track Best State
            if total_conflicts < best_conflicts:
                best_conflicts = total_conflicts
                best_state = self._save_state()
                best_iteration = iteration + 1
                if total_conflicts == 0:
                    print(f"  RRR Converged to 0 conflicts at iteration {iteration + 1}!")
                    if not is_cleanup_pass:
                        # Force one last pass with strict blocking to be 100% sure
                        is_cleanup_pass = True
                        self.soft_blocking = False
                        print("  Running final strict pass to verify Zero-DRC...")
                        continue
                    break

            # Print result for this iteration
            print(
                f"    Conflicts: {total_conflicts} (overlap: {overlap_conflicts}, bottleneck: {bottleneck_conflicts})"
            )
            print(f"    Routed: {nets_routed}, Failed: {nets_failed}, Vias: {total_vias}")
            print(f"    Time: {iter_time_ms:.0f}ms ({nets_per_sec:.1f} nets/s)")
            if conflicted_nets and len(conflicted_nets) <= 5:
                print(f"    Conflicted nets: {', '.join(conflicted_nets)}")
            elif conflicted_nets:
                print(f"    Conflicted nets: {len(conflicted_nets)} nets")

            # Callback
            if progress_callback:
                progress_callback(progress)

            if total_conflicts == 0 and nets_failed == 0:
                print("  ✓ Routing complete - no conflicts and all nets routed!")
                break

            self.update_congestion_costs(history_increment)
            self.decay_history_costs(history_decay)

        if best_state is not None:
            print(
                f"  Restoring best state from iteration {best_iteration} (Conflicts: {best_conflicts})"
            )
            self._restore_state(best_state)
            
            # Zero-DRC Guarantee: If we still have conflicts, rip up the offending nets.
            # This ensures that we never return a design with shorts, even if incomplete.
            if best_conflicts > 0:
                _, _, final_conflicts = self._analyze_conflicts()
                print(f"  Final cleanup: Ripping up {len(final_conflicts)} conflicted nets to ensure Zero-DRC.")
                for net in final_conflicts:
                    self.rip_up_net(net)
                
                # Verify zero conflicts
                final_overlap, final_bottleneck, _ = self._analyze_conflicts()
                print(f"  ✓ Zero-DRC Guaranteed: {final_overlap} overlaps, {final_bottleneck} bottlenecks.")

        # Final Post-Processing (now trace-aware)
        if hasattr(self, "_run_post_processing"):
            self._run_post_processing(netlist, positions)

        self.stats.total_time_ms = (time.perf_counter() - start_time) * 1000.0
        self.stats.nets_routed = sum(1 for r in self.routed_paths.values() if r.success)
        self.stats.nets_routed = sum(1 for r in self.routed_paths.values() if r.success)
        self.progress_history = progress_history

        # Print profiling stats
        print("\n=== Router Profiling Stats ===")
        print(f"Total Time: {self.stats.total_time_ms:.1f}ms")
        print(f"  - Cost Prep: {self.stats.profile.prepare_costs_ms:.1f}ms")
        print(f"  - Rip-up: {self.stats.profile.rip_up_ms:.1f}ms")
        print(f"  - A* Total: {self.stats.profile.astar_total_ms:.1f}ms")
        print(
            f"    - Numba: {self.stats.profile.numba_time_ms:.1f}ms ({self.stats.profile.numba_calls} calls, {self.stats.profile.numba_time_ms / max(1, self.stats.profile.numba_calls):.3f}ms/call)"
        )
        print(
            f"    - Python: {self.stats.profile.python_time_ms:.1f}ms ({self.stats.profile.python_calls} calls, {self.stats.profile.python_time_ms / max(1, self.stats.profile.python_calls):.3f}ms/call)"
        )
        print(f"  - Conflict Analysis: {self.stats.profile.analyze_conflicts_ms:.1f}ms")
        print("==============================\n")

        # Optional final validation
        if validate_final:
            from temper_placer.routing.routing_invariants import (
                format_violations,
                validate_no_overlaps,
                validate_route_result,
            )

            # Validate each route
            all_violations = []
            for route in self.routed_paths.values():
                all_violations.extend(validate_route_result(route, self))

            if all_violations:
                print(format_violations(all_violations))

            # Check for final overlaps
            overlaps = validate_no_overlaps(self.routed_paths)
            if overlaps:
                print(f"  Final overlap check: {len(overlaps)} overlapping cells")
                for net1, net2, cell in overlaps[:5]:
                    print(f"    {net1} at ({cell[0]}, {cell[1]}, L{cell[2] + 1})")

        # Post-Processing Pipeline (temper-2whm)
        self._run_post_processing(netlist, positions)

        return self.routed_paths

    def _analyze_conflicts(self) -> tuple[int, int, list[str]]:
        """Analyze and classify conflicts.

        Returns:
            Tuple of (overlap_conflicts, bottleneck_conflicts, conflicted_nets)
            - overlap_conflicts: cells with exactly 2 nets
            - bottleneck_conflicts: cells with 3+ nets (severe)
            - conflicted_nets: list of net names involved in conflicts
        """
        overlap_count = 0
        bottleneck_count = 0
        conflicted_nets: set[str] = set()

        for (_x, _y, _layer), nets in self.net_occupancy.items():
            if len(nets) == 2:
                overlap_count += 1
                conflicted_nets.update(nets)
            elif len(nets) > 2:
                bottleneck_count += 1
                conflicted_nets.update(nets)

        return overlap_count, bottleneck_count, sorted(conflicted_nets)

    def _get_conflicted_nets(self) -> list[str]:
        """Get list of nets involved in conflicts for incremental rerouting.

        Excludes nets that have converged (stable conflict-free for threshold iterations).
        """
        conflicted: set[str] = set()
        for nets in self.net_occupancy.values():
            if len(nets) > 1:
                conflicted.update(nets)

        # Exclude converged nets
        non_converged = [n for n in conflicted if not self._is_net_converged(n)]
        return sorted(non_converged)

    def _find_blocking_nets(
        self, start: tuple[float, float], end: tuple[float, float], radius: int = 5
    ) -> set[str]:
        """Find nets that are blocking the path between start and end.

        Looks at cells along the Manhattan path between start and end
        and identifies which nets occupy those cells.
        """
        blockers: set[str] = set()

        # Convert to grid coordinates
        start_grid = self._world_to_grid(start[0], start[1])
        end_grid = self._world_to_grid(end[0], end[1])

        # Sample cells along Manhattan path
        x0, y0 = start_grid
        x1, y1 = end_grid

        # Check cells in bounding box with some radius
        min_x = max(0, min(x0, x1) - radius)
        max_x = min(self.grid_size[0], max(x0, x1) + radius)
        min_y = max(0, min(y0, y1) - radius)
        max_y = min(self.grid_size[1], max(y0, y1) + radius)

        for x in range(min_x, max_x):
            for y in range(min_y, max_y):
                for layer in range(self.num_layers):
                    key = (x, y, layer)
                    if key in self.net_occupancy:
                        blockers.update(self.net_occupancy[key])

        return blockers

    def _is_net_converged(self, net_name: str, threshold: int = 2) -> bool:
        """Check if a net has converged (conflict-free for threshold iterations)."""
        status = self._net_status.get(net_name)
        if not status:
            return False
        return status.converged or status.conflict_free_count >= threshold

    def _compute_path_hash(self, cells: list[GridCell]) -> int:
        """Compute a hash of a path for change detection."""
        if not cells:
            return 0
        return hash(tuple((c.x, c.y, c.layer) for c in cells))

    def _save_state(self) -> dict:
        """Save current routing state."""
        return {
            "routed_paths": self.routed_paths.copy(),
            "occupancy": self.occupancy.copy(),
            "net_occupancy": {k: v.copy() for k, v in self.net_occupancy.items()},
            "cell_owner": self.cell_owner.copy(),
            "present_congestion": self.present_congestion.copy(),
            "history_cost": self.history_cost.copy(),
            "owner_grid": self.owner_grid.copy(),
            "class_grid": self.class_grid.copy(),
            "_pad_net_map": self._pad_net_map.copy(),
            "_net_status": {k: v for k, v in self._net_status.items()},
            "net_to_id": self.net_to_id.copy(),
            "_next_net_id": self._next_net_id,
        }

    def _restore_occupancy_and_ownership(self, original_state: list) -> None:
        """Restore occupancy and ownership state from a saved list."""
        for (
            key,
            original_val,
            original_class_id,
            original_owner,
            was_in_net_occ,
            original_congestion,
        ) in original_state:
            gx, gy, l = key
            # Only restore if the cell is currently free (0)
            # If it became part of a routed path (2), we keep it as 2.
            # If it is -1? We restore to whatever it was.
            # But wait, unblocking sets it to 0. 
            # If routing claimed it, it's 2.
            # If routing failed, it's 0.
            # So if it's 0, restore. 
            # If it's 2 (occupied by CURRENT net), keep it.
            # WARN: If retry failed, we want to restore EVERYTHING even if we visited it?
            # No, if retry failed, we haven't called _mark_path_occupied yet!
            # So the grid is still 0 (or whatever temporary value A* logic set? A* uses CameFrom, doesn't set occupancy).
            # So the grid should be 0.
            
            # The only case where it is NOT 0 is if some other process constrained it?
            # No.
            
            # However, logic below (lines 2321+) checked for == 0.
            # Let's keep that safely.
            
            if self.occupancy[gx, gy, l] == 0:
                self.occupancy[gx, gy, l] = original_val
                self.class_grid[gx, gy, l] = original_class_id
                self.present_congestion[gx, gy, l] = original_congestion
                
                if original_owner is not None:
                    self.cell_owner[key] = original_owner
                
                if was_in_net_occ:
                    if key not in self.net_occupancy:
                        self.net_occupancy[key] = set()
                    self.net_occupancy[key].add(self._current_net) # Use current net name? No, wait. 
                    # was_in_net_occ logic was "net_name in self.net_occupancy[key]".
                    # We are in route_net_rrr context. net_name is available if passed.
                    # But helper doesn't know net_name. `self._current_net` was set in route_net_rrr.
        
    def _restore_state(self, state: dict) -> None:
        """Restore routing state."""
        self.routed_paths = state["routed_paths"]
        self.occupancy = state["occupancy"]
        self.net_occupancy = state["net_occupancy"]
        self.cell_owner = state["cell_owner"]
        self.present_congestion = state["present_congestion"]
        self.history_cost = state["history_cost"]
        self.owner_grid = state.get("owner_grid", self.owner_grid)
        self.class_grid = state.get("class_grid", self.class_grid)
        self._pad_net_map = state.get("_pad_net_map", self._pad_net_map)
        self._net_status = state.get("_net_status", self._net_status)
        self.net_to_id = state.get("net_to_id", self.net_to_id)
        self._next_net_id = state.get("_next_net_id", self._next_net_id)

        # Reset Numba views to ensure they are synchronized with restored arrays
        self._history_np = None
        self._congestion_np = None
        self._occupancy_np = None
        self._owner_np = None

    def _update_net_status(self, net_name: str, path: RoutePath, is_conflicted: bool) -> None:
        """Update convergence status for a net after routing."""
        new_hash = self._compute_path_hash(path.cells)

        status = self._net_status.get(net_name)
        if status is None:
            self._net_status[net_name] = NetStatus(
                net_name=net_name,
                path_hash=new_hash,
                conflict_free_count=0 if is_conflicted else 1,
                converged=False,
            )
            return

        # Check if path changed
        path_changed = status.path_hash != new_hash

        if is_conflicted or path_changed:
            # Reset convergence counter
            self._net_status[net_name] = NetStatus(
                net_name=net_name,
                path_hash=new_hash,
                conflict_free_count=0,
                converged=False,
            )
        else:
            # Increment conflict-free counter
            new_count = status.conflict_free_count + 1
            self._net_status[net_name] = NetStatus(
                net_name=net_name,
                path_hash=new_hash,
                conflict_free_count=new_count,
                converged=new_count >= 2,
            )

    def route_bus_cohort(
        self,
        bus: "BusCohortConstraint",
        all_pin_positions: dict[str, list[tuple[float, float]]],
        assignments: dict[str, "LayerAssignment"],
        cost_maps: dict[str, Array] | None = None,
        p_scale: float = 1.0,
    ) -> None:
        """Routes a bus cohort in parallel.

        Args:
            bus: Bus group constraint
            all_pin_positions: Map of net names to pin positions
            assignments: Map of net names to layer assignments
            cost_maps: Optional per-net cost maps
            p_scale: Penalty scale for RRR
        """
        # 1. Collect start/end grid cells for all nets
        # We assume 2nd pin (point-to-point) for now.
        start_grid = []
        end_grid = []

        for net_name in bus.nets:
            pins = all_pin_positions[net_name]
            if len(pins) < 2:
                continue
            start_grid.append(self._world_to_grid(pins[0][0], pins[0][1]))
            end_grid.append(self._world_to_grid(pins[1][0], pins[1][1]))

        if not start_grid:
            return

        # 2. Unblock pads for all nets in the cohort
        original_occupancy = []
        unblock_radius = 5  # Cells

        for net_name in bus.nets:
            pins = all_pin_positions[net_name]
            for px, py in pins:
                gx, gy = self._world_to_grid(px, py)
                for dx in range(-unblock_radius, unblock_radius + 1):
                    for dy in range(-unblock_radius, unblock_radius + 1):
                        nx, ny = gx + dx, gy + dy
                        if 0 <= nx < self.grid_size[0] and 0 <= ny < self.grid_size[1]:
                            for l in range(self.num_layers):
                                if int(self.occupancy[nx, ny, l]) != 0:
                                    original_occupancy.append(
                                        (nx, ny, l, int(self.occupancy[nx, ny, l]))
                                    )
                                    self.occupancy[nx, ny, l] = 0

        # 3. Find parallel paths
        # We use the layer from the first net's assignment
        first_net = bus.nets[0]
        layer = 0
        if first_net in assignments:
            layer = assignments[first_net].primary_layer.value

        all_net_paths = self.find_bus_path_rrr(
            start_grid, end_grid, layer=layer, bus_constraint=bus, p_scale=p_scale
        )

        # 4. Process results
        if all_net_paths:
            for i, net_name in enumerate(bus.nets):
                path = all_net_paths[i]

                # Check if this net matches its own end pin (simple check)
                # In more advanced, we'd adjust the endpoints

                res = RoutePath(
                    net=net_name,
                    cells=path,
                    length=len(path) * self.cell_size,
                    via_count=0,
                    success=True,
                    trace_width=self.design_rules.get_rules_for_net(net_name).trace_width
                    if self.design_rules
                    else 0.2,
                )
                self.routed_paths[net_name] = res

                # Update occupancy (simplification: only for final cells)
                # Real implementation should use _get_inflated_cells
                for cell in path:
                    self.occupancy[cell.x, cell.y, cell.layer] = 2
        else:
            # Mark all as failed
            for net_name in bus.nets:
                res = RoutePath(
                    net=net_name,
                    cells=[],
                    length=0.0,
                    via_count=0,
                    success=False,
                    failure_reason="Could not find parallel bus path",
                )
                self.routed_paths[net_name] = res

        # 5. Restore original occupancy for untouched cells
        for gx, gy, l, v in original_occupancy:
            if self.occupancy[gx, gy, l] == 0:
                self.occupancy[gx, gy, l] = v

    def route_net_mst(
        self,
        net_name: str,
        pin_positions: list[tuple[float, float]],
        assignment: "LayerAssignment",
        cost_map: Array | None = None,
        p_scale: float = 1.0,
        pin_sides: list[int] | None = None,
        trace_width_mm: float | None = None,
        clearance_mm: float | None = None,
        via_diameter_mm: float | None = None,
        via_drill_mm: float | None = None,
        bypass_clearance_generation: bool = False,
        custom_heuristic: "Callable | None" = None,
        guide_map: np.ndarray | None = None,
        guide_bias: float = 0.0,
    ) -> RoutePath:
        """Routes a multi-pin net using a Minimum Spanning Tree (MST) approach.

        This method connects all pins of a net by finding paths between them,
        prioritizing connections that minimize overall cost and conflicts.
        It uses a modified Prim's algorithm to build the MST.
        """
        from temper_placer.routing.layer_assignment import Layer

        # Track net rules for layer cost system (temper-b577)
        if self.design_rules:
            self._current_net_rules = self.design_rules.get_rules_for_net(net_name)
        else:
            self._current_net_rules = None
        
        # DEBUG: Diagnostic for router path selection
        print(f"DEBUG: route_net_mst called for {net_name} ({len(pin_positions)} pins)", flush=True)

        if len(pin_positions) < 2:
            # Single-pin or empty nets don't need routing
            res = RoutePath(
                net=net_name,
                cells=[],
                length=0.0,
                via_count=0,
                success=True,
                difficulty=0.0,
                cell_difficulties=[],
            )
            self.routed_paths[net_name] = res
            return res

        grid_pins = [self._world_to_grid(x, y) for x, y in pin_positions]
        num_pins = len(grid_pins)
        # print(f"DEBUG_MST: Net={net_name} NumPins={num_pins} GridPins={grid_pins}")
        # print(f"DEBUG_MST: pin_sides={pin_sides}")

        # Map pin sides to layers
        pin_layers = []
        if pin_sides is not None:
            for side in pin_sides:
                pin_layers.append(0 if side == 0 else (self.num_layers - 1))
        else:
            # Default to all Top or use Through-hole assumption
            pin_layers = [0] * num_pins

        # print(f"DEBUG_MST: pin_layers={pin_layers}")

        # Determine candidate start layers based on first pin
        candidate_start_layers_per_pin = []
        for i, (gx, gy) in enumerate(grid_pins):
            candidates = []
            if pin_sides is not None:
                candidates.append(pin_layers[i])
            else:
                candidates.append(0)  # Default to top layer
                if assignment:
                    if assignment.primary_layer == Layer.L4_BOT:
                        candidates = [self.num_layers - 1]
                    elif assignment.primary_layer in (Layer.L2_GND, Layer.L3_PWR):
                        candidates = [1 if assignment.primary_layer == Layer.L2_GND else 2]

                    if len(assignment.allowed_layers) > 1:
                        layer_map = {
                            Layer.L1_TOP: 0,
                            Layer.L2_GND: 1,
                            Layer.L3_PWR: 2,
                            Layer.L4_BOT: self.num_layers - 1,
                        }
                        for lay_enum in assignment.allowed_layers:
                            lay_idx = layer_map.get(lay_enum)
                            if lay_idx is not None and lay_idx not in candidates:
                                candidates.append(lay_idx)
                else:
                    candidates = [0, self.num_layers - 1]  # No assignment? Try Top then Bottom.
            candidate_start_layers_per_pin.append(list(set(candidates)))  # Remove duplicates

        allow_via = len(assignment.allowed_layers) > 1 if assignment else True

        # Set current net for DRC oracle queries
        self._current_net = net_name

        # Determine design rules upfront for unblocking calculation
        trace_width = trace_width_mm if trace_width_mm is not None else self._default_trace_width_mm
        via_diameter = via_diameter_mm if via_diameter_mm is not None else 0.6
        via_drill = via_drill_mm if via_drill_mm is not None else 0.3
        clearance = clearance_mm if clearance_mm is not None else self.min_clearance

        if self.design_rules and trace_width_mm is None:
            rules = self.design_rules.get_rules_for_net(net_name)
            trace_width = rules.trace_width
            via_diameter = rules.via_diameter
            via_drill = rules.via_drill
            clearance = rules.clearance

        # Determine class-specific unblock needs
        # CRITICAL: Must be large enough to unblock entire component pads (10mm default)
        unblock_radius = max(5, int(10.0 / self.cell_size))  # 10mm radius for large pads
        if HAS_NUMBA and self.design_rules:
            rules_c = self.design_rules.get_rules_for_net(net_name)
            class_id = self._get_class_id(rules_c)

            MAX_HV = 400.0
            LV_REF = 0.0
            sep_hv_lv = get_hv_lv_separation(MAX_HV, LV_REF)
            iso_hv_hv = 2.5

            if class_id == CLASS_HV:
                req_from_hv = iso_hv_hv
                req_from_lv = sep_hv_lv
            else:
                req_from_hv = sep_hv_lv
                req_from_lv = self.min_clearance

            rad_hv = int(math.ceil(req_from_hv / self.cell_size))
            rad_lv = int(math.ceil(req_from_lv / self.cell_size))
            unblock_radius = max(unblock_radius, rad_hv + 2, rad_lv + 2)

        # Base net isolation unblock
        req_isolation = clearance + (trace_width / 2.0)
        rad_isolation = int(math.ceil(req_isolation / self.cell_size))
        unblock_radius = max(unblock_radius, rad_isolation + 2)

        # Adaptive Unblocking Retry Loop
        retry_factors = [1.0]
        if self._adaptive_unblocking_enabled:
            # 1.0x, 2.0x, 3.0x (Standard) -> 3.0x (Desperation Soft Rip-up)
            retry_factors = [1.0, 2.0, 3.0, 3.0]
        
        final_result = None

        for attempt_idx, radius_factor in enumerate(retry_factors):
            # Soft Rip-up: Last attempt uses reduced p_scale
            is_desperation = (attempt_idx == len(retry_factors) - 1) and (len(retry_factors) > 1)
            current_p_scale = 0.1 if is_desperation else p_scale
            
            if is_desperation:
                 pass # Could log: print(f"DEBUG: {net_name} attempting Soft Rip-up (p=0.1)...")

            # Recalculate unblock radius with factor
            current_unblock_radius = int(unblock_radius * radius_factor)
            
            # Clear distance map cache
            self._clear_distance_map_cache()

            # Temporarily unblock pin locations with current radius
            original_occupancy = []
            for gx, gy in grid_pins:
                for dx in range(-current_unblock_radius, current_unblock_radius + 1):
                    for dy in range(-current_unblock_radius, current_unblock_radius + 1):
                        nx, ny = gx + dx, gy + dy
                        if 0 <= nx < self.grid_size[0] and 0 <= ny < self.grid_size[1]:
                            for l in range(self.num_layers):
                                if self.occupancy[nx, ny, l] == -1:
                                    pad_net = self._pad_net_map.get((nx, ny, l))
                                    # Semi-Strict Unblocking:
                                    # 1. Own Pad (pad_net == net_name) -> YES
                                    # 2. Courtyard (pad_net is None) -> YES (Required for escape)
                                    # 3. Neighbor Pad (pad_net == Other) -> NO!
                                    if pad_net is None or pad_net == net_name:
                                        original_occupancy.append((nx, ny, l, -1))
                                        self.occupancy[nx, ny, l] = 0
            
            # Force clear exact centers
            for i, (gx, gy) in enumerate(grid_pins):
                for l in range(self.num_layers):
                    if self.occupancy[gx, gy, l] != 0:
                        original_occupancy.append((gx, gy, l, int(self.occupancy[gx, gy, l])))
                        self.occupancy[gx, gy, l] = 0

            # --- MST Init ---
            connected_pins = set()
            connected_pins.add(0) # Start pin 0
            
            # Reset PQ
            pq = []
            
            allowed_layers_indices = (
                [l.value - 1 for l in assignment.allowed_layers] if assignment else None
            )

            # Seed PQ from start pin (0) to all other pins
            for i in range(1, num_pins):
                for start_l in candidate_start_layers_per_pin[0]:
                    for end_l in candidate_start_layers_per_pin[i]:
                        path = self.find_path_rrr(
                            grid_pins[0], grid_pins[i], start_l, allow_via,
                            allowed_layers=allowed_layers_indices, cost_map=cost_map, p_scale=current_p_scale,
                            end_layer=end_l, clearance_mm=clearance_mm, clearance_mask=None,
                            custom_heuristic=custom_heuristic, guide_map=guide_map, guide_bias=guide_bias
                        )
                        if path:
                            # Cost is path length + via cost
                            path_cost = (
                                len(path)
                                + sum(
                                    1 for j in range(1, len(path)) if path[j].layer != path[j - 1].layer
                                )
                                * self.via_cost
                            )
                            heapq.heappush(pq, (path_cost, 0, i, path))

            current_iter_all_cells = []
            current_iter_total_vias = 0
            current_iter_difficulty = 0.0
            current_iter_difficulties = []
            success = False
            
            # MST Loop
            while pq and len(connected_pins) < num_pins:
                cost, from_idx, to_idx, path = heapq.heappop(pq)
                if to_idx in connected_pins:
                    continue
                
                connected_pins.add(to_idx)
                current_iter_all_cells.extend(path)
                
                # Metrics and vias
                for j in range(len(path)):
                    if j > 0 and path[j].layer != path[j-1].layer:
                        current_iter_total_vias += 1
                    d = self._get_cell_difficulty(path[j])
                    current_iter_difficulty += d
                    current_iter_difficulties.append(d)
                
                # Add neighbors of newly connected pin
                for i in range(num_pins):
                    if i not in connected_pins:
                         for start_l in candidate_start_layers_per_pin[to_idx]:
                             for end_l in candidate_start_layers_per_pin[i]:
                                  path_new = self.find_path_rrr(
                                     grid_pins[to_idx], grid_pins[i], start_l, allow_via,
                                     allowed_layers=allowed_layers_indices, cost_map=cost_map, p_scale=current_p_scale,
                                     end_layer=end_l, clearance_mm=clearance_mm, clearance_mask=None,
                                     custom_heuristic=custom_heuristic, guide_map=guide_map, guide_bias=guide_bias
                                  )
                                  if path_new:
                                      pc = (
                                          len(path_new) 
                                          + sum(1 for j in range(1,len(path_new)) if path_new[j].layer != path_new[j-1].layer) 
                                          * self.via_cost
                                      )
                                      heapq.heappush(pq, (pc, to_idx, i, path_new))

            if len(connected_pins) == num_pins:
                success = True
                
                # --- FEAT-1: Automatic Via Array Generation (Inside Loop) ---
                explicit_vias = []
                if self.design_rules:
                    via_template = self.design_rules.get_via_template(net_name)
                    if via_template and via_template.via_count > 1:
                        for i in range(1, len(current_iter_all_cells)):
                            c1 = current_iter_all_cells[i - 1]
                            c2 = current_iter_all_cells[i]

                            if c1.layer != c2.layer:
                                center_x = c2.x * self.cell_size + self.origin[0]
                                center_y = c2.y * self.cell_size + self.origin[1]
                                positions = via_template.get_via_positions(center_x, center_y)
                                layers = ["F.Cu", "B.Cu"]
                                for px, py in positions:
                                    explicit_vias.append(
                                        TraceVia(
                                            net=net_name,
                                            position=(px, py),
                                            size=via_template.pad_diameter,
                                            drill=via_template.drill_diameter,
                                            layers=layers,
                                        )
                                    )
                                    # Note: We don't mark occupancy for extra vias here, 
                                    # we rely on explicit_vias in RoutePath and _mark_path_occupied later.
                                    # Actually, MST marking logic was inline. 
                                    # Let's keep it simple: just create the objects.

                final_result = RoutePath(
                    net=net_name,
                    cells=current_iter_all_cells,
                    length=len(current_iter_all_cells) * self.cell_size,
                    via_count=current_iter_total_vias,
                    success=True,
                    cell_size=self.cell_size,
                    difficulty=current_iter_difficulty,
                    cell_difficulties=current_iter_difficulties,
                    trace_width=trace_width,
                    explicit_vias=explicit_vias
                )
            
            # Restore state
            # Inline restoration because original_occupancy is 4-tuple here, not 6-tuple expected by helper
            for gx, gy, l, v in original_occupancy:
                if self.occupancy[gx, gy, l] == 0:
                     self.occupancy[gx, gy, l] = v
            
            if success:
                if attempt_idx > 0:
                     print(f"DEBUG: {net_name} MST recovered with unblock factor {radius_factor}x")
                break
        
        if final_result:
            # Mark cells as occupied
            # We need to replicate the localized inflation logic that was at the end of function
            # OR utilize _mark_path_occupied() which is generic.
            # MST had specific logic for per-path via inflation?
            # No, it just iterated cells.
            
            # Let's use the explicit logic from before to be safe about via diameters.
            # But wait, RoutePath has explicit_vias now.
            # _mark_path_occupied handles explicit_vias!
            self._mark_path_occupied(net_name, final_result)
            
            self.routed_paths[net_name] = final_result
            return final_result
        else:
             res = RoutePath(net=net_name, cells=[], length=0.0, via_count=0, success=False, failure_reason="MST failed connectivity")
             self.routed_paths[net_name] = res
             return res

        if self.drc_oracle is not None:
            net_rules = self.design_rules.get_rules_for_net(net_name) if self.design_rules else None
            self._register_routed_path(final_all_cells, net_name, rules=net_rules)

        # Restore original occupancy
        for gx, gy, l, v in original_occupancy:
            self.occupancy[gx, gy, l] = v

        res = RoutePath(
            net=net_name,
            cells=final_all_cells,
            length=len(final_all_cells) * self.cell_size,
            via_count=final_total_vias,
            success=True,
            difficulty=final_total_difficulty,
            cell_difficulties=final_cell_difficulties,
            trace_width=trace_width,
            explicit_vias=explicit_vias,
        )
        self.routed_paths[net_name] = res
        return res

    def route_net_hierarchical(
        self,
        net_name: str,
        pin_positions: list[tuple[float, float]],
        assignment: "LayerAssignment",
        **kwargs,
    ) -> RoutePath:
        """
        2-pass hierarchical routing for clearance-constrained nets.

        Fixes A* visit explosion caused by aggressive clearance masks.
        Routes on relaxed grid first, then uses result as guide.

        Issue: temper-edni
        """
        from temper_placer.routing.hierarchical import route_net_hierarchical

        return route_net_hierarchical(self, net_name, pin_positions, assignment, **kwargs)

    def find_bus_path_rrr(
        self,
        start_cells: list[tuple[int, int]],
        end_cells: list[tuple[int, int]],
        layer: int = 0,
        bus_constraint: "BusCohortConstraint | None" = None,
        cost_map: Array | None = None,
        p_scale: float = 1.0,
        clearance_mm: float | None = None,
    ) -> list[list[GridCell]] | None:
        """Finds parallel paths for a bus cohort using multi-path A*.

        This implementation uses a 'primary path' approach where the first net
        in the bus is routed, and other nets follow as parallel offsets.
        The expansion logic ensures that the entire cohort can fit at each step.
        """
        if not bus_constraint:
            return None

        t_start = time.perf_counter()

        num_nets = len(bus_constraint.nets)

        # Calculate relative offsets from the primary start pin
        start_x0, start_y0 = start_cells[0]
        offsets = []
        for i in range(num_nets):
            sx, sy = start_cells[i]
            offsets.append((sx - start_x0, sy - start_y0))

        # Priority queue: (f, g, primary_x, primary_y, layer, path_nodes)
        pq = []

        start_x, start_y = start_cells[0]
        end_x, end_y = end_cells[0]

        start_cell = GridCell(start_x, start_y, layer)
        end_cell = GridCell(end_x, end_y, layer)

        h = self._heuristic(start_cell, end_cell)
        # We don't track orientation anymore, just rigid offsets
        heapq.heappush(pq, (h, 0.0, start_x, start_y, layer, [start_cell]))

        visited = {}  # (x, y, layer) -> min_g

        print(f"DEBUG_BUS: Routing bus {bus_constraint.name} with {num_nets} nets")
        print(f"DEBUG_BUS: Primary Start: ({start_x}, {start_y}), End: ({end_x}, {end_y})")
        print(f"DEBUG_BUS: Offsets: {offsets}")

        while pq:
            f, g, cx, cy, cl, path = heapq.heappop(pq)

            curr_cell = path[-1]
            if curr_cell.x == end_x and curr_cell.y == end_y:
                duration_ms = (time.perf_counter() - t_start) * 1000.0
                self.stats.profile.astar_total_ms += duration_ms
                self.stats.profile.python_time_ms += duration_ms
                self.stats.profile.python_calls += 1

                print(f"DEBUG_BUS: Success! Path length: {len(path)} (Time: {duration_ms:.1f}ms)")
                all_paths = [[] for _ in range(num_nets)]
                for c in path:
                    for i in range(num_nets):
                        dx, dy = offsets[i]
                        all_paths[i].append(GridCell(c.x + dx, c.y + dy, c.layer))
                return all_paths

            state = (cx, cy, cl)
            if state in visited and visited[state] <= g:
                continue
            visited[state] = g

            # Expansion
            for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
                nx, ny = cx + dx, cy + dy

                if not (0 <= nx < self.grid_size[0] and 0 <= ny < self.grid_size[1]):
                    continue

                valid_step = True
                step_cost = 1.0

                for i in range(num_nets):
                    ox, oy = offsets[i]
                    tx, ty = nx + ox, ny + oy

                    if not (0 <= tx < self.grid_size[0] and 0 <= ty < self.grid_size[1]):
                        valid_step = False
                        break

                    if int(self.occupancy[tx, ty, cl]) != 0:
                        valid_step = False
                        break

                    step_cost += self.present_congestion[tx, ty, cl] * p_scale

                if valid_step:
                    new_g = g + step_cost
                    new_cell = GridCell(nx, ny, cl)
                    new_h = self._heuristic(new_cell, end_cell)
                    new_path = path + [new_cell]
                    heapq.heappush(pq, (new_g + new_h, new_g, nx, ny, cl, new_path))

        return None

    def find_path_rrr(
        self,
        start: tuple[int, int],
        end: tuple[int, int],
        layer: int = 0,
        allow_layer_change: bool = False,
        allowed_layers: list[int] | None = None,
        cost_map: Array | None = None,
        p_scale: float = 1.0,
        end_layer: int | None = None,
        clearance_mm: float | None = None,
        clearance_mask: Array | None = None,
        custom_heuristic: "Callable | None" = None,
        guide_map: np.ndarray | None = None,
        guide_bias: float = 0.0,
    ) -> list[GridCell] | None:
        """Find path using A* with RRR cost function.

        Uses Numba-accelerated implementation if available, otherwise falls back to Python.
        """
        # DEBUG prints removed for performance - uncomment for debugging
        # print(f"DEBUG_ASTAR: find_path_rrr called: start={start} end={end} layer={layer} end_layer={end_layer} allow_change={allow_layer_change}")

        # Prepare cached arrays for fast lookup
        self._prepare_cost_arrays()

        start_cell = GridCell(start[0], start[1], layer)

        # Determine target layer: either explicit end_layer or same as start layer
        target_layer = end_layer if end_layer is not None else layer
        end_cell = GridCell(end[0], end[1], target_layer)

        # Basic validity checks
        is_start_hard_blocked = int(self.occupancy[start[0], start[1], layer]) == -1
        is_end_hard_blocked = int(self.occupancy[end[0], end[1], target_layer]) == -1

        if is_start_hard_blocked:
            # print(f"DEBUG_ASTAR: Start blocked at {start} on layer {layer}")
            return None

        # If end is blocked on target layer, try to find an accessible layer
        if is_end_hard_blocked:
            # print(f"DEBUG_ASTAR: End blocked at {end} on target layer {target_layer}")
            found = False
            for l in range(self.num_layers):
                if int(self.occupancy[end[0], end[1], l]) != -1:
                    target_layer = l
                    end_cell = GridCell(end[0], end[1], l)
                    found = True
                    # print(f"DEBUG_ASTAR: Using alternative end layer {l} for {end}")
                    break
            if not found:
                # print(f"DEBUG_ASTAR: End blocked on all layers at {end}")
                return None

        # Compute clearance mask if needed
        req_clearance = clearance_mm if clearance_mm is not None else self.min_clearance
        if clearance_mask is None and req_clearance > 0 and HAS_NUMBA:
            radius = int(math.ceil(req_clearance / self.cell_size))
            if radius > 0:
                if self.soft_blocking:
                    obstacles = (self._occupancy_np == -1).astype(np.int32)
                else:
                    obstacles = (self._occupancy_np != 0).astype(np.int32)

                clearance_mask = dilate_grid_numba(obstacles, radius)

                for gx, gy in [(start[0], start[1]), (end[0], end[1])]:
                    x_min, x_max = max(0, gx - radius), min(self.grid_size[0], gx + radius + 1)
                    y_min, y_max = max(0, gy - radius), min(self.grid_size[1], gy + radius + 1)
                    clearance_mask[x_min:x_max, y_min:y_max, :] = 0

        # Try Numba implementation first
        # Now supports clearance_mask and guide_map!
        use_numba = HAS_NUMBA
        if custom_heuristic is not None:
            use_numba = False  # Custom heuristics only work in Python A*

        # print(f"DEBUG_ASTAR: use_numba={use_numba}, has_custom_heuristic={custom_heuristic is not None}")

        if use_numba:
            try:
                t_numba = time.perf_counter()
                self.stats.profile.numba_calls += 1

                # Use pre-converted arrays directly (already correct dtype from _prepare_cost_arrays)
                occ = self._occupancy_np
                hist = self._history_np
                cong = self._congestion_np

                cmap = None
                if cost_map is not None:
                    cmap = np.ascontiguousarray(cost_map, dtype=np.float32)

                cspace = self._soft_c_space_np  # Already correct dtype or None

                if clearance_mask is not None:
                    clearance_mask = np.ascontiguousarray(clearance_mask)

                # Use Adaptive Numba router (supports dist_map, clearance_mask, and guide_map)
                dist_map = self._compute_distance_map(end_cell, _layer=target_layer)

                # Convert allowed_layers to boolean mask for Numba
                allowed_mask = None
                if allowed_layers is not None:
                    allowed_mask = np.zeros(self.num_layers, dtype=np.bool_)
                    for l in allowed_layers:
                        if 0 <= l < self.num_layers:
                            allowed_mask[l] = True

                # Determine primary layer for penalty
                primary_idx = -1
                if hasattr(self, "_current_assignment") and self._current_assignment:
                    primary_idx = self._current_assignment.primary_layer.value - 1

                path_coords = find_path_astar_numba_adaptive(
                    start[0],
                    start[1],
                    layer,
                    end[0],
                    end[1],
                    target_layer,
                    self.grid_size[0],
                    self.grid_size[1],
                    self.num_layers,
                    occ,
                    hist,
                    cong,
                    float(self.via_cost),
                    float(p_scale),
                    dist_map,
                    cmap,
                    clearance_mask,
                    self.soft_blocking,
                    cspace,
                    None,  # tap_mask
                    guide_map,
                    float(guide_bias),
                    class_grid=self.class_grid,
                    current_class_id=0,  # Not available in this context yet
                    min_clearance=self.min_clearance,
                    cell_size=self.cell_size,
                    allowed_layers_mask=allowed_mask,
                    primary_layer_idx=primary_idx,
                    layer_penalty=5.0,
                )

                if path_coords:
                    dt = (time.perf_counter() - t_numba) * 1000.0
                    self.stats.profile.numba_time_ms += dt
                    self.stats.profile.astar_total_ms += dt
                    return [GridCell(int(x), int(y), int(l)) for x, y, l in path_coords]
                elif not path_coords:
                    return None
            except Exception as e:
                with open("numba_debug.log", "a") as f:
                    f.write(f"Numba routing failed: {e}\n")
                    import traceback

                    traceback.print_exc(file=f)

        # Python Fallback (Original Implementation)
        t_python = time.perf_counter()
        self.stats.profile.python_calls += 1
        try:
            # Debug clearance mask at start and end
            if clearance_mask is not None:
                start_blocked_by_mask = clearance_mask[start[0], start[1], layer] != 0
                end_blocked_by_mask = clearance_mask[end[0], end[1], target_layer] != 0
                print(
                    f"DEBUG_ASTAR: Clearance mask: start_blocked={start_blocked_by_mask}, end_blocked={end_blocked_by_mask}"
                )

            print(f"DEBUG_ASTAR: Searching for path from {start_cell} to {end_cell}")

            open_set: list[tuple[float, int, GridCell, float]] = [(0.0, 0, start_cell, 0.0)]
            counter = 0
            came_from, g_score, visited = {}, {start_cell: 0.0}, set()
            visit_count = 0
            max_visits = 100000  # Safety limit

            while open_set and visit_count < max_visits:
                _, _, current, current_g = heapq.heappop(open_set)
                visit_count += 1

                if current in visited:
                    continue
                visited.add(current)

                # DEBUG: Check if we're at the goal
                if (
                    current.x == end_cell.x
                    and current.y == end_cell.y
                    and current.layer == end_cell.layer
                ):
                    if current != end_cell:
                        print(
                            f"DEBUG_ASTAR: EQUALITY BUG! current={current} matches coords but != end_cell={end_cell}"
                        )
                    print(f"DEBUG_ASTAR: Reached goal at {current}, visits={visit_count}")

                if current == end_cell:
                    dt = (time.perf_counter() - t_python) * 1000.0
                    self.stats.profile.python_time_ms += dt
                    self.stats.profile.astar_total_ms += dt
                    print(f"DEBUG_ASTAR: Path found after visiting {visit_count} cells")
                    path = [current]
                    while current in came_from:
                        current = came_from[current]
                        path.append(current)
                    path.reverse()
                    return path
                for neighbor in self._get_neighbors(current, allow_layer_change, allowed_layers):
                    if neighbor in visited:
                        continue

                    # Clearance check for Python fallback
                    if clearance_mask is not None:
                        if clearance_mask[neighbor.x, neighbor.y, neighbor.layer] != 0:
                            continue

                    move_cost = self._get_neighbor_cost(
                        current, neighbor, cost_map, p_scale=p_scale
                    )
                    tentative_g = current_g + move_cost
                    if neighbor not in g_score or tentative_g < g_score[neighbor]:
                        came_from[neighbor], g_score[neighbor] = current, tentative_g
                        counter += 1
                        heapq.heappush(
                            open_set,
                            (
                                tentative_g
                                + (
                                    custom_heuristic(neighbor, end_cell)
                                    if custom_heuristic
                                    else self._heuristic(neighbor, end_cell)
                                ),
                                counter,
                                neighbor,
                                tentative_g,
                            ),
                        )

            dt = (time.perf_counter() - t_python) * 1000.0
            self.stats.profile.python_time_ms += dt
            self.stats.profile.astar_total_ms += dt
            if visit_count >= max_visits:
                print(f"DEBUG_ASTAR: Hit visit limit ({max_visits}) without finding path")
            else:
                print(
                    f"DEBUG_ASTAR: Exhausted open_set after {visit_count} visits without finding path"
                )
            return None
        finally:
            self._clear_cost_arrays()

    def route_all_nets(
        self,
        netlist: Netlist,
        positions: Array,
        net_order: list[str],
        assignments: dict[str, "LayerAssignment"],
    ) -> dict[str, RoutePath]:
        return self.rrr_route_all_nets(netlist, positions, net_order, assignments, max_iterations=1)

    def get_conflict_locations(self) -> list[dict]:
        """Return coordinates and nets for all conflicted cells."""
        conflicts = []
        for (x, y, layer), nets in self.net_occupancy.items():
            if len(nets) > 1:
                conflicts.append(
                    {
                        "x": int(x),
                        "y": int(y),
                        "layer": int(layer),
                        "nets": sorted(nets),
                        "world_x": x * self.cell_size + self.origin[0],
                        "world_y": y * self.cell_size + self.origin[1],
                    }
                )
        return conflicts

    def _run_post_processing(self, netlist: "Netlist | None" = None, positions: "Array | None" = None) -> None:
        """Run post-processing optimization passes on routed geometry.

        Executes via optimization, trace nudging, and trace ballooning
        using the unified PostProcessingPipeline to eliminate DRC violations.
        """
        from temper_placer.routing.post_processing.pipeline import PostProcessConfig, PostProcessingPipeline
        from temper_placer.routing.constraints.drc_oracle import DRCOracle

        logger.info("Starting post-processing pipeline")

        # 1. Initialize Oracle if missing
        if not self.drc_oracle:
            if not self.clearance_matrix:
                logger.warning("No clearance matrix or oracle available, skipping post-processing")
                return
            self.drc_oracle = DRCOracle(rules=self.clearance_matrix)

        # 2. Build physical geometry from grid paths and board pads
        if netlist is not None and positions is not None:
            self.drc_oracle.geometry = self._to_pcb_geometry(netlist, positions)
        
        geometry = self.drc_oracle.geometry

        if not geometry.tracks and not geometry.vias:
            logger.info("No geometry to optimize")
            return

        logger.info(f"Initial geometry: {len(geometry.tracks)} tracks, {len(geometry.vias)} vias")

        # 3. Initialize and run pipeline
        config = PostProcessConfig() # Default config
        pipeline = PostProcessingPipeline(config, self.drc_oracle)
        
        try:
            result = pipeline.process(self.routed_paths, geometry)
            self.optimized_geometry = result.geometry
            self.post_processing_metrics = {
                stage: {
                    "violations_fixed": metrics.violations_fixed,
                    "time_ms": metrics.execution_time_ms
                }
                for stage, metrics in result.metrics.items()
            }
            self.post_processing_metrics["total_violations_fixed"] = result.total_violations_fixed
            
            logger.info(f"Post-processing complete. Fixed {result.total_violations_fixed} violations.")
            if result.total_violations_fixed > 0:
                for stage, metrics in result.metrics.items():
                    if metrics.violations_fixed > 0:
                        logger.info(f"  - {stage}: Fixed {metrics.violations_fixed} violations in {metrics.execution_time_ms:.1f}ms")
            
        except Exception as e:
            logger.error(f"Post-processing pipeline failed: {e}")
            import traceback
            logger.error(traceback.format_exc())

    def _to_pcb_geometry(self, netlist: "Netlist", positions: "Array") -> "PCBGeometry":
        """Convert grid-based RoutePath objects and board pads to physical PCBGeometry.
        
        This enables continuous-space optimization like nudging and via consolidation.
        """
        from temper_placer.routing.constraints.spatial_index import PCBGeometry, Pad, Track, Via
        from temper_placer.routing.constraints.geometry import Point
        from temper_placer.io.kicad_exporter import path_to_segments, path_to_vias
        import math

        geometry = PCBGeometry()

        # 1. Add pads from netlist and positions
        # This is critical for the nudger to avoid colliding with pads
        comp_by_ref = {c.ref: (i, c) for i, c in enumerate(netlist.components)}
        for comp in netlist.components:
            idx = comp_by_ref[comp.ref][0]
            pos = positions[idx]
            rot = math.radians((comp.initial_rotation or 0) * 90)
            side = comp.initial_side or 0

            for pin in comp.pins:
                abs_pos = pin.absolute_position(tuple(pos), rot, side=side)
                # Map layer string/name to index
                l_idx = 0
                if pin.layer == "B.Cu":
                    l_idx = 1
                elif pin.layer == "all":
                    l_idx = 0 # Thru-hole treated as top for now, or check all

                geometry.add_pad(Pad(
                    center=Point(abs_pos[0], abs_pos[1]),
                    shape=pin.shape,
                    size=(pin.width, pin.height),
                    net=pin.net or "",
                    layer=l_idx,
                    id=f"{comp.ref}.{pin.name}"
                ))

        # 2. Convert each routed path to tracks and vias
        for net_name, path in self.routed_paths.items():
            if not path.success or not path.cells:
                continue

            # Convert to tracks
            segments = path_to_segments(path, self.origin, self.cell_size, path.trace_width)
            for seg in segments:
                # Map KiCad layer name back to index
                l_idx = 0
                if seg.layer == "B.Cu":
                    l_idx = 1
                
                geometry.add_track(Track(
                    start=Point(seg.start[0], seg.start[1]),
                    end=Point(seg.end[0], seg.end[1]),
                    width=seg.width,
                    net=seg.net,
                    layer=l_idx
                ))

            # Convert to vias
            vias = path_to_vias(path, self.origin, self.cell_size, path.via_diameter, path.via_drill)
            for v in vias:
                geometry.add_via(Via(
                    center=Point(v.position[0], v.position[1]),
                    diameter=v.size,
                    drill=v.drill,
                    net=v.net
                ))

        geometry.rebuild_index()
        return geometry


def compute_completion_rate(results: dict[str, RoutePath]) -> float:
    if not results:
        return 1.0
    return sum(1 for r in results.values() if r.success) / len(results)


def compute_net_metrics(net_name: str, pin_positions: list[tuple[float, float]]) -> NetMetrics:
    if len(pin_positions) < 2:
        return NetMetrics(
            net_name,
            len(pin_positions),
            0.0,
            0.0,
            _is_power_net(net_name),
            _is_ground_net(net_name),
        )
    xs, ys = [p[0] for p in pin_positions], [p[1] for p in pin_positions]
    w, h = max(xs) - min(xs), max(ys) - min(ys)
    return NetMetrics(
        net_name,
        len(pin_positions),
        w * h,
        w + h,
        _is_power_net(net_name),
        _is_ground_net(net_name),
    )


def _is_power_net(n: str) -> bool:
    return any(x in n.upper() for x in ["VCC", "VDD", "3V3", "5V", "12V", "VBUS", "VBAT", "V+"])


def _is_ground_net(n: str) -> bool:
    return any(x in n.upper() for x in ["GND", "VSS", "AGND", "DGND", "PGND", "V-"])


def order_nets_for_routing(
    net_names: list[str],
    net_pin_positions: dict[str, list[tuple[float, float]]],
    strategy: str = "shortest_first",
) -> list[str]:
    if strategy == "arbitrary":
        return net_names
    mlist = [compute_net_metrics(n, net_pin_positions.get(n, [])) for n in net_names]
    pairs = list(zip(net_names, mlist))
    if strategy == "shortest_first":
        pairs.sort(key=lambda x: x[1].estimated_wirelength)
    elif strategy == "smallest_bbox":
        pairs.sort(key=lambda x: x[1].bounding_box_area)
    elif strategy == "power_first":
        pwr = [x for x in pairs if x[1].is_power or x[1].is_ground]
        sig = [x for x in pairs if not (x[1].is_power or x[1].is_ground)]
        sig.sort(key=lambda x: x[1].estimated_wirelength)
        pairs = pwr + sig
    return [n for n, _ in pairs]
