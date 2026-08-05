"""Pinned Python oracle for Wave-4 **cluster E** -- congestion & placement feedback.

DO NOT EDIT -- THESE ARE THE REFERENCE.
=======================================
Every executable statement below is a **verbatim** ``git show`` extraction
from commit ``143752893c177dc976da614566c64e4e53e4951f`` (``origin/main``,
2026-08-04) of the six modules listed in the survey's cluster E
(``docs/evidence/2026-08-04-router-v6-migration-survey.md`` §4):

===========================  =======  ================================================
module                       stmts    top-level definitions copied here
===========================  =======  ================================================
``congestion.py``              160    ``CongestionGrid``, ``Bottleneck``,
                                      ``CongestionResult``, ``estimate_net_demand``,
                                      ``_get_pin_positions``, ``analyze_congestion``
``congestion_analysis.py``      79    ``CongestionSeverity``, ``CongestedRegion``,
                                      ``CongestionMap``,
                                      ``identify_congested_regions``,
                                      ``_classify_congestion``
``routing_demand.py``           73    ``RoutingDemand``, ``estimate_routing_demand``
``placement_suggestions.py``    58    ``PlacementSuggestion``, ``PlacementSuggestions``,
                                      ``generate_placement_suggestions``,
                                      ``_find_affected_components``,
                                      ``_calculate_suggested_position``
``congestion_heatmap.py``       51    ``CongestionHeatmap``
``apply_suggestions.py``        48    ``AppliedAdjustment``, ``AdjustmentResult``,
                                      ``apply_suggestions_with_damping``,
                                      ``_calculate_damped_position``,
                                      ``update_component_positions``
===========================  =======  ================================================

Nothing here has been cleaned up, refactored, reformatted, or fixed --
**including the three defects documented under "Known defects" below**.  A
fix would break the verbatim pin and silently weaken the differential proof:
the Rust kernel's contract is *this behaviour*, defects and all, until a
separate PR changes the production module and re-pins the oracle.

``test_congestion_rust_differential.py::test_oracle_is_verbatim_copy``
re-extracts every definition above from the pinned commit and compares the
source text character for character, so drift here fails CI rather than
passing quietly.

What was deliberately NOT copied
--------------------------------
``routing_demand.RoutingDemandStage`` and ``routing_demand.validate_routing_demand``
are excluded.  They are the Stage wrapper and its ``@register_validator``
hook -- orchestration, in the survey's GLUE sense, not kernel -- and
``@register_validator("RoutingDemand")`` mutates a *process-global* validator
registry at import time, so importing the oracle would double-register a
validator for the shipped module.  The exclusion is behavioural, not
cosmetic, and is asserted by ``test_oracle_excludes_the_stage_wrapper``.

Everything else that differs from the six source files is import plumbing:
the six import blocks are merged into the single block below, the
cross-module imports (``placement_suggestions`` -> ``congestion_analysis``,
``apply_suggestions`` -> ``placement_suggestions``) resolve locally instead,
and ``from __future__ import annotations`` is present (5 of the 6 sources
have it; ``congestion.py`` does not, and every annotation in it is either
quoted or deferred-safe, so the merge is semantics-preserving).

Which language's operator each call site uses (catalog §2)
-----------------------------------------------------------
The Rust mirror must pick its helper per call site by reading this table --
``np_maximum`` / ``py_min`` / ``f64::max`` are three different functions and
this cluster uses two of the three, sometimes in the same expression.

**numpy ufuncs -- NaN propagates from EITHER operand (B12).  Use ``np_maximum``.**

* ``CongestionGrid.get_utilization``: ``np.maximum(self.supply, 1e-6)``.
  Measured: a NaN anywhere in ``supply`` yields NaN, where ``f64::max``
  would keep ``1e-6`` and CPython ``max`` would depend on argument order.
* ``CongestionGrid.get_overflow``: ``np.maximum(self.demand - self.supply, 0.0)``.
* ``CongestionHeatmap.from_router``: ``np.max(congestion_3d, axis=2)`` and
  ``np.max(history_3d, axis=2)`` -- the *reduction*, whose NaN semantics are
  again propagate-not-discard.

**CPython builtins -- the FIRST argument survives a NaN (B5).  Use ``py_max``/``py_min``.**

* ``CongestionResult.overflow_ratio``: ``min(self.total_overflow / total_demand, 1.0)``
  -- measured NaN in, NaN out, because the NaN is the *first* argument.
  ``f64::min`` would return ``1.0``.
* ``estimate_net_demand``: ``max(0, int(...))`` and ``min(grid.width_cells - 1, int(...))``
  x4.  These are **int** ``max``/``min``, not float -- the ``int()`` truncation
  happens first and can raise (see "Known defects").
* ``congestion_analysis.identify_congested_regions``: ``min(1.0, congestion / 10.0)``
  -- NaN is the *second* argument here, so a NaN congestion score returns
  ``1.0``, the opposite of ``overflow_ratio`` above.  Same builtin, opposite
  outcome, five files apart: this is exactly the asymmetry B5 records.
* ``placement_suggestions.generate_placement_suggestions``:
  ``min(1.0, region.bottleneck_score * 1.2)``.
* ``congestion_heatmap.get_congestion_at``: ``max(0, min(gx, self.grid.shape[0] - 1))``
  -- **min-then-max nesting, on ints.**  The order is load-bearing per B5's
  grid-raster note and must not be rewritten as ``max``-then-``min``.

**libm ``pow``, not multiplication or ``sqrt`` (B7).**

* ``placement_suggestions._find_affected_components`` and
  ``._calculate_suggested_position``: ``(dx**2 + dy**2) ** 0.5``.
* ``apply_suggestions.AdjustmentResult.total_movement``: same expression.
  Measured on 20 000 random pairs: this form disagrees with
  ``math.hypot`` on **16.88%** of them and with ``sqrt(dx*dx + dy*dy)`` on
  **0.28%**.  Three spellings, three different answers -- copy the ``pow``
  form.

**numpy reduction order, not a left fold (B7).**

* ``CongestionHeatmap.get_total_congestion``: ``np.sum(self.grid)`` uses
  numpy's *pairwise* summation.  Measured on an 8x8 float32 grid it differs
  from a naive left-to-right accumulation in the last bits
  (``36.58964920043945`` vs ``36.5896481545642``).  A Rust ``iter().sum()``
  is the wrong answer.

**Python round-half-EVEN in string formatting (B3 family).**

* ``placement_suggestions.generate_placement_suggestions`` builds
  ``f"... (score: {region.bottleneck_score:.2f})"``, and that string is a
  dataclass field compared by the differential.  ``format(0.125, '.2f')`` is
  ``'0.12'``, not ``'0.13'``: CPython rounds the *exact binary value*
  half-to-even.  Any Rust mirror built out of ``(x * 100.0).round() / 100.0``
  gets ``0.13`` -- ``f64::round`` is half-away-from-zero.

**dtype leaks that a value-only comparison would miss.**

* ``CongestionHeatmap.from_router`` returns ``normalized.astype(np.float32)``
  -- an f32 grid, and the f32 rounding of ``combined / max_val`` is part of
  the contract.
* ``CongestionHeatmap.get_hotspots`` returns tuples whose third element is a
  ``numpy.float32`` while the first two are Python ``float``.  Measured.
  ``tests/router_v6/_signature.py`` separates those; ``==`` does not.

Known defects -- REPORTED, NOT FIXED
-------------------------------------
Found while pinning this oracle.  All three are reproduced verbatim above and
pinned by named differential cases, because the oracle's job is to be the
pre-migration behaviour, not the correct behaviour.

**D1 -- ``analyze_congestion``'s ``positions`` argument is dead.**
``_get_pin_positions`` computes ``comp_x, comp_y`` from ``positions`` (or from
``comp.initial_position``), then never reads them: the pin position actually
appended comes from ``pin_world_position(pin, comp)``, which reads the
component's own ``initial_position``.  The ``else`` branch even assigns to
``_comp_x, _comp_y`` -- underscore-prefixed, so linters see the whole triple
as intentionally unused rather than as a bug.  Measured: passing a
``positions`` array that moves every component tens of millimetres produces a
**byte-identical** result to ``positions=None``.  This is the placement
feedback loop's input, so the loop is currently blind to the positions it is
supposed to be evaluating.  Pinned by
``test_d1_positions_argument_is_ignored``.

**D2 -- the ``layer_assignments`` path raises ``ModuleNotFoundError``.**
``analyze_congestion`` does ``from temper_placer.routing.layer_assignment import Layer``
in two places.  There is no ``temper_placer.routing`` package -- the tree is
``temper_placer.router_v6`` -- so *any* call with ``layer_assignments is not None``
raises ``ModuleNotFoundError: No module named 'temper_placer.routing'``
before it computes anything.  The entire multi-layer branch of this module is
unreachable in production.  Pinned as **error parity** by
``test_d2_layer_assignments_raises_module_not_found``: the Rust arm must
raise the same exception type with the same message, which is the honest
contract until someone fixes the import.

**D3 -- off-board nets add demand to a 7x7 block at the origin.**
In ``estimate_net_demand`` the grid indices are clamped with
``col_min = max(0, int(...))`` but ``col_max = min(width_cells - 1, int(...))``
-- the upper bound is clamped from *above* only.  For a net entirely to the
left of the board, ``col_max`` stays negative, and
``new_demand[row_min:row_max + 1, col_min:col_max + 1]`` becomes a
**negative-index slice**: measured, a net at x in [-5, -4] on a 10x10 grid
writes demand into ``[0:-3, 0:-3]``, i.e. 49 cells at the board origin, when
the correct answer is zero cells.  Pinned by
``test_d3_offboard_net_writes_negative_slice``.

Cluster membership note
------------------------
The survey's cluster-E membership holds on reading, with one correction:
**``routing_demand.py`` does not import numpy.**  The brief's catalog note
lists it alongside ``congestion.py`` and ``congestion_heatmap.py`` as a B12
site; it is not one.  Its kernel is pure ``int``/``float`` arithmetic plus
two ``re.search`` calls, so B12 does not apply to it and B3/B5 do.  The other
five modules' membership is as surveyed.
"""

# ruff: noqa: UP037
#   ``CongestionGrid.from_board`` is annotated ``-> "CongestionGrid"`` and
#   ``analyze_congestion`` takes ``dict[str, "LayerAssignment"]``.  Both quoted
#   forward references are part of the verbatim pin.  Unquoting them is an
#   edit to the oracle, and the ``LayerAssignment`` one would additionally
#   turn a currently-inert reference to the non-existent
#   ``temper_placer.routing`` package (defect D2) into a runtime name.

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, TypeAlias

import numpy as np

from temper_placer.core.board import Board
from temper_placer.core.netlist import Netlist
from temper_placer.core.pin_geometry import pin_world_position
from temper_placer.router_v6.routing_results import RoutingResults
from temper_placer.router_v6.stage0_data import ParsedPCB

Array: TypeAlias = np.ndarray  # numpy alias replacing JAX Array post-JAX retirement

if TYPE_CHECKING:
    from typing import Any

    from temper_placer.routing.layer_assignment import LayerAssignment
else:
    Any = object

__all__ = [
    "AdjustmentResult",
    "AppliedAdjustment",
    "Bottleneck",
    "CongestedRegion",
    "CongestionGrid",
    "CongestionHeatmap",
    "CongestionMap",
    "CongestionResult",
    "CongestionSeverity",
    "PlacementSuggestion",
    "PlacementSuggestions",
    "RoutingDemand",
    "analyze_congestion",
    "apply_suggestions_with_damping",
    "estimate_net_demand",
    "estimate_routing_demand",
    "generate_placement_suggestions",
    "identify_congested_regions",
    "update_component_positions",
]


# --- congestion.py -----------------------------------------------------


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
        width_cells = int(math.ceil(board.width / cell_size_mm))
        height_cells = int(math.ceil(board.height / cell_size_mm))

        if num_layers == 1:
            demand = np.zeros((height_cells, width_cells))
            supply = np.full((height_cells, width_cells), default_supply)
        else:
            demand = np.zeros((num_layers, height_cells, width_cells))
            supply = np.full((num_layers, height_cells, width_cells), default_supply)

        return cls(
            demand=demand,
            supply=supply,
            cell_size_mm=cell_size_mm,
            width_cells=width_cells,
            height_cells=height_cells,
            num_layers=num_layers,
            origin=board.origin,
        )

    def get_utilization(self) -> Array:
        """Compute utilization (demand/supply) for each cell.

        Returns:
            Array of utilization ratios, same shape as demand.
        """
        return self.demand / np.maximum(self.supply, 1e-6)

    def get_overflow(self) -> Array:
        """Compute overflow (demand - supply) for each cell.

        Returns:
            Array of overflow values, clipped to >= 0.
        """
        return np.maximum(self.demand - self.supply, 0.0)


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
        center_x = origin[0] + (self.x + 0.5) * cell_size_mm
        center_y = origin[1] + (self.y + 0.5) * cell_size_mm
        return (center_x, center_y)


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
        total_demand = float(self.grid.demand.sum())
        if total_demand == 0:
            return 0.0
        return min(self.total_overflow / total_demand, 1.0)

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

        # Get component position
        if positions is not None:
            comp_x, comp_y = float(positions[comp_idx, 0]), float(positions[comp_idx, 1])
        elif comp.initial_position is not None:
            comp_x, comp_y = comp.initial_position
        else:
            _comp_x, _comp_y = 0.0, 0.0

        # Find pin and get its position
        for pin in comp.pins:
            if pin.name == pin_name or pin.number == pin_name:
                pin_x, pin_y = pin_world_position(pin, comp)
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
        from temper_placer.routing.layer_assignment import Layer

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
            from temper_placer.routing.layer_assignment import Layer

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


# --- congestion_analysis.py --------------------------------------------


class CongestionSeverity(Enum):
    """Congestion severity levels."""

    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class CongestedRegion:
    """A congested region on the PCB."""

    center: tuple[float, float]  # Region center (x, y) in mm
    radius: float  # Region radius in mm
    severity: CongestionSeverity
    failed_net_count: int  # Number of failed nets in this region
    bottleneck_score: float  # 0.0-1.0, higher = worse congestion


@dataclass
class CongestionMap:
    """Map of congested regions across the PCB."""

    regions: list[CongestedRegion]

    @property
    def congested_region_count(self) -> int:
        """Number of congested regions."""
        return len(self.regions)

    @property
    def critical_region_count(self) -> int:
        """Number of critical congestion regions."""
        return sum(1 for r in self.regions if r.severity == CongestionSeverity.CRITICAL)

    def get_regions_by_severity(self, severity: CongestionSeverity) -> list[CongestedRegion]:
        """Get all regions with specified severity."""
        return [r for r in self.regions if r.severity == severity]


def identify_congested_regions(
    routing_results: RoutingResults,
    board_width: float,
    board_height: float,
    grid_size: float = 10.0,  # mm per grid cell
) -> CongestionMap:
    """
    Identify congested regions from routing results.

    Analyzes failed nets and routing density to identify areas
    that need placement adjustment or more routing resources.

    Args:
        routing_results: Routing results from Stage 4.9
        board_width: Board width (mm)
        board_height: Board height (mm)
        grid_size: Size of analysis grid cells (mm)

    Returns:
        CongestionMap with identified congested regions

    Example:
        >>> from temper_placer.router_v6.routing_results import RoutingResults
        >>> results = RoutingResults(compiled_routes={}, failed_nets=[])
        >>> congestion = identify_congested_regions(results, 100, 100)
        >>> congestion.congested_region_count >= 0
        True
    """
    # Create grid for congestion analysis
    grid_cells_x = int(board_width / grid_size) + 1
    grid_cells_y = int(board_height / grid_size) + 1

    # Initialize congestion grid
    congestion_grid = [[0.0 for _ in range(grid_cells_x)] for _ in range(grid_cells_y)]
    failed_net_grid = [[0 for _ in range(grid_cells_x)] for _ in range(grid_cells_y)]

    # Analyze failed nets
    for _failed_net in routing_results.failed_nets:
        # Failed nets contribute to congestion
        # In practice, would use net pin locations
        # Simplified: assume center of board
        cx = int(board_width / 2 / grid_size)
        cy = int(board_height / 2 / grid_size)
        if 0 <= cx < grid_cells_x and 0 <= cy < grid_cells_y:
            failed_net_grid[cy][cx] += 1
            congestion_grid[cy][cx] += 0.5  # Failed net penalty

    # Analyze successful routes for density
    for _net_name, compiled_route in routing_results.compiled_routes.items():
        # Extract coordinates (handle RoutePath and RoutePath3D)
        coords = []
        if hasattr(compiled_route.path, "segments"):
            coords = [c[:2] for c in compiled_route.path.segments]
        elif hasattr(compiled_route.path, "coordinates"):
            coords = compiled_route.path.coordinates

        for coord in coords:
            x, y = coord
            cell_x = int(x / grid_size)
            cell_y = int(y / grid_size)

            if 0 <= cell_x < grid_cells_x and 0 <= cell_y < grid_cells_y:
                congestion_grid[cell_y][cell_x] += 0.1  # Route density contribution

    # Identify congested regions
    regions = []
    for y in range(grid_cells_y):
        for x in range(grid_cells_x):
            congestion = congestion_grid[y][x]
            failed_nets = failed_net_grid[y][x]

            # Only create region if significant congestion
            if congestion > 0.5 or failed_nets > 0:
                severity = _classify_congestion(congestion, failed_nets)

                # Convert grid coordinates to mm
                center_x = (x + 0.5) * grid_size
                center_y = (y + 0.5) * grid_size

                regions.append(
                    CongestedRegion(
                        center=(center_x, center_y),
                        radius=grid_size / 2,
                        severity=severity,
                        failed_net_count=failed_nets,
                        bottleneck_score=min(1.0, congestion / 10.0),
                    )
                )

    return CongestionMap(regions=regions)


def _classify_congestion(
    congestion_score: float,
    failed_net_count: int,
) -> CongestionSeverity:
    """
    Classify congestion severity.

    Args:
        congestion_score: Accumulated congestion score
        failed_net_count: Number of failed nets

    Returns:
        CongestionSeverity classification
    """
    # Failed nets are critical
    if failed_net_count >= 3:
        return CongestionSeverity.CRITICAL
    elif failed_net_count >= 1:
        return CongestionSeverity.HIGH

    # Based on congestion score
    if congestion_score > 5.0:
        return CongestionSeverity.HIGH
    elif congestion_score > 3.0:
        return CongestionSeverity.MEDIUM
    elif congestion_score > 1.0:
        return CongestionSeverity.LOW
    else:
        return CongestionSeverity.NONE


# --- routing_demand.py -------------------------------------------------


@dataclass
class RoutingDemand:
    """Routing demand estimate for the design."""

    total_nets: int  # Total number of nets
    routable_nets: int  # Nets requiring routing (>1 pin)
    total_pins: int  # Total pin count

    # Demand by net class
    signal_nets: int  # Regular signal nets
    power_nets: int  # Power/ground nets
    diff_pair_nets: int  # Differential pair nets

    # Complexity metrics
    avg_pins_per_net: float  # Average fanout
    max_pins_per_net: int  # Maximum fanout

    @property
    def routing_complexity(self) -> float:
        """Simple routing complexity score (0-1)."""
        # Higher pin count and fanout = higher complexity
        if self.routable_nets == 0:
            return 0.0
        return min(1.0, (self.avg_pins_per_net / 10.0) * (self.routable_nets / 100.0))


def estimate_routing_demand(
    pcb: ParsedPCB,
) -> RoutingDemand:
    """
    Estimate routing demand from PCB design.

    Args:
        pcb: Parsed PCB from Stage 0

    Returns:
        RoutingDemand with demand estimates

    Example:
        >>> demand = estimate_routing_demand(pcb)
        >>> demand.routable_nets > 0
        True
    """
    total_nets = len(pcb.nets)
    total_pins = sum(len(comp.pins) for comp in pcb.components)

    # Count routable nets (need >1 pin)
    routable_nets = 0
    pin_counts = []

    # Classify nets
    signal_nets = 0
    power_nets = 0
    diff_pair_nets = 0

    # Handle both dict and list formats for nets
    # Type annotation says list[Net] but tests and some code paths use dict
    if isinstance(pcb.nets, dict):
        net_items = pcb.nets.items()
    else:
        # Assume list[Net]
        net_items = [(net.name, net) for net in pcb.nets]

    for net_name, _net in net_items:
        # Count pins in this net
        pin_count = sum(1 for comp in pcb.components for pin in comp.pins if pin.net == net_name)

        if pin_count > 1:
            routable_nets += 1
            pin_counts.append(pin_count)

            # Classify by name heuristics -- diagnostic/estimation only
            # (feeds a rough demand count, not a clearance/creepage/DRC or
            # plane-eligibility decision), but anchored anyway: a bare
            # "+"/"-" substring test matched almost every net on the
            # board (most net names contain a hyphenated pin suffix like
            # "-p2"), which silently inflated power_nets at the expense
            # of signal_nets. FIXED 2026-07-28, found completing the
            # audit scripts/check_net_classification.py's vocabulary
            # extension prompted -- see
            # docs/evidence/2026-07-28-zone-layer-classification-fix.md.
            net_upper = net_name.upper()
            if re.search(r"(?:^|_)(?:GND|VCC|VDD|VSS)(?:$|[\d_])", net_upper) or re.search(
                r"^[+-]", net_upper
            ):
                power_nets += 1
            elif any(x in net_upper for x in ["_P", "_N", "DP", "DN"]):
                diff_pair_nets += 1
            else:
                signal_nets += 1

    # Calculate statistics
    if pin_counts:
        avg_pins_per_net = sum(pin_counts) / len(pin_counts)
        max_pins_per_net = max(pin_counts)
    else:
        avg_pins_per_net = 0.0
        max_pins_per_net = 0

    return RoutingDemand(
        total_nets=total_nets,
        routable_nets=routable_nets,
        total_pins=total_pins,
        signal_nets=signal_nets,
        power_nets=power_nets,
        diff_pair_nets=diff_pair_nets,
        avg_pins_per_net=avg_pins_per_net,
        max_pins_per_net=max_pins_per_net,
    )


# --- placement_suggestions.py ------------------------------------------


@dataclass
class PlacementSuggestion:
    """A suggested placement adjustment."""

    component_id: str
    current_position: tuple[float, float]
    suggested_position: tuple[float, float]
    reason: str  # Why this move is suggested
    priority: float  # 0.0-1.0, higher = more important


@dataclass
class PlacementSuggestions:
    """Collection of placement suggestions."""

    suggestions: list[PlacementSuggestion]

    @property
    def suggestion_count(self) -> int:
        """Number of suggestions."""
        return len(self.suggestions)

    def get_high_priority_suggestions(self, threshold: float = 0.7) -> list[PlacementSuggestion]:
        """Get suggestions above priority threshold."""
        return [s for s in self.suggestions if s.priority >= threshold]


def generate_placement_suggestions(
    congestion_map: CongestionMap,
    component_positions: dict[str, tuple[float, float]] | None = None,
) -> PlacementSuggestions:
    """
    Generate placement suggestions based on congestion analysis.

    Proposes component movements to reduce congestion in critical regions.

    Args:
        congestion_map: Congestion analysis from F.2
        component_positions: Optional dict of component_id -> (x, y)

    Returns:
        PlacementSuggestions with proposed adjustments

    Example:
        >>> from temper_placer.router_v6.congestion_analysis import CongestionMap
        >>> congestion = CongestionMap(regions=[])
        >>> suggestions = generate_placement_suggestions(congestion)
        >>> suggestions.suggestion_count >= 0
        True
    """
    if component_positions is None:
        component_positions = {}

    suggestions = []

    # Analyze each congested region
    for region in congestion_map.regions:
        # Only generate suggestions for significant congestion
        if region.bottleneck_score < 0.5:
            continue

        # Find components in or near this region
        affected_components = _find_affected_components(
            region,
            component_positions,
        )

        # Generate movement suggestions for these components
        for comp_id, comp_pos in affected_components:
            # Suggest moving away from congested region
            suggested_pos = _calculate_suggested_position(
                comp_pos,
                region.center,
                region.severity.value,
            )

            # Calculate priority based on congestion severity
            priority = min(1.0, region.bottleneck_score * 1.2)

            suggestions.append(
                PlacementSuggestion(
                    component_id=comp_id,
                    current_position=comp_pos,
                    suggested_position=suggested_pos,
                    reason=f"Reduce {region.severity.value} congestion (score: {region.bottleneck_score:.2f})",
                    priority=priority,
                )
            )

    return PlacementSuggestions(suggestions=suggestions)


def _find_affected_components(
    region,
    component_positions: dict[str, tuple[float, float]],
) -> list[tuple[str, tuple[float, float]]]:
    """
    Find components affected by congested region.

    Args:
        region: Congested region
        component_positions: Component positions

    Returns:
        List of (component_id, position) tuples
    """
    affected = []

    for comp_id, comp_pos in component_positions.items():
        # Check if component is in or near the congested region
        dx = comp_pos[0] - region.center[0]
        dy = comp_pos[1] - region.center[1]
        distance = (dx**2 + dy**2) ** 0.5

        # Include components within 2x region radius
        if distance < region.radius * 2:
            affected.append((comp_id, comp_pos))

    return affected


def _calculate_suggested_position(
    current_pos: tuple[float, float],
    congestion_center: tuple[float, float],
    severity: str,
) -> tuple[float, float]:
    """
    Calculate suggested new position.

    Args:
        current_pos: Current component position
        congestion_center: Center of congested region
        severity: Congestion severity

    Returns:
        Suggested new position
    """
    # Move away from congestion center
    dx = current_pos[0] - congestion_center[0]
    dy = current_pos[1] - congestion_center[1]
    distance = (dx**2 + dy**2) ** 0.5

    if distance < 0.1:
        # Already at center, move arbitrarily
        dx, dy = 5.0, 0.0
        distance = 5.0

    # Normalize direction
    dx_norm = dx / distance
    dy_norm = dy / distance

    # Move distance based on severity
    move_distance = {
        "critical": 10.0,
        "high": 7.0,
        "medium": 5.0,
        "low": 3.0,
    }.get(severity, 3.0)

    # Calculate new position
    new_x = current_pos[0] + dx_norm * move_distance
    new_y = current_pos[1] + dy_norm * move_distance

    return (new_x, new_y)


# --- congestion_heatmap.py ---------------------------------------------


@dataclass
class CongestionHeatmap:
    """2D congestion map from routing analysis.

    Provides query interface for placement optimization:
    - High congestion areas should repel components
    - Enables RoutingCongestionLoss to steer placement
    """

    grid: np.ndarray  # 2D float array, values 0-1 (normalized congestion)
    cell_size: float  # mm per grid cell
    origin: tuple[float, float]  # world coordinates of grid origin

    @classmethod
    def from_router(cls, router: Any) -> CongestionHeatmap:
        """Build heatmap from router's congestion data.

        Combines:
        - present_congestion: current net overlap counts
        - history_cost: accumulated routing difficulty
        - conflict_locations: explicit conflict points

        Args:
            router: MazeRouter with routing results

        Returns:
            Normalized congestion heatmap
        """
        # Aggregate congestion across layers (max per cell)
        congestion_3d = router.present_congestion
        congestion_2d = np.max(congestion_3d, axis=2)

        # Add contribution from history costs (routing difficulty)
        history_3d = router.history_cost
        history_2d = np.max(history_3d, axis=2) - 1.0  # Base cost is 1.0

        # Combine (weighted sum)
        combined = congestion_2d + 0.5 * history_2d

        # Boost explicit conflict locations
        conflict_locs = router.get_conflict_locations()
        for loc in conflict_locs:
            gx = int((loc["world_x"] - router.origin[0]) / router.cell_size)
            gy = int((loc["world_y"] - router.origin[1]) / router.cell_size)
            if 0 <= gx < combined.shape[0] and 0 <= gy < combined.shape[1]:
                combined[gx, gy] += len(loc["nets"])  # More nets = worse

        # Normalize to 0-1
        max_val = np.max(combined)
        normalized = combined / max_val if max_val > 0 else combined

        return cls(
            grid=normalized.astype(np.float32),
            cell_size=router.cell_size,
            origin=router.origin,
        )

    def get_congestion_at(self, x: float, y: float) -> float:
        """Query congestion at world coordinate.

        Args:
            x, y: World coordinates in mm

        Returns:
            Congestion score 0-1 (0 = free, 1 = highly congested)
        """
        gx = int((x - self.origin[0]) / self.cell_size)
        gy = int((y - self.origin[1]) / self.cell_size)

        # Clamp to grid bounds
        gx = max(0, min(gx, self.grid.shape[0] - 1))
        gy = max(0, min(gy, self.grid.shape[1] - 1))

        return float(self.grid[gx, gy])

    def get_total_congestion(self) -> float:
        """Sum of all congestion values."""
        return float(np.sum(self.grid))

    def get_hotspots(
        self, threshold: float = 0.5, max_count: int = 10
    ) -> list[tuple[float, float, float]]:
        """Find high-congestion locations.

        Args:
            threshold: Minimum congestion to consider a hotspot
            max_count: Maximum hotspots to return

        Returns:
            List of (x, y, congestion) tuples in world coordinates
        """
        hotspots = []

        # Find cells above threshold
        for gx in range(self.grid.shape[0]):
            for gy in range(self.grid.shape[1]):
                val = self.grid[gx, gy]
                if val >= threshold:
                    world_x = gx * self.cell_size + self.origin[0]
                    world_y = gy * self.cell_size + self.origin[1]
                    hotspots.append((world_x, world_y, val))

        # Sort by congestion descending
        hotspots.sort(key=lambda h: h[2], reverse=True)

        return hotspots[:max_count]


# --- apply_suggestions.py ----------------------------------------------


@dataclass
class AppliedAdjustment:
    """A placement adjustment that was applied."""

    component_id: str
    original_position: tuple[float, float]
    suggested_position: tuple[float, float]
    applied_position: tuple[float, float]
    damping_factor: float  # How much suggestion was dampened (0.0-1.0)


@dataclass
class AdjustmentResult:
    """Result of applying placement adjustments."""

    adjustments: list[AppliedAdjustment]

    @property
    def adjustment_count(self) -> int:
        """Number of adjustments applied."""
        return len(self.adjustments)

    @property
    def total_movement(self) -> float:
        """Total movement distance across all adjustments (mm)."""
        total = 0.0
        for adj in self.adjustments:
            dx = adj.applied_position[0] - adj.original_position[0]
            dy = adj.applied_position[1] - adj.original_position[1]
            total += (dx**2 + dy**2) ** 0.5
        return total


def apply_suggestions_with_damping(
    suggestions: PlacementSuggestions,
    current_positions: dict[str, tuple[float, float]],
    damping_factor: float = 0.5,  # Conservative default
    min_priority_threshold: float = 0.5,
) -> AdjustmentResult:
    """
    Apply placement suggestions with damping to prevent oscillation.

    Damping reduces the magnitude of adjustments to ensure gradual
    convergence and avoid oscillation between states.

    Args:
        suggestions: Placement suggestions from F.3
        current_positions: Current component positions
        damping_factor: How much to dampen movements (0.0-1.0)
        min_priority_threshold: Minimum priority to apply

    Returns:
        AdjustmentResult with applied adjustments

    Example:
        >>> from temper_placer.router_v6.placement_suggestions import PlacementSuggestions
        >>> suggestions = PlacementSuggestions(suggestions=[])
        >>> positions = {}
        >>> result = apply_suggestions_with_damping(suggestions, positions)
        >>> result.adjustment_count >= 0
        True
    """
    adjustments = []

    # Filter for high-priority suggestions
    filtered_suggestions = [
        s for s in suggestions.suggestions if s.priority >= min_priority_threshold
    ]

    for suggestion in filtered_suggestions:
        comp_id = suggestion.component_id

        # Get current position
        current_pos = current_positions.get(comp_id)
        if current_pos is None:
            continue

        # Calculate damped position
        applied_pos = _calculate_damped_position(
            current_pos,
            suggestion.suggested_position,
            damping_factor,
        )

        adjustments.append(
            AppliedAdjustment(
                component_id=comp_id,
                original_position=current_pos,
                suggested_position=suggestion.suggested_position,
                applied_position=applied_pos,
                damping_factor=damping_factor,
            )
        )

    return AdjustmentResult(adjustments=adjustments)


def _calculate_damped_position(
    current: tuple[float, float],
    suggested: tuple[float, float],
    damping: float,
) -> tuple[float, float]:
    """
    Calculate damped position between current and suggested.

    Args:
        current: Current position
        suggested: Suggested position
        damping: Damping factor (0.0 = no movement, 1.0 = full movement)

    Returns:
        Damped position
    """
    # Linear interpolation with damping
    new_x = current[0] + (suggested[0] - current[0]) * damping
    new_y = current[1] + (suggested[1] - current[1]) * damping

    return (new_x, new_y)


def update_component_positions(
    current_positions: dict[str, tuple[float, float]],
    adjustment_result: AdjustmentResult,
) -> dict[str, tuple[float, float]]:
    """
    Update component positions based on applied adjustments.

    Args:
        current_positions: Current positions
        adjustment_result: Applied adjustments

    Returns:
        Updated positions dictionary
    """
    updated = current_positions.copy()

    for adjustment in adjustment_result.adjustments:
        updated[adjustment.component_id] = adjustment.applied_position

    return updated
