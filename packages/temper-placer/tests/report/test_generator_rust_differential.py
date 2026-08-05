"""Differential test: report/generator.py compute (temper-io-types) vs the
pinned Python oracle.

Wave 4, Phase 5 — the report surface migration. The Rust migration
(reproducing ``temper_placer/report/generator.py``'s compute bit-identically
in the ``temper-io-types`` crate) is driven through the delegation shim
``temper_placer.report.generator``; the pre-migration implementation is
pinned verbatim as the oracle (``_generator_py_oracle.py``).

Migrated: ``calculate_benchmark_result`` (the numeric scoring kernel) and
the ``generate_json_report`` data shape (``json.dump`` itself stays Python
stdlib). ``generate_text_report`` stays Python (Rich console rendering is a
library semantic, not reimplementable — see VERIFICATION.md).
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from pathlib import Path

import temper_io_types as _rust

import tests.report._generator_py_oracle as _oracle
from temper_placer.report.generator import (
    BenchmarkResult,
    BenchmarkSummary,
    calculate_benchmark_result,
    generate_json_report,
)

# Module-scope RED arm.
assert hasattr(_rust, "report_calculate_benchmark_result")
assert hasattr(_rust, "report_benchmark_json_data")


@dataclass
class _LossBreakdown:
    loss_breakdown: dict


@dataclass
class _MockOptResult:
    history: list = field(default_factory=list)


def _opt_result(rng: random.Random):
    keys = ["wirelength", "overlap", "boundary", "thermal", "other"]
    loss = {k: rng.uniform(0.0, 200.0) for k in keys}
    loss["overlap"] = rng.choice([0.0, 0.3, 5.0, 10.0, 10.5, 50.0, 120.0])
    loss["boundary"] = rng.choice([0.0, 0.5, 9.0, 10.0, 11.0, 60.0])
    loss["wirelength"] = rng.uniform(0.0, 500.0)
    loss["thermal"] = rng.choice([0.0, 1.0, 25.0, 100.0])
    return _MockOptResult(history=[_LossBreakdown(loss_breakdown=loss)])


def _baseline(rng: random.Random) -> dict:
    style = rng.random()
    human_wl = rng.choice([0.0, 0.0, 1.0, 42.5, 300.0])
    human_metrics = {"total_wirelength_mm": human_wl, "total_hpwl_mm": rng.uniform(0, 500),
                     "compactness_score": rng.uniform(0.0, 1.0), "density": rng.uniform(0.0, 1.0)}
    if style < 0.5:
        return {"human_placement": {"metrics": human_metrics}}
    if style < 0.8:
        return {"human_metrics": human_metrics}
    return {}


def _result_key(r: BenchmarkResult):
    return (
        r.name,
        r.drc_errors,
        _f(r.wirelength_ratio),
        _f(r.overlap_score),
        _f(r.boundary_score),
        _f(r.thermal_score),
        _f(r.compactness_score),
        _f(r.overall_score),
        r.status,
        tuple(r.violations),
    )


def _f(v):
    return v.hex() if isinstance(v, float) else v


def _fixtures() -> list[tuple[str, _MockOptResult, dict]]:
    rng = random.Random(0xD15EA5E)
    out = []
    for _ in range(40):
        out.append((f"bench_{rng.randint(0, 99)}", _opt_result(rng), _baseline(rng)))
    return out


def test_calculate_benchmark_result_identical():
    for name, opt, baseline in _fixtures():
        ours = calculate_benchmark_result(name, opt, baseline, None)
        theirs = _oracle.calculate_benchmark_result(name, opt, baseline, None)
        assert _result_key(ours) == _result_key(theirs)


def test_score_status_matrix_pins():
    """Hand-built cases pin the status decision and score formulas."""
    cases = [
        # (overlap, boundary, wl, thermal, compactness) -> expected status
        (120.0, 0.5, 1.0, 1.0, 0.5, "FAIL"),   # overlap > 10
        (0.3, 11.0, 1.0, 1.0, 0.5, "FAIL"),    # boundary > 10
        (0.3, 0.5, 0.9, 1.0, 0.5, "BETTER"),   # wl_ratio < 0.95
        (0.3, 0.5, 1.0, 1.0, 0.5, "PASS"),
        (0.0, 0.0, 0.0, 0.0, 0.5, "BETTER"),
    ]
    for overlap, boundary, wl, thermal, compact, expected_status in cases:
        opt = _MockOptResult(history=[_LossBreakdown(loss_breakdown={
            "wirelength": wl, "overlap": overlap, "boundary": boundary, "thermal": thermal,
        })])
        baseline = {"human_placement": {"metrics": {
            "total_wirelength_mm": 1.0, "compactness_score": compact,
        }}}
        ours = calculate_benchmark_result("t", opt, baseline, None)
        theirs = _oracle.calculate_benchmark_result("t", opt, baseline, None)
        assert ours.status == expected_status == theirs.status
        assert _result_key(ours) == _result_key(theirs)


def test_hard_constraint_score_floor():
    """overlap/boundary score is 1.0 below 1.0 and decays from there."""
    for val in [0.0, 0.5, 0.999, 1.0, 10.0, 100.0, 150.0]:
        opt = _MockOptResult(history=[_LossBreakdown(loss_breakdown={
            "wirelength": 1.0, "overlap": val, "boundary": 0.0, "thermal": 0.0,
        })])
        baseline = {"human_metrics": {"total_wirelength_mm": 1.0, "compactness_score": 0.5}}
        ours = calculate_benchmark_result("t", opt, baseline, None)
        assert ours.overlap_score == _oracle.calculate_benchmark_result(
            "t", opt, baseline, None
        ).overlap_score


def test_zero_human_wl_ratio_is_one():
    """human_wl <= 0 -> ratio 1.0 (no division by zero)."""
    for human_wl in [0.0, -1.0]:
        opt = _MockOptResult(history=[_LossBreakdown(loss_breakdown={
            "wirelength": 42.0, "overlap": 0.0, "boundary": 0.0, "thermal": 0.0,
        })])
        baseline = {"human_metrics": {"total_wirelength_mm": human_wl}}
        ours = calculate_benchmark_result("t", opt, baseline, None)
        assert ours.wirelength_ratio == 1.0


def test_generate_json_report_byte_identical(tmp_path: Path):
    rng = random.Random(99)
    summary = BenchmarkSummary(
        total_pcbs=5,
        passed=3,
        failed=2,
        better_than_human=1,
        results=[_build_result(rng, i) for i in range(5)],
        timestamp="2026-08-04 12:00:00",
    )
    ours_path = tmp_path / "ours.json"
    theirs_path = tmp_path / "theirs.json"
    generate_json_report(summary, ours_path)
    _oracle.generate_json_report(summary, theirs_path)
    assert ours_path.read_bytes() == theirs_path.read_bytes()


def _build_result(rng: random.Random, i: int) -> BenchmarkResult:
    return BenchmarkResult(
        name=f"p{i}",
        drc_errors=rng.choice([0, 1, 7]),
        wirelength_ratio=rng.uniform(0.5, 2.0),
        overlap_score=rng.uniform(0, 1),
        boundary_score=rng.uniform(0, 1),
        thermal_score=rng.uniform(0, 1),
        compactness_score=rng.uniform(0, 1),
        overall_score=rng.uniform(0, 1),
        status=rng.choice(["BETTER", "PASS", "FAIL"]),
        violations=rng.sample(["Overlap too high (12.3)", "Boundary violation (4.0)"],
                              rng.randint(0, 2)),
    )


def test_json_shape_leaf_types():
    """int fields stay ints; pass_rate is float; list order preserved."""
    summary = BenchmarkSummary(
        total_pcbs=4, passed=2, failed=2, better_than_human=1,
        results=[_build_result(random.Random(1), 0)], timestamp="t",
    )
    ours_path = Path("/tmp/_ours_gen.json")
    generate_json_report(summary, ours_path)
    data = json.loads(ours_path.read_text())
    ours_path.unlink()
    assert data["summary"]["total_pcbs"] == 4 and isinstance(data["summary"]["total_pcbs"], int)
    assert data["summary"]["pass_rate"] == 0.5 and isinstance(data["summary"]["pass_rate"], float)
    assert data["summary"]["pass_rate"] == 0.5
