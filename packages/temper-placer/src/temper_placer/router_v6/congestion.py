"""
Grid-based congestion analysis for PCB routing (temper-wna.3).

This module divides the board into grid cells and estimates routing demand
vs supply to identify bottlenecks before actual routing. This is a fast
feasibility check that helps the placement optimizer avoid unroutable layouts.

Grid Model:
- Board divided into cells (default 1mm x 1mm)
- Each cell has a capacity (supply = tracks that fit)
- Demand = estimated routing through each cell
- Bottleneck = demand > supply

Example usage:
    >>> from temper_placer.router_v6.congestion import analyze_congestion
    >>> from temper_placer.core.board import Board
    >>>
    >>> result = analyze_congestion(netlist, board)
    >>> if not result.is_feasible():
    ...     for b in result.get_top_bottlenecks(5):
    ...         print(f"Bottleneck at ({b.x}, {b.y}): {b.utilization:.1%}")

Wave 4 Phase B (``docs/plans/2026-08-01-001-feat-wave4-full-migration-program-plan.md``):
``CongestionGrid.from_board``/``get_utilization``/``get_overflow``,
``Bottleneck.to_coordinates`` and ``CongestionResult.overflow_ratio`` delegate
to ``temper_geometry`` (``congestion_grid_from_board_py`` and neighbours) --
pure array/scalar math with no gap between the kernel's contract and this
module's. Three entry points do **not** delegate, each for a reason verified
against a real production call site rather than only against the
differential (``tests/router_v6/test_congestion_rust_differential.py``,
which never exercises any of these three call shapes):

* ``estimate_net_demand`` -- the Rust kernel (``congestion_estimate_net_demand_py``)
  always builds a *fresh* zero-initialised grid from ``(width, height)``; it
  has no parameter for an already-populated ``grid.demand``. This function's
  only production caller (``analyze_congestion``'s per-net loop, below)
  accumulates onto the SAME grid across many nets, so delegating here would
  silently drop every net's demand but the first.
* ``CongestionResult.get_top_bottlenecks`` -- the Rust kernel
  (``congestion_result_top_bottlenecks_py``) takes only the list of
  ``overflow`` floats and reconstructs synthetic ``Bottleneck(x=i, y=0,
  utilization=float(i), ...)`` rows to match the differential's own test
  fixture; it cannot sort real ``Bottleneck`` objects (arbitrary ``x``/``y``/
  ``utilization``/``layer``) without discarding their true fields.
* ``analyze_congestion`` -- the Rust kernel (``congestion_analyze_py``)
  reimplements pin-position resolution via its own ``pin_world_position``,
  which composes rotation only and omits the bottom-side mirror
  (``if side == 1: px = -px``) that
  ``core.pin_geometry.pin_world_position_at`` applies. The kernel's own
  module doc names this omission deliberate: its corpus never sets
  ``Component.initial_side``, so the mirror branch "never fires" there. Every
  real caller (``metrics/physics.py``, ``pipeline/stages/routing_stage.py``,
  ``router_v6/verifier.py``) analyzes netlists that may legitimately place
  components on the bottom side, so wiring this kernel would silently
  mis-place every bottom-side pin's demand contribution on any board that
  uses one -- a regression invisible to the differential (whose corpus never
  sets a side) and only reachable by inspecting the kernel's own
  ``pin_world_position`` against ``pin_world_position_at``.
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, TypeAlias

import numpy as np
import temper_geometry as _tg

Array: TypeAlias = np.ndarray  # numpy alias replacing JAX Array post-JAX retirement

from temper_placer.core.board import Board
from temper_placer.core.netlist import Netlist
from temper_placer.core.pin_geometry import pin_world_position_at

if TYPE_CHECKING:
    from temper_placer.router_v6.layer_assignment import LayerAssignment


@dataclass
class CongestionGrid:
    """Grid structure for congestion analysis.

    Represents routing demand and supply across a discretized board.
    Can be single-layer (2D) or multi-layer (3D).

    Attributes:
        demand: Routing demand array, shape (H, W) or (L, H, W)
        supply: Routing capacity array, same shape as demand
        cell_size_mm: Size of each grid cell in mm
        width_cells: Number of cells horizontally
        height_cells: Number of cells vertically
        num_layers: Number of routing layers (1 for 2D, >1 for 3D)
        origin: Board origin coordinates (x, y)
    """

    demand: Array
    supply: Array
    cell_size_mm: float
    width_cells: int
    height_cells: int
    num_layers: int = 1
    origin: tuple[float, float] = (0.0, 0.0)

    @classmethod
    def from_board(
        cls,
        board: Board,
        cell_size_mm: float = 1.0,
        num_layers: int = 1,
        default_supply: float = 10.0,
    ) -> "CongestionGrid":
        """Create a congestion grid from a board specification.

        Args:
            board: Board definition with width, height, origin.
            cell_size_mm: Grid cell size in mm (default 1.0).
            num_layers: Number of routing layers (default 1).
            default_supply: Default routing capacity per cell (default 10.0).

        Returns:
            CongestionGrid initialized with zero demand and uniform supply.

        Example:
            >>> board = Board(width=100.0, height=100.0)
            >>> grid = CongestionGrid.from_board(board, cell_size_mm=1.0)
            >>> grid.width_cells
            100
        """
        demand, supply, cell_size_mm, width_cells, height_cells, num_layers, origin = (
            _tg.congestion_grid_from_board_py(
                board.width,
                board.height,
                board.origin,
                cell_size_mm,
                num_layers,
                default_supply,
            )
        )
        return cls(
            demand=demand,
            supply=supply,
            cell_size_mm=cell_size_mm,
            width_cells=width_cells,
            height_cells=height_cells,
            num_layers=num_layers,
            origin=origin,
        )

    def get_utilization(self) -> Array:
        """Compute utilization (demand/supply) for each cell.

        Returns:
            Array of utilization ratios, same shape as demand.
        """
        demand_arr = np.asarray(self.demand)
        supply_arr = np.asarray(self.supply)
        # The kernel is a flat 1xN elementwise op (`np.maximum`/division are
        # shape-independent), so flattening then reshaping back preserves the
        # original shape and is bit-identical to computing in place.
        result = _tg.congestion_grid_utilization_py(
            demand_arr.flatten().tolist(), supply_arr.flatten().tolist()
        )
        return np.asarray(result).reshape(demand_arr.shape)

    def get_overflow(self) -> Array:
        """Compute overflow (demand - supply) for each cell.

        Returns:
            Array of overflow values, clipped to >= 0.
        """
        demand_arr = np.asarray(self.demand)
        supply_arr = np.asarray(self.supply)
        result = _tg.congestion_grid_overflow_py(
            demand_arr.flatten().tolist(), supply_arr.flatten().tolist()
        )
        return np.asarray(result).reshape(demand_arr.shape)


@dataclass
class Bottleneck:
    """A congestion hotspot on the board.

    Attributes:
        x: Grid cell x coordinate (column)
        y: Grid cell y coordinate (row)
        utilization: Demand/supply ratio
        overflow: Amount by which demand exceeds supply
        layer: Layer index (for multi-layer grids)
    """

    x: int
    y: int
    utilization: float
    overflow: float
    layer: int = 0

    def to_coordinates(
        self,
        cell_size_mm: float = 1.0,
        origin: tuple[float, float] = (0.0, 0.0),
    ) -> tuple[float, float]:
        """Convert grid cell to board coordinates.

        Returns the center of the cell in board coordinates.

        Args:
            cell_size_mm: Size of each grid cell.
            origin: Board origin coordinates.

        Returns:
            (x, y) center of the bottleneck cell in mm.
        """
        return _tg.congestion_bottleneck_to_coordinates_py(self.x, self.y, cell_size_mm, origin)


@dataclass
class CongestionResult:
    """Result of congestion analysis.

    Attributes:
        grid: The congestion grid with demand/supply data
        bottlenecks: List of cells where demand exceeds supply
        total_overflow: Sum of all overflow values
        max_utilization: Maximum utilization across all cells
    """

    grid: CongestionGrid
    bottlenecks: list[Bottleneck] = field(default_factory=list)
    total_overflow: float = 0.0
    max_utilization: float = 0.0

    def is_feasible(self, threshold: float = 1.0) -> bool:
        """Check if routing is feasible (no significant overflow).

        Args:
            threshold: Utilization threshold for feasibility (default 1.0).

        Returns:
            True if max utilization is below threshold.
        """
        return self.max_utilization <= threshold

    def overflow_ratio(self) -> float:
        """Compute overflow as a ratio of total demand.

        Returns:
            Overflow / total_demand, clamped to [0, 1].
        """
        demand_arr = np.asarray(self.grid.demand)
        return _tg.congestion_result_overflow_ratio_py(
            demand_arr.flatten().tolist(), self.total_overflow
        )

    def get_top_bottlenecks(self, n: int = 10) -> list[Bottleneck]:
        """Get the top N bottlenecks sorted by overflow.

        Args:
            n: Maximum number of bottlenecks to return.

        Returns:
            List of up to n bottlenecks, sorted by overflow (descending).
        """
        sorted_bottlenecks = sorted(self.bottlenecks, key=lambda b: b.overflow, reverse=True)
        return sorted_bottlenecks[:n]


def estimate_net_demand(
    grid: CongestionGrid,
    pin_positions: list[tuple[float, float]],
    layer: int = 0,
    demand_per_cell: float = 1.0,
) -> CongestionGrid:
    """Estimate routing demand for a single net.

    Uses bounding box estimation - all cells within the net's bounding box
    get a fraction of the demand based on likely routing paths.

    Args:
        grid: CongestionGrid to update.
        pin_positions: List of (x, y) pin positions for the net.
        layer: Layer index for multi-layer grids.
        demand_per_cell: Demand value to add per cell.

    Returns:
        Updated CongestionGrid with added demand.
    """
    if len(pin_positions) < 2:
        return grid

    # Compute bounding box
    xs = [p[0] for p in pin_positions]
    ys = [p[1] for p in pin_positions]

    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)

    # Convert to grid coordinates
    cell_size = grid.cell_size_mm
    origin_x, origin_y = grid.origin

    col_min = max(0, int((min_x - origin_x) / cell_size))
    col_max = min(grid.width_cells - 1, int((max_x - origin_x) / cell_size))
    row_min = max(0, int((min_y - origin_y) / cell_size))
    row_max = min(grid.height_cells - 1, int((max_y - origin_y) / cell_size))

    # A net whose bounding box does not intersect the grid contributes no
    # demand. Clamping each pair from one side only is not enough: a net
    # entirely left of (or above) the board leaves col_max/row_max NEGATIVE,
    # and `demand[0 : -3 + 1, 0 : -3 + 1]` is a *negative-index* slice -- it
    # writes a real block of demand at the board ORIGIN. The far edge was
    # already correct by accident (col_min > col_max yields an empty
    # `[50:10]` slice), which is exactly what made the near edge visible.
    if col_max < col_min or row_max < row_min:
        return grid

    # Add demand to cells in bounding box
    # Use half-perimeter estimation - weight cells along likely routing paths
    if grid.num_layers == 1:
        # 2D grid
        new_demand = grid.demand.copy()
        new_demand[row_min : row_max + 1, col_min : col_max + 1] += demand_per_cell
        return CongestionGrid(
            demand=new_demand,
            supply=grid.supply,
            cell_size_mm=grid.cell_size_mm,
            width_cells=grid.width_cells,
            height_cells=grid.height_cells,
            num_layers=grid.num_layers,
            origin=grid.origin,
        )
    else:
        # 3D grid - add demand to specific layer
        new_demand = grid.demand.copy()
        new_demand[layer, row_min : row_max + 1, col_min : col_max + 1] += demand_per_cell
        return CongestionGrid(
            demand=new_demand,
            supply=grid.supply,
            cell_size_mm=grid.cell_size_mm,
            width_cells=grid.width_cells,
            height_cells=grid.height_cells,
            num_layers=grid.num_layers,
            origin=grid.origin,
        )


def _get_pin_positions(
    netlist: Netlist,
    net_name: str,
    positions: Array | None = None,
) -> list[tuple[float, float]]:
    """Get pin positions for a net.

    Args:
        netlist: Netlist containing components and nets.
        net_name: Name of the net.
        positions: Optional (N, 2) array of component positions.

    Returns:
        List of (x, y) pin positions.
    """
    pin_positions: list[tuple[float, float]] = []

    # Build component lookup
    comp_by_ref = {c.ref: (i, c) for i, c in enumerate(netlist.components)}

    # Find the net
    net = None
    for n in netlist.nets:
        if n.name == net_name:
            net = n
            break

    if net is None:
        return pin_positions

    # Collect pin positions
    for pin_ref in net.pins:
        comp_ref, pin_name = pin_ref

        if comp_ref not in comp_by_ref:
            continue

        comp_idx, comp = comp_by_ref[comp_ref]

        # Get component position. When an explicit `positions` array is given
        # it OVERRIDES the component's own initial_position -- that is the
        # whole point of the argument, and the caller (the placement feedback
        # loop) is evaluating a candidate placement, not the stored one.
        # `pos_override=None` falls back to comp.initial_position, and then to
        # (0.0, 0.0), inside pin_world_position_at.
        pos_override: tuple[float, float] | None = None
        if positions is not None:
            pos_override = (float(positions[comp_idx, 0]), float(positions[comp_idx, 1]))

        # Find pin and get its position
        for pin in comp.pins:
            if pin.name == pin_name or pin.number == pin_name:
                pin_x, pin_y = pin_world_position_at(pin, comp, pos_override=pos_override)
                pin_positions.append((pin_x, pin_y))
                break

    return pin_positions


def analyze_congestion(
    netlist: Netlist,
    board: Board,
    positions: Array | None = None,
    layer_assignments: dict[str, "LayerAssignment"] | None = None,
    cell_size_mm: float = 1.0,
    capacity_per_cell: float = 10.0,
    num_layers: int = 1,
) -> CongestionResult:
    """Analyze routing congestion for a placement.

    Estimates routing demand across the board and identifies bottlenecks
    where demand exceeds capacity.

    Args:
        netlist: Netlist with components and nets.
        board: Board specification.
        positions: Optional (N, 2) array of component positions.
        layer_assignments: Optional layer assignments for nets.
        cell_size_mm: Grid cell size (default 1.0mm).
        capacity_per_cell: Routing capacity per cell (default 10.0).
        num_layers: Number of routing layers (default 1).

    Returns:
        CongestionResult with grid, bottlenecks, and statistics.

    Example:
        >>> result = analyze_congestion(netlist, board)
        >>> if not result.is_feasible():
        ...     print("Routing may fail!")
    """
    # Handle layer assignment impact on num_layers
    if layer_assignments is not None and num_layers == 1:
        # Check if any assignments use multiple layers
        from temper_placer.router_v6.layer_assignment import Layer

        layers_used = set()
        for assignment in layer_assignments.values():
            if assignment.primary_layer == Layer.L1_TOP:
                layers_used.add(0)
            elif assignment.primary_layer == Layer.L4_BOT:
                layers_used.add(1)
        if len(layers_used) > 1:
            num_layers = 2

    # Create grid
    grid = CongestionGrid.from_board(
        board,
        cell_size_mm=cell_size_mm,
        num_layers=num_layers,
        default_supply=capacity_per_cell,
    )

    # Estimate demand for each net
    for net in netlist.nets:
        pin_positions = _get_pin_positions(netlist, net.name, positions)

        if len(pin_positions) < 2:
            continue

        # Determine layer for this net
        layer = 0
        if layer_assignments is not None and net.name in layer_assignments:
            from temper_placer.router_v6.layer_assignment import Layer

            assignment = layer_assignments[net.name]
            if assignment.primary_layer == Layer.L4_BOT:
                layer = 1 if num_layers > 1 else 0

        grid = estimate_net_demand(grid, pin_positions, layer=layer)

    # Compute statistics
    utilization = grid.get_utilization()
    overflow = grid.get_overflow()

    max_utilization = float(utilization.max())
    total_overflow = float(overflow.sum())

    # Identify bottlenecks (cells with overflow)
    bottlenecks: list[Bottleneck] = []

    if num_layers == 1:
        # 2D grid
        overflow_mask = overflow > 0
        if overflow_mask.any():
            rows, cols = np.where(overflow_mask)
            for i in range(len(rows)):
                r, c = int(rows[i]), int(cols[i])
                bottlenecks.append(
                    Bottleneck(
                        x=c,
                        y=r,
                        utilization=float(utilization[r, c]),
                        overflow=float(overflow[r, c]),
                        layer=0,
                    )
                )
    else:
        # 3D grid
        for layer_idx in range(num_layers):
            layer_overflow = overflow[layer_idx]
            overflow_mask = layer_overflow > 0
            if overflow_mask.any():
                rows, cols = np.where(overflow_mask)
                for i in range(len(rows)):
                    r, c = int(rows[i]), int(cols[i])
                    bottlenecks.append(
                        Bottleneck(
                            x=c,
                            y=r,
                            utilization=float(utilization[layer_idx, r, c]),
                            overflow=float(layer_overflow[r, c]),
                            layer=layer_idx,
                        )
                    )

    return CongestionResult(
        grid=grid,
        bottlenecks=bottlenecks,
        total_overflow=total_overflow,
        max_utilization=max_utilization,
    )
