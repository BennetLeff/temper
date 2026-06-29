"""Tests for pipeline_report.py (U7)."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline_report import _build_data, _compute_p95, generate_report

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "packages" / "temper-placer" / "src"))
from temper_placer.regression.metrics_recorder import load_metrics


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def _metrics_jsonl(stages: list[dict]) -> str:
    """Build a JSONL string from stage dicts with name, duration_ms, drc_delta, history_count."""
    lines = []
    for s in stages:
        rec = {
            "schema_version": 2,
            "timestamp": "2026-06-28T00:00:00+00:00",
            "git_commit": "abc123",
            "board": "temper",
            "stage": s["name"],
            "stage_name": s["name"],
            "metrics": {"wall_time_ms": s["duration_ms"]},
        }
        if s.get("drc_delta") is not None:
            rec["drc_delta"] = s["drc_delta"]
        lines.append(json.dumps(rec))
    return "\n".join(lines)


def _execution_json(stage_names: list[str], durations_s: list[float], success: bool = True) -> str:
    stage_timings = {name: dur for name, dur in zip(stage_names, durations_s)}
    return json.dumps({
        "stage_order": stage_names,
        "stage_timings": stage_timings,
        "total_duration_s": sum(durations_s),
        "success": success,
        "events": [],
    })


class TestComputeP95:
    def test_returns_none_for_few_records(self):
        records = [
            {"stage_name": "placement", "metrics": {"wall_time_ms": 100}},
        ]
        p95, p99 = _compute_p95(records, "placement")
        assert p95 is None
        assert p99 is None

    def test_returns_p95_with_enough_records(self):
        records = [
            {"stage_name": "placement", "metrics": {"wall_time_ms": v}}
            for v in [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
        ]
        p95, p99 = _compute_p95(records, "placement")
        assert p95 == pytest.approx(95.5)
        assert p99 == pytest.approx(99.1)

    def test_matches_stage_name_or_stage_field(self):
        records = [
            {"stage": "routing", "metrics": {"wall_time_ms": v}}
            for v in [10, 20, 30, 40, 50]
        ]
        assert _compute_p95(records, "routing")[0] is not None


class TestBuildData:
    def test_stage_order_matches_execution_log(self):
        metrics = [{"stage_name": s, "stage": s, "metrics": {"wall_time_ms": 100}} for s in ["a", "b", "c"]]
        exec_log = {"stage_order": ["a", "b", "c"], "stage_timings": {"a": 0.1, "b": 0.2, "c": 0.3}}
        data = _build_data(metrics, exec_log)
        assert [s["name"] for s in data["stages"]] == ["a", "b", "c"]

    def test_no_history_all_grey(self):
        metrics = [{"stage_name": "foo", "stage": "foo", "metrics": {"wall_time_ms": 50}}]
        exec_log = {"stage_order": ["foo"], "stage_timings": {"foo": 0.05}}
        data = _build_data(metrics, exec_log)
        assert data["has_history"] is False
        assert data["stages"][0]["color"] == "var(--grey)"

    def test_with_history_green_when_under_p95(self):
        metrics = [{"stage_name": "foo", "stage": "foo", "metrics": {"wall_time_ms": v}}
                   for v in [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]]
        exec_log = {"stage_order": ["foo"], "stage_timings": {"foo": 0.05}}
        data = _build_data(metrics, exec_log)
        assert data["has_history"] is True
        assert data["stages"][0]["color"] == "var(--green)"

    def test_drc_violations_collected(self):
        metrics = [
            {"stage_name": "drc", "stage": "drc", "metrics": {"wall_time_ms": 100}, "drc_delta": 3},
        ]
        exec_log = {"stage_order": ["drc"], "stage_timings": {"drc": 0.1}}
        data = _build_data(metrics, exec_log)
        assert len(data["drc_violations"]) == 1
        assert data["drc_violations"][0]["drc_delta"] == 3


class TestGenerateReportEndToEnd:
    def test_happy_path_produces_valid_html(self, tmp_path):
        metrics_file = tmp_path / "metrics.jsonl"
        exec_file = tmp_path / "execution.json"
        output_file = tmp_path / "report.html"

        _write(metrics_file, _metrics_jsonl([
            {"name": "placement", "duration_ms": 5000},
            {"name": "routing", "duration_ms": 8000, "drc_delta": 2},
            {"name": "drc", "duration_ms": 2000, "drc_delta": 2},
        ] + [
            {"name": "placement", "duration_ms": 4000 + i * 100} for i in range(10)
        ]))
        _write(exec_file, _execution_json(
            ["placement", "routing", "drc"],
            [5.0, 8.0, 2.0],
        ))

        generate_report(metrics_file, exec_file, output_file)

        html = output_file.read_text()
        assert "<!DOCTYPE html>" in html
        assert "window.__PIPELINE_DATA__" in html
        assert "placement" in html
        assert "routing" in html
        assert "drc" in html

    def test_per_stage_timing_table_present(self, tmp_path):
        metrics_file = tmp_path / "metrics.jsonl"
        exec_file = tmp_path / "execution.json"
        output_file = tmp_path / "report.html"

        _write(metrics_file, _metrics_jsonl([
            {"name": "placement", "duration_ms": 5000},
            {"name": "routing", "duration_ms": 8000},
        ] + [
            {"name": "placement", "duration_ms": 4000 + i * 100} for i in range(10)
        ]))
        _write(exec_file, _execution_json(["placement", "routing"], [5.0, 8.0]))

        generate_report(metrics_file, exec_file, output_file)

        html = output_file.read_text()
        assert '<table id="stage-table">' in html
        assert '"duration_ms": 5000' in html
        assert '"duration_ms": 8000' in html

    def test_drc_summary_present(self, tmp_path):
        metrics_file = tmp_path / "metrics.jsonl"
        exec_file = tmp_path / "execution.json"
        output_file = tmp_path / "report.html"

        _write(metrics_file, _metrics_jsonl([
            {"name": "drc", "duration_ms": 2000, "drc_delta": 3},
        ] + [
            {"name": "drc", "duration_ms": 2000 + i * 50} for i in range(10)
        ]))
        _write(exec_file, _execution_json(["drc"], [2.0]))

        generate_report(metrics_file, exec_file, output_file)

        html = output_file.read_text()
        assert "DRC Summary" in html
        assert "3" in html  # drc_delta value

    def test_first_run_baseline_building(self, tmp_path):
        metrics_file = tmp_path / "metrics.jsonl"
        exec_file = tmp_path / "execution.json"
        output_file = tmp_path / "report.html"

        _write(metrics_file, _metrics_jsonl([
            {"name": "placement", "duration_ms": 5000},
        ]))  # only 1 record, < 5 for p95
        _write(exec_file, _execution_json(["placement"], [5.0]))

        generate_report(metrics_file, exec_file, output_file)

        html = output_file.read_text()
        assert "Baseline building" in html

    def test_empty_drc_no_violations(self, tmp_path):
        metrics_file = tmp_path / "metrics.jsonl"
        exec_file = tmp_path / "execution.json"
        output_file = tmp_path / "report.html"

        _write(metrics_file, _metrics_jsonl([
            {"name": "placement", "duration_ms": 5000},
        ] + [
            {"name": "placement", "duration_ms": 4000 + i * 100} for i in range(10)
        ]))
        _write(exec_file, _execution_json(["placement"], [5.0]))

        generate_report(metrics_file, exec_file, output_file)

        html = output_file.read_text()
        assert "No DRC violations" in html

    def test_zero_duration_stage_shows_min_px_width(self, tmp_path):
        metrics_file = tmp_path / "metrics.jsonl"
        exec_file = tmp_path / "execution.json"
        output_file = tmp_path / "report.html"

        _write(metrics_file, _metrics_jsonl([
            {"name": "placement", "duration_ms": 5000},
            {"name": "zero_stage", "duration_ms": 0},
        ] + [
            {"name": "placement", "duration_ms": 4000 + i * 100} for i in range(10)
        ]))
        _write(exec_file, _execution_json(["placement", "zero_stage"], [5.0, 0.0]))

        generate_report(metrics_file, exec_file, output_file)

        html = output_file.read_text()
        assert '"duration_ms": 0' in html
        assert "min-width: 4px" in html

    def test_load_jsonl_skips_invalid_lines(self, tmp_path):
        jsonl = tmp_path / "test.jsonl"
        jsonl.write_text('{}\nnot json\n{"valid": true}\n')
        records = load_metrics(jsonl)
        assert len(records) == 2

    def test_load_jsonl_empty_or_missing(self, tmp_path):
        missing = tmp_path / "missing.jsonl"
        assert load_metrics(missing) == []

        empty = tmp_path / "empty.jsonl"
        empty.write_text("")
        assert load_metrics(empty) == []

    def test_yellow_when_above_p95(self, tmp_path):
        metrics_file = tmp_path / "metrics.jsonl"
        exec_file = tmp_path / "execution.json"
        output_file = tmp_path / "report.html"

        historical = [{"stage_name": "slow", "stage": "slow", "metrics": {"wall_time_ms": v}}
                      for v in [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]]
        current = {"stage_name": "slow", "stage": "slow", "metrics": {"wall_time_ms": 97}}
        _write(metrics_file, "\n".join(json.dumps(r) for r in historical + [current]))
        _write(exec_file, _execution_json(["slow"], [0.097]))

        generate_report(metrics_file, exec_file, output_file)
        html = output_file.read_text()
        assert "var(--yellow)" in html
