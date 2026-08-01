"""Property-based tests for the Rust routing-quality composite score
(``temper_quality_oracle.routing_quality_score_py``, Wave 4 Phase A #1).

The kernel backs ``temper_placer/metrics/routing_quality.py``'s composite
0-100 score: 60% completion, 20% DRC (all-or-nothing), 20% via-density
efficiency (clamped).  It is pure closed-form f64 arithmetic — no
recursion, no iteration — so every property below is a direct statement
about correctly-rounded IEEE-754 operations, and each one is
vacuity-guarded (its docstring says why a constant / degenerate
implementation fails it).

Exactness notes:

- ``completion * 60`` (CPython float × int) and ``completion * 60.0``
  (Rust) are the same correctly-rounded f64 multiply.
- ``vias / net_count`` (CPython int true-division) and
  ``vias as f64 / net_count as f64`` (Rust) are the same correctly-rounded
  f64 divide — so the efficiency term depends only on the *real* ratio,
  which is what makes the ratio-scale metamorphic relation M1 bit-exact.
- The clamp: CPython ``max(0.0, min(1.0, x))`` and Rust
  ``x.min(1.0).max(0.0)`` agree on every input, including non-finite ones
  (CPython's comparison-based ``min``/``max`` keep the first non-NaN
  operand, and Rust's ``f64::min``/``max`` ignore NaN the same way) —
  NaN inputs are excluded from the strategies anyway.
- Op order is pinned: ``(completion_score + drc_score) + efficiency_score``
  left-to-right in both implementations (the differential suite asserts
  bit-identical output).
- The [0, 100] bound (P2) holds **only** for completion ∈ [0, 1] — the
  kernel deliberately does not clamp completion; the property is bounded
  to that domain and says so.
"""

from __future__ import annotations

import random

import pytest
import temper_quality_oracle as _tqo
from hypothesis import given, settings
from hypothesis import strategies as st

from temper_placer.metrics.routing_quality import evaluate_routing_quality

MAX_EXAMPLES = 200

# Completion is a routing fraction, [0, 1]. NaN/inf are excluded — the
# kernel is defined for finite inputs (see module docstring for the
# non-finite agreement note anyway).
_completion = st.floats(
    min_value=0.0,
    max_value=1.0,
    allow_nan=False,
    allow_infinity=False,
)
_vias = st.integers(min_value=0, max_value=1000)
_drc = st.integers(min_value=0, max_value=20)
_nets = st.integers(min_value=0, max_value=200)


def _score(completion, vias, drc, net_count):
    return _tqo.routing_quality_score_py(completion, vias, drc, net_count)


# ---------------------------------------------------------------------------
# 5 invariants (each vacuity-guarded)
# ---------------------------------------------------------------------------


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(completion=_completion, vias=_vias, drc=_drc, nets=_nets)
def test_score_range_richness(completion, vias, drc, nets):
    """P1 — the mapping covers a rich output range (a constant fails)."""
    outputs = {
        _score(c, vias, drc, nets)
        for c in (0.0, 0.25, 0.5, 0.75, 1.0)
    }
    outputs |= {
        _score(completion, v, drc, nets)
        for v in (0, 1, 2, 4, 10, 20, 100)
    }
    # At minimum the five completion levels alone must already separate.
    assert len(outputs) >= 5


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(completion=_completion, vias=_vias, drc=_drc, nets=_nets)
def test_score_bounded_0_100(completion, vias, drc, nets):
    """P2 — 0 <= score <= 100 for completion in [0, 1] (honestly bounded:
    the kernel does not clamp completion, so outside [0, 1] the bound does
    not hold; inside it, completion*60 ∈ [0, 60], drc ∈ {0, 20}, and the
    clamped efficiency ∈ [0, 20], so the sum ∈ [0, 100]).  A constant 0
    fails the completion=1.0 side; a constant 100 fails the completion=0
    / drc>0 side."""
    s = _score(completion, vias, drc, nets)
    assert 0.0 <= s <= 100.0


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(completion=_completion, vias=_vias, drc=_drc, nets=_nets,
       delta=st.floats(min_value=0.0, max_value=1.0, allow_nan=False,
                       allow_infinity=False))
def test_score_monotone_in_completion(completion, vias, drc, nets, delta):
    """P3 — non-decreasing in completion for fixed (vias, drc, nets):
    raising the completion rate never lowers the score (f64 multiply by
    the positive constant 60.0 is monotone, and the other two terms are
    completion-independent).  A constant fails the c2 > c1 direction
    (P1 already proves strict variation exists)."""
    c1 = min(completion, 1.0 - delta)
    c2 = c1 + delta
    s1 = _score(c1, vias, drc, nets)
    s2 = _score(c2, vias, drc, nets)
    assert s2 >= s1


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(completion=_completion, vias=_vias, nets=_nets)
def test_drc_all_or_nothing_step(completion, vias, nets):
    """P4 — DRC is all-or-nothing: drc == 0 earns exactly the 20.0 DRC
    points that drc >= 1 earns nothing for.  The *difference* is not
    bit-exact — the +20.0 / +0.0 intermediate sums round differently
    (error is a few ulps, ~3e-14 at these magnitudes) — so this is
    asserted at the repo's 1e-12-relative non-exact-metamorphosis
    convention (cf. test_domain_clearance_dist_rust_pbt.py M2); the
    bit-exact contract lives in the differential suite.  A constant
    fails (0 != 20) and a proportional drc penalty fails (step != 20)."""
    assert abs(
        _score(completion, vias, 0, nets) - _score(completion, vias, 1, nets) - 20.0
    ) <= 1e-12 * 20.0
    assert abs(
        _score(completion, vias, 0, nets) - _score(completion, vias, 20, nets) - 20.0
    ) <= 1e-12 * 20.0


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(completion=_completion, drc=_drc,
       nets=st.integers(min_value=1, max_value=200))
def test_efficiency_clamp_boundaries_bit_exact(completion, drc, nets):
    """P5 — the efficiency clamp is exactly 20.0 at <= 2 vias/net and
    exactly 0.0 at >= 10 vias/net (bit-exact closed forms, not
    inequalities): 2n/n and 10n/n divide exactly, so the penalty is
    exactly 0.0 / 1.0 and the score collapses to 60*completion + drc_part
    + {20.0 | 0.0}.  A constant fails; the boundary POSITIONS are pinned
    by the shifted-boundary mutant in the vacuity section below (an
    unclamped linear penalty coincides with the clamped value at these
    exact test points, so it is not a discriminating mutant)."""
    drc_part = 20.0 if drc == 0 else 0.0
    low = _score(completion, 2 * nets, drc, nets)
    assert low == 60.0 * completion + drc_part + 20.0
    high = _score(completion, 10 * nets, drc, nets)
    assert high == 60.0 * completion + drc_part + 0.0
    # Zero nets: efficiency is pinned to 20.0 regardless of vias.
    assert _score(completion, 0, drc, 0) == 60.0 * completion + drc_part + 20.0
    assert _score(completion, 1000, drc, 0) == 60.0 * completion + drc_part + 20.0


# ---------------------------------------------------------------------------
# Metamorphic relations (>= 3 required)
# ---------------------------------------------------------------------------


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(completion=_completion, vias=_vias, drc=_drc,
       nets=st.integers(min_value=1, max_value=100),
       scale=st.integers(min_value=2, max_value=50))
def test_mr1_ratio_scale_invariance(completion, vias, drc, nets, scale):
    """M1 — bit-exact ratio-scale invariance: scaling vias and nets by the
    same integer factor k leaves the score unchanged.  (k*vias)/(k*nets)
    has the same real quotient as vias/nets and correctly-rounded division
    depends only on that real quotient, so the efficiency term — and the
    whole score — is bit-identical."""
    assert _score(completion, scale * vias, drc, scale * nets) == _score(
        completion, vias, drc, nets
    )


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(completion=_completion, vias_a=_vias, vias_b=_vias, drc=_drc)
def test_mr2_zero_net_vias_irrelevance(completion, vias_a, vias_b, drc):
    """M2 — bit-exact vias irrelevance at net_count == 0: with no nets to
    judge, the via count cannot influence the score (the kernel guards the
    ratio behind net_count > 0 and pins efficiency to 20.0)."""
    assert _score(completion, vias_a, drc, 0) == _score(completion, vias_b, drc, 0)


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(completion=_completion, drc=_drc,
       nets=st.integers(min_value=1, max_value=200),
       extra=st.integers(min_value=1, max_value=1000))
def test_mr3_vias_monotone_non_increasing(completion, drc, nets, extra):
    """M3 — non-increasing in vias for fixed (completion, drc, nets):
    more vias per net never raises the score.  (Correctly-rounded division
    by a positive constant is monotone, and the penalty chain
    (x-2)/8 → clamp → 1-x → *20 is monotone non-increasing in x.)"""
    s_low = _score(completion, 0, drc, nets)
    s_high = _score(completion, extra, drc, nets)
    assert s_high <= s_low
    if extra >= 10 * nets:
        # Efficiency pinned to the floor: the extra-vias score equals the
        # completion+drc floor exactly (see P5 upper clamp).
        drc_part = 20.0 if drc == 0 else 0.0
        assert s_high == 60.0 * completion + drc_part


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(completion=_completion, drc=_drc)
def test_mr4_acceptability_flip(completion, drc):
    """M4 — module-level metamorphic relation on the delegation wrapper:
    the acceptability flag is exactly (completion >= 0.8 and drc == 0), so
    crossing 0.8 with drc == 0 flips is_acceptable False → True while
    score changes by exactly 60*delta; with drc >= 1 the flag stays False
    no matter how high completion goes."""
    class _R:
        pass

    def result(c, e):
        r, d = _R(), _R()
        r.completion_rate = c
        r.total_vias = 0
        r.total_wirelength = 0.0
        r.routed_nets = ["N1"]
        r.failed_nets = ["N2"]
        d.error_count = e
        return r, d

    below = evaluate_routing_quality(*result(0.79, drc))
    above = evaluate_routing_quality(*result(0.81, drc))
    assert below.is_acceptable is False
    assert above.is_acceptable == (drc == 0)
    if drc == 0:
        # The score moves by 60 * 0.02 — up to rounding: 0.79/0.81 are
        # not exactly representable and the +40 additions round, so this
        # relation is asserted with a tight tolerance, not bit-exact (the
        # bit-exact contract lives in the differential suite; the PBT
        # convention tolerates bounded non-exact metamorphoses — cf.
        # test_domain_clearance_dist_rust_pbt.py M2).
        delta = above.score - below.score
        assert abs(delta - 60.0 * 0.02) <= 1e-12 * 1.2


def test_pbt_smoke_deterministic_seed():
    """The PBT strategies are non-vacuous in aggregate: a quick seeded
    sweep over the property inputs must produce strictly more than one
    distinct score (guards against the whole suite silently degenerating
    to a single input class)."""
    rng = random.Random(0x5EED)
    distinct = {
        _score(rng.uniform(0.0, 1.0), rng.randint(0, 1000),
               rng.randint(0, 20), rng.randint(0, 200))
        for _ in range(500)
    }
    assert len(distinct) > 100


# ---------------------------------------------------------------------------
# Vacuity mutants (G4 evidence pattern, cf. test_bottleneck_geometry_pbt.py)
# ---------------------------------------------------------------------------


@pytest.fixture
def restore_kernel():
    original = _tqo.routing_quality_score_py
    yield
    _tqo.routing_quality_score_py = original


def test_p1_fails_for_constant_score(restore_kernel) -> None:
    """A constant kernel cannot cover a rich output range (P1)."""
    _tqo.routing_quality_score_py = lambda *_a, **_k: 50.0
    with pytest.raises(AssertionError):
        test_score_range_richness.hypothesis.inner_test(0.5, 4, 0, 10)


def test_p3_fails_for_decreasing_kernel(restore_kernel) -> None:
    """A kernel that DECREASES in completion breaks P3's monotonicity
    (a constant is trivially monotone, so it is not the discriminating
    mutant here — P1 covers constants)."""
    _tqo.routing_quality_score_py = lambda completion, vias, drc, nets: (
        60.0 * (1.0 - completion)
        + (20.0 if drc == 0 else 0.0)
        + (20.0 * (1.0 - max(0.0, min(1.0, (vias / nets - 2.0) / 8.0))) if nets > 0 else 20.0)
    )
    with pytest.raises(AssertionError):
        test_score_monotone_in_completion.hypothesis.inner_test(0.5, 4, 0, 10, 0.1)


def test_p4_fails_for_proportional_drc_penalty(restore_kernel) -> None:
    """A kernel that scales DRC points with the error count (e.g. 20 - drc)
    breaks the all-or-nothing step (P4): drc 0 vs drc 1 differ by less than
    the full 20.0."""
    _tqo.routing_quality_score_py = lambda completion, drc, *_rest: (
        60.0 * completion + (20.0 - drc if drc <= 20 else 0.0)
    )
    with pytest.raises(AssertionError):
        test_drc_all_or_nothing_step.hypothesis.inner_test(0.5, 4, 10)


def test_p5_fails_for_shifted_clamp_boundary(restore_kernel) -> None:
    """A kernel whose clamp boundary is shifted (penalty clamps only at
    (x - 4)/8 instead of (x - 2)/8) breaks P5: at exactly 10 vias/net the
    penalty is 0.75, not 1.0, so the high-side closed form fails. (An
    unclamped linear penalty would NOT fail P5 — at its only test points,
    2 and 10 vias/net, the unclamped value coincides with the clamped
    value; the boundary positions are what P5 pins.)"""
    _tqo.routing_quality_score_py = lambda completion, vias, drc, nets: (
        60.0 * completion
        + (20.0 if drc == 0 else 0.0)
        + (20.0 * (1.0 - max(0.0, min(1.0, (vias / nets - 4.0) / 8.0))) if nets > 0 else 20.0)
    )
    with pytest.raises(AssertionError):
        test_efficiency_clamp_boundaries_bit_exact.hypothesis.inner_test(0.5, 0, 10)


def test_p2_fails_for_out_of_bounds_score(restore_kernel) -> None:
    """A kernel that can exceed 100 (e.g. a buggy unclamped efficiency
    boost) breaks the bounded property (P2)."""
    _tqo.routing_quality_score_py = lambda *_a, **_k: 150.0
    with pytest.raises(AssertionError):
        test_score_bounded_0_100.hypothesis.inner_test(0.5, 4, 0, 10)
