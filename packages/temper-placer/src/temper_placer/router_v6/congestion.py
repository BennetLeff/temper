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
``Bottleneck.to_coordinates``, ``CongestionResult.overflow_ratio``,
``estimate_net_demand`` and ``CongestionResult.get_top_bottlenecks`` all
delegate to ``temper_geometry``. Two of those delegations close gaps this
module's earlier wave-4 wiring had to document as blocking:

* ``estimate_net_demand`` delegates to ``congestion_estimate_net_demand_py``
  in its **accumulator** form (the trailing ``demand`` array). The kernel
  used to always build a fresh zero-initialised grid from ``(width, height)``
  with no parameter for an already-populated ``grid.demand``; this
  function's only production caller (``analyze_congestion``'s per-net loop)
  accumulates onto the SAME grid across many nets, so the plain form would
  silently drop every net's demand but the first. The kernel now adds
  ``demand_per_cell`` into the passed-in demand grid in place; the pinned
  ``None`` form keeps the fresh-grid contract the single-net differential
  binds.
* ``CongestionResult.get_top_bottlenecks`` delegates to
  ``congestion_result_top_bottlenecks_py``, which sorts REAL bottleneck
  records -- ``(x, y, utilization, overflow, layer)``, the flattened
  ``Bottleneck`` dataclass -- rather than reconstructing synthetic
  ``Bottleneck(x=i, y=0, utilization=i, ...)`` rows from a bare list of
  ``overflow`` floats (which discarded the true fields of any real record).

``analyze_congestion`` keeps its orchestration in Python for a documented
reason, not by accident. Its two optional parameters -- ``positions=`` and
``layer_assignments=`` -- are NOT part of ``congestion_analyze_py``'s
contract: that kernel (see ``packages/temper-geometry/src/congestion_analysis.rs``)
is bound by its own differential with ``positions=None,
layer_assignments=None`` always, resolves every net on layer 0, and assumes a
``(0.0, 0.0)`` board origin. Every production caller uses the excluded
shapes: ``metrics/physics.py`` passes ``positions=``,
``router_v6/verifier.py`` passes ``positions=`` AND ``layer_assignments=``,
and nothing constrains a real ``Board``'s origin to zero. Wiring the whole
function to that kernel would silently mis-place every pin's demand on any
board that uses one of those features -- the same defect class this module's
wave-4 wiring exists to avoid (the kernel's own bottom-side mirror,
``if side == 1: px = -px``, was the third instance of that class, fixed in
#832 and pinned by the differential's ``mixed_side_mirror`` design). What
``analyze_congestion`` DOES run is nonetheless delegated at every compute
layer: the grid kernels, the per-net demand accumulation
(``estimate_net_demand`` above), ``get_utilization``/``get_overflow``, and
pin-position resolution (``pin_world_position_at`` already calls
``pin_world_position_kernel_py``, which mirrors X before rotation for
bottom-side components). The remaining Python is orchestration -- layer
promotion, the per-net loop, and dataclass assembly -- exactly the seams the
established migration pattern keeps on this side of the boundary
(``routing_demand.py`` keeps its dict/list marshalling).
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, TypeAlias

import numpy as np
import temper_geometry as _tg

Array: TypeAlias = np.ndarray  # numpy alias replacing JAX Array post-JAX retirement

from temper_placer.core.board import Board
from temper_placer.core.netlist import Netlist
from temper_placer.core.pad_identity import net_pin_occurrence_indices, nth_matching_pin
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

        Delegates to ``congestion_result_top_bottlenecks_py``, which sorts
        REAL bottleneck records (``(x, y, utilization, overflow, layer)``) --
        the flattened ``Bottleneck`` dataclass -- via Python's own ``sorted``
        (timsort; NaN-key and signed-zero semantics pinned by the
        differential) and a real ``[:n]`` slice (a NEGATIVE ``n`` drops the
        last ``|n|``, exactly like the reference's ``sorted_bottlenecks[:n]``).

        Args:
            n: Maximum number of bottlenecks to return.

        Returns:
            List of up to n bottlenecks, sorted by overflow (descending).
        """
        rows = [(b.x, b.y, b.utilization, b.overflow, b.layer) for b in self.bottlenecks]
        out = _tg.congestion_result_top_bottlenecks_py(rows, n)
        return [
            Bottleneck(x=x, y=y, utilization=utilization, overflow=overflow, layer=layer)
            for (x, y, utilization, overflow, layer) in out
        ]


def estimate_net_demand(
    grid: CongestionGrid,
    pin_positions: list[tuple[float, float]],
    layer: int = 0,
    demand_per_cell: float = 1.0,
) -> CongestionGrid:
    """Estimate routing demand for a single net.

    Uses bounding box estimation - all cells within the net's bounding box
    get a fraction of the demand based on likely routing paths.

    Delegates to ``congestion_estimate_net_demand_py``'s **accumulator**
    form: this module's only caller (``analyze_congestion``'s per-net loop)
    accumulates onto the SAME grid across many nets, so the kernel must add
    into an already-populated demand array rather than rebuild a fresh zero
    one -- the accumulator parameter is what makes that delegation safe (see
    the module docstring).

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

    # The kernel mutates the array it is given, so it gets a copy -- the
    # caller's grid stays untouched, exactly as the pinned reference's
    # `grid.demand.copy()` semantics require.
    new_demand = grid.demand.copy()
    out_demand, is_identity = _tg.congestion_estimate_net_demand_py(
        grid.width_cells * grid.cell_size_mm,
        grid.height_cells * grid.cell_size_mm,
        grid.cell_size_mm,
        grid.origin,
        list(pin_positions),
        layer,
        demand_per_cell,
        grid.num_layers,
        new_demand,
    )
    # Identity return for the D3 guard (a net whose bounding box does not
    # intersect the grid): the input grid object itself is handed back.
    if is_identity:
        return grid
    return CongestionGrid(
        demand=out_demand,
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

    Pin resolution uses
    :func:`temper_placer.core.pad_identity.nth_matching_pin`
    (occurrence-indexed), not a bare ``if pin.name == pin_name or
    pin.number == pin_name: break`` first-match scan -- a component with
    more than one physical pad sharing a pad number (K2/K3's
    manufacturer-duplicated current-sharing contacts) would otherwise have
    every occurrence resolve to the SAME coordinate, silently corrupting
    the min-cut source/sink geometry this feeds. See
    ``temper_placer.core.pad_identity``'s module docstring.
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
    occurrence_indices = net_pin_occurrence_indices(net.pins)
    for (comp_ref, pin_name), occurrence in zip(net.pins, occurrence_indices, strict=True):
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
        pin = nth_matching_pin(comp, pin_name, occurrence)
        if pin is not None:
            pin_x, pin_y = pin_world_position_at(pin, comp, pos_override=pos_override)
            pin_positions.append((pin_x, pin_y))

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
