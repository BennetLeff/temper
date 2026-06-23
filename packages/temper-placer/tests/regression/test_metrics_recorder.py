"""Tests for pipeline metrics recorder (R1, R4)."""
import json
from pathlib import Path
import pytest
from temper_placer.regression.closure_test import ClosureResult
from temper_placer.regression.metrics_recorder import (
    CURRENT_SCHEMA_VERSION, PipelineMetricsRecord,
    find_metrics_file, load_metrics, record_closure_result, record_metrics)


class TestPipelineMetricsRecord:
    def test_to_jsonl_has_schema_version(self):
        r = PipelineMetricsRecord(board="temper", stage="closure",
            metrics={"drc_errors": 0}, timestamp="2026-06-22T00:00:00+00:00",
            git_commit="abc1234")
        d = json.loads(r.to_jsonl())
        assert d["schema_version"] == CURRENT_SCHEMA_VERSION
        assert d["board"] == "temper"

    def test_timestamp_auto_generated(self):
        r = PipelineMetricsRecord(board="test", stage="closure", metrics={})
        assert r.timestamp
        from datetime import datetime
        datetime.fromisoformat(r.timestamp)

    def test_to_jsonl_roundtrip(self):
        r = PipelineMetricsRecord(board="test", stage="closure",
            metrics={"wall_time_ms": 42000, "completion_pct": 98.5},
            git_commit="deadbeef", timestamp="2026-06-22T12:00:00+00:00")
        d = json.loads(r.to_jsonl())
        assert d["metrics"]["wall_time_ms"] == 42000


class TestRecordClosureResult:
    def test_adapts_closure_result(self):
        cr = ClosureResult(passed=True, board_id="temper", benders_iterations=12,
            benders_cuts=5, router_completion_pct=98.5, drc_errors=0,
            drc_warnings=2, wall_clock_seconds=42.0)
        r = record_closure_result(cr, board_id="temper", commit="abc1234")
        assert r.board == "temper"
        assert r.metrics["wall_time_ms"] == 42000
        assert r.metrics["benders_iterations"] == 12


class TestRecordMetrics:
    def test_appends_line(self, tmp_path: Path):
        fp = tmp_path / "test.jsonl"
        r = PipelineMetricsRecord(board="test", stage="closure",
            metrics={"drc_errors": 0}, timestamp="2026-06-22T00:00:00+00:00")
        record_metrics(r, fp)
        assert fp.exists()
        assert len(fp.read_text().strip().split("\n")) == 1

    def test_appends_multiple(self, tmp_path: Path):
        fp = tmp_path / "test.jsonl"
        for i in range(3):
            record_metrics(PipelineMetricsRecord(
                board=f"b{i}", stage="closure", metrics={"v": i},
                timestamp="2026-06-22T00:00:00+00:00"), fp)
        assert len(fp.read_text().strip().split("\n")) == 3

    def test_creates_parent_dir(self, tmp_path: Path):
        fp = tmp_path / "sub" / "m.jsonl"
        record_metrics(PipelineMetricsRecord(
            board="t", stage="c", metrics={},
            timestamp="2026-06-22T00:00:00+00:00"), fp)
        assert fp.exists()


class TestLoadMetrics:
    def test_empty_for_missing(self):
        assert load_metrics(Path("/nonexistent")) == []

    def test_loads_valid(self, tmp_path: Path):
        fp = tmp_path / "t.jsonl"
        for i in range(2):
            record_metrics(PipelineMetricsRecord(
                board=f"b{i}", stage="c", metrics={"v": float(i)},
                timestamp="2026-06-22T00:00:00+00:00"), fp)
        assert len(load_metrics(fp)) == 2

    def test_skips_invalid_json(self, tmp_path: Path):
        fp = tmp_path / "t.jsonl"
        fp.write_text('{"v": true}\nnot json\n{"v": 2}\n')
        with pytest.warns(UserWarning, match="Invalid JSON"):
            assert len(load_metrics(fp)) == 2

    def test_skips_future_schema(self, tmp_path: Path):
        fp = tmp_path / "t.jsonl"
        fp.write_text(json.dumps({"schema_version": 1, "board": "a",
            "stage": "c", "metrics": {}, "timestamp": "t", "git_commit": ""})
            + "\n" + json.dumps({"schema_version": 99, "board": "f",
            "stage": "c", "metrics": {}, "timestamp": "t", "git_commit": ""}) + "\n")
        with pytest.warns(UserWarning, match="Future schema_version 99"):
            assert len(load_metrics(fp)) == 1

    def test_warns_missing_schema(self, tmp_path: Path):
        fp = tmp_path / "t.jsonl"
        fp.write_text(json.dumps({"board": "old", "stage": "c",
            "metrics": {}, "timestamp": "t", "git_commit": ""}) + "\n")
        with pytest.warns(UserWarning, match="No schema_version"):
            assert len(load_metrics(fp)) == 1


class TestFindMetricsFile:
    def test_path(self, tmp_path: Path):
        d = tmp_path / "power_pcb_dataset" / "metrics"
        d.mkdir(parents=True)
        r = find_metrics_file(tmp_path)
        assert r.parent == d
        assert r.name == "pipeline_metrics.jsonl"
