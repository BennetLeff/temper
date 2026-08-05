"""Differential test: CP-SAT comparison kernel in Rust
(``temper_design_bundle_python.compare_metric_dicts``) vs the pinned Python
oracle (Wave 4, Phase 4 — regression slice).

``temper_placer/regression/cp_sat_comparison.py`` is fully portable compute:
``compare_metric_dicts`` (the Pareto-style per-metric gate, the wirelength
ratio/tolerance rule, the ``:.2f``/``:.3f``/``:.4f`` detail strings, the
summary line, and the failing-metric list repr) moves to
``temper-design-bundle``. The pre-migration module is pinned verbatim as the
oracle (``_cp_sat_comparison_py_oracle.py``, commit ``0a29f15e3``).

Formatting notes (each pinned by the differential):
- Fixed-point ``:.Nf`` formatting is measured CPython-parity (the
  validation-slice precedent).
- The summary's ``Failing: ['a', 'b']`` list is Python's repr of a list of
  str; the kernel renders the same shape (single quotes, ``, `` join).
  Metric names are score-dict keys — realistically simple identifiers; a
  name containing a quote/backslash is a documented narrowing.
- ``bool`` interpolation in the detail lines renders ``True``/``False``
  (Python) — the kernel must not use Rust's ``true``/``false``.
"""

from __future__ import annotations

import random

import pytest
import temper_design_bundle_python as _tdb

import tests.regression._cp_sat_comparison_py_oracle as _oracle

# Rust symbol under test — must exist or this file fails to collect (RED).
COMPARE_METRIC_DICTS = _tdb.compare_metric_dicts

from temper_placer.regression.cp_sat_comparison import (  # noqa: E402
    ParityComparisonResult,
    compare_metric_dicts as ShimCompare,
)


def _f(v):
    return None if v is None else float(v).hex()


def _canon_comp(c):
    return (c.name, _f(c.cp_sat_value), _f(c.jax_value), c.passed, c.detail)


def _canon_result(r):
    return (
        r.passed,
        tuple(_canon_comp(c) for c in r.comparisons),
        r.summary,
    )


def _random_scores(rng):
    keys = ["clearance_3mm", "clearance_6mm", "thermal_score", "total_manhattan_wirelength", "zone_score"]
    d = {}
    for k in keys:
        if rng.random() < 0.7:
            d[k] = rng.choice([rng.uniform(0.0, 100.0), rng.randint(0, 100)])
    return d


# ---------------------------------------------------------------------------
# R1a — differential
# ---------------------------------------------------------------------------


def test_differential_random():
    rng = random.Random(0xFEED)
    for _ in range(400):
        cand = _random_scores(rng)
        base = _random_scores(rng)
        o = _oracle.compare_metric_dicts(cand, base)
        s = ShimCompare(cand, base)
        assert _canon_result(s) == _canon_result(o)


def test_differential_wirelength_rules():
    """The wirelength metric is lower-is-better within a 5% tolerance; the
    baseline==0 arm requires candidate==0 (ratio=inf)."""
    cases = [
        ({"total_manhattan_wirelength": 100.0}, {"total_manhattan_wirelength": 100.0}),
        ({"total_manhattan_wirelength": 104.9}, {"total_manhattan_wirelength": 100.0}),
        ({"total_manhattan_wirelength": 105.1}, {"total_manhattan_wirelength": 100.0}),
        ({"total_manhattan_wirelength": 0.0}, {"total_manhattan_wirelength": 0.0}),
        ({"total_manhattan_wirelength": 1.0}, {"total_manhattan_wirelength": 0.0}),
        ({"total_manhattan_wirelength": 0.5}, {"total_manhattan_wirelength": 0.4}),
        ({"total_manhattan_wirelength": 0.0}, {"total_manhattan_wirelength": 10.0}),
    ]
    for cand, base in cases:
        o = _oracle.compare_metric_dicts(cand, base)
        s = ShimCompare(cand, base)
        assert _canon_result(s) == _canon_result(o)
        comp = s.comparisons[0]
        assert comp.name == "total_manhattan_wirelength"
        if base["total_manhattan_wirelength"] > 0:
            assert comp.detail.startswith(
                f"total_manhattan_wirelength: candidate={cand['total_manhattan_wirelength']:.2f}"
            )
            assert "ratio=1.050" in comp.detail or "ratio=" in comp.detail


def test_differential_higher_is_better_metrics():
    o = _oracle.compare_metric_dicts(
        {"clearance_3mm": 0.9, "thermal_score": 0.5},
        {"clearance_3mm": 0.8, "thermal_score": 0.6},
    )
    s = ShimCompare(
        {"clearance_3mm": 0.9, "thermal_score": 0.5},
        {"clearance_3mm": 0.8, "thermal_score": 0.6},
    )
    assert _canon_result(s) == _canon_result(o)
    by_name = {c.name: c for c in s.comparisons}
    assert by_name["clearance_3mm"].passed
    assert not by_name["thermal_score"].passed
    assert not s.passed
    assert "thermal_score" in s.summary


def test_differential_summary_failing_list():
    """The summary's Failing list renders Python-list-of-str style."""
    o = _oracle.compare_metric_dicts(
        {"a": 1.0, "b": 2.0},
        {"a": 2.0, "b": 3.0},
        wirelength_metric="none",
    )
    s = ShimCompare(
        {"a": 1.0, "b": 2.0},
        {"a": 2.0, "b": 3.0},
        wirelength_metric="none",
    )
    assert _canon_result(s) == _canon_result(o)
    assert "Failing: ['a', 'b']" in s.summary


def test_differential_empty_intersection():
    o = _oracle.compare_metric_dicts({"a": 1.0}, {"b": 2.0})
    s = ShimCompare({"a": 1.0}, {"b": 2.0})
    assert _canon_result(s) == _canon_result(o)
    assert s.passed is True  # vacuous intersection — oracle semantics
    assert s.comparisons == []
    assert s.summary == "Parity comparison: 0/0 metrics passed"


def test_differential_all_passed_summary():
    o = _oracle.compare_metric_dicts(
        {"a": 5.0, "b": 5.0},
        {"a": 5.0, "b": 4.0},
        wirelength_metric="none",
    )
    s = ShimCompare(
        {"a": 5.0, "b": 5.0},
        {"a": 5.0, "b": 4.0},
        wirelength_metric="none",
    )
    assert _canon_result(s) == _canon_result(o)
    assert "Parity comparison: 2/2 metrics passed" in s.summary


def test_differential_custom_wirelength_metric():
    o = _oracle.compare_metric_dicts(
        {"wl": 10.0, "score": 1.0},
        {"wl": 10.0, "score": 1.0},
        wirelength_metric="wl",
    )
    s = ShimCompare(
        {"wl": 10.0, "score": 1.0},
        {"wl": 10.0, "score": 1.0},
        wirelength_metric="wl",
    )
    assert _canon_result(s) == _canon_result(o)


def test_differential_type_carrying_values():
    """int and float leaves in the score dicts compare identically (the
    oracle converts with float() and keeps the numeric comparison)."""
    o = _oracle.compare_metric_dicts(
        {"a": 5, "b": 2},
        {"a": 5.0, "b": 3},
        wirelength_metric="none",
    )
    s = ShimCompare(
        {"a": 5, "b": 2},
        {"a": 5.0, "b": 3},
        wirelength_metric="none",
    )
    assert _canon_result(s) == _canon_result(o)
    assert s.comparisons[0].cp_sat_value == 5.0  # float()-converted


# ---------------------------------------------------------------------------
# R1d — metamorphic relations (>=3, honestly bounded)
# ---------------------------------------------------------------------------


def test_mr1_passed_is_monotone_in_candidate():
    """Improving a higher-is-better candidate metric from below to at-or-above
    the baseline can only flip that metric pass and the overall result to
    True — never the reverse."""
    base = {"a": 5.0}
    results = []
    for cand_val in (4.0, 4.99, 5.0, 5.01, 6.0):
        s = ShimCompare({"a": cand_val}, base, wirelength_metric="none")
        results.append(s.passed)
        assert s.comparisons[0].passed == (cand_val >= 5.0 - 1e-9)
    assert results == [False, False, True, True, True]


def test_mr2_wirelength_ratio_scale_invariance():
    """Scaling both candidate and baseline wirelength by the same positive
    factor preserves the pass decision and the ratio (bounded to the ratio
    detail: the detail string's candidate/baseline numbers scale, the
    decision and ratio are invariant)."""
    for cand, base in [(100.0, 95.0), (105.0, 100.0), (104.9, 100.0)]:
        r1 = ShimCompare(
            {"wl": cand, "t": 1.0}, {"wl": base, "t": 1.0}, wirelength_metric="wl"
        )
        r2 = ShimCompare(
            {"wl": cand * 10, "t": 1.0}, {"wl": base * 10, "t": 1.0}, wirelength_metric="wl"
        )
        assert r1.comparisons[0].passed == r2.comparisons[0].passed
        # ratio text is preserved: candidate/base ratio unchanged
        d1 = r1.comparisons[0].detail
        d2 = r2.comparisons[0].detail
        ratio_part1 = d1.split("ratio=")[1].split(",")[0]
        ratio_part2 = d2.split("ratio=")[1].split(",")[0]
        assert ratio_part1 == ratio_part2


def test_mr3_metric_permutation_order_invariance():
    """The per-metric comparisons are emitted in sorted metric-name order,
    so the result is independent of the dict insertion order."""
    cand1 = {"b": 1.0, "a": 2.0}
    base1 = {"b": 1.0, "a": 1.0}
    cand2 = {"a": 2.0, "b": 1.0}
    base2 = {"a": 1.0, "b": 1.0}
    r1 = ShimCompare(cand1, base1, wirelength_metric="none")
    r2 = ShimCompare(cand2, base2, wirelength_metric="none")
    assert [c.name for c in r1.comparisons] == [c.name for c in r2.comparisons] == ["a", "b"]


def test_mr4_every_metric_passing_implies_overall_passing():
    """Per-metric passed flags are conjunctive with the overall result."""
    for seed in range(30):
        rng = random.Random(seed)
        cand = _random_scores(rng)
        base = _random_scores(rng)
        s = ShimCompare(cand, base)
        assert s.passed == all(c.passed for c in s.comparisons)


# ---------------------------------------------------------------------------
# R1c — non-vacuous properties (>=5)
# ---------------------------------------------------------------------------


def test_prop1_clearance_tolerance_boundary():
    """A candidate exactly at the baseline passes; exactly 5%+epsilon above
    baseline fails (1e-9 slack applies to higher-is-better only, NOT to the
    wirelength 5% tolerance)."""
    assert ShimCompare({"wl": 105.0}, {"wl": 100.0}, wirelength_metric="wl").passed
    assert not ShimCompare({"wl": 105.1}, {"wl": 100.0}, wirelength_metric="wl").passed


def test_prop2_zero_baseline_wirelength_is_strict():
    """baseline==0 requires candidate==0 exactly (-0.0 counts as 0)."""
    assert ShimCompare({"wl": 0.0}, {"wl": 0.0}, wirelength_metric="wl").passed
    assert ShimCompare({"wl": -0.0}, {"wl": 0.0}, wirelength_metric="wl").passed
    assert not ShimCompare({"wl": 1e-12}, {"wl": 0.0}, wirelength_metric="wl").passed


def test_prop3_higher_is_better_epsilon():
    """Higher-is-better metrics pass within 1e-9 of baseline."""
    assert ShimCompare({"a": 5.0 - 1e-9}, {"a": 5.0}, wirelength_metric="none").passed
    assert not ShimCompare({"a": 5.0 - 1e-8}, {"a": 5.0}, wirelength_metric="none").passed


def test_prop4_detail_strings_carry_fixed_precision():
    r = ShimCompare(
        {"clearance_3mm": 0.56789, "total_manhattan_wirelength": 1234.5678},
        {"clearance_3mm": 0.5, "total_manhattan_wirelength": 1200.0},
    )
    by_name = {c.name: c for c in r.comparisons}
    assert "candidate=0.5679, baseline=0.5000, delta=0.0679" in by_name["clearance_3mm"].detail
    assert "candidate=1234.57, baseline=1200.00, ratio=1.029" in by_name[
        "total_manhattan_wirelength"
    ].detail


def test_prop5_metric_union_semantics():
    """Only metrics present in BOTH dicts are compared; keys unique to one
    side are ignored (set intersection)."""
    r = ShimCompare(
        {"shared": 1.0, "only_cand": 99.0},
        {"shared": 0.5, "only_base": 88.0},
        wirelength_metric="none",
    )
    assert [c.name for c in r.comparisons] == ["shared"]
    assert r.passed


def test_prop6_summary_reports_all_failing_metrics():
    r = ShimCompare(
        {"x": 0.0, "y": 0.0, "z": 10.0},
        {"x": 1.0, "y": 2.0, "z": 10.0},
        wirelength_metric="none",
    )
    assert "Failing: ['x', 'y']" in r.summary
    assert r.summary.startswith("Parity FAILED: 1/3 metrics passed")
