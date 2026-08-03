"""Property-based tests for the Rust composite-quality-score kernels
(``temper_quality_oracle.placement_score_py`` /
``temper_quality_oracle.drc_score_py`` /
``temper_quality_oracle.overall_score_py`` /
``temper_quality_oracle.interpret_score_py``, Wave 4 Phase A #5 —
migration of ``temper_placer/metrics/quality_score.py``).

The kernels are pure closed-form f64 arithmetic over bounded violation
counts and wirelength scalars: per-violation penalties subtracted from
100.0 in a fixed left-to-right order, the ``min(10, (avg_len-50)/10)``
wirelength penalty, the constant-first ``max(0.0, min(100.0, score))``
clamp, the 50/50 or 40/40/20 weighted overall, and the
``>= 90 / >= 80 / >= 60`` interpretation thresholds.  Every property
below is a direct statement about correctly-rounded IEEE-754 operations,
and each is vacuity-guarded (its docstring says why a constant /
degenerate implementation fails it).

Exactness notes:

- All per-violation penalties are exact int arithmetic in Python,
  converted to f64 exactly at the subtraction, so
  ``score -= overlap_count * 20`` ⇔ ``score -= overlap_count as f64 * 20.0``
  is bit-identical; the closed-form recomputes in P2/P3/P6 below use the
  same left-to-right op order and are bit-exact.
- The clamp is ``max(0.0, min(100.0, score))`` — constant FIRST, matching
  CPython's first-argument NaN semantics (B5); the strategies keep
  counts finite and non-negative so the clamp is a plain bound.
- Penalty-translation metamorphic relations (M1/M2) are exact for small
  counts because 100.0 - 20.0k / 15.0e / 3.0w stay exactly representable
  in f64 (small integers in the same binade — Sterbenz-style exact
  subtraction), so the difference is exactly the per-unit penalty until
  the clamp engages; the strategies bound the counts so the clamp never
  engages inside the relation's domain.
"""

from __future__ import annotations

import random

import pytest
import temper_quality_oracle as _tqo
from hypothesis import given, settings
from hypothesis import strategies as st

MAX_EXAMPLES = 200

# Bounded violation counts (realistic + headroom; stays unclamped so the
# exact translation relations hold).
_overlap = st.integers(min_value=0, max_value=4)
_boundary = st.integers(min_value=0, max_value=5)
_hvlv = st.integers(min_value=0, max_value=3)
_keepout = st.integers(min_value=0, max_value=8)
_clearance = st.integers(min_value=0, max_value=10)
_zone = st.integers(min_value=0, max_value=8)
_wl = st.floats(min_value=0.0, max_value=1e4, allow_nan=False, allow_infinity=False)
_avg = st.floats(min_value=0.0, max_value=200.0, allow_nan=False, allow_infinity=False)
_drc_err = st.integers(min_value=0, max_value=6)
_drc_warn = st.integers(min_value=0, max_value=30)
_score_val = st.floats(min_value=-10.0, max_value=120.0, allow_nan=False, allow_infinity=False)

# ---------------------------------------------------------------------------
# Exact-translation input class (P3/P6, M1/M2)
# ---------------------------------------------------------------------------
# The per-unit-penalty translation relations are only exact while BOTH
# endpoints stay strictly inside (0, 100): outside that range the final
# clamp `max(0.0, min(100.0, ·))` engages and the difference is no longer
# the raw penalty.  To keep the relation honestly bounded, these relations
# draw from a constrained class where the total penalty is at most 45:
#
#   - hv_lv is FIXED at 0 (its 25/unit weight is the largest; excluding it
#     keeps the bound tight), boundary/keepout/zone ∈ {0, 1}, and
#     clearance ∈ {0, 1, 2} (so the 5/unit (clearance - hv_lv) term is at
#     most 10);
#   - total_wirelength is FIXED at 0.0 so the wirelength branch is skipped
#     (avg_net_length is then irrelevant — the branch never runs);
#   - the base point is overlap = 0, so base ∈ [100 - 45, 100] = [55, 100]
#     and the worst shifted point (overlap = 3, total penalty 45 + 60 =
#     105 → but clamped) is avoided by capping delta at 2: shifted ∈
#     [100 - 45 - 40, 100] = [15, 100].  Both endpoints are therefore
#     strictly inside (0, 100] and the subtraction is Sterbenz-exact.
#
# Every relation documents this class and states why a degenerate kernel
# fails within it.
_exact_boundary = st.integers(min_value=0, max_value=1)
_exact_keepout = st.integers(min_value=0, max_value=1)
_exact_zone = st.integers(min_value=0, max_value=1)
_exact_clearance = st.integers(min_value=0, max_value=2)


def _place(overlap, boundary, hvlv, keepout, clearance, zone, total_wl, avg_len):
    return _tqo.placement_score_py(
        overlap, boundary, hvlv, keepout, clearance, zone, total_wl, avg_len
    )


def _drc(err, warn):
    return _tqo.drc_score_py(err, warn)


# ---------------------------------------------------------------------------
# P1..P7: non-vacuous invariants (each vacuity-guarded)
# ---------------------------------------------------------------------------


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(
    boundary=_exact_boundary, keepout=_exact_keepout, clearance=_exact_clearance,
    zone=_exact_zone, total_wl=_wl, avg_len=_avg,
)
def test_placement_bounded_and_rich(boundary, keepout, clearance, zone, total_wl, avg_len):
    """P1 — 0 <= placement <= 100, and the mapping is rich: a constant
    kernel cannot stay in range while also separating the input classes
    (e.g. a constant 100.0 fails the violation side; a constant 0.0 fails
    the clean side).  Bounded to the constrained class (hv_lv = 0,
    boundary/keepout/zone ∈ {0,1}, clearance ∈ {0,1,2}) so varying the
    overlap count over {0..4} yields ≥ 2 distinct unclamped scores."""
    s = _place(4, boundary, 0, keepout, clearance, zone, total_wl, avg_len)
    assert 0.0 <= s <= 100.0
    outs = {
        _place(o, boundary, 0, keepout, clearance, zone, total_wl, avg_len)
        for o in (0, 1, 2, 3, 4)
    }
    assert len(outs) >= 2


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(
    overlap=_overlap, boundary=_boundary, hvlv=_hvlv, keepout=_keepout,
    clearance=_clearance, zone=_zone,
)
def test_placement_closed_form_no_wirelength(overlap, boundary, hvlv, keepout, clearance, zone):
    """P2 — closed form, bit-exact, with no wirelength penalty
    (total_wl = 0.0 skips the branch): placement ==
    max(0.0, min(100.0, 100 - 20o - 15b - 25h - 10k - 5(c-h) - 10z))
    with the same left-to-right op order.  A kernel that drops a penalty
    (e.g. ignore keepout) or mis-weights one fails."""
    expected = max(
        0.0,
        min(
            100.0,
            100.0
            - 20.0 * overlap
            - 15.0 * boundary
            - 25.0 * hvlv
            - 10.0 * keepout
            - 5.0 * (clearance - hvlv)
            - 10.0 * zone,
        ),
    )
    got = _place(overlap, boundary, hvlv, keepout, clearance, zone, 0.0, 0.0)
    assert got == expected, f"placement closed-form: rust={got!r} expected={expected!r}"


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(
    boundary=_exact_boundary, keepout=_exact_keepout, clearance=_exact_clearance,
    zone=_exact_zone, delta=st.integers(min_value=1, max_value=2),
)
def test_placement_overlap_penalty_translation_exact(boundary, keepout, clearance, zone, delta):
    """P3 — exact overlap-penalty translation on the constrained class
    (hv_lv = 0, total_wirelength = 0, base overlap = 0; both endpoints
    strictly inside (0, 100] so the clamp never engages): raising
    overlap_count by delta lowers the placement score by exactly 20*delta
    (bit-exact, Sterbenz-exact subtraction of small integers).  A kernel
    that mis-weights overlaps (e.g. 25 instead of 20) fails."""
    base = _place(0, boundary, 0, keepout, clearance, zone, 0.0, 0.0)
    shifted = _place(delta, boundary, 0, keepout, clearance, zone, 0.0, 0.0)
    assert 0.0 < shifted <= 100.0, f"translation endpoint left the domain: {shifted!r}"
    assert shifted == base - 20.0 * delta, (
        f"overlap translation: base={base!r} shifted={shifted!r} delta={delta}"
    )


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(avg_len=st.floats(min_value=50.0, max_value=150.0, allow_nan=False, allow_infinity=False))
def test_placement_wirelength_penalty_closed_form(avg_len):
    """P4 — wirelength penalty closed form, bit-exact, on the clean
    (zero-violation) domain: placement(0,..,0, wl>0, avg) ==
    100.0 - min(10, (avg - 50) / 10) for avg in [50, 150] (the penalty is
    < 10 so the clamp never engages, and the subtraction is exact).  A
    kernel that drops the wirelength branch (returns 100.0) or the
    min(10, ·) cap fails."""
    p = _place(0, 0, 0, 0, 0, 0, 1.0, avg_len)
    expected = 100.0 - min(10, (avg_len - 50.0) / 10.0)
    assert p == expected, f"wirelength closed-form: rust={p!r} expected={expected!r}"


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(
    err=st.integers(min_value=0, max_value=6),
    warn=st.integers(min_value=0, max_value=30),
)
def test_drc_closed_form_bit_exact(err, warn):
    """P5 — DRC closed form, bit-exact: drc_score ==
    max(0.0, min(100.0, 100 - 15e - 3w)).  A kernel that ignores warnings
    or mis-weights the error penalty fails."""
    expected = max(0.0, min(100.0, 100.0 - 15.0 * err - 3.0 * warn))
    got = _drc(err, warn)
    assert got == expected, f"drc closed-form: rust={got!r} expected={expected!r}"


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(warn=st.integers(min_value=0, max_value=4), delta=st.integers(min_value=1, max_value=5))
def test_drc_error_penalty_translation_exact(warn, delta):
    """P6 — exact DRC error-penalty translation on the constrained class
    (base error_count = 0, warn ∈ {0..4} so base ∈ [88, 100] and the worst
    shifted point 100 - 3*4 - 15*5 = 13 stays strictly positive): raising
    error_count by delta lowers the DRC score by exactly 15*delta
    (bit-exact; Sterbenz-exact subtraction in the unclamped domain).  A
    kernel with the wrong error weight (e.g. 10) fails."""
    base = _drc(0, warn)
    shifted = _drc(delta, warn)
    assert 0.0 < shifted <= 100.0, f"translation endpoint left the domain: {shifted!r}"
    assert shifted == base - 15.0 * delta, (
        f"drc translation: base={base!r} shifted={shifted!r} delta={delta}"
    )


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(score=_score_val)
def test_interpretation_thresholds_exact(score):
    """P7 — interpretation is exactly the threshold mapping
    >= 90 → 'excellent', >= 80 → 'good', >= 60 → 'ok', else 'poor' (the
    comparison is IEEE and the strings are the fixed vocabulary).  A
    kernel with shifted thresholds (e.g. >= 95) or an inverted mapping
    fails at the boundary pins below (tested explicitly on 59.999/60.0/
    79.999/80.0/89.999/90.0)."""
    if score >= 90.0:
        expected = "excellent"
    elif score >= 80.0:
        expected = "good"
    elif score >= 60.0:
        expected = "ok"
    else:
        expected = "poor"
    assert _tqo.interpret_score_py(score) == expected, f"score={score!r}"


def test_interpretation_boundary_pins():
    """Exact threshold boundary pins (bit-exact comparisons)."""
    assert _tqo.interpret_score_py(90.0) == "excellent"
    assert _tqo.interpret_score_py(89.999) == "good"
    assert _tqo.interpret_score_py(80.0) == "good"
    assert _tqo.interpret_score_py(79.999) == "ok"
    assert _tqo.interpret_score_py(60.0) == "ok"
    assert _tqo.interpret_score_py(59.999) == "poor"


# ---------------------------------------------------------------------------
# Metamorphic relations (>= 3 required; 4 provided)
# ---------------------------------------------------------------------------


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(
    boundary=_exact_boundary, keepout=_exact_keepout, clearance=_exact_clearance,
    zone=_exact_zone, k=st.integers(min_value=1, max_value=2),
)
def test_mr1_overlap_scale_linearity(boundary, keepout, clearance, zone, k):
    """M1 — bit-exact overlap-penalty linearity on the constrained class
    (hv_lv = 0, total_wirelength = 0, base overlap = 0; endpoints strictly
    inside (0, 100]): the score difference from k additional overlaps is
    exactly k times the difference from 1 additional overlap (both equal
    20k / 20 exactly; Sterbenz-exact subtraction).  A kernel whose
    overlap penalty is non-linear in the count fails."""
    base = _place(0, boundary, 0, keepout, clearance, zone, 0.0, 0.0)
    one = _place(1, boundary, 0, keepout, clearance, zone, 0.0, 0.0)
    kth = _place(k, boundary, 0, keepout, clearance, zone, 0.0, 0.0)
    assert base - one == 20.0
    assert base - kth == 20.0 * k


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(warn=st.integers(min_value=0, max_value=4), k=st.integers(min_value=1, max_value=5))
def test_mr2_drc_error_scale_linearity(warn, k):
    """M2 — bit-exact DRC error-penalty linearity on the constrained class
    (base error_count = 0, warn ∈ {0..4} so base ∈ [88, 100] and the worst
    shifted point 100 - 3*4 - 15*5 = 13 stays strictly positive): k
    additional errors lower the DRC score by exactly 15k (Sterbenz-exact
    in the unclamped domain).  A non-linear error penalty fails."""
    base = _drc(0, warn)
    kth = _drc(k, warn)
    assert 0.0 < kth <= 100.0, f"translation endpoint left the domain: {kth!r}"
    assert base - kth == 15.0 * k


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(
    ps=st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
    ds=st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
    rs=st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
)
def test_mr3_overall_weighted_sum_reconstruction(ps, ds, rs):
    """M3 — bit-exact overall reconstruction: without routing the overall
    is 0.5*ps + 0.5*ds; with routing it is 0.4*ps + 0.4*ds + 0.2*rs (the
    same left-to-right chains).  A kernel that mis-weights (e.g. 50/50
    even when routing is present) or drops the routing term fails."""
    assert _tqo.overall_score_py(ps, ds, None) == 0.5 * ps + 0.5 * ds
    assert _tqo.overall_score_py(ps, ds, rs) == 0.4 * ps + 0.4 * ds + 0.2 * rs


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(
    ps_a=st.floats(min_value=0.0, max_value=60.0, allow_nan=False, allow_infinity=False),
    ps_b=st.floats(min_value=60.0, max_value=100.0, allow_nan=False, allow_infinity=False),
    ds=st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
)
def test_mr4_overall_monotone_in_subscores(ps_a, ps_b, ds):
    """M4 — exact overall monotonicity: with ps_b >= ps_a (both finite),
    overall(ps_b, ds) >= overall(ps_a, ds) for fixed ds (both weighted
    chains are monotone in each subscore, and IEEE rounding is monotone —
    the comparison is exact).  A kernel whose overall decreases in the
    placement subscore fails."""
    lo = _tqo.overall_score_py(ps_a, ds, None)
    hi = _tqo.overall_score_py(ps_b, ds, None)
    assert hi >= lo


def test_pbt_smoke_deterministic_seed():
    """The PBT strategies are non-vacuous in aggregate: a quick seeded
    sweep over the property inputs must produce strictly more than one
    distinct placement score (guards against the whole suite silently
    degenerating to a single input class)."""
    rng = random.Random(0x0A11CE)
    distinct = {
        _place(
            rng.randint(0, 4), rng.randint(0, 1), 0,
            rng.randint(0, 1), rng.randint(0, 2), rng.randint(0, 1),
            rng.uniform(0.0, 1e4), rng.uniform(0.0, 200.0),
        )
        for _ in range(500)
    }
    assert len(distinct) > 20


# ---------------------------------------------------------------------------
# Vacuity mutants (G4 evidence pattern)
# ---------------------------------------------------------------------------


@pytest.fixture
def _restore_place():
    original = _tqo.placement_score_py
    yield
    _tqo.placement_score_py = original


@pytest.fixture
def _restore_drc():
    original = _tqo.drc_score_py
    yield
    _tqo.drc_score_py = original


@pytest.fixture
def _restore_overall():
    original = _tqo.overall_score_py
    yield
    _tqo.overall_score_py = original


@pytest.fixture
def _restore_interpret():
    original = _tqo.interpret_score_py
    yield
    _tqo.interpret_score_py = original


def test_p1_fails_for_constant_placement(_restore_place) -> None:
    """A constant placement kernel (always 100.0) breaks the richness arm
    of P1 (the violation inputs collapse)."""
    _tqo.placement_score_py = lambda *_a, **_k: 100.0
    with pytest.raises(AssertionError):
        test_placement_bounded_and_rich.hypothesis.inner_test(1, 1, 2, 1, 100.0, 60.0)


def test_p2_fails_for_missing_keepout_penalty(_restore_place) -> None:
    """A kernel that DROPS the keepout penalty (10/unit) breaks the P2
    closed form: the expected value subtracts 10*keepout but the kernel
    does not."""
    _tqo.placement_score_py = (
        lambda overlap, boundary, hvlv, keepout, clearance, zone, total_wl, avg_len: max(  # noqa: ARG005
            0.0,
            min(
                100.0,
                100.0
                - 20.0 * overlap
                - 15.0 * boundary
                - 25.0 * hvlv
                - 5.0 * (clearance - hvlv)
                - 10.0 * zone,
            ),
        )
    )
    with pytest.raises(AssertionError):
        test_placement_closed_form_no_wirelength.hypothesis.inner_test(1, 0, 0, 1, 0, 0)


def test_p3_fails_for_wrong_overlap_weight(_restore_place) -> None:
    """A kernel with the WRONG overlap weight (25 instead of 20) breaks
    the exact translation P3 (shifted != base - 20k)."""
    _tqo.placement_score_py = (
        lambda overlap, boundary, hvlv, keepout, clearance, zone, total_wl, avg_len: max(  # noqa: ARG005
            0.0,
            min(
                100.0,
                100.0
                - 25.0 * overlap
                - 15.0 * boundary
                - 25.0 * hvlv
                - 10.0 * keepout
                - 5.0 * (clearance - hvlv)
                - 10.0 * zone,
            ),
        )
    )
    with pytest.raises(AssertionError):
        test_placement_overlap_penalty_translation_exact.hypothesis.inner_test(1, 1, 2, 1, 1)


def test_p4_fails_for_missing_wirelength_penalty(_restore_place) -> None:
    """A kernel that DROPS the wirelength branch (always returns the
    violation-only score) breaks the P4 closed form."""
    _tqo.placement_score_py = lambda *_a, **_k: 100.0
    with pytest.raises(AssertionError):
        test_placement_wirelength_penalty_closed_form.hypothesis.inner_test(60.0)


def test_p5_fails_for_ignored_warnings(_restore_drc) -> None:
    """A DRC kernel that IGNORES warnings (warning weight 0) breaks the
    P5 closed form (expected subtracts 3*warn)."""
    _tqo.drc_score_py = lambda err, warn: max(0.0, min(100.0, 100.0 - 15.0 * err))  # noqa: ARG005
    with pytest.raises(AssertionError):
        test_drc_closed_form_bit_exact.hypothesis.inner_test(2, 5)


def test_p6_fails_for_wrong_drc_error_weight(_restore_drc) -> None:
    """A DRC kernel with the WRONG error weight (10 instead of 15) breaks
    the exact translation P6 (shifted != base - 15k)."""
    _tqo.drc_score_py = lambda err, warn: max(0.0, min(100.0, 100.0 - 10.0 * err - 3.0 * warn))
    with pytest.raises(AssertionError):
        test_drc_error_penalty_translation_exact.hypothesis.inner_test(2, 4)


def test_p7_fails_for_shifted_thresholds(_restore_interpret) -> None:
    """An interpretation kernel with SHIFTED thresholds (excellent at
    >= 95 instead of >= 90) breaks the boundary pins (90.0 reads 'good'
    under the mutant, but P7 and the explicit boundary pins demand
    'excellent')."""
    _tqo.interpret_score_py = (
        lambda s: "excellent"
        if s >= 95.0
        else ("good" if s >= 80.0 else ("ok" if s >= 60.0 else "poor"))
    )
    with pytest.raises(AssertionError):
        test_interpretation_thresholds_exact.hypothesis.inner_test(90.0)


def test_mr3_fails_for_wrong_routing_weight(_restore_overall) -> None:
    """An overall kernel that uses the no-routing 50/50 weights even when
    a routing score is present breaks M3's reconstruction (the routing
    term is dropped)."""
    _tqo.overall_score_py = lambda ps, ds, rs: 0.5 * ps + 0.5 * ds  # noqa: ARG005
    with pytest.raises(AssertionError):
        test_mr3_overall_weighted_sum_reconstruction.hypothesis.inner_test(50.0, 50.0, 100.0)
