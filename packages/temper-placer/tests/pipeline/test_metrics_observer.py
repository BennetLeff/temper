"""Tests for MetricsObserver that bridges stage events to JSONL metrics."""

from pathlib import Path
from unittest import mock

import pytest

from temper_placer.pipeline.dag_observability import PipelineExecutionLog
from temper_placer.pipeline.metrics_observer import MetricsObserver


@pytest.fixture
def tmp_output_dir(tmp_path: Path) -> Path:
    return tmp_path / "metrics"


@pytest.fixture
def execution_log() -> PipelineExecutionLog:
    return PipelineExecutionLog()


@pytest.fixture
def observer(tmp_output_dir: Path, execution_log: PipelineExecutionLog) -> MetricsObserver:
    return MetricsObserver(output_dir=tmp_output_dir, execution_log=execution_log, board="test-board")


class TestOnStageStart:
    """Tests for MetricsObserver.on_stage_start."""

    def test_records_start_time(self, observer: MetricsObserver):
        observer.on_stage_start("load", 0, {})
        assert "load" in observer._stage_start_times

    def test_multiple_stages(self, observer: MetricsObserver):
        observer.on_stage_start("load", 0, {})
        observer.on_stage_start("route", 1, {"key": "val"})
        assert "load" in observer._stage_start_times
        assert "route" in observer._stage_start_times


class TestOnStageComplete:
    """Tests for MetricsObserver.on_stage_complete."""

    def test_writes_record_on_complete(self, observer: MetricsObserver):
        with mock.patch.object(observer, "_write") as mock_write, \
             mock.patch.object(observer, "_validate_schema"), \
             mock.patch.object(observer, "_cross_validate_against"), \
             mock.patch.object(observer, "_check_canary"):
            observer.on_stage_complete("load", 0.5, {})
            mock_write.assert_called_once()

    def test_includes_drc_delta_when_present(self, observer: MetricsObserver):
        with mock.patch.object(observer, "_write") as mock_write, \
             mock.patch.object(observer, "_validate_schema"), \
             mock.patch.object(observer, "_cross_validate_against"), \
             mock.patch.object(observer, "_check_canary"):
            observer.on_stage_complete(
                "drc", 1.0,
                {"drc_errors_before": 10, "drc_errors_after": 3},
            )
            mock_write.assert_called_once()
            record = mock_write.call_args[0][0]
            assert record.drc_delta == 7

    def test_strips_start_time_after_complete(self, observer: MetricsObserver):
        observer._stage_start_times["load"] = 100.0
        with mock.patch.object(observer, "_validate_schema"), \
             mock.patch.object(observer, "_cross_validate_against"), \
             mock.patch.object(observer, "_check_canary"), \
             mock.patch.object(observer, "_write"):
            observer.on_stage_complete("load", 0.5, {})
        assert "load" not in observer._stage_start_times


class TestOnStageSkip:
    """Tests for MetricsObserver.on_stage_skip (no-op)."""

    def test_noop(self, observer: MetricsObserver):
        observer.on_stage_skip("load", "condition false")
        # No exception raised, no side effects.


class TestOnStageError:
    """Tests for MetricsObserver.on_stage_error (no-op)."""

    def test_noop(self, observer: MetricsObserver):
        observer.on_stage_error("load", ValueError("bad input"))
        # No exception raised.


class TestOnFeedbackTriggered:
    """Tests for MetricsObserver.on_feedback_triggered (no-op)."""

    def test_noop(self, observer: MetricsObserver):
        observer.on_feedback_triggered("sidecar", "route", "place", 2)
        # No exception raised.


class TestOnPipelineComplete:
    """Tests for MetricsObserver.on_pipeline_complete (no-op)."""

    def test_noop(self, observer: MetricsObserver):
        observer.on_pipeline_complete(True, 10.0, {"load": 1.0, "route": 9.0})
        # No exception raised.
