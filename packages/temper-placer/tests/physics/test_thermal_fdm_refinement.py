"""
Order-of-accuracy refinement ladder for the thermal FDM solver (U5 / R11).

Solves a smooth, continuous-conductivity analytic geometry (uniform-k 1D bar
with fixed-temperature top, adiabatic bottom/sides, uniform heating) at grid
spacings h, h/2, h/4; computes error vs the closed-form parabolic profile;
asserts the observed convergence rate matches the stencil's actual order.

**Finding:** The shipped stencil yields **1st-order** global convergence
(error ∝ h; rate ≈ 1.0) on the smooth uniform-k case due to cell-centre
Dirichlet BC application — not the 2nd-order the 5-point interior stencil
would deliver with a boundary-conforming Dirichlet.  The harmonic-mean
interface treatment drops to 1st-order at material discontinuities as well
(a known caveat), so the solver is effectively 1st-order in all regimes.

The fail-capable check constructs a deliberately 2nd-order error sequence
and proves the 1st-order rate assertion rejects it.

@req(2026-07-09-001-feat-physics-verification-rigor-plan, R11): order-of-accuracy refinement ladder
"""

from __future__ import annotations

import numpy as np
import pytest

from temper_placer.physics.thermal_fdm import ThermalFDMConfig, solve_thermal_fdm

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_EXPECTED_ORDER = 1.0  # stencil is effectively 1st-order (cell-centre Dirichlet BC)
_ORDER_TOLERANCE = 0.30  # |observed_rate - EXPECTED_ORDER| must be below this


def _analytic_bar_1d(
    y_world: np.ndarray, T_top: float, Q: float, k_eff: float, H: float
) -> np.ndarray:
    """Analytic 1D bar: T(y) = T_top + Q/(2*k) * (H² - y²).

    Dirichlet at y=H (T=T_top), adiabatic at y=0 (dT/dy=0), uniform Q.
    """
    return T_top + Q / (2.0 * k_eff) * (H**2 - y_world**2)


def _solve_and_error(
    cell_size_mm: float,
    height_cells: int,
    width_cells: int,
    T_top: float,
    k_eff_target: float,
    Q_uniform: float,
) -> float:
    """Solve FDM at a given resolution; return RMS error vs analytic over
    the full field.

    The cell-centre Dirichlet BC introduces a uniform O(cs) shift, so
    excluding the Dirichlet row does not alter the rate estimate.
    """
    board_thickness = 1.6
    k_val = k_eff_target / (board_thickness * 1e-3)

    config = ThermalFDMConfig(
        cell_size_mm=cell_size_mm,
        origin_mm=(0.0, 0.0),
        height_cells=height_cells,
        width_cells=width_cells,
        ambient_C=T_top,
        heatsink_edge="TOP",
        k_fr4=k_val,
        k_copper=k_val,  # uniform material → continuous k
        board_thickness_mm=board_thickness,
    )

    copper_grid = np.zeros((height_cells, width_cells), dtype=np.float64)
    Q_src = np.full((height_cells, width_cells), Q_uniform, dtype=np.float64)

    result = solve_thermal_fdm(
        config=config,
        devices={},
        power_map={},
        copper_grid=copper_grid,
        Q_field=Q_src,
    )
    assert result.is_usable, f"Solver returned {result.status}"
    assert result.field is not None
    T_numeric = np.asarray(result.field.grid, dtype=np.float64)

    H = height_cells * cell_size_mm
    y_cells = np.arange(height_cells)
    y_world = y_cells * cell_size_mm + cell_size_mm / 2.0
    T_analytic_1d = _analytic_bar_1d(y_world, T_top, Q_uniform, k_eff_target, H)
    T_analytic = np.tile(T_analytic_1d[:, np.newaxis], (1, width_cells))

    diff = T_numeric - T_analytic
    return float(np.sqrt(np.mean(diff**2)))


def _convergence_rates(errors: list[float]) -> list[float]:
    """Compute observed convergence orders from successive errors.

    For p-th order convergence: error ∝ h^p, so  error_i / error_{i+1} ≈ 2^p.
    Returns p = log₂(error_i / error_{i+1}) for each adjacent pair.
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
    """Assert every observed convergence rate is consistent with *expected*
    order within *tolerance*.  Raises ``AssertionError`` on violation.
    """
    for i, rate in enumerate(rates):
        delta = abs(rate - expected)
        assert delta < tolerance, (
            f"Convergence rate {rate:.3f} at level {i} contradicts "
            f"{expected}-order expectation (|rate-{expected}|={delta:.3f} >= {tolerance})"
        )


# ---------------------------------------------------------------------------
# Happy path: 1st-order convergence on a smooth uniform-k bar
# ---------------------------------------------------------------------------


@pytest.mark.property
@pytest.mark.k1
def test_thermal_fdm_refinement_convergence_order():
    """R11: Error decreases ~2× per halving (1st-order convergence) on a
    smooth continuous-conductivity uniform bar.

    The cell-centre Dirichlet BC application limits the global convergence to
    1st order (error ∝ cs).  The interior 5-point stencil is 2nd-order, but
    the BC error dominates the RMS norm.

    Grid ladder:  h = 2.0 mm (10×10) → h/2 = 1.0 mm (20×20) → h/4 = 0.5 mm (40×40).
    Finest grid is 40×40 = 1600 cells, within the 2500-cell default budget.
    """
    T_top = 40.0  # °C — Dirichlet on TOP edge
    k_eff_target = 1.0  # W/K (in-plane)
    Q_uniform = 0.1  # W/mm²

    errors = [
        _solve_and_error(cs, hc, wc, T_top, k_eff_target, Q_uniform)
        for cs, hc, wc in (
            (2.0, 10, 10),
            (1.0, 20, 20),
            (0.5, 40, 40),
        )
    ]

    rates = _convergence_rates(errors)

    # Monotonic decrease
    assert errors[0] > errors[1] > errors[2], (
        f"Error must decrease with grid refinement; got {errors}"
    )

    _assert_convergence_order(rates, expected=1.0)


# ---------------------------------------------------------------------------
# Fail-capable: prove the rate check is not vacuous
# ---------------------------------------------------------------------------


def test_refinement_rate_check_rejects_second_order_sequence():
    """Fail-capable: a synthetic 2nd-order error sequence is rejected by
    the 1st-order assertion.

    A 2nd-order method reduces error by ~4× per halving (rate ≈ 2.0).
    Proves the 1st-order rate check is not vacuously true.
    """
    # 2nd-order: error ∝ h² → error ratio per halving ≈ 4
    second_order_errors = [0.4, 0.1, 0.025]
    rates = _convergence_rates(second_order_errors)

    # Sanity: the synthetic rates really are ~2.0
    for r in rates:
        assert abs(r - 2.0) < 0.3, f"Expected ~2nd-order rates, got {rates}"

    with pytest.raises(AssertionError):
        _assert_convergence_order(rates, expected=1.0)


def test_refinement_rate_check_rejects_constant_sequence():
    """Fail-capable: a non-decreasing error sequence (stalled convergence)
    is also rejected.
    """
    stalled_errors = [0.5, 0.5, 0.5]
    rates = _convergence_rates(stalled_errors)
    with pytest.raises(AssertionError):
        _assert_convergence_order(rates, expected=1.0)


# ---------------------------------------------------------------------------
# Edge: explicit tolerance-band regression markers
# ---------------------------------------------------------------------------


def test_refinement_rate_tolerance_guard():
    """A rate of 1.25 (barely within the 1st-order tolerance) must pass.
    A rate of 0.65 (clearly outside) must fail.
    """
    # error ∝ h^1.25 → ratio ≈ 2^1.25 ≈ 2.38
    errors_pass = [1.0, 1.0 / (2.0**1.25), 1.0 / (4.0**1.25)]
    rates_pass = _convergence_rates(errors_pass)
    _assert_convergence_order(rates_pass, expected=1.0)

    # error ∝ h^0.65 → ratio ≈ 2^0.65 ≈ 1.57
    errors_fail = [1.0, 1.0 / (2.0**0.65), 1.0 / (4.0**0.65)]
    rates_fail = _convergence_rates(errors_fail)
    with pytest.raises(AssertionError):
        _assert_convergence_order(rates_fail, expected=1.0)
