"""Tests for SchemaValidator (U4): schema validation of pipeline metrics."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from temper_placer.pipeline.metrics_observer import (
    CrossValidationError,
    MetricsObserver,
)
from temper_placer.pipeline.dag_observability import PipelineExecutionLog
from temper_placer.regression.schema_validator import (
    SchemaValidationError,
    SchemaValidator,
)


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def schema_yaml(tmp_path: Path) -> Path:
    """Minimal schema for unit tests (subset of the real schema)."""
    content = {
        "schema_version": 1,
        "metrics": {
            "wall_time_ms": {
                "unit": "milliseconds",
                "min": 0,
                "max": 3600000,
                "zero_is_valid": False,
                "introduced": "2026-06-28",
            },
            "drc_delta": {
                "unit": "count",
                "min": -100000,
                "max": 100000,
                "zero_is_valid": True,
                "introduced": "2026-06-28",
            },
        },
    }
    path = tmp_path / "metrics_schema.yaml"
    path.write_text(yaml.dump(content))
    return path


@pytest.fixture
def validator(schema_yaml: Path) -> SchemaValidator:
    return SchemaValidator(schema_path=schema_yaml)


# ---------------------------------------------------------------------------
# test cases
# ---------------------------------------------------------------------------


class TestSchemaValidatorHappy:
    """Test 1 / Test 5: values pass schema constraints."""

    def test_nonzero_passes_when_zero_is_valid_false(self, validator: SchemaValidator) -> None:
        """wall_time_ms: 5234 passes (zero_is_valid: false, min: 0)."""
        validator.validate({"wall_time_ms": 5234.0})

    def test_zero_passes_when_zero_is_valid_true(self, validator: SchemaValidator) -> None:
        """drc_delta: 0 with zero_is_valid: true -> passes."""
        validator.validate({"drc_delta": 0.0})


class TestSchemaValidatorReject:
    """Test 2-4, 6: rejected cases."""

    def test_zero_when_zero_is_valid_false(self, validator: SchemaValidator) -> None:
        with pytest.raises(SchemaValidationError, match="zero_is_valid is false"):
            validator.validate({"wall_time_ms": 0.0})

    def test_below_min(self, validator: SchemaValidator) -> None:
        with pytest.raises(SchemaValidationError, match="below minimum"):
            validator.validate({"wall_time_ms": -1.0})

    def test_exceeds_max(self, validator: SchemaValidator) -> None:
        with pytest.raises(SchemaValidationError, match="exceeds maximum"):
            validator.validate({"wall_time_ms": 5000000.0})

    def test_unknown_field_rejected(self, validator: SchemaValidator) -> None:
        with pytest.raises(SchemaValidationError, match="unknown field"):
            validator.validate({"nonexistent_metric": 1.0})


class TestSchemaValidatorEdge:
    def test_empty_metrics_passes(self, validator: SchemaValidator) -> None:
        validator.validate({})

    def test_at_min_boundary(self, validator: SchemaValidator) -> None:
        validator.validate({"wall_time_ms": 1.0})

    def test_at_max_boundary(self, validator: SchemaValidator) -> None:
        validator.validate({"wall_time_ms": 3600000.0})

    def test_negative_drc_delta_passes(self, validator: SchemaValidator) -> None:
        validator.validate({"drc_delta": -1.0})


class TestSchemaValidatorIntegration:
    """Test 7: schema runs before cross-validation in MetricsObserver."""

    def test_schema_rejects_before_cross_validation(self, tmp_path: Path) -> None:
        output_dir = tmp_path / "metrics_output"
        output_dir.mkdir()

        execution_log = PipelineExecutionLog()
        execution_log.stage_timings["test_stage"] = 5.234
        observer = MetricsObserver(
            output_dir=output_dir,
            execution_log=execution_log,
            board="test",
        )

        cross_called = False

        def _tracked_cross_validate(*, start_t, stage_name, caller_duration_s) -> None:
            nonlocal cross_called
            cross_called = True
            raise AssertionError("cross-validation should not be reached")

        with patch.object(observer, "_cross_validate_against", side_effect=_tracked_cross_validate):
            observer.on_stage_start("test_stage", 0, {})
            with pytest.raises(SchemaValidationError, match="exceeds maximum"):
                observer.on_stage_complete("test_stage", 5000.0, {})

        # Cross-validation was never reached because schema rejected wall_time_ms out of range
        assert not cross_called
        # No record written because schema validation failed
        assert not (output_dir / "pipeline_metrics.jsonl").exists()

    def test_schema_passes_then_cross_validation_runs(self, tmp_path: Path) -> None:
        output_dir = tmp_path / "metrics_output"
        output_dir.mkdir()

        execution_log = PipelineExecutionLog()
        execution_log.stage_timings["test_stage"] = 5.234
        observer = MetricsObserver(
            output_dir=output_dir,
            execution_log=execution_log,
            board="test",
        )

        cross_called = False

        def _tracked_cross_validate(*, start_t, stage_name, caller_duration_s) -> None:
            nonlocal cross_called
            cross_called = True

        with patch.object(observer, "_cross_validate_against", side_effect=_tracked_cross_validate):
            observer.on_stage_start("test_stage", 0, {})
            observer.on_stage_complete("test_stage", 5.234, {})

        assert cross_called
        assert (output_dir / "pipeline_metrics.jsonl").exists()
