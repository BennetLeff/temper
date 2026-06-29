"""Tests for MetricsObserver (U1): bridging stage events to JSONL metrics."""

from __future__ import annotations

import contextlib
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from temper_placer.pipeline.dag_engine import StageDAGEngine
from temper_placer.pipeline.dag_observability import (
    PipelineExecutionLog,
    StageEvent,
)
from temper_placer.pipeline.metrics_observer import (
    CrossValidationError,
    MetricsObserver,
)
from temper_placer.pipeline.state import PipelineConfig, PipelineState
from temper_placer.regression.metrics_recorder import load_metrics
from temper_placer.regression.schema_validator import SchemaValidationError, SchemaValidator

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _write_manifest(path: Path, stages: list[dict], name: str = "test") -> Path:
    manifest = {"pipeline": {"name": name, "version": "1.0.0"}, "stages": stages}
    path.write_text(yaml.dump(manifest))
    return path


def _passthrough_stage(name: str, provides: list[str], requires: list[str] | None = None) -> dict:
    return {
        "name": name,
        "handler": "tests.pipeline.conftest.PassthroughStage",
        "requires": requires or [],
        "provides": provides,
    }


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_config(tmp_path: Path) -> PipelineConfig:
    pcb_path = tmp_path / "test.kicad_pcb"
    pcb_path.write_text("(kicad_pcb (version 20211014))")
    return PipelineConfig(
        input_pcb=pcb_path,
        output_pcb=tmp_path / "output.kicad_pcb",
        epochs=100,
        seed=42,
        max_movement_mm=2.0,
    )


@pytest.fixture
def passthrough_manifest(tmp_path: Path) -> Path:
    manifest = {
        "pipeline": {"name": "passthrough-test", "version": "1.0.0"},
        "stages": [
            {
                "name": "input",
                "handler": "tests.pipeline.conftest.PassthroughStage",
                "requires": [],
                "provides": ["board", "netlist", "constraints", "loops"],
            },
            {
                "name": "output",
                "handler": "tests.pipeline.conftest.PassthroughStage",
                "requires": ["board", "netlist"],
                "provides": ["output_files", "physics_report"],
            },
        ],
    }
    manifest_path = tmp_path / "passthrough_manifest.yaml"
    manifest_path.write_text(yaml.dump(manifest))
    return manifest_path


@pytest.fixture
def eight_stage_manifest(tmp_path: Path) -> Path:
    stages = []
    for i in range(1, 9):
        reqs = [f"data_{i - 1}"] if i > 1 else []
        stages.append(_passthrough_stage(f"stage_{i}", provides=[f"data_{i}"], requires=reqs))
    return _write_manifest(tmp_path / "eight_stage.yaml", stages, "eight-stage")


@pytest.fixture
def single_stage_manifest(tmp_path: Path) -> Path:
    stages = [_passthrough_stage("only_stage", provides=["result"])]
    return _write_manifest(tmp_path / "single_stage.yaml", stages, "single-stage")


@pytest.fixture
def execution_log() -> PipelineExecutionLog:
    return PipelineExecutionLog()


# ---------------------------------------------------------------------------
# Test 1 — Happy path: multi-stage pipeline
# ---------------------------------------------------------------------------


class TestHappyPath:
    def test_eight_stages_produces_eight_entries(
        self, eight_stage_manifest: Path, sample_config, tmp_path: Path
    ):
        engine = StageDAGEngine(eight_stage_manifest)
        observer = MetricsObserver(tmp_path / "metrics", engine.execution_log)
        engine.add_observer(observer)
        state = PipelineState(config=sample_config)

        with patch.object(observer._schema_validator, "validate"):
            engine.run(state)

        metrics_path = tmp_path / "metrics" / "pipeline_metrics.jsonl"
        assert metrics_path.exists()
        records = load_metrics(metrics_path)
        assert len(records) == 8, f"Expected 8 entries, got {len(records)}"

        seen_stages = set()
        for r in records:
            assert r["stage_name"] != "closure", "Expected per-stage name, not default"
            assert r["stage_name"] == r["stage"]
            assert r["metrics"]["wall_time_ms"] >= 0
            seen_stages.add(r["stage_name"])

        assert seen_stages == {f"stage_{i}" for i in range(1, 9)}


# ---------------------------------------------------------------------------
# Test 2 — PipelineExecutionLog.to_dict() includes events list
# ---------------------------------------------------------------------------


class TestExecutionLogEvents:
    def test_to_dict_includes_events(self):
        log = PipelineExecutionLog()
        log.events.append(StageEvent(name="test", kind="start", iteration=0))
        log.events.append(
            StageEvent(name="test", kind="complete", duration_s=0.5, outputs={"ok": True})
        )
        log.events.append(
            StageEvent(
                name="test",
                kind="feedback_triggered",
                feedback_contract="c1",
                feedback_attempt=2,
            )
        )

        d = log.to_dict()
        assert "events" in d
        assert len(d["events"]) == 3
        assert d["events"][0]["kind"] == "start"
        assert d["events"][1]["kind"] == "complete"
        assert d["events"][1]["duration_s"] == 0.5
        assert d["events"][1]["outputs"] == {"ok": True}
        assert d["events"][2]["feedback_contract"] == "c1"

    def test_to_dict_empty_events(self):
        log = PipelineExecutionLog()
        d = log.to_dict()
        assert "events" in d
        assert d["events"] == []


# ---------------------------------------------------------------------------
# Test 3 — Single-stage pipeline → 1 entry
# ---------------------------------------------------------------------------


class TestSingleStage:
    def test_single_stage_produces_one_entry(
        self, single_stage_manifest: Path, sample_config, tmp_path: Path
    ):
        engine = StageDAGEngine(single_stage_manifest)
        observer = MetricsObserver(tmp_path / "metrics", engine.execution_log)
        engine.add_observer(observer)
        state = PipelineState(config=sample_config)

        with patch.object(observer._schema_validator, "validate"):
            engine.run(state)

        metrics_path = tmp_path / "metrics" / "pipeline_metrics.jsonl"
        records = load_metrics(metrics_path)
        assert len(records) == 1
        assert records[0]["stage_name"] == "only_stage"
        assert records[0]["metrics"]["wall_time_ms"] >= 0


# ---------------------------------------------------------------------------
# Test 4 — Cross-validation: mismatch beyond tolerance
# ---------------------------------------------------------------------------


class TestCrossValidationError:
    def test_mismatch_beyond_tolerance_raises(self, execution_log, tmp_path: Path):
        execution_log.stage_timings["bad_stage"] = 0.0
        observer = MetricsObserver(tmp_path / "metrics", execution_log)

        with pytest.raises(CrossValidationError, match="Timing mismatch"):
            observer.on_stage_complete("bad_stage", 5.234, {})

    def test_mismatch_does_not_write_record(self, execution_log, tmp_path: Path):
        execution_log.stage_timings["bad_stage"] = 0.0
        observer = MetricsObserver(tmp_path / "metrics", execution_log)

        with contextlib.suppress(CrossValidationError):
            observer.on_stage_complete("bad_stage", 5.234, {})

        metrics_path = tmp_path / "metrics" / "pipeline_metrics.jsonl"
        records = load_metrics(metrics_path)
        assert len(records) == 0


# ---------------------------------------------------------------------------
# Test 5 — Cross-validation: within tolerance
# ---------------------------------------------------------------------------


class TestCrossValidationPass:
    def test_within_tolerance_writes_record(self, execution_log, tmp_path: Path):
        execution_log.stage_timings["good_stage"] = 5.234
        observer = MetricsObserver(tmp_path / "metrics", execution_log)

        observer.on_stage_complete("good_stage", 5.240, {})  # 6ms diff < 10ms

        metrics_path = tmp_path / "metrics" / "pipeline_metrics.jsonl"
        records = load_metrics(metrics_path)
        assert len(records) == 1
        assert records[0]["stage_name"] == "good_stage"

    def test_exact_match_writes(self, execution_log, tmp_path: Path):
        execution_log.stage_timings["exact"] = 1.5
        observer = MetricsObserver(tmp_path / "metrics", execution_log)

        observer.on_stage_complete("exact", 1.5, {})

        records = load_metrics(tmp_path / "metrics" / "pipeline_metrics.jsonl")
        assert len(records) == 1

    def test_stage_not_in_log_skips_validation(self, execution_log, tmp_path: Path):
        observer = MetricsObserver(tmp_path / "metrics", execution_log)

        observer.on_stage_complete("unknown", 2.0, {})

        records = load_metrics(tmp_path / "metrics" / "pipeline_metrics.jsonl")
        assert len(records) == 1


# ---------------------------------------------------------------------------
# Test 6 — Schema validation
# ---------------------------------------------------------------------------


class TestSchemaValidation:
    def test_zero_is_valid_false_rejects_zero(self) -> None:
        validator = SchemaValidator()
        with pytest.raises(SchemaValidationError, match="__pipeline_liveness__"):
            validator.validate({"__pipeline_liveness__": 0.0})

    def test_nonzero_passes_schema(self, execution_log, tmp_path: Path):
        """wall_time_ms > 0 passes the default schema (zero_is_valid: false)."""
        execution_log.stage_timings["s"] = 0.0
        observer = MetricsObserver(tmp_path / "metrics", execution_log)

        observer.on_stage_complete("s", 0.001, {})

        records = load_metrics(tmp_path / "metrics" / "pipeline_metrics.jsonl")
        assert len(records) == 1
        assert records[0]["metrics"]["wall_time_ms"] == 1

    def test_zero_wall_time_ms_rejected_by_default_schema(self) -> None:
        """__pipeline_liveness__: 0 is rejected by the package-shipped schema (zero_is_valid: false)."""
        validator = SchemaValidator()
        with pytest.raises(SchemaValidationError, match="__pipeline_liveness__"):
            validator.validate({"__pipeline_liveness__": 0.0})


# ---------------------------------------------------------------------------
# Test 7 — Canary integrity
# ---------------------------------------------------------------------------


class TestCanaryIntegrity:
    def test_normal_record_includes_canary(self, execution_log, tmp_path: Path):
        observer = MetricsObserver(tmp_path / "metrics", execution_log)

        observer.on_stage_complete("stage", 1.0, {})

        records = load_metrics(tmp_path / "metrics" / "pipeline_metrics.jsonl")
        assert records[0]["metrics"]["__pipeline_liveness__"] == 42.0

    def test_canary_mismatch_raises(self, execution_log, tmp_path: Path):
        from temper_placer.pipeline.metrics_observer import CanaryCheckError
        from temper_placer.regression.metrics_recorder import PipelineMetricsRecord

        observer = MetricsObserver(tmp_path / "metrics", execution_log)

        record = PipelineMetricsRecord(
            board="test",
            stage="test",
            metrics={"wall_time_ms": 100.0},  # no canary key
            stage_name="test",
        )

        with pytest.raises(CanaryCheckError, match="Expected canary value"):
            observer._check_canary(record)

    def test_canary_wrong_value_raises(self, execution_log, tmp_path: Path):
        from temper_placer.pipeline.metrics_observer import CanaryCheckError
        from temper_placer.regression.metrics_recorder import PipelineMetricsRecord

        observer = MetricsObserver(tmp_path / "metrics", execution_log)

        record = PipelineMetricsRecord(
            board="test",
            stage="test",
            metrics={"wall_time_ms": 100.0, "__pipeline_liveness__": 99.0},
            stage_name="test",
        )

        with pytest.raises(CanaryCheckError, match="Expected canary value"):
            observer._check_canary(record)


# ---------------------------------------------------------------------------
# Test 8 — Integration: observer registered with DAG engine
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Test 8.5 — Cross-validation: Path A (start_t is not None) mismatch
# ---------------------------------------------------------------------------


class TestCrossValidationPathA:
    def test_on_stage_start_then_complete_with_zero_calltime_raises(
        self, execution_log, tmp_path: Path
    ):
        """Path A: when start_t is not None, observer's own elapsed time
        differs from caller_duration_s=0.0 by >10ms -> CrossValidationError.
        """
        import time as _time

        observer = MetricsObserver(tmp_path / "metrics", execution_log)
        observer.on_stage_start("s", 0, {})
        _time.sleep(0.02)
        with pytest.raises(CrossValidationError, match="Timing mismatch"):
            observer.on_stage_complete("s", 0.0, {})


# ---------------------------------------------------------------------------
# Test 9 — Integration: observer registered with DAG engine
# ---------------------------------------------------------------------------


class TestIntegration:
    def test_observer_fires_on_stage_transitions(
        self, passthrough_manifest: Path, sample_config, tmp_path: Path
    ):
        engine = StageDAGEngine(passthrough_manifest)
        observer = MetricsObserver(tmp_path / "metrics", engine.execution_log)
        engine.add_observer(observer)
        state = PipelineState(config=sample_config)

        with patch.object(observer._schema_validator, "validate"):
            engine.run(state)

        metrics_path = tmp_path / "metrics" / "pipeline_metrics.jsonl"
        assert metrics_path.exists()
        records = load_metrics(metrics_path)
        assert len(records) == 2
        stages = {r["stage_name"] for r in records}
        assert stages == {"input", "output"}
        for r in records:
            assert r["metrics"]["wall_time_ms"] >= 0
            assert r["metrics"]["__pipeline_liveness__"] == 42.0

    def test_observer_handles_drc_delta_from_outputs(
        self, passthrough_manifest: Path, sample_config, tmp_path: Path
    ):
        engine = StageDAGEngine(passthrough_manifest)
        observer = MetricsObserver(tmp_path / "metrics", engine.execution_log)
        engine.add_observer(observer)
        state = PipelineState(config=sample_config)

        engine.run(state)

        records = load_metrics(tmp_path / "metrics" / "pipeline_metrics.jsonl")
        for r in records:
            assert "drc_delta" not in r or r["drc_delta"] is None

    def test_execution_log_events_are_populated(
        self, passthrough_manifest: Path, sample_config
    ):
        engine = StageDAGEngine(passthrough_manifest)
        state = PipelineState(config=sample_config)

        engine.run(state)

        log_dict = engine.execution_log.to_dict()
        assert len(log_dict["events"]) >= 4  # start + complete per stage
        kinds = {e["kind"] for e in log_dict["events"]}
        assert "start" in kinds
        assert "complete" in kinds
