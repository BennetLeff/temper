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
from hypothesis import given, settings
from hypothesis import strategies as st

# ---------------------------------------------------------------------------
# K1: Closed-form analytic 1D bar — both U5 and U7 must match analytic
# ---------------------------------------------------------------------------


@pytest.mark.k1
def test_independent_scorer_matches_analytic():
    """K1: Both U5 (direct sparse solve) and U7 (convective-boundary FDM)
    match the closed-form 1D parabolic profile within 2% at peak.

    This is the third independent reference (analytic solution) — proving
    that two structurally different models converge to the same correct
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

    # U7: independent convective-boundary solve (sparse-direct, no iteration)
    scorer = ThermalScorer(ThermalScorerConfig(h=10.0))
    u7_grid, iterations, residual = scorer.solve_independent(
        config,
        devices=devices,
        power_map=power_map,
        copper_grid=copper_grid,
        Q_field=Q_field,
    )

    # Analytic: T(y) = T_top + Q/(2*k_eff) * (H^2 - y^2)
    col = width_cells // 2
    T_u5_center = u5_grid[:, col]
    T_u7_center = u7_grid[:, col]
    y_cells = np.arange(height_cells)
    y_world = y_cells * cell_size + cell_size / 2
    T_analytic = T_top + Q_uniform / (2 * k_eff_target) * (H**2 - y_world**2)

    # Both independently match analytic within 2% at each point
    u5_rel_err = np.max(np.abs(T_u5_center - T_analytic) / np.maximum(np.abs(T_analytic), 1e-6))
    u7_rel_err = np.max(np.abs(T_u7_center - T_analytic) / np.maximum(np.abs(T_analytic), 1e-6))

    assert u5_rel_err < 0.02, f"U5 relative error {u5_rel_err:.4f} exceeds 2%"
    assert u7_rel_err < 0.02, f"U7 relative error {u7_rel_err:.4f} exceeds 2%"

    # U5 and U7 agree with each other (both match analytic)
    u5_u7_max_diff = float(np.max(np.abs(u7_grid - u5_grid)))
    assert u5_u7_max_diff < 0.5, (
        f"U5-U7 max diff {u5_u7_max_diff:.3f}°C — should agree on well-conditioned problem"
    )


# ---------------------------------------------------------------------------
# Falsifiability: High-conductivity-contrast geometry makes them disagree
# ---------------------------------------------------------------------------


def test_falsifiability_high_contrast_disagreement():
    """Falsifiability: On a high-Biot-number geometry (small board, pure FR4,
    point source), the convective-boundary U7 model produces a measurably
    different field from U5's adiabatic-Neumann model because heat can leave
    through the three convective edges (U5 is adiabatic there).

    The assertion: max|U7 - U5| > 1.0 deg-C.  This cannot happen if both
    models share the same boundary physics — two different numerical solvers
    on the same h=0 PDE would produce identical fields.  The disagreement
    proves model independence (genuinely different boundary conditions).

    U7 uses a sparse-direct solve (SuperLU), not an iterative solver.
    Falsifiability is driven by the convective boundary physics, not by
    a bounded iteration budget.
    """
    from temper_placer.physics.thermal_fdm import ThermalFDMConfig, solve_thermal_fdm
    from temper_placer.validation.thermal_scorer import (
        FALSIFIABILITY_THRESHOLD_C,
        ThermalScorer,
        ThermalScorerConfig,
        falsifiability_assertion,
    )

    # Small board (30 mm square) to make edge convection significant
    # relative to the board area — higher Biot number.
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

    # Pure FR4 board (no copper) — convective cooling dominates more when
    # in-plane conduction is weak.
    copper_grid = np.zeros((h, w), dtype=np.float64)

    # Point heat source near centre, away from the heatsink (TOP) edge.
    Q_field = np.zeros((h, w), dtype=np.float64)
    Q_field[12, 15] = 1.0

    devices: dict[str, tuple[float, float]] = {}
    power_map: dict[str, float] = {}

    # U5: direct sparse solve with adiabatic Neumann at non-heatsink edges
    u5_result = solve_thermal_fdm(
        config=config,
        devices=devices,
        power_map=power_map,
        copper_grid=copper_grid,
        Q_field=Q_field,
    )
    assert u5_result.is_usable
    u5_grid = np.asarray(u5_result.field.grid, dtype=np.float64)

    # U7: convective-boundary (Robin BC) direct solve
    scorer = ThermalScorer(ThermalScorerConfig(h=10.0))
    u7_grid, _iterations, _residual = scorer.solve_independent(
        config,
        devices=devices,
        power_map=power_map,
        copper_grid=copper_grid,
        Q_field=Q_field,
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
        f"max|U7-U5| = {max_diff:.3f}°C <= {FALSIFIABILITY_THRESHOLD_C}°C threshold"
    )


# ---------------------------------------------------------------------------
# Error: Systematically-biased field caught by independent scorer
# ---------------------------------------------------------------------------


def test_biased_field_caught_by_independent_scorer():
    """Error: A systematically-biased U5 field (e.g., wrong k_fr4) passes
    hard gates (it's still a valid field) but is flagged by the independent
    scorer because U7's convective-boundary solve disagrees with the biased
    result *much more* than it does with the correctly-configured field.

    U5 and U7 have genuinely different boundary physics (adiabatic vs
    convective), so their fields disagree even on a correct config.  The
    scorer's deviation margin catches the bias by a wider margin.
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
    scorer = ThermalScorer(ThermalScorerConfig(h=10.0))
    result_biased = scorer.score(
        u5_biased,
        config_correct,
        devices=devices,
        power_map=power_map,
        copper_grid=copper_grid,
        Q_field=Q_field,
    )

    # Score the correct U5 field for baseline
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
        f"Biased deviation {biased_dev:.3f}°C should exceed "
        f"correct deviation {correct_dev:.3f}°C by >2x.  "
        f"The independent scorer failed to flag the systematic bias."
    )

    # The correct field: U5 and U7 have different boundary physics
    # (adiabatic vs convective), so agreement is NOT expected.
    # The biased field should still show *larger* deviation than the
    # correct field — that's how the scorer catches systematic bias.
    assert not result_correct.agreement, (
        f"U5 (adiabatic) and U7 (convective) should disagree on boundary: "
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
        assert b.is_conservative, f"{b.name}: should be conservative (2D model underestimates T)"
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
    assert result1.convergence_iterations == result2.convergence_iterations


# ---------------------------------------------------------------------------
# Integration: Scorer is a callable consumable by build_scorecard
# ---------------------------------------------------------------------------


def test_scorer_is_callable_for_build_scorecard():
    """Integration: ThermalScorer is callable with the same signature as
    ``score()``, ready to be passed as the ``scorer`` parameter to U2's
    ``build_scorecard``.  The scorer identity tag "independent" confirms it
    is NOT a field (independence guard).

    The structural axis must reference the convective-boundary (Robin BC)
    model to document model independence.
    """
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
        config=config,
        devices=devices,
        power_map=power_map,
        copper_grid=copper_grid,
        Q_field=Q_field,
    )

    scorer = ThermalScorer(ThermalScorerConfig(h=10.0))

    # Verify callable with same signature as score()
    result = scorer(u5_result, config, devices, power_map, copper_grid, Q_field)
    assert isinstance(result, ThermalScoreResult)

    # Independence guard: solver tag is "independent"
    assert result.solver == "independent", (
        f"solver='{result.solver}' — must be 'independent' for the "
        f"independence guard in build_scorecard"
    )

    # Structural axis documents the convective-boundary (Robin BC) model
    assert len(result.structural_axis) > 50
    assert "convective" in result.structural_axis.lower() or "Robin" in result.structural_axis
    assert result.structural_axis == STRUCTURAL_INDEPENDENCE_AXIS

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
        config=config,
        devices=devices,
        power_map=power_map,
        copper_grid=copper_grid,
    )
    assert u5_result.is_usable

    scorer = ThermalScorer(ThermalScorerConfig(h=10.0))
    result = scorer.score(u5_result, config, devices, power_map, copper_grid)

    assert result.u5_peak_C > config.ambient_C, "Should see heating above ambient"
    assert result.u7_peak_C > config.ambient_C, "Independent solve should also see heating"
    assert result.convergence_iterations == 0, (
        "Direct solve produces 0 iterations (not an iterative solver)"
    )


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
        config=config,
        devices=devices,
        power_map=power_map,
        copper_grid=copper_grid,
    )
    assert u5_result.is_usable
    u5_grid = np.asarray(u5_result.field.grid, dtype=np.float64)

    scorer = ThermalScorer(ThermalScorerConfig(h=10.0))
    u7_grid, _, _ = scorer.solve_independent(
        config,
        devices=devices,
        power_map=power_map,
        copper_grid=copper_grid,
    )

    # Both should be at ambient
    assert abs(float(np.max(u5_grid)) - 40.0) < 0.1
    assert abs(float(np.max(u7_grid)) - 40.0) < 0.1

    result = scorer.score(u5_result, config, devices, power_map, copper_grid)
    assert result.agreement
    assert result.peak_deviation_C < 0.1


# ---------------------------------------------------------------------------
# Fail-closed: UNMEASURED field raises FieldNotReadyError
# ---------------------------------------------------------------------------


def test_score_unmeasured_field_raises():
    """Fail-closed: ``ThermalScorer.score()`` must raise ``FieldNotReadyError``
    when the U5 ``FieldResult`` is ``UNMEASURED`` (field=None).

    UNMEASURED means 'could not measure,' NOT '0 deg-C everywhere.'
    The scorer must never silently substitute a flat zero grid.
    """
    from temper_placer.fields.result import FieldNotReadyError, FieldResult
    from temper_placer.physics.thermal_fdm import ThermalFDMConfig
    from temper_placer.placer.cp_sat.gates import GateResult, GateStatus
    from temper_placer.validation.thermal_scorer import ThermalScorer, ThermalScorerConfig

    config = ThermalFDMConfig(
        cell_size_mm=1.0,
        origin_mm=(0.0, 0.0),
        height_cells=10,
        width_cells=10,
        ambient_C=40.0,
        heatsink_edge="TOP",
    )

    gate_result = GateResult(
        status=GateStatus.UNMEASURED,
        error_message="SPICE not installed; cannot compute thermal field",
    )
    u5_result = FieldResult(gate_result=gate_result, field=None)

    scorer = ThermalScorer(ThermalScorerConfig(h=10.0))

    with pytest.raises(FieldNotReadyError, match=r"UNMEASURED.*0 deg-C"):
        scorer.score(
            u5_result,
            config,
            devices={},
            power_map={},
            copper_grid=np.zeros((10, 10), dtype=np.float64),
            Q_field=np.zeros((10, 10), dtype=np.float64),
        )


# ---------------------------------------------------------------------------
# Edge: Structural axis is well-documented
# ---------------------------------------------------------------------------


def test_structural_independence_documented():
    """Edge: The structural independence axis string is substantial and
    identifies the convective-boundary (Robin BC) model vs U5's adiabatic
    Neumann model."""
    from temper_placer.validation.thermal_scorer import STRUCTURAL_INDEPENDENCE_AXIS

    contains_convective = (
        "convective" in STRUCTURAL_INDEPENDENCE_AXIS.lower()
        or "Robin" in STRUCTURAL_INDEPENDENCE_AXIS
    )
    assert contains_convective, "Must name the independent method (convective-boundary / Robin BC)"

    contains_direct = (
        "sparse" in STRUCTURAL_INDEPENDENCE_AXIS.lower()
        or "direct" in STRUCTURAL_INDEPENDENCE_AXIS.lower()
    )
    assert contains_direct, "Must reference U5's method"

    assert len(STRUCTURAL_INDEPENDENCE_AXIS) > 100, (
        "Structural axis documentation must be substantial (>100 chars)"
    )


# ---------------------------------------------------------------------------
# PBT guard: scorer must not produce runaway temperatures
# ---------------------------------------------------------------------------


@pytest.mark.property
@given(
    power=st.floats(1.0, 100.0),
    copper_frac=st.floats(0.0, 1.0),
    ambient_C=st.floats(20.0, 60.0),
)
@settings(max_examples=50)
def test_scorer_no_runaway_temperatures(power, copper_frac, ambient_C):
    """PBT guard: for any physically-plausible power/copper/ambient,
    the scorer must NOT produce a temperature far above the FDM
    (a realistic ceiling — no runaway solves)."""
    from temper_placer.physics.heat_removal import build_h_field
    from temper_placer.physics.thermal_fdm import ThermalFDMConfig, solve_thermal_fdm
    from temper_placer.physics.tj_cross_check import DeviceThermalConfig
    from temper_placer.validation.thermal_scorer import ThermalScorer, ThermalScorerConfig

    config = ThermalFDMConfig(
        cell_size_mm=1.0,
        origin_mm=(0.0, 0.0),
        height_cells=20,
        width_cells=20,
        ambient_C=ambient_C,
        heatsink_edge="BOTTOM",
    )
    copper = np.full((20, 20), copper_frac, dtype=np.float64)
    dt = DeviceThermalConfig(
        name="Q1",
        R_theta_jc=0.6,
        R_theta_cs=0.25,
        R_theta_sa=1.0,
        T_j_max=150.0,
        R_jc_because="test",
        R_cs_because="test",
        R_sa_because="test",
        T_j_max_because="test",
    )
    h_field = build_h_field(
        config=config,
        devices={"Q1": (10.0, 5.0)},
        device_thermal={"Q1": dt},
    )
    u5 = solve_thermal_fdm(
        config=config,
        devices={"Q1": (10.0, 5.0)},
        power_map={"Q1": power},
        copper_grid=copper,
        h_field=h_field,
    )
    scorer = ThermalScorer(ThermalScorerConfig(max_iterations=500))
    score = scorer.score(
        u5_result=u5,
        fdm_config=config,
        devices={"Q1": (10.0, 5.0)},
        power_map={"Q1": power},
        copper_grid=copper,
        h_field=h_field,
    )
    # Conservative ceiling: 10x the FDM peak (generous — catches the 59k C bug
    # which was ~300x the FDM peak of 223 C). With h_field both models use
    # the same through-plane sink, so they should agree within a factor.
    u5_peak = u5.field.grid.max() if u5.field is not None else 0.0
    assert score.u7_peak_C < max(50.0, u5_peak * 10.0), (
        f"scorer runaway: u7_peak={score.u7_peak_C:.0f} C "
        f"vs u5_peak={u5_peak:.0f} C "
        f"(power={power:.0f}W, copper={copper_frac:.2f}, amb={ambient_C:.0f}C)"
    )
