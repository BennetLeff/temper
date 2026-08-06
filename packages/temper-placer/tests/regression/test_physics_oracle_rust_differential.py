"""Differential test: physics-oracle compute kernels in Rust
(``temper_drc_rs.compute_oracle_margins`` / ``overall_score`` /
``clearance_passed``) vs the pinned Python oracle (Wave 4, Phase 4 —
regression slice).

``temper_placer/regression/physics_oracle.py`` moves its pure compute —
``compute_oracle_margins`` (score -> engineering-unit margin math),
``overall_score`` (the CPython-3.12 Neumaier-compensated ``sum()``/``len``
aggregation), and the clearance pass/fail threshold decision — into
``temper_drc_rs``. The pre-migration module is pinned verbatim as the oracle
(``_physics_oracle_py_oracle.py``, commit ``0a29f15e3``).

Design boundaries, argued in the migrated module and
``packages/temper-drc-rs/VERIFICATION.md``:

- This is an ORACLE/comparison kernel, NOT a physics gate (R1h): no CP-SAT
  constraint gates on a physics quantity here; the module scores a placement
  against physics metrics, it does not constrain the solve. State recorded
  explicitly because the ledger requires it.
- The metric functions themselves (``thermal_score``, ``dual_rail_clearance_report``,
  ``zone_compliance_score``, ``loop_area_score``, ``compactness_score``,
  ``derive_constraints_from_spec``, the parser, ``infer_quality_config``)
  live in other surfaces that are NOT part of this slice; the orchestration
  that calls them stays Python as cross-boundary call-backs.
- ``overall_score`` must reproduce CPython 3.12's ``sum()`` float path
  exactly: builtin ``sum()`` uses Neumaier-compensated summation for floats
  (measured: a plain ``+=`` accumulation diverges from ``sum()`` on
  4640/20000 random inputs on this platform) — plain accumulation would be
  a REAL mutation, caught by the differential.
- Margin multiplication is IEEE-754, identical in both arms.
"""

from __future__ import annotations

import random

import pytest
import temper_drc_rs as _tdrc

import tests.regression._physics_oracle_py_oracle as _oracle

# Rust symbols under test — must exist or this file fails to collect (RED).
COMPUTE_ORACLE_MARGINS = _tdrc.compute_oracle_margins
OVERALL_SCORE = _tdrc.overall_score
CLEARANCE_PASSED = _tdrc.clearance_passed

from temper_placer.regression.physics_oracle import (
    compute_oracle_margins as ShimMargins,  # noqa: E402
)


def _f(value):
    return None if value is None else float(value).hex()


def _canon_dict(d):
    return tuple((k, _f(v)) for k, v in d.items())


def _ref_overall(scores):
    """Verbatim transcription of the oracle's ``overall`` expression
    (``sum(normalized_scores) / len(normalized_scores) if normalized_scores
    else 0.0``), pinned against the oracle module's own line."""
    return sum(scores) / len(scores) if scores else 0.0


# ---------------------------------------------------------------------------
# R1a — differential
# ---------------------------------------------------------------------------


def test_differential_margins_random():
    rng = random.Random(0x0AC)
    for _ in range(400):
        report = {}
        for key in ("thermal_score", "hv_lv_clearance_score", "loop_area_score"):
            if rng.random() < 0.8:
                report[key] = rng.uniform(0.0, 2.0)
        # missing keys exercise the 1.0 defaults
        max_heat = rng.uniform(1.0, 30.0)
        hv_thresh = rng.uniform(1.0, 20.0)
        loop_max = rng.uniform(10.0, 200.0)
        o = _oracle.compute_oracle_margins(
            report,
            max_heatspread_mm=max_heat,
            hv_lv_threshold_mm=hv_thresh,
            max_loop_area_mm2=loop_max,
        )
        s = ShimMargins(
            report,
            max_heatspread_mm=max_heat,
            hv_lv_threshold_mm=hv_thresh,
            max_loop_area_mm2=loop_max,
        )
        assert _canon_dict(s) == _canon_dict(o), (report, max_heat, hv_thresh, loop_max)


def test_differential_margins_empty_report():
    o = _oracle.compute_oracle_margins({}, max_heatspread_mm=10.0, hv_lv_threshold_mm=6.5, max_loop_area_mm2=100.0)
    s = ShimMargins({}, max_heatspread_mm=10.0, hv_lv_threshold_mm=6.5, max_loop_area_mm2=100.0)
    assert _canon_dict(s) == _canon_dict(o)
    # all-missing report -> all defaults of 1.0
    assert _canon_dict(s) == (
        ("thermal_headroom_mm", (10.0).hex()),
        ("clearance_margin_mm", (0.0).hex()),
        ("loop_area_margin_mm2", (100.0).hex()),
    )


def test_differential_margins_threshold_keys():
    """The three margin keys are exact and in the oracle's order."""
    o = _oracle.compute_oracle_margins(
        {"thermal_score": 0.8, "hv_lv_clearance_score": 1.2, "loop_area_score": 0.5},
        max_heatspread_mm=10.0,
        hv_lv_threshold_mm=6.5,
        max_loop_area_mm2=100.0,
    )
    s = ShimMargins(
        {"thermal_score": 0.8, "hv_lv_clearance_score": 1.2, "loop_area_score": 0.5},
        max_heatspread_mm=10.0,
        hv_lv_threshold_mm=6.5,
        max_loop_area_mm2=100.0,
    )
    assert s == o
    assert list(s) == ["thermal_headroom_mm", "clearance_margin_mm", "loop_area_margin_mm2"]
    assert s["thermal_headroom_mm"] == 8.0
    assert s["clearance_margin_mm"] == pytest.approx(1.3)  # 0.2 * 6.5 = 1.2999999999999998
    assert s["loop_area_margin_mm2"] == 50.0


def test_differential_overall_random():
    rng = random.Random(0xBEEF)
    for _ in range(400):
        n = rng.randint(0, 8)
        scores = [rng.uniform(-1e4, 1e4) for _ in range(n)]
        assert OVERALL_SCORE(scores) == _ref_overall(scores)
    assert OVERALL_SCORE([]) == 0.0


def test_differential_overall_neumaier_boundary():
    """The classic Neumaier-failure case: a plain left-to-right sum loses the
    1.0. The kernel's compensated `sum()` recovers it: the OVERALL (the
    mean) is 1.0/3, where a plain-accumulation arm would give 0.0/3."""
    scores = [1e16, 1.0, -1e16]
    o = _ref_overall(scores)
    s = OVERALL_SCORE(scores)
    assert s == o
    assert s == pytest.approx(1.0 / 3)
    # the compensated sum itself is exactly 1.0 (not 0.0)
    assert s * 3.0 == 1.0


def test_differential_clearance_passed():
    for clearance in (0.0, 0.5, 0.949999999, 0.95, 0.9500000001, 1.0, 1.5):
        assert CLEARANCE_PASSED(clearance, 0.95) == (clearance >= 0.95)


# ---------------------------------------------------------------------------
# R1d — metamorphic relations (>=3, honestly bounded)
# ---------------------------------------------------------------------------


def test_mr1_margin_linear_in_score():
    """Scaling every score by a constant k scales each margin proportionally
    (thermal and loop are directly proportional; clearance margin is affine
    in the score with slope hv_lv_threshold)."""
    for score in (0.0, 0.25, 0.5, 1.0):
        for k in (2.0, 3.0):
            r0 = {"thermal_score": score, "hv_lv_clearance_score": score, "loop_area_score": score}
            o0 = _oracle.compute_oracle_margins(r0, max_heatspread_mm=10.0, hv_lv_threshold_mm=6.5, max_loop_area_mm2=100.0)
            rk = {kk: v * k for kk, v in r0.items()}
            ok = _oracle.compute_oracle_margins(rk, max_heatspread_mm=10.0, hv_lv_threshold_mm=6.5, max_loop_area_mm2=100.0)
            s0 = ShimMargins(r0, max_heatspread_mm=10.0, hv_lv_threshold_mm=6.5, max_loop_area_mm2=100.0)
            sk = ShimMargins(rk, max_heatspread_mm=10.0, hv_lv_threshold_mm=6.5, max_loop_area_mm2=100.0)
            assert s0 == o0 and sk == ok
            assert sk["thermal_headroom_mm"] == k * s0["thermal_headroom_mm"]
            assert sk["loop_area_margin_mm2"] == k * s0["loop_area_margin_mm2"]
            # affine in the score with slope hv_lv_threshold (both arms
            # compute (score*k - 1.0) * threshold — exact equality)
            assert sk["clearance_margin_mm"] == (score * k - 1.0) * 6.5


def test_mr2_missing_key_is_default():
    """A report missing a score is identical to a report carrying the 1.0
    default for that key (the kernel's dict .get(key, 1.0) semantics)."""
    for key in ("thermal_score", "hv_lv_clearance_score", "loop_area_score"):
        r0 = {}
        r1 = {key: 1.0}
        o0 = _oracle.compute_oracle_margins(r0, max_heatspread_mm=10.0, hv_lv_threshold_mm=6.5, max_loop_area_mm2=100.0)
        o1 = _oracle.compute_oracle_margins(r1, max_heatspread_mm=10.0, hv_lv_threshold_mm=6.5, max_loop_area_mm2=100.0)
        s0 = ShimMargins(r0, max_heatspread_mm=10.0, hv_lv_threshold_mm=6.5, max_loop_area_mm2=100.0)
        s1 = ShimMargins(r1, max_heatspread_mm=10.0, hv_lv_threshold_mm=6.5, max_loop_area_mm2=100.0)
        assert s0 == o0 and s1 == o1 and s0 == s1


def test_mr3_clearance_pass_threshold_boundary():
    """The pass decision is exactly ``clearance >= threshold`` — the boundary
    value passes and any value one ulp below fails."""
    import struct

    below = struct.unpack("f", struct.pack("f", 0.95))[0]
    # widen to double; 0.95 as float32 is slightly below the f64 0.95
    assert not CLEARANCE_PASSED(float(below), 0.95)
    assert CLEARANCE_PASSED(0.95, 0.95)
    assert CLEARANCE_PASSED(0.9500000000001, 0.95)


def test_mr4_overall_permutation_sensitivity_bounded():
    """``sum`` is a commutativity-holder, so a permutation may change the
    last bit — the oracle's own ``sum()`` has the same property. The
    relation asserted is: the kernel agrees with the oracle on every
    permutation (both arms move together), NOT that the result is
    permutation-invariant."""
    rng = random.Random(42)
    for _ in range(50):
        scores = [rng.uniform(-1e4, 1e4) for _ in range(6)]
        shuffled = scores[::-1]
        assert OVERALL_SCORE(shuffled) == _ref_overall(shuffled)
        assert OVERALL_SCORE(scores) == _ref_overall(scores)


# ---------------------------------------------------------------------------
# R1c — non-vacuous properties (>=5)
# ---------------------------------------------------------------------------


def test_prop1_margin_formula_exact():
    s = ShimMargins(
        {"thermal_score": 0.75, "hv_lv_clearance_score": 0.8, "loop_area_score": 0.4},
        max_heatspread_mm=10.0,
        hv_lv_threshold_mm=6.5,
        max_loop_area_mm2=100.0,
    )
    assert s["thermal_headroom_mm"] == 7.5
    assert s["clearance_margin_mm"] == pytest.approx(-1.3)  # signed: negative = violation
    assert s["loop_area_margin_mm2"] == 40.0


def test_prop2_clearance_margin_signed():
    """Score < 1.0 -> negative clearance margin (a violation estimate); score
    > 1.0 -> positive headroom."""
    for score in (0.5, 0.99, 1.0, 1.01, 1.5):
        s = ShimMargins(
            {"hv_lv_clearance_score": score},
            max_heatspread_mm=10.0,
            hv_lv_threshold_mm=6.5,
            max_loop_area_mm2=100.0,
        )
        assert (s["clearance_margin_mm"] < 0) == (score < 1.0)
        assert (s["clearance_margin_mm"] > 0) == (score > 1.0)


def test_prop3_overall_score_healthy_board():
    """All-1.0 scores -> overall 1.0; all-0.0 -> overall 0.0."""
    assert OVERALL_SCORE([1.0, 1.0, 1.0, 1.0, 1.0]) == 1.0
    assert OVERALL_SCORE([0.0, 0.0, 0.0, 0.0, 0.0]) == 0.0


def test_prop4_overall_score_is_mean():
    """For two scores the overall is exactly their average."""
    for a, b in [(0.0, 1.0), (0.5, 0.5), (1.0, 2.0)]:
        assert OVERALL_SCORE([a, b]) == (a + b) / 2.0


def test_prop5_overall_empty_is_zero():
    assert OVERALL_SCORE([]) == 0.0


def test_prop6_overall_matches_oracle_on_metric_round_numbers():
    """A realistic 5-metric report (the oracle's own normalized_scores list)
    must match the oracle bit-for-bit."""
    scores = [0.95, 1.0, 0.875, 0.7, 0.8]
    assert OVERALL_SCORE(scores) == _ref_overall(scores)


def test_prop7_clearance_passed_flag_matches_margin_sign():
    """The pass decision and the signed clearance margin are consistent in
    the two clear regimes: score >= 1.0 passes with a non-negative margin;
    score < 0.95 fails with a negative margin. In the 0.95 <= score < 1.0
    window the oracle PASSES with a still-negative margin (the threshold is
    on the raw score, the margin on (score-1.0)) — the oracle's own quirk,
    preserved by the kernel."""
    for score in (0.7, 0.9, 0.94):
        passed = CLEARANCE_PASSED(score, 0.95)
        margin = ShimMargins(
            {"hv_lv_clearance_score": score},
            max_heatspread_mm=10.0,
            hv_lv_threshold_mm=6.5,
            max_loop_area_mm2=100.0,
        )["clearance_margin_mm"]
        assert not passed
        assert margin < 0.0
    for score in (1.0, 1.5):
        passed = CLEARANCE_PASSED(score, 0.95)
        margin = ShimMargins(
            {"hv_lv_clearance_score": score},
            max_heatspread_mm=10.0,
            hv_lv_threshold_mm=6.5,
            max_loop_area_mm2=100.0,
        )["clearance_margin_mm"]
        assert passed
        assert margin >= 0.0
