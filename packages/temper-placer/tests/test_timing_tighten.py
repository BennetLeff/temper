"""Tests for auto-baseline tightening — detection logic (U1) and CLI (U2)."""

import json
import statistics
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml
from click.testing import CliRunner

from temper_placer.cli.timing import timing
from temper_placer.profiling.timing_gate import (
    TightenResult,
    _extract_wall_ms,
    detect_tightenable_stages,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_timing_record(
    board="temper_placed",
    stage="clearance_grid",
    wall_ms=40.0,
    timestamp="2026-06-28T12:00:00Z",
) -> dict:
    return {
        "schema_version": 2,
        "timestamp": timestamp,
        "git_commit": "abc123",
        "board": board,
        "stage": stage,
        "module": "pipeline-timing",
        "metrics": {"current_ms": wall_ms, "baseline_ms": 100.0, "delta_ms": -60.0, "delta_pct": -60.0, "threshold_ms": 120.0, "passed": 1.0},
        "stage_name": stage,
    }


def _make_wall_ms_record(
    board="temper_placed",
    stage="clearance_grid",
    wall_ms=40.0,
    timestamp="2026-06-28T12:00:00Z",
) -> dict:
    return {
        "schema_version": 2,
        "timestamp": timestamp,
        "git_commit": "abc123",
        "board": board,
        "stage": stage,
        "module": "pipeline-timing",
        "metrics": {"wall_ms_mean": wall_ms, "n_runs": 3, "wall_ms_min": wall_ms - 1, "wall_ms_max": wall_ms + 1},
        "stage_name": stage,
    }


def _jsonl_text(*records: dict) -> str:
    return "\n".join(json.dumps(r) for r in records) + "\n"


def _tmp_jsonl(tmp_path: Path, *records: dict) -> Path:
    path = tmp_path / "pipeline_metrics.jsonl"
    path.write_text(_jsonl_text(*records))
    return path


def _tmp_manifest(tmp_path: Path, stages: list[dict]) -> Path:
    path = tmp_path / "timing_baselines.yaml"
    path.write_text(yaml.safe_dump({"format_version": 1, "stages": stages}))
    return path


def _load_manifest_dict(path: Path) -> dict:
    with open(path) as f:
        return yaml.safe_load(f) or {}


def _manifest_entry(
    board="temper_placed",
    stage="clearance_grid",
    wall_ms_mean=100.0,
) -> dict:
    return {
        "board": board,
        "pipeline": "DeterministicPipeline",
        "stage": stage,
        "wall_ms_mean": wall_ms_mean,
        "wall_ms_p95": 120.0,
        "n_runs": 3,
        "individual_ms": [100.0, 100.0, 100.0],
        "git_hash": "abc123",
        "captured_at": "2026-06-01T00:00:00Z",
    }


# ---------------------------------------------------------------------------
# Tests: _extract_wall_ms
# ---------------------------------------------------------------------------

class TestExtractWallMs:
    def test_wall_ms_mean_present(self):
        rec = {"metrics": {"wall_ms_mean": 42.0}}
        assert _extract_wall_ms(rec) == 42.0

    def test_current_ms_fallback(self):
        rec = {"metrics": {"current_ms": 37.5}}
        assert _extract_wall_ms(rec) == 37.5

    def test_wall_ms_mean_preferred_over_current_ms(self):
        rec = {"metrics": {"wall_ms_mean": 42.0, "current_ms": 37.5}}
        assert _extract_wall_ms(rec) == 42.0

    def test_no_matching_field(self):
        rec = {"metrics": {"other": 10.0}}
        assert _extract_wall_ms(rec) is None

    def test_empty_metrics(self):
        rec = {"metrics": {}}
        assert _extract_wall_ms(rec) is None

    def test_missing_metrics_key(self):
        rec = {}
        assert _extract_wall_ms(rec) is None


# ---------------------------------------------------------------------------
# Tests: detect_tightenable_stages
# ---------------------------------------------------------------------------

class TestDetectTightenableStages:
    def test_no_jsonl_file(self, tmp_path: Path):
        manifest = _load_manifest_dict(_tmp_manifest(tmp_path, [_manifest_entry()]))
        jsonl = tmp_path / "nonexistent.jsonl"
        results = detect_tightenable_stages(jsonl, manifest)
        assert results == []

    def test_no_pipeline_timing_records(self, tmp_path: Path):
        manifest = _load_manifest_dict(_tmp_manifest(tmp_path, [_manifest_entry()]))
        rec = {
            "schema_version": 2,
            "board": "temper_placed",
            "stage": "clearance_grid",
            "module": "pipeline",
            "metrics": {},
        }
        jsonl = _tmp_jsonl(tmp_path, rec)
        results = detect_tightenable_stages(jsonl, manifest)
        assert results == []

    def test_insufficient_runs(self, tmp_path: Path):
        manifest = _load_manifest_dict(_tmp_manifest(tmp_path, [_manifest_entry()]))
        runs = [_make_timing_record(wall_ms=40.0, timestamp=f"2026-06-{28-i:02d}T12:00:00Z") for i in range(4)]
        jsonl = _tmp_jsonl(tmp_path, *runs)
        results = detect_tightenable_stages(jsonl, manifest, n_runs=7)
        assert results == []

    def test_exact_n_runs_all_below(self, tmp_path: Path):
        manifest = _load_manifest_dict(_tmp_manifest(tmp_path, [_manifest_entry()]))
        runs = [_make_timing_record(wall_ms=40.0, timestamp=f"2026-06-{28-i:02d}T12:00:00Z") for i in range(7)]
        jsonl = _tmp_jsonl(tmp_path, *runs)
        results = detect_tightenable_stages(jsonl, manifest, n_runs=7)
        assert len(results) == 1
        assert results[0].board == "temper_placed"
        assert results[0].stage == "clearance_grid"
        assert results[0].proposed_ms == 40.0
        assert results[0].streak_count == 7
        assert results[0].drop_pct == 60.0

    def test_more_than_n_runs_all_below(self, tmp_path: Path):
        manifest = _load_manifest_dict(_tmp_manifest(tmp_path, [_manifest_entry()]))
        runs = [_make_timing_record(wall_ms=30.0 + i, timestamp=f"2026-07-{i:02d}T12:00:00Z") for i in range(10)]
        jsonl = _tmp_jsonl(tmp_path, *runs)
        results = detect_tightenable_stages(jsonl, manifest, n_runs=7)

        # Should use most recent N (the last 7 in timestamp order)
        assert len(results) == 1
        # Most recent N are the last 7 (timestamps 07-03 through 07-09),
        # values: 33,34,35,36,37,38,39 — median = 36
        assert results[0].proposed_ms == 36.0
        assert results[0].streak_count == 10  # all 10 are qualifying
        assert len(results[0].qualifying_runs) == 7

    def test_streak_broken(self, tmp_path: Path):
        manifest = _load_manifest_dict(_tmp_manifest(tmp_path, [_manifest_entry()]))
        runs = [
            *_make_records(8, 40.0, day_start=1),         # 8 qualifying, old
            _make_timing_record(wall_ms=90.0, timestamp="2026-07-25T12:00:00Z"),  # most recent, above threshold
        ]
        jsonl = _tmp_jsonl(tmp_path, *runs)
        results = detect_tightenable_stages(jsonl, manifest, n_runs=7)
        # Most recent record is above threshold → streak from top is 0
        assert results == []

    def test_threshold_boundary(self, tmp_path: Path):
        # wall_ms == baseline * threshold → qualifies
        manifest = _load_manifest_dict(_tmp_manifest(tmp_path, [_manifest_entry(wall_ms_mean=100.0)]))
        runs = [_make_timing_record(wall_ms=50.0, timestamp=f"2026-07-{i:02d}T12:00:00Z") for i in range(7)]
        jsonl = _tmp_jsonl(tmp_path, *runs)
        results = detect_tightenable_stages(jsonl, manifest, n_runs=7, threshold=0.50)
        assert len(results) == 1

    def test_threshold_boundary_above(self, tmp_path: Path):
        # wall_ms == baseline * 0.501 → does not qualify
        manifest = _load_manifest_dict(_tmp_manifest(tmp_path, [_manifest_entry(wall_ms_mean=100.0)]))
        runs = [_make_timing_record(wall_ms=50.1, timestamp=f"2026-07-{i:02d}T12:00:00Z") for i in range(7)]
        jsonl = _tmp_jsonl(tmp_path, *runs)
        results = detect_tightenable_stages(jsonl, manifest, n_runs=7, threshold=0.50)
        assert results == []

    def test_noise_floor(self, tmp_path: Path):
        manifest = _load_manifest_dict(_tmp_manifest(tmp_path, [_manifest_entry(wall_ms_mean=5.0)]))
        runs = [_make_timing_record(wall_ms=1.0, timestamp=f"2026-07-{i:02d}T12:00:00Z") for i in range(7)]
        jsonl = _tmp_jsonl(tmp_path, *runs)
        results = detect_tightenable_stages(jsonl, manifest, n_runs=7, noise_floor=10.0)
        assert results == []

    def test_median_odd_count(self, tmp_path: Path):
        manifest = _load_manifest_dict(_tmp_manifest(tmp_path, [_manifest_entry()]))
        # 7 values: 30, 35, 38, 40, 42, 45, 50 → median = 40
        values = [30.0, 35.0, 38.0, 40.0, 42.0, 45.0, 50.0]
        runs = [_make_timing_record(wall_ms=v, timestamp=f"2026-07-{i:02d}T12:00:00Z") for i, v in enumerate(values)]
        jsonl = _tmp_jsonl(tmp_path, *runs)
        results = detect_tightenable_stages(jsonl, manifest, n_runs=7)
        assert results[0].proposed_ms == 40.0

    def test_median_even_count(self, tmp_path: Path):
        manifest = _load_manifest_dict(_tmp_manifest(tmp_path, [_manifest_entry(wall_ms_mean=100.0)]))
        # 8 values, all below 50ms threshold: median = (40+42)/2 = 41
        values = [30.0, 35.0, 38.0, 40.0, 42.0, 45.0, 48.0, 49.0]
        runs = [_make_timing_record(wall_ms=v, timestamp=f"2026-07-{i:02d}T12:00:00Z") for i, v in enumerate(values)]
        jsonl = _tmp_jsonl(tmp_path, *runs)
        results = detect_tightenable_stages(jsonl, manifest, n_runs=8)
        assert results[0].proposed_ms == 41.0

    def test_multiple_stages_mixed(self, tmp_path: Path):
        manifest = _load_manifest_dict(
            _tmp_manifest(
                tmp_path,
                [
                    _manifest_entry(stage="clearance_grid", wall_ms_mean=100.0),
                    _manifest_entry(stage="zone_geometry", wall_ms_mean=50.0),
                    _manifest_entry(stage="slot_generation", wall_ms_mean=20.0),
                ],
            )
        )
        runs_cg = [_make_timing_record(stage="clearance_grid", wall_ms=40.0, timestamp=f"2026-07-{i:02d}T12:00:00Z") for i in range(7)]
        runs_zg = [_make_timing_record(stage="zone_geometry", wall_ms=10.0, timestamp=f"2026-07-{i:02d}T12:00:00Z") for i in range(7)]
        # slot_generation: only 5 runs below, 2 above → not eligible
        runs_sg = [
            *_make_records(5, 5.0, day_start=1, stage="slot_generation"),
            _make_timing_record(stage="slot_generation", wall_ms=25.0, timestamp="2026-07-06T12:00:00Z"),
            _make_timing_record(stage="slot_generation", wall_ms=25.0, timestamp="2026-07-07T12:00:00Z"),
        ]
        jsonl = _tmp_jsonl(tmp_path, *runs_cg, *runs_zg, *runs_sg)
        results = detect_tightenable_stages(jsonl, manifest, n_runs=7)
        assert len(results) == 2
        stages = {r.stage for r in results}
        assert stages == {"clearance_grid", "zone_geometry"}

    def test_board_filter(self, tmp_path: Path):
        manifest = _load_manifest_dict(
            _tmp_manifest(
                tmp_path,
                [
                    _manifest_entry(board="temper_placed", wall_ms_mean=100.0),
                    _manifest_entry(board="other_board", wall_ms_mean=100.0),
                ],
            )
        )
        runs_tp = [_make_timing_record(board="temper_placed", wall_ms=40.0, timestamp=f"2026-07-{i:02d}T12:00:00Z") for i in range(7)]
        runs_ob = [_make_timing_record(board="other_board", wall_ms=40.0, timestamp=f"2026-07-{i:02d}T12:00:00Z") for i in range(7)]
        jsonl = _tmp_jsonl(tmp_path, *runs_tp, *runs_ob)
        results = detect_tightenable_stages(jsonl, manifest, n_runs=7, board_filter="temper_placed")
        assert len(results) == 1
        assert results[0].board == "temper_placed"

    def test_stage_filter(self, tmp_path: Path):
        manifest = _load_manifest_dict(
            _tmp_manifest(
                tmp_path,
                [
                    _manifest_entry(stage="clearance_grid", wall_ms_mean=100.0),
                    _manifest_entry(stage="zone_geometry", wall_ms_mean=40.0),
                ],
            )
        )
        runs_cg = [_make_timing_record(stage="clearance_grid", wall_ms=40.0, timestamp=f"2026-07-{i:02d}T12:00:00Z") for i in range(7)]
        runs_zg = [_make_timing_record(stage="zone_geometry", wall_ms=10.0, timestamp=f"2026-07-{i:02d}T12:00:00Z") for i in range(7)]
        jsonl = _tmp_jsonl(tmp_path, *runs_cg, *runs_zg)
        results = detect_tightenable_stages(jsonl, manifest, n_runs=7, stage_filter="clearance_grid")
        assert len(results) == 1
        assert results[0].stage == "clearance_grid"

    def test_missing_wall_ms(self, tmp_path: Path):
        manifest = _load_manifest_dict(_tmp_manifest(tmp_path, [_manifest_entry()]))
        runs = [
            _make_timing_record(wall_ms=40.0, timestamp="2026-07-01T12:00:00Z"),
            # record missing metrics entirely
            {"schema_version": 2, "board": "temper_placed", "stage": "clearance_grid", "module": "pipeline-timing", "metrics": {}},
            _make_timing_record(wall_ms=40.0, timestamp="2026-07-02T12:00:00Z"),
            _make_timing_record(wall_ms=40.0, timestamp="2026-07-03T12:00:00Z"),
            _make_timing_record(wall_ms=40.0, timestamp="2026-07-04T12:00:00Z"),
            _make_timing_record(wall_ms=40.0, timestamp="2026-07-05T12:00:00Z"),
            _make_timing_record(wall_ms=40.0, timestamp="2026-07-06T12:00:00Z"),
            _make_timing_record(wall_ms=40.0, timestamp="2026-07-07T12:00:00Z"),
        ]
        jsonl = _tmp_jsonl(tmp_path, *runs)
        results = detect_tightenable_stages(jsonl, manifest, n_runs=7)
        # The record with no wall_ms is skipped, streak continues
        assert len(results) == 1
        assert results[0].streak_count == 7

    def test_wall_ms_mean_records_used(self, tmp_path: Path):
        manifest = _load_manifest_dict(_tmp_manifest(tmp_path, [_manifest_entry()]))
        runs = [_make_wall_ms_record(wall_ms=40.0, timestamp=f"2026-07-{i:02d}T12:00:00Z") for i in range(7)]
        jsonl = _tmp_jsonl(tmp_path, *runs)
        results = detect_tightenable_stages(jsonl, manifest, n_runs=7)
        assert len(results) == 1
        assert results[0].proposed_ms == 40.0

    def test_results_sorted_by_drop_pct_descending(self, tmp_path: Path):
        manifest = _load_manifest_dict(
            _tmp_manifest(
                tmp_path,
                [
                    _manifest_entry(stage="small_drop", wall_ms_mean=50.0),
                    _manifest_entry(stage="big_drop", wall_ms_mean=500.0),
                ],
            )
        )
        runs_sd = [_make_timing_record(stage="small_drop", wall_ms=25.0, timestamp=f"2026-07-{i:02d}T12:00:00Z") for i in range(7)]
        runs_bd = [_make_timing_record(stage="big_drop", wall_ms=100.0, timestamp=f"2026-07-{i:02d}T12:00:00Z") for i in range(7)]
        jsonl = _tmp_jsonl(tmp_path, *runs_sd, *runs_bd)
        results = detect_tightenable_stages(jsonl, manifest, n_runs=7)
        assert len(results) == 2
        # big_drop: 80% drop should come first
        assert results[0].stage == "big_drop"
        assert results[1].stage == "small_drop"
        assert results[0].drop_pct > results[1].drop_pct


# ---------------------------------------------------------------------------
# Helpers for CLI tests
# ---------------------------------------------------------------------------

def _make_records(n, wall_ms, day_start=1, stage="clearance_grid", board="temper_placed"):
    """Generate N timing records with consecutive daily timestamps."""
    return [
        _make_timing_record(board=board, stage=stage, wall_ms=wall_ms,
                           timestamp=f"2026-07-{day_start + i:02d}T12:00:00Z")
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# CLI Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def tmp_repo(tmp_path, monkeypatch):
    """Set up a temp repo root with timing_baselines.yaml and metrics/ dir."""
    import sys

    timing_mod = sys.modules["temper_placer.cli.timing"]

    datadir = tmp_path / "power_pcb_dataset" / "metrics"
    datadir.mkdir(parents=True, exist_ok=True)

    yaml_path = tmp_path / "power_pcb_dataset" / "timing_baselines.yaml"
    monkeypatch.setattr(timing_mod, "_timing_baselines_path", lambda: yaml_path)
    monkeypatch.setattr(timing_mod, "_repo_root", lambda: tmp_path)

    jsonl_path = tmp_path / "power_pcb_dataset" / "metrics" / "pipeline_metrics.jsonl"

    return {"tmp_path": tmp_path, "yaml_path": yaml_path, "jsonl_path": jsonl_path}


def _write_manifest(path: Path, stages: list[dict]):
    path.write_text(yaml.safe_dump({"format_version": 1, "stages": stages}))


def _write_jsonl(path: Path, *records: dict):
    path.write_text(_jsonl_text(*records))


# ---------------------------------------------------------------------------
# Tests: CLI
# ---------------------------------------------------------------------------

class TestTightenCLI:
    def test_help(self, runner):
        result = runner.invoke(timing, ["tighten", "--help"])
        assert result.exit_code == 0
        assert "--dry-run" in result.output
        assert "--n-runs" in result.output
        assert "--threshold" in result.output
        assert "--ci" in result.output

    def test_no_manifest(self, runner, tmp_repo):
        result = runner.invoke(timing, ["tighten", "--dry-run"])
        assert result.exit_code == 0
        assert "No timing baselines" in result.output

    def test_no_jsonl_file(self, runner, tmp_repo):
        _write_manifest(tmp_repo["yaml_path"], [_manifest_entry()])
        jsonl = tmp_repo["jsonl_path"]
        if jsonl.exists():
            jsonl.unlink()
        result = runner.invoke(timing, ["tighten", "--dry-run"])
        assert result.exit_code == 0
        assert "No metrics data to analyze" in result.output

    def test_dry_run_prints_table_no_changes(self, runner, tmp_repo):
        _write_manifest(tmp_repo["yaml_path"], [_manifest_entry()])
        runs = _make_records(10, 40.0)
        _write_jsonl(tmp_repo["jsonl_path"], *runs)

        result = runner.invoke(timing, ["tighten", "--dry-run", "--n-runs", "7"])

        assert result.exit_code == 0
        assert "Eligible stages" in result.output
        assert "clearance_grid" in result.output
        assert "100.0 ms" in result.output  # baseline
        assert "40.0 ms" in result.output   # proposed
        assert "Dry run" in result.output
        # Manifest unchanged
        content = yaml.safe_load(tmp_repo["yaml_path"].read_text())
        assert content["stages"][0]["wall_ms_mean"] == 100.0

    def test_dry_run_stage_filter(self, runner, tmp_repo):
        _write_manifest(tmp_repo["yaml_path"], [
            _manifest_entry(stage="clearance_grid", wall_ms_mean=100.0),
            _manifest_entry(stage="zone_geometry", wall_ms_mean=50.0),
        ])
        runs_cg = _make_records(7, 40.0, stage="clearance_grid")
        runs_zg = _make_records(7, 10.0, stage="zone_geometry")
        _write_jsonl(tmp_repo["jsonl_path"], *runs_cg, *runs_zg)

        result = runner.invoke(
            timing, ["tighten", "--dry-run", "--stage", "clearance_grid", "--n-runs", "7"]
        )
        assert result.exit_code == 0
        assert "clearance_grid" in result.output
        assert "zone_geometry" not in result.output

    def test_no_eligible_stages(self, runner, tmp_repo):
        _write_manifest(tmp_repo["yaml_path"], [_manifest_entry()])
        runs = _make_records(5, 40.0)  # 5 < 7
        _write_jsonl(tmp_repo["jsonl_path"], *runs)

        result = runner.invoke(timing, ["tighten", "--dry-run", "--n-runs", "7"])
        assert result.exit_code == 0
        assert "No stages eligible for tightening" in result.output

    def test_non_dry_prompts_confirmation(self, runner, tmp_repo):
        _write_manifest(tmp_repo["yaml_path"], [_manifest_entry()])
        runs = _make_records(10, 40.0)
        _write_jsonl(tmp_repo["jsonl_path"], *runs)

        result = runner.invoke(
            timing, ["tighten", "--n-runs", "7"], input="n\n"
        )
        assert result.exit_code == 0
        assert "Aborted" in result.output
        # Manifest unchanged
        content = yaml.safe_load(tmp_repo["yaml_path"].read_text())
        assert content["stages"][0]["wall_ms_mean"] == 100.0

    def test_apply_changes(self, runner, tmp_repo):
        _write_manifest(tmp_repo["yaml_path"], [_manifest_entry()])
        runs = _make_records(10, 40.0)
        _write_jsonl(tmp_repo["jsonl_path"], *runs)

        result = runner.invoke(
            timing, ["tighten", "--n-runs", "7"], input="y\n"
        )
        assert result.exit_code == 0
        assert "Tightening" in result.output
        assert "clearance_grid" in result.output

        content = yaml.safe_load(tmp_repo["yaml_path"].read_text())
        entry = content["stages"][0]
        assert entry["wall_ms_mean"] == 40.0
        assert "tightened_from_ms" in entry
        assert entry["tightened_from_ms"] == 100.0
        assert "tightened_at" in entry
        assert "tightened_n_runs" in entry
        assert "tightened_trigger_pct" in entry
        assert "wall_ms_p95" in entry

    def test_provenance_fields_written(self, runner, tmp_repo):
        _write_manifest(tmp_repo["yaml_path"], [_manifest_entry(wall_ms_mean=100.0)])
        runs = _make_records(8, 40.0)
        _write_jsonl(tmp_repo["jsonl_path"], *runs)

        result = runner.invoke(
            timing, ["tighten", "--n-runs", "7", "--threshold", "0.50"], input="y\n"
        )
        assert result.exit_code == 0

        content = yaml.safe_load(tmp_repo["yaml_path"].read_text())
        entry = content["stages"][0]
        assert entry["tightened_from_ms"] == 100.0
        assert entry["tightened_n_runs"] == 7
        assert entry["tightened_trigger_pct"] == 0.50
        assert "tightened_at" in entry

    def test_ci_mode_no_prompt(self, runner, tmp_repo):
        _write_manifest(tmp_repo["yaml_path"], [_manifest_entry()])
        runs = _make_records(10, 40.0)
        _write_jsonl(tmp_repo["jsonl_path"], *runs)

        result = runner.invoke(timing, ["tighten", "--ci", "--n-runs", "7"])
        assert result.exit_code == 0
        assert "Tightening" in result.output

        content = yaml.safe_load(tmp_repo["yaml_path"].read_text())
        assert content["stages"][0]["wall_ms_mean"] == 40.0

    def test_multiple_stages_updated(self, runner, tmp_repo):
        _write_manifest(tmp_repo["yaml_path"], [
            _manifest_entry(stage="clearance_grid", wall_ms_mean=100.0),
            _manifest_entry(stage="zone_geometry", wall_ms_mean=40.0),
        ])
        runs_cg = _make_records(7, 40.0, stage="clearance_grid")
        runs_zg = _make_records(7, 15.0, stage="zone_geometry")
        _write_jsonl(tmp_repo["jsonl_path"], *runs_cg, *runs_zg)

        result = runner.invoke(
            timing, ["tighten", "--n-runs", "7"], input="y\n"
        )
        assert result.exit_code == 0
        assert "Tightening 2 stage" in result.output

        content = yaml.safe_load(tmp_repo["yaml_path"].read_text())
        by_stage = {e["stage"]: e["wall_ms_mean"] for e in content["stages"]}
        assert by_stage["clearance_grid"] == 40.0
        assert by_stage["zone_geometry"] == 15.0

    def test_untightened_stages_unchanged(self, runner, tmp_repo):
        _write_manifest(tmp_repo["yaml_path"], [
            _manifest_entry(stage="clearance_grid", wall_ms_mean=100.0),
            _manifest_entry(stage="sequential_routing", wall_ms_mean=2800.0),
        ])
        # Only clearance_grid qualifies
        runs = _make_records(10, 40.0, stage="clearance_grid")
        _write_jsonl(tmp_repo["jsonl_path"], *runs)

        result = runner.invoke(
            timing, ["tighten", "--n-runs", "7"], input="y\n"
        )
        assert result.exit_code == 0

        content = yaml.safe_load(tmp_repo["yaml_path"].read_text())
        by_stage = {e["stage"]: e["wall_ms_mean"] for e in content["stages"]}
        assert by_stage["clearance_grid"] == 40.0
        assert by_stage["sequential_routing"] == 2800.0  # unchanged

    def test_custom_n_runs_and_threshold(self, runner, tmp_repo):
        _write_manifest(tmp_repo["yaml_path"], [_manifest_entry(wall_ms_mean=100.0)])
        # Only 5 runs below 60% threshold, not enough for default N=7
        runs = _make_records(5, 60.0)
        _write_jsonl(tmp_repo["jsonl_path"], *runs)

        result = runner.invoke(
            timing, ["tighten", "--dry-run", "--n-runs", "5", "--threshold", "0.60"]
        )
        assert result.exit_code == 0
        assert "clearance_grid" in result.output

    def test_baselines_written_message(self, runner, tmp_repo):
        _write_manifest(tmp_repo["yaml_path"], [_manifest_entry()])
        runs = _make_records(7, 40.0)
        _write_jsonl(tmp_repo["jsonl_path"], *runs)

        result = runner.invoke(
            timing, ["tighten", "--n-runs", "7"], input="y\n"
        )
        assert result.exit_code == 0
        assert "Baselines written to power_pcb_dataset/timing_baselines.yaml" in result.output

    def test_manifest_preserves_format_version(self, runner, tmp_repo):
        _write_manifest(tmp_repo["yaml_path"], [_manifest_entry()])
        runs = _make_records(7, 40.0)
        _write_jsonl(tmp_repo["jsonl_path"], *runs)

        result = runner.invoke(
            timing, ["tighten", "--n-runs", "7"], input="y\n"
        )
        assert result.exit_code == 0

        content = yaml.safe_load(tmp_repo["yaml_path"].read_text())
        assert content["format_version"] == 1
