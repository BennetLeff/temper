"""
U7: Independent thermal scorer (H6: **model**-independent method + falsifiability).

**Model independence axis**: Convective-boundary 2-D finite-difference model
with Robin (convective) boundary conditions on the three non-heatsink edges,
solved via sparse-direct ``spsolve`` (SuperLU).  U5 treats those edges as
adiabatic Neumann — a genuinely different physical model, not just a different
solver of the same PDE.

This scorer assembles the same 5-point harmonic-mean stencil as U5 for the
in-plane conduction :math:`\\nabla\\cdot(k\\nabla T) = -Q`, but **adds a
convective term** ``h \\cdot (T - T_{\\text{amb}})`` at the three boundary edges
the heatsink does NOT cover.  U5's adiabatic-Neumann boundary is the special
case ``h = 0``, so the two models genuinely differ in their boundary physics.

- U5: 5-point stencil, Dirichlet at heatsink edge, adiabatic Neumann
  (zero-flux) at the other three edges → sparse-direct ``spsolve``
  (``thermal_fdm.py:_assemble_system`` + ``spsolve``)
- U7: 5-point stencil, Dirichlet at heatsink edge, **convective (Robin)**
  BC at the other three edges → sparse-direct ``spsolve``
  (``_convective_fdm_solve``)

This is **model independence**, not just solver independence.  Two different
numerical-discretisation approaches to the same ``h=0`` PDE would collapse to
the same ``k_eff`` approximation; the convective-boundary variant is a
different *physical* model, and the falsifiability test asserts disagreement
on a geometry where convection matters.

**Falsifiability**: On a high-Biot-number geometry (small board, pure FR4,
point source) where edge convection is thermally significant, U7's
temperature field is measurably COOLER than U5's because heat can leave
through the three convective edges (U5 is adiabatic there).  The test
asserts ``max|U7 - U5| > FALSIFIABILITY_THRESHOLD_C``, which cannot happen
if both models share the same boundary physics.

**Geometry-feature envelope**: The scorer is trusted on rectangular board
grids with cell size >= 0.25 mm, grid dimensions up to 100x100 cells,
Dirichlet boundary on one edge, Robin (convective) on the other three,
and per-cell copper fraction in [0, 1].  It assumes steady-state isotropic
in-plane conduction; it does **not** handle anisotropic materials, via
stitching, or time-dependent boundary conditions.

**Determinism**: The sparse-direct solve via SuperLU is deterministic
(same inputs → bit-identical output; no RNG, no iteration budget).

Public API
----------
::

    from temper_placer.validation.thermal_scorer import (
        ThermalScorer,
        ThermalScorerConfig,
        ThermalScoreResult,
    )

    scorer = ThermalScorer(ThermalScorerConfig(h=10.0))
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
    import scipy

    from temper_placer.fields.result import FieldResult
    from temper_placer.physics.thermal_fdm import ThermalFDMConfig


# ---------------------------------------------------------------------------
# Convection coefficient — physically grounded fixed value
# ---------------------------------------------------------------------------

# Natural convection heat transfer coefficient for still air, horizontal
# plate (heated surface facing up) or vertical plate.  Standard textbook
# range: 2--25 W/(m^2.K) (Incropera & DeWitt, "Fundamentals of Heat and
# Mass Transfer", Table 1-4, typical values for natural convection in
# gases).  We use 10 W/(m^2.K) as a conservative midpoint estimate.
#
# This is a FIXED value, never tuned to pass a test.  Changing it would
# require a commensurate update to the falsifiability threshold.
CONVECTION_COEFFICIENT_H_W_PER_M2K: float = 10.0

# ---------------------------------------------------------------------------
# Physical-model assumptions: shared vs independent
# ---------------------------------------------------------------------------

# Assumptions shared with U5 (the convective boundary is the ONLY point of
# model divergence).  Shared systematic bias is a *stated limitation*: the
# falsifiability test cannot rule out errors that affect both models
# identically.
SHARED_ASSUMPTIONS: list[str] = [
    "Effective interface conductivity (harmonic mean at copper/FR4 boundaries)",
    "Conduction-only in-plane (no internal convection or radiation)",
    "Vias treated as bulk material (no explicit via thermal modelling)",
    "No 3-D through-plane temperature gradient (2D lumped approximation)",
    "Steady-state conduction (no transient or time-dependent BCs)",
    "Isotropic per-cell conductivity (k_eff = k_material * thickness)",
    "Linear superposition of multiple heat sources",
    "Cell size >= 0.25 mm, grid up to 100x100 cells",
]

# Assumptions that differ between U5 and U7 (the model-independence axis).
INDEPENDENT_ASSUMPTIONS: list[str] = [
    "U7: Convective (Robin) boundary at three non-heatsink edges (h=10 W/(m^2.K))",
    "U5: Adiabatic (Neumann, zero-flux) boundary at three non-heatsink edges",
]

# ---------------------------------------------------------------------------
# Structural independence axis (documented)
# ---------------------------------------------------------------------------

STRUCTURAL_INDEPENDENCE_AXIS = (
    "Convective-boundary 2-D FDM with Robin BC on three non-heatsink edges "
    "(h=10 W/(m^2.K), sparse-direct spsolve) vs U5's adiabatic-Neumann 2-D FDM "
    "with Dirichlet only at the heatsink edge (sparse-direct spsolve).  Same "
    "5-point harmonic-mean stencil and same k_eff reconstruction, but genuinely "
    "different boundary physics: U5 assumes zero-flux at the three non-Dirichlet "
    "edges (h=0 limit), U7 adds a convective heat-loss term.  This is model "
    "independence, not just solver independence — two different solver families "
    "on the same h=0 PDE would collapse to the same k_eff approximation."
)

# Threshold for falsifiability: max|U7 - U5| must exceed this on the
# high-Biot-number divergence geometry to prove model independence.
FALSIFIABILITY_THRESHOLD_C = 1.0  # deg-C

# Closed-form agreement tolerance (same analytic as U5's K1)
CLOSED_FORM_TOLERANCE_C = 2.0  # % relative error at peak

# Geometry envelope
GEOMETRY_ENVELOPE = (
    "Rectangular grid, cell_size >= 0.25 mm, up to 100x100 cells, "
    "one Dirichlet (heatsink) edge, three Robin (convective) edges, "
    "per-cell copper in [0,1], isotropic in-plane steady-state conduction."
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ThermalScorerConfig:
    """Configuration for the independent convective-boundary thermal scorer.

    The scorer uses a sparse-direct linear solve (SuperLU) with the
    convective boundary term ``h * (T - T_amb)`` added at the three
    non-heatsink edges.

    Attributes:
        h: Convection heat transfer coefficient (W/(m^2.K)).  Physically
            grounded fixed value; documented in ``CONVECTION_COEFFICIENT_H``.
        max_iterations: Retained for backward compatibility; the convective
            FDM uses direct solve (no iteration).
        tolerance_C: Retained for backward compatibility; unused.
        relaxation: Retained for backward compatibility; unused.
    """

    h: float = CONVECTION_COEFFICIENT_H_W_PER_M2K
    max_iterations: int = 5000  # backward compat; unused in convective model
    tolerance_C: float = 0.05  # backward compat; unused in convective model
    relaxation: float = 1.2  # backward compat; unused in convective model


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
            "delta-T across the FR4 dielectric."
        ),
        bounding_input=(
            "Use board_thickness_mm=3.2 (double the default 1.6).  The "
            "additional through-plane delta-T is P * (t / (k_fr4 * A_footprint)).  "
            "For a 15 W device with 25 mm^2 footprint: "
            "15 * (0.0032 / (0.3 * 25e-6)) approx 6.4 deg-C extra at the device."
        ),
        peak_deviation_C=6.4,
        is_conservative=True,
    ),
    StructuralBound(
        name="nonlinear_copper_conductivity",
        description=(
            "Copper thermal conductivity decreases approx 0.4%/K.  The 2D model "
            "uses constant k_copper=385 W/(m.K); at a 12 K rise this is "
            "approx 383 W/(m.K), a approx 0.5% reduction.  For a bounding worst-case "
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
        u5_peak_C: U5 field's peak temperature (deg-C).
        u7_peak_C: Independent solver's peak temperature (deg-C).
        u5_mean_C: U5 field's mean temperature (deg-C).
        u7_mean_C: Independent solver's mean temperature (deg-C).
        peak_deviation_C: ``|u7_peak - u5_peak|`` (deg-C).
        mean_deviation_C: ``|np.mean(U7-U5)|`` (deg-C).
        max_cell_deviation_C: ``max|U7 - U5|`` per cell (deg-C).
        agreement: True when all deviation metrics are within closed-form
            tolerance of the geometric-mean reference.
        convergence_iterations: 0 (direct solve; retained for B/C).
        residual_C: 0.0 (exact to machine precision; retained for B/C).
        structural_bounds: The three structural uncertainty bounds.
        geometry_envelope: Trusted geometry description.
        solver: "independent" — identity tag for independence guard.
        shared_assumptions: Physical-model assumptions shared with U5.
        independent_assumptions: Physical-model assumptions that differ.
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
    structural_bounds: list[StructuralBound] = field(
        default_factory=lambda: list(STRUCTURAL_BOUNDS)
    )
    geometry_envelope: str = GEOMETRY_ENVELOPE
    solver: str = "independent"
    shared_assumptions: list[str] = field(default_factory=lambda: list(SHARED_ASSUMPTIONS))
    independent_assumptions: list[str] = field(
        default_factory=lambda: list(INDEPENDENT_ASSUMPTIONS)
    )


# ---------------------------------------------------------------------------
# Falsifiability assertion
# ---------------------------------------------------------------------------


def falsifiability_assertion(u5_field: np.ndarray, u7_field: np.ndarray) -> bool:
    """Return True when the two fields demonstrably disagree.

    The falsifiability threshold (1.0 deg-C) is calibrated so that numerical
    noise from two runs of the same solver would never trigger it, but the
    genuinely different convective-boundary model does on a high-Biot-number
    geometry where edge convection is thermally significant.
    """
    max_diff = float(np.max(np.abs(u7_field - u5_field)))
    return max_diff > FALSIFIABILITY_THRESHOLD_C


# ---------------------------------------------------------------------------
# Convective-boundary FDM solver (model-independent from U5)
# ---------------------------------------------------------------------------


def _is_heatsink_edge_cell(
    row: int,
    col: int,
    height_cells: int,
    width_cells: int,
    heatsink_edge: str,
) -> bool:
    """Return True if (row, col) lies on the declared heatsink edge."""
    edge = heatsink_edge.upper().strip()
    if edge == "TOP":
        return row == height_cells - 1
    elif edge == "BOTTOM":
        return row == 0
    elif edge == "LEFT":
        return col == 0
    elif edge == "RIGHT":
        return col == width_cells - 1
    return False


def _is_convective_edge_cell(
    row: int,
    col: int,
    height_cells: int,
    width_cells: int,
    heatsink_edge: str,
) -> bool:
    """Return True if (row, col) is on one of the three NON-heatsink edges."""
    hs = heatsink_edge.upper().strip()
    return (
        (row == 0 and hs != "BOTTOM")
        or (row == height_cells - 1 and hs != "TOP")
        or (col == 0 and hs != "LEFT")
        or (col == width_cells - 1 and hs != "RIGHT")
    ) and not _is_heatsink_edge_cell(row, col, height_cells, width_cells, heatsink_edge)


def _is_neumann_boundary_u7(
    row: int,
    col: int,
    direction: str,
    height_cells: int,
    width_cells: int,
    heatsink_edge: str,
) -> bool:
    """Return True if the neighbour in *direction* would cross a board edge
    that is NOT the heatsink (convective edge; handled separately) or if it
    would cross the board boundary entirely.

    This mirrors U5's ``_is_neumann_boundary``: returns True for edges that
    should NOT create a conductive stencil connection.
    """
    h = height_cells
    w = width_cells
    hs_edge = heatsink_edge.upper().strip()

    if direction == "north" and row == h - 1:
        return hs_edge != "TOP"
    if direction == "south" and row == 0:
        return hs_edge != "BOTTOM"
    if direction == "west" and col == 0:
        return hs_edge != "LEFT"
    if direction == "east" and col == w - 1:
        return hs_edge != "RIGHT"
    return False


def _build_conductivity_field_gs(
    config: ThermalFDMConfig,
    copper_grid: np.ndarray | None = None,
) -> np.ndarray:
    """Build per-cell in-plane conductance k_eff (W/K) — identical physics
    to U5's ``_build_conductivity_field`` but implemented here to avoid any
    import of thermal_fdm internal helpers.

    Computed in the ``temper-thermal`` Rust crate
    (``packages/temper-thermal/src/thermal_scorer.rs``) with the exact f64
    operation order of the former vectorized-numpy loop.
    """
    import temper_thermal as _tt

    h = config.height_cells
    w = config.width_cells
    raw = _tt.build_conductivity_field_py(
        config.k_fr4,
        config.k_copper,
        config.board_thickness_mm,
        None if copper_grid is None else np.ascontiguousarray(copper_grid, dtype=np.float64).tobytes(),
        h,
        w,
    )
    return np.frombuffer(raw, dtype=np.float64).reshape((h, w)).copy()


def _build_heat_source_field_gs(
    config: ThermalFDMConfig,
    devices: dict[str, tuple[float, float]],
    power_map: dict[str, float],
    Q_field: np.ndarray | None = None,
) -> np.ndarray:
    """Build per-cell areal heat source Q (W/mm^2) — identical to U5's
    ``_build_heat_source_field`` but independent implementation.

    The per-device footprint spreading loop (the genuine Python loop here)
    is computed in the ``temper-thermal`` Rust crate
    (``packages/temper-thermal/src/thermal_scorer.rs``), preserving dict
    insertion order and the reference's exact floor/ceil index math.
    """
    import temper_thermal as _tt

    h = config.height_cells
    w = config.width_cells
    ox, oy = config.origin_mm
    cs = config.cell_size_mm

    if Q_field is not None:
        return np.asarray(Q_field, dtype=np.float64)

    raw = _tt.build_heat_source_field_py(
        [(name, x, y) for name, (x, y) in devices.items()],
        list(power_map.items()),
        ox,
        oy,
        cs,
        h,
        w,
    )
    return np.frombuffer(raw, dtype=np.float64).reshape((h, w)).copy()


def _is_heatsink_boundary_face_u7(
    row: int,
    col: int,
    direction: str,
    height_cells: int,
    width_cells: int,
    heatsink_edge: str,
) -> bool:
    """Return True if the face in *direction* is the outer boundary
    in the heatsink direction (Dirichlet face, not Neumann)."""
    hs = heatsink_edge.upper().strip()
    if direction == "north" and row == height_cells - 1 and hs == "TOP":
        return True
    if direction == "south" and row == 0 and hs == "BOTTOM":
        return True
    if direction == "east" and col == width_cells - 1 and hs == "RIGHT":
        return True
    return bool(direction == "west" and col == 0 and hs == "LEFT")


def _assemble_convective_system(
    config: ThermalFDMConfig,
    k_field: np.ndarray,
    Q_field: np.ndarray,
    h_conv: float,
    h_field: np.ndarray | None = None,
) -> tuple[scipy.sparse.csr_matrix, np.ndarray]:
    """Assemble the sparse linear system A*T = b for the convective-boundary FDM.

    Same 5-point harmonic-mean stencil as U5's ``_assemble_system``, PLUS a
    convective term ``h_conv * (T - T_amb)`` at the three non-heatsink edges.

    Dirichlet face term at the heatsink edge (boundary-aligned, 2nd-order),
    Robin (convective) at all other edges.

    When *h_field* is provided, adds a per-cell through-plane vertical sink
    term (same pattern as U5's ``_assemble_system``).

    Assembly is computed in the ``temper-thermal`` Rust crate
    (``packages/temper-thermal/src/thermal_scorer.rs``) with the exact f64
    operation order of the former pure-Python ``lil_matrix`` loop; the sparse
    matrix is rebuilt here and the solve stays in scipy (SuperLU).
    """
    import temper_thermal as _tt
    from scipy.sparse import coo_matrix

    from temper_placer.physics.thermal_fdm import _heatsink_edge_code

    h = config.height_cells
    w = config.width_cells
    n = h * w

    rows, cols, values, b = _tt.assemble_convective_system_py(
        np.ascontiguousarray(k_field, dtype=np.float64).tobytes(),
        np.ascontiguousarray(Q_field, dtype=np.float64).tobytes(),
        None
        if h_field is None
        else np.ascontiguousarray(h_field, dtype=np.float64).tobytes(),
        h,
        w,
        config.ambient_C,
        config.cell_size_mm,
        config.board_thickness_mm,
        h_conv,
        _heatsink_edge_code(config.heatsink_edge),
    )
    A = coo_matrix((values, (rows, cols)), shape=(n, n), dtype=np.float64).tocsr()
    return A, np.asarray(b, dtype=np.float64)


def _convective_fdm_solve(
    config: ThermalFDMConfig,
    k_field: np.ndarray,
    Q_field: np.ndarray,
    scorer_config: ThermalScorerConfig,
    h_field: np.ndarray | None = None,
) -> tuple[np.ndarray, int, float]:
    """Solve the convective-boundary FDM via sparse-direct SuperLU.

    Returns (T_grid, 0, 0.0) where the zero iterations and residual reflect
    the direct-solve nature (retained for backward compat with the
    solve_independent return signature).
    """
    from scipy.sparse.linalg import spsolve

    A, b = _assemble_convective_system(
        config,
        k_field,
        Q_field,
        h_conv=scorer_config.h,
        h_field=h_field,
    )
    T_flat: np.ndarray = spsolve(A, b)
    T_grid = T_flat.reshape(config.height_cells, config.width_cells)
    return T_grid, 0, 0.0


# ---------------------------------------------------------------------------
# Scorer class — pluggable into U2's build_scorecard
# ---------------------------------------------------------------------------


class ThermalScorer:
    """Independent thermal scorer using convective-boundary FDM.

    This scorer is **model independent** of U5's FDM solver:
    same 5-point harmonic-mean stencil for in-plane conduction, but with a
    convective (Robin) boundary condition at the three non-heatsink edges
    instead of U5's adiabatic Neumann.

    The convective coefficient ``h`` is a physically grounded fixed value
    (10 W/(m^2.K) for natural convection in still air), never tuned to pass
    a test.

    Consumable by U2's ``build_scorecard`` as the ``scorer`` parameter.
    """

    def __init__(self, config: ThermalScorerConfig | None = None) -> None:
        self.config = config or ThermalScorerConfig()

    # ------------------------------------------------------------------
    # Public: independent solve (returns raw grid)
    # ------------------------------------------------------------------

    def solve_independent(
        self,
        fdm_config: ThermalFDMConfig,
        devices: dict[str, tuple[float, float]] | None = None,
        power_map: dict[str, float] | None = None,
        copper_grid: np.ndarray | None = None,
        Q_field: np.ndarray | None = None,
        h_field: np.ndarray | None = None,
    ) -> tuple[np.ndarray, int, float]:
        """Run the independent convective-boundary solve, returning
        ``(T_grid, 0, 0.0)``.

        The iterations and residual are always 0 because the solver is a
        sparse-direct solve (SuperLU); they are retained for backward
        compatibility with the ``solve_independent`` return signature.

        Args:
            fdm_config: Same grid / BC config as U5's ``ThermalFDMConfig``.
            devices: ``{ref: (x_mm, y_mm)}``.
            power_map: ``{ref: power_W}``.
            copper_grid: Per-cell copper fraction ``(h, w)``.
            Q_field: Direct per-cell heat source ``(h, w)`` W/mm^2.
            h_field: Per-cell through-plane vertical sink conductance ``(h, w)``
                in W/(K·mm^2), same as U5's ``solve_thermal_fdm`` parameter.

        Returns:
            ``(T_grid, 0, 0.0)`` where ``T_grid`` has shape
            ``(height_cells, width_cells)`` float64.
        """
        devices = devices or {}
        power_map = power_map or {}

        k_field = _build_conductivity_field_gs(fdm_config, copper_grid=copper_grid)
        Q_src = _build_heat_source_field_gs(fdm_config, devices, power_map, Q_field=Q_field)

        return _convective_fdm_solve(fdm_config, k_field, Q_src, self.config, h_field=h_field)

    # ------------------------------------------------------------------
    # Public: score (compare U5 field to independent solve)
    # ------------------------------------------------------------------

    def score(
        self,
        u5_result: FieldResult,
        fdm_config: ThermalFDMConfig,
        devices: dict[str, tuple[float, float]] | None = None,
        power_map: dict[str, float] | None = None,
        copper_grid: np.ndarray | None = None,
        Q_field: np.ndarray | None = None,
        h_field: np.ndarray | None = None,
    ) -> ThermalScoreResult:
        """Score U5's thermal field by comparing to the independent
        convective-boundary solve.

        Args:
            u5_result: ``FieldResult`` from ``solve_thermal_fdm()`` (U5).
            fdm_config: Same config passed to U5's solver.
            devices: Same devices passed to U5's solver.
            power_map: Same power_map passed to U5's solver.
            copper_grid: Same copper_grid passed to U5's solver.
            Q_field: Same Q_field passed to U5's solver.
            h_field: Same h_field passed to U5's solver (through-plane sink).

        Returns:
            ``ThermalScoreResult`` with comparison metrics, structural bounds,
            and shared/independent assumption documentation.
        """
        if u5_result.field is None:
            from temper_placer.fields.result import FieldNotReadyError

            raise FieldNotReadyError(
                f"Cannot score UNMEASURED thermal field: "
                f"{u5_result.error_message or 'unknown'}; "
                f"UNMEASURED means 'could not measure,' not '0 deg-C everywhere'"
            )

        # u5_result always comes from solve_thermal_fdm() (see docstring above),
        # which returns a CostField (never a bare ndarray) on every non-UNMEASURED
        # path -- see temper_placer.fields.result.FieldResult's field union and
        # thermal_fdm.solve_thermal_fdm's own "CLEAN status and a CostField grid
        # on success" contract. Narrow explicitly rather than widening FieldResult
        # itself with an ndarray-safe accessor this call site does not need.
        from temper_placer.fields.field import CostField

        assert isinstance(u5_result.field, CostField), (
            f"solve_thermal_fdm() must return a CostField on success, got {type(u5_result.field)!r}"
        )
        u5_grid = np.asarray(u5_result.field.grid, dtype=np.float64)
        u5_peak = float(np.max(u5_grid))
        u5_mean = float(np.mean(u5_grid))

        u7_grid, _iterations, _residual = self.solve_independent(
            fdm_config,
            devices=devices,
            power_map=power_map,
            copper_grid=copper_grid,
            Q_field=Q_field,
            h_field=h_field,
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
            scorer_id="thermal-convective-fdm",
            structural_axis=STRUCTURAL_INDEPENDENCE_AXIS,
            u5_peak_C=u5_peak,
            u7_peak_C=u7_peak,
            u5_mean_C=u5_mean,
            u7_mean_C=u7_mean,
            peak_deviation_C=peak_dev,
            mean_deviation_C=mean_dev,
            max_cell_deviation_C=max_cell_dev,
            agreement=agreement,
            convergence_iterations=0,
            residual_C=0.0,
        )

    def __call__(
        self,
        u5_result: FieldResult,
        fdm_config: ThermalFDMConfig,
        devices: dict[str, tuple[float, float]] | None = None,
        power_map: dict[str, float] | None = None,
        copper_grid: np.ndarray | None = None,
        Q_field: np.ndarray | None = None,
        h_field: np.ndarray | None = None,
    ) -> ThermalScoreResult:
        """Callable interface for U2's ``build_scorecard``."""
        return self.score(
            u5_result=u5_result,
            fdm_config=fdm_config,
            devices=devices,
            power_map=power_map,
            copper_grid=copper_grid,
            Q_field=Q_field,
            h_field=h_field,
        )
