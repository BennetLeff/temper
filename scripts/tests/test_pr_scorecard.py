"""Tests for pr_scorecard.py."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pr_scorecard import compute_scorecard, format_markdown, load_metrics


def _record(stage_name, wall_time_ms, drc_delta=None):
    """Build a minimal valid pipeline metrics record."""
    rec = {
        "schema_version": 2,
        "board": "temper",
        "stage": stage_name,
        "stage_name": stage_name,
        "metrics": {"wall_time_ms": float(wall_time_ms)},
    }
    if drc_delta is not None:
        rec["drc_delta"] = drc_delta
    return rec


def _write_jsonl(tmp_path, name, records):
    path = tmp_path / name
    with open(path, "w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")
    return path


class TestLoadMetrics:
    def test_load_valid_jsonl(self, tmp_path):
        path = tmp_path / "test.jsonl"
        path.write_text('{"a": 1}\n{"b": 2}\n')
        records = load_metrics(path)
        assert len(records) == 2

    def test_load_empty_file(self, tmp_path):
        path = tmp_path / "empty.jsonl"
        path.write_text("")
        records = load_metrics(path)
        assert records == []

    def test_load_missing_file(self, tmp_path):
        records = load_metrics(tmp_path / "nonexistent.jsonl")
        assert records == []

    def test_skip_invalid_json(self, tmp_path):
        path = tmp_path / "invalid.jsonl"
        path.write_text('{"valid": 1}\nnot json\n{"also": 2}\n')
        records = load_metrics(path)
        assert len(records) == 2


class TestComputeScorecard:
    def test_happy_same_stages(self, tmp_path):
        baseline = [
            _record("parse", 1234),
            _record("placement", 45000, drc_delta=2),
        ]
        current = [
            _record("parse", 1289),
            _record("placement", 45200, drc_delta=4),
        ]
        b_path = _write_jsonl(tmp_path, "baseline.jsonl", baseline)
        c_path = _write_jsonl(tmp_path, "current.jsonl", current)

        b = load_metrics(b_path)
        c = load_metrics(c_path)
        rows = compute_scorecard(b, c)

        assert len(rows) == 2
        assert rows[0]["stage"] == "parse"
        assert rows[0]["baseline_ms"] == 1234
        assert rows[0]["current_ms"] == 1289
        assert rows[0]["delta_pct"] == 4.5  # (1289-1234)/1234*100
        assert rows[0]["drc_delta"] is None
        assert rows[0]["status"] == "ok"

        assert rows[1]["stage"] == "placement"
        assert rows[1]["baseline_ms"] == 45000
        assert rows[1]["current_ms"] == 45200
        assert rows[1]["delta_pct"] == 0.4  # (45200-45000)/45000*100
        assert rows[1]["drc_delta"] == 4
        assert rows[1]["status"] == "ok"

    def test_no_significant_change(self, tmp_path):
        baseline = [_record("parse", 1000)]
        current = [_record("parse", 1005)]
        b_path = _write_jsonl(tmp_path, "baseline.jsonl", baseline)
        c_path = _write_jsonl(tmp_path, "current.jsonl", current)

        rows = compute_scorecard(load_metrics(b_path), load_metrics(c_path))
        assert rows[0]["delta_pct"] == 0.5

    def test_new_stage(self, tmp_path):
        baseline = [_record("parse", 1000)]
        current = [_record("parse", 1000), _record("fanout", 500)]
        b_path = _write_jsonl(tmp_path, "baseline.jsonl", baseline)
        c_path = _write_jsonl(tmp_path, "current.jsonl", current)

        rows = compute_scorecard(load_metrics(b_path), load_metrics(c_path))
        assert len(rows) == 2
        new_rows = [r for r in rows if r["status"] == "new"]
        assert len(new_rows) == 1
        assert new_rows[0]["stage"] == "fanout"
        assert new_rows[0]["current_ms"] == 500
        assert new_rows[0]["baseline_ms"] is None
        assert new_rows[0]["delta_pct"] is None

    def test_removed_stage(self, tmp_path):
        baseline = [_record("parse", 1000), _record("routing", 30000)]
        current = [_record("parse", 1000)]
        b_path = _write_jsonl(tmp_path, "baseline.jsonl", baseline)
        c_path = _write_jsonl(tmp_path, "current.jsonl", current)

        rows = compute_scorecard(load_metrics(b_path), load_metrics(c_path))
        assert len(rows) == 2
        removed_rows = [r for r in rows if r["status"] == "removed"]
        assert len(removed_rows) == 1
        assert removed_rows[0]["stage"] == "routing"
        assert removed_rows[0]["baseline_ms"] == 30000
        assert removed_rows[0]["current_ms"] is None
        assert removed_rows[0]["delta_pct"] is None
        assert removed_rows[0]["drc_delta"] is None

    def test_zero_wall_time_baseline(self, tmp_path):
        baseline = [_record("parse", 0)]
        current = [_record("parse", 500)]
        b_path = _write_jsonl(tmp_path, "baseline.jsonl", baseline)
        c_path = _write_jsonl(tmp_path, "current.jsonl", current)

        rows = compute_scorecard(load_metrics(b_path), load_metrics(c_path))
        assert rows[0]["delta_pct"] is None  # N/A when baseline is 0
        assert rows[0]["current_ms"] == 500
        assert rows[0]["baseline_ms"] == 0

    def test_negative_delta(self, tmp_path):
        baseline = [_record("parse", 2000)]
        current = [_record("parse", 1500)]
        b_path = _write_jsonl(tmp_path, "baseline.jsonl", baseline)
        c_path = _write_jsonl(tmp_path, "current.jsonl", current)

        rows = compute_scorecard(load_metrics(b_path), load_metrics(c_path))
        assert rows[0]["delta_pct"] == -25.0  # improvement

    def test_stage_name_from_stage_fallback(self, tmp_path):
        baseline = [{"stage": "parse", "metrics": {"wall_time_ms": 100.0}}]
        current = [{"stage": "parse", "metrics": {"wall_time_ms": 110.0}}]
        b_path = _write_jsonl(tmp_path, "baseline.jsonl", baseline)
        c_path = _write_jsonl(tmp_path, "current.jsonl", current)

        rows = compute_scorecard(load_metrics(b_path), load_metrics(c_path))
        assert rows[0]["stage"] == "parse"
        assert rows[0]["delta_pct"] == 10.0

    def test_empty_both_files(self, tmp_path):
        b_path = _write_jsonl(tmp_path, "baseline.jsonl", [])
        c_path = _write_jsonl(tmp_path, "current.jsonl", [])
        rows = compute_scorecard(load_metrics(b_path), load_metrics(c_path))
        assert rows == []


class TestFormatMarkdown:
    def test_formatted_table(self):
        rows = [
            {
                "stage": "parse",
                "status": "ok",
                "baseline_ms": 1234,
                "current_ms": 1289,
                "delta_pct": 4.5,
                "drc_delta": None,
            },
            {
                "stage": "placement",
                "status": "ok",
                "baseline_ms": 45000,
                "current_ms": 45200,
                "delta_pct": 0.4,
                "drc_delta": 4,
            },
        ]
        md = format_markdown(rows)
        assert "| Stage | Baseline (ms) | Current (ms) | Delta | Drift |" in md
        assert "| parse | 1234 | 1289 | +4.5% | - |" in md
        assert "| placement | 45000 | 45200 | +0.4% | +4 drc |" in md

    def test_new_stage_markdown(self):
        rows = [
            {
                "stage": "fanout",
                "status": "new",
                "baseline_ms": None,
                "current_ms": 500,
                "delta_pct": None,
                "drc_delta": None,
            },
        ]
        md = format_markdown(rows)
        assert "**fanout** (new)" in md
        assert "| **fanout** (new) | - | 500 | N/A | - |" in md

    def test_removed_stage_markdown(self):
        rows = [
            {
                "stage": "routing",
                "status": "removed",
                "baseline_ms": 30000,
                "current_ms": None,
                "delta_pct": None,
                "drc_delta": None,
            },
        ]
        md = format_markdown(rows)
        assert "~~routing~~ (removed)" in md
        assert "| ~~routing~~ (removed) | 30000 | - | N/A | - |" in md

    def test_negative_delta_markdown(self):
        rows = [
            {
                "stage": "routing",
                "status": "ok",
                "baseline_ms": 5000,
                "current_ms": 4500,
                "delta_pct": -10.0,
                "drc_delta": None,
            },
        ]
        md = format_markdown(rows)
        assert "| routing | 5000 | 4500 | -10.0% | - |" in md

    def test_negative_drc_delta_markdown(self):
        rows = [
            {
                "stage": "routing",
                "status": "ok",
                "baseline_ms": 5000,
                "current_ms": 5000,
                "delta_pct": 0.0,
                "drc_delta": -3,
            },
        ]
        md = format_markdown(rows)
        assert "| routing | 5000 | 5000 | +0.0% | -3 drc |" in md

    def test_nil_delta_markdown(self):
        rows = [
            {
                "stage": "parse",
                "status": "ok",
                "baseline_ms": 0,
                "current_ms": 500,
                "delta_pct": None,
                "drc_delta": None,
            },
        ]
        md = format_markdown(rows)
        assert "| parse | 0 | 500 | N/A | - |" in md


class TestCliIntegration:
    def test_basic_cli(self, tmp_path):
        baseline = [_record("parse", 1000), _record("placement", 50000)]
        current = [_record("parse", 1050), _record("placement", 51000)]
        b_path = _write_jsonl(tmp_path, "baseline.jsonl", baseline)
        c_path = _write_jsonl(tmp_path, "current.jsonl", current)

        import subprocess

        result = subprocess.run(
            [
                sys.executable,
                str(Path(__file__).resolve().parents[1] / "pr_scorecard.py"),
                "--baseline",
                str(b_path),
                "--current",
                str(c_path),
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "## Pipeline Scorecard" in result.stdout
        assert "| Stage | Baseline (ms) | Current (ms) | Delta | Drift |" in result.stdout
        assert "| parse | 1000 | 1050 | +5.0% | - |" in result.stdout
        assert "| placement | 50000 | 51000 | +2.0% | - |" in result.stdout

    def test_json_output(self, tmp_path):
        baseline = [_record("parse", 1000)]
        current = [_record("parse", 1050)]
        b_path = _write_jsonl(tmp_path, "baseline.jsonl", baseline)
        c_path = _write_jsonl(tmp_path, "current.jsonl", current)

        import subprocess

        result = subprocess.run(
            [
                sys.executable,
                str(Path(__file__).resolve().parents[1] / "pr_scorecard.py"),
                "--baseline",
                str(b_path),
                "--current",
                str(c_path),
                "--json",
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        parsed = json.loads(result.stdout)
        assert isinstance(parsed, list)
        assert parsed[0]["stage"] == "parse"
        assert parsed[0]["delta_pct"] == 5.0
