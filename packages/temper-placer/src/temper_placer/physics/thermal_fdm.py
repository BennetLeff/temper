"""
Thermal FDM field solver (U5): finite-difference thermal solve of
:math:`\\nabla\\cdot(k\\nabla T) = -Q` over the board grid.

Produces a ``CostField`` wrapped in a ``FieldResult`` for downstream
A* routing cost injection.

Geometry-faithful, deterministic (sparse-direct solve via SuperLU), and
fail-closed (UNMEASURED on any solve failure, never a silent flat field).

Distinct from ``thermal_potential.py`` (kernel superposition heuristic)
and ``thermal.py`` (lumped-parameter Tj model).  This module reads real
copper + per-device power to produce a 2-D temperature field.

Copper reconstruction follows the pattern in ``loop_area.py``: traces
from a routed PCB are rasterised to fractional copper coverage per
cell, avoiding the centreline-disconnection bug.  At placement-time
(with no routing yet), a guessed copper grid can be supplied instead.

Public API (consumed by U7/U8/U9)
----------------------------------
.. code-block:: python

    from temper_placer.physics.thermal_fdm import (
        ThermalFDMConfig,
        solve_thermal_fdm,
    )

    result: FieldResult = solve_thermal_fdm(
        config=ThermalFDMConfig(
            cell_size_mm=0.5,
            origin_mm=(0.0, 0.0),
            height_cells=100,
            width_cells=200,
            ambient_C=40.0,
            heatsink_edge="TOP",
        ),
        devices={"Q1": (25.0, 10.0), "Q2": (35.0, 10.0)},
        power_map={"Q1": 15.0, "Q2": 7.5},
        copper_grid=my_copper_fraction_array,   # optional: placement-time crude
        traces=routed_trace_segments,           # optional: routing-time real copper
    )
    if result.is_usable:
        cost_field: CostField = result.field       # (H, W) float64
        routing_input = result.to_cost_field_input()  # CostFieldInput (flat float32)
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    import scipy

    from temper_placer.fields.result import FieldResult


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ThermalFDMConfig:
    """Configuration for the thermal FDM solver.

    The grid parameters (cell_size_mm, origin_mm, height_cells, width_cells)
    must match the A* occupancy grid so the resulting ``CostField`` aligns
    1:1 for downstream injection.
    """

    cell_size_mm: float
    origin_mm: tuple[float, float]
    height_cells: int
    width_cells: int

    ambient_C: float = 40.0
    heatsink_edge: str = "TOP"  # "TOP" | "BOTTOM" | "LEFT" | "RIGHT"

    # Thermal properties
    board_thickness_mm: float = 1.6
    k_fr4: float = 0.3  # W/(m·K) — FR4 through-plane conductivity
    k_copper: float = 385.0  # W/(m·K) — copper conductivity

    # Budget constraints
    max_cells: int = 2500
    target_solve_time_s: float = 2.0


# ---------------------------------------------------------------------------
# Trace rasterisation (copper reconstruction)
# ---------------------------------------------------------------------------


def _trace_to_cell_coverage(
    trace_start: tuple[float, float],
    trace_end: tuple[float, float],
    trace_width_mm: float,
    origin_mm: tuple[float, float],
    cell_size_mm: float,
    height_cells: int,
    width_cells: int,
) -> np.ndarray:
    """Rasterise a single trace segment to fractional copper coverage per cell.

    Uses anti-aliased line rasterisation: each cell's coverage is the
    fraction of the cell area overlapped by the fat trace (line of given
    width), avoiding the naive centreline rasterisation bug that creates
    grid-disconnected cells for diagonal traces.

    Returns a ``(height_cells, width_cells)`` float64 array with values
    in [0, 1] that can be accumulated across multiple traces.  Computed
    in the ``temper-thermal`` Rust crate with the exact f64 operation
    order of the former pure-Python supersampling loop.
    """
    import temper_thermal as _tt

    x0, y0 = trace_start
    x1, y1 = trace_end
    ox, oy = origin_mm
    raw = _tt.trace_to_cell_coverage(
        x0,
        y0,
        x1,
        y1,
        trace_width_mm,
        ox,
        oy,
        cell_size_mm,
        height_cells,
        width_cells,
    )
    return np.frombuffer(raw, dtype=np.float64).reshape((height_cells, width_cells)).copy()


def _point_to_segment_distance(
    px: float,
    py: float,
    ax: float,
    ay: float,
    bx: float,
    by: float,
) -> float:
    """Squared Euclidean distance from point to line segment AB."""
    dx = bx - ax
    dy = by - ay
    seg_len_sq = dx * dx + dy * dy

    if seg_len_sq < 1e-18:
        return float(np.sqrt((px - ax) ** 2 + (py - ay) ** 2))

    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / seg_len_sq))
    proj_x = ax + t * dx
    proj_y = ay + t * dy
    return float(np.sqrt((px - proj_x) ** 2 + (py - proj_y) ** 2))


def _build_conductivity_field(
    config: ThermalFDMConfig,
    copper_grid: np.ndarray | None = None,
    traces: list | None = None,
) -> np.ndarray:
    """Build per-cell effective in-plane conductance k_eff (W/K).

    k_eff = (copper_fraction * k_copper + (1-fraction) * k_fr4) * thickness

    When *traces* is provided, they are rasterised to build *copper_grid*
    internally (accumulated, clipped to [0, 1]).
    """
    h = config.height_cells
    w = config.width_cells
    k_fr4_eff = config.k_fr4 * config.board_thickness_mm * 1e-3  # W/K per square
    k_cu_eff = config.k_copper * config.board_thickness_mm * 1e-3

    if copper_grid is None and traces is None:
        return np.full((h, w), k_fr4_eff, dtype=np.float64)

    if copper_grid is not None:
        frac = np.asarray(copper_grid, dtype=np.float64)
    else:
        frac = np.zeros((h, w), dtype=np.float64)

    if traces is not None:
        for t in traces:
            if hasattr(t, "start") and hasattr(t, "end"):
                sx, sy = float(t.start[0]), float(t.start[1])
                ex, ey = float(t.end[0]), float(t.end[1])
                tw = getattr(t, "width", 0.5)  # default 0.5mm trace width
            elif isinstance(t, (list, tuple)) and len(t) >= 4:
                sx, sy, ex, ey = float(t[0]), float(t[1]), float(t[2]), float(t[3])
                tw = float(t[4]) if len(t) >= 5 else 0.5
            else:
                continue
            cell_cov = _trace_to_cell_coverage(
                (sx, sy),
                (ex, ey),
                tw,
                config.origin_mm,
                config.cell_size_mm,
                h,
                w,
            )
            frac = np.minimum(1.0, frac + cell_cov)

    return k_fr4_eff + (k_cu_eff - k_fr4_eff) * np.clip(frac, 0.0, 1.0)


# ---------------------------------------------------------------------------
# Heat source field
# ---------------------------------------------------------------------------


def _build_heat_source_field(
    config: ThermalFDMConfig,
    devices: dict[str, tuple[float, float]],
    power_map: dict[str, float],
    Q_field: np.ndarray | None = None,
) -> np.ndarray:
    """Build per-cell areal heat source Q (W/mm²).

    Each device's power is spread over a footprint of ``footprint_mm``
    (default 5x5 mm).  If *Q_field* is provided directly, it is used
    as-is (for uniform-source test cases).
    """
    h = config.height_cells
    w = config.width_cells
    ox, oy = config.origin_mm
    cs = config.cell_size_mm

    if Q_field is not None:
        return np.asarray(Q_field, dtype=np.float64)

    Q = np.zeros((h, w), dtype=np.float64)
    if not devices:
        return Q

    footprint_mm = 5.0  # mm per side, square footprint
    half_f = footprint_mm / 2.0

    for dev_name, (dx_mm, dy_mm) in devices.items():
        power = power_map.get(dev_name, 0.0)
        if power <= 0:
            continue

        # Device bounding box in grid coordinates
        col_min = max(0, int(np.floor((dx_mm - half_f - ox) / cs)))
        col_max = min(w, int(np.ceil((dx_mm + half_f - ox) / cs)))
        row_min = max(0, int(np.floor((dy_mm - half_f - oy) / cs)))
        row_max = min(h, int(np.ceil((dy_mm + half_f - oy) / cs)))

        n_cells = max(1, (row_max - row_min) * (col_max - col_min))
        Q_density = power / (n_cells * cs * cs)  # W/mm²
        Q[row_min:row_max, col_min:col_max] += Q_density

    return Q


# ---------------------------------------------------------------------------
# FDM assembly and solve
# ---------------------------------------------------------------------------


def _is_neumann_boundary(
    row: int,
    col: int,
    direction: str,  # "north", "south", "east", "west"
    config: ThermalFDMConfig,
) -> bool:
    """Return True if the neighbour in *direction* would cross a
    Neumann (adiabatic) board edge, i.e. no connection should be made
    across this boundary.  The heatsink edge is Dirichlet, NOT Neumann —
    interior cells connect to it."""
    h = config.height_cells
    w = config.width_cells
    hs_edge = config.heatsink_edge.upper().strip()

    if direction == "north" and row == h - 1:
        return hs_edge != "TOP"
    if direction == "south" and row == 0:
        return hs_edge != "BOTTOM"
    if direction == "west" and col == 0:
        return hs_edge != "LEFT"
    if direction == "east" and col == w - 1:
        return hs_edge != "RIGHT"
    return False


def _is_heatsink_boundary_face(
    row: int,
    col: int,
    direction: str,
    config: ThermalFDMConfig,
) -> bool:
    """Return True if the face in *direction* is the outer boundary
    in the heatsink direction (Dirichlet face, not Neumann)."""
    h = config.height_cells
    w = config.width_cells
    hs = config.heatsink_edge.upper().strip()
    if direction == "north" and row == h - 1 and hs == "TOP":
        return True
    if direction == "south" and row == 0 and hs == "BOTTOM":
        return True
    if direction == "east" and col == w - 1 and hs == "RIGHT":
        return True
    return bool(direction == "west" and col == 0 and hs == "LEFT")


def _assemble_system(
    config: ThermalFDMConfig,
    k_field: np.ndarray,
    Q_field: np.ndarray,
    h_field: np.ndarray | None = None,
) -> tuple[scipy.sparse.csr_matrix, np.ndarray]:
    """Assemble the sparse linear system A·T = b for the FDM discretisation.

    Uses the 5-point stencil with harmonic-mean interface conductivity
    for material boundaries.  Dirichlet face term at the heatsink edge
    (boundary-aligned, 2nd-order), Neumann adiabatic (zero-flux) at all
    other edges.

    When *h_field* is provided, adds a per-cell vertical sink term
    ``h(T - T_amb)`` for through-plane heat removal (heatsink path).
    The sink adds ``h_cell`` to the diagonal and ``h_cell * T_amb`` to
    the RHS, preserving symmetry, SPD, and the M-matrix property
    (positive diagonal addition improves diagonal dominance).
    When ``h_field`` is None or all-zero, behaviour is identical to
    the pure in-plane conduction solve.

    Assembly is computed in the ``temper-thermal`` Rust crate
    (``packages/temper-thermal/src/fdm.rs``) with the exact f64
    operation order of the former pure-Python loop; the sparse matrix
    is rebuilt here and the solve stays in scipy (SuperLU).
    """
    import temper_thermal as _tt
    from scipy.sparse import coo_matrix

    h = config.height_cells
    w = config.width_cells
    n = h * w

    rows, cols, values, b = _tt.assemble_system_py(
        np.ascontiguousarray(k_field, dtype=np.float64).tobytes(),
        np.ascontiguousarray(Q_field, dtype=np.float64).tobytes(),
        None
        if h_field is None
        else np.ascontiguousarray(h_field, dtype=np.float64).tobytes(),
        h,
        w,
        config.ambient_C,
        config.cell_size_mm,
        config.heatsink_edge.upper().strip(),
    )
    A = coo_matrix((values, (rows, cols)), shape=(n, n), dtype=np.float64).tocsr()
    return A, np.asarray(b, dtype=np.float64)


# ---------------------------------------------------------------------------
# Matrix inspection (for verification)
# ---------------------------------------------------------------------------


def get_system_matrix(
    config: ThermalFDMConfig,
    copper_grid: np.ndarray | None = None,
    traces: list | None = None,
    h_field: np.ndarray | None = None,
) -> scipy.sparse.csr_matrix:
    """Return the assembled system matrix A for the isotropic FDM discretisation.

    This is a utility for verifying matrix-class properties (symmetry,
    positive-definiteness, M-matrix sign pattern).  It builds the
    conductivity field from *config* and *copper_grid*/*traces*, assembles
    the sparse CSR system matrix, and returns it without solving.

    Args:
        config: Grid geometry and boundary conditions.
        copper_grid: ``(height_cells, width_cells)`` per-cell copper
            coverage fraction in [0, 1].
        traces: Optional routed trace segments.
        h_field: Optional per-cell vertical conductance ``(H, W)`` in
            ``W/(K·mm²)`` for through-plane heat removal (#141).

    Returns:
        The ``scipy.sparse.csr_matrix`` system matrix A.
    """
    k_field = _build_conductivity_field(config, copper_grid=copper_grid, traces=traces)
    h, w = config.height_cells, config.width_cells
    Q_dummy = np.zeros((h, w), dtype=np.float64)
    A, _ = _assemble_system(config, k_field, Q_dummy, h_field=h_field)
    return A


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def solve_thermal_fdm(
    config: ThermalFDMConfig,
    devices: dict[str, tuple[float, float]] | None = None,
    power_map: dict[str, float] | None = None,
    copper_grid: np.ndarray | None = None,
    traces: list | None = None,
    Q_field: np.ndarray | None = None,
    h_field: np.ndarray | None = None,
) -> FieldResult:
    """Solve :math:`\\nabla\\cdot(k\\nabla T) - h(T - T_\\mathrm{amb}) = -Q`
    on the board grid.

    When *h_field* is provided, a per-cell vertical sink models
    through-plane heat removal (e.g. junction→case→sink→ambient).
    The units of ``h_field`` are ``W/(K·mm²)`` (per-area vertical
    conductance).  When ``h_field`` is ``None``, the solve reduces to
    pure in-plane conduction.

    Args:
        config: Grid geometry, boundary conditions, and budget limits.
        devices: ``{component_ref: (x_mm, y_mm)}`` mapping for heat sources.
        power_map: ``{component_ref: power_W}`` — per-device dissipation.
        copper_grid: ``(height_cells, width_cells)`` per-cell copper coverage
            fraction in [0, 1].  Used at placement-time when no routing exists.
            Ignored when *traces* is also given (traces take priority for
            rasterisation, though any pre-existing coverage is accumulated).
        traces: Routed trace segments from a parsed ``.kicad_pcb``.  Each
            element must have ``.start`` / ``.end`` attributes or be a
            ``(x1, y1, x2, y2, [width])`` tuple.  Rasterised to fractional
            copper coverage per cell (routing-time solve).
        Q_field: Direct per-cell heat source (W/mm²).  When provided,
            *devices*/*power_map* are ignored.  Used for uniform-source
            test cases.
        h_field: Optional per-cell vertical conductance ``(H, W)`` in
            ``W/(K·mm²)`` for through-plane heat removal (#141).

    Returns:
        ``FieldResult`` with:
        - ``CLEAN`` status and a ``CostField`` grid on success.
        - ``UNMEASURED`` status and ``field=None`` when the grid exceeds
          ``max_cells`` or the linear solve fails.
    """
    from temper_placer.fields.field import CostField
    from temper_placer.fields.result import FieldResult
    from temper_placer.placer.cp_sat.gates import GateResult, GateStatus

    n_cells = config.height_cells * config.width_cells
    if n_cells > config.max_cells:
        return FieldResult(
            gate_result=GateResult(
                status=GateStatus.UNMEASURED,
                error_message=(
                    f"Grid size {n_cells} ({config.height_cells}x{config.width_cells}) "
                    f"exceeds max_cells={config.max_cells}"
                ),
            ),
            field=None,
        )

    devices = devices or {}
    power_map = power_map or {}

    # Build conductivity and heat source fields
    k_field = _build_conductivity_field(config, copper_grid=copper_grid, traces=traces)
    Q_src = _build_heat_source_field(config, devices, power_map, Q_field=Q_field)

    # Assemble linear system
    A, b = _assemble_system(config, k_field, Q_src, h_field=h_field)

    # Direct deterministic solve via SuperLU
    from scipy.sparse.linalg import spsolve

    t_start = time.monotonic()
    try:
        T_flat = spsolve(A, b)
    except Exception as exc:
        return FieldResult(
            gate_result=GateResult(
                status=GateStatus.UNMEASURED,
                error_message=f"Linear solve failed: {exc}",
            ),
            field=None,
        )
    t_elapsed = time.monotonic() - t_start

    if t_elapsed > config.target_solve_time_s:
        return FieldResult(
            gate_result=GateResult(
                status=GateStatus.UNMEASURED,
                error_message=(
                    f"Solve time {t_elapsed:.2f}s exceeds target {config.target_solve_time_s}s"
                ),
            ),
            field=None,
        )

    T_grid = T_flat.reshape(config.height_cells, config.width_cells)

    return FieldResult(
        gate_result=GateResult(status=GateStatus.CLEAN),
        field=CostField(
            grid=T_grid,
            cell_size_mm=config.cell_size_mm,
            origin_mm=config.origin_mm,
        ),
    )
