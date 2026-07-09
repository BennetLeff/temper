"""
Tests for U7 independent thermal scorer.

Covers:
- K1: Scorer and U5 agree on closed-form 1D bar (analytic anchor)
- Falsifiability: High-conductivity-contrast geometry makes them disagree
- Error: Systematically-biased field caught by independent scorer
- Edge: Each structural bounding case produces a distinct score
- Integration: Scorer is a callable consumable by build_scorecard
"""

from __future__ import annotations

import numpy as np
import pytest


# ---------------------------------------------------------------------------
# K1: Closed-form analytic 1D bar — both U5 and U7 must match analytic
# ---------------------------------------------------------------------------


@pytest.mark.k1
def test_independent_scorer_matches_analytic():
    """K1: Both U5 (direct sparse solve) and U7 (iterative Gauss-Seidel)
    match the closed-form 1D parabolic profile within 2% at peak.

    This is the third independent reference (analytic solution) — proving
    that two structurally different solvers converge to the same correct
    answer on a well-conditioned geometry.
    """
    from temper_placer.physics.thermal_fdm import ThermalFDMConfig, solve_thermal_fdm
    from temper_placer.validation.thermal_scorer import ThermalScorer, ThermalScorerConfig

    cell_size = 0.5
    height_cells = 40
    width_cells = 5
    H = height_cells * cell_size
    T_top = 40.0

    k_eff_target = 1.0
    board_thickness = 1.6
    k_fr4_val = k_eff_target / (board_thickness * 1e-3)
    Q_uniform = 0.1

    config = ThermalFDMConfig(
        cell_size_mm=cell_size,
        origin_mm=(0.0, 0.0),
        height_cells=height_cells,
        width_cells=width_cells,
        ambient_C=T_top,
        heatsink_edge="TOP",
        k_fr4=k_fr4_val,
        k_copper=k_fr4_val,
        board_thickness_mm=board_thickness,
    )

    devices: dict[str, tuple[float, float]] = {}
    power_map: dict[str, float] = {}
    copper_grid = np.zeros((height_cells, width_cells), dtype=np.float64)
    Q_field = np.full((height_cells, width_cells), Q_uniform, dtype=np.float64)

    # U5: direct sparse solve
    u5_result = solve_thermal_fdm(
        config=config,
        devices=devices,
        power_map=power_map,
        copper_grid=copper_grid,
        Q_field=Q_field,
    )
    assert u5_result.is_usable
    u5_grid = np.asarray(u5_result.field.grid, dtype=np.float64)

    # U7: independent iterative solve — needs enough budget to converge
    scorer = ThermalScorer(ThermalScorerConfig(
        max_iterations=20000, tolerance_C=0.0001, relaxation=1.0,
    ))
    u7_grid, iterations, residual = scorer.solve_independent(
        config, devices=devices, power_map=power_map,
        copper_grid=copper_grid, Q_field=Q_field,
    )

    # Analytic: T(y) = T_top + Q/(2*k_eff) * (H^2 - y^2)
    col = width_cells // 2
    T_u5_center = u5_grid[:, col]
    T_u7_center = u7_grid[:, col]
    y_cells = np.arange(height_cells)
    y_world = y_cells * cell_size + cell_size / 2
    T_analytic = T_top + Q_uniform / (2 * k_eff_target) * (H**2 - y_world**2)

    # Both independently match analytic within 2% at each point
    u5_rel_err = np.max(
        np.abs(T_u5_center - T_analytic) / np.maximum(np.abs(T_analytic), 1e-6)
    )
    u7_rel_err = np.max(
        np.abs(T_u7_center - T_analytic) / np.maximum(np.abs(T_analytic), 1e-6)
    )

    assert u5_rel_err < 0.02, f"U5 relative error {u5_rel_err:.4f} exceeds 2%"
    assert u7_rel_err < 0.02, f"U7 relative error {u7_rel_err:.4f} exceeds 2%"

    # U5 and U7 agree with each other (both match analytic)
    u5_u7_max_diff = float(np.max(np.abs(u7_grid - u5_grid)))
    assert u5_u7_max_diff < 0.5, (
        f"U5-U7 max diff {u5_u7_max_diff:.3f}°C "
        f"— should agree on well-conditioned problem"
    )


# ---------------------------------------------------------------------------
# Falsifiability: High-conductivity-contrast geometry makes them disagree
# ---------------------------------------------------------------------------


def test_falsifiability_high_contrast_disagreement():
    """Falsifiability: On a geometry with extreme copper/FR4 conductivity
    contrast (~1000:1), the iterative Gauss-Seidel solver with a bounded
    iteration budget produces a measurably different field from U5's exact
    direct solve.

    The assertion: max|U7 - U5| > 1.0 °C at the hottest cell.  This cannot
    happen if U7 were just a recompilation of U5 — both would produce
    identical results.  The disagreement proves structural independence.

    The bounded budget is the structural property: direct solvers solve to
    machine precision; iterative solvers stop at a budget.  The high-
    conductivity contrast magnifies the convergence gap.
    """
    from temper_placer.physics.thermal_fdm import ThermalFDMConfig, solve_thermal_fdm
    from temper_placer.validation.thermal_scorer import (
        FALSIFIABILITY_THRESHOLD_C,
        ThermalScorer,
        ThermalScorerConfig,
        falsifiability_assertion,
    )

    cell_size = 1.0
    h = 50
    w = 50

    config = ThermalFDMConfig(
        cell_size_mm=cell_size,
        origin_mm=(0.0, 0.0),
        height_cells=h,
        width_cells=w,
        ambient_C=40.0,
        heatsink_edge="TOP",
        max_cells=3000,
    )

    # Copper island: solid copper in centre, FR4 everywhere else
    copper_grid = np.zeros((h, w), dtype=np.float64)
    copper_grid[15:25, 20:30] = 1.0

    # Point heat source in the copper island
    Q_field = np.zeros((h, w), dtype=np.float64)
    Q_field[20, 25] = 1.0

    devices: dict[str, tuple[float, float]] = {}
    power_map: dict[str, float] = {}

    # U5: exact direct solve
    u5_result = solve_thermal_fdm(
        config=config,
        devices=devices,
        power_map=power_map,
        copper_grid=copper_grid,
        Q_field=Q_field,
    )
    assert u5_result.is_usable
    u5_grid = np.asarray(u5_result.field.grid, dtype=np.float64)

    # U7: iterative solver with severely bounded budget (50 sweeps)
    # On this high-contrast geometry, 50 sweeps is nowhere near convergence.
    scorer = ThermalScorer(ThermalScorerConfig(
        max_iterations=50,
        tolerance_C=0.0001,
        relaxation=1.0,
    ))
    u7_grid, iterations, residual = scorer.solve_independent(
        config, devices=devices, power_map=power_map,
        copper_grid=copper_grid, Q_field=Q_field,
    )

    # Solver hit the budget (did not converge early)
    assert iterations == 50, (
        f"Expected max iterations 50, got {iterations} — "
        f"solver converged too early"
    )

    # Falsifiability: they must disagree beyond the threshold
    max_diff = float(np.max(np.abs(u7_grid - u5_grid)))
    assert falsifiability_assertion(u5_grid, u7_grid), (
        f"Falsifiability FAILED: max|U7-U5| = {max_diff:.3f}°C, "
        f"threshold = {FALSIFIABILITY_THRESHOLD_C}°C. "
        f"U5 and U7 produced essentially identical fields — "
        f"they may be two compilations of one model."
    )

    assert max_diff > FALSIFIABILITY_THRESHOLD_C, (
        f"max|U7-U5| = {max_diff:.3f}°C <= "
        f"{FALSIFIABILITY_THRESHOLD_C}°C threshold"
    )


# ---------------------------------------------------------------------------
# Error: Systematically-biased field caught by independent scorer
# ---------------------------------------------------------------------------


def test_biased_field_caught_by_independent_scorer():
    """Error: A systematically-biased U5 field (e.g., wrong k_fr4) passes
    hard gates (it's still a valid field) but is flagged by the independent
    scorer because U7's independent solve disagrees with the biased result.

    The scorer's deviation margin catches the bias even though every hard
    gate (status=CLEAN) passes.
    """
    from temper_placer.physics.thermal_fdm import ThermalFDMConfig, solve_thermal_fdm
    from temper_placer.validation.thermal_scorer import ThermalScorer, ThermalScorerConfig

    cell_size = 0.5
    h = 30
    w = 30

    # Correct config
    config_correct = ThermalFDMConfig(
        cell_size_mm=cell_size,
        origin_mm=(0.0, 0.0),
        height_cells=h,
        width_cells=w,
        ambient_C=40.0,
        heatsink_edge="TOP",
        max_cells=3000,
    )

    # Biased config: wrong k_fr4 (3x too high -> under-predicts temperature)
    config_biased = ThermalFDMConfig(
        cell_size_mm=cell_size,
        origin_mm=(0.0, 0.0),
        height_cells=h,
        width_cells=w,
        ambient_C=40.0,
        heatsink_edge="TOP",
        k_fr4=0.9,  # BIAS: 3x the correct 0.3
        k_copper=385.0,
        board_thickness_mm=1.6,
        max_cells=3000,
    )

    # Uniform FR4 board, point source in centre
    copper_grid = np.zeros((h, w), dtype=np.float64)
    Q_field = np.zeros((h, w), dtype=np.float64)
    Q_field[15, 15] = 2.0  # 2 W/mm²

    devices: dict[str, tuple[float, float]] = {}
    power_map: dict[str, float] = {}

    # U5 with biased config — still produces CLEAN result
    u5_biased = solve_thermal_fdm(
        config=config_biased,
        devices=devices,
        power_map=power_map,
        copper_grid=copper_grid,
        Q_field=Q_field,
    )
    assert u5_biased.is_usable, "Biased U5 field should still be usable"

    # U5 with correct config (ground truth comparison)
    u5_correct = solve_thermal_fdm(
        config=config_correct,
        devices=devices,
        power_map=power_map,
        copper_grid=copper_grid,
        Q_field=Q_field,
    )
    assert u5_correct.is_usable

    # Independent scorer evaluates the biased field
    scorer = ThermalScorer(ThermalScorerConfig(
        max_iterations=5000, tolerance_C=0.01, relaxation=1.0,
    ))
    result_biased = scorer.score(
        u5_biased, config_correct,
        devices=devices, power_map=power_map,
        copper_grid=copper_grid, Q_field=Q_field,
    )

    # Score the correct U5 field for baseline
    result_correct = scorer.score(
        u5_correct, config_correct,
        devices=devices, power_map=power_map,
        copper_grid=copper_grid, Q_field=Q_field,
    )

    # The biased field should show LARGER deviation than the correct field
    biased_dev = result_biased.peak_deviation_C
    correct_dev = result_correct.peak_deviation_C

    assert biased_dev > correct_dev * 2.0, (
        f"Biased deviation {biased_dev:.3f}°C should exceed "
        f"correct deviation {correct_dev:.3f}°C by >2x.  "
        f"The independent scorer failed to flag the systematic bias."
    )

    # The correct field agrees with the independent scorer
    assert result_correct.agreement, (
        f"Correct U5 field should agree with independent scorer: "
        f"peak dev={result_correct.peak_deviation_C:.3f}°C, "
        f"mean dev={result_correct.mean_deviation_C:.3f}°C"
    )


# ---------------------------------------------------------------------------
# Edge: Each structural bounding case produces a distinct score
# ---------------------------------------------------------------------------


def test_structural_bounding_cases_distinct():
    """Edge: Each of the three structural bounding cases produces a
    distinct deviation bound, proving they model different uncertainty
    dimensions rather than being three copies of the same estimate.
    """
    from temper_placer.validation.thermal_scorer import STRUCTURAL_BOUNDS

    assert len(STRUCTURAL_BOUNDS) == 3, "Expected exactly 3 structural bounds"

    names = {b.name for b in STRUCTURAL_BOUNDS}
    assert len(names) == 3, "Structural bound names must be unique"
    assert "mounting_hardware_heat_path" in names
    assert "through_plane_gradient_3d" in names
    assert "nonlinear_copper_conductivity" in names

    # Each bound has distinct peak deviation
    deviations = [b.peak_deviation_C for b in STRUCTURAL_BOUNDS]
    assert len(set(deviations)) == len(deviations), (
        f"Peak deviations must be distinct: {deviations}"
    )

    # Each bound is conservative (2D model is optimistic)
    for b in STRUCTURAL_BOUNDS:
        assert b.is_conservative, (
            f"{b.name}: should be conservative (2D model underestimates T)"
        )
        assert b.peak_deviation_C > 0
        assert len(b.description) > 20
        assert len(b.bounding_input) > 20


def test_structural_bound_mounting_hardware():
    """Edge: Mounting-hardware heat path bound models extra heat sinking
    through mounting holes that the 2D model neglects."""
    from temper_placer.validation.thermal_scorer import STRUCTURAL_BOUNDS

    bound = next(b for b in STRUCTURAL_BOUNDS if b.name == "mounting_hardware_heat_path")
    assert bound.is_conservative
    assert bound.peak_deviation_C > 0
    text = (bound.bounding_input + bound.description).lower()
    assert "dirichlet" in text or "mount" in text


def test_structural_bound_through_plane():
    """Edge: 3D through-plane gradient bound models the temperature drop
    across the board thickness."""
    from temper_placer.validation.thermal_scorer import STRUCTURAL_BOUNDS

    bound = next(b for b in STRUCTURAL_BOUNDS if b.name == "through_plane_gradient_3d")
    assert bound.is_conservative
    assert bound.peak_deviation_C > 0
    text = bound.description.lower()
    assert "thickness" in text or "3d" in text or "through" in text


def test_structural_bound_nonlinear():
    """Edge: Nonlinear conductivity bound models temperature-dependent
    material properties."""
    from temper_placer.validation.thermal_scorer import STRUCTURAL_BOUNDS

    bound = next(b for b in STRUCTURAL_BOUNDS if b.name == "nonlinear_copper_conductivity")
    assert bound.is_conservative
    assert bound.peak_deviation_C > 0
    text = bound.description.lower()
    assert "copper" in text or "conductivity" in text


# ---------------------------------------------------------------------------
# Edge: Scorer is deterministic
# ---------------------------------------------------------------------------


def test_scorer_deterministic():
    """Edge: Two runs of the independent scorer on the same inputs produce
    bit-identical results (no RNG, no non-deterministic ordering)."""
    from temper_placer.physics.thermal_fdm import ThermalFDMConfig, solve_thermal_fdm
    from temper_placer.validation.thermal_scorer import ThermalScorer, ThermalScorerConfig

    cell_size = 1.0
    h = 20
    w = 20

    config = ThermalFDMConfig(
        cell_size_mm=cell_size,
        origin_mm=(0.0, 0.0),
        height_cells=h,
        width_cells=w,
        ambient_C=40.0,
        heatsink_edge="TOP",
        max_cells=3000,
    )

    copper_grid = np.zeros((h, w), dtype=np.float64)
    copper_grid[5:15, 5:15] = 1.0
    Q_field = np.zeros((h, w), dtype=np.float64)
    Q_field[10, 10] = 1.5

    devices: dict[str, tuple[float, float]] = {}
    power_map: dict[str, float] = {}

    scorer = ThermalScorer(ThermalScorerConfig(
        max_iterations=500, tolerance_C=0.001, relaxation=1.0,
    ))

    u5_result = solve_thermal_fdm(
        config=config, devices=devices, power_map=power_map,
        copper_grid=copper_grid, Q_field=Q_field,
    )

    result1 = scorer.score(u5_result, config, devices, power_map, copper_grid, Q_field)
    result2 = scorer.score(u5_result, config, devices, power_map, copper_grid, Q_field)

    assert result1.u7_peak_C == result2.u7_peak_C
    assert result1.u7_mean_C == result2.u7_mean_C
    assert result1.peak_deviation_C == result2.peak_deviation_C
    assert result1.convergence_iterations == result2.convergence_iterations


# ---------------------------------------------------------------------------
# Integration: Scorer is a callable consumable by build_scorecard
# ---------------------------------------------------------------------------


def test_scorer_is_callable_for_build_scorecard():
    """Integration: ThermalScorer is callable with the same signature as
    ``score()``, ready to be passed as the ``scorer`` parameter to U2's
    ``build_scorecard``.  The scorer identity tag "independent" confirms it
    is NOT a field (independence guard)."""
    from temper_placer.physics.thermal_fdm import ThermalFDMConfig, solve_thermal_fdm
    from temper_placer.validation.thermal_scorer import (
        STRUCTURAL_INDEPENDENCE_AXIS,
        ThermalScorer,
        ThermalScorerConfig,
        ThermalScoreResult,
    )

    cell_size = 1.0
    h = 15
    w = 15

    config = ThermalFDMConfig(
        cell_size_mm=cell_size,
        origin_mm=(0.0, 0.0),
        height_cells=h,
        width_cells=w,
        ambient_C=40.0,
        heatsink_edge="TOP",
        max_cells=3000,
    )

    copper_grid = np.zeros((h, w), dtype=np.float64)
    Q_field = np.zeros((h, w), dtype=np.float64)
    Q_field[7, 7] = 0.5
    devices: dict[str, tuple[float, float]] = {}
    power_map: dict[str, float] = {}

    u5_result = solve_thermal_fdm(
        config=config, devices=devices, power_map=power_map,
        copper_grid=copper_grid, Q_field=Q_field,
    )

    scorer = ThermalScorer(ThermalScorerConfig(max_iterations=500, tolerance_C=0.01))

    # Verify callable with same signature as score()
    result = scorer(u5_result, config, devices, power_map, copper_grid, Q_field)
    assert isinstance(result, ThermalScoreResult)

    # Independence guard: solver tag is "independent"
    assert result.solver == "independent", (
        f"solver='{result.solver}' — must be 'independent' for the "
        f"independence guard in build_scorecard"
    )

    # Structural axis is documented
    assert len(result.structural_axis) > 50
    assert (
        "Gauss-Seidel" in result.structural_axis
        or "iterative" in result.structural_axis
    )
    assert STRUCTURAL_INDEPENDENCE_AXIS == result.structural_axis

    # Geometry envelope
    assert len(result.geometry_envelope) > 20

    # Structural bounds are present
    assert len(result.structural_bounds) == 3

    # Scorer result is NOT the same type as FieldResult
    from temper_placer.fields.result import FieldResult

    assert not isinstance(result, FieldResult)


# ---------------------------------------------------------------------------
# Edge: Scorer with device-based power
# ---------------------------------------------------------------------------


def test_scorer_with_device_power():
    """Edge: Scorer works with device-based power input (not Q_field)."""
    from temper_placer.physics.thermal_fdm import ThermalFDMConfig, solve_thermal_fdm
    from temper_placer.validation.thermal_scorer import ThermalScorer, ThermalScorerConfig

    cell_size = 1.0
    h = 30
    w = 30

    config = ThermalFDMConfig(
        cell_size_mm=cell_size,
        origin_mm=(0.0, 0.0),
        height_cells=h,
        width_cells=w,
        ambient_C=40.0,
        heatsink_edge="TOP",
        max_cells=3000,
    )

    copper_grid = np.zeros((h, w), dtype=np.float64)
    devices = {"Q1": (15.0, 15.0), "Q2": (25.0, 10.0)}
    power_map = {"Q1": 15.0, "Q2": 7.5}

    u5_result = solve_thermal_fdm(
        config=config, devices=devices, power_map=power_map,
        copper_grid=copper_grid,
    )
    assert u5_result.is_usable

    scorer = ThermalScorer(ThermalScorerConfig(
        max_iterations=2000, tolerance_C=0.05, relaxation=1.2,
    ))
    result = scorer.score(u5_result, config, devices, power_map, copper_grid)

    assert result.u5_peak_C > config.ambient_C, "Should see heating above ambient"
    assert result.u7_peak_C > config.ambient_C, "Independent solve should also see heating"
    assert result.convergence_iterations > 0


# ---------------------------------------------------------------------------
# Edge: empty grid (no heat sources) — both produce ambient flat field
# ---------------------------------------------------------------------------


def test_scorer_no_heat_sources_flat():
    """Edge: With no heat sources, both solvers produce flat ambient field."""
    from temper_placer.physics.thermal_fdm import ThermalFDMConfig, solve_thermal_fdm
    from temper_placer.validation.thermal_scorer import ThermalScorer, ThermalScorerConfig

    config = ThermalFDMConfig(
        cell_size_mm=1.0,
        origin_mm=(0.0, 0.0),
        height_cells=10,
        width_cells=10,
        ambient_C=40.0,
        heatsink_edge="TOP",
        max_cells=3000,
    )

    devices: dict[str, tuple[float, float]] = {}
    power_map: dict[str, float] = {}
    copper_grid = np.zeros((10, 10), dtype=np.float64)

    u5_result = solve_thermal_fdm(
        config=config, devices=devices, power_map=power_map,
        copper_grid=copper_grid,
    )
    assert u5_result.is_usable
    u5_grid = np.asarray(u5_result.field.grid, dtype=np.float64)

    scorer = ThermalScorer(ThermalScorerConfig(
        max_iterations=200, tolerance_C=0.01, relaxation=1.0,
    ))
    u7_grid, _, _ = scorer.solve_independent(
        config, devices=devices, power_map=power_map, copper_grid=copper_grid,
    )

    # Both should be at ambient
    assert abs(float(np.max(u5_grid)) - 40.0) < 0.1
    assert abs(float(np.max(u7_grid)) - 40.0) < 0.1

    result = scorer.score(u5_result, config, devices, power_map, copper_grid)
    assert result.agreement
    assert result.peak_deviation_C < 0.1


# ---------------------------------------------------------------------------
# Edge: Structural axis is well-documented
# ---------------------------------------------------------------------------


def test_structural_independence_documented():
    """Edge: The structural independence axis string is substantial and
    identifies both solver families (iterative Gauss-Seidel vs direct sparse)."""
    from temper_placer.validation.thermal_scorer import STRUCTURAL_INDEPENDENCE_AXIS

    contains_iterative = (
        "Gauss-Seidel" in STRUCTURAL_INDEPENDENCE_AXIS
        or "iterative" in STRUCTURAL_INDEPENDENCE_AXIS
    )
    assert contains_iterative, "Must name the independent method"

    contains_direct = (
        "sparse" in STRUCTURAL_INDEPENDENCE_AXIS.lower()
        or "direct" in STRUCTURAL_INDEPENDENCE_AXIS.lower()
    )
    assert contains_direct, "Must reference U5's method"

    assert len(STRUCTURAL_INDEPENDENCE_AXIS) > 100, (
        "Structural axis documentation must be substantial (>100 chars)"
    )
