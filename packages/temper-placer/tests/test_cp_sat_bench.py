"""TDD tests for CP-SAT benchmark runner."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from pathlib import Path

# `benchmarks/` lives at the repo root, which is not on sys.path when running
# from packages/temper-placer. A plain `from benchmarks.cp_sat_bench import ...`
# cannot resolve even after adding the repo root to sys.path: the repo-root
# `benchmarks/` is a *namespace* package (no __init__.py), while the local
# `packages/temper-placer/benchmarks/` is a regular package that shadows it on
# sys.path. Load the module by absolute file path instead. (cp_sat_bench.py
# itself re-adds temper-placer's src/ and the repo root to sys.path.)
_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_BENCH_SRC = _REPO_ROOT / "benchmarks" / "cp_sat_bench.py"
_BENCH_SPEC = importlib.util.spec_from_file_location("cp_sat_bench", _BENCH_SRC)
assert _BENCH_SPEC is not None and _BENCH_SPEC.loader is not None
_BENCH_MODULE = importlib.util.module_from_spec(_BENCH_SPEC)
# Register in sys.modules before exec: the module's dataclasses resolve their
# __module__ against sys.modules during class creation.
sys.modules["cp_sat_bench"] = _BENCH_MODULE
_BENCH_SPEC.loader.exec_module(_BENCH_MODULE)
BenchmarkRunner = _BENCH_MODULE.BenchmarkRunner
compare_baseline = _BENCH_MODULE.compare_baseline

# Repo-root `benchmarks/` directory (test file is at
# packages/temper-placer/tests/test_cp_sat_bench.py -> parents[3]).
_BENCHMARKS_DIR = _REPO_ROOT / "benchmarks"

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
        d = _BENCHMARKS_DIR / "scenarios"
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
        d = _BENCHMARKS_DIR / "scenarios"
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
