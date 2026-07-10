"""
Method of Manufactured Solutions (MMS) correctness verification for the
thermal FDM solver (U5).

Picks smooth analytic T*(x,y) that satisfies the solver's boundary
conditions, derives the exact source Q*(x,y) = -div(k grad T*) from the
continuous PDE, feeds Q* to the solver, and verifies the solution
converges to T* at 2nd order as the grid refines.

Two manufactured solutions:

1. **Uniform k**: T*(x,y) = T_amb + A * cos(pi*x/Lx) * cos(pi*y/(2Ly))
   Exercises the full 2D 5-point stencil + mixed Dirichlet/Neumann BCs.

2. **Spatially-varying k**: SAME T*(x,y) but with
   k(x,y) = k0 + k1 * sin(pi*x/Lx) * sin(pi*y/(2Ly))
   Exercises harmonic-mean interface treatment with genuinely heterogeneous
   conductivity.

The refinement ladder proves you converge at the right ORDER; MMS proves
you converge to the RIGHT THING.

@req(2026-07-09-001-feat-physics-verification-rigor-plan, R13): MMS correctness verification
"""

from __future__ import annotations

import numpy as np
import pytest
import sympy as sp

from temper_placer.physics.thermal_fdm import ThermalFDMConfig, solve_thermal_fdm

# ============================================================================
# Symbolic derivation of manufactured solutions
# ============================================================================

# Symbolic variables
x, y = sp.symbols("x y", real=True)
Lx, Ly = sp.symbols("Lx Ly", positive=True)
A = sp.symbols("A", positive=True)  # temperature scale factor (°C)
T_amb_s = sp.symbols("T_amb")
k0, k1 = sp.symbols("k0 k1", positive=True)

# Wave numbers matching the BCs
ax = sp.pi / Lx  # alpha_x: ensures dT/dx = 0 at x=0, Lx
ay = sp.pi / (2 * Ly)  # alpha_y: ensures dT/dy = 0 at y=0, T*=T_amb at y=Ly

# ------------------------------------------------------------------
# Manufactured temperature (shared by both cases)
# T*(x,y) = T_amb + A * cos(ax * x) * cos(ay * y)
#
# BC checks:
#   y = Ly: cos(ay*Ly) = cos(pi/2) = 0  => T* = T_amb (Dirichlet TOP)
#   y = 0:  dT/dy ∝ sin(ay*0) = 0       => adiabatic BOTTOM
#   x = 0:  dT/dx ∝ sin(ax*0) = 0       => adiabatic LEFT
#   x = Lx: dT/dx ∝ sin(ax*Lx) = sin(pi)=0 => adiabatic RIGHT
# ------------------------------------------------------------------
T_star = T_amb_s + A * sp.cos(ax * x) * sp.cos(ay * y)

# ------------------------------------------------------------------
# Case 1: Uniform k
# Q* = -k0 * laplacian(T*) = k0 * A * (ax^2 + ay^2) * cos(ax*x) * cos(ay*y)
# ------------------------------------------------------------------
lap_T = sp.diff(T_star, x, 2) + sp.diff(T_star, y, 2)
Q1 = -k0 * lap_T

# Simplify: Q1 = k0 * A * (ax^2 + ay^2) * cos(ax*x) * cos(ay*y)
Q1_simplified = sp.simplify(Q1)

# ------------------------------------------------------------------
# Case 2: Spatially-varying k
# k(x,y) = k0 + k1 * sin(ax * x) * sin(ay * y)
#
# k varies in [k0 - k1, k0 + k1].  With k1 < k0, k stays positive.
# The sin*sin form satisfies dk/dx = 0 at x=0,Lx and dk/dy = 0 at y=0
# (no special BC on k needed, but smoothness helps convergence).
#
# Q* = -div(k grad T) = -(k * laplacian(T) + grad(k) . grad(T))
# ------------------------------------------------------------------
k_star = k0 + k1 * sp.sin(ax * x) * sp.sin(ay * y)

grad_k_x = sp.diff(k_star, x)
grad_k_y = sp.diff(k_star, y)
grad_T_x = sp.diff(T_star, x)
grad_T_y = sp.diff(T_star, y)

k_lap_T = k_star * lap_T
grad_k_dot_grad_T = grad_k_x * grad_T_x + grad_k_y * grad_T_y
Q2 = -(k_lap_T + grad_k_dot_grad_T)

Q2_simplified = sp.simplify(Q2)

# Lambdify for numpy evaluation (use 'numpy' backend for speed)
# Q1 and Q2 don't depend on T_amb (it cancels in the derivatives), but
# we include it in the signature so all args match.
_Q1_np = sp.lambdify((x, y, Lx, Ly, A, T_amb_s, k0), Q1_simplified, "numpy")
_Q2_np = sp.lambdify((x, y, Lx, Ly, A, T_amb_s, k0, k1), Q2_simplified, "numpy")
_T_np = sp.lambdify((x, y, Lx, Ly, A, T_amb_s), T_star, "numpy")

# ============================================================================
# Helpers
# ============================================================================

_EXPECTED_ORDER = 2.0
_ORDER_TOLERANCE = 0.36
_T_AMB = 40.0  # °C — solver's ambient / Dirichlet temperature


def _cell_centers(cs_mm: float, n_cells: int) -> np.ndarray:
    """Return world coordinates (mm) of cell centers along one axis."""
    return (np.arange(n_cells, dtype=np.float64) + 0.5) * cs_mm


def _mm_error_norms(
    T_numeric: np.ndarray,
    T_analytic: np.ndarray,
) -> tuple[float, float]:
    """Return (L2 error, L-infinity error) between numeric and analytic."""
    diff = T_numeric - T_analytic
    return float(np.sqrt(np.mean(diff**2))), float(np.max(np.abs(diff)))


def _convergence_rates(errors: list[float]) -> list[float]:
    """Compute observed convergence orders from successive errors.

    For p-th order convergence: error ∝ h^p, so error_i/error_{i+1} ≈ 2^p.
    """
    rates: list[float] = []
    for i in range(len(errors) - 1):
        ratio = errors[i] / errors[i + 1]
        if ratio <= 1.0:
            rates.append(0.0)
        else:
            rates.append(float(np.log2(ratio)))
    return rates


def _assert_convergence_order(
    rates: list[float],
    expected: float = _EXPECTED_ORDER,
    tolerance: float = _ORDER_TOLERANCE,
) -> None:
    """Assert every observed rate is consistent with *expected* order."""
    for i, rate in enumerate(rates):
        delta = abs(rate - expected)
        assert delta < tolerance, (
            f"Convergence rate {rate:.3f} at level {i} contradicts "
            f"{expected}-order expectation "
            f"(|rate-{expected}|={delta:.3f} >= {tolerance})"
        )


# ============================================================================
# MMS Case 1: Uniform k — exercises full 2D stencil + mixed BCs
# ============================================================================


@pytest.mark.k1
def test_mms_uniform_k_convergence():
    """MMS: manufactured sin-sin solution with uniform conductivity.

    T*(x,y) = T_amb + A * cos(pi*x/Lx) * cos(pi*y/(2*Ly))

    Derived Q*(x,y) = k * A * (pi^2/Lx^2 + pi^2/(4*Ly^2))
                      * cos(pi*x/Lx) * cos(pi*y/(2*Ly))

    Grid ladder: h = 2.0mm (10x15) -> h/2 = 1.0mm (20x30) ->
                 h/4 = 0.5mm (40x60).

    Verifies 2nd-order convergence in both L2 and L∞ norms.
    """
    A_val = 20.0  # °C — temperature excursion scale
    k_eff = 1.0  # W/K (in-plane effective conductance)
    board_thickness = 1.6  # mm
    # k_eff = k * thickness_mm * 1e-3 => k = k_eff / (thickness * 1e-3)
    k_val = k_eff / (board_thickness * 1e-3)

    cell_sizes = [2.0, 1.0, 0.5]
    h_cells_list = [10, 20, 40]
    w_cells_list = [15, 30, 60]  # rectangular: exercises anisotropic 2D stencil

    errors_l2: list[float] = []
    errors_linf: list[float] = []

    for cs, hc, wc in zip(cell_sizes, h_cells_list, w_cells_list):
        Lx_val = wc * cs
        Ly_val = hc * cs

        x_c = _cell_centers(cs, wc)  # shape (W,)
        y_c = _cell_centers(cs, hc)  # shape (H,)
        X, Y = np.meshgrid(x_c, y_c)  # shapes (H, W)

        T_analytic = _T_np(X, Y, Lx_val, Ly_val, A_val, _T_AMB)
        Q_analytic = _Q1_np(X, Y, Lx_val, Ly_val, A_val, _T_AMB, k_eff)

        config = ThermalFDMConfig(
            cell_size_mm=cs,
            origin_mm=(0.0, 0.0),
            height_cells=hc,
            width_cells=wc,
            ambient_C=_T_AMB,
            heatsink_edge="TOP",
            k_fr4=k_val,
            k_copper=k_val,  # uniform material
            board_thickness_mm=board_thickness,
            max_cells=10000,
        )

        copper_grid = np.zeros((hc, wc), dtype=np.float64)
        result = solve_thermal_fdm(
            config=config,
            devices={},
            power_map={},
            copper_grid=copper_grid,
            Q_field=np.asarray(Q_analytic, dtype=np.float64),
        )

        assert result.is_usable, f"Solver failed at cs={cs}mm"
        T_numeric = np.asarray(result.field.grid, dtype=np.float64)

        l2, linf = _mm_error_norms(T_numeric, T_analytic)
        errors_l2.append(l2)
        errors_linf.append(linf)

    # Monotonic error decrease with refinement
    assert errors_l2[0] > errors_l2[1] > errors_l2[2], (
        f"L2 error must decrease with refinement; got {errors_l2}"
    )
    assert errors_linf[0] > errors_linf[1] > errors_linf[2], (
        f"Linf error must decrease with refinement; got {errors_linf}"
    )

    rates_l2 = _convergence_rates(errors_l2)
    rates_linf = _convergence_rates(errors_linf)

    _assert_convergence_order(rates_l2, expected=_EXPECTED_ORDER)
    _assert_convergence_order(rates_linf, expected=_EXPECTED_ORDER)


# ============================================================================
# MMS Case 2: Spatially-varying k — exercises harmonic-mean interfaces
# ============================================================================


@pytest.mark.k1
def test_mms_varying_k_convergence():
    """MMS: manufactured solution with smooth spatially-varying conductivity.

    T*(x,y) = T_amb + A * cos(pi*x/Lx) * cos(pi*y/(2*Ly))

    k(x,y) = k_fr4 + dk * sin(pi*x/Lx) * sin(pi*y/(2*Ly))

    where dk = k_cu - k_fr4 (in-plane effective conductance).

    The copper fraction field is computed so that
    _build_conductivity_field produces k(x,y) at cell centres.

    Q*(x,y) = -div(k grad T) = -(k * laplacian(T) + grad(k) . grad(T))

    derived symbolically via sympy (conductivity varies between cells,
    exercising the harmonic-mean interface treatment).

    Grid ladder: same as Case 1 (h=2.0, 1.0, 0.5 mm).
    """
    A_val = 20.0  # °C
    k_fr4_eff = 0.5  # W/K  (in-plane)
    k_cu_eff = 2.0  # W/K  (in-plane)
    dk_eff = k_cu_eff - k_fr4_eff  # 1.5 W/K
    board_thickness = 1.6  # mm

    # k = k * thickness => k_val = k_eff / (thickness * 1e-3)
    k_fr4_val = k_fr4_eff / (board_thickness * 1e-3)
    k_cu_val = k_cu_eff / (board_thickness * 1e-3)

    cell_sizes = [2.0, 1.0, 0.5]
    h_cells_list = [10, 20, 40]
    w_cells_list = [15, 30, 60]

    errors_l2: list[float] = []
    errors_linf: list[float] = []

    for cs, hc, wc in zip(cell_sizes, h_cells_list, w_cells_list):
        Lx_val = wc * cs
        Ly_val = hc * cs

        x_c = _cell_centers(cs, wc)
        y_c = _cell_centers(cs, hc)
        X, Y = np.meshgrid(x_c, y_c)

        T_analytic = _T_np(X, Y, Lx_val, Ly_val, A_val, _T_AMB)
        Q_analytic = _Q2_np(X, Y, Lx_val, Ly_val, A_val, _T_AMB, k_fr4_eff, dk_eff)

        # Compute copper fraction such that _build_conductivity_field
        # yields k(x,y) = k_fr4_eff + dk_eff * sin(ax*x) * sin(ay*y)
        # at cell centres:
        #   k_eff = k_fr4_eff + (k_cu_eff - k_fr4_eff) * frac
        #   => frac = (k_eff - k_fr4_eff) / dk_eff
        #          = sin(ax*x) * sin(ay*y)  (note: ax=pi/Lx, ay=pi/(2*Ly))
        k_desired = k_fr4_eff + dk_eff * np.sin(np.pi * X / Lx_val) * np.sin(
            np.pi * Y / (2 * Ly_val)
        )
        copper_frac = (k_desired - k_fr4_eff) / dk_eff

        config = ThermalFDMConfig(
            cell_size_mm=cs,
            origin_mm=(0.0, 0.0),
            height_cells=hc,
            width_cells=wc,
            ambient_C=_T_AMB,
            heatsink_edge="TOP",
            k_fr4=k_fr4_val,
            k_copper=k_cu_val,
            board_thickness_mm=board_thickness,
            max_cells=10000,
        )

        result = solve_thermal_fdm(
            config=config,
            devices={},
            power_map={},
            copper_grid=np.asarray(copper_frac, dtype=np.float64),
            Q_field=np.asarray(Q_analytic, dtype=np.float64),
        )

        assert result.is_usable, f"Solver failed at cs={cs}mm"
        T_numeric = np.asarray(result.field.grid, dtype=np.float64)

        l2, linf = _mm_error_norms(T_numeric, T_analytic)
        errors_l2.append(l2)
        errors_linf.append(linf)

    # Monotonic error decrease
    assert errors_l2[0] > errors_l2[1] > errors_l2[2], (
        f"L2 error must decrease with refinement; got {errors_l2}"
    )
    assert errors_linf[0] > errors_linf[1] > errors_linf[2], (
        f"Linf error must decrease with refinement; got {errors_linf}"
    )

    rates_l2 = _convergence_rates(errors_l2)
    rates_linf = _convergence_rates(errors_linf)

    _assert_convergence_order(rates_l2, expected=_EXPECTED_ORDER)
    _assert_convergence_order(rates_linf, expected=_EXPECTED_ORDER)


# ============================================================================
# Peak-error sanity check
# ============================================================================


@pytest.mark.k1
def test_mms_peak_error_decreases_with_refinement():
    """The worst pointwise error in the domain must decrease monotonically
    as the grid is refined (both uniform-k and varying-k cases).

    This catches dead-zone bugs where the global norm shrinks by luck
    but a specific cell stays wrong.
    """
    A_val = 20.0
    k_eff = 1.0
    board_thickness = 1.6
    k_val = k_eff / (board_thickness * 1e-3)
    _T_amb = 40.0

    cell_sizes = [2.5, 1.25, 0.625]
    h_cells_list = [8, 16, 32]
    w_cells_list = [12, 24, 48]

    all_peaks: list[tuple[str, float, float, float]] = []

    # --- Uniform k ---
    for cs, hc, wc in zip(cell_sizes, h_cells_list, w_cells_list):
        Lx_val = wc * cs
        Ly_val = hc * cs
        x_c = _cell_centers(cs, wc)
        y_c = _cell_centers(cs, hc)
        X, Y = np.meshgrid(x_c, y_c)
        T_analytic = _T_np(X, Y, Lx_val, Ly_val, A_val, _T_amb)
        Q_analytic = _Q1_np(X, Y, Lx_val, Ly_val, A_val, _T_amb, k_eff)

        config = ThermalFDMConfig(
            cell_size_mm=cs,
            origin_mm=(0.0, 0.0),
            height_cells=hc,
            width_cells=wc,
            ambient_C=_T_amb,
            heatsink_edge="TOP",
            k_fr4=k_val,
            k_copper=k_val,
            board_thickness_mm=board_thickness,
            max_cells=10000,
        )
        result = solve_thermal_fdm(
            config=config,
            devices={},
            power_map={},
            copper_grid=np.zeros((hc, wc), dtype=np.float64),
            Q_field=np.asarray(Q_analytic, dtype=np.float64),
        )
        assert result.is_usable
        T_numeric = np.asarray(result.field.grid, dtype=np.float64)
        peak = float(np.max(np.abs(T_numeric - T_analytic)))
        all_peaks.append(("uniform", cs, hc, peak))

    # --- Varying k ---
    k_fr4_eff = 0.5
    k_cu_eff = 2.0
    dk_eff = k_cu_eff - k_fr4_eff
    k_fr4_val = k_fr4_eff / (board_thickness * 1e-3)
    k_cu_val = k_cu_eff / (board_thickness * 1e-3)

    for cs, hc, wc in zip(cell_sizes, h_cells_list, w_cells_list):
        Lx_val = wc * cs
        Ly_val = hc * cs
        x_c = _cell_centers(cs, wc)
        y_c = _cell_centers(cs, hc)
        X, Y = np.meshgrid(x_c, y_c)
        T_analytic = _T_np(X, Y, Lx_val, Ly_val, A_val, _T_amb)
        Q_analytic = _Q2_np(
            X, Y, Lx_val, Ly_val, A_val, _T_amb, k_fr4_eff, dk_eff
        )
        k_desired = k_fr4_eff + dk_eff * np.sin(
            np.pi * X / Lx_val
        ) * np.sin(np.pi * Y / (2 * Ly_val))
        copper_frac = (k_desired - k_fr4_eff) / dk_eff

        config = ThermalFDMConfig(
            cell_size_mm=cs,
            origin_mm=(0.0, 0.0),
            height_cells=hc,
            width_cells=wc,
            ambient_C=_T_amb,
            heatsink_edge="TOP",
            k_fr4=k_fr4_val,
            k_copper=k_cu_val,
            board_thickness_mm=board_thickness,
            max_cells=10000,
        )
        result = solve_thermal_fdm(
            config=config,
            devices={},
            power_map={},
            copper_grid=np.asarray(copper_frac, dtype=np.float64),
            Q_field=np.asarray(Q_analytic, dtype=np.float64),
        )
        assert result.is_usable
        T_numeric = np.asarray(result.field.grid, dtype=np.float64)
        peak = float(np.max(np.abs(T_numeric - T_analytic)))
        all_peaks.append(("varying", cs, hc, peak))

    # Verify monotonic decrease per case
    for label in ("uniform", "varying"):
        case_peaks = [p for p in all_peaks if p[0] == label]
        assert case_peaks[0][3] > case_peaks[1][3] > case_peaks[2][3], (
            f"{label}-k peak errors must decrease with refinement: "
            f"{[(p[1], p[3]) for p in case_peaks]}"
        )
