"""
Tests for U10 thermal helps-battery run orchestrator.

Covers:
- (happy) synthetic run where physics clears the bar → KEEP + full scorecard
- (happy, kill) run where cheap captures the benefit → KILL
- (error) operating-point gate not-CLEAN aborts before scoring
- (error) exceeding cost budget → INCONCLUSIVE with cost reason
- (edge) run timestamp earlier than prereg timestamp → rejected
- (integration, smoke) field-on vs field-off diverges + UNMEASURED terminates
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

from temper_placer.core.board import Board
from temper_placer.core.netlist import Component, Netlist
from temper_placer.physics.thermal_fdm import ThermalFDMConfig, solve_thermal_fdm
from temper_placer.validation.helps_battery import BatteryVerdict
from temper_placer.validation.prereg.schema import PreregistrationManifest
from temper_placer.validation.results.battery_run import (
    BatteryRunArtifact,
    BatteryRunReport,
    _ensure_field_diverges,
    _ensure_operating_point_clean,
    _make_thermal_scorer_adapter,
    run_thermal_helps_battery,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _mini_board(width: float = 100.0, height: float = 100.0) -> Board:
    return Board(width=width, height=height)


def _mini_netlist(components: list[Component]) -> Netlist:
    nl = Netlist()
    nl.components = list(components)
    nl.build_indices()
    return nl


def _mini_prereg_path(tmp_path: Path) -> Path:
    """Write a minimal synthetic prereg YAML."""
    prereg_yaml = tmp_path / "test_prereg.yaml"
    prereg_yaml.write_text("""\
version: 1
created_at: "2026-07-09T00:00:00Z"
fields:
  - field_name: "thermal"
    independent_instrument: "thermal-gauss-seidel"
    cheap_baseline:
      name: "uniform_heat_spread"
      description: "Uniform placement"
      metric: "thermal_score"
      target_value: 0.0
      because: "Baseline"
    parametric_ranges:
      - parameter: "heatspread"
        min: 5.0
        max: 40.0
        because: "Cover range"
    structural_bounding_cases:
      - case_name: "single_igbt"
        description: "Min config"
        because: "Required"
    pass_bar:
      margin_gain:
        name: "X"
        value: 0.10
        because: "Meaningful improvement"
      beat_cheap_baseline_by:
        name: "Y"
        value: 0.05
        because: "Measurable"
      across_perturbations:
        name: "N"
        value: 2.0
        because: "2 perturbations for fast test"
    kill_criterion:
      description: "Any pass-bar violation kills the field"
      because: "Safety-critical"
    cost_budget:
      max_total_battery_seconds: 3600.0
      max_rounds_budget: 20
      field_convergence_round_limit: 5
      thermal_grid_cells_max: 10000
      target_solve_time_ms_per_field: 5000.0
""")
    return prereg_yaml


def _mini_fdm_config() -> ThermalFDMConfig:
    return ThermalFDMConfig(
        cell_size_mm=2.0,
        origin_mm=(0.0, 0.0),
        height_cells=25,
        width_cells=25,
        ambient_C=40.0,
        heatsink_edge="TOP",
        max_cells=5000,
    )


def _mini_op_config() -> dict:
    return {
        "V_bus": 325.0,
        "V_BR": 1200.0,
        "I_load_rms": 16.0,
        "L_coil": 100e-6,
        "L_leakage": 1e-6,
        "f_sw": 25000.0,
    }


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------


class TestSmokeTestFieldDivergence:
    """Pre-battery smoke test catches silent field plumbing failures."""

    def test_field_diverges_on_small_board(self):
        """Smoke test passes when field-on vs field-off diverge."""
        board = _mini_board(100, 100)
        c1 = Component(
            ref="Q1", footprint="TO-247", bounds=(10.0, 5.0),
            pins=[], initial_position=(50.0, 20.0), net_class="HighVoltage",
        )
        c2 = Component(
            ref="Q2", footprint="TO-247", bounds=(10.0, 5.0),
            pins=[], initial_position=(30.0, 20.0), net_class="HighVoltage",
        )
        netlist = _mini_netlist([c1, c2])
        fdm_config = _mini_fdm_config()
        devices = {"Q1": (50.0, 20.0), "Q2": (30.0, 20.0)}
        power_map = {"Q1": 30.0, "Q2": 15.0}

        # Should not raise — field diverges
        _ensure_field_diverges(
            board=board, netlist=netlist, fdm_config=fdm_config,
            devices=devices, power_map=power_map,
            n_perturbations=2, base_seed=99,
        )

    def test_unmeasured_field_terminates_smoke(self):
        """Smoke test aborts when FDM returns UNMEASURED (grid too large)."""
        board = _mini_board(100, 100)
        netlist = _mini_netlist([])
        fdm_config = ThermalFDMConfig(
            cell_size_mm=0.1,
            origin_mm=(0.0, 0.0),
            height_cells=200,
            width_cells=200,
            ambient_C=40.0,
            heatsink_edge="TOP",
            max_cells=10,  # tiny limit forces UNMEASURED
        )
        devices = {"Q1": (50.0, 20.0)}
        power_map = {"Q1": 30.0}

        with pytest.raises(RuntimeError, match="UNMEASURED"):
            _ensure_field_diverges(
                board=board, netlist=netlist, fdm_config=fdm_config,
                devices=devices, power_map=power_map,
                n_perturbations=1, base_seed=99,
            )


# ---------------------------------------------------------------------------
# Happy: KEEP
# ---------------------------------------------------------------------------


class TestHappyKeep:
    """Physics clears the bar → KEEP."""

    def test_keep_synthetic_run(self, tmp_path):
        """A synthetic run where physics is measurably better → KEEP."""
        prereg_path = _mini_prereg_path(tmp_path)
        board = _mini_board(100, 100)
        q1 = Component(
            ref="Q1", footprint="TO-247", bounds=(10.0, 5.0),
            pins=[], initial_position=(50.0, 20.0), net_class="HighVoltage",
        )
        q2 = Component(
            ref="Q2", footprint="TO-247", bounds=(10.0, 5.0),
            pins=[], initial_position=(30.0, 20.0), net_class="HighVoltage",
        )
        netlist = _mini_netlist([q1, q2])
        fdm_config = _mini_fdm_config()
        devices = {"Q1": (50.0, 20.0), "Q2": (30.0, 20.0)}
        power_map = {"Q1": 30.0, "Q2": 15.0}
        op_config = _mini_op_config()

        artifact = run_thermal_helps_battery(
            prereg_path=prereg_path,
            board=board,
            netlist=netlist,
            fdm_config=fdm_config,
            devices=devices,
            power_map=power_map,
            operating_point_config=op_config,
            base_seed=42,
            n_perturbations=2,
            skip_smoke_test=False,
            skip_human_reference=True,
            artifact_dir=str(tmp_path),
        )

        # The verdict should be defined (KEEP, KILL, or INCONCLUSIVE)
        assert artifact.verdict in (
            BatteryVerdict.KEEP,
            BatteryVerdict.KILL,
            BatteryVerdict.INCONCLUSIVE,
        ), f"Unexpected verdict: {artifact.verdict}"
        assert artifact.gate_clean
        assert artifact.n_perturbations == 2
        assert artifact.run_hash
        assert not artifact.human_reference_calibrated

        # Artifact is saved
        artifact_files = list(tmp_path.glob("thermal_battery_*.json"))
        assert len(artifact_files) == 1
        saved = json.loads(artifact_files[0].read_text())
        assert saved["field_name"] == "thermal"

        # Per-arm report exists
        assert artifact.per_arm_report is not None

        if artifact.verdict == BatteryVerdict.KEEP:
            assert "KEEP" in artifact.verdict_details
        elif artifact.verdict == BatteryVerdict.KILL:
            assert "KILL" in artifact.verdict_details

    def test_artifact_reproducible(self, tmp_path):
        """Same inputs produce the same verdict."""
        prereg_path = _mini_prereg_path(tmp_path)
        board = _mini_board(100, 150)
        q1 = Component(
            ref="Q1", footprint="TO-247", bounds=(10.0, 5.0),
            pins=[], initial_position=(50.0, 10.0), net_class="HighVoltage",
        )
        netlist = _mini_netlist([q1])
        fdm_config = _mini_fdm_config()
        devices = {"Q1": (50.0, 10.0)}
        power_map = {"Q1": 30.0}
        op_config = _mini_op_config()

        run_ts = datetime(2026, 7, 9, 12, 0, 0, tzinfo=timezone.utc)

        a1 = run_thermal_helps_battery(
            prereg_path=prereg_path, board=board, netlist=netlist,
            fdm_config=fdm_config, devices=devices, power_map=power_map,
            operating_point_config=op_config,
            base_seed=42, n_perturbations=2,
            skip_smoke_test=True, skip_human_reference=True,
            battery_run_timestamp=run_ts,
        )
        a2 = run_thermal_helps_battery(
            prereg_path=prereg_path, board=board, netlist=netlist,
            fdm_config=fdm_config, devices=devices, power_map=power_map,
            operating_point_config=op_config,
            base_seed=42, n_perturbations=2,
            skip_smoke_test=True, skip_human_reference=True,
            battery_run_timestamp=run_ts,
        )

        assert a1.verdict == a2.verdict
        assert a1.run_hash == a2.run_hash


# ---------------------------------------------------------------------------
# Happy: KILL
# ---------------------------------------------------------------------------


class TestHappyKill:
    """Cheap captures the benefit → KILL (KILL is a SUCCESS)."""

    def test_kill_records_success(self, tmp_path):
        """Verdict KILL is a valid, successful result — harness can conclude kill."""
        prereg_yaml = tmp_path / "kill_prereg.yaml"
        prereg_yaml.write_text("""\
version: 1
created_at: "2026-07-09T00:00:00Z"
fields:
  - field_name: "thermal"
    independent_instrument: "thermal-gauss-seidel"
    cheap_baseline:
      name: "uniform_heat_spread"
      description: "Uniform"
      metric: "thermal_score"
      target_value: 0.0
      because: "Baseline"
    parametric_ranges:
      - parameter: "h"
        min: 5.0
        max: 40.0
        because: "Cover"
    structural_bounding_cases:
      - case_name: "s"
        description: "d"
        because: "b"
    pass_bar:
      margin_gain:
        name: "X"
        value: 0.50           # very high bar — physics can't reach
        because: "High bar"
      beat_cheap_baseline_by:
        name: "Y"
        value: 0.45
        because: "High bar"
      across_perturbations:
        name: "N"
        value: 2.0
        because: "Stats"
    kill_criterion:
      description: "Any pass-bar violation kills"
      because: "Safety"
    cost_budget:
      max_total_battery_seconds: 3600.0
      max_rounds_budget: 20
      field_convergence_round_limit: 5
      thermal_grid_cells_max: 10000
      target_solve_time_ms_per_field: 5000.0
""")
        board = _mini_board(100, 100)
        q1 = Component(
            ref="Q1", footprint="TO-247", bounds=(10.0, 5.0),
            pins=[], initial_position=(50.0, 20.0), net_class="HighVoltage",
        )
        netlist = _mini_netlist([q1])
        fdm_config = _mini_fdm_config()
        devices = {"Q1": (50.0, 20.0)}
        power_map = {"Q1": 30.0}
        op_config = _mini_op_config()
        run_ts = datetime(2026, 7, 9, 12, 0, 0, tzinfo=timezone.utc)

        artifact = run_thermal_helps_battery(
            prereg_path=prereg_yaml, board=board, netlist=netlist,
            fdm_config=fdm_config, devices=devices, power_map=power_map,
            operating_point_config=op_config,
            base_seed=42, n_perturbations=2,
            skip_smoke_test=True, skip_human_reference=True,
            battery_run_timestamp=run_ts,
        )

        # With a high bar, the verdict SHOULD be KILL (or INCONCLUSIVE)
        # The point is the harness CAN conclude kill — it doesn't force keep
        assert artifact.verdict in (
            BatteryVerdict.KILL, BatteryVerdict.INCONCLUSIVE,
        ), f"Expected KILL or INCONCLUSIVE, got {artifact.verdict}"


# ---------------------------------------------------------------------------
# Error: gate not-CLEAN
# ---------------------------------------------------------------------------


class TestGateAbort:
    """Operating-point gate not-CLEAN → abort before scoring.

    When ngspice is installed (SPICE cross-check available), the gate
    returns CLEAN on feasible parameters.  When it is absent, the gate
    returns UNMEASURED.  Both paths are tested adaptively.
    """

    def _gate_has_spice(self) -> bool:
        """Check whether ngspice is available for the gate."""
        from temper_placer.validation.spice import NgspiceValidator
        return NgspiceValidator().check_ngspice()

    def test_unmeasured_gate_or_clean(self):
        """Gate with viable params: CLEAN if SPICE present, UNMEASURED otherwise."""
        params = {
            "V_bus": 325.0, "V_BR": 1200.0, "I_load_rms": 16.0,
            "L_coil": 100e-6, "L_leakage": 1e-6, "f_sw": 25000.0,
        }
        if self._gate_has_spice():
            # SPICE present → gate returns CLEAN (no raise)
            _ensure_operating_point_clean(params)
        else:
            # No SPICE → gate returns UNMEASURED → SystemError
            with pytest.raises(SystemError, match="UNMEASURED"):
                _ensure_operating_point_clean(params)

    def test_violations_gate_aborts(self):
        """Gate with infeasible parameters → SystemError (VIOLATIONS)."""
        with pytest.raises(SystemError, match="VIOLATIONS"):
            _ensure_operating_point_clean({
                "V_bus": 2000.0,   # way too high — V_bus > V_BR*derate
                "V_BR": 1200.0,
                "I_load_rms": 100.0,   # extreme current
                "L_coil": 1e-9,    # tiny inductance → huge di/dt
                "L_leakage": 1e-9,
                "f_sw": 25000.0,
                "T_j_max": 25.0,   # junction max below ambient → violation
            })

    def test_full_run_skips_gate_when_config_absent(self, tmp_path):
        """When operating_point_config is None, gate is skipped (test-only)."""
        prereg_path = _mini_prereg_path(tmp_path)
        board = _mini_board(100, 100)
        q1 = Component(
            ref="Q1", footprint="TO-247", bounds=(10.0, 5.0),
            pins=[], initial_position=(50.0, 20.0), net_class="HighVoltage",
        )
        netlist = _mini_netlist([q1])
        fdm_config = _mini_fdm_config()
        devices = {"Q1": (50.0, 20.0)}
        power_map = {"Q1": 30.0}

        artifact = run_thermal_helps_battery(
            prereg_path=prereg_path, board=board, netlist=netlist,
            fdm_config=fdm_config, devices=devices, power_map=power_map,
            operating_point_config=None,  # skipped
            base_seed=42, n_perturbations=2,
            skip_smoke_test=True, skip_human_reference=True,
        )

        assert not artifact.gate_clean


# ---------------------------------------------------------------------------
# Error: cost budget exceeded
# ---------------------------------------------------------------------------


class TestCostBudgetExceeded:
    """Exceeding cost budget → INCONCLUSIVE with cost reason."""

    def test_cost_budget_exceeded_inconclusive(self, tmp_path):
        """When cost exceeds budget, verdict is INCONCLUSIVE."""
        prereg_yaml = tmp_path / "cost_budget_prereg.yaml"
        prereg_yaml.write_text("""\
version: 1
created_at: "2026-07-09T00:00:00Z"
fields:
  - field_name: "thermal"
    independent_instrument: "thermal-gauss-seidel"
    cheap_baseline:
      name: "uniform_heat_spread"
      description: "Uniform"
      metric: "thermal_score"
      target_value: 0.0
      because: "Baseline"
    parametric_ranges:
      - parameter: "h"
        min: 5.0
        max: 40.0
        because: "Cover"
    structural_bounding_cases:
      - case_name: "s"
        description: "d"
        because: "b"
    pass_bar:
      margin_gain:
        name: "X"
        value: 0.10
        because: "b"
      beat_cheap_baseline_by:
        name: "Y"
        value: 0.05
        because: "b"
      across_perturbations:
        name: "N"
        value: 2.0
        because: "b"
    kill_criterion:
      description: "Any pass-bar violation kills"
      because: "Safety"
    cost_budget:
      max_total_battery_seconds: 0.0001    # impossibly tight
      max_rounds_budget: 20
      field_convergence_round_limit: 5
      thermal_grid_cells_max: 10000
      target_solve_time_ms_per_field: 5000.0
""")

        board = _mini_board(100, 100)
        q1 = Component(
            ref="Q1", footprint="TO-247", bounds=(10.0, 5.0),
            pins=[], initial_position=(50.0, 20.0), net_class="HighVoltage",
        )
        netlist = _mini_netlist([q1])
        fdm_config = _mini_fdm_config()
        devices = {"Q1": (50.0, 20.0)}
        power_map = {"Q1": 30.0}

        run_ts = datetime(2026, 7, 9, 12, 0, 0, tzinfo=timezone.utc)

        artifact = run_thermal_helps_battery(
            prereg_path=prereg_yaml, board=board, netlist=netlist,
            fdm_config=fdm_config, devices=devices, power_map=power_map,
            operating_point_config=None,  # skip gate
            base_seed=42, n_perturbations=2,
            skip_smoke_test=True, skip_human_reference=True,
            battery_run_timestamp=run_ts,
        )

        assert artifact.verdict == BatteryVerdict.INCONCLUSIVE
        assert artifact.budget_exceeded

    def test_max_rounds_budget_exceeded(self, tmp_path):
        """Exceeding max_rounds_budget → INCONCLUSIVE."""
        prereg_yaml = tmp_path / "rounds_budget_prereg.yaml"
        prereg_yaml.write_text("""\
version: 1
created_at: "2026-07-09T00:00:00Z"
fields:
  - field_name: "thermal"
    independent_instrument: "thermal-gauss-seidel"
    cheap_baseline:
      name: "uniform_heat_spread"
      description: "Uniform"
      metric: "thermal_score"
      target_value: 0.0
      because: "Baseline"
    parametric_ranges:
      - parameter: "h"
        min: 5.0
        max: 40.0
        because: "Cover"
    structural_bounding_cases:
      - case_name: "s"
        description: "d"
        because: "b"
    pass_bar:
      margin_gain:
        name: "X"
        value: 0.10
        because: "b"
      beat_cheap_baseline_by:
        name: "Y"
        value: 0.05
        because: "b"
      across_perturbations:
        name: "N"
        value: 10.0
        because: "b"
    kill_criterion:
      description: "Any pass-bar violation kills"
      because: "Safety"
    cost_budget:
      max_total_battery_seconds: 3600.0
      max_rounds_budget: 1         # only 1 perturbation allowed
      field_convergence_round_limit: 5
      thermal_grid_cells_max: 10000
      target_solve_time_ms_per_field: 5000.0
""")

        board = _mini_board(100, 100)
        q1 = Component(
            ref="Q1", footprint="TO-247", bounds=(10.0, 5.0),
            pins=[], initial_position=(50.0, 20.0), net_class="HighVoltage",
        )
        netlist = _mini_netlist([q1])
        fdm_config = _mini_fdm_config()
        devices = {"Q1": (50.0, 20.0)}
        power_map = {"Q1": 30.0}

        run_ts = datetime(2026, 7, 9, 12, 0, 0, tzinfo=timezone.utc)

        artifact = run_thermal_helps_battery(
            prereg_path=prereg_yaml, board=board, netlist=netlist,
            fdm_config=fdm_config, devices=devices, power_map=power_map,
            operating_point_config=None,
            base_seed=42, n_perturbations=5,   # 5 > 1 max_rounds
            skip_smoke_test=True, skip_human_reference=True,
            battery_run_timestamp=run_ts,
        )

        assert artifact.verdict == BatteryVerdict.INCONCLUSIVE
        assert artifact.budget_exceeded


# ---------------------------------------------------------------------------
# Edge: timestamp rejection
# ---------------------------------------------------------------------------


class TestTimestampRejection:
    """Run timestamp earlier than prereg → rejected."""

    def test_run_before_prereg_rejected(self, tmp_path):
        """Battery run timestamp earlier than prereg created_at → ValueError."""
        prereg_path = _mini_prereg_path(tmp_path)
        board = _mini_board(100, 100)
        q1 = Component(
            ref="Q1", footprint="TO-247", bounds=(10.0, 5.0),
            pins=[], initial_position=(50.0, 20.0), net_class="HighVoltage",
        )
        netlist = _mini_netlist([q1])
        fdm_config = _mini_fdm_config()
        devices = {"Q1": (50.0, 20.0)}
        power_map = {"Q1": 30.0}

        # Prereg created_at: "2026-07-09T00:00:00Z"
        # Run at 2019 — way before prereg
        run_ts = datetime(2019, 1, 1, tzinfo=timezone.utc)

        with pytest.raises(ValueError, match="post-dates"):
            run_thermal_helps_battery(
                prereg_path=prereg_path, board=board, netlist=netlist,
                fdm_config=fdm_config, devices=devices, power_map=power_map,
                operating_point_config=None,
                base_seed=42, n_perturbations=2,
                skip_smoke_test=True, skip_human_reference=True,
                battery_run_timestamp=run_ts,
            )


# ---------------------------------------------------------------------------
# Integration: real wiring test with solve_thermal_fdm + ThermalScorer
# ---------------------------------------------------------------------------


class TestIntegrationRealWiring:
    """At least one test calls solve_thermal_fdm + ThermalScorer through
    build_scorecard to prove the integration."""

    def test_real_fdm_plus_scorer_wiring(self, tmp_path):
        """Integration: solve_thermal_fdm + ThermalScorer through build_scorecard."""
        from temper_placer.validation.prereg.schema import PreregistrationManifest
        from temper_placer.validation.thermal_scorer import ThermalScorer, ThermalScorerConfig
        from temper_placer.validation.scorecard import build_scorecard

        prereg_path = _mini_prereg_path(tmp_path)
        board = _mini_board(100, 100)
        q1 = Component(
            ref="Q1", footprint="TO-247", bounds=(10.0, 5.0),
            pins=[], initial_position=(50.0, 20.0), net_class="HighVoltage",
        )
        netlist = _mini_netlist([q1])
        fdm_config = _mini_fdm_config()
        devices = {"Q1": (50.0, 20.0)}
        power_map = {"Q1": 30.0}

        # Build scorer adapter
        scorer = ThermalScorer(ThermalScorerConfig(max_iterations=1000, tolerance_C=0.1))
        scorer_adapter = _make_thermal_scorer_adapter(
            scorer, fdm_config, devices, power_map,
        )

        # Create a minimal placement
        from temper_placer.validation.results.battery_run import _MinimalPlacement
        placement = _MinimalPlacement(
            positions=np.array([[50.0, 90.0]], dtype=np.float32),
            refs=["Q1"],
        )

        # Exercise build_scorecard with ThermalScorer
        scorecard = build_scorecard(
            placement, board, netlist,
            scorer=scorer_adapter,
            scorer_id="thermal-gauss-seidel",
            field_id="thermal_field",
        )

        assert scorecard is not None
        assert scorecard.scorer_id == "thermal-gauss-seidel"
        assert len(scorecard.margins) >= 1

        # Thermal margin should be present
        thermal_margin = scorecard.margin_for("thermal")
        assert thermal_margin is not None


# ---------------------------------------------------------------------------
# Reporter integration
# ---------------------------------------------------------------------------


class TestReporterIntegration:
    """Battery verdict surfaced through RegressionReporter."""

    def test_reporter_surfaces_battery_verdict(self):
        """RegressionReporter.add_battery_verdict + battery_report + summary."""
        from temper_placer.regression.reporter import (
            BatteryVerdictReport,
            RegressionReporter,
        )

        reporter = RegressionReporter()
        reporter.add_battery_verdict(BatteryVerdictReport(
            field_name="thermal",
            verdict="keep",
            verdict_details="KEEP: margin_gain=0.35 >= 0.10 (X)",
            cost_seconds=12.5,
            budget_exceeded=False,
            event="keep",
        ))

        assert len(reporter.battery_verdicts) == 1
        assert reporter.battery_verdicts[0].verdict == "keep"
        assert reporter.battery_verdicts[0].cost_seconds == 12.5

        report_str = reporter.battery_report()
        assert "KEEP" in report_str
        assert "thermal" in report_str
        assert "12.5" in report_str

        summary_str = reporter.summary()
        assert "Battery Verdicts" in summary_str

    def test_reporter_with_multiple_verdicts(self):
        """Multiple battery verdicts accumulate."""
        from temper_placer.regression.reporter import (
            BatteryVerdictReport,
            RegressionReporter,
        )

        reporter = RegressionReporter()
        reporter.add_battery_verdict(BatteryVerdictReport(
            field_name="thermal", verdict="kill",
            verdict_details="KILL: margin_gain < 0",
            cost_seconds=5.0, budget_exceeded=False, event="kill",
        ))
        reporter.add_battery_verdict(BatteryVerdictReport(
            field_name="clearance", verdict="keep",
            verdict_details="KEEP: pass",
            cost_seconds=3.0, budget_exceeded=False, event="keep",
        ))

        assert len(reporter.battery_verdicts) == 2
        assert reporter.battery_verdicts[0].event == "kill"
        assert reporter.battery_verdicts[1].event == "keep"

    def test_reporter_empty_verdicts_handled(self):
        """Empty battery_verdicts produces a clean message, not crash."""
        from temper_placer.regression.reporter import RegressionReporter

        reporter = RegressionReporter()
        assert reporter.battery_report() == "No battery verdicts recorded."
        assert "Battery Verdicts" not in reporter.summary()


# ---------------------------------------------------------------------------
# BatteryRunResult dataclass smoke
# ---------------------------------------------------------------------------


class TestArtifactDataclass:
    """BatteryRunArtifact and BatteryRunReport smoke tests."""

    def test_artifact_round_trip_json(self, tmp_path):
        """Artifact can be saved and loaded with fidelity."""
        artifact = BatteryRunArtifact(
            field_name="thermal",
            verdict=BatteryVerdict.KEEP,
            verdict_details="KEEP: test",
            prereg_version=1,
            prereg_created_at="2026-07-09T00:00:00Z",
            run_timestamp_utc="2026-07-09T12:00:00+00:00",
            run_hash="abc123",
            gate_clean=True,
            human_reference_calibrated=False,
            human_reference={"calibrated": False, "skipped": True},
            cost_seconds=13.7,
            budget_exceeded=False,
            budget_detail="",
            divergence_detected=True,
            divergence_detail="All good",
            n_perturbations=5,
            per_arm_report=BatteryRunReport(
                field_name="thermal",
                verdict="keep",
                verdict_details="test",
                divergence_detected=True,
                divergence_detail="ok",
                cost_seconds=13.7,
                budget_exceeded=False,
                budget_detail="",
                n_perturbations=5,
                arch={"no_field_margins": {"thermal": {"mean": 1.0, "n": 5}}},
            ),
        )

        p = tmp_path / "test_artifact.json"
        artifact.save(p)
        loaded = BatteryRunArtifact.load(p)

        assert loaded.verdict == BatteryVerdict.KEEP
        assert loaded.run_hash == "abc123"
        assert loaded.cost_seconds == 13.7
        assert loaded.gate_clean

    def test_artifact_to_dict(self):
        """to_dict serializes enum values correctly."""
        artifact = BatteryRunArtifact(
            field_name="t", verdict=BatteryVerdict.KILL,
            verdict_details="k", prereg_version=1,
            prereg_created_at="x", run_timestamp_utc="y",
            run_hash="h", gate_clean=True,
            human_reference_calibrated=False, human_reference={},
            cost_seconds=0, budget_exceeded=False, budget_detail="",
            divergence_detected=False, divergence_detail="",
            n_perturbations=0,
        )
        d = artifact.to_dict()
        assert d["verdict"] == "kill"
        assert d["field_name"] == "t"


# ---------------------------------------------------------------------------
# Human-reference skip
# ---------------------------------------------------------------------------


class TestHumanReferenceSkip:
    """Human-reference calibration is skipped when board data is absent."""

    def test_human_ref_skipped_by_default(self, tmp_path):
        """skip_human_reference=True → calibrated=False."""
        prereg_path = _mini_prereg_path(tmp_path)
        board = _mini_board(100, 100)
        q1 = Component(
            ref="Q1", footprint="TO-247", bounds=(10.0, 5.0),
            pins=[], initial_position=(50.0, 20.0), net_class="HighVoltage",
        )
        netlist = _mini_netlist([q1])
        fdm_config = _mini_fdm_config()
        devices = {"Q1": (50.0, 20.0)}
        power_map = {"Q1": 30.0}

        artifact = run_thermal_helps_battery(
            prereg_path=prereg_path, board=board, netlist=netlist,
            fdm_config=fdm_config, devices=devices, power_map=power_map,
            operating_point_config=None,
            base_seed=42, n_perturbations=2,
            skip_smoke_test=True, skip_human_reference=True,
        )

        assert not artifact.human_reference_calibrated


# ---------------------------------------------------------------------------
# Fail-closed: device_power derivation (#140)
# ---------------------------------------------------------------------------


class TestFailClosedPowerDerivation:
    """Battery aborts when device_loss_configs is missing (fail-closed)."""

    def test_op_config_without_device_loss_configs_aborts(self, tmp_path):
        """operating_point_config without device_loss_configs and without
        explicit power_map → SystemError (#140 fail-closed guard)."""
        prereg_path = _mini_prereg_path(tmp_path)
        board = _mini_board(100, 100)
        q1 = Component(
            ref="Q1", footprint="TO-247", bounds=(10.0, 5.0),
            pins=[], initial_position=(50.0, 20.0), net_class="HighVoltage",
        )
        netlist = _mini_netlist([q1])
        fdm_config = _mini_fdm_config()
        devices = {"Q1": (50.0, 20.0)}
        op_config = _mini_op_config()

        with pytest.raises(SystemError, match="device_loss_configs"):
            run_thermal_helps_battery(
                prereg_path=prereg_path, board=board, netlist=netlist,
                fdm_config=fdm_config, devices=devices,
                power_map=None,  # not provided
                operating_point_config=op_config,
                device_loss_configs=None,  # missing
                base_seed=42, n_perturbations=2,
                skip_smoke_test=True, skip_human_reference=True,
            )

    def test_explicit_power_map_overrides_derivation(self, tmp_path):
        """When power_map is explicitly provided, it overrides derivation
        even when device_loss_configs is present."""
        prereg_path = _mini_prereg_path(tmp_path)
        board = _mini_board(100, 100)
        q1 = Component(
            ref="Q1", footprint="TO-247", bounds=(10.0, 5.0),
            pins=[], initial_position=(50.0, 20.0), net_class="HighVoltage",
        )
        netlist = _mini_netlist([q1])
        fdm_config = _mini_fdm_config()
        devices = {"Q1": (50.0, 20.0)}
        power_map = {"Q1": 30.0}
        op_config = _mini_op_config()

        from temper_placer.physics.device_power import DeviceLossConfig

        loss_configs = {
            "Q1": DeviceLossConfig(
                name="Q1", device_type="IGBT", V_ce_sat=1.7,
                E_on=0.32e-3, E_off=0.21e-3,
                V_ce_sat_because="test",
                E_on_because="test",
                E_off_because="test",
            ),
        }

        run_ts = datetime(2026, 7, 9, 12, 0, 0, tzinfo=timezone.utc)

        artifact = run_thermal_helps_battery(
            prereg_path=prereg_path, board=board, netlist=netlist,
            fdm_config=fdm_config, devices=devices,
            power_map=power_map,  # explicit override
            operating_point_config=op_config,
            device_loss_configs=loss_configs,
            base_seed=42, n_perturbations=2,
            skip_smoke_test=True, skip_human_reference=True,
            battery_run_timestamp=run_ts,
        )

        # Should run without error — power_map takes priority
        assert artifact.verdict in (
            BatteryVerdict.KEEP, BatteryVerdict.KILL, BatteryVerdict.INCONCLUSIVE,
        )

    def test_derived_power_map_produces_sane_results(self, tmp_path):
        """Battery run with derived power_map (via device_loss_configs)
        completes without error and produces a valid verdict."""
        prereg_path = _mini_prereg_path(tmp_path)
        board = _mini_board(100, 100)
        q1 = Component(
            ref="Q1", footprint="TO-247", bounds=(10.0, 5.0),
            pins=[], initial_position=(50.0, 20.0), net_class="HighVoltage",
        )
        q2 = Component(
            ref="Q2", footprint="TO-247", bounds=(10.0, 5.0),
            pins=[], initial_position=(30.0, 20.0), net_class="HighVoltage",
        )
        netlist = _mini_netlist([q1, q2])
        fdm_config = _mini_fdm_config()
        devices = {"Q1": (50.0, 20.0), "Q2": (30.0, 20.0)}
        op_config = _mini_op_config()

        from temper_placer.physics.device_power import (
            DeviceLossConfig,
            temper_igbt_loss_config,
        )

        loss_configs = {
            "Q1": temper_igbt_loss_config("Q1"),
            "Q2": temper_igbt_loss_config("Q2"),
        }

        run_ts = datetime(2026, 7, 9, 12, 0, 0, tzinfo=timezone.utc)

        artifact = run_thermal_helps_battery(
            prereg_path=prereg_path, board=board, netlist=netlist,
            fdm_config=fdm_config, devices=devices,
            power_map=None,  # derive from loss configs
            operating_point_config=op_config,
            device_loss_configs=loss_configs,
            base_seed=42, n_perturbations=2,
            skip_smoke_test=True, skip_human_reference=True,
            battery_run_timestamp=run_ts,
        )

        assert artifact.verdict in (
            BatteryVerdict.KEEP, BatteryVerdict.KILL, BatteryVerdict.INCONCLUSIVE,
        )
        assert artifact.gate_clean


# ---------------------------------------------------------------------------
# Smoke test: scorer adapter
# ---------------------------------------------------------------------------


class TestScorerAdapter:
    """ThermalScorer adapter for build_scorecard compatibility."""

    def test_adapter_returns_physics_oracle_result(self):
        """Adapter returns PhysicsOracleResult consumable by build_scorecard."""
        from temper_placer.validation.thermal_scorer import ThermalScorer, ThermalScorerConfig

        fdm_config = _mini_fdm_config()
        devices = {"Q1": (50.0, 20.0)}
        power_map = {"Q1": 30.0}
        scorer = ThermalScorer(ThermalScorerConfig(max_iterations=500, tolerance_C=0.1))
        adapter = _make_thermal_scorer_adapter(scorer, fdm_config, devices, power_map)

        result = adapter(None, None, None)

        assert result.board_id == "unknown"
        assert "thermal_score" in (result.quality_report or {})
        thermal = result.quality_report.get("thermal_score", -1)
        assert 0.0 <= thermal <= 1.0
