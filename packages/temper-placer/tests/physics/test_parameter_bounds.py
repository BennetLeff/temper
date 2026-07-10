"""
Tests for L2 parameter bounds and soundness gate (verified-interval / worst-case).

Covers:
- Monotonicity: T_j INCREASES with P, DECREASES with k_eff, INCREASES with
  T_amb, DECREASES with h_sink — property tests over parameter ranges.
- Worst-case corner: corner T_j >= any random-sample T_j (by monotonicity).
- Soundness gate: corner violates T_j_max but samples don't → "sampled-only".
- All-clear: corner within T_j_max → "sound".
"""

from __future__ import annotations

import numpy as np
import pytest

from temper_placer.physics.thermal_fdm import ThermalFDMConfig, solve_thermal_fdm
from temper_placer.validation.prereg.schema import (
    BecauseThreshold,
    CheapBaseline,
    CostBudget,
    FieldPreregistration,
    KillCriterion,
    ParametricRange,
    PassBar,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mini_prereg(
    power_min: float = 5.0,
    power_max: float = 180.0,
    rjc_min: float = 0.5,
    rjc_max: float = 3.5,
    heatspread_min: float = 5.0,
    heatspread_max: float = 40.0,
) -> FieldPreregistration:
    return FieldPreregistration.model_validate({
        "field_name": "thermal",
        "independent_instrument": "physics_oracle",
        "cheap_baseline": {
            "name": "uniform_heat_spread",
            "description": "Baseline",
            "metric": "thermal_score",
            "target_value": 0.0,
            "because": "Baseline",
        },
        "parametric_ranges": [
            {
                "parameter": "power_dissipation_w",
                "min": power_min,
                "max": power_max,
                "because": "Power sweep range",
            },
            {
                "parameter": "junction_to_case_c_per_w",
                "min": rjc_min,
                "max": rjc_max,
                "because": "R_theta sweep",
            },
            {
                "parameter": "max_heatspread_mm",
                "min": heatspread_min,
                "max": heatspread_max,
                "because": "Heatspread range",
            },
        ],
        "structural_bounding_cases": [
            {"case_name": "single_igbt", "description": "Min config", "because": "Required"},
        ],
        "pass_bar": {
            "margin_gain": {"value": 0.1, "because": "b"},
            "beat_cheap_baseline_by": {"value": 0.05, "because": "b"},
            "across_perturbations": {"value": 5, "because": "b"},
        },
        "kill_criterion": {"description": "Any violation kills", "because": "b"},
        "cost_budget": {
            "max_total_battery_seconds": 3600,
            "max_rounds_budget": 20,
            "field_convergence_round_limit": 5,
            "thermal_grid_cells_max": 10000,
            "target_solve_time_ms_per_field": 5000,
        },
    })


def _mini_fdm_config(
    ambient_C: float = 40.0,
    height_cells: int = 20,
    width_cells: int = 20,
    cell_size_mm: float = 2.0,
) -> ThermalFDMConfig:
    return ThermalFDMConfig(
        cell_size_mm=cell_size_mm,
        origin_mm=(0.0, 0.0),
        height_cells=height_cells,
        width_cells=width_cells,
        ambient_C=ambient_C,
        heatsink_edge="TOP",
        max_cells=5000,
    )


def _peak_T(
    devices: dict[str, tuple[float, float]],
    power_map: dict[str, float],
    fdm_config: ThermalFDMConfig,
    copper_grid: np.ndarray | None = None,
    h_field: np.ndarray | None = None,
) -> float:
    """Run FDM solve and return peak T_j."""
    from temper_placer.physics.thermal_fdm import solve_thermal_fdm

    result = solve_thermal_fdm(
        config=fdm_config,
        devices=devices,
        power_map=power_map,
        copper_grid=copper_grid,
        h_field=h_field,
    )
    assert result.is_usable, f"FDM failed: {result.error_message}"
    assert result.field is not None
    return float(np.max(result.field.grid))


# ---------------------------------------------------------------------------
# Monotonicity tests
# ---------------------------------------------------------------------------


class TestMonotonicity:
    """T_j is monotone in each physics parameter over the operating envelope."""

    def test_Tj_increases_with_power(self):
        """Higher power -> higher T_j (A unchanged, b increases, A^{-1} >= 0)."""
        fdm_config = _mini_fdm_config()
        devices = {"Q1": (20.0, 10.0)}
        copper = np.zeros((20, 20), dtype=np.float64)
        h_field = np.zeros((20, 20), dtype=np.float64)

        T_low = _peak_T(devices, {"Q1": 5.0}, fdm_config, copper_grid=copper, h_field=h_field)
        T_mid = _peak_T(devices, {"Q1": 90.0}, fdm_config, copper_grid=copper, h_field=h_field)
        T_high = _peak_T(devices, {"Q1": 180.0}, fdm_config, copper_grid=copper, h_field=h_field)

        assert T_high > T_mid > T_low, (
            f"Expected T_j to INCREASE with power: "
            f"T(5W)={T_low:.1f}, T(90W)={T_mid:.1f}, T(180W)={T_high:.1f}"
        )

    def test_Tj_decreases_with_conductivity(self):
        """Higher k_eff -> lower T_j (M-matrix ordering property)."""
        fdm_config = _mini_fdm_config()
        devices = {"Q1": (20.0, 10.0)}
        power = {"Q1": 50.0}

        # Pure FR4 (low k) vs copper (high k)
        copper_low = np.zeros((20, 20), dtype=np.float64)
        copper_high = np.full((20, 20), 0.5, dtype=np.float64)
        h_field = np.zeros((20, 20), dtype=np.float64)

        T_low_k = _peak_T(devices, power, fdm_config, copper_grid=copper_low, h_field=h_field)
        T_high_k = _peak_T(devices, power, fdm_config, copper_grid=copper_high, h_field=h_field)

        assert T_high_k < T_low_k, (
            f"Expected T_j to DECREASE with conductivity (copper coverage): "
            f"T(pure_FR4)={T_low_k:.1f}, T(50%_copper)={T_high_k:.1f}"
        )

    def test_Tj_increases_with_ambient(self):
        """Higher T_amb -> higher T_j everywhere."""
        devices = {"Q1": (20.0, 10.0)}
        power = {"Q1": 30.0}
        copper = np.zeros((20, 20), dtype=np.float64)
        h_field = np.zeros((20, 20), dtype=np.float64)

        T_20 = _peak_T(devices, power, _mini_fdm_config(ambient_C=20.0),
                        copper_grid=copper, h_field=h_field)
        T_40 = _peak_T(devices, power, _mini_fdm_config(ambient_C=40.0),
                        copper_grid=copper, h_field=h_field)
        T_60 = _peak_T(devices, power, _mini_fdm_config(ambient_C=60.0),
                        copper_grid=copper, h_field=h_field)

        assert T_60 > T_40 > T_20, (
            f"Expected T_j to INCREASE with ambient: "
            f"T(20C)={T_20:.1f}, T(40C)={T_40:.1f}, T(60C)={T_60:.1f}"
        )

    def test_Tj_decreases_with_h_sink(self):
        """Higher vertical sink -> lower T_j."""
        fdm_config = _mini_fdm_config()
        devices = {"Q1": (20.0, 10.0)}
        power = {"Q1": 50.0}
        copper = np.zeros((20, 20), dtype=np.float64)

        h = fdm_config.height_cells
        w = fdm_config.width_cells
        h_zero = np.zeros((h, w), dtype=np.float64)

        # Moderate vertical sink over the device footprint
        h_moderate = np.zeros((h, w), dtype=np.float64)
        # Device footprint ~5mm square near (20, 10), cell_size=2mm
        # cells: row 4-6, col 9-11
        h_moderate[4:7, 9:12] = 0.01  # W/(K·mm²)

        T_no_sink = _peak_T(devices, power, fdm_config, copper_grid=copper, h_field=h_zero)
        T_with_sink = _peak_T(devices, power, fdm_config, copper_grid=copper, h_field=h_moderate)

        assert T_with_sink < T_no_sink, (
            f"Expected T_j to DECREASE with h_sink: "
            f"T(no_sink)={T_no_sink:.1f}, T(with_sink)={T_with_sink:.1f}"
        )


# ---------------------------------------------------------------------------
# Parameter bounds tests
# ---------------------------------------------------------------------------


class TestParameterBounds:
    """Parameter box building and worst-case corner computation."""

    def test_build_parameter_bounds_from_prereg(self):
        """Build bounds from prereg and verify all are monotone."""
        from temper_placer.physics.parameter_bounds import build_thermal_parameter_bounds

        prereg = _mini_prereg()
        fdm_config = _mini_fdm_config()
        bounds = build_thermal_parameter_bounds(prereg, fdm_config)

        assert len(bounds) >= 5, f"Expected >= 5 bounds, got {len(bounds)}"

        bound_by_name = {b.parameter: b for b in bounds}

        # Power: monotone INCREASING
        power_b = bound_by_name["power_dissipation_w"]
        assert power_b.monotonicity == +1
        assert power_b.worst_case_value == power_b.max

        # Junction-to-case: monotone INCREASING (higher R -> higher T_j)
        rjc_b = bound_by_name["junction_to_case_c_per_w"]
        assert rjc_b.monotonicity == +1
        assert rjc_b.worst_case_value == rjc_b.max

        # Heatspread: monotone DECREASING
        heat_b = bound_by_name["max_heatspread_mm"]
        assert heat_b.monotonicity == -1
        assert heat_b.worst_case_value == heat_b.min

        # Ambient: monotone INCREASING
        amb_b = bound_by_name["ambient_C"]
        assert amb_b.monotonicity == +1
        assert amb_b.worst_case_value == amb_b.max

        # h_sink: monotone DECREASING
        h_b = bound_by_name["h_sink_min"]
        assert h_b.monotonicity == -1
        assert h_b.worst_case_value == 0.0

    def test_worst_case_corner_values(self):
        """Corner picks max for increasing params, min for decreasing."""
        from temper_placer.physics.parameter_bounds import (
            build_thermal_parameter_bounds,
            worst_case_corner,
        )

        prereg = _mini_prereg(
            power_min=5.0, power_max=180.0,
            rjc_min=0.5, rjc_max=3.5,
            heatspread_min=5.0, heatspread_max=40.0,
        )
        fdm_config = _mini_fdm_config(ambient_C=40.0)
        bounds = build_thermal_parameter_bounds(prereg, fdm_config)
        corner = worst_case_corner(bounds)

        assert corner["power_dissipation_w"] == 180.0
        assert corner["junction_to_case_c_per_w"] == 3.5
        assert corner["max_heatspread_mm"] == 5.0  # min heatspread = worst case
        assert corner["ambient_C"] == 50.0  # max ambient
        assert corner["h_sink_min"] == 0.0  # no sink

    def test_monotonicity_proof_is_nonempty(self):
        """The proof text explains all four monotonicity cases."""
        from temper_placer.physics.parameter_bounds import monotonicity_proof

        proof = monotonicity_proof()
        assert len(proof) > 200
        assert "M-matrix" in proof
        assert "INCREASING" in proof
        assert "DECREASING" in proof


# ---------------------------------------------------------------------------
# Worst-case corner test
# ---------------------------------------------------------------------------


class TestWorstCaseCorner:
    """Corner T_j >= random sample T_j (mathematical guarantee)."""

    def test_corner_greater_equal_random_sample(self):
        """T_j at worst-case corner >= T_j at a random interior sample."""
        from temper_placer.physics.parameter_bounds import (
            build_thermal_parameter_bounds,
            worst_case_corner,
        )

        prereg = _mini_prereg()
        fdm_config = _mini_fdm_config(ambient_C=40.0, cell_size_mm=2.0, height_cells=15, width_cells=15)
        devices = {"Q1": (15.0, 10.0)}

        # --- Corner: max power (180W), pure FR4, max ambient (50C), no sink ---
        corner_config = ThermalFDMConfig(
            cell_size_mm=fdm_config.cell_size_mm,
            origin_mm=fdm_config.origin_mm,
            height_cells=fdm_config.height_cells,
            width_cells=fdm_config.width_cells,
            ambient_C=50.0,  # max ambient
            heatsink_edge=fdm_config.heatsink_edge,
            k_fr4=fdm_config.k_fr4,
            k_copper=fdm_config.k_copper,
            board_thickness_mm=fdm_config.board_thickness_mm,
            max_cells=fdm_config.max_cells,
        )
        corner_copper = np.zeros((15, 15), dtype=np.float64)
        corner_h = np.zeros((15, 15), dtype=np.float64)
        T_corner = _peak_T(
            devices, {"Q1": 180.0}, corner_config,
            copper_grid=corner_copper, h_field=corner_h,
        )

        # --- Random interior sample: 30W, 50% copper, 35C ambient, moderate sink ---
        sample_config = ThermalFDMConfig(
            cell_size_mm=fdm_config.cell_size_mm,
            origin_mm=fdm_config.origin_mm,
            height_cells=fdm_config.height_cells,
            width_cells=fdm_config.width_cells,
            ambient_C=35.0,
            heatsink_edge=fdm_config.heatsink_edge,
            k_fr4=fdm_config.k_fr4,
            k_copper=fdm_config.k_copper,
            board_thickness_mm=fdm_config.board_thickness_mm,
            max_cells=fdm_config.max_cells,
        )
        sample_copper = np.full((15, 15), 0.5, dtype=np.float64)
        sample_h = np.full((15, 15), 0.005, dtype=np.float64)  # moderate sink
        T_sample = _peak_T(
            devices, {"Q1": 30.0}, sample_config,
            copper_grid=sample_copper, h_field=sample_h,
        )

        assert T_corner >= T_sample, (
            f"Expected corner T_j ({T_corner:.1f}C) >= random sample "
            f"({T_sample:.1f}C) by monotonicity"
        )


# ---------------------------------------------------------------------------
# Soundness gate tests
# ---------------------------------------------------------------------------


class TestSoundnessGate:
    """The compute_thermal_soundness function returns correct flags."""

    def test_corner_violates_tj_max_flagged_sampled_only(self):
        """When corner T_j > T_j_max, soundness gate flags sampled-only."""
        from temper_placer.physics.parameter_bounds import compute_thermal_soundness

        prereg = _mini_prereg(power_max=180.0)
        fdm_config = _mini_fdm_config(ambient_C=40.0, cell_size_mm=2.0, height_cells=15, width_cells=15)
        devices = {"Q1": (15.0, 10.0)}
        power_map = {"Q1": 50.0}

        # Pure FR4 + max power → very high T_j, should exceed T_j_max=150.
        sr = compute_thermal_soundness(
            prereg=prereg,
            fdm_config=fdm_config,
            devices=devices,
            power_map=power_map,
            T_j_max=150.0,
            copper_grid=None,
            h_field=None,
        )

        assert not sr.is_sound, (
            f"Expected sampled-only, got sound: {sr.detail}"
        )
        assert sr.corner_peak_C > sr.T_j_max_C, (
            f"Corner peak {sr.corner_peak_C:.1f}C should exceed "
            f"T_j_max={sr.T_j_max_C:.1f}C for this test"
        )
        assert sr.all_monotone, (
            f"Expected all parameters monotone, got non-monotone: {sr.non_monotone_params}"
        )

    def test_all_clear_config_passes_soundness(self):
        """When corner T_j <= T_j_max, soundness gate returns 'sound'.

        Uses a physically feasible low-power scenario: a small grid with
        negligible heat source.  Even pure FR4 (no copper) stays well
        below T_j_max of 150 deg-C at sub-milliwatt dissipation.
        (Real induction cookers at 30W+ will always be sampled-only on
        the pure-FR4 corner — this is the gate's honest baseline.)
        """
        from temper_placer.physics.parameter_bounds import compute_thermal_soundness

        # Tiny power: 1 mW on a 5x5 grid with 10mm cells = 50mm x 50mm board
        prereg = _mini_prereg(power_max=0.001)
        fdm_config = _mini_fdm_config(
            ambient_C=25.0, cell_size_mm=10.0, height_cells=5, width_cells=5,
        )
        devices = {"Q1": (25.0, 25.0)}
        power_map = {"Q1": 0.0005}

        sr = compute_thermal_soundness(
            prereg=prereg,
            fdm_config=fdm_config,
            devices=devices,
            power_map=power_map,
            T_j_max=150.0,
            copper_grid=None,
            h_field=None,
        )

        assert sr.is_sound, (
            f"Expected SOUND, got: {sr.detail}"
        )
        assert sr.corner_peak_C <= sr.T_j_max_C, (
            f"Corner peak {sr.corner_peak_C:.1f}C should be <= "
            f"T_j_max={sr.T_j_max_C:.1f}C"
        )
        assert "SOUND" in sr.detail.upper()

    def test_soundness_result_fields(self):
        """ThermalSoundnessResult dataclass has correct defaults."""
        from temper_placer.physics.parameter_bounds import ThermalSoundnessResult

        sr = ThermalSoundnessResult(
            is_sound=True,
            detail="test",
            corner_peak_C=100.0,
            T_j_max_C=150.0,
            all_monotone=True,
            non_monotone_params=[],
        )
        assert sr.is_sound
        assert sr.detail == "test"
        assert sr.corner_peak_C == 100.0
        assert sr.T_j_max_C == 150.0
        assert sr.all_monotone
        assert sr.non_monotone_params == []

    def test_soundness_result_sampled_only(self):
        """ThermalSoundnessResult with non-monotone params includes them."""
        from temper_placer.physics.parameter_bounds import ThermalSoundnessResult

        sr = ThermalSoundnessResult(
            is_sound=False,
            detail="sampled-only",
            corner_peak_C=500.0,
            T_j_max_C=150.0,
            all_monotone=False,
            non_monotone_params=["unknown_param"],
        )
        assert not sr.is_sound
        assert "unknown_param" in sr.non_monotone_params
        assert not sr.all_monotone

    def test_unknown_param_is_non_monotone(self):
        """An unclassifiable parameter gets monotonicity=0."""
        from temper_placer.physics.parameter_bounds import build_thermal_parameter_bounds

        prereg = FieldPreregistration.model_validate({
            "field_name": "test",
            "independent_instrument": "o",
            "cheap_baseline": {
                "name": "c", "description": "d", "metric": "m",
                "target_value": 0.0, "because": "b",
            },
            "parametric_ranges": [
                {
                    "parameter": "mystery_param",
                    "min": 0.0,
                    "max": 100.0,
                    "because": "unknown physics",
                },
            ],
            "structural_bounding_cases": [
                {"case_name": "c", "description": "d", "because": "b"},
            ],
            "pass_bar": {
                "margin_gain": {"value": 0.1, "because": "b"},
                "beat_cheap_baseline_by": {"value": 0.05, "because": "b"},
                "across_perturbations": {"value": 5, "because": "b"},
            },
            "kill_criterion": {"description": "k", "because": "b"},
            "cost_budget": {
                "max_total_battery_seconds": 3600,
                "max_rounds_budget": 20,
                "field_convergence_round_limit": 5,
                "thermal_grid_cells_max": 10000,
                "target_solve_time_ms_per_field": 5000,
            },
        })

        bounds = build_thermal_parameter_bounds(prereg)
        mystery = [b for b in bounds if b.parameter == "mystery_param"]
        assert len(mystery) == 1
        assert mystery[0].monotonicity == 0
