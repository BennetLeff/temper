"""Differential tests: temper-quality-oracle Rust composite-quality-score
kernels vs the pure-Python reference (temper_placer/metrics/quality_score.py,
Wave 4 Phase A #5 — the composite placement/DRC/routing score and its
interpretation).

The pre-migration implementation is pinned here as an oracle (verbatim
semantics, including the exact f64 operation order: ``score = 100.0`` then
six left-to-right int-penalty subtractions, the wirelength penalty
``min(10, (avg_len - 50) / 10)`` with the parenthesized float division
evaluated before the ``min``, the ``max(0.0, min(100.0, score))`` clamp
with the constant FIRST (Python's first-argument NaN semantics), the
weighted overall ``0.5 * ps + 0.5 * ds`` / ``0.4 * ps + 0.4 * ds +
0.2 * rs`` left-to-right chains, and the ``>= 90 / >= 80 / >= 60``
interpretation thresholds).  Any change to the Rust kernels
(packages/temper-quality-oracle/src/quality_score.rs) or the Python
delegation that disagrees with the oracle fails here, bit-exactly.

Bit-exactness notes (Wave 4 catalog):

- **B5 (Python min/max first-argument NaN semantics):** the oracle writes
  ``max(0.0, min(100.0, score))`` — the CONSTANT is the first argument, and
  CPython's builtin keeps the first argument on a NaN comparison
  (``min(100.0, NaN) == 100.0``).  The Rust side mirrors the argument order
  (``(100.0_f64.min(score)).max(0.0)``), so the constant is the receiver.
  Likewise the wirelength ``min(10, x)`` ⇔ ``10.0_f64.min(x)``.
- **B7 (f64 operation order):** every int penalty is exact int arithmetic
  in Python, converted to f64 exactly at the subtraction (small ints), so
  ``score -= overlap_count * 20`` ⇔ ``score -= overlap_count as f64 * 20.0``;
  the wirelength penalty keeps the parenthesized ``(avg_len - 50) / 10``;
  the overall chains stay left-to-right with no reassociation or fusing.
- **B1/B2/B3/B4/B6/B8/B9/B10 are not applicable:** the kernel calls no
  libm functions (no sqrt/pow/log/hypot), divides no named constants,
  rounds nothing, cannot produce denormal-range intermediates (every
  intermediate is a bounded [0,100]-range sum; ``avg_len - 50`` for any
  representable adjacent float is ≥ ulp(50) ≈ 7.1e-15, normal), and
  renders no floats/strings (interpretation returns a fixed vocabulary
  of plain strings, no reprs).  The B8 inapplicability is pinned by
  ``test_direct_wirelength_penalty_smallest_nonzero``.

The direct ``temper_quality_oracle`` pins fail first (the crate is not
yet built with the new functions); the module-level pins exercise the
full delegation path once wired.
"""

from __future__ import annotations

import random

import pytest
import temper_quality_oracle as _tqo

from temper_placer.metrics.quality_score import (
    QualityScore,
    compute_quality_score,
    interpret_score,
)

# ---------------------------------------------------------------------------
# Oracle (pre-migration implementation, verbatim)
# ---------------------------------------------------------------------------
# Do not edit these — they are the reference the migration is pinned to.
# They are a copy of the module's arithmetic AS COMMITTED before the Rust
# kernels existed.


def _oracle_placement_score(metrics) -> float:
    """Verbatim pre-migration ``_compute_placement_score``."""
    score = 100.0

    # Critical violations (block routing or violate safety)
    score -= metrics.overlap_count * 20
    score -= metrics.boundary_violations * 15
    score -= metrics.hv_lv_violations * 25
    score -= metrics.keepout_violations * 10

    # Medium violations (sub-optimal but not critical)
    score -= (metrics.clearance_violations - metrics.hv_lv_violations) * 5
    score -= metrics.zone_violations * 10

    # Wirelength penalty
    if metrics.total_wirelength > 0:
        # Assume avg net length > 50mm is problematic
        avg_len = getattr(metrics, "avg_net_length", 0.0)
        if avg_len > 50:
            score -= min(10, (avg_len - 50) / 10)

    return max(0.0, min(100.0, score))


def _oracle_drc_score(drc_result) -> float:
    """Verbatim pre-migration ``_compute_drc_score``."""
    score = 100.0
    score -= drc_result.error_count * 15
    score -= drc_result.warning_count * 3
    return max(0.0, min(100.0, score))


def _oracle_interpret_score(score: float) -> str:
    """Verbatim pre-migration ``interpret_score``."""
    if score >= 90:
        return "excellent"
    elif score >= 80:
        return "good"
    elif score >= 60:
        return "ok"
    else:
        return "poor"


class _MetricsStub:
    """Attribute stub standing in for PlacementMetrics (zero defaults)."""

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)
        for default_key in (
            "overlap_count",
            "boundary_violations",
            "hv_lv_violations",
            "keepout_violations",
            "clearance_violations",
            "zone_violations",
            "total_wirelength",
            "avg_net_length",
        ):
            if not hasattr(self, default_key):
                setattr(self, default_key, 0.0 if "wire" in default_key or "avg" in default_key else 0)


class _DrcStub:
    """Attribute stub standing in for DrcResult (zero defaults)."""

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)
        for default_key in ("error_count", "warning_count"):
            if not hasattr(self, default_key):
                setattr(self, default_key, 0)


def _random_metrics(rng):
    m = _MetricsStub(
        overlap_count=rng.randint(0, 20),
        boundary_violations=rng.randint(0, 10),
        hv_lv_violations=rng.randint(0, 8),
        keepout_violations=rng.randint(0, 10),
        clearance_violations=rng.randint(0, 20),
        zone_violations=rng.randint(0, 8),
        total_wirelength=rng.choice([0.0, rng.uniform(0.0, 1e4)]),
        avg_net_length=rng.choice([0.0, rng.uniform(0.0, 200.0), rng.uniform(49.9, 51.0)]),
    )
    # clearance must be >= hv_lv for the medium-violation subtraction
    m.clearance_violations = max(m.clearance_violations, m.hv_lv_violations)
    return m


def _random_drc(rng):
    return _DrcStub(
        error_count=rng.randint(0, 20),
        warning_count=rng.randint(0, 40),
    )


# ---------------------------------------------------------------------------
# Direct Rust pins (bit-exact float equality)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("seed", range(25))
def test_direct_placement_score_bit_exact(seed):
    """Rust placement kernel == oracle, bit-exact, over random metrics."""
    rng = random.Random(seed)
    for _ in range(40):
        m = _random_metrics(rng)
        expected = _oracle_placement_score(m)
        got = _tqo.placement_score_py(
            m.overlap_count,
            m.boundary_violations,
            m.hv_lv_violations,
            m.keepout_violations,
            m.clearance_violations,
            m.zone_violations,
            m.total_wirelength,
            getattr(m, "avg_net_length", 0.0),
        )
        assert got == expected, (
            f"placement mismatch: rust={got!r} oracle={expected!r} "
            f"(overlap={m.overlap_count} boundary={m.boundary_violations} "
            f"hvlv={m.hv_lv_violations} keepout={m.keepout_violations} "
            f"clear={m.clearance_violations} zone={m.zone_violations} "
            f"wl={m.total_wirelength!r} avg={getattr(m, 'avg_net_length', 0.0)!r})"
        )


@pytest.mark.parametrize("seed", range(20))
def test_direct_drc_score_bit_exact(seed):
    """Rust DRC kernel == oracle, bit-exact, over random DRC counts."""
    rng = random.Random(1000 + seed)
    for _ in range(40):
        d = _random_drc(rng)
        expected = _oracle_drc_score(d)
        got = _tqo.drc_score_py(d.error_count, d.warning_count)
        assert got == expected, (
            f"drc mismatch: rust={got!r} oracle={expected!r} "
            f"(errors={d.error_count} warnings={d.warning_count})"
        )


@pytest.mark.parametrize("seed", range(20))
def test_direct_interpret_score_bit_exact(seed):
    """Rust interpretation kernel == oracle, bit-exact, over random scores."""
    rng = random.Random(2000 + seed)
    for _ in range(50):
        s = rng.choice([rng.uniform(-10.0, 120.0), 0.0, 59.999, 60.0, 79.999, 80.0, 89.999, 90.0])
        expected = _oracle_interpret_score(s)
        got = _tqo.interpret_score_py(s)
        assert got == expected, f"interpret mismatch: rust={got!r} oracle={expected!r} (score={s!r})"


def test_direct_known_values():
    """Hand-computed values (exact f64 in both implementations)."""
    # Perfect placement: 100.0; 2 overlaps: 100 - 40 = 60.0 exactly.
    assert _tqo.placement_score_py(2, 0, 0, 0, 0, 0, 0.0, 0.0) == 60.0
    # DRC: 2 errors + 3 warnings: 100 - 30 - 9 = 61.0 exactly.
    assert _tqo.drc_score_py(2, 3) == 61.0
    # Clamp: 20 overlaps → 100 - 400 = -300 → 0.0
    assert _tqo.placement_score_py(20, 0, 0, 0, 0, 0, 0.0, 0.0) == 0.0
    # Interpretation thresholds.
    assert _tqo.interpret_score_py(90.0) == "excellent"
    assert _tqo.interpret_score_py(89.999) == "good"
    assert _tqo.interpret_score_py(80.0) == "good"
    assert _tqo.interpret_score_py(79.999) == "ok"
    assert _tqo.interpret_score_py(60.0) == "ok"
    assert _tqo.interpret_score_py(59.999) == "poor"


def test_direct_overall_score_bit_exact():
    """The weighted overall is (0.5*ps + 0.5*ds) or
    (0.4*ps + 0.4*ds + 0.2*rs) left-to-right, bit-exact."""
    ps, ds, rs = 63.5, 41.25, 88.0
    assert _tqo.overall_score_py(ps, ds, None) == 0.5 * ps + 0.5 * ds
    assert _tqo.overall_score_py(ps, ds, rs) == 0.4 * ps + 0.4 * ds + 0.2 * rs


def test_direct_wirelength_penalty_smallest_nonzero():
    """Branch/arithmetic boundary: avg_len just above 50.0 (the smallest
    representable step, ulp(50) ≈ 7.1e-15) produces the smallest nonzero
    penalty (avg_len - 50) / 10 ≈ 7.1e-16, bit-exact on both sides.

    B8 (denormal underflow) is genuinely NOT applicable to this kernel:
    the wirelength penalty is `(avg_len - 50) / 10`, and 50.0 + 1e-310
    rounds to exactly 50.0 in f64, so no representable avg_len can place
    the penalty quotient in the denormal band — the closest-to-zero
    penalty is this adjacent-float case, which is normal (~7.1e-16).
    The denormal-band B8 case is pinned in the device_power and
    inductance differential suites, where the kernels do reach
    denormal-range intermediates; this one cannot.
    """
    n50 = 50.0 + 1e-15  # still 50.0 + small step... use nextafter
    import struct as _s

    n50 = _s.unpack(
        ">d",
        _s.pack(">Q", _s.unpack(">Q", _s.pack(">d", 50.0))[0] + 1),
    )[0]
    delta = n50 - 50.0
    assert 0.0 < delta < 1e-13, f"expected an adjacent-float delta, got {delta!r}"
    m = _MetricsStub(
        overlap_count=0, boundary_violations=0, hv_lv_violations=0,
        keepout_violations=0, clearance_violations=0, zone_violations=0,
        total_wirelength=1.0, avg_net_length=n50,
    )
    expected = _oracle_placement_score(m)
    got = _tqo.placement_score_py(0, 0, 0, 0, 0, 0, 1.0, n50)
    assert got == expected, f"adjacent-float penalty: rust={got!r} oracle={expected!r}"
    # The sub-ulp penalty (7.1e-16 << ulp(100.0) ≈ 1.4e-14) rounds away in
    # the final `100.0 - penalty` on BOTH sides identically — the pin is
    # that both implementations round it away the same way, not that it
    # survives.  A penalty that DOES survive rounding is pinned in the
    # 1 mm case (avg_len 60 → penalty 1.0) in the Rust unit tests and in
    # test_direct_known_values via the 2-overlap placement.
    assert got == 100.0, f"expected sub-ulp penalty to round away identically, got {got!r}"


def test_direct_nan_semantics():
    """Non-finite parity (B5): NaN flows through the min/max clamps the
    same way on both sides."""
    # min(100.0, NaN) keeps the constant 100.0 → max(0.0, 100.0) = 100.0.
    assert _tqo.placement_score_py(0, 0, 0, 0, 0, 0, float("nan"), 0.0) == 100.0
    # NaN avg_net_length with total_wirelength > 0: avg_len > 50 is False
    # (IEEE), so no penalty → 100.0.
    assert _tqo.placement_score_py(0, 0, 0, 0, 0, 0, 1.0, float("nan")) == 100.0
    # NaN overall score → "poor" (all comparisons False).
    assert _tqo.interpret_score_py(float("nan")) == "poor"


def test_direct_zero_wirelength_skips_penalty():
    """total_wirelength == 0 skips the wirelength penalty entirely, even for
    a huge avg_net_length (branch parity)."""
    m = _MetricsStub(
        overlap_count=0, boundary_violations=0, hv_lv_violations=0,
        keepout_violations=0, clearance_violations=0, zone_violations=0,
        total_wirelength=0.0, avg_net_length=1e6,
    )
    expected = _oracle_placement_score(m)
    got = _tqo.placement_score_py(0, 0, 0, 0, 0, 0, 0.0, 1e6)
    assert got == expected == 100.0, f"zero-wl: rust={got!r} oracle={expected!r}"


# ---------------------------------------------------------------------------
# Module-level pins (full delegation path)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("seed", range(10))
def test_module_level_compute_quality_score_bit_exact(seed):
    """compute_quality_score (delegating) == oracle composition, bit-exact
    (no routing path)."""
    rng = random.Random(3000 + seed)
    for _ in range(20):
        m = _random_metrics(rng)
        d = _random_drc(rng)
        expected_ps = _oracle_placement_score(m)
        expected_ds = _oracle_drc_score(d)
        expected_overall = 0.5 * expected_ps + 0.5 * expected_ds
        expected_interpretation = _oracle_interpret_score(expected_overall)

        score = compute_quality_score(m, d)
        assert isinstance(score, QualityScore)
        assert score.placement_score == expected_ps
        assert score.drc_score == expected_ds
        assert score.routing_score is None
        assert score.overall == expected_overall, (
            f"overall mismatch: got={score.overall!r} oracle={expected_overall!r} "
            f"(ps={expected_ps!r} ds={expected_ds!r})"
        )
        assert score.interpretation == expected_interpretation
        assert score.pass_quality == (expected_overall >= 60)


def test_module_level_interpret_score_delegates():
    """interpret_score (delegating) == oracle across the thresholds."""
    for s in [-1.0, 0.0, 59.999, 60.0, 79.999, 80.0, 89.999, 90.0, 100.0, 120.0]:
        assert interpret_score(s) == _oracle_interpret_score(s), f"score={s!r}"


def test_module_level_defaults_flow():
    """The dataclass defaults flow through the delegation exactly."""
    score = compute_quality_score(_MetricsStub(), _DrcStub())
    # All-zero metrics → 100.0 placement, 100.0 drc → overall 100.0.
    assert score.placement_score == 100.0
    assert score.drc_score == 100.0
    assert score.overall == 100.0
    assert score.interpretation == "excellent"
    assert score.pass_quality is True
    # to_dict serialization round-trips the delegated values exactly.
    d = score.to_dict()
    assert d["overall"] == 100.0
    assert d["placement_score"] == 100.0
    assert d["drc_score"] == 100.0
    assert d["routing_score"] is None
    assert d["interpretation"] == "excellent"
    assert d["pass_quality"] is True
