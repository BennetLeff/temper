"""
Coverage paydown v4 — remaining regression allowlist entries.

Covers functions not exercised by existing suites:
- compute_input_fingerprint / compute_source_fingerprint
- SchemaValidator.validate (direct invocation, not via differential oracle)
- DrcRatchet edge cases (load missing, check unknown backend)
- find_ceiling_raises edge cases (new board, per-type warnings raises)
- _marshal_ceiling_int edge cases
- check_noise_headroom edge cases
- _provenance_sample_count edge cases
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml


# ============================================================================
# compute_input_fingerprint / compute_source_fingerprint
# ============================================================================


class TestComputeInputFingerprint:
    def test_returns_hex_string(self, tmp_path: Path):
        from temper_placer.regression.fingerprint import compute_input_fingerprint

        pcb = tmp_path / "test.kicad_pcb"
        pcb.write_text("(kicad_pcb)")
        constraints = tmp_path / "test.yaml"
        constraints.write_text("version: '1.0'")
        baseline = tmp_path / "test.json"
        baseline.write_text("{}")

        fp = compute_input_fingerprint(pcb, constraints, baseline, 42, 100)
        assert isinstance(fp, str)
        assert len(fp) == 64  # SHA-256 hex
        assert all(c in "0123456789abcdef" for c in fp)

    def test_different_seed_produces_different_fingerprint(self, tmp_path: Path):
        from temper_placer.regression.fingerprint import compute_input_fingerprint

        pcb = tmp_path / "test.kicad_pcb"
        pcb.write_text("(kicad_pcb)")
        constraints = tmp_path / "test.yaml"
        constraints.write_text("version: '1.0'")
        baseline = tmp_path / "test.json"
        baseline.write_text("{}")

        fp1 = compute_input_fingerprint(pcb, constraints, baseline, 42, 100)
        fp2 = compute_input_fingerprint(pcb, constraints, baseline, 99, 100)
        assert fp1 != fp2

    def test_different_epochs_produces_different_fingerprint(self, tmp_path: Path):
        from temper_placer.regression.fingerprint import compute_input_fingerprint

        pcb = tmp_path / "test.kicad_pcb"
        pcb.write_text("(kicad_pcb)")
        constraints = tmp_path / "test.yaml"
        constraints.write_text("version: '1.0'")
        baseline = tmp_path / "test.json"
        baseline.write_text("{}")

        fp1 = compute_input_fingerprint(pcb, constraints, baseline, 42, 100)
        fp2 = compute_input_fingerprint(pcb, constraints, baseline, 42, 999)
        assert fp1 != fp2

    def test_handles_missing_files(self, tmp_path: Path):
        from temper_placer.regression.fingerprint import compute_input_fingerprint

        missing = tmp_path / "nonexistent.kicad_pcb"
        constraints = tmp_path / "test.yaml"
        constraints.write_text("version: '1.0'")
        baseline = tmp_path / "test.json"
        baseline.write_text("{}")

        # Should not crash on missing file
        fp = compute_input_fingerprint(missing, constraints, baseline, 42, 100)
        assert isinstance(fp, str)
        assert len(fp) == 64

    def test_same_inputs_same_fingerprint(self, tmp_path: Path):
        from temper_placer.regression.fingerprint import compute_input_fingerprint

        pcb = tmp_path / "test.kicad_pcb"
        pcb.write_text("(kicad_pcb)")
        constraints = tmp_path / "test.yaml"
        constraints.write_text("version: '1.0'")
        baseline = tmp_path / "test.json"
        baseline.write_text("{}")

        fp1 = compute_input_fingerprint(pcb, constraints, baseline, 42, 100)
        fp2 = compute_input_fingerprint(pcb, constraints, baseline, 42, 100)
        assert fp1 == fp2


class TestComputeSourceFingerprint:
    def test_returns_hex_string(self):
        from temper_placer.regression.fingerprint import compute_source_fingerprint

        # Use the real repo root so SOURCE_FINGERPRINT_DIRS are found
        repo_root = Path(__file__).resolve().parents[4]  # up to repo root
        fp = compute_source_fingerprint(repo_root)
        assert isinstance(fp, str)
        assert len(fp) == 64
        assert all(c in "0123456789abcdef" for c in fp)

    def test_handles_missing_dirs(self, tmp_path: Path):
        from temper_placer.regression.fingerprint import compute_source_fingerprint

        # Empty tmp_path has no src dirs -> should produce empty fingerprint
        fp = compute_source_fingerprint(tmp_path)
        assert isinstance(fp, str)
        assert len(fp) == 64

    def test_different_code_different_fingerprint(self, tmp_path: Path):
        from temper_placer.regression.fingerprint import compute_source_fingerprint

        # Create two different source trees
        dir_a = tmp_path / "a"
        dir_b = tmp_path / "b"
        (dir_a / "packages" / "temper-placer" / "src").mkdir(parents=True)
        (dir_b / "packages" / "temper-placer" / "src").mkdir(parents=True)

        # Patch SOURCE_FINGERPRINT_DIRS temporarily by using a subprocess
        # approach -- instead, directly test that different code produces
        # different fingerprints by writing different files
        import temper_placer.regression.fingerprint as fpm

        old_dirs = fpm.SOURCE_FINGERPRINT_DIRS
        try:
            fpm.SOURCE_FINGERPRINT_DIRS = ["test_src"]
            (tmp_path / "test_src").mkdir()
            (tmp_path / "test_src" / "mod1.py").write_text("x = 1")
            fp1 = fpm.compute_source_fingerprint(tmp_path)

            (tmp_path / "test_src" / "mod1.py").write_text("x = 2")
            fp2 = fpm.compute_source_fingerprint(tmp_path)

            assert fp1 != fp2
        finally:
            fpm.SOURCE_FINGERPRINT_DIRS = old_dirs


# ============================================================================
# SchemaValidator.validate (direct invocation, not via differential oracle)
# ============================================================================


class TestSchemaValidatorValidate:
    def test_valid_metrics_pass(self, tmp_path: Path):
        from temper_placer.regression.schema_validator import SchemaValidator

        schema_yaml = tmp_path / "metrics_schema.yaml"
        schema_yaml.write_text(
            yaml.dump(
                {
                    "schema_version": 1,
                    "metrics": {
                        "completion_pct": {"min": 0, "max": 100, "zero_is_valid": True},
                        "drc_errors": {"min": 0, "zero_is_valid": True},
                    },
                }
            )
        )
        v = SchemaValidator(schema_yaml)
        # Should not raise
        v.validate({"completion_pct": 95.0, "drc_errors": 0.0})

    def test_unknown_field_raises(self, tmp_path: Path):
        from temper_placer.regression.schema_validator import (
            SchemaValidationError,
            SchemaValidator,
        )

        schema_yaml = tmp_path / "metrics_schema.yaml"
        schema_yaml.write_text(
            yaml.dump(
                {
                    "schema_version": 1,
                    "metrics": {
                        "completion_pct": {"min": 0, "max": 100},
                    },
                }
            )
        )
        v = SchemaValidator(schema_yaml)
        with pytest.raises(SchemaValidationError, match="unknown field"):
            v.validate({"unknown_metric": 1.0})

    def test_below_minimum_raises(self, tmp_path: Path):
        from temper_placer.regression.schema_validator import (
            SchemaValidationError,
            SchemaValidator,
        )

        schema_yaml = tmp_path / "metrics_schema.yaml"
        schema_yaml.write_text(
            yaml.dump(
                {
                    "schema_version": 1,
                    "metrics": {
                        "completion_pct": {"min": 0, "max": 100},
                    },
                }
            )
        )
        v = SchemaValidator(schema_yaml)
        with pytest.raises(SchemaValidationError, match="below minimum"):
            v.validate({"completion_pct": -1.0})

    def test_above_maximum_raises(self, tmp_path: Path):
        from temper_placer.regression.schema_validator import (
            SchemaValidationError,
            SchemaValidator,
        )

        schema_yaml = tmp_path / "metrics_schema.yaml"
        schema_yaml.write_text(
            yaml.dump(
                {
                    "schema_version": 1,
                    "metrics": {
                        "completion_pct": {"min": 0, "max": 100},
                    },
                }
            )
        )
        v = SchemaValidator(schema_yaml)
        with pytest.raises(SchemaValidationError, match="exceeds maximum"):
            v.validate({"completion_pct": 150.0})

    def test_zero_invalid_raises(self, tmp_path: Path):
        from temper_placer.regression.schema_validator import (
            SchemaValidationError,
            SchemaValidator,
        )

        schema_yaml = tmp_path / "metrics_schema.yaml"
        schema_yaml.write_text(
            yaml.dump(
                {
                    "schema_version": 1,
                    "metrics": {
                        # min=0 so "below minimum" doesn't fire first;
                        # zero_is_valid=False so 0.0 triggers the zero check
                        "benders_iterations": {"min": 0, "zero_is_valid": False},
                    },
                }
            )
        )
        v = SchemaValidator(schema_yaml)
        with pytest.raises(SchemaValidationError, match="zero_is_valid"):
            v.validate({"benders_iterations": 0.0})

    def test_missing_field_passes_when_not_required(self, tmp_path: Path):
        from temper_placer.regression.schema_validator import SchemaValidator

        schema_yaml = tmp_path / "metrics_schema.yaml"
        schema_yaml.write_text(
            yaml.dump(
                {
                    "schema_version": 1,
                    "metrics": {
                        "completion_pct": {"min": 0, "max": 100},
                        "drc_errors": {"min": 0},
                    },
                }
            )
        )
        v = SchemaValidator(schema_yaml)
        # Only supply one field, the other should not be required
        v.validate({"completion_pct": 50.0})

    def test_bad_schema_top_level_raises(self, tmp_path: Path):
        from temper_placer.regression.schema_validator import (
            SchemaValidationError,
            SchemaValidator,
        )

        schema_yaml = tmp_path / "metrics_schema.yaml"
        schema_yaml.write_text("42")
        with pytest.raises(SchemaValidationError, match="top-level must be a dict"):
            SchemaValidator(schema_yaml)

    def test_bad_schema_metrics_raises(self, tmp_path: Path):
        from temper_placer.regression.schema_validator import (
            SchemaValidationError,
            SchemaValidator,
        )

        schema_yaml = tmp_path / "metrics_schema.yaml"
        schema_yaml.write_text("metrics: 123")
        with pytest.raises(SchemaValidationError, match="'metrics' must be a dict"):
            SchemaValidator(schema_yaml)


# ============================================================================
# DrcRatchet edge cases
# ============================================================================


class TestDrcRatchetEdgeCases:
    def test_load_missing_file_no_error(self, tmp_path: Path):
        from temper_placer.regression.drc_ratchet import DrcRatchet

        ratchet = DrcRatchet(tmp_path / "nonexistent.json")
        ratchet.load()  # Should not raise
        assert ratchet.entries == {}

    def test_check_unknown_backend(self, tmp_path: Path):
        from temper_placer.regression.drc_ratchet import DrcRatchet

        # Create the PCB file so the check gets past "file not found"
        pcb_dir = tmp_path / "pcb"
        pcb_dir.mkdir()
        (pcb_dir / "test.kicad_pcb").write_text("(kicad_pcb)")

        ceiling_path = tmp_path / "drc_ceiling.json"
        ceiling_path.write_text(
            json.dumps(
                {
                    "boards": [
                        {
                            "board_id": "test",
                            "path": "pcb/test.kicad_pcb",
                            "error_ceiling": 10,
                            "warning_ceiling": 0,
                        }
                    ]
                }
            )
        )
        ratchet = DrcRatchet(ceiling_path, backend="made_up_backend")
        ratchet.load()
        results = ratchet.check(tmp_path)
        assert len(results) == 1
        assert not results[0].passed
        assert "Unknown DRC backend" in results[0].message

    def test_find_ceiling_raises_new_board_in_new(self, tmp_path: Path):
        from temper_placer.regression.drc_ratchet import DrcRatchet

        old = {"boards": []}
        new = {
            "boards": [
                {
                    "board_id": "new_board",
                    "path": "pcb/new.kicad_pcb",
                    "error_ceiling": 50,
                    "warning_ceiling": 0,
                }
            ]
        }
        ratchet = DrcRatchet(tmp_path / "dummy.json")
        raises = ratchet.find_ceiling_raises(old, new)
        # New board not in old -> no raise (only boards in both are checked)
        assert len(raises) == 0

    def test_find_ceiling_raises_no_change(self, tmp_path: Path):
        from temper_placer.regression.drc_ratchet import DrcRatchet

        ceiling = {
            "boards": [
                {
                    "board_id": "test",
                    "path": "pcb/test.kicad_pcb",
                    "error_ceiling": 100,
                    "warning_ceiling": 10,
                    "violations_by_type": {"clearance": 50},
                    "warnings_by_type": {"silk": 5},
                }
            ]
        }
        ratchet = DrcRatchet(tmp_path / "dummy.json")
        raises = ratchet.find_ceiling_raises(ceiling, ceiling)
        assert len(raises) == 0

    def test_find_ceiling_raises_warning_increase(self, tmp_path: Path):
        from temper_placer.regression.drc_ratchet import DrcRatchet

        old = {
            "boards": [
                {
                    "board_id": "test",
                    "path": "pcb/test.kicad_pcb",
                    "error_ceiling": 100,
                    "warning_ceiling": 5,
                    "violations_by_type": {},
                    "warnings_by_type": {},
                }
            ]
        }
        new = {
            "boards": [
                {
                    "board_id": "test",
                    "path": "pcb/test.kicad_pcb",
                    "error_ceiling": 100,
                    "warning_ceiling": 10,
                    "violations_by_type": {},
                    "warnings_by_type": {},
                }
            ]
        }
        ratchet = DrcRatchet(tmp_path / "dummy.json")
        raises = ratchet.find_ceiling_raises(old, new)
        assert len(raises) == 1
        assert "warning_ceiling" in raises[0][1][0]

    def test_find_ceiling_raises_new_violation_type(self, tmp_path: Path):
        from temper_placer.regression.drc_ratchet import DrcRatchet

        old = {
            "boards": [
                {
                    "board_id": "test",
                    "path": "pcb/test.kicad_pcb",
                    "error_ceiling": 100,
                    "warning_ceiling": 0,
                    "violations_by_type": {},
                    "warnings_by_type": {},
                }
            ]
        }
        new = {
            "boards": [
                {
                    "board_id": "test",
                    "path": "pcb/test.kicad_pcb",
                    "error_ceiling": 100,
                    "warning_ceiling": 0,
                    "violations_by_type": {"creepage": 10},
                    "warnings_by_type": {},
                }
            ]
        }
        ratchet = DrcRatchet(tmp_path / "dummy.json")
        raises = ratchet.find_ceiling_raises(old, new)
        assert len(raises) == 1
        assert "violations_by_type[creepage]" in raises[0][1][0]

    def test_find_ceiling_raises_new_warning_type(self, tmp_path: Path):
        from temper_placer.regression.drc_ratchet import DrcRatchet

        old = {
            "boards": [
                {
                    "board_id": "test",
                    "path": "pcb/test.kicad_pcb",
                    "error_ceiling": 100,
                    "warning_ceiling": 0,
                    "violations_by_type": {},
                    "warnings_by_type": {},
                }
            ]
        }
        new = {
            "boards": [
                {
                    "board_id": "test",
                    "path": "pcb/test.kicad_pcb",
                    "error_ceiling": 100,
                    "warning_ceiling": 0,
                    "violations_by_type": {},
                    "warnings_by_type": {"silk_overlap": 3},
                }
            ]
        }
        ratchet = DrcRatchet(tmp_path / "dummy.json")
        raises = ratchet.find_ceiling_raises(old, new)
        assert len(raises) == 1
        assert "warnings_by_type[silk_overlap]" in raises[0][1][0]


# ============================================================================
# _marshal_ceiling_int edge cases
# ============================================================================


class TestMarshalCeilingInt:
    def test_rejects_float(self):
        from temper_placer.regression.drc_ratchet import (
            CeilingMarshalError,
            _marshal_ceiling_int,
        )

        with pytest.raises(CeilingMarshalError, match="non-integer"):
            _marshal_ceiling_int(100.5, "error_ceiling", "test_board")

    def test_rejects_float_zero(self):
        from temper_placer.regression.drc_ratchet import (
            CeilingMarshalError,
            _marshal_ceiling_int,
        )

        with pytest.raises(CeilingMarshalError, match="non-integer"):
            _marshal_ceiling_int(0.0, "error_ceiling", "test_board")

    def test_rejects_bool(self):
        from temper_placer.regression.drc_ratchet import (
            CeilingMarshalError,
            _marshal_ceiling_int,
        )

        with pytest.raises(CeilingMarshalError, match="non-integer"):
            _marshal_ceiling_int(True, "error_ceiling", "test_board")

    def test_rejects_none(self):
        from temper_placer.regression.drc_ratchet import (
            CeilingMarshalError,
            _marshal_ceiling_int,
        )

        with pytest.raises(CeilingMarshalError, match="non-integer"):
            _marshal_ceiling_int(None, "error_ceiling", "test_board")

    def test_rejects_string(self):
        from temper_placer.regression.drc_ratchet import (
            CeilingMarshalError,
            _marshal_ceiling_int,
        )

        with pytest.raises(CeilingMarshalError, match="non-integer"):
            _marshal_ceiling_int("100", "error_ceiling", "test_board")

    def test_accepts_int(self):
        from temper_placer.regression.drc_ratchet import _marshal_ceiling_int

        result = _marshal_ceiling_int(42, "error_ceiling", "test_board")
        assert result == 42

    def test_accepts_zero_int(self):
        from temper_placer.regression.drc_ratchet import _marshal_ceiling_int

        result = _marshal_ceiling_int(0, "error_ceiling", "test_board")
        assert result == 0


# ============================================================================
# check_noise_headroom edge cases
# ============================================================================


class TestCheckNoiseHeadroom:
    def test_no_nondeterministic_types_returns_empty(self):
        from temper_placer.regression.drc_ratchet import DrcCeilingEntry, check_noise_headroom

        entry = DrcCeilingEntry(
            board_id="test",
            path="pcb/test.kicad_pcb",
            error_ceiling=100,
            warning_ceiling=10,
            violations_by_type={},
            nondeterministic_error_types={},
        )
        violations = check_noise_headroom("test", entry)
        assert violations == []

    def test_single_observed_value_skipped(self):
        from temper_placer.regression.drc_ratchet import DrcCeilingEntry, check_noise_headroom

        entry = DrcCeilingEntry(
            board_id="test",
            path="pcb/test.kicad_pcb",
            error_ceiling=100,
            warning_ceiling=10,
            violations_by_type={"clearance": 50},
            nondeterministic_error_types={
                "clearance": {"observed": [50], "samples": 120}
            },
        )
        violations = check_noise_headroom("test", entry)
        # Single observed value: < 2 distinct values → skipped
        assert violations == []

    def test_no_per_type_ceiling_skipped(self):
        from temper_placer.regression.drc_ratchet import DrcCeilingEntry, check_noise_headroom

        entry = DrcCeilingEntry(
            board_id="test",
            path="pcb/test.kicad_pcb",
            error_ceiling=100,
            warning_ceiling=10,
            violations_by_type={},  # clearance NOT in violations_by_type
            nondeterministic_error_types={
                "clearance": {"observed": [48, 49, 50], "samples": 120}
            },
        )
        violations = check_noise_headroom("test", entry)
        # No per-type ceiling for clearance → skipped
        assert violations == []

    def test_observed_not_a_list_skipped(self):
        from temper_placer.regression.drc_ratchet import DrcCeilingEntry, check_noise_headroom

        entry = DrcCeilingEntry(
            board_id="test",
            path="pcb/test.kicad_pcb",
            error_ceiling=100,
            warning_ceiling=10,
            violations_by_type={"clearance": 50},
            nondeterministic_error_types={
                "clearance": {"observed": 50, "samples": 120}  # not a list
            },
        )
        violations = check_noise_headroom("test", entry)
        assert violations == []

    def test_headroom_sufficient_no_violation(self):
        from temper_placer.regression.drc_ratchet import DrcCeilingEntry, check_noise_headroom

        entry = DrcCeilingEntry(
            board_id="test",
            path="pcb/test.kicad_pcb",
            error_ceiling=100,
            warning_ceiling=10,
            violations_by_type={"clearance": 55},
            nondeterministic_error_types={
                "clearance": {"observed": [48, 49], "samples": 120}
            },
        )
        # ceiling=55, max=49, headroom=6, spread=1 → headroom >= spread
        violations = check_noise_headroom("test", entry)
        assert violations == []

    def test_headroom_insufficient_reports_violation(self):
        from temper_placer.regression.drc_ratchet import DrcCeilingEntry, check_noise_headroom

        entry = DrcCeilingEntry(
            board_id="test",
            path="pcb/test.kicad_pcb",
            error_ceiling=100,
            warning_ceiling=10,
            violations_by_type={"clearance": 380},
            nondeterministic_error_types={
                "clearance": {"observed": [377, 378, 379], "samples": 120}
            },
        )
        # ceiling=380, max=379, headroom=1, spread=2 → headroom < spread
        violations = check_noise_headroom("test", entry)
        assert len(violations) == 1
        v = violations[0]
        assert v.board_id == "test"
        assert v.category == "clearance"
        assert v.spread == 2
        assert v.headroom == 1


# ============================================================================
# NoiseHeadroomViolation properties
# ============================================================================


class TestNoiseHeadroomViolation:
    def test_properties(self):
        from temper_placer.regression.drc_ratchet import NoiseHeadroomViolation

        nv = NoiseHeadroomViolation(
            board_id="b",
            category="test_cat",
            observed=[1, 2, 4],
            samples=120,
            ceiling=10,
        )
        assert nv.spread == 3  # 4 - 1
        assert nv.headroom == 6  # 10 - 4
        assert "b" in nv.message
        assert "test_cat" in nv.message
        assert "120 samples" in nv.message

    def test_message_when_samples_none(self):
        from temper_placer.regression.drc_ratchet import NoiseHeadroomViolation

        nv = NoiseHeadroomViolation(
            board_id="b",
            category="cat",
            observed=[1, 3],
            samples=None,
            ceiling=5,
        )
        assert "unrecorded sample count" in nv.message


# ============================================================================
# DrcCategoryFailure
# ============================================================================


class TestDrcCategoryFailure:
    def test_delta(self):
        from temper_placer.regression.drc_ratchet import DrcCategoryFailure

        cf = DrcCategoryFailure(
            rule="clearance", count=15, allowed=10, is_new=False
        )
        assert cf.delta == 5

    def test_delta_zero(self):
        from temper_placer.regression.drc_ratchet import DrcCategoryFailure

        cf = DrcCategoryFailure(
            rule="clearance", count=10, allowed=10, is_new=False
        )
        assert cf.delta == 0

    def test_is_new_flag(self):
        from temper_placer.regression.drc_ratchet import DrcCategoryFailure

        cf = DrcCategoryFailure(
            rule="new_cat", count=3, allowed=0, is_new=True, kind="warning"
        )
        assert cf.is_new is True
        assert cf.kind == "warning"
        assert cf.source == "unknown"


# ============================================================================
# _provenance_sample_count
# ============================================================================


class TestProvenanceSampleCount:
    def test_structured_field(self):
        from temper_placer.regression.drc_ratchet import _provenance_sample_count

        assert _provenance_sample_count({"sample_count": 120}) == 120
        assert _provenance_sample_count({"sample_count": 42}) == 42

    def test_legacy_measured_via(self):
        from temper_placer.regression.drc_ratchet import _provenance_sample_count

        assert _provenance_sample_count(
            {"measured_via": "(120 samples; kicad-cli 8.0.1)"}
        ) == 120
        assert _provenance_sample_count(
            {"measured_via": "collected 200 samples"}
        ) == 200

    def test_bool_sample_count_returns_none(self):
        from temper_placer.regression.drc_ratchet import _provenance_sample_count

        assert _provenance_sample_count({"sample_count": True}) is None

    def test_zero_sample_count_returns_none(self):
        from temper_placer.regression.drc_ratchet import _provenance_sample_count

        assert _provenance_sample_count({"sample_count": 0}) is None

    def test_missing_returns_none(self):
        from temper_placer.regression.drc_ratchet import _provenance_sample_count

        assert _provenance_sample_count({}) is None

    def test_structured_takes_priority(self):
        from temper_placer.regression.drc_ratchet import _provenance_sample_count

        # Structured field should be used even when measured_via is present
        result = _provenance_sample_count(
            {
                "sample_count": 150,
                "measured_via": "(120 samples; old method)",
            }
        )
        assert result == 150


# ============================================================================
# DrcRatchet.check_noise_headroom instance method
# ============================================================================


class TestDrcRatchetCheckNoiseHeadroom:
    def test_empty_entries_returns_empty(self, tmp_path: Path):
        from temper_placer.regression.drc_ratchet import DrcRatchet

        ratchet = DrcRatchet(tmp_path / "nonexistent.json")
        ratchet.load()
        violations = ratchet.check_noise_headroom()
        assert violations == []

    def test_single_entry_with_violation(self, tmp_path: Path):
        from temper_placer.regression.drc_ratchet import DrcRatchet

        ceiling_path = tmp_path / "drc_ceiling.json"
        ceiling_path.write_text(
            json.dumps(
                {
                    "boards": [
                        {
                            "board_id": "test",
                            "path": "pcb/test.kicad_pcb",
                            "error_ceiling": 380,
                            "warning_ceiling": 10,
                            "violations_by_type": {"clearance": 380},
                            "nondeterministic_error_types": {
                                "clearance": {
                                    "observed": [377, 378, 379],
                                    "samples": 120,
                                }
                            },
                        }
                    ]
                }
            )
        )
        ratchet = DrcRatchet(ceiling_path)
        ratchet.load()
        violations = ratchet.check_noise_headroom()
        assert len(violations) == 1
        assert violations[0].board_id == "test"
        assert violations[0].category == "clearance"
