"""Tests for pipeline metrics trend CLI (R2, R5)."""
from pathlib import Path
from datetime import timedelta
import pytest
from temper_placer.regression.metrics_recorder import PipelineMetricsRecord, record_metrics
from scripts.pipeline_metrics import _compute_trends, _parse_window


def _make_records(tmp_path, values):
    fp = tmp_path / "t.jsonl"
    for i, v in enumerate(values):
        record_metrics(PipelineMetricsRecord(
            board=v.get("board", "temper"), stage=v.get("stage", "closure"),
            metrics=v.get("metrics", {}),
            timestamp=v.get("timestamp", f"2026-06-{10 + i:02d}T00:00:00+00:00")), fp)
    from temper_placer.regression.metrics_recorder import load_metrics
    return load_metrics(fp)


class TestParseWindow:
    def test_30d(self):
        assert _parse_window("30d") == timedelta(days=30)

    def test_7d(self):
        assert _parse_window("7d") == timedelta(days=7)

    def test_invalid(self):
        with pytest.raises(SystemExit):
            _parse_window("30h")


class TestComputeTrends:
    def test_stable_no_regression(self, tmp_path):
        r = _make_records(tmp_path, [{"metrics": {"v": 10.0}}, {"metrics": {"v": 10.1}},
            {"metrics": {"v": 10.0}}, {"metrics": {"v": 9.9}}, {"metrics": {"v": 10.0}}])
        assert not _compute_trends(r, "temper", "closure", timedelta(days=30), 1.0)["has_regression"]

    def test_outlier_flags_regression(self, tmp_path):
        r = _make_records(tmp_path, [{"metrics": {"v": 10.0}}, {"metrics": {"v": 10.1}},
            {"metrics": {"v": 10.0}}, {"metrics": {"v": 9.9}}, {"metrics": {"v": 50.0}}])
        assert _compute_trends(r, "temper", "closure", timedelta(days=30), 1.0)["has_regression"]

    def test_single_point(self, tmp_path):
        r = _make_records(tmp_path, [{"metrics": {"v": 10.0}}])
        assert "error" in _compute_trends(r, "temper", "closure", timedelta(days=30), 1.0)

    def test_wrong_board(self, tmp_path):
        r = _make_records(tmp_path, [{"board": "other", "metrics": {"v": 10.0}}])
        assert "error" in _compute_trends(r, "temper", "closure", timedelta(days=30), 1.0)

    def test_fields_computed(self, tmp_path):
        r = _make_records(tmp_path, [{"metrics": {"v": 1.0}}, {"metrics": {"v": 2.0}},
            {"metrics": {"v": 3.0}}])
        m = _compute_trends(r, "temper", "closure", timedelta(days=30), 1.0)["metrics"][0]
        assert "mean" in m and "sigma" in m and "drift_sigma" in m
        assert m["data_points"] == 3
