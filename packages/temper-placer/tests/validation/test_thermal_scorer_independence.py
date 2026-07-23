"""
Tests for U7 model-independent thermal scorer (U3 — genuine model independence).

Covers:
- K1: U5 and U7 agree on closed-form 1D bar via independent methods
- Falsifiability: High-Biot-number geometry — U5 vs U7 disagree beyond threshold
- Error: Systematically-biased U5 field flagged by U7 even though hard gates pass
- Integration (R19): U7 plugs into build_scorecard as scorer, never as field
- Determinism: Same inputs -> bit-identical results (sparse-direct solve)
"""

from __future__ import annotations

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# K1: Closed-form analytic 1D bar — both U5 and U7 match analytic
# ---------------------------------------------------------------------------


@pytest.mark.k1
def test_independent_model_matches_analytic():
    """K1: Both U5 (adiabatic edges) and U7 (convective edges) match the
    closed-form 1D parabolic profile on a narrow bar where side-edge effects
    are minimal.

    The board is tall and narrow (5 cells wide), so the side-edge convection
    in U7 affects only the outermost columns.  The center-column temperature
    profile is dominated by the Dirichlet heatsink at the top and uniform
    volumetric heating — both models independently converge to the analytic
    solution within 2% at the center.
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

    # U5: adiabatic edges, direct sparse solve
    u5_result = solve_thermal_fdm(
        config=config,
        devices=devices,
        power_map=power_map,
        copper_grid=copper_grid,
        Q_field=Q_field,
    )
    assert u5_result.is_usable
    u5_grid = np.asarray(u5_result.field.grid, dtype=np.float64)

    # U7: convective edges, direct sparse solve (model-independent)
    scorer = ThermalScorer(ThermalScorerConfig(h=10.0))
    u7_grid, iterations, residual = scorer.solve_independent(
        config,
        devices=devices,
        power_map=power_map,
        copper_grid=copper_grid,
        Q_field=Q_field,
    )

    # Direct solve: no iterations
    assert iterations == 0
    assert residual == 0.0

    # Analytic: T(y) = T_top + Q/(2*k_eff) * (H^2 - y^2)
    col = width_cells // 2
    T_u5_center = u5_grid[:, col]
    T_u7_center = u7_grid[:, col]
    y_cells = np.arange(height_cells)
    y_world = y_cells * cell_size + cell_size / 2
    T_analytic = T_top + Q_uniform / (2 * k_eff_target) * (H**2 - y_world**2)

    u5_rel_err = np.max(np.abs(T_u5_center - T_analytic) / np.maximum(np.abs(T_analytic), 1e-6))
    u7_rel_err = np.max(np.abs(T_u7_center - T_analytic) / np.maximum(np.abs(T_analytic), 1e-6))

    assert u5_rel_err < 0.02, f"U5 relative error {u5_rel_err:.4f} exceeds 2%"
    assert u7_rel_err < 0.02, f"U7 relative error {u7_rel_err:.4f} exceeds 2%"

    # Both agree with each other on the center column
    u5_u7_max_diff = float(np.max(np.abs(u7_grid - u5_grid)))
    assert u5_u7_max_diff < 2.0, (
        f"U5-U7 max diff {u5_u7_max_diff:.3f} deg-C "
        f"— should agree within tolerance on centre column of narrow bar"
    )


# ---------------------------------------------------------------------------
# Falsifiability: High-Biot-number geometry — models DIVERGE
# ---------------------------------------------------------------------------


def test_falsifiability_convective_vs_adiabatic():
    """Falsifiability: On a high-Biot-number geometry (10x10 mm pure-FR4
    board, point heat source), the convective-boundary model (U7) produces
    a measurably LOWER temperature field than U5's adiabatic model because
    heat can leave through the three non-heatsink edges via convection.

    This proves genuine model independence: two numerical-discretisation
    approaches to the same h=0 PDE would produce identical fields on this
    input; the disagreement comes from the convective boundary physics
    that U5 omits.

    Both models are correct under their own assumptions: U5 is correct
    for a board with thermally insulated edges; U7 is correct for a board
    in still air with natural convection at the edges.  The disagreement
    is NOT a bug in either model — it is evidence of model divergence.
    """
    from temper_placer.physics.thermal_fdm import ThermalFDMConfig, solve_thermal_fdm
    from temper_placer.validation.thermal_scorer import (
        CONVECTION_COEFFICIENT_H_W_PER_M2K,
        FALSIFIABILITY_THRESHOLD_C,
        ThermalScorer,
        ThermalScorerConfig,
        falsifiability_assertion,
    )

    cell_size = 1.0  # mm
    h = 10
    w = 10

    config = ThermalFDMConfig(
        cell_size_mm=cell_size,
        origin_mm=(0.0, 0.0),
        height_cells=h,
        width_cells=w,
        ambient_C=40.0,
        heatsink_edge="TOP",
        max_cells=5000,
    )

    # Pure FR4, no copper — low k_eff makes convection significant
    copper_grid = np.zeros((h, w), dtype=np.float64)

    # Point heat source in centre: 1 W/mm^2 at the centre cell
    Q_field = np.zeros((h, w), dtype=np.float64)
    Q_field[5, 5] = 1.0

    devices: dict[str, tuple[float, float]] = {}
    power_map: dict[str, float] = {}

    # U5: adiabatic edges (heat can only leave through heatsink at TOP)
    u5_result = solve_thermal_fdm(
        config=config,
        devices=devices,
        power_map=power_map,
        copper_grid=copper_grid,
        Q_field=Q_field,
    )
    assert u5_result.is_usable
    u5_grid = np.asarray(u5_result.field.grid, dtype=np.float64)

    # U7: convective edges (heat can also leave through BOTTOM, LEFT, RIGHT)
    scorer = ThermalScorer(
        ThermalScorerConfig(
            h=CONVECTION_COEFFICIENT_H_W_PER_M2K,
        )
    )
    u7_grid, iterations, _residual = scorer.solve_independent(
        config,
        devices=devices,
        power_map=power_map,
        copper_grid=copper_grid,
        Q_field=Q_field,
    )

    assert iterations == 0, "Direct solve should report 0 iterations"

    # U7 should be COOLER overall (heat loss through convective edges)
    assert float(np.mean(u7_grid)) < float(np.mean(u5_grid)), (
        f"U7 mean {float(np.mean(u7_grid)):.2f} should be lower than "
        f"U5 mean {float(np.mean(u5_grid)):.2f} — convection removes heat"
    )

    # Falsifiability: they must disagree beyond the threshold
    max_diff = float(np.max(np.abs(u7_grid - u5_grid)))
    assert falsifiability_assertion(u5_grid, u7_grid), (
        f"Falsifiability FAILED: max|U7-U5| = {max_diff:.3f} deg-C, "
        f"threshold = {FALSIFIABILITY_THRESHOLD_C} deg-C. "
        f"U5 and U7 produced essentially identical fields — "
        f"the convective boundary term had no measurable effect."
    )

    assert max_diff > FALSIFIABILITY_THRESHOLD_C, (
        f"max|U7-U5| = {max_diff:.3f} deg-C <= {FALSIFIABILITY_THRESHOLD_C} deg-C threshold"
    )


# ---------------------------------------------------------------------------
# Error: Systematically-biased U5 field caught by independent scorer
# ---------------------------------------------------------------------------


def test_biased_field_caught_by_independent_model():
    """Error: A systematically-biased U5 field (wrong k_fr4 — 3x too high,
    causing under-prediction of temperature) passes hard gates (status=CLEAN)
    but is flagged by the independent convective-boundary scorer.

    We use a narrow (5-cell-wide) bar where heat transfer is dominated by
    the Dirichlet heatsink at the top, so the convective edge effect on the
    centre-column temperature is small.  This lets the correct U5 and U7
    agree well, while the biased U5 deviates substantially.

    The scorer's peak deviation rises substantially for the biased field
    compared to the correct field, demonstrating that the independent model
    catches systematic errors that internal consistency checks miss.
    """
    from temper_placer.physics.thermal_fdm import ThermalFDMConfig, solve_thermal_fdm
    from temper_placer.validation.thermal_scorer import ThermalScorer, ThermalScorerConfig

    cell_size = 0.5
    height_cells = 40
    width_cells = 5

    # Use the K1 uniform-bar configuration so centre column is analytic-close
    k_eff_target = 1.0
    board_thickness = 1.6
    k_fr4_val = k_eff_target / (board_thickness * 1e-3)
    T_top = 40.0

    # Correct config
    config_correct = ThermalFDMConfig(
        cell_size_mm=cell_size,
        origin_mm=(0.0, 0.0),
        height_cells=height_cells,
        width_cells=width_cells,
        ambient_C=T_top,
        heatsink_edge="TOP",
        k_fr4=k_fr4_val,
        k_copper=k_fr4_val,
        board_thickness_mm=board_thickness,
        max_cells=3000,
    )

    # Biased config: 3x wrong k_fr4 -> under-predicts temperature
    config_biased = ThermalFDMConfig(
        cell_size_mm=cell_size,
        origin_mm=(0.0, 0.0),
        height_cells=height_cells,
        width_cells=width_cells,
        ambient_C=T_top,
        heatsink_edge="TOP",
        k_fr4=k_fr4_val * 3.0,  # BIAS: 3x the correct value
        k_copper=k_fr4_val * 3.0,
        board_thickness_mm=board_thickness,
        max_cells=3000,
    )

    # Uniform heating (same as K1 analytic)
    Q_uniform = 0.1
    Q_field = np.full((height_cells, width_cells), Q_uniform, dtype=np.float64)
    copper_grid = np.zeros((height_cells, width_cells), dtype=np.float64)
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

    # Independent scorer evaluates both using CORRECT config
    scorer = ThermalScorer(ThermalScorerConfig(h=10.0))

    result_biased = scorer.score(
        u5_biased,
        config_correct,
        devices=devices,
        power_map=power_map,
        copper_grid=copper_grid,
        Q_field=Q_field,
    )

    result_correct = scorer.score(
        u5_correct,
        config_correct,
        devices=devices,
        power_map=power_map,
        copper_grid=copper_grid,
        Q_field=Q_field,
    )

    # The biased field should show LARGER deviation than the correct field
    biased_dev = result_biased.peak_deviation_C
    correct_dev = result_correct.peak_deviation_C

    assert biased_dev > correct_dev * 2.0, (
        f"Biased deviation {biased_dev:.3f} deg-C should exceed "
        f"correct deviation {correct_dev:.3f} deg-C by >2x.  "
        f"The independent scorer failed to flag the systematic bias."
    )

    # The correct field agrees with the independent scorer
    assert result_correct.agreement, (
        f"Correct U5 field should agree with independent scorer on "
        f"narrow bar (convection negligible on centre): "
        f"peak dev={result_correct.peak_deviation_C:.3f} deg-C, "
        f"mean dev={result_correct.mean_deviation_C:.3f} deg-C"
    )


# ---------------------------------------------------------------------------
# Integration (R19): U7 plugs into build_scorecard as scorer, not field
# ---------------------------------------------------------------------------


def test_scorer_plugs_into_build_scorecard():
    """Integration (R19): ThermalScorer is callable with the signature
    expected by ``build_scorecard``.

    The scorer identity tag "independent" confirms it is NOT a field
    (independence guard).  The scorer result exposes shared/independent
    assumption lists for auditability.
    """
    from temper_placer.physics.thermal_fdm import ThermalFDMConfig, solve_thermal_fdm
    from temper_placer.validation.thermal_scorer import (
        INDEPENDENT_ASSUMPTIONS,
        SHARED_ASSUMPTIONS,
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
        config=config,
        devices=devices,
        power_map=power_map,
        copper_grid=copper_grid,
        Q_field=Q_field,
    )

    scorer = ThermalScorer(ThermalScorerConfig(h=10.0))

    # Verify callable with same signature as build_scorecard expects
    result = scorer(u5_result, config, devices, power_map, copper_grid, Q_field)
    assert isinstance(result, ThermalScoreResult)

    # Independence guard: solver tag is "independent"
    assert result.solver == "independent", (
        f"solver='{result.solver}' — must be 'independent' for the "
        f"independence guard in build_scorecard"
    )

    # Scorer identity
    assert result.scorer_id == "thermal-convective-fdm"

    # Structural axis documents model independence (convective boundary)
    assert (
        "convective" in result.structural_axis.lower() or "robin" in result.structural_axis.lower()
    ), "Structural axis must document the convective boundary model"
    assert len(result.structural_axis) > 100
    assert result.structural_axis == STRUCTURAL_INDEPENDENCE_AXIS

    # Geometry envelope is documented
    assert len(result.geometry_envelope) > 20

    # Structural bounds are present
    assert len(result.structural_bounds) == 3

    # Shared and independent assumptions are documented
    assert len(result.shared_assumptions) >= 5, (
        f"Expected at least 5 shared assumptions, got {len(result.shared_assumptions)}"
    )
    assert len(result.independent_assumptions) == 2, (
        f"Expected 2 independent assumptions (U7 convection, U5 adiabatic), "
        f"got {len(result.independent_assumptions)}"
    )

    # Verify the module-level exports match
    assert result.shared_assumptions == SHARED_ASSUMPTIONS
    assert result.independent_assumptions == INDEPENDENT_ASSUMPTIONS

    # Scorer result is NOT a FieldResult (it goes in the scorer slot)
    from temper_placer.fields.result import FieldResult

    assert not isinstance(result, FieldResult)

    # Direct solve: iterations and residual are 0
    assert result.convergence_iterations == 0
    assert result.residual_C == 0.0


# ---------------------------------------------------------------------------
# Determinism: Same inputs -> bit-identical results
# ---------------------------------------------------------------------------


def test_scorer_deterministic():
    """Determinism: Two runs of the independent scorer on the same inputs
    produce bit-identical results.  The sparse-direct SuperLU solver has
    no RNG, no iteration budget, no non-deterministic ordering."""
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

    scorer = ThermalScorer(ThermalScorerConfig(h=10.0))

    u5_result = solve_thermal_fdm(
        config=config,
        devices=devices,
        power_map=power_map,
        copper_grid=copper_grid,
        Q_field=Q_field,
    )

    result1 = scorer.score(u5_result, config, devices, power_map, copper_grid, Q_field)
    result2 = scorer.score(u5_result, config, devices, power_map, copper_grid, Q_field)

    assert result1.u7_peak_C == result2.u7_peak_C
    assert result1.u7_mean_C == result2.u7_mean_C
    assert result1.peak_deviation_C == result2.peak_deviation_C
    assert result1.max_cell_deviation_C == result2.max_cell_deviation_C
    assert result1.convergence_iterations == result2.convergence_iterations


# ---------------------------------------------------------------------------
# Shared / independent assumption audit
# ---------------------------------------------------------------------------


def test_shared_assumptions_documented():
    """Edge: The shared-assumptions list is well-formed and acknowledges
    known limitations."""
    from temper_placer.validation.thermal_scorer import (
        INDEPENDENT_ASSUMPTIONS,
        SHARED_ASSUMPTIONS,
    )

    assert len(SHARED_ASSUMPTIONS) >= 5

    # Shared assumptions must mention key modelling simplifications
    shared_text = " ".join(SHARED_ASSUMPTIONS).lower()
    assert "conduction" in shared_text or "conduct" in shared_text
    assert "2d" in shared_text or "3-d" in shared_text or "plane" in shared_text
    assert "isotropic" in shared_text

    # Independent assumptions: U7 convective, U5 adiabatic
    assert len(INDEPENDENT_ASSUMPTIONS) == 2
    ind_text = " ".join(INDEPENDENT_ASSUMPTIONS).lower()
    assert "convect" in ind_text or "robin" in ind_text, (
        "Independent assumptions must mention the convective boundary"
    )
    assert "adiabat" in ind_text or "neumann" in ind_text, (
        "Independent assumptions must mention U5's adiabatic boundary"
    )


# ---------------------------------------------------------------------------
# Convection coefficient is documented and physically grounded
# ---------------------------------------------------------------------------


def test_convection_coefficient_grounded():
    """Edge: The convection coefficient is documented with its physical
    grounding and is a fixed value, never tuned."""
    from temper_placer.validation.thermal_scorer import CONVECTION_COEFFICIENT_H_W_PER_M2K

    assert CONVECTION_COEFFICIENT_H_W_PER_M2K == 10.0, (
        f"h = {CONVECTION_COEFFICIENT_H_W_PER_M2K} — must be the fixed "
        f"physically-grounded value 10.0 W/(m^2.K)"
    )
