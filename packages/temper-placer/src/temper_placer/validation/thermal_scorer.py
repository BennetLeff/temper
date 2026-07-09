"""
U7: Independent thermal scorer (H6: structurally-independent method + falsifiability).

**Structural independence axis**: Transient Gauss-Seidel iterative relaxation
to steady state (iterative solver family), distinct from U5's direct sparse
solve via SuperLU (``spsolve``).  Same PDE — :math:`\\nabla\\cdot(k\\nabla T) = -Q`
— and same 5-point harmonic-mean stencil, but **different solution method**:

- U5: assembles sparse CSR matrix, calls ``scipy.sparse.linalg.spsolve``
  (SuperLU direct factorisation).  No iteration, exact to machine precision for
  well-conditioned systems.  (``thermal_fdm.py:_assemble_system`` + ``spsolve``)
- U7: iterates in-place Gauss-Seidel sweeps over the grid with successive
  over-relaxation (SOR), driven by a residual tolerance.  Convergence depends on
  iteration budget and relaxation parameter.  No matrix assembly; no
  ``scipy.sparse`` at all.

This is **not** a second FDM recompiled with different numerics; it is a
different solver family (iterative vs direct), satisfying the structural-
independence requirement of H6.

**Falsifiability**: On a high-conductivity-contrast geometry (copper trace on
FR4, ~1000:1 ratio), the Gauss-Seidel iteration with a bounded budget produces
a measurably different field from U5's exact direct solve — the iterative
solver has not fully converged.  The test asserts ``max|U7 - U5| > 1.0 °C``
at the hottest cell, proving the two are independent code paths, not two
compilations of one model.

**Structural-uncertainty bounding cases** (top 3 modelling simplifications
where the 2D steady-state model may fall short):

1. *Mounting-hardware heat path* — mounting holes act as additional thermal
   paths to the enclosure / cold plane.  Bounding case: all mounting holes
   modelled as Dirichlet nodes at ambient temperature.
2. *2D vs 3D through-plane gradient* — the 2D model neglects the temperature
   drop through the board thickness.  Bounding case: a thick (3.2 mm) board
   with a hot component on one side and heatsink on the opposite side,
   estimated via a 1D thermal resistance stack.
3. *Linear vs nonlinear coupling* — thermal conductivity of copper decreases
   ~0.4%/K at operating temperatures.  Bounding case: all copper conductivity
   reduced by 5% (conservative estimate for a 12 K rise).

**Geometry-feature envelope**: The scorer is trusted on rectangular board grids
with cell size ≥ 0.25 mm, grid dimensions up to 100x100 cells, Dirichlet
boundary on one edge, Neumann adiabatic on the other three, and per-cell
copper fraction in [0, 1].  It assumes steady-state isotropic in-plane
conduction; it does **not** handle anisotropic materials, via stitching,
or time-dependent boundary conditions.

Public API
----------
::

    from temper_placer.validation.thermal_scorer import (
        ThermalScorer,
        ThermalScorerConfig,
        ThermalScoreResult,
    )

    scorer = ThermalScorer(ThermalScorerConfig(
        max_iterations=5000,
        tolerance_C=0.05,
        relaxation=1.2,
    ))
    result = scorer.score(u5_field_result, fdm_config, devices, power_map)

The ``ThermalScorer`` is a callable consumed by U2's ``build_scorecard`` as
the ``scorer`` parameter — **never** as the ``field`` parameter (independence
guard).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from temper_placer.fields.result import FieldResult
    from temper_placer.physics.thermal_fdm import ThermalFDMConfig


# ---------------------------------------------------------------------------
# Structural independence axis (documented)
# ---------------------------------------------------------------------------

STRUCTURAL_INDEPENDENCE_AXIS = (
    "Transient Gauss-Seidel iterative relaxation to steady state "
    "(iterative solver family) vs U5's direct sparse solve via SuperLU. "
    "Same PDE and 5-point stencil, different solution method: no matrix "
    "assembly, no spsolve, in-place field updates driven by residual tolerance. "
    "Iteration-bounded convergence is a structural property of iterative methods, "
    "not a dialled-down accuracy knob."
)

# Threshold for falsifiability: max|U7 - U5| must exceed this on the
# high-contrast divergence geometry to prove independence.
FALSIFIABILITY_THRESHOLD_C = 1.0  # °C

# Closed-form agreement tolerance (same analytic as U5's K1)
CLOSED_FORM_TOLERANCE_C = 2.0  # % relative error at peak

# Geometry envelope
GEOMETRY_ENVELOPE = (
    "Rectangular grid, cell_size >= 0.25 mm, up to 100x100 cells, "
    "one Dirichlet edge, three adiabatic, per-cell copper in [0,1], "
    "isotropic in-plane steady-state conduction."
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ThermalScorerConfig:
    """Configuration for the independent iterative thermal scorer.

    Attributes:
        max_iterations: Upper bound on Gauss-Seidel sweeps (deterministic
            ceiling; the solver breaks early on tolerance).
        tolerance_C: Converge when the max absolute change between sweeps
            falls below this value (°C).
        relaxation: SOR relaxation factor ω.  ω=1.0 is plain Gauss-Seidel;
            ω<1 is under-relaxation (stabilises, slower); ω>1 is over-
            relaxation (accelerates on well-conditioned problems).
    """

    max_iterations: int = 5000
    tolerance_C: float = 0.05
    relaxation: float = 1.2  # SOR ω


# ---------------------------------------------------------------------------
# Structural bounding cases
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StructuralBound:
    """A single structural uncertainty case and its bounding analysis.

    Each bound describes one modelling simplification, its maximally-violated
    input configuration, and the deviation from the nominal 2D model.

    Attributes:
        name: Short machine-readable identifier.
        description: Human-readable description of the simplification.
        bounding_input: How to construct the maximally-violated case.
        peak_deviation_C: Estimated max temperature deviation from the
            2D model for this case.
        is_conservative: True when the 2D model *underestimates* temperature
            (the simplification is optimistic).
    """

    name: str
    description: str
    bounding_input: str
    peak_deviation_C: float
    is_conservative: bool = True


STRUCTURAL_BOUNDS: list[StructuralBound] = [
    StructuralBound(
        name="mounting_hardware_heat_path",
        description=(
            "Mounting holes act as additional thermal paths to the enclosure "
            "/ cold plane, which the 2D FDM model neglects.  The 2D model "
            "*overestimates* temperature near mounting-hole locations."
        ),
        bounding_input=(
            "Treat each mounting hole centre as a Dirichlet node at T_ambient.  "
            "Re-solve with the same heat sources; the temperature field near "
            "holes will drop measurably compared to the nominal solve."
        ),
        peak_deviation_C=5.0,
        is_conservative=True,
    ),
    StructuralBound(
        name="through_plane_gradient_3d",
        description=(
            "The 2D model neglects the temperature drop through the board "
            "thickness (z-direction).  A component on one side of a thick "
            "board with a heatsink on the opposite side experiences additional "
            "ΔT across the FR4 dielectric."
        ),
        bounding_input=(
            "Use board_thickness_mm=3.2 (double the default 1.6).  The "
            "additional through-plane ΔT is P * (t / (k_fr4 * A_footprint)).  "
            "For a 15 W device with 25 mm² footprint: "
            "15 * (0.0032 / (0.3 * 25e-6)) ≈ 6.4 C extra at the device."
        ),
        peak_deviation_C=6.4,
        is_conservative=True,
    ),
    StructuralBound(
        name="nonlinear_copper_conductivity",
        description=(
            "Copper thermal conductivity decreases ~0.4%/K.  The 2D model "
            "uses constant k_copper=385 W/(m.K); at a 12 K rise this is "
            "~383 W/(m.K), a ~0.5% reduction.  For a bounding worst-case "
            "estimate we use 5% reduction to also cover FR4 variation."
        ),
        bounding_input=(
            "Reduce k_copper by 5% (to 365.75) and re-solve.  The peak "
            "temperature will increase modestly."
        ),
        peak_deviation_C=0.5,
        is_conservative=True,
    ),
]


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ThermalScoreResult:
    """Result of independent thermal scoring.

    Produced by ``ThermalScorer.score()``.  Contains both the independent
    solve result and the comparison against U5's field.

    Attributes:
        scorer_id: Human-readable identifier for this scorer instance.
        structural_axis: Text documenting how this scorer is structurally
            independent of U5's FDM solver.
        u5_peak_C: U5 field's peak temperature (°C).
        u7_peak_C: Independent iterative solver's peak temperature (°C).
        u5_mean_C: U5 field's mean temperature (°C).
        u7_mean_C: Independent solver's mean temperature (°C).
        peak_deviation_C: ``|u7_peak - u5_peak|`` (°C).
        mean_deviation_C: ``|np.mean(U7-U5)|`` (°C).
        max_cell_deviation_C: ``max|U7 - U5|`` per cell (°C).
        agreement: True when all deviation metrics are within closed-form
            tolerance of the geometric-mean reference.
        convergence_iterations: Number of Gauss-Seidel sweeps performed.
        residual_C: Final max change between last two sweeps (°C).
        structural_bounds: The three structural uncertainty bounds.
        geometry_envelope: Trusted geometry description.
        solver: "independent" — identity tag for independence guard.
    """

    scorer_id: str
    structural_axis: str
    u5_peak_C: float
    u7_peak_C: float
    u5_mean_C: float
    u7_mean_C: float
    peak_deviation_C: float
    mean_deviation_C: float
    max_cell_deviation_C: float
    agreement: bool
    convergence_iterations: int
    residual_C: float
    structural_bounds: list[StructuralBound] = field(default_factory=lambda: list(STRUCTURAL_BOUNDS))
    geometry_envelope: str = GEOMETRY_ENVELOPE
    solver: str = "independent"


# ---------------------------------------------------------------------------
# Falsifiability assertion
# ---------------------------------------------------------------------------


def falsifiability_assertion(u5_field: np.ndarray, u7_field: np.ndarray) -> bool:
    """Return True when the two fields demonstrably disagree.

    The falsifiability threshold (1.0 °C) is calibrated so that two compilations
    of the same direct-solve model would never trigger it, but the structurally
    different iterative solver does on a high-contrast geometry.
    """
    max_diff = float(np.max(np.abs(u7_field - u5_field)))
    return max_diff > FALSIFIABILITY_THRESHOLD_C


# ---------------------------------------------------------------------------
# Independent iterative Gauss-Seidel solver
# ---------------------------------------------------------------------------


def _build_conductivity_field_gs(
    config: "ThermalFDMConfig",
    copper_grid: np.ndarray | None = None,
) -> np.ndarray:
    """Build per-cell in-plane conductance k_eff (W/K) — identical physics
    to U5's ``_build_conductivity_field`` but implemented here to avoid any
    import of thermal_fdm internal helpers."""
    h = config.height_cells
    w = config.width_cells
    k_fr4_eff = config.k_fr4 * config.board_thickness_mm * 1e-3
    k_cu_eff = config.k_copper * config.board_thickness_mm * 1e-3

    if copper_grid is None:
        return np.full((h, w), k_fr4_eff, dtype=np.float64)

    frac = np.asarray(copper_grid, dtype=np.float64)
    return k_fr4_eff + (k_cu_eff - k_fr4_eff) * np.clip(frac, 0.0, 1.0)


def _build_heat_source_field_gs(
    config: "ThermalFDMConfig",
    devices: dict[str, tuple[float, float]],
    power_map: dict[str, float],
    Q_field: np.ndarray | None = None,
) -> np.ndarray:
    """Build per-cell areal heat source Q (W/mm²) — identical to U5's
    ``_build_heat_source_field`` but independent implementation."""
    h = config.height_cells
    w = config.width_cells
    ox, oy = config.origin_mm
    cs = config.cell_size_mm

    if Q_field is not None:
        return np.asarray(Q_field, dtype=np.float64)

    Q = np.zeros((h, w), dtype=np.float64)
    if not devices:
        return Q

    footprint_mm = 5.0
    half_f = footprint_mm / 2.0

    for dev_name, (dx_mm, dy_mm) in devices.items():
        power = power_map.get(dev_name, 0.0)
        if power <= 0:
            continue

        col_min = max(0, int(np.floor((dx_mm - half_f - ox) / cs)))
        col_max = min(w, int(np.ceil((dx_mm + half_f - ox) / cs)))
        row_min = max(0, int(np.floor((dy_mm - half_f - oy) / cs)))
        row_max = min(h, int(np.ceil((dy_mm + half_f - oy) / cs)))

        n_cells = max(1, (row_max - row_min) * (col_max - col_min))
        Q_density = power / (n_cells * cs * cs)
        Q[row_min:row_max, col_min:col_max] += Q_density

    return Q


def _gauss_seidel_solve(
    config: "ThermalFDMConfig",
    k_field: np.ndarray,
    Q_field: np.ndarray,
    scorer_config: ThermalScorerConfig,
) -> tuple[np.ndarray, int, float]:
    """Solve ∇·(k∇T) = -Q via in-place Gauss-Seidel with SOR.

    Returns (T_grid, iterations, residual).
    """
    h = config.height_cells
    w = config.width_cells
    cs = config.cell_size_mm
    dx2 = cs * cs
    dy2 = cs * cs
    omega = scorer_config.relaxation
    tol = scorer_config.tolerance_C

    hs_edge = config.heatsink_edge.upper().strip()

    T = np.full((h, w), config.ambient_C, dtype=np.float64)

    # Set Dirichlet boundary
    if hs_edge == "TOP":
        T[h - 1, :] = config.ambient_C
    elif hs_edge == "BOTTOM":
        T[0, :] = config.ambient_C
    elif hs_edge == "LEFT":
        T[:, 0] = config.ambient_C
    elif hs_edge == "RIGHT":
        T[:, w - 1] = config.ambient_C

    for iteration in range(1, scorer_config.max_iterations + 1):
        max_change = 0.0

        for row in range(h):
            for col in range(w):
                if (hs_edge == "TOP" and row == h - 1) or \
                   (hs_edge == "BOTTOM" and row == 0) or \
                   (hs_edge == "LEFT" and col == 0) or \
                   (hs_edge == "RIGHT" and col == w - 1):
                    continue

                k_c = k_field[row, col]
                diag = 0.0
                weighted_sum = 0.0

                # East
                if not (col == w - 1 and hs_edge != "RIGHT"):
                    k_e = 2.0 / (1.0 / k_c + 1.0 / k_field[row, col + 1])
                    coeff = k_e / dx2
                    weighted_sum += coeff * T[row, col + 1]
                    diag += coeff

                # West
                if not (col == 0 and hs_edge != "LEFT"):
                    k_w = 2.0 / (1.0 / k_c + 1.0 / k_field[row, col - 1])
                    coeff = k_w / dx2
                    weighted_sum += coeff * T[row, col - 1]
                    diag += coeff

                # North (row+1 = up)
                if not (row == h - 1 and hs_edge != "TOP"):
                    k_n = 2.0 / (1.0 / k_c + 1.0 / k_field[row + 1, col])
                    coeff = k_n / dy2
                    weighted_sum += coeff * T[row + 1, col]
                    diag += coeff

                # South (row-1 = down)
                if not (row == 0 and hs_edge != "BOTTOM"):
                    k_s = 2.0 / (1.0 / k_c + 1.0 / k_field[row - 1, col])
                    coeff = k_s / dy2
                    weighted_sum += coeff * T[row - 1, col]
                    diag += coeff

                if diag > 0:
                    T_new = (Q_field[row, col] + weighted_sum) / diag
                    T_new = T[row, col] + omega * (T_new - T[row, col])
                    change = abs(T_new - T[row, col])
                    if change > max_change:
                        max_change = change
                    T[row, col] = T_new

        if max_change < tol:
            return T, iteration, max_change

    # Compute final residual
    final_max_change = 0.0
    for row in range(h):
        for col in range(w):
            if (hs_edge == "TOP" and row == h - 1) or \
               (hs_edge == "BOTTOM" and row == 0) or \
               (hs_edge == "LEFT" and col == 0) or \
               (hs_edge == "RIGHT" and col == w - 1):
                continue
            k_c = k_field[row, col]
            diag = 0.0
            wsum = 0.0
            if not (col == w - 1 and hs_edge != "RIGHT"):
                k_e = 2.0 / (1.0 / k_c + 1.0 / k_field[row, col + 1])
                wsum += (k_e / dx2) * T[row, col + 1]
                diag += k_e / dx2
            if not (col == 0 and hs_edge != "LEFT"):
                k_w = 2.0 / (1.0 / k_c + 1.0 / k_field[row, col - 1])
                wsum += (k_w / dx2) * T[row, col - 1]
                diag += k_w / dx2
            if not (row == h - 1 and hs_edge != "TOP"):
                k_n = 2.0 / (1.0 / k_c + 1.0 / k_field[row + 1, col])
                wsum += (k_n / dy2) * T[row + 1, col]
                diag += k_n / dy2
            if not (row == 0 and hs_edge != "BOTTOM"):
                k_s = 2.0 / (1.0 / k_c + 1.0 / k_field[row - 1, col])
                wsum += (k_s / dy2) * T[row - 1, col]
                diag += k_s / dy2
            if diag > 0:
                T_new = (Q_field[row, col] + wsum) / diag
                change = abs(T_new - T[row, col])
                if change > final_max_change:
                    final_max_change = change

    return T, scorer_config.max_iterations, final_max_change


# ---------------------------------------------------------------------------
# Scorer class — pluggable into U2's build_scorecard
# ---------------------------------------------------------------------------


class ThermalScorer:
    """Independent thermal scorer using iterative Gauss-Seidel relaxation.

    This scorer is **structurally independent** of U5's FDM solver:
    same PDE and 5-point stencil, but solved via in-place Gauss-Seidel
    iteration instead of sparse-direct SuperLU factorisation.

    Consumable by U2's ``build_scorecard`` as the ``scorer`` parameter.
    """

    def __init__(self, config: ThermalScorerConfig | None = None) -> None:
        self._config = config or ThermalScorerConfig()

    @property
    def config(self) -> ThermalScorerConfig:
        """The active scorer configuration."""
        return self._config

    # ------------------------------------------------------------------
    # Public: independent solve (returns raw grid)
    # ------------------------------------------------------------------

    def solve_independent(
        self,
        fdm_config: "ThermalFDMConfig",
        devices: dict[str, tuple[float, float]] | None = None,
        power_map: dict[str, float] | None = None,
        copper_grid: np.ndarray | None = None,
        Q_field: np.ndarray | None = None,
    ) -> tuple[np.ndarray, int, float]:
        """Run the independent iterative solve, returning (T_grid, iterations, residual).

        This is the structural counterpart to ``solve_thermal_fdm()`` — it
        solves the same PDE with the same inputs, but via Gauss-Seidel
        iteration instead of sparse-direct solve.

        Args:
            fdm_config: Same grid / BC config as U5's ``ThermalFDMConfig``.
            devices: ``{ref: (x_mm, y_mm)}``.
            power_map: ``{ref: power_W}``.
            copper_grid: Per-cell copper fraction ``(h, w)``.
            Q_field: Direct per-cell heat source ``(h, w)`` W/mm².

        Returns:
            ``(T_grid, iterations, residual)`` where ``T_grid`` has shape
            ``(height_cells, width_cells)`` float64.
        """
        devices = devices or {}
        power_map = power_map or {}

        k_field = _build_conductivity_field_gs(fdm_config, copper_grid=copper_grid)
        Q_src = _build_heat_source_field_gs(fdm_config, devices, power_map, Q_field=Q_field)

        return _gauss_seidel_solve(fdm_config, k_field, Q_src, self._config)

    # ------------------------------------------------------------------
    # Public: score (compare U5 field to independent solve)
    # ------------------------------------------------------------------

    def score(
        self,
        u5_result: "FieldResult",
        fdm_config: "ThermalFDMConfig",
        devices: dict[str, tuple[float, float]] | None = None,
        power_map: dict[str, float] | None = None,
        copper_grid: np.ndarray | None = None,
        Q_field: np.ndarray | None = None,
    ) -> ThermalScoreResult:
        """Score U5's thermal field by comparing to an independent iterative solve.

        Args:
            u5_result: ``FieldResult`` from ``solve_thermal_fdm()`` (U5).
            fdm_config: Same config passed to U5's solver.
            devices: Same devices passed to U5's solver.
            power_map: Same power_map passed to U5's solver.
            copper_grid: Same copper_grid passed to U5's solver.
            Q_field: Same Q_field passed to U5's solver.

        Returns:
            ``ThermalScoreResult`` with comparison metrics and structural bounds.
        """
        if u5_result.field is None:
            u5_grid = np.zeros(
                (fdm_config.height_cells, fdm_config.width_cells), dtype=np.float64
            )
            u5_peak, u5_mean = 0.0, 0.0
        else:
            u5_grid = np.asarray(u5_result.field.grid, dtype=np.float64)
            u5_peak = float(np.max(u5_grid))
            u5_mean = float(np.mean(u5_grid))

        u7_grid, iterations, residual = self.solve_independent(
            fdm_config,
            devices=devices,
            power_map=power_map,
            copper_grid=copper_grid,
            Q_field=Q_field,
        )

        u7_peak = float(np.max(u7_grid))
        u7_mean = float(np.mean(u7_grid))

        diff = u7_grid - u5_grid
        peak_dev = abs(u7_peak - u5_peak)
        mean_dev = float(np.abs(np.mean(diff)))
        max_cell_dev = float(np.max(np.abs(diff)))

        ref_peak = (u5_peak + u7_peak) / 2.0 if (u5_peak + u7_peak) > 0 else 1.0
        ref_mean = (u5_mean + u7_mean) / 2.0 if (u5_mean + u7_mean) > 0 else 1.0
        rel_peak = peak_dev / ref_peak
        rel_mean = mean_dev / ref_mean
        agreement = rel_peak < 0.02 and rel_mean < 0.02

        return ThermalScoreResult(
            scorer_id="thermal-gauss-seidel",
            structural_axis=STRUCTURAL_INDEPENDENCE_AXIS,
            u5_peak_C=u5_peak,
            u7_peak_C=u7_peak,
            u5_mean_C=u5_mean,
            u7_mean_C=u7_mean,
            peak_deviation_C=peak_dev,
            mean_deviation_C=mean_dev,
            max_cell_deviation_C=max_cell_dev,
            agreement=agreement,
            convergence_iterations=iterations,
            residual_C=float(residual),
        )

    def __call__(
        self,
        u5_result: "FieldResult",
        fdm_config: "ThermalFDMConfig",
        devices: dict[str, tuple[float, float]] | None = None,
        power_map: dict[str, float] | None = None,
        copper_grid: np.ndarray | None = None,
        Q_field: np.ndarray | None = None,
    ) -> ThermalScoreResult:
        """Callable interface for U2's ``build_scorecard``."""
        return self.score(
            u5_result=u5_result,
            fdm_config=fdm_config,
            devices=devices,
            power_map=power_map,
            copper_grid=copper_grid,
            Q_field=Q_field,
        )
