"""Tests for uncovered ConstraintReport properties.

These properties are exercised indirectly but never asserted on directly,
leaving them as zero-coverage in the allowlist.
"""

from temper_placer.constraints.reporter import (
    ConstraintReport,
    ConstraintResult,
    ConstraintStatus,
)


def test_report_satisfied_filter():
    """ConstraintReport.satisfied filters satisfied constraints."""
    report = ConstraintReport(
        results=[
            ConstraintResult("A", ConstraintStatus.SATISFIED, "hard", ["C1"], "ok"),
            ConstraintResult("B", ConstraintStatus.VIOLATED, "hard", ["C2"], "fail"),
            ConstraintResult("C", ConstraintStatus.SATISFIED, "soft", ["C3"], "ok"),
            ConstraintResult("D", ConstraintStatus.SKIPPED, "hard", ["C4"], "skip"),
        ]
    )
    satisfied = report.satisfied
    assert len(satisfied) == 2
    assert all(r.status == ConstraintStatus.SATISFIED for r in satisfied)


def test_report_hard_results_filter():
    """ConstraintReport.hard_results filters hard-tier results only."""
    report = ConstraintReport(
        results=[
            ConstraintResult("A", ConstraintStatus.SATISFIED, "hard", ["C1"], "ok"),
            ConstraintResult("B", ConstraintStatus.VIOLATED, "hard", ["C2"], "fail"),
            ConstraintResult("C", ConstraintStatus.VIOLATED, "soft", ["C3"], "warn"),
            ConstraintResult("D", ConstraintStatus.SATISFIED, "soft", ["C4"], "ok"),
        ]
    )
    hard = report.hard_results
    assert len(hard) == 2
    assert all(r.tier == "hard" for r in hard)


def test_report_soft_results_filter():
    """ConstraintReport.soft_results filters soft-tier results only."""
    report = ConstraintReport(
        results=[
            ConstraintResult("A", ConstraintStatus.SATISFIED, "hard", ["C1"], "ok"),
            ConstraintResult("B", ConstraintStatus.VIOLATED, "hard", ["C2"], "fail"),
            ConstraintResult("C", ConstraintStatus.VIOLATED, "soft", ["C3"], "warn"),
            ConstraintResult("D", ConstraintStatus.SATISFIED, "soft", ["C4"], "ok"),
        ]
    )
    soft = report.soft_results
    assert len(soft) == 2
    assert all(r.tier == "soft" for r in soft)


def test_report_satisfied_empty():
    """ConstraintReport.satisfied returns empty list when none satisfied."""
    report = ConstraintReport(
        results=[
            ConstraintResult("A", ConstraintStatus.VIOLATED, "hard", ["C1"], "fail"),
            ConstraintResult("B", ConstraintStatus.SKIPPED, "soft", ["C2"], "skip"),
        ]
    )
    assert report.satisfied == []
    assert report.hard_results == [report.results[0]]
    assert report.soft_results == [report.results[1]]
