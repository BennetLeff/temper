"""Tests for pipeline metrics recorder (R1, R4)."""

import json
from pathlib import Path

import pytest

from temper_placer.regression.closure_test import ClosureResult
from temper_placer.regression.metrics_recorder import (
    CURRENT_SCHEMA_VERSION,
    PipelineMetricsRecord,
    find_metrics_file,
    load_metrics,
    record_closure_result,
    record_metrics,
)


class TestPipelineMetricsRecord:
    def test_to_jsonl_has_schema_version(self):
        record = PipelineMetricsRecord(
            board="temper",
            stage="closure",
            metrics={"drc_errors": 0},
            timestamp="2026-06-22T00:00:00+00:00",
            git_commit="abc1234",
        )
        data = json.loads(record.to_jsonl())
        assert data["schema_version"] == CURRENT_SCHEMA_VERSION
        assert data["board"] == "temper"
        assert data["stage"] == "closure"
        assert data["git_commit"] == "abc1234"
        assert data["metrics"]["drc_errors"] == 0

    def test_timestamp_auto_generated(self):
        record = PipelineMetricsRecord(board="test", stage="closure", metrics={})
        assert record.timestamp
        from datetime import datetime
        datetime.fromisoformat(record.timestamp)

    def test_to_jsonl_roundtrip(self):
        record = PipelineMetricsRecord(
            board="test",
            stage="closure",
            metrics={"wall_time_ms": 42000, "completion_pct": 98.5},
            git_commit="deadbeef",
            timestamp="2026-06-22T12:00:00+00:00",
        )
        data = json.loads(record.to_jsonl())
        assert data["metrics"]["wall_time_ms"] == 42000
        assert data["metrics"]["completion_pct"] == 98.5


class TestRecordClosureResult:
    def test_adapts_closure_result(self):
        result = ClosureResult(
            passed=True,
            board_id="temper",
            benders_iterations=12,
            benders_cuts=5,
            router_completion_pct=98.5,
            drc_errors=0,
            drc_warnings=2,
            wall_clock_seconds=42.0,
        )
        record = record_closure_result(result, board_id="temper", commit="abc1234")
        assert record.board == "temper"
        assert record.stage == "closure"
        assert record.git_commit == "abc1234"
        m = record.metrics
        assert m["completion_pct"] == 98.5
        assert m["drc_errors"] == 0
        assert m["drc_warnings"] == 2
        assert m["wall_time_ms"] == 42000
        assert m["benders_iterations"] == 12
        assert m["benders_cuts"] == 5


class TestRecordMetrics:
    def test_appends_line(self, tmp_path: Path):
        filepath = tmp_path / "test_metrics.jsonl"
        record = PipelineMetricsRecord(
            board="test", stage="closure", metrics={"drc_errors": 0},
            timestamp="2026-06-22T00:00:00+00:00",
        )
        record_metrics(record, filepath)
        assert filepath.exists()
        lines = filepath.read_text().strip().split("\n")
        assert len(lines) == 1

    def test_appends_multiple(self, tmp_path: Path):
        filepath = tmp_path / "test_multi.jsonl"
        for i in range(3):
            record = PipelineMetricsRecord(
                board=f"board_{i}", stage="closure", metrics={"drc_errors": i},
                timestamp="2026-06-22T00:00:00+00:00",
            )
            record_metrics(record, filepath)
        lines = filepath.read_text().strip().split("\n")
        assert len(lines) == 3

    def test_creates_parent_dir(self, tmp_path: Path):
        filepath = tmp_path / "subdir" / "metrics.jsonl"
        record = PipelineMetricsRecord(
            board="test", stage="closure", metrics={},
            timestamp="2026-06-22T00:00:00+00:00",
        )
        record_metrics(record, filepath)
        assert filepath.exists()


class TestLoadMetrics:
    def test_empty_for_missing_file(self):
        records = load_metrics(Path("/nonexistent/path.jsonl"))
        assert records == []

    def test_loads_valid_records(self, tmp_path: Path):
        filepath = tmp_path / "valid.jsonl"
        record1 = PipelineMetricsRecord(
            board="a", stage="closure", metrics={"v": 1.0},
            timestamp="2026-06-22T00:00:00+00:00",
        )
        record2 = PipelineMetricsRecord(
            board="b", stage="closure", metrics={"v": 2.0},
            timestamp="2026-06-22T01:00:00+00:00",
        )
        record_metrics(record1, filepath)
        record_metrics(record2, filepath)
        records = load_metrics(filepath)
        assert len(records) == 2
        assert records[0]["board"] == "a"
        assert records[1]["board"] == "b"

    def test_skips_invalid_json(self, tmp_path: Path):
        filepath = tmp_path / "invalid.jsonl"
        filepath.write_text('{"valid": true}\nnot json\n{"also": "valid"}\n')
        with pytest.warns(UserWarning, match="Invalid JSON at line 2"):
            records = load_metrics(filepath)
        assert len(records) == 2

    def test_skips_future_schema(self, tmp_path: Path):
        filepath = tmp_path / "future.jsonl"
        v1 = json.dumps({"schema_version": CURRENT_SCHEMA_VERSION, "board": "a",
                          "stage": "c", "metrics": {}, "timestamp": "t", "git_commit": ""})
        v99 = json.dumps({"schema_version": 99, "board": "future",
                           "stage": "c", "metrics": {}, "timestamp": "t", "git_commit": ""})
        filepath.write_text(v1 + "\n" + v99 + "\n")
        with pytest.warns(UserWarning, match="Future schema_version 99"):
            records = load_metrics(filepath)
        assert len(records) == 1
        assert records[0]["board"] == "a"

    def test_warns_missing_schema(self, tmp_path: Path):
        filepath = tmp_path / "no_version.jsonl"
        filepath.write_text(
            json.dumps({"board": "legacy", "stage": "c", "metrics": {},
                         "timestamp": "t", "git_commit": ""}) + "\n"
        )
        with pytest.warns(UserWarning, match="No schema_version"):
            records = load_metrics(filepath)
        assert len(records) == 1

    def test_skips_empty_lines(self, tmp_path: Path):
        filepath = tmp_path / "empty_lines.jsonl"
        filepath.write_text(
            '\n\n{"schema_version": 1, "board": "a", "stage": "c", '
            '"metrics": {}, "timestamp": "t", "git_commit": ""}\n\n'
        )
        records = load_metrics(filepath)
        assert len(records) == 1


class TestFindMetricsFile:
    def test_returns_expected_path(self, tmp_path: Path):
        metrics_dir = tmp_path / "power_pcb_dataset" / "metrics"
        metrics_dir.mkdir(parents=True)
        result = find_metrics_file(tmp_path)
        assert result.parent == metrics_dir
        assert result.name == "pipeline_metrics.jsonl"
