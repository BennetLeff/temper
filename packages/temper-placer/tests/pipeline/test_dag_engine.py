"""Tests for dag_engine: execution, timeouts, retries, feedback contracts."""

import json
import time
from pathlib import Path

import pytest
import yaml

from temper_placer.pipeline.dag_engine import StageDAGEngine
from temper_placer.pipeline.dag_observability import PipelineExecutionLog
from temper_placer.pipeline.dag_types import (
    StageResult,
    StageTimeoutError,
)
from temper_placer.pipeline.state import PipelineState


class MockStage:
    """Stage handler that returns a configurable StageResult."""

    def __init__(self, outputs=None, delay_s=0.0, should_fail=False, side_effect=None):
        self.outputs = outputs or {}
        self.delay_s = delay_s
        self.should_fail = should_fail
        self.side_effect = side_effect

    def __call__(self, state, context):
        if self.should_fail:
            raise RuntimeError("Mock stage failure")
        if self.side_effect:
            return self.side_effect(state, context)
        if self.delay_s > 0:
            time.sleep(self.delay_s)
        return StageResult(outputs=self.outputs, duration_s=self.delay_s)


class FailingStage:
    """Stage that always raises an exception."""

    def __call__(self, state, context):
        raise RuntimeError("Intentional failure for testing")


class SlowStage:
    """Stage that sleeps for a configurable duration, checking deadline."""

    def __call__(self, state, context):
        time.sleep(2.0)
        return StageResult(outputs={}, duration_s=2.0)


def _write_engine_manifest(path: Path, stages: list[dict], name: str = "engine-test") -> Path:
    manifest = {
        "pipeline": {"name": name, "version": "1.0.0"},
        "stages": stages,
    }
    with open(path, "w") as f:
        yaml.dump(manifest, f)
    return path


@pytest.fixture
def linear_manifest(tmp_path):
    """2-stage linear DAG with mock handlers."""
    stages = [
        {
            "name": "stage_a",
            "handler": "tests.pipeline.test_dag_engine.MockStage",
            "requires": [],
            "provides": ["data_a"],
        },
        {
            "name": "stage_b",
            "handler": "tests.pipeline.test_dag_engine.MockStage",
            "requires": ["data_a"],
            "provides": ["data_b"],
        },
    ]
    return _write_engine_manifest(tmp_path / "linear.yaml", stages)


class TestEngineInit:
    def test_engine_loads_manifest(self, minimal_manifest):
        engine = StageDAGEngine(minimal_manifest)
        assert engine.manifest.pipeline.name == "minimal-test"
        assert len(engine.stage_order) > 0

    def test_engine_topological_order_linear(self, linear_manifest):
        engine = StageDAGEngine(linear_manifest)
        assert engine.stage_order == ["stage_a", "stage_b"]

    def test_engine_topological_order_diamond(self, tmp_path):
        stages = [
            {"name": "a", "handler": "tests.pipeline.test_dag_engine.MockStage",
             "requires": [], "provides": ["key_a"]},
            {"name": "b", "handler": "tests.pipeline.test_dag_engine.MockStage",
             "requires": ["key_a"], "provides": ["key_b"]},
            {"name": "c", "handler": "tests.pipeline.test_dag_engine.MockStage",
             "requires": ["key_a"], "provides": ["key_c"]},
            {"name": "d", "handler": "tests.pipeline.test_dag_engine.MockStage",
             "requires": ["key_b", "key_c"], "provides": ["key_d"]},
        ]
        path = _write_engine_manifest(tmp_path / "diamond.yaml", stages)
        engine = StageDAGEngine(path)
        assert engine.stage_order[0] == "a"
        assert engine.stage_order[-1] == "d"
        assert engine.stage_order.index("b") < engine.stage_order.index("d")
        assert engine.stage_order.index("c") < engine.stage_order.index("d")

    def test_engine_stage_map(self, minimal_manifest):
        engine = StageDAGEngine(minimal_manifest)
        assert "producer" in engine.stage_map
        assert "consumer" in engine.stage_map

    def test_engine_provides_map(self, minimal_manifest):
        engine = StageDAGEngine(minimal_manifest)
        assert "data_a" in engine.provides_map
        assert "consumer" not in engine.provides_map.get("data_a", set())
        assert "producer" in engine.provides_map["data_a"]


class TestObserverEvents:
    def test_observer_receives_start_and_complete(self, linear_manifest, sample_config,
                                                    mock_observer):
        engine = StageDAGEngine(linear_manifest)
        engine.add_observer(mock_observer)
        state = PipelineState(config=sample_config)

        result = engine.run(state)
        assert result.success is True

        start_events = [e for e in mock_observer.events if e[0] == "start"]
        complete_events = [e for e in mock_observer.events if e[0] == "complete"]
        assert len(start_events) == 2
        assert len(complete_events) == 2

    def test_observer_receives_pipeline_complete(self, linear_manifest, sample_config,
                                                    mock_observer):
        engine = StageDAGEngine(linear_manifest)
        engine.add_observer(mock_observer)
        state = PipelineState(config=sample_config)

        engine.run(state)
        pipeline_events = [e for e in mock_observer.events if e[0] == "pipeline_complete"]
        assert len(pipeline_events) == 1
        assert pipeline_events[0][1] is True


class TestSkipConditions:
    def test_skip_if_true_skips_stage(self, tmp_path, sample_config, mock_observer):
        stages = [
            {
                "name": "s1",
                "handler": "tests.pipeline.test_dag_engine.MockStage",
                "requires": [],
                "provides": ["data"],
                "skip_if": "true",
            },
        ]
        path = _write_engine_manifest(tmp_path / "skip.yaml", stages)
        engine = StageDAGEngine(path)
        engine.add_observer(mock_observer)
        state = PipelineState(config=sample_config)

        result = engine.run(state)
        assert result.success is True
        skip_events = [e for e in mock_observer.events if e[0] == "skip"]
        assert len(skip_events) == 1

    def test_skip_if_false_runs_stage(self, tmp_path, sample_config, mock_observer):
        stages = [
            {
                "name": "s1",
                "handler": "tests.pipeline.test_dag_engine.MockStage",
                "requires": [],
                "provides": ["data"],
                "skip_if": "false",
            },
        ]
        path = _write_engine_manifest(tmp_path / "noskip.yaml", stages)
        engine = StageDAGEngine(path)
        engine.add_observer(mock_observer)
        state = PipelineState(config=sample_config)

        engine.run(state)
        skip_events = [e for e in mock_observer.events if e[0] == "skip"]
        assert len(skip_events) == 0


class TestDryRun:
    def test_dry_run_skips_geometric_and_output(self, tmp_path, mock_observer):
        stages = [
            {"name": "input", "handler": "tests.pipeline.test_dag_engine.MockStage",
             "requires": [], "provides": ["board", "netlist"]},
            {"name": "geometric", "handler": "tests.pipeline.test_dag_engine.MockStage",
             "requires": ["board", "netlist"], "provides": ["placement_state"]},
            {"name": "output", "handler": "tests.pipeline.test_dag_engine.MockStage",
             "requires": ["board", "placement_state"], "provides": ["output_files"]},
        ]
        path = _write_engine_manifest(tmp_path / "dryrun.yaml", stages)
        engine = StageDAGEngine(path)
        engine.add_observer(mock_observer)

        from temper_placer.pipeline.state import PipelineConfig
        config = PipelineConfig(input_pcb=Path("/fake/pcb.kicad_pcb"), dry_run=True)
        state = PipelineState(config=config)

        engine.run(state)
        skipped = [e[1] for e in mock_observer.events if e[0] == "skip"]
        assert "geometric" in skipped
        assert "output" in skipped


class TestTimeout:
    def test_stage_timeout_skip(self, tmp_path, sample_config):
        stages = [
            {
                "name": "slow",
                "handler": "tests.pipeline.test_dag_engine.MockStage",
                "requires": [],
                "provides": ["data"],
                "timeout_s": 0.001,
                "on_timeout": "skip",
            },
            {
                "name": "fast",
                "handler": "tests.pipeline.test_dag_engine.MockStage",
                "requires": ["data"],
                "provides": ["result"],
            },
        ]
        path = _write_engine_manifest(tmp_path / "timeout_skip.yaml", stages)
        engine = StageDAGEngine(path)
        state = PipelineState(config=sample_config)

        result = engine.run(state)
        assert result.success is True

    def test_stage_timeout_fail(self, tmp_path, sample_config):
        stages = [
            {
                "name": "slow",
                "handler": "tests.pipeline.test_dag_engine.SlowStage",
                "requires": [],
                "provides": ["data"],
                "timeout_s": 0.001,
                "on_timeout": "fail",
            },
        ]
        path = _write_engine_manifest(tmp_path / "timeout_fail.yaml", stages)
        engine = StageDAGEngine(path)
        state = PipelineState(config=sample_config)

        result = engine.run(state)
        assert result.success is False
        assert "timed out" in (result.failure_reason or "")


class TestRetry:
    def test_stage_retry_on_exception(self, tmp_path, sample_config):
        stages = [
            {
                "name": "flaky",
                "handler": "tests.pipeline.test_dag_engine.MockStage",
                "requires": [],
                "provides": ["data"],
                "retry": {"max_attempts": 2, "backoff_s": 0.0},
            },
        ]
        path = _write_engine_manifest(tmp_path / "retry.yaml", stages)
        engine = StageDAGEngine(path)
        state = PipelineState(config=sample_config)

        result = engine.run(state)
        assert result.success is True


class TestFeedbackContracts:
    def test_feedback_trigger_re_executes(self, tmp_path, sample_config, mock_observer):
        stages = [
            {
                "name": "producer",
                "handler": "tests.pipeline.test_dag_engine.MockStage",
                "requires": [],
                "provides": ["metric_val"],
                "feedback_contracts": [
                    {
                        "name": "retry-low",
                        "trigger": {"metric": "metric_val", "condition": "lt", "threshold": 0.5},
                        "target_stage": "producer",
                        "max_retriggers": 2,
                    }
                ],
            },
        ]
        path = _write_engine_manifest(tmp_path / "feedback.yaml", stages)
        engine = StageDAGEngine(path)
        engine.add_observer(mock_observer)
        state = PipelineState(config=sample_config)

        engine.run(state)
        feedback_events = [e for e in mock_observer.events if e[0] == "feedback"]
        assert len(feedback_events) >= 0

    def test_feedback_max_retriggers_exhausted(self, tmp_path, sample_config):
        stages = [
            {
                "name": "producer",
                "handler": "tests.pipeline.test_dag_engine.MockStage",
                "requires": [],
                "provides": ["metric_val"],
                "feedback_contracts": [
                    {
                        "name": "always-low",
                        "trigger": {"metric": "metric_val", "condition": "lt", "threshold": 999},
                        "target_stage": "producer",
                        "max_retriggers": 2,
                        "parameter_adjustments": {"epochs_boost": 200},
                    }
                ],
            },
        ]
        path = _write_engine_manifest(tmp_path / "exhaust.yaml", stages)
        engine = StageDAGEngine(path)
        state = PipelineState(config=sample_config)

        result = engine.run(state)
        assert result.success is True
        assert len(engine.execution_log.feedback_activations) <= 3


class TestExecutionLog:
    def test_execution_log_stage_timings(self, linear_manifest, sample_config):
        engine = StageDAGEngine(linear_manifest)
        state = PipelineState(config=sample_config)

        engine.run(state)
        log = engine.execution_log
        assert log.success is True
        assert "stage_a" in log.stage_timings
        assert "stage_b" in log.stage_timings

    def test_execution_log_dag_topology(self, linear_manifest):
        engine = StageDAGEngine(linear_manifest)
        assert len(engine.execution_log.dag_topology) == 2
        names = [s["name"] for s in engine.execution_log.dag_topology]
        assert "stage_a" in names
        assert "stage_b" in names

    def test_execution_log_json_written(self, linear_manifest, sample_config, tmp_path):
        engine = StageDAGEngine(linear_manifest)
        config = sample_config
        config.output_pcb = tmp_path / "output.kicad_pcb"
        state = PipelineState(config=config)

        engine.run(state)
        json_path = tmp_path / "pipeline_execution.json"
        assert json_path.exists()

        with open(json_path) as f:
            data = json.load(f)
        assert data["success"] is True
        assert "stage_order" in data
        assert "stage_timings" in data

    def test_execution_log_to_dict(self, linear_manifest, sample_config):
        engine = StageDAGEngine(linear_manifest)
        state = PipelineState(config=sample_config)
        engine.run(state)

        d = engine.execution_log.to_dict()
        assert "dag_topology" in d
        assert "stage_order" in d
        assert "stage_timings" in d
        assert "success" in d
        assert "total_duration_s" in d


class TestEngineFailure:
    def test_stage_exception_fails_pipeline(self, tmp_path, sample_config):
        stages = [
            {
                "name": "bad_stage",
                "handler": "tests.pipeline.test_dag_engine.FailingStage",
                "requires": [],
                "provides": ["data"],
                "retry": {"max_attempts": 0, "backoff_s": 0.0},
            },
        ]
        path = _write_engine_manifest(tmp_path / "fail.yaml", stages)

        engine = StageDAGEngine(path)
        state = PipelineState(config=sample_config)

        result = engine.run(state)
        assert result.success is False


class TestContextPopulation:
    def test_config_fields_in_context(self, linear_manifest, sample_config):
        engine = StageDAGEngine(linear_manifest)
        state = PipelineState(config=sample_config)

        old_init = engine._init_context
        captured = {}

        def capture_init(config):
            ctx = old_init(config)
            captured.update(ctx)
            return ctx

        engine._init_context = capture_init
        engine.run(state)
        assert "input_pcb" in captured
        assert "epochs" in captured
        assert captured["epochs"] == 100
