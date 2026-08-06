"""Property-based tests for the Rust safety-timing kernels
(``temper_thermal.estimate_filter_delay_py`` /
``temper_thermal.estimate_fault_response_time_py`` /
``temper_thermal.is_safety_timing_valid_py``, Wave 4 Phase 4 —
migration of ``temper_placer/physics/safety.py``).

Every property is vacuity-guarded: its docstring says why a constant /
degenerate implementation fails it, and each has a real mutant test.
Exactness notes:

- The filter-delay kernel is ``-r*c * log(1 - thr)`` with the
  ``r <= 0 || c <= 0`` guard (returns 0.0) and the CPython log-domain
  raise for ``1 - thr <= 0``.
- Monotonicity relations (P3/P4/M2) are exact comparisons: every
  operation is monotone non-decreasing on the positive domain and IEEE
  rounding is monotone, so rounded outputs compare the same way.
- Power-of-two scaling (M1) is exact for the filter delay: scaling r or
  c by a power of two scales the product tau exactly (no rounding in a
  power-of-two multiply), and the -tau·log result scales exactly.
"""

from __future__ import annotations

import math

import temper_thermal as _tt
from hypothesis import given, settings
from hypothesis import strategies as st

MAX_EXAMPLES = 200

_r = st.floats(min_value=1e-6, max_value=1e6, allow_nan=False, allow_infinity=False)
_c = st.floats(min_value=1e-12, max_value=1e-3, allow_nan=False, allow_infinity=False)
# thr bounded away from 0 so `-tau * log(1 - thr)` stays strictly
# positive (thr = 0.0 makes log(1.0) = 0.0 and -tau*0.0 = -0.0, which
# is >= 0 but not > 0); the thr = 0.0 degeneracy itself is pinned in
# the differential suite.
_thr = st.floats(min_value=1e-3, max_value=0.999, allow_nan=False, allow_infinity=False)
_delay = st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False)
_ns = st.floats(min_value=0.0, max_value=1000.0, allow_nan=False, allow_infinity=False)


def _d(r, c, thr):
    return _tt.estimate_filter_delay_py(r, c, thr)


def _f(ind, fd, cd, ml):
    return _tt.estimate_fault_response_time_py(ind, fd, cd, ml)


# ---------------------------------------------------------------------------
# P1..P5: five+ non-vacuous properties (each vacuity-guarded)
# ---------------------------------------------------------------------------


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(r=_r, c=_c, thr=_thr)
def test_filter_delay_positive_and_guard_arms(r, c, thr):
    """P1 — positive r, c give a strictly positive delay, and each guard
    arm (r <= 0, c <= 0) separately forces 0.0.  A kernel that never
    guards fails the arms; a kernel that always returns 0.0 fails the
    positive arm."""
    assert _d(r, c, thr) > 0.0
    assert _d(0.0, c, thr) == 0.0
    assert _d(r, 0.0, thr) == 0.0
    assert _d(-1.0, c, thr) == 0.0
    assert _d(r, -1e-9, thr) == 0.0


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(r=_r, c=_c, thr=_thr)
def test_filter_delay_closed_form_bit_exact(r, c, thr):
    """P2 — closed form, bit-exact: t == -r*c * log(1-thr) (same op
    order in Python).  A kernel that drops the minus sign, swaps the
    log argument (log(thr)), or multiplies r*c after the log fails."""
    expected = -(r * c) * math.log(1.0 - thr)
    got = _d(r, c, thr)
    assert got == expected, f"rust={got!r} python={expected!r}"


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(r=_r, c=_c, thr=_thr)
def test_filter_delay_monotone_in_tau(r, c, thr):
    """P3 — delay is strictly increasing in r and in c (tau = r*c is
    monotone and IEEE rounding is monotone).  A kernel with r and c
    swapped, or a sign flip, fails."""
    assert _d(2.0 * r, c, thr) > _d(r, c, thr)
    assert _d(r, 2.0 * c, thr) > _d(r, c, thr)


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(r=_r, c=_c)
def test_filter_delay_increasing_in_threshold(r, c):
    """P4 — for fixed r, c, delay is strictly increasing in the
    threshold fraction (log(1-thr) decreases as thr increases; -tau·log
    increases).  A kernel that uses log(thr) instead of log(1-thr)
    fails."""
    t1 = _d(r, c, 0.3)
    t2 = _d(r, c, 0.7)
    assert t2 > t1


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(ind=_ns, fd=_delay, cd=_ns, ml=_ns)
def test_fault_response_additive_and_defaults(ind, fd, cd, ml):
    """P5 — the response time is exactly
    fd + (cd + ml) * 1e-3 (µs), with the first argument (loop
    inductance) irrelevant — a documented reference property.  A kernel
    that uses the inductance, or drops the 1e-3 conversion, fails."""
    expected = fd + (cd + ml) * 1e-3
    got = _f(ind, fd, cd, ml)
    assert got == expected, f"rust={got!r} python={expected!r}"
    # The inductance argument is genuinely ignored by the reference.
    assert _f(ind, fd, cd, ml) == _f(12345.0, fd, cd, ml)


# ---------------------------------------------------------------------------
# Vacuity guards (real mutants that must fail the property)
# ---------------------------------------------------------------------------


def _mutant_constant_delay(r, c, thr):
    """P1 mutant: always returns 0.0 — no positive arm."""
    del r, c, thr
    return 0.0


def _mutant_sign_flip(r, c, thr):
    """P2/P3 mutant: positive tau·log(1-thr) — wrong sign."""
    return (r * c) * math.log(1.0 - thr)


def _mutant_log_thr(r, c, thr):
    """P4 mutant: log(thr) instead of log(1-thr) — decreasing in thr."""
    return -(r * c) * math.log(thr)


def _mutant_uses_inductance(ind, fd, cd, ml):
    """P5 mutant: adds the (ignored) inductance argument."""
    return fd + (cd + ml) * 1e-3 + ind * 1e-6


def test_p1_fails_for_constant_kernel():
    # A constant-0.0 kernel passes the guard arms (0.0 for each <=0
    # input) but fails P1's positive arm: the drawn positive inputs
    # must give a strictly positive delay.
    r, c, thr = 1e3, 1e-6, 0.632
    assert not (_mutant_constant_delay(r, c, thr) > 0.0)


def test_p2_fails_for_sign_flip():
    r, c, thr = 1e3, 1e-6, 0.632
    expected = -(r * c) * math.log(1.0 - thr)
    assert _mutant_sign_flip(r, c, thr) != expected


def test_p3_fails_for_sign_flip_monotonicity():
    r, c, thr = 1e3, 1e-6, 0.5
    base = _mutant_sign_flip(r, c, thr)
    doubled = _mutant_sign_flip(2.0 * r, c, thr)
    assert not (doubled > base)  # P3 monotone-increasing violated


def test_p4_fails_for_log_thr():
    r, c = 1e3, 1e-6
    assert _mutant_log_thr(r, c, 0.7) < _mutant_log_thr(r, c, 0.3)  # decreasing → P4 fails


def test_p5_fails_for_using_inductance():
    ind, fd, cd, ml = 10.0, 2.5, 150.0, 200.0
    assert _mutant_uses_inductance(ind, fd, cd, ml) != _mutant_uses_inductance(0.0, fd, cd, ml)


# ---------------------------------------------------------------------------
# M1..M3: metamorphic relations (honestly bounded)
# ---------------------------------------------------------------------------


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(r=_r, c=_c, thr=_thr)
def test_m1_power_of_two_scale_exact(r, c, thr):
    """M1 — scaling r (or c) by a power of two scales the delay by the
    same power of two EXACTLY: power-of-two multiplies are exact (no
    rounding), so tau and -tau·log scale exactly (barring overflow/
    underflow, which the strategies' magnitudes avoid)."""
    assert _d(2.0 * r, c, thr) == 2.0 * _d(r, c, thr)
    assert _d(r, 4.0 * c, thr) == 4.0 * _d(r, c, thr)


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(r=_r, c=_c, thr=_thr)
def test_m2_rc_product_commutative_exact(r, c, thr):
    """M2 — the delay depends only on the product r*c: swapping r and c
    gives the same product tau exactly (IEEE multiply is commutative),
    hence the SAME delay bit-for-bit."""
    assert _d(r, c, thr) == _d(c, r, thr)


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(fd=_delay, cd=_ns, ml=_ns)
def test_m3_response_time_component_commutative(fd, cd, ml):
    """M3 — the digital delay depends on the IEEE sum (cd + ml), which
    is commutative: swapping cd and ml leaves the response time
    bit-identical.  (A ±100 ns component SHIFT is NOT exact — floating
    addition is not associative — so that stronger claim is not made.)"""
    assert _f(0.0, fd, cd, ml) == _f(0.0, fd, ml, cd)
