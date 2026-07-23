"""TDD tests for CP-SAT benchmark runner."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from benchmarks.cp_sat_bench import BenchmarkRunner, compare_baseline

REQUIRED_FIELDS = {
    "scenario",
    "seed",
    "status",
    "solve_time_s",
    "objective_value",
    "n_components",
    "placed_count",
    "rounds",
    "drc_errors",
    "board_width_mm",
    "board_height_mm",
    "timeout_ms",
}


class TestJsonlOutput:
    def test_trivial_scenario_produces_valid_jsonl(self):
        from benchmarks.cp_sat_bench import BenchmarkRunner

        d = Path(__file__).resolve().parent.parent.parent / "benchmarks" / "scenarios"
        with tempfile.TemporaryDirectory() as tmp:
            r = BenchmarkRunner(
                scenarios_dir=d, output_dir=Path(tmp), seeds=[42], scenario_filter="trivial"
            )
            r.run()
            out = Path(tmp) / "cp_sat_metrics.jsonl"
            assert out.exists()
            with open(out) as f:
                recs = [json.loads(line) for line in f if line.strip()]
            assert len(recs) >= 1
            for rec in recs:
                missing = REQUIRED_FIELDS - set(rec.keys())
                assert not missing, f"Missing: {missing}"


class TestWallTime:
    def test_wall_time_non_negative(self):
        d = Path(__file__).resolve().parent.parent.parent / "benchmarks" / "scenarios"
        with tempfile.TemporaryDirectory() as tmp:
            r = BenchmarkRunner(
                scenarios_dir=d, output_dir=Path(tmp), seeds=[42, 123], scenario_filter="trivial"
            )
            r.run()
            with open(Path(tmp) / "cp_sat_metrics.jsonl") as f:
                recs = [json.loads(line) for line in f if line.strip()]
            for rec in recs:
                assert rec["solve_time_s"] >= 0.0


class TestCompareMode:
    def test_compare_detects_regression(self):
        baseline = [
            {
                "scenario": "trivial",
                "seed": 42,
                "status": "optimal",
                "solve_time_s": 0.5,
                "drc_errors": 0,
            }
        ]
        pr_data = [
            {
                "scenario": "trivial",
                "seed": 42,
                "status": "infeasible",
                "solve_time_s": 0.5,
                "drc_errors": 0,
            }
        ]
        with tempfile.TemporaryDirectory() as tmp:
            bp, pp = Path(tmp) / "base.jsonl", Path(tmp) / "pr.jsonl"
            for f, d in [(bp, baseline), (pp, pr_data)]:
                with open(f, "w") as fh:
                    for r in d:
                        fh.write(json.dumps(r) + "\n")
            regs = compare_baseline(pp, bp)
            assert len(regs) > 0

    def test_compare_no_regression_when_improved(self):
        baseline = [
            {
                "scenario": "trivial",
                "seed": 42,
                "status": "optimal",
                "solve_time_s": 0.5,
                "drc_errors": 2,
            }
        ]
        pr_data = [
            {
                "scenario": "trivial",
                "seed": 42,
                "status": "optimal",
                "solve_time_s": 0.3,
                "drc_errors": 0,
            }
        ]
        with tempfile.TemporaryDirectory() as tmp:
            bp, pp = Path(tmp) / "base.jsonl", Path(tmp) / "pr.jsonl"
            for f, d in [(bp, baseline), (pp, pr_data)]:
                with open(f, "w") as fh:
                    for r in d:
                        fh.write(json.dumps(r) + "\n")
            regs = compare_baseline(pp, bp)
            assert len(regs) == 0
