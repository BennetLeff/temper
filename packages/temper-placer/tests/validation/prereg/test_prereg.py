"""Tests for the pre-registration schema and loader (U1).

Covers:
  * Happy path: well-formed thermal record loads, exposes X/Y/N + kill
    criterion + cost budgets.
  * Edge: missing structural_bounding_cases fails validation.
  * Edge: missing a cost budget field fails validation.
  * Error: created_at in the future relative to battery-run timestamp
    is rejected.
  * Happy: every threshold field carries a non-empty ``because`` or
    load fails.
"""

from __future__ import annotations

import textwrap
from datetime import datetime, timezone, timedelta
from pathlib import Path
from tempfile import NamedTemporaryFile

import pytest
import yaml

from temper_placer.validation.prereg.schema import (
    BecauseThreshold,
    CheapBaseline,
    CostBudget,
    FieldPreregistration,
    KillCriterion,
    ParametricRange,
    PassBar,
    PreregistrationManifest,
    StructuralBoundingCase,
)


# ---- helpers ----------------------------------------------------------------

def _thermal_record(**overrides):  # type: ignore[no-untyped-def]
    """Minimal well-formed thermal field record dict."""
    return {
        "field_name": "thermal",
        "independent_instrument": "temper_placer.physics.thermal.ThermalOracle",
        "cheap_baseline": {
            "name": "uniform_heat_spread",
            "description": "No thermal optimization.",
            "metric": "thermal_score",
            "target_value": 0.0,
            "because": "Worst-case thermal profile.",
        },
        "parametric_ranges": [
            {
                "parameter": "max_heatspread_mm",
                "min": 5.0,
                "max": 40.0,
                "because": "Tight enclosure to open chassis.",
            }
        ],
        "structural_bounding_cases": [
            {
                "case_name": "single_igbt",
                "description": "Single IGBT, passive cooling.",
                "because": "Minimum viable configuration.",
            }
        ],
        "pass_bar": {
            "margin_gain": {
                "name": "X",
                "value": 0.10,
                "because": "Must improve by >= 0.10.",
            },
            "beat_cheap_baseline_by": {
                "name": "Y",
                "value": 0.05,
                "because": "Must beat baseline by >= 0.05.",
            },
            "across_perturbations": {
                "name": "N",
                "value": 5.0,
                "because": "Minimum 5 perturbations.",
            },
        },
        "kill_criterion": {
            "description": "Ships iff pass bar met.",
            "because": "Thermal is safety-critical.",
        },
        "cost_budget": {
            "max_total_battery_seconds": 3600.0,
            "max_rounds_budget": 20,
            "field_convergence_round_limit": 5,
            "thermal_grid_cells_max": 10000,
            "target_solve_time_ms_per_field": 5000.0,
        },
        **overrides,
    }


def _make_manifest(fields: list[dict]) -> dict:  # type: ignore[type-arg]
    return {
        "version": 1,
        "created_at": "2026-07-09T00:00:00Z",
        "fields": fields,
    }


def _write_yaml(data: dict) -> Path:  # type: ignore[type-arg]
    """Write a dict to a temp YAML file and return its Path."""
    tmp = NamedTemporaryFile(suffix=".yaml", mode="w", delete=False)
    tmp.write(yaml.dump(data))
    tmp.close()
    return Path(tmp.name)


# ---- happy-path tests -------------------------------------------------------


class TestWellFormedThermalRecordLoads:
    """Happy path: a well-formed thermal record loads and exposes all fields."""

    def test_all_top_level_fields_present(self) -> None:
        manifest = _make_manifest([_thermal_record()])
        path = _write_yaml(manifest)
        try:
            loaded = PreregistrationManifest.load(path)
            assert loaded.version == 1
            assert loaded.created_at == "2026-07-09T00:00:00Z"
            assert len(loaded.fields) == 1
        finally:
            path.unlink()

    def test_x_y_n_exposed(self) -> None:
        """The pass_bar margin_gain (X), beat_cheap_baseline_by (Y),
        and across_perturbations (N) thresholds are accessible."""
        manifest = _make_manifest([_thermal_record()])
        path = _write_yaml(manifest)
        try:
            loaded = PreregistrationManifest.load(path)
            field = loaded.fields[0]
            pass_bar = field.pass_bar
            assert pass_bar.margin_gain.name == "X"
            assert pass_bar.margin_gain.value == 0.10
            assert pass_bar.beat_cheap_baseline_by.name == "Y"
            assert pass_bar.beat_cheap_baseline_by.value == 0.05
            assert pass_bar.across_perturbations.name == "N"
            assert pass_bar.across_perturbations.value == 5.0
        finally:
            path.unlink()

    def test_kill_criterion_exposed(self) -> None:
        manifest = _make_manifest([_thermal_record()])
        path = _write_yaml(manifest)
        try:
            loaded = PreregistrationManifest.load(path)
            kc = loaded.fields[0].kill_criterion
            assert "pass bar" in kc.description.lower()
            assert "safety-critical" in kc.because
        finally:
            path.unlink()

    def test_cost_budget_exposed(self) -> None:
        manifest = _make_manifest([_thermal_record()])
        path = _write_yaml(manifest)
        try:
            loaded = PreregistrationManifest.load(path)
            budget = loaded.fields[0].cost_budget
            assert budget.max_total_battery_seconds == 3600.0
            assert budget.max_rounds_budget == 20
            assert budget.field_convergence_round_limit == 5
            assert budget.thermal_grid_cells_max == 10000
            assert budget.target_solve_time_ms_per_field == 5000.0
        finally:
            path.unlink()

    def test_cheap_baseline_exposed(self) -> None:
        manifest = _make_manifest([_thermal_record()])
        path = _write_yaml(manifest)
        try:
            loaded = PreregistrationManifest.load(path)
            baseline = loaded.fields[0].cheap_baseline
            assert baseline.name == "uniform_heat_spread"
            assert baseline.metric == "thermal_score"
            assert baseline.target_value == 0.0
        finally:
            path.unlink()

    def test_parametric_ranges_exposed(self) -> None:
        manifest = _make_manifest([_thermal_record()])
        path = _write_yaml(manifest)
        try:
            loaded = PreregistrationManifest.load(path)
            ranges = loaded.fields[0].parametric_ranges
            assert len(ranges) == 1
            assert ranges[0].parameter == "max_heatspread_mm"
            assert ranges[0].min == 5.0
            assert ranges[0].max == 40.0
        finally:
            path.unlink()

    def test_structural_bounding_cases_exposed(self) -> None:
        manifest = _make_manifest([_thermal_record()])
        path = _write_yaml(manifest)
        try:
            loaded = PreregistrationManifest.load(path)
            cases = loaded.fields[0].structural_bounding_cases
            assert len(cases) == 1
            assert cases[0].case_name == "single_igbt"
        finally:
            path.unlink()

    def test_independent_instrument_exposed(self) -> None:
        manifest = _make_manifest([_thermal_record()])
        path = _write_yaml(manifest)
        try:
            loaded = PreregistrationManifest.load(path)
            assert loaded.fields[0].independent_instrument == (
                "temper_placer.physics.thermal.ThermalOracle"
            )
        finally:
            path.unlink()

    def test_frozen_yaml_loads(self) -> None:
        """The shipped thermal_prereg.yaml must load without error."""
        prereg_path = (
            Path(__file__).resolve().parent.parent.parent.parent
            / "src"
            / "temper_placer"
            / "validation"
            / "prereg"
            / "thermal_prereg.yaml"
        )
        manifest = PreregistrationManifest.load(prereg_path)
        assert manifest.version == 1
        assert len(manifest.fields) == 1
        field = manifest.fields[0]
        assert field.field_name == "thermal"
        # X/Y/N accessible
        assert field.pass_bar.margin_gain.value == 0.10
        assert field.pass_bar.beat_cheap_baseline_by.value == 0.05
        assert field.pass_bar.across_perturbations.value == 5.0
        # Cost budget accessible
        assert field.cost_budget.max_total_battery_seconds == 3600.0


# ---- edge-case tests --------------------------------------------------------


class TestMissingStructuralBoundingCasesFails:
    """Edge: structural_bounding_cases is mandatory."""

    def test_empty_list_fails(self) -> None:
        record = _thermal_record(structural_bounding_cases=[])
        manifest = _make_manifest([record])
        path = _write_yaml(manifest)
        try:
            with pytest.raises(ValueError, match="structural_bounding_cases"):
                PreregistrationManifest.load(path)
        finally:
            path.unlink()

    def test_missing_key_fails(self) -> None:
        record = _thermal_record()
        del record["structural_bounding_cases"]
        manifest = _make_manifest([record])
        path = _write_yaml(manifest)
        try:
            with pytest.raises(ValueError):
                PreregistrationManifest.load(path)
        finally:
            path.unlink()


class TestMissingCostBudgetFails:
    """Edge: every cost budget field is required."""

    def test_missing_max_total_battery_seconds_fails(self) -> None:
        record = _thermal_record()
        del record["cost_budget"]["max_total_battery_seconds"]
        manifest = _make_manifest([record])
        path = _write_yaml(manifest)
        try:
            with pytest.raises(ValueError, match="max_total_battery_seconds"):
                PreregistrationManifest.load(path)
        finally:
            path.unlink()

    def test_missing_max_rounds_budget_fails(self) -> None:
        record = _thermal_record()
        del record["cost_budget"]["max_rounds_budget"]
        manifest = _make_manifest([record])
        path = _write_yaml(manifest)
        try:
            with pytest.raises(ValueError, match="max_rounds_budget"):
                PreregistrationManifest.load(path)
        finally:
            path.unlink()

    def test_missing_thermal_grid_cells_max_fails(self) -> None:
        record = _thermal_record()
        del record["cost_budget"]["thermal_grid_cells_max"]
        manifest = _make_manifest([record])
        path = _write_yaml(manifest)
        try:
            with pytest.raises(ValueError, match="thermal_grid_cells_max"):
                PreregistrationManifest.load(path)
        finally:
            path.unlink()

    def test_missing_entire_cost_budget_fails(self) -> None:
        record = _thermal_record()
        del record["cost_budget"]
        manifest = _make_manifest([record])
        path = _write_yaml(manifest)
        try:
            with pytest.raises(ValueError, match="cost_budget"):
                PreregistrationManifest.load(path)
        finally:
            path.unlink()


# ---- temporal-gating tests --------------------------------------------------


class TestCreatedAtFutureTimestampRejected:
    """Error: created_at must predate the battery-run timestamp."""

    def test_future_created_at_rejected(self) -> None:
        manifest = _make_manifest([_thermal_record()])
        path = _write_yaml(manifest)
        # Battery run at 2026-07-08; created_at is 2026-07-09 -> future
        battery_ts = datetime(2026, 7, 8, tzinfo=timezone.utc)
        try:
            with pytest.raises(ValueError, match="post-dates battery-run"):
                PreregistrationManifest.load(path, battery_run_timestamp=battery_ts)
        finally:
            path.unlink()

    def test_same_timestamp_accepted(self) -> None:
        manifest = _make_manifest([_thermal_record()])
        path = _write_yaml(manifest)
        battery_ts = datetime(2026, 7, 9, 0, 0, 0, tzinfo=timezone.utc)
        try:
            loaded = PreregistrationManifest.load(path, battery_run_timestamp=battery_ts)
            assert loaded.created_at == "2026-07-09T00:00:00Z"
        finally:
            path.unlink()

    def test_past_created_at_accepted(self) -> None:
        manifest = _make_manifest([_thermal_record()])
        path = _write_yaml(manifest)
        battery_ts = datetime(2026, 7, 10, tzinfo=timezone.utc)
        try:
            loaded = PreregistrationManifest.load(path, battery_run_timestamp=battery_ts)
            assert loaded.created_at == "2026-07-09T00:00:00Z"
        finally:
            path.unlink()

    def test_naive_battery_timestamp_treated_as_utc(self) -> None:
        """A naive battery-run timestamp (no tzinfo) is treated as UTC."""
        manifest = _make_manifest([_thermal_record()])
        path = _write_yaml(manifest)
        # Naive 2026-07-08 < 2026-07-09 UTC -> should be rejected
        battery_ts = datetime(2026, 7, 8)  # naive, treated as UTC
        try:
            with pytest.raises(ValueError, match="post-dates"):
                PreregistrationManifest.load(path, battery_run_timestamp=battery_ts)
        finally:
            path.unlink()


# ---- because-citation tests -------------------------------------------------


class TestBecauseCitationMandatory:
    """Happy/error: every threshold field must carry a non-empty ``because``."""

    def test_missing_because_on_cheap_baseline_fails(self) -> None:
        record = _thermal_record()
        record["cheap_baseline"]["because"] = ""
        manifest = _make_manifest([record])
        path = _write_yaml(manifest)
        try:
            with pytest.raises(ValueError, match="because"):
                PreregistrationManifest.load(path)
        finally:
            path.unlink()

    def test_missing_because_on_parametric_range_fails(self) -> None:
        record = _thermal_record()
        del record["parametric_ranges"][0]["because"]
        manifest = _make_manifest([record])
        path = _write_yaml(manifest)
        try:
            with pytest.raises(ValueError, match="because"):
                PreregistrationManifest.load(path)
        finally:
            path.unlink()

    def test_missing_because_on_structural_bounding_case_fails(self) -> None:
        record = _thermal_record()
        record["structural_bounding_cases"][0]["because"] = "  "
        manifest = _make_manifest([record])
        path = _write_yaml(manifest)
        try:
            with pytest.raises(ValueError, match="because"):
                PreregistrationManifest.load(path)
        finally:
            path.unlink()

    def test_missing_because_on_margin_gain_fails(self) -> None:
        record = _thermal_record()
        record["pass_bar"]["margin_gain"]["because"] = ""
        manifest = _make_manifest([record])
        path = _write_yaml(manifest)
        try:
            with pytest.raises(ValueError, match="because"):
                PreregistrationManifest.load(path)
        finally:
            path.unlink()

    def test_missing_because_on_beat_cheap_baseline_by_fails(self) -> None:
        record = _thermal_record()
        record["pass_bar"]["beat_cheap_baseline_by"]["because"] = ""
        manifest = _make_manifest([record])
        path = _write_yaml(manifest)
        try:
            with pytest.raises(ValueError, match="because"):
                PreregistrationManifest.load(path)
        finally:
            path.unlink()

    def test_missing_because_on_across_perturbations_fails(self) -> None:
        record = _thermal_record()
        record["pass_bar"]["across_perturbations"]["because"] = ""
        manifest = _make_manifest([record])
        path = _write_yaml(manifest)
        try:
            with pytest.raises(ValueError, match="because"):
                PreregistrationManifest.load(path)
        finally:
            path.unlink()

    def test_missing_because_on_kill_criterion_fails(self) -> None:
        record = _thermal_record()
        record["kill_criterion"]["because"] = ""
        manifest = _make_manifest([record])
        path = _write_yaml(manifest)
        try:
            with pytest.raises(ValueError, match="because"):
                PreregistrationManifest.load(path)
        finally:
            path.unlink()

    def test_all_because_present_succeeds(self) -> None:
        """A record with all `because` fields non-empty loads cleanly."""
        manifest = _make_manifest([_thermal_record()])
        path = _write_yaml(manifest)
        try:
            loaded = PreregistrationManifest.load(path)
            # Verify every threshold has a non-empty because
            f = loaded.fields[0]
            assert f.cheap_baseline.because.strip()
            assert all(r.because.strip() for r in f.parametric_ranges)
            assert all(c.because.strip() for c in f.structural_bounding_cases)
            assert f.pass_bar.margin_gain.because.strip()
            assert f.pass_bar.beat_cheap_baseline_by.because.strip()
            assert f.pass_bar.across_perturbations.because.strip()
            assert f.kill_criterion.because.strip()
        finally:
            path.unlink()


# ---- direct-model tests -----------------------------------------------------


class TestDirectModelConstruction:
    """Verify pydantic model construction works without YAML indirection."""

    def test_construct_field_manually(self) -> None:
        field = FieldPreregistration(
            field_name="test_field",
            independent_instrument="dummy.Instrument",
            cheap_baseline=CheapBaseline(
                name="null",
                description="does nothing",
                metric="m",
                target_value=0.0,
                because="No effort",
            ),
            parametric_ranges=[
                ParametricRange(
                    parameter="p",
                    min=0.0,
                    max=1.0,
                    because="covers full range",
                )
            ],
            structural_bounding_cases=[
                StructuralBoundingCase(
                    case_name="single",
                    description="one",
                    because="mandatory",
                )
            ],
            pass_bar=PassBar(
                margin_gain=BecauseThreshold(name="X", value=0.1, because="X"),
                beat_cheap_baseline_by=BecauseThreshold(name="Y", value=0.05, because="Y"),
                across_perturbations=BecauseThreshold(name="N", value=5.0, because="N"),
            ),
            kill_criterion=KillCriterion(
                description="ships if OK",
                because="safety",
            ),
            cost_budget=CostBudget(
                max_total_battery_seconds=100.0,
                max_rounds_budget=10,
                field_convergence_round_limit=3,
                thermal_grid_cells_max=5000,
                target_solve_time_ms_per_field=1000.0,
            ),
        )
        assert field.field_name == "test_field"
        assert field.pass_bar.margin_gain.value == 0.1

    def test_construct_manifest_manually(self) -> None:
        manifest = PreregistrationManifest(
            version=1,
            created_at="2026-01-01T00:00:00Z",
            fields=[],
        )
        assert manifest.version == 1
        assert len(manifest.fields) == 0


class TestBecauseThresholdModel:
    """BecauseThreshold carries a value + mandatory because."""

    def test_empty_because_rejected(self) -> None:
        with pytest.raises(ValueError, match="because"):
            BecauseThreshold(value=1.0, because="")

    def test_whitespace_because_rejected(self) -> None:
        with pytest.raises(ValueError, match="because"):
            BecauseThreshold(value=1.0, because="   ")

    def test_valid_because_accepted(self) -> None:
        bt = BecauseThreshold(value=0.5, because="rationale")
        assert bt.value == 0.5
