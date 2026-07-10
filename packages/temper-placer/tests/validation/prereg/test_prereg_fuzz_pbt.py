"""Property-based pre-registration fuzz tests (R21).

Validates the PreregistrationManifest temporal gating and structural
completeness rules across Hypothesis-generated malformed records.

Uses ``thermal_prereg.yaml`` as the valid baseline and mutates it.

R21 invariants:
  - created_at >= run timestamp is rejected (pre-reg must predate results).
  - Any record missing a mandatory field is rejected:
      structural_bounding_cases (non-empty), cost_budget (all fields),
      because citations (non-empty), pass_bar thresholds, kill_criterion.
  - A complete valid record with created_at < run timestamp loads.
"""

from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile

import pytest
import yaml
from hypothesis import assume, given, settings
from hypothesis.strategies import (
    integers,
    one_of,
    sampled_from,
    text,
)

from temper_placer.validation.prereg.schema import (
    BecauseThreshold,
    PreregistrationManifest,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _thermal_record():
    """Minimal well-formed thermal field record dict (matching thermal_prereg.yaml structure)."""
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
            "margin_gain": {"name": "X", "value": 0.10, "because": "X rationale"},
            "beat_cheap_baseline_by": {"name": "Y", "value": 0.05, "because": "Y rationale"},
            "across_perturbations": {"name": "N", "value": 5.0, "because": "N rationale"},
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
    }


_MANIFEST_TEMPLATE = {
    "version": 1,
    "created_at": "2026-07-09T00:00:00Z",
    "fields": [_thermal_record()],
}


def _write_yaml(data: dict) -> Path:
    tmp = NamedTemporaryFile(suffix=".yaml", mode="w", delete=False)
    tmp.write(yaml.dump(data))
    tmp.close()
    return Path(tmp.name)


# ---------------------------------------------------------------------------
# R21: Temporal gating — created_at vs battery_run_timestamp
# ---------------------------------------------------------------------------


class TestCreatedAtTemporalGate:
    """Theorem: A record with created_at >= the supplied run timestamp is rejected;
    created_at < run timestamp is accepted.
    """

    @given(
        created_hours_offset=integers(min_value=-720, max_value=720),
        run_hours_offset=integers(min_value=-720, max_value=720),
    )
    @settings(max_examples=200, deadline=30000)
    def test_temporal_gate_rejects_post_dating_records(self, created_hours_offset, run_hours_offset):
        """created_at > battery_run_timestamp → rejection."""
        base = datetime(2026, 7, 9, 12, 0, 0, tzinfo=timezone.utc)
        created_at_dt = base + timedelta(hours=created_hours_offset)
        battery_ts = base + timedelta(hours=run_hours_offset)

        created_at_str = created_at_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        manifest = copy.deepcopy(_MANIFEST_TEMPLATE)
        manifest["created_at"] = created_at_str
        path = _write_yaml(manifest)
        try:
            if created_at_dt > battery_ts:
                with pytest.raises(ValueError, match="post-dates battery-run"):
                    PreregistrationManifest.load(path, battery_run_timestamp=battery_ts)
            else:
                loaded = PreregistrationManifest.load(path, battery_run_timestamp=battery_ts)
                assert loaded.version == 1
        finally:
            path.unlink()

    @given(
        seconds_past=integers(min_value=1, max_value=86400),
    )
    @settings(max_examples=100, deadline=30000)
    def test_created_at_after_run_by_seconds_rejected(self, seconds_past):
        """created_at is seconds after run timestamp → rejected."""
        battery_ts = datetime(2026, 7, 9, 0, 0, 0, tzinfo=timezone.utc)
        created_at = battery_ts + timedelta(seconds=seconds_past)
        assert created_at > battery_ts

        created_at_str = created_at.strftime("%Y-%m-%dT%H:%M:%SZ")
        manifest = copy.deepcopy(_MANIFEST_TEMPLATE)
        manifest["created_at"] = created_at_str
        path = _write_yaml(manifest)
        try:
            with pytest.raises(ValueError, match="post-dates battery-run"):
                PreregistrationManifest.load(path, battery_run_timestamp=battery_ts)
        finally:
            path.unlink()

    @given(
        days_before=integers(min_value=1, max_value=365),
    )
    @settings(max_examples=100, deadline=30000)
    def test_created_at_before_run_by_days_accepted(self, days_before):
        """created_at is days before run timestamp → loads successfully."""
        battery_ts = datetime(2026, 7, 10, 0, 0, 0, tzinfo=timezone.utc)
        created_at = battery_ts - timedelta(days=days_before)

        created_at_str = created_at.strftime("%Y-%m-%dT%H:%M:%SZ")
        manifest = copy.deepcopy(_MANIFEST_TEMPLATE)
        manifest["created_at"] = created_at_str
        path = _write_yaml(manifest)
        try:
            loaded = PreregistrationManifest.load(path, battery_run_timestamp=battery_ts)
            assert loaded.version == 1
            assert loaded.created_at == created_at_str
        finally:
            path.unlink()

    def test_exact_same_timestamp_accepted(self):
        """created_at exactly equals run timestamp → loads (inclusive)."""
        manifest = copy.deepcopy(_MANIFEST_TEMPLATE)
        manifest["created_at"] = "2026-07-09T00:00:00Z"
        path = _write_yaml(manifest)
        battery_ts = datetime(2026, 7, 9, 0, 0, 0, tzinfo=timezone.utc)
        try:
            loaded = PreregistrationManifest.load(path, battery_run_timestamp=battery_ts)
            assert loaded.version == 1
        finally:
            path.unlink()

    def test_naive_timestamp_treated_as_utc(self):
        """A naive battery-run timestamp is treated as UTC per the loader."""
        manifest = copy.deepcopy(_MANIFEST_TEMPLATE)
        manifest["created_at"] = "2026-07-09T12:00:00Z"
        path = _write_yaml(manifest)
        # naive 2026-07-09T00:00:00 treated as UTC < 12:00 UTC → rejected
        battery_ts = datetime(2026, 7, 9, 0, 0, 0)  # naive
        try:
            with pytest.raises(ValueError, match="post-dates"):
                PreregistrationManifest.load(path, battery_run_timestamp=battery_ts)
        finally:
            path.unlink()

    def test_no_battery_timestamp_skips_gate(self):
        """If battery_run_timestamp is None, no temporal check is performed."""
        manifest = copy.deepcopy(_MANIFEST_TEMPLATE)
        # created_at far in the future relative to "now" — would normally fail
        manifest["created_at"] = "2026-07-09T00:00:00Z"
        path = _write_yaml(manifest)
        try:
            loaded = PreregistrationManifest.load(path)
            assert loaded.version == 1
        finally:
            path.unlink()


# ---------------------------------------------------------------------------
# R21: Structural completeness fuzz — mandatory field rejection
# ---------------------------------------------------------------------------


_MANDATORY_FIELD_DELETIONS = {
    "delete_structural_bounding_cases": (
        ["fields", 0, "structural_bounding_cases"],
        "structural_bounding_cases",
    ),
    "set_structural_bounding_cases_empty": (
        "set structural_bounding_cases to []",
        None,  # special-cased below
    ),
    "delete_cost_budget": (
        ["fields", 0, "cost_budget"],
        "cost_budget",
    ),
    "delete_cost_budget_max_total": (
        ["fields", 0, "cost_budget", "max_total_battery_seconds"],
        "max_total_battery_seconds",
    ),
    "delete_cost_budget_max_rounds": (
        ["fields", 0, "cost_budget", "max_rounds_budget"],
        "max_rounds_budget",
    ),
    "delete_cost_budget_field_conv": (
        ["fields", 0, "cost_budget", "field_convergence_round_limit"],
        "field_convergence_round_limit",
    ),
    "delete_cost_budget_grid_cells": (
        ["fields", 0, "cost_budget", "thermal_grid_cells_max"],
        "thermal_grid_cells_max",
    ),
    "delete_cost_budget_solve_time": (
        ["fields", 0, "cost_budget", "target_solve_time_ms_per_field"],
        "target_solve_time_ms_per_field",
    ),
    "empty_because_on_cheap_baseline": (
        "set because='' on cheap_baseline",
        "because",
    ),
    "empty_because_on_parametric_range": (
        "set because='' on parametric_ranges[0]",
        "because",
    ),
    "empty_because_on_structural_case": (
        "set because='' on structural_bounding_cases[0]",
        "because",
    ),
    "empty_because_on_margin_gain": (
        "set because='' on pass_bar.margin_gain",
        "because",
    ),
    "empty_because_on_beat_cheap": (
        "set because='' on pass_bar.beat_cheap_baseline_by",
        "because",
    ),
    "empty_because_on_across_perturbations": (
        "set because='' on pass_bar.across_perturbations",
        "because",
    ),
    "empty_because_on_kill_criterion": (
        "set because='' on kill_criterion",
        "because",
    ),
    "empty_kill_criterion_description": (
        "set description='' on kill_criterion",
        "description",
    ),
    "delete_pass_bar": (
        ["fields", 0, "pass_bar"],
        "pass_bar",
    ),
    "delete_pass_bar_margin_gain": (
        ["fields", 0, "pass_bar", "margin_gain"],
        "margin_gain",
    ),
    "delete_kill_criterion": (
        ["fields", 0, "kill_criterion"],
        "kill_criterion",
    ),
    "delete_cheap_baseline": (
        ["fields", 0, "cheap_baseline"],
        "cheap_baseline",
    ),
}


class TestMandatoryFieldRejection:
    """Theorem: Any record missing a mandatory field is rejected by load()."""

    @given(
        mutation_name=sampled_from(sorted(_MANDATORY_FIELD_DELETIONS.keys())),
    )
    @settings(max_examples=100, deadline=30000)
    def test_mandatory_field_missing_or_empty_is_rejected(self, mutation_name):
        """Each mandatory-field mutation causes load() to raise ValueError."""
        manifest = copy.deepcopy(_MANIFEST_TEMPLATE)
        # Set created_at far enough in the past so temporal gate doesn't interfere
        manifest["created_at"] = "2020-01-01T00:00:00Z"
        battery_ts = datetime(2026, 7, 9, tzinfo=timezone.utc)

        mutation = _MANDATORY_FIELD_DELETIONS[mutation_name]

        if mutation_name == "set_structural_bounding_cases_empty":
            manifest["fields"][0]["structural_bounding_cases"] = []
        elif isinstance(mutation[0], str) and mutation[0].startswith("set "):
            # String-based mutation instructions
            instruction = mutation[0]
            if "cheap_baseline" in instruction:
                manifest["fields"][0]["cheap_baseline"]["because"] = ""
            elif "parametric_ranges" in instruction:
                manifest["fields"][0]["parametric_ranges"][0]["because"] = ""
            elif "structural_bounding_cases" in instruction:
                manifest["fields"][0]["structural_bounding_cases"][0]["because"] = ""
            elif "pass_bar.margin_gain" in instruction:
                manifest["fields"][0]["pass_bar"]["margin_gain"]["because"] = ""
            elif "pass_bar.beat_cheap_baseline_by" in instruction:
                manifest["fields"][0]["pass_bar"]["beat_cheap_baseline_by"]["because"] = ""
            elif "pass_bar.across_perturbations" in instruction:
                manifest["fields"][0]["pass_bar"]["across_perturbations"]["because"] = ""
            elif "kill_criterion" in instruction and "description" in instruction:
                manifest["fields"][0]["kill_criterion"]["description"] = ""
            elif "kill_criterion" in instruction:
                manifest["fields"][0]["kill_criterion"]["because"] = ""
        else:
            # Path-based deletion
            path_parts = mutation[0]
            ref = manifest
            for key in path_parts[:-1]:
                ref = ref[key]
            del ref[path_parts[-1]]

        path = _write_yaml(manifest)
        try:
            with pytest.raises(Exception):
                PreregistrationManifest.load(path, battery_run_timestamp=battery_ts)
        finally:
            path.unlink()

    def test_structural_bounding_cases_empty_rejected(self):
        """Empty structural_bounding_cases list is rejected."""
        manifest = copy.deepcopy(_MANIFEST_TEMPLATE)
        manifest["fields"][0]["structural_bounding_cases"] = []
        manifest["created_at"] = "2020-01-01T00:00:00Z"
        path = _write_yaml(manifest)
        try:
            with pytest.raises(ValueError, match="structural_bounding_cases"):
                PreregistrationManifest.load(
                    path, battery_run_timestamp=datetime(2026, 7, 9, tzinfo=timezone.utc)
                )
        finally:
            path.unlink()

    def test_kill_criterion_empty_description_rejected(self):
        """Kill criterion with empty description is rejected."""
        manifest = copy.deepcopy(_MANIFEST_TEMPLATE)
        manifest["fields"][0]["kill_criterion"]["description"] = ""
        manifest["created_at"] = "2020-01-01T00:00:00Z"
        path = _write_yaml(manifest)
        try:
            with pytest.raises(ValueError, match="description"):
                PreregistrationManifest.load(
                    path, battery_run_timestamp=datetime(2026, 7, 9, tzinfo=timezone.utc)
                )
        finally:
            path.unlink()


# ---------------------------------------------------------------------------
# R21: Complete valid record loads
# ---------------------------------------------------------------------------


class TestCompleteValidRecordLoads:
    """Theorem: A complete, valid record with created_at < run timestamp loads successfully."""

    def test_shipped_thermal_prereg_loads(self):
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
        assert field.pass_bar.margin_gain.value == 0.10
        assert field.cost_budget.max_total_battery_seconds == 3600.0

    def test_shipped_prereg_with_future_timestamp_loads(self):
        """Shipped prereg loads when battery_run_timestamp is after created_at."""
        prereg_path = (
            Path(__file__).resolve().parent.parent.parent.parent
            / "src"
            / "temper_placer"
            / "validation"
            / "prereg"
            / "thermal_prereg.yaml"
        )
        future_battery = datetime(2026, 7, 10, tzinfo=timezone.utc)
        manifest = PreregistrationManifest.load(prereg_path, battery_run_timestamp=future_battery)
        assert manifest.version == 1

    def test_complete_valid_record_loads(self):
        """A synthetically-constructed complete record loads and exposes all fields."""
        manifest = copy.deepcopy(_MANIFEST_TEMPLATE)
        manifest["created_at"] = "2020-01-01T00:00:00Z"
        path = _write_yaml(manifest)
        battery_ts = datetime(2026, 7, 9, tzinfo=timezone.utc)
        try:
            loaded = PreregistrationManifest.load(path, battery_run_timestamp=battery_ts)
            assert loaded.version == 1
            assert len(loaded.fields) == 1
            f = loaded.fields[0]
            assert f.field_name == "thermal"
            assert f.pass_bar.margin_gain.value == 0.10
            assert f.pass_bar.beat_cheap_baseline_by.value == 0.05
            assert f.pass_bar.across_perturbations.value == 5.0
            assert f.cost_budget.max_total_battery_seconds == 3600.0
            assert f.cost_budget.max_rounds_budget == 20
            assert f.cost_budget.field_convergence_round_limit == 5
            assert f.cost_budget.thermal_grid_cells_max == 10000
            assert f.cost_budget.target_solve_time_ms_per_field == 5000.0
            assert f.cheap_baseline.name == "uniform_heat_spread"
            assert len(f.parametric_ranges) == 1
            assert len(f.structural_bounding_cases) == 1
            assert f.structural_bounding_cases[0].case_name == "single_igbt"
            assert f.kill_criterion.description == "Ships iff pass bar met."
        finally:
            path.unlink()

    @given(
        created_days_before=integers(min_value=1, max_value=365),
    )
    @settings(max_examples=100, deadline=30000)
    def test_complete_record_with_past_created_at_always_loads(self, created_days_before):
        """A complete valid record with created_at well before run always loads."""
        battery_ts = datetime(2026, 7, 9, tzinfo=timezone.utc)
        created_at = battery_ts - timedelta(days=created_days_before)

        manifest = copy.deepcopy(_MANIFEST_TEMPLATE)
        manifest["created_at"] = created_at.strftime("%Y-%m-%dT%H:%M:%SZ")
        path = _write_yaml(manifest)
        try:
            loaded = PreregistrationManifest.load(path, battery_run_timestamp=battery_ts)
            assert loaded.version == 1
            assert len(loaded.fields) == 1
        finally:
            path.unlink()


# ---------------------------------------------------------------------------
# R21: BecauseThreshold model-level invariant
# ---------------------------------------------------------------------------


class TestBecauseThresholdFuzz:
    """Theorem: BecauseThreshold rejects empty/whitespace because at model level."""

    @given(
        because=one_of(
            text(alphabet=" " * 20, min_size=0, max_size=20),
            sampled_from([""]),
        ),
    )
    @settings(max_examples=200, deadline=30000)
    def test_becausethreshold_empty_or_whitespace_rejected(self, because):
        """Empty or whitespace-only because raises ValueError at model construction."""
        with pytest.raises(ValueError, match="because"):
            BecauseThreshold(value=1.0, because=because)

    @given(
        because=text(alphabet="abcdefghijklmnopqrstuvwxyz ", min_size=1, max_size=5),
    )
    @settings(max_examples=200, deadline=30000)
    def test_becausethreshold_non_empty_non_whitespace_accepted(self, because):
        """A non-empty, non-whitespace because is accepted."""
        assume(because.strip())  # ensure at least one non-whitespace char
        bt = BecauseThreshold(value=1.0, because=because)
        assert bt.value == 1.0
        assert bt.because == because
