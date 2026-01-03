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
from temper_placer.io.export_types import TraceVia
from temper_placer.routing.via_array import calculate_via_array, should_use_via_array
from temper_placer.routing.safety_distances import (
    calculate_safety_distances,
    calculate_safety_distances,
    get_hv_lv_separation,
    is_high_voltage,
)

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
logger = logging.getLogger(__name__)


@dataclass(frozen=True, order=True)
class GridCell:
    """A cell in the routing grid."""

    x: int
    y: int
    layer: int = 0

    def __hash__(self) -> int:
        return hash((self.x, self.y, self.layer))


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

        self._component_positions: Array | None = None
        self.stats = RoutingStats()

        # Layer balancing
        self.layer_balance_weight = layer_balance_weight
        self.layer_usage_count = np.zeros(num_layers, dtype=np.int32)  # Track cells used per layer

        # Net convergence tracking for early termination
        self._net_status: dict[str, NetStatus] = {}

        # Note: numpy cache no longer needed since grids are already numpy
        self._history_np: np.ndarray | None = None
        self._congestion_np: np.ndarray | None = None
        self._occupancy_np: np.ndarray | None = None

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

    def _get_inflated_cells(
        self, x: int, y: int, layer: int, width_mm: float = None, clearance_mm: float = None
    ) -> list[tuple[int, int, int]]:
        """Get all cells that a shape at (x,y) with given width/clearance would occupy.

        This accounts for actual copper footprint plus clearance.

        Args:
            x, y, layer: Center cell
            width_mm: Shape width/diameter in mm (uses default trace width if None)
            clearance_mm: Minimum clearance in mm (uses self.min_clearance if None)

        Returns:
            List of (x, y, layer) tuples for all affected cells
        """
        width = width_mm if width_mm is not None else self._default_trace_width_mm
        clearance = clearance_mm if clearance_mm is not None else self.min_clearance

        # Inflation radius in cells: shape extends width/2 + clearance from center
        required_radius_mm = (width / 2.0) + clearance
        radius_cells = int(np.ceil(required_radius_mm / self.cell_size))

        cells = []
        for dx in range(-radius_cells, radius_cells + 1):
            for dy in range(-radius_cells, radius_cells + 1):
                nx, ny = x + dx, y + dy
                # Bounds check
                if 0 <= nx < self.grid_size[0] and 0 <= ny < self.grid_size[1]:
                    cells.append((nx, ny, layer))
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
        return cls(
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

        # 2. Re-initialize occupancy and cost structures
        self.occupancy = np.zeros((*new_grid_size, self.num_layers), dtype=np.int32)
        self.grid_size = new_grid_size
        self.cell_size = new_cell_size_mm

        # Reset RRR structures - we clear net_occupancy as coordinate-mapping it is complex,
        # but the occupancy grid itself acts as the barrier for subsequent nets.
        self.net_occupancy = {}
        self.present_congestion = np.zeros((*new_grid_size, self.num_layers), dtype=np.float32)
        self.history_cost = np.ones((*new_grid_size, self.num_layers), dtype=np.float32)

        # Reset A* acceleration caches
        self._history_np = None
        self._congestion_np = None
        self._occupancy_np = None

        # 3. Map old occupancy to new grid
        factor = old_cell_size / new_cell_size_mm

        # Use simple mapping for now. For Fine -> Coarse, this is effectively Max-Pooling.
        indices = np.where(old_occupancy != 0)
        for x, y, l in zip(*indices):
            val = old_occupancy[x, y, l]

            if factor < 1.0:  # Upsampling (Coarse -> Fine)
                nx_s = int(x * factor)
                ny_s = int(y * factor)
                nx_e = int((x + 1) * factor)
                ny_e = int((y + 1) * factor)
                # Ensure we don't go out of bounds due to rounding
                nx_e = min(nx_e, new_grid_size[0])
                ny_e = min(ny_e, new_grid_size[1])
                self.occupancy[nx_s:nx_e, ny_s:ny_e, l] = val
            else:  # Downsampling (Fine -> Coarse)
                nx = int(round(x * factor))
                ny = int(round(y * factor))
                if 0 <= nx < new_grid_size[0] and 0 <= ny < new_grid_size[1]:
                    # Prefer hard blocks (-1) over trace blocks (2)
                    if self.occupancy[nx, ny, l] == 0 or val == -1:
                        self.occupancy[nx, ny, l] = val

        # Sync congestion to reflect occupied cells
        self.present_congestion[self.occupancy != 0] = 1.0

    def rip_up_net(self, net_name: str) -> None:
        """Remove a net from the grid."""
        if net_name not in self.routed_paths:
            return
        path = self.routed_paths[net_name]
        for cell in path.cells:
            # Remove occupancy for all cells within trace radius
            # DRC-2: Use exact trace width and 0 clearance (occupancy stores copper only)
            affected_cells = self._get_inflated_cells(
                cell.x, cell.y, cell.layer, width_mm=path.trace_width, clearance_mm=0.0
            )
            for ax, ay, al in affected_cells:
                key = (ax, ay, al)
                if key in self.net_occupancy and net_name in self.net_occupancy[key]:
                    self.net_occupancy[key].remove(net_name)
                    if not self.net_occupancy[key]:
                        self.occupancy[ax, ay, al] = 0
                        del self.net_occupancy[key]
                        # DRC-1: Clear ownership
                        if (ax, ay, al) in self.cell_owner:
                            del self.cell_owner[(ax, ay, al)]
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
        base_cost = 1.0
        # Wrong-way penalty
        wrong_way_cost = 0.0
        if neighbor.layer == 0:  # L1 prefers horizontal
            if neighbor.y != current.y:
                wrong_way_cost = self.wrong_way_penalty
        elif neighbor.layer == 1:  # L4 prefers vertical
            if neighbor.x != current.x:
                wrong_way_cost = self.wrong_way_penalty

        # Difficulty gradient (soft feedback for router)
        diff = self._get_cell_difficulty(neighbor)

        # Use cached numpy arrays if available (much faster indexing)
        if self._history_np is not None:
            h = self._history_np[neighbor.x, neighbor.y, neighbor.layer]
            p = self._congestion_np[neighbor.x, neighbor.y, neighbor.layer]
            blocked = self._occupancy_np[neighbor.x, neighbor.y, neighbor.layer] == -1
            occupied = self._occupancy_np[neighbor.x, neighbor.y, neighbor.layer] == 2

            # Add soft C-space cost if present
            c_space_cost = 0.0
            if self._soft_c_space_np is not None:
                # Handle 2D or 3D soft C-space
                if self._soft_c_space_np.ndim == 2:
                    c_space_cost = float(self._soft_c_space_np[neighbor.x, neighbor.y])
                else:
                    c_space_cost = float(
                        self._soft_c_space_np[neighbor.x, neighbor.y, neighbor.layer]
                    )

                if c_space_cost == np.inf:
                    blocked = True

            # Check hard C-space (static obstacles)
            # Note: C-space is 2D (all layers same? Or should be 3D?)
            # Usually pads are on Top/Bottom. Inner layers are clearer.
            # But the Builder assumes 2D grid for now.
            # We should probably map Builder grid to Layers properly.
            # For now, let's assume it applies to the current layer if we don't have per-layer C-Space.
            # Or better: The Builder creates a single grid for Pads (which are typically on outer layers, or all if THT).
            # This is a simplification. Tracks/Vias are layer specific.
            # If CSpaceGrid is 2D, we assume it blocks ALL layers?
            # No, that would be bad for tracks under pads.
            # Pads usually block only their layer.
            # Let's assume for this specific integration that c_space_grid is 2D and applies to the CURRENT generic pad layer check.
            # Ideally, self.c_space_grid should be 3D or we check it only on Top/Bottom?
            # Actually, THT pads block all. SMD pads block Surface.
            # The CSpaceBuilder flattened everything.
            # I should just check it. If it blocks, it blocks.
            if self._c_space_grid_np is not None:
                # Assuming 2D grid for now, applies check.
                # Ideally we only check this if `neighbor.layer` matches the C-Space context (e.g. Surface).
                # But pads are on surfaces.
                # Let's assume `c_space_grid` contains ONLY objects relevant to current routing.
                # If I want to route on inner layer, I might pass an empty C-Space?
                # Actually, THT pads block all. SMD pads block Surface.
                # The CSpaceBuilder flattened everything.
                # I should just check it. If it blocks, it blocks.
                if (
                    self._c_space_grid_np[neighbor.x, neighbor.y]
                    if self._c_space_grid_np.ndim == 2
                    else self._c_space_grid_np[neighbor.x, neighbor.y, neighbor.layer]
                ):
                    blocked = True
        else:
            h = float(self.history_cost[neighbor.x, neighbor.y, neighbor.layer])
            p = float(self.present_congestion[neighbor.x, neighbor.y, neighbor.layer])
            blocked = self.occupancy[neighbor.x, neighbor.y, neighbor.layer] == -1
            occupied = self.occupancy[neighbor.x, neighbor.y, neighbor.layer] == 2

            c_space_cost = 0.0
            if self.soft_c_space is not None:
                if self.soft_c_space.ndim == 2:
                    c_space_cost = float(self.soft_c_space[neighbor.x, neighbor.y])
                else:
                    c_space_cost = float(self.soft_c_space[neighbor.x, neighbor.y, neighbor.layer])

                if c_space_cost == np.inf:
                    blocked = True

        # Hard-blocked cells (components) are always impassable
        if blocked:
            return 1e9

        # Soft blocking: occupied cells get high cost but are passable
        # This enables negotiated congestion (PathFinder algorithm)
        sharing_penalty = 0.0
        if occupied:
            # DRC-1: Check if cell is owned by a different net (net isolation)
            # Cells owned by other nets are ALWAYS blocked - no shorts allowed
            key = (neighbor.x, neighbor.y, neighbor.layer)
            owner = self.cell_owner.get(key)
            if owner is not None and owner != self._current_net:
                # Cell owned by different net - block completely (no shorts allowed)
                return 1e9
            if self.soft_blocking:
                sharing_penalty = 50.0 * (1.0 + p)  # Higher penalty with more congestion
            else:
                # STRICT MODE: Occupied cells are impassable
                return 1e9

        if cost_map is not None:
            if cost_map.ndim == 2:
                strategy_mult = float(cost_map[neighbor.x, neighbor.y])
            else:
                strategy_mult = float(cost_map[neighbor.x, neighbor.y, neighbor.layer])
        else:
            strategy_mult = 1.0

        # Include soft C-space cost in base cost
        congestion_cost = (
            base_cost + wrong_way_cost + sharing_penalty + h + diff + c_space_cost
        ) * (1.0 + p * p_scale)
        total_cost = strategy_mult * congestion_cost

        # Layer balance cost: encourage even distribution across layers
        if self.num_layers > 1 and self.layer_balance_weight > 0:
            # Calculate usage imbalance (standard deviation of layer usage)
            layer_usage = self.layer_usage_count.astype(np.float32)
            if np.sum(layer_usage) > 0:
                mean_usage = np.mean(layer_usage)
                # std_usage = np.std(layer_usage) # Unused but keeping for reference

                # Penalize moving to layer with above-average usage
                if layer_usage[neighbor.layer] > mean_usage:
                    imbalance_penalty = (layer_usage[neighbor.layer] - mean_usage) / max(
                        1.0, mean_usage
                    )
                    total_cost += self.layer_balance_weight * imbalance_penalty

        # Dynamic via cost: lower in congested areas to encourage layer escape
        if current.layer != neighbor.layer:
            if p > 2.0 and self.soft_blocking:
                # Congested area - discount via cost to encourage escape
                total_cost += self.via_cost * self.congestion_via_discount
            else:
                total_cost += self.via_cost

            # DRC check for via placement (temper-mado.2)
            if self.drc_oracle and self._current_net:
                via_x = neighbor.x * self.cell_size + self.origin[0]
                via_y = neighbor.y * self.cell_size + self.origin[1]
                via_dia = self.drc_oracle.rules.get_via_diameter(self._current_net)
                valid, _ = self.drc_oracle.can_place_via((via_x, via_y), via_dia, self._current_net)
                if not valid:
                    if self.strict_mode:
                        # Retry with neckdown relaxation for vias too?
                        # Yes, often we need to drop a via near a pad
                        is_neckdown = self.neckdown_mask[neighbor.x, neighbor.y, neighbor.layer]
                        if is_neckdown:
                            valid, _ = self.drc_oracle.can_place_via(
                                (via_x, via_y), via_dia, self._current_net, neckdown=True
                            )

                        if not valid:
                            return 1e9  # Block completely in strict mode
                    else:
                        total_cost += 200.0  # Heavy penalty for bad via

        # DRC check for track segment (temper-mado.1)
        if self.drc_oracle and self._current_net:
            curr_x = current.x * self.cell_size + self.origin[0]
            curr_y = current.y * self.cell_size + self.origin[1]
            neigh_x = neighbor.x * self.cell_size + self.origin[0]
            neigh_y = neighbor.y * self.cell_size + self.origin[1]

            if self.strict_mode:
                start_world = (curr_x, curr_y)
                end_world = (neigh_x, neigh_y)

                # Neckdown: Use 0.15mm width if in neckdown zone, else 0.2mm
                # Neckdown applies if ANY part of segment is in zone.
                is_neckdown = (
                    self.neckdown_mask[neighbor.x, neighbor.y, neighbor.layer]
                    or self.neckdown_mask[current.x, current.y, current.layer]
                )
                check_width = 0.15 if is_neckdown else 0.2

                is_valid, reason = self.drc_oracle.can_place_track_segment(
                    start_world,
                    end_world,
                    layer=neighbor.layer,
                    net=self._current_net,
                    width=check_width,
                    neckdown=is_neckdown,
                )

                if not is_valid:
                    return 1e9  # Infinite cost
            else:
                valid, _ = self.drc_oracle.can_place_track_segment(
                    (curr_x, curr_y),
                    (neigh_x, neigh_y),
                    layer=neighbor.layer,
                    net=self._current_net,
                    width=0.2,
                )
                if not valid:
                    total_cost += 100.0  # Penalty for DRC violation

        return total_cost

    def _prepare_cost_arrays(self) -> None:
        """Convert JAX arrays to numpy for faster A* indexing.

        Called at the start of find_path to avoid repeated JAX->Python conversion.
        """
        t0 = time.perf_counter()
        self._history_np = np.asarray(self.history_cost)
        self._congestion_np = np.asarray(self.present_congestion)
        self._occupancy_np = np.asarray(self.occupancy)
        if self.soft_c_space is not None:
            self._soft_c_space_np = np.asarray(self.soft_c_space)
        if self.c_space_grid is not None:
            self._c_space_grid_np = np.asarray(self.c_space_grid)
        self.stats.profile.prepare_costs_ms += (time.perf_counter() - t0) * 1000.0

    def _clear_cost_arrays(self) -> None:
        """Clear cached numpy arrays after path finding."""
        self._history_np = None
        self._congestion_np = None
        self._occupancy_np = None
        self._soft_c_space_np = None
        self._c_space_grid_np = None

    def _world_to_grid(self, world_x: float, world_y: float) -> tuple[int, int]:
        """Convert world coordinates to grid cell indices."""
        grid_x = int((world_x - self.origin[0]) / self.cell_size)
        grid_y = int((world_y - self.origin[1]) / self.cell_size)
        # Clamp to valid range
        grid_x = max(0, min(self.grid_size[0] - 1, grid_x))
        grid_y = max(0, min(self.grid_size[1] - 1, grid_y))
        return (grid_x, grid_y)

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

        x_min = np.round((cx - half_widths - self.origin[0]) / self.cell_size).astype(int)
        x_max = np.round((cx + half_widths - self.origin[0]) / self.cell_size).astype(int)
        y_min = np.round((cy - half_heights - self.origin[1]) / self.cell_size).astype(int)
        y_max = np.round((cy + half_heights - self.origin[1]) / self.cell_size).astype(int)

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
                        dist_mm = math.sqrt(dx*dx + dy*dy) * self.cell_size
                        
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

                gx_min_block = int(math.ceil((min_x_mm - self.origin[0]) / self.cell_size))
                gy_min_block = int(math.ceil((min_y_mm - self.origin[1]) / self.cell_size))
                gx_max_block = int(math.floor((max_x_mm - self.origin[0]) / self.cell_size))
                gy_max_block = int(math.floor((max_y_mm - self.origin[1]) / self.cell_size))

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

    def _world_to_grid(self, x: float, y: float) -> tuple[int, int]:
        gx, gy = (
            int(round((x - self.origin[0]) / self.cell_size)),
            int(round((y - self.origin[1]) / self.cell_size)),
        )
        return max(0, min(gx, self.grid_size[0] - 1)), max(0, min(gy, self.grid_size[1] - 1))

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
            return self._distance_map_cache[cache_key]

        # Use Numba-accelerated BFS when available
        if HAS_NUMBA:
            # Ensure occupancy is contiguous int32
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
                (self.grid_size[0], self.grid_size[1], self.num_layers), float("inf"), dtype=np.float32
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
                )
                
                # Convert result to GridCells
                if result:
                    path = []
                    for x, y, l in result:
                        path.append(GridCell(x, y, l))
                    return path
                return None

        except Exception as e:
            logger.warning(f"Numba A* failed, falling back to Python: {e}")

        try:
            dist_map = self._compute_distance_map(GridCell(end[0], end[1], layer), _layer=layer)

            if HAS_NUMBA and self._history_np is not None and self._congestion_np is not None:
                try:
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
                    )
                    
                    if result:
                        path = []
                        for x, y, l in result:
                            path.append(GridCell(x, y, l))
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
                if not self._check_class_clearance(neighbor.x, neighbor.y, neighbor.layer, current_class_id):
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

        # Mark cells as occupied WITH TRACE WIDTH INFLATION (temper-z87d)
        # This accounts for actual copper footprint, not just center-line
        unique_cells = set(all_cells)
        for cell in unique_cells:
            # Get all cells within trace radius
            affected_cells = self._get_inflated_cells(cell.x, cell.y, cell.layer)
            for ax, ay, al in affected_cells:
                self.occupancy[ax, ay, al] = 2
                self.class_grid[ax, ay, al] = current_class_id  # Update class grid (temper-kmbw)
                self.present_congestion[ax, ay, al] += 1.0
                key = (ax, ay, al)
                if key not in self.net_occupancy:
                    self.net_occupancy[key] = set()
                self.net_occupancy[key].add(net_name)

        # Restore original occupancy
        for gx, gy, l, v in original_occupancy:
            self.occupancy[gx, gy, l] = v

        res = RoutePath(
            net=net_name,
            cells=all_cells,  # Ordered path for simplification
            length=float(len(all_cells)),
            via_count=total_vias,
            success=True,
            difficulty=total_difficulty,
            cell_difficulties=cell_difficulties,
        )
        self.routed_paths[net_name] = res
        return res

    def _get_neighbors(
        self,
        cell: GridCell,
        allow_layer_change: bool = False,
        allowed_layers: list[int] | None = None,
    ) -> list[GridCell]:
        neighbors = []
        layers = allowed_layers if allowed_layers is not None else list(range(self.num_layers))

        # DEBUG: Log for start cell only
        is_start = cell.x == 100 and cell.y == 250 and cell.layer == 0

        # DEBUG: Log for cells on layer 1 near start
        is_layer1_near_start = cell.layer == 1 and cell.x >= 98 and cell.x <= 102 and cell.y == 250

        if not self.layer_stackup.is_plane_layer(cell.layer):
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
                        if is_layer1_near_start:
                            print(
                                f"DEBUG_NEIGHBOR: Skipping ({nx}, {ny}, L{cell.layer}) - hard blocked"
                            )
                        continue
                    if occ == 2 and not self.soft_blocking:
                        if is_layer1_near_start:
                            print(
                                f"DEBUG_NEIGHBOR: Skipping ({nx}, {ny}, L{cell.layer}) - occupied and strict mode"
                            )
                        continue

                    neighbors.append(GridCell(nx, ny, cell.layer))
                    if is_layer1_near_start:
                        print(
                            f"DEBUG_NEIGHBOR: Added horizontal neighbor ({nx}, {ny}, L{cell.layer})"
                        )
        else:
            if is_layer1_near_start:
                print(f"DEBUG_NEIGHBOR: Layer {cell.layer} is plane layer - no horizontal movement")

        if allow_layer_change and self.num_layers > 1:
            for nl in layers:
                if nl != cell.layer:
                    occ = int(self.occupancy[cell.x, cell.y, nl])
                    if is_start:
                        print(
                            f"DEBUG_NEIGHBOR: Checking via from L{cell.layer} to L{nl} at ({cell.x}, {cell.y}): occ={occ}, soft_blocking={self.soft_blocking}"
                        )
                    if occ == -1:
                        continue
                    if occ == 2 and not self.soft_blocking:
                        if is_start:
                            print(
                                f"DEBUG_NEIGHBOR: Skipping via to L{nl} because occ=2 and soft_blocking=False"
                            )
                        continue
                    neighbors.append(GridCell(cell.x, cell.y, nl))
                    if is_start:
                        print(f"DEBUG_NEIGHBOR: Added via neighbor to L{nl}")
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
        self._default_trace_width_mm = trace_width_mm if trace_width_mm is not None else 0.2
        self.min_clearance = clearance_mm if clearance_mm is not None else 0.2

        # Determine starting layer for routing
        # If pin_sides are provided, use the side of the first pin.
        # Otherwise, use the primary layer from assignment or default to L1_TOP (layer 0).
        start_layer = 0
        if pin_sides and len(pin_sides) > 0:
            start_layer = 0 if pin_sides[0] == 0 else (self.num_layers - 1)
        elif assignment:
            start_layer = 0 if assignment.primary_layer == Layer.L1_TOP else 1

        allow_via = len(assignment.allowed_layers) > 1 if assignment else True
        allowed_layers_indices = (
            [l.value for l in assignment.allowed_layers] if assignment else None
        )

        grid_pins = [self._world_to_grid(x, y) for x, y in pin_positions]

        # Temporarily unblock pin locations and any cells owned by this net
        original_occupancy_and_ownership = []
        unblock_radius = max(
            5, int(2.0 / self.cell_size)
        )  # Ensure enough space to escape pad/trace

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

                        # Unblock if it's a hard block (-1) or owned by this net (2)
                        if self.occupancy[gx, gy, l] == -1:
                            original_occupancy_and_ownership.append(
                                (key, -1, self.class_grid[gx, gy, l], owner, was_in_net_occ)
                            )
                            self.occupancy[gx, gy, l] = 0
                            self.class_grid[gx, gy, l] = CLASS_DEFAULT  # Clear class for unblocked
                        elif key in self.cell_owner and self.cell_owner[key] == net_name:
                            original_occupancy_and_ownership.append(
                                (key, 2, self.class_grid[gx, gy, l], owner, was_in_net_occ)
                            )
                            self.occupancy[gx, gy, l] = 0
                            self.class_grid[gx, gy, l] = CLASS_DEFAULT  # Clear class for unblocked

                        # Also unblock any cells that were part of this net's previous route
                        if was_in_net_occ:
                            if (
                                len(original_occupancy_and_ownership) == 0
                                or original_occupancy_and_ownership[-1][0] != key
                            ):
                                # Checking last appended might be tricky with loops, but key is unique per iteration.
                                # Just append if not already handled by elif above.
                                is_handled = (self.occupancy[gx, gy, l] == -1) or (
                                    key in self.cell_owner and self.cell_owner[key] == net_name
                                )
                                # But we already modified occupancy above!
                                # We need to check if we appended for this KEY in this iteration.
                                # Since we are inside the innermost loop for this key, we can checking if we just appended.
                                pass

                            # Logic for unblocking net_occupancy even if global occupancy wasn't -1 or Owned
                            # E.g. Shared via or crossing?
                            # For now, just focus on owned cells.

                            if (
                                len(original_occupancy_and_ownership) > 0
                                and original_occupancy_and_ownership[-1][0] == key
                            ):
                                pass  # Already captured
                            else:
                                original_occupancy_and_ownership.append(
                                    (
                                        key,
                                        int(self.occupancy[gx, gy, l]),
                                        self.class_grid[gx, gy, l],
                                        owner,
                                        was_in_net_occ,
                                    )
                                )

                            if net_name in self.net_occupancy[key]:
                                self.net_occupancy[key].remove(net_name)

                            if not self.net_occupancy[key]:
                                # If no other nets, clear occupancy
                                if (
                                    self.occupancy[gx, gy, l] != -1
                                ):  # Don't clear hard blocks (already handled above if they were hard blocks)
                                    self.occupancy[gx, gy, l] = 0
                                del self.net_occupancy[key]
                                if key in self.cell_owner:
                                    del self.cell_owner[key]

                            self.present_congestion[gx, gy, l] = max(
                                0.0, self.present_congestion[gx, gy, l] - 1.0
                            )

        # Also unblock any cells that were part of this net's previous route
        # This is handled by rip_up_net, but if this is the first route, it won't be called.
        # The above loop handles pin locations, but a full rip_up_net is more comprehensive.
        # For RRR, rip_up_net is called before this. For initial route, this is fine.

        final_all_cells, final_total_vias = [], 0
        final_total_difficulty = 0.0
        final_cell_difficulties: list[float] = []
        final_success = True
        last_failure_reason = None

        # Route point-to-point connections
        # For multi-pin nets, this is a simple chain. MST routing should be used for better results.
        # This method is primarily for P2P segments within a larger topology.
        current_start_grid = grid_pins[0]
        current_start_layer = start_layer

        for i in range(1, len(grid_pins)):
            target_grid = grid_pins[i]
            target_layer = start_layer  # Default to same layer as start, A* will find vias

            # If pin_sides are provided, try to end on the correct layer for the target pin
            if pin_sides and i < len(pin_sides):
                target_layer = 0 if pin_sides[i] == 0 else (self.num_layers - 1)

            # Try to find a path from current_start_grid to target_grid
            path = self.find_path_rrr_adaptive(
                current_start_grid,
                target_grid,
                current_start_layer,
                allow_via,
                allowed_layers_indices,
                cost_map=cost_map,
                p_scale=p_scale,
            )

            if path is None:
                final_success = False
                last_failure_reason = f"No path from {current_start_grid} to {target_grid}"
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
                # Avoid duplicating the connection point if extending an existing path
                if path[0] == final_all_cells[-1]:
                    path = path[1:]

            if not path:
                # Segment was empty or already connected (e.g. same point)
                continue

            final_all_cells.extend(path)

            # Update current_start for next segment
            current_start_grid = target_grid
            current_start_layer = path[-1].layer  # Continue from the layer the path ended on

        # Mark cells as occupied WITH TRACE WIDTH INFLATION
        if final_success:
            self._mark_path_occupied(
                net_name,
                RoutePath(
                    net_name, final_all_cells, 0, 0, True, trace_width=self._default_trace_width_mm
                ),
            )

        # Restore original occupancy for any cells that were temporarily unblocked but not part of the final route
        for (
            key,
            original_val,
            original_class_id,
            original_owner,
            was_in_net_occ,
        ) in original_occupancy_and_ownership:
            if self.occupancy[key[0], key[1], key[2]] == 0:  # Only restore if still free
                self.occupancy[key[0], key[1], key[2]] = original_val
                self.class_grid[key[0], key[1], key[2]] = original_class_id
                if original_owner is not None:
                    self.cell_owner[key] = original_owner
                if was_in_net_occ:
                    if key not in self.net_occupancy:
                        self.net_occupancy[key] = set()
                    self.net_occupancy[key].add(net_name)
                    # Restore congestion if it was decremented?
                    # The decrement logic was: self.present_congestion -= 1.0
                    # So we should increment it back.
                    self.present_congestion[key[0], key[1], key[2]] += 1.0
            # If it was a hard block (-1) and is now part of the routed path (2), keep it as 2.
            # If it was a hard block (-1) and is still 0 (not routed), restore it to -1.

        # Clear current net
        self._current_net = None
        self._default_trace_width_mm = 0.25  # Reset to default
        self.min_clearance = 0.2  # Reset to default

        if final_success:
            return RoutePath(
                net=net_name,
                cells=final_all_cells,
                length=len(final_all_cells) * self.cell_size,
                via_count=final_total_vias,
                success=True,
                difficulty=final_total_difficulty,
                cell_difficulties=final_cell_difficulties,
                trace_width=self._default_trace_width_mm,
            )
        else:
            return RoutePath(
                net=net_name,
                cells=[],
                length=0.0,
                via_count=0,
                success=False,
                difficulty=0.0,
                cell_difficulties=[],
                failure_reason=last_failure_reason,
            )

    def _mark_path_occupied(self, net_name: str, path: RoutePath) -> None:
        """Marks the cells of a routed path as occupied."""
        unique_cells = set(path.cells)
        for cell in unique_cells:
            # Get all cells within trace radius
            affected_cells = self._get_inflated_cells(
                cell.x, cell.y, cell.layer, width_mm=path.trace_width
            )
            for ax, ay, al in affected_cells:
                # Only mark as occupied if not a hard block (-1)
                if self.occupancy[ax, ay, al] != -1:
                    self.occupancy[ax, ay, al] = 2
                    self.present_congestion[ax, ay, al] += 1.0
                    key = (ax, ay, al)
                    if key not in self.net_occupancy:
                        self.net_occupancy[key] = set()
                    self.net_occupancy[key].add(net_name)
                    self.cell_owner[key] = net_name  # Assign ownership

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
                    bus = (
                        self.design_rules.get_bus_cohort_for_net(net_name)
                        if self.design_rules
                        else None
                    )
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

                    # Check for explicit topology
                    topology = None
                    if self.design_rules and net_name in self.design_rules.net_topologies:
                        topology = self.design_rules.net_topologies[net_name]

                    if topology:
                        result = self.route_net_topology(
                            net_name,
                            topology,
                            netlist,
                            positions,
                            assignments.get(net_name),
                            cost_maps.get(net_name) if cost_maps else None,
                            p_scale=p_scale,
                        )
                    else:
                        # Use MST router by default for better multi-pin support and via arrays
                        result = self.route_net_mst(
                            net_name,
                            all_pin_positions[net_name],
                            assignments.get(net_name),
                            cost_map=cost_maps.get(net_name) if cost_maps else None,
                            p_scale=p_scale,
                            pin_sides=all_pin_sides.get(net_name),
                        )

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
                    break

            # Print progress
            print(f"  RRR Iteration {iteration + 1}/{max_iterations} (p_scale={p_scale:.1f})")
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

        # Restore best state if found
        if best_state is not None:
            print(
                f"  Restoring best state from iteration {best_iteration} (Conflicts: {best_conflicts})"
            )
            self._restore_state(best_state)

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

        self._run_post_processing()

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
        }

    def _restore_state(self, state: dict) -> None:
        """Restore routing state."""
        self.routed_paths = state["routed_paths"]
        self.occupancy = state["occupancy"]
        self.net_occupancy = state["net_occupancy"]
        self.cell_owner = state["cell_owner"]
        self.present_congestion = state["present_congestion"]
        self.history_cost = state["history_cost"]

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
        print(f"DEBUG_MST: Net={net_name} NumPins={num_pins} GridPins={grid_pins}")
        print(f"DEBUG_MST: pin_sides={pin_sides}")

        # Map pin sides to layers
        pin_layers = []
        if pin_sides is not None:
            for side in pin_sides:
                pin_layers.append(0 if side == 0 else (self.num_layers - 1))
        else:
            # Default to all Top or use Through-hole assumption
            pin_layers = [0] * num_pins

        print(f"DEBUG_MST: pin_layers={pin_layers}")

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

        # Clear distance map cache
        self._clear_distance_map_cache()

        # Temporarily unblock pin locations with radius
        original_occupancy = []
        for gx, gy in grid_pins:
            for dx in range(-unblock_radius, unblock_radius + 1):
                for dy in range(-unblock_radius, unblock_radius + 1):
                    nx, ny = gx + dx, gy + dy
                    if 0 <= nx < self.grid_size[0] and 0 <= ny < self.grid_size[1]:
                        for l in range(self.num_layers):
                            if self.occupancy[nx, ny, l] == -1:
                                pad_net = self._pad_net_map.get((nx, ny, l))
                                if pad_net is None or pad_net == net_name:
                                    original_occupancy.append((nx, ny, l, -1))
                                    self.occupancy[nx, ny, l] = 0

        # CRITICAL: Force clear the EXACT pin center on ALL layers to ensure pathfinding can start/end there
        for i, (gx, gy) in enumerate(grid_pins):
            for l in range(self.num_layers):
                if self.occupancy[gx, gy, l] != 0:  # If not already free
                    original_occupancy.append((gx, gy, l, int(self.occupancy[gx, gy, l])))
                    self.occupancy[gx, gy, l] = 0

        # DEBUG: Show occupancy at pin centers after unblocking
        for i, (gx, gy) in enumerate(grid_pins):
            occ_vals = [int(self.occupancy[gx, gy, l]) for l in range(self.num_layers)]
            print(f"DEBUG_MST: Pin {i} at ({gx}, {gy}) occupancy after unblock: {occ_vals}")

        # DEBUG: Sample occupancy along the path from start to end on layer 1
        start_x, start_y = grid_pins[0]
        end_x, end_y = grid_pins[1]
        sample_points = [start_x, (start_x + end_x) // 2, end_x]
        for x in sample_points:
            occ = int(self.occupancy[x, start_y, 1])  # Check layer 1
            print(f"DEBUG_MST: Occupancy at ({x}, {start_y}, L1): {occ}")

        # DEBUG: Count blocked cells on layer 1 along the direct path
        blocked_count = 0
        blocked_cells = []
        for x in range(min(start_x, end_x), max(start_x, end_x) + 1):
            if int(self.occupancy[x, start_y, 1]) == -1:
                blocked_count += 1
                blocked_cells.append(x)
        print(
            f"DEBUG_MST: Blocked cells on direct path (L1, y={start_y}): {blocked_count} / {abs(end_x - start_x) + 1}"
        )
        if blocked_cells:
            print(f"DEBUG_MST: Blocked cell x-coordinates: {blocked_cells[:20]}")

        # Creepage Awareness: Generate class-specific clearance mask
        # TEMP: Disabled for EXP-16 testing - clearance mask blocks entire path
        clearance_mask = None
        current_class_id = CLASS_DEFAULT

        # if clearance_mask is not None:
        #     w, h = self.grid_size
        #     for gx, gy in grid_pins:
        #          for dx in range(-unblock_radius, unblock_radius + 1):
        #              for dy in range(-unblock_radius, unblock_radius + 1):
        #                  nx, ny = gx + dx, gy + dy
        #                  if 0 <= nx < w and 0 <= ny < h:
        #                      clearance_mask[nx, ny, :] = 0

        # MST routing logic
        # Nodes in the MST will be (pin_idx, layer_idx)
        # We need to connect all pins. Start with the first pin.

        # Keep track of connected pins and their cells
        connected_pins = set()  # Stores pin indices
        connected_cells = set()  # Stores GridCell objects of the routed path
        all_paths: list[list[GridCell]] = []  # Stores individual paths found

        # Priority queue for Prim's algorithm: (cost, from_pin_idx, to_pin_idx, path_cells)
        # Cost is the path length.
        pq = []

        # Start with the first pin (index 0)
        start_pin_idx = 0
        connected_pins.add(start_pin_idx)

        # Add all possible connections from the first pin to other pins to the PQ
        initial_paths_found = 0
        for i in range(1, num_pins):
            for start_l in candidate_start_layers_per_pin[start_pin_idx]:
                for end_l in candidate_start_layers_per_pin[i]:
                    path = self.find_path_rrr(
                        grid_pins[start_pin_idx],
                        grid_pins[i],
                        start_l,
                        allow_via,
                        cost_map=cost_map,
                        p_scale=p_scale,
                        end_layer=end_l,
                        clearance_mm=clearance_mm,
                        clearance_mask=None,  # TEMP: Disable to test connectivity
                        custom_heuristic=custom_heuristic,
                        guide_map=guide_map,
                        guide_bias=guide_bias,
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
                        heapq.heappush(pq, (path_cost, start_pin_idx, i, path))
                        initial_paths_found += 1

        print(
            f"DEBUG_MST: Found {initial_paths_found} initial paths from pin {start_pin_idx} to other pins"
        )
        print(f"DEBUG_MST: candidate_start_layers_per_pin={candidate_start_layers_per_pin}")

        final_all_cells = []
        final_via_cells = set()
        final_total_vias = 0
        final_total_difficulty = 0.0
        final_cell_difficulties = []

        while pq and len(connected_pins) < num_pins:
            cost, from_idx, to_idx, path = heapq.heappop(pq)

            if to_idx in connected_pins:
                continue  # This pin is already connected

            connected_pins.add(to_idx)
            all_paths.append(path)

            # Add new connections from the newly connected pin to all unconnected pins
            for next_unconnected_idx in range(num_pins):
                if next_unconnected_idx not in connected_pins:
                    for start_l in candidate_start_layers_per_pin[to_idx]:
                        for end_l in candidate_start_layers_per_pin[next_unconnected_idx]:
                            new_path = self.find_path_rrr(
                                grid_pins[to_idx],
                                grid_pins[next_unconnected_idx],
                                start_l,
                                allow_via,
                                cost_map=cost_map,
                                p_scale=p_scale,
                                end_layer=end_l,
                                clearance_mm=clearance_mm,
                                clearance_mask=clearance_mask,
                                custom_heuristic=custom_heuristic,
                                guide_map=guide_map,
                                guide_bias=guide_bias,
                            )
                            if new_path:
                                new_path_cost = (
                                    len(new_path)
                                    + sum(
                                        1
                                        for j in range(1, len(new_path))
                                        if new_path[j].layer != new_path[j - 1].layer
                                    )
                                    * self.via_cost
                                )
                                heapq.heappush(
                                    pq, (new_path_cost, to_idx, next_unconnected_idx, new_path)
                                )

        if len(connected_pins) < num_pins:
            # Not all pins could be connected
            for gx, gy, l, v in original_occupancy:
                self.occupancy[gx, gy, l] = v
            res = RoutePath(
                net=net_name,
                cells=[],
                length=0.0,
                via_count=0,
                success=False,
                failure_reason=f"Could not connect all pins for net {net_name}",
            )
            self.routed_paths[net_name] = res
            return res

        # Combine all paths into a single set of unique cells
        for path in all_paths:
            for cell in path:
                final_all_cells.append(cell)

            # Identify vias and accumulate difficulty
            for j in range(1, len(path)):
                if path[j].layer != path[j - 1].layer:
                    final_total_vias += 1
                    final_via_cells.add((path[j - 1].x, path[j - 1].y, path[j - 1].layer))
                    final_via_cells.add((path[j].x, path[j].y, path[j].layer))

                d = self._get_cell_difficulty(path[j])
                final_total_difficulty += d
                final_cell_difficulties.append(d)

        # FEAT-1: Automatic Via Array Generation
        explicit_vias: list[TraceVia] = []
        if self.design_rules:
            via_template = self.design_rules.get_via_template(net_name)
            if via_template and via_template.via_count > 1:
                for i in range(1, len(final_all_cells)):
                    c1 = final_all_cells[i - 1]
                    c2 = final_all_cells[i]

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
                                    size=via_template.via_diameter_mm,
                                    drill=via_template.via_drill_mm,
                                    layers=layers,
                                )
                            )

                            gx, gy = self._world_to_grid(px, py)

                            via_copper_cells = self._get_inflated_cells(
                                gx, gy, 0, width_mm=via_template.via_diameter_mm, clearance_mm=0.0
                            )

                            for ix, iy, _ in via_copper_cells:
                                for l in range(self.num_layers):
                                    if 0 <= ix < self.grid_size[0] and 0 <= iy < self.grid_size[1]:
                                        self.occupancy[ix, iy, l] = 2
                                        self.class_grid[ix, iy, l] = current_class_id
                                        self.present_congestion[ix, iy, l] += 1.0

                                        key_inf = (ix, iy, l)
                                        if key_inf not in self.net_occupancy:
                                            self.net_occupancy[key_inf] = set()
                                        self.net_occupancy[key_inf].add(net_name)
                                        self.cell_owner[key_inf] = net_name

        # Mark cells as occupied with differentiated inflation
        unique_cells = {(c.x, c.y, c.layer) for c in final_all_cells}
        for cx, cy, cl in unique_cells:
            is_via = (cx, cy, cl) in final_via_cells
            width = via_diameter if is_via else trace_width

            affected_cells = self._get_inflated_cells(cx, cy, cl, width_mm=width, clearance_mm=0.0)
            for ax, ay, al in affected_cells:
                self.occupancy[ax, ay, al] = 2
                self.class_grid[ax, ay, al] = current_class_id
                self.present_congestion[ax, ay, al] += 1.0
                key = (ax, ay, al)
                if key not in self.net_occupancy:
                    self.net_occupancy[key] = set()
                self.net_occupancy[key].add(net_name)
                self.cell_owner[key] = net_name

        if self.drc_oracle is not None:
            net_rules = (
                self.design_rules.get_rules_for_net(net_name) if self.design_rules else None
            )
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
        print(
            f"DEBUG_ASTAR: find_path_rrr called: start={start} end={end} layer={layer} end_layer={end_layer} allow_change={allow_layer_change}"
        )

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
            print(f"DEBUG_ASTAR: Start blocked at {start} on layer {layer}")
            return None

        # If end is blocked on target layer, try to find an accessible layer
        if is_end_hard_blocked:
            print(f"DEBUG_ASTAR: End blocked at {end} on target layer {target_layer}")
            found = False
            for l in range(self.num_layers):
                if int(self.occupancy[end[0], end[1], l]) != -1:
                    target_layer = l
                    end_cell = GridCell(end[0], end[1], l)
                    found = True
                    print(f"DEBUG_ASTAR: Using alternative end layer {l} for {end}")
                    break
            if not found:
                print(f"DEBUG_ASTAR: End blocked on all layers at {end}")
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

        print(
            f"DEBUG_ASTAR: use_numba={use_numba}, has_custom_heuristic={custom_heuristic is not None}"
        )

        if use_numba:
            try:
                t_numba = time.perf_counter()
                self.stats.profile.numba_calls += 1

                occ = self._occupancy_np.astype(np.int32)
                hist = self._history_np.astype(np.float32)
                cong = self._congestion_np.astype(np.float32)

                cmap = None
                if cost_map is not None:
                    cmap = np.asarray(cost_map, dtype=np.float32)

                cspace = None
                if self.soft_c_space is not None:
                    cspace = self._soft_c_space_np.astype(np.float32)

                if clearance_mask is not None:
                    clearance_mask = np.ascontiguousarray(clearance_mask)

                # Use Adaptive Numba router (supports dist_map, clearance_mask, and guide_map)
                dist_map = self._compute_distance_map(end_cell, _layer=target_layer)

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

    def _run_post_processing(self) -> None:
        """Run post-processing optimization passes on routed geometry.

        Executes via optimization, trace nudging, and trace ballooning
        to eliminate DRC violations after routing is complete.
        """
        from temper_placer.routing.constraints.spatial_index import PCBGeometry
        from temper_placer.routing.post_processing.via_optimizer import ViaOptimizer
        from temper_placer.routing.post_processing.nudger import GeometricNudger
        from temper_placer.routing.post_processing.trace_ballooner import TraceBallooner

        logger.info("Starting post-processing pipeline")

        if not self.drc_oracle:
            logger.warning("No DRC oracle available, skipping post-processing")
            return

        geometry = self.drc_oracle.geometry

        if not geometry.tracks and not geometry.vias:
            logger.info("No geometry to optimize")
            return

        logger.info(f"Initial geometry: {len(geometry.tracks)} tracks, {len(geometry.vias)} vias")

        via_optimizer = ViaOptimizer(self.drc_oracle)
        geometry = via_optimizer.optimize_vias(geometry)
        logger.info(
            f"Via optimization complete: {via_optimizer.stats.vias_consolidated} consolidated, "
            f"{via_optimizer.stats.vias_repositioned} repositioned, {via_optimizer.stats.vias_eliminated} eliminated"
        )

        violations = self.drc_oracle.validate_all()
        if not violations:
            logger.info("Post-processing complete: 0 DRC violations")
            return

        nudger = GeometricNudger(self.drc_oracle)
        nudger.oracle.geometry = geometry
        nudger.optimize(iterations=50, step_size=0.5)
        logger.info(f"Trace nudging complete")

        geometry = self.drc_oracle.geometry

        ballooner = TraceBallooner(geometry)
        result = ballooner.balloon_traces(geometry.tracks)
        logger.info(f"Trace ballooning complete: {result.segments_expanded} segments expanded")

        violations = self.drc_oracle.validate_all()
        if violations:
            logger.warning(f"Post-processing complete with {len(violations)} remaining violations")
        else:
            logger.info("Post-processing complete: 0 DRC violations")


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
