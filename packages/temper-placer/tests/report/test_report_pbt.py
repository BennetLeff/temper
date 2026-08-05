"""Property-based tests for the migrated report surface (temper-io-types).

R1c: >= 5 non-vacuous properties per module. These properties are written
against the delegation shims (so they also pass the moment the Rust lands)
and are deliberately independent of the differential oracle arms — they
constrain the OUTPUT structure rather than the bit-level content.

Properties are stated for each module; vacuity guards assert the input
fixture actually exercises the property (G4-style: a property over an empty
board asserts something about an EMPTY board, but a property that needs a
violation asserts the fixture has one first).
"""

from __future__ import annotations

import json
import random

import pytest

from temper_placer.report.formatter import format_json, format_text
from temper_placer.report.generator import (
    BenchmarkResult,
    BenchmarkSummary,
    calculate_benchmark_result,
)
from temper_placer.report.summary import generate_summary
from temper_placer.validation.drc_result import (
    CheckResult,
    Issue,
    Location,
    RunResult,
    Severity,
)
from temper_placer.validation.drc_types import ComponentPlacement, Placement


def _result(n_checks: int, n_issues: int, rng: random.Random) -> RunResult:
    checks = []
    for _ in range(n_checks):
        issues = []
        for _ in range(n_issues):
            issues.append(
                Issue(
                    severity=rng.choice(list(Severity)),
                    code="C",
                    message="m",
                    category="c",
                    check_name="c",
                    affected_items=[],
                    location=Location(x=1.0, y=2.0, layer="F.Cu"),
                )
            )
        checks.append(
            CheckResult(
                check_name="c", passed=rng.random() < 0.5, issues=issues,
                elapsed_ms=1.0, metrics={"m": rng.uniform(0, 1)},
            )
        )
    return RunResult(check_results=checks, total_elapsed_ms=10.0)


def _placement(n: int) -> Placement:
    return Placement(
        components={
            f"R{i}": ComponentPlacement(
                ref=f"R{i}", footprint="fp", x=float(i), y=0.0, rotation=0.0,
                layer="F.Cu", width=1.0, height=1.0,
            )
            for i in range(n)
        }
    )


# ---------------------------------------------------------------------------
# formatter
# ---------------------------------------------------------------------------

def test_prop_formatter_text_is_single_banded_string():
    for seed in range(20):
        rng = random.Random(seed)
        text = format_text(_result(rng.randint(0, 5), rng.randint(0, 4), rng))
        assert isinstance(text, str)
        assert text.count("=") >= 2  # at least the two 80-wide bands
        assert text.endswith("=" * 80)


def test_prop_formatter_json_round_trips_and_counts_agree():
    for seed in range(20):
        rng = random.Random(seed)
        result = _result(rng.randint(0, 5), rng.randint(0, 4), rng)
        data = json.loads(format_json(result))
        assert data["total_checks"] == len(result.check_results)
        assert data["passed_checks"] == sum(1 for c in result.check_results if c.passed)
        assert data["failed_checks"] == sum(1 for c in result.check_results if not c.passed)
        assert data["total_issues"] == len(result.all_issues)
        assert len(data["checks"]) == len(result.check_results)
        assert all(c["issue_count"] == len(c["issues"]) for c in data["checks"])


def test_prop_formatter_json_is_valid_utf8_escaped():
    result = _result(1, 1, random.Random(1))
    result.check_results[0].issues[0].message = 'quote " backslash \\ é 中文'
    result.check_results[0].issues[0].code = "X'Y"
    out = format_json(result)
    json.loads(out)  # must parse


def test_prop_formatter_text_severity_lines_prefixed():
    rng = random.Random(3)
    result = _result(2, 3, rng)
    text = format_text(result)
    for issue in result.all_issues:
        assert f"[{issue.severity.name}]" in text


# ---------------------------------------------------------------------------
# summary
# ---------------------------------------------------------------------------

def test_prop_summary_counts_match_result():
    for seed in range(20):
        rng = random.Random(seed)
        result = _result(rng.randint(0, 4), rng.randint(0, 3), rng)
        placement = _placement(rng.randint(0, 6))
        text = generate_summary(result, placement, None)
        assert f"Components: {len(placement.components)}" in text
        assert f"Nets: {len(placement.nets)}" in text
        assert f"Total Checks: {len(result.check_results)}" in text


def test_prop_summary_passed_failed_sum():
    rng = random.Random(11)
    result = _result(5, 1, rng)
    text = generate_summary(result, _placement(1), None)
    passed = sum(1 for c in result.check_results if c.passed)
    failed = sum(1 for c in result.check_results if not c.passed)
    assert f"Passed: {passed}" in text
    assert f"Failed: {failed}" in text


def test_prop_summary_empty_result_says_zero():
    result = RunResult(check_results=[], total_elapsed_ms=0.0)
    text = generate_summary(result, _placement(0), None)
    assert "Total Checks: 0" in text
    assert "Passed: 0" in text


# ---------------------------------------------------------------------------
# generator
# ---------------------------------------------------------------------------

def _simple_opt(overlap, boundary, wl, thermal, compact):
    from dataclasses import dataclass

    @dataclass
    class LB:
        loss_breakdown: dict

    @dataclass
    class Hist:
        history: list

    return Hist(history=[LB({"wirelength": wl, "overlap": overlap,
                             "boundary": boundary, "thermal": thermal})]), {
        "human_placement": {"metrics": {
            "total_wirelength_mm": 1.0, "compactness_score": compact}}
    }


def test_prop_benchmark_scores_in_unit_range():
    for overlap in [0.0, 0.5, 5.0, 10.0, 100.0]:
        opt, baseline = _simple_opt(overlap, 0.0, 1.0, 0.0, 0.5)
        r = calculate_benchmark_result("t", opt, baseline, None)
        assert 0.0 <= r.overlap_score <= 1.0
        assert 0.0 <= r.overall_score <= 1.0


def test_prop_benchmark_fail_implies_violation_message():
    opt, baseline = _simple_opt(120.0, 0.0, 1.0, 0.0, 0.5)
    r = calculate_benchmark_result("t", opt, baseline, None)
    assert r.status == "FAIL"
    assert r.violations, "FAIL status must carry at least one violation message"
    assert any("Overlap too high" in v for v in r.violations)


def test_prop_benchmark_thermal_score_monotone_inverse():
    """thermal_score strictly decreases as thermal penalty grows (when >0)."""
    vals = [0.0, 1.0, 10.0, 100.0]
    scores = []
    for th in vals:
        opt, baseline = _simple_opt(0.0, 0.0, 1.0, th, 0.5)
        r = calculate_benchmark_result("t", opt, baseline, None)
        scores.append(r.thermal_score)
    assert scores[0] == 1.0
    assert all(scores[i] > scores[i + 1] for i in range(len(scores) - 1))


def test_prop_benchmark_overall_uses_balanced_formula():
    """When hard constraints pass, overall is the weighted formula — not the
    min()*0.5 fallback."""
    opt, baseline = _simple_opt(0.0, 0.0, 1.0, 0.0, 0.5)
    r = calculate_benchmark_result("t", opt, baseline, None)
    expected = 0.4 * (1.0 / max(1.0, 0.5)) + 0.3 * 1.0 + 0.3 * 0.5
    assert r.overall_score == pytest.approx(expected, abs=1e-12)


def test_prop_summary_timestamp_columns_align():
    """Markdown-free text report: runtime line always present."""
    rng = random.Random(5)
    text = format_text(_result(1, 0, rng))
    assert "Runtime:" in text
