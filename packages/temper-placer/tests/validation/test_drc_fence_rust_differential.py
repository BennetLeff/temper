"""Differential test: drc_fence aggregation kernels in Rust (temper_drc_rs)
vs the pinned Python oracle (Wave 4, Phase 4 — validation DRC-check slice).

``temper_placer/validation/drc_fence.py`` moves two pure compute kernels to
``temper_drc_rs``:
- ``_issue_fingerprint`` (canonical violation fingerprint) →
  ``temper_drc_rs.issue_fingerprint``
- ``MetricsSummary.from_run_result`` (the per-check aggregation loop:
  checks_run order, check_timings, per-category issue counts, custom-metric
  accumulation) → ``temper_drc_rs.metrics_summary``

The ``DRCFence.check`` orchestration stays Python (wall-clock timing,
logging, budget/failure raising — orchestration, not compute, argued
in-source). The oracle is the verbatim pre-migration module
(``_drc_fence_py_oracle.py``, commit ``aece7c372``).

Comparison convention: floats bit-exact via ``float.hex()``.
"""

from __future__ import annotations

import random

import pytest
import temper_drc_rs as _tdrc
from hypothesis import given, settings
from hypothesis import strategies as st

import tests.validation._drc_fence_py_oracle as _oracle
from temper_placer.validation.drc_fence import (
    MetricsSummary as ShimMetricsSummary,
)
from temper_placer.validation.drc_result import (
    CheckResult,
    Issue,
    RunResult,
    Severity,
)

# Rust symbols under test — must exist or this file fails to collect (RED).
ISSUE_FINGERPRINT = _tdrc.issue_fingerprint
METRICS_SUMMARY = _tdrc.metrics_summary

from temper_placer.validation.drc_fence import _issue_fingerprint as shim_fingerprint  # noqa: E402

# ---------------------------------------------------------------------------
# issue_fingerprint — differential + PBT + MR
# ---------------------------------------------------------------------------


def _fingerprint_both(code, message, affected_items):
    ref = _oracle._issue_fingerprint(
        _oracle.Issue(
            severity=_oracle.Severity.ERROR, code=code, message=message,
            category="drc", check_name="c", affected_items=list(affected_items),
        )
    )
    got = ISSUE_FINGERPRINT(code, message, list(affected_items))
    # the delegating shim (drc_fence._issue_fingerprint) must agree too
    shim = shim_fingerprint(
        Issue(
            severity=Severity.ERROR, code=code, message=message,
            category="drc", check_name="c", affected_items=list(affected_items),
        )
    )
    assert shim == got == ref
    return ref, got


@settings(max_examples=60, deadline=None)
@given(
    st.text(min_size=0, max_size=30),
    st.text(min_size=0, max_size=60),
    st.lists(st.text(min_size=0, max_size=12), min_size=0, max_size=8),
)
def test_fingerprint_differential(code, message, items):
    ref, got = _fingerprint_both(code, message, items)
    assert got == ref


def test_fingerprint_differential_edge():
    # empty items → "code:message:"
    ref, got = _fingerprint_both("X", "m", [])
    assert got == ref == "X:m:"
    # duplicate items — sorted() keeps duplicates
    ref, got = _fingerprint_both("X", "m", ["b", "a", "b"])
    assert got == ref == "X:m:a,b,b"
    # sorting is lexical (byte order)
    ref, got = _fingerprint_both("X", "m", ["Z1", "R10", "R2", "r1"])
    assert got == ref == "X:m:R10,R2,Z1,r1"


def test_prop1_fingerprint_sorted_items():
    """P1: the item list in the fingerprint is sorted."""
    for items in (["b", "a"], ["z", "y", "x"], ["10", "9"], ["C10", "C2"]):
        ref, got = _fingerprint_both("X", "m", items)
        suffix = got.split(":", 2)[2]
        assert suffix == ",".join(sorted(items))


def test_prop2_fingerprint_missing_parts():
    """P2: empty code/message/items each render as the empty segment —
    exactly two colons in the output."""
    ref, got = _fingerprint_both("", "", [])
    assert got == ref == "::"
    assert got.count(":") == 2


def test_prop3_fingerprint_distinguishes_messages():
    """P3: different messages with the same code and items yield different
    fingerprints (the message is not dropped)."""
    a, _ = _fingerprint_both("X", "msg one", ["a"])
    b, _ = _fingerprint_both("X", "msg two", ["a"])
    assert a != b


def test_mr1_fingerprint_item_permutation():
    """MR1: permuting affected_items leaves the fingerprint unchanged
    (sorted before join)."""
    items = ["c", "a", "b", "d"]
    ref, _ = _fingerprint_both("X", "m", items)
    for _ in range(5):
        perm = items[:]
        random.shuffle(perm)
        _, got = _fingerprint_both("X", "m", perm)
        assert got == ref


def test_mr2_fingerprint_composition():
    """MR2: the fingerprint is exactly the concatenation of the three
    fields with ":" separators — splitting recovers the sorted items."""
    code, message, items = "DRC_1", "hello world", ["b", "a", "c"]
    _, got = _fingerprint_both(code, message, items)
    c, m, rest = got.split(":", 2)
    assert c == code and m == message
    assert rest == ",".join(sorted(items))


def test_mr3_fingerprint_prefix_monotone():
    """MR3: appending an item to affected_items appends to the sorted tail
    of the fingerprint's item segment (the prefix is unchanged)."""
    _, got = _fingerprint_both("X", "m", ["a", "b"])
    _, got2 = _fingerprint_both("X", "m", ["a", "b", "c"])
    assert got2.startswith(got + ",")


# ---------------------------------------------------------------------------
# metrics_summary — differential
# ---------------------------------------------------------------------------


def _mk_run_result(rng, n_checks):
    check_results = []
    for _ in range(n_checks):
        n_issues = rng.randint(0, 4)
        categories = [rng.choice(["erc", "drc", "safety", "emc", "other"]) for _ in range(n_issues)]
        metrics = {}
        if rng.random() < 0.7:
            metrics = {f"m{k}": rng.uniform(-100, 100) for k in range(rng.randint(1, 3))}
        check_results.append(
            CheckResult(
                check_name=f"check_{rng.randint(0, 3)}",
                passed=rng.random() < 0.7,
                issues=[
                    Issue(severity=Severity.ERROR, code="X", message="m",
                          category=cat, check_name=f"check_{k}")
                    for k, cat in enumerate(categories)
                ],
                elapsed_ms=rng.uniform(0, 500),
                metrics=metrics,
            )
        )
    return RunResult(check_results=check_results, total_elapsed_ms=rng.uniform(0, 1000))


def _summary_fields(s):
    return (
        s.total_checks,
        s.passed_checks,
        s.failed_checks,
        float(s.total_elapsed_ms).hex(),
        s.info_count,
        s.warning_count,
        s.error_count,
        s.critical_count,
        s.erc_issues,
        s.drc_issues,
        s.safety_issues,
        s.emc_issues,
        tuple(s.checks_run),
        tuple((k, float(v).hex()) for k, v in s.check_timings.items()),
        tuple(sorted((k, float(v).hex()) for k, v in s.custom_metrics.items())),
        tuple(s.checks_skipped),
    )


def test_metrics_summary_differential_deterministic():
    rr = RunResult(
        check_results=[
            CheckResult(check_name="a", passed=True, elapsed_ms=1.5,
                        issues=[
                            Issue(severity=Severity.ERROR, code="X", message="m", category="drc", check_name="a"),
                            Issue(severity=Severity.WARNING, code="X", message="m", category="erc", check_name="a"),
                        ],
                        metrics={"m1": 1.0, "m2": 2.5}),
            CheckResult(check_name="b", passed=False, elapsed_ms=3.25,
                        issues=[Issue(severity=Severity.CRITICAL, code="X", message="m", category="emc", check_name="b")],
                        metrics={"m1": 0.5}),
            CheckResult(check_name="a", passed=True, elapsed_ms=0.75,
                        issues=[Issue(severity=Severity.INFO, code="X", message="m", category="safety", check_name="a")],
                        metrics={"m1": 2.0, "m3": 10.0}),
            CheckResult(check_name="c", passed=True, elapsed_ms=9.0,
                        issues=[Issue(severity=Severity.INFO, code="X", message="m", category="other", check_name="c")],
                        metrics={}),
        ],
        total_elapsed_ms=15.0,
    )
    oracle_s = _oracle.MetricsSummary.from_run_result(rr, skipped_checks=["skip1"])
    shim_s = ShimMetricsSummary.from_run_result(rr, skipped_checks=["skip1"])
    assert _summary_fields(shim_s) == _summary_fields(oracle_s)
    # duplicate check names: checks_run keeps both; check_timings keeps the
    # LAST elapsed_ms at the FIRST position
    assert shim_s.checks_run == ["a", "b", "a", "c"]
    assert shim_s.check_timings["a"] == 0.75
    assert shim_s.erc_issues == 1 and shim_s.drc_issues == 1
    assert shim_s.safety_issues == 1 and shim_s.emc_issues == 1
    assert shim_s.custom_metrics == {"m1": 3.5, "m2": 2.5, "m3": 10.0}


def test_metrics_summary_differential_random():
    rng = random.Random(2026)
    for _ in range(100):
        rr = _mk_run_result(rng, rng.randint(0, 6))
        skipped = [f"s{i}" for i in range(rng.randint(0, 2))]
        oracle_s = _oracle.MetricsSummary.from_run_result(rr, skipped_checks=skipped)
        shim_s = ShimMetricsSummary.from_run_result(rr, skipped_checks=skipped)
        assert _summary_fields(shim_s) == _summary_fields(oracle_s)


def test_metrics_summary_empty():
    rr = RunResult(check_results=[], total_elapsed_ms=0.0)
    oracle_s = _oracle.MetricsSummary.from_run_result(rr)
    shim_s = ShimMetricsSummary.from_run_result(rr)
    assert _summary_fields(shim_s) == _summary_fields(oracle_s)
    assert shim_s.checks_run == [] and shim_s.check_timings == {}
    assert shim_s.erc_issues == shim_s.drc_issues == 0


def test_metrics_summary_int_values_type_preserved():
    """The oracle assigns/accumulates the caller's numeric values verbatim
    (``check_timings[name] = elapsed_ms``; ``custom_metrics[key] += value``):
    an int stays int (exact beyond 2^53), int+int accumulates as int, and an
    int+float ``+=`` promotes to float. Regression: the shim previously
    coerced ``float(...)`` into the kernel's f64, turning ``3`` into ``3.0``."""
    rr = RunResult(
        check_results=[
            CheckResult(check_name="a", passed=True, elapsed_ms=3, metrics={"m1": 3}),
            CheckResult(check_name="a", passed=True, elapsed_ms=7, metrics={"m1": 4}),
            CheckResult(check_name="b", passed=True, elapsed_ms=2, metrics={"m1": 0.5, "m2": 1}),
        ],
    )
    oracle_s = _oracle.MetricsSummary.from_run_result(rr)
    shim_s = ShimMetricsSummary.from_run_result(rr)
    assert _summary_fields(shim_s) == _summary_fields(oracle_s)
    # type preservation, shim == oracle exactly (values AND types)
    assert shim_s.check_timings == oracle_s.check_timings == {"a": 7, "b": 2}
    assert shim_s.custom_metrics == oracle_s.custom_metrics == {"m1": 7.5, "m2": 1}
    assert type(shim_s.check_timings["a"]) is int
    assert type(shim_s.check_timings["b"]) is int
    assert type(shim_s.custom_metrics["m1"]) is float  # int + float → float
    assert type(shim_s.custom_metrics["m2"]) is int


# ---------------------------------------------------------------------------
# PBT — five non-vacuous properties of the migrated kernels
# ---------------------------------------------------------------------------


def test_prop4_metrics_category_counting():
    """P4: only erc/drc/safety/emc categories are counted (the oracle's
    elif chain — "other" categories are not tallied anywhere)."""
    rr = RunResult(
        check_results=[
            CheckResult(check_name="x", passed=True,
                        issues=[
                            Issue(severity=Severity.INFO, code="X", message="m", category="erc", check_name="x"),
                            Issue(severity=Severity.INFO, code="X", message="m", category="other", check_name="x"),
                            Issue(severity=Severity.INFO, code="X", message="m", category="drc", check_name="x"),
                        ]),
        ],
    )
    s = ShimMetricsSummary.from_run_result(rr)
    assert s.erc_issues == 1 and s.drc_issues == 1
    assert s.safety_issues == 0 and s.emc_issues == 0


def test_prop5_metrics_custom_accumulation():
    """P5: custom metrics accumulate across check results by key; a key seen
    first in a later check keeps its first-seen dict position."""
    rr = RunResult(
        check_results=[
            CheckResult(check_name="a", passed=True, metrics={"k1": 1.0}),
            CheckResult(check_name="b", passed=True, metrics={"k2": 5.0, "k1": 2.0}),
            CheckResult(check_name="c", passed=True, metrics={"k1": 3.0}),
        ],
    )
    s = ShimMetricsSummary.from_run_result(rr)
    assert s.custom_metrics == {"k1": 6.0, "k2": 5.0}
    assert list(s.custom_metrics) == ["k1", "k2"]


# ---------------------------------------------------------------------------
# Metamorphic relations (additional to the fingerprint MRs above)
# ---------------------------------------------------------------------------


def test_mr4_metrics_permuting_checks_permutes_run_order():
    """MR4: permuting check_results permutes checks_run accordingly and
    leaves the counts and custom-metric totals unchanged (bounded: timings
    are keyed by name, so the timings dict is invariant under permutation
    when names are distinct)."""
    rng = random.Random(71)
    checks = [
        CheckResult(check_name=n, passed=True, elapsed_ms=float(i), metrics={"m": float(i)})
        for i, n in enumerate(["a", "b", "c", "d"])
    ]
    rr = RunResult(check_results=checks)
    base = ShimMetricsSummary.from_run_result(rr)
    for _ in range(5):
        perm = checks[:]
        rng.shuffle(perm)
        got = ShimMetricsSummary.from_run_result(RunResult(check_results=perm))
        assert got.checks_run == [c.check_name for c in perm]
        assert got.check_timings == base.check_timings
        assert got.custom_metrics == base.custom_metrics
        assert got.passed_checks == base.passed_checks


def test_mr5_metrics_duplicate_names_last_timing_wins():
    """MR5: when a check name appears twice, the timing map holds the LAST
    value at the FIRST position (Python dict assignment semantics), while
    checks_run holds both entries."""
    rr = RunResult(
        check_results=[
            CheckResult(check_name="x", passed=True, elapsed_ms=1.0),
            CheckResult(check_name="x", passed=True, elapsed_ms=2.0),
        ],
    )
    s = ShimMetricsSummary.from_run_result(rr)
    assert s.checks_run == ["x", "x"]
    assert s.check_timings == {"x": 2.0}


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
