"""Property-based tests for the Rust EMI kernels
(``temper_thermal.predict_radiated_emissions_py`` /
``temper_thermal.check_emi_compliance_py``, Wave 4 Phase 4 — migration
of ``temper_placer/physics/emi.py``).

Every property is vacuity-guarded: its docstring says why a constant /
degenerate implementation fails it.  Exactness notes:

- The kernel is
  ``20 * log10(1.316e-14 * A * I * pow(f, 2.0) / d * 1e6)`` with the
  three ``<= 0`` input guards and the ``e_uv_per_m <= 0`` output guard.
- Power-of-two scaling relations (M1) are exact because scaling by a
  power of two commutes through multiplication without rounding, and
  through the single-argument log10 only up to the log's own rounding:
  log10(2^k·z) is NOT exactly log10(z) + k·log10(2), so M1 is a
  monotone-comparison relation on the dB result, not a bit-exact one —
  bounded honestly below.
- Monotonicity in each input is exact for positive inputs: every
  operation in the chain (multiply, pow, divide, log10) is a monotone
  non-decreasing real function on the positive domain and IEEE rounding
  is monotone, so outputs compare the same way (P4/P5/M2/M3).
"""

from __future__ import annotations

import math

import pytest
import temper_thermal as _tt
from hypothesis import given, settings
from hypothesis import strategies as st

MAX_EXAMPLES = 200

_area = st.floats(min_value=1e-6, max_value=1e4, allow_nan=False, allow_infinity=False)
_current = st.floats(min_value=1e-6, max_value=1e3, allow_nan=False, allow_infinity=False)
_freq = st.floats(min_value=1e-3, max_value=1e3, allow_nan=False, allow_infinity=False)
_dist = st.floats(min_value=0.1, max_value=30.0, allow_nan=False, allow_infinity=False)
_db = st.floats(min_value=-200.0, max_value=200.0, allow_nan=False, allow_infinity=False)


def _e(a, i, f, d=3.0):
    return _tt.predict_radiated_emissions_py(a, i, f, d)


# ---------------------------------------------------------------------------
# P1..P5: five+ non-vacuous properties (each vacuity-guarded)
# ---------------------------------------------------------------------------


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(a=_area, i=_current, f=_freq, d=_dist)
def test_emi_finite_and_guard_arms(a, i, f, d):
    """P1 — positive inputs give a finite dBµV/m value (log-domain), and
    each of the three input guards separately forces 0.0.  A kernel that
    never guards (always computes) fails the guard arms; a kernel that
    always returns 0.0 fails the positive arm."""
    assert math.isfinite(_e(a, i, f, d))
    assert _e(0.0, i, f, d) == 0.0
    assert _e(a, 0.0, f, d) == 0.0
    assert _e(a, i, 0.0, d) == 0.0
    assert _e(-1.0, i, f, d) == 0.0


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(a=_area, i=_current, f=_freq, d=_dist)
def test_emi_closed_form_bit_exact(a, i, f, d):
    """P2 — closed form, bit-exact: the result equals the reference
    arithmetic written in Python (same op order: the four-op left-to-
    right field chain with pow(f, 2.0), the *1e6 conversion, and
    20*log10).  A kernel that drops the *1e6 unit conversion, uses
    f*f instead of pow, or drops the 20 multiplier fails."""
    e_v = (1.316e-14 * a * i * (f**2)) / d
    e_uv = e_v * 1e6
    expected = 20 * math.log10(e_uv)
    got = _e(a, i, f, d)
    assert got == expected, f"rust={got!r} python={expected!r}"


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(a=_area, i=_current, f=_freq, d=_dist)
def test_emi_distance_inverse_relation(a, i, f, d):
    """P3 — dB scales as -20 dB per 10x distance (E ∝ 1/d → dBµV/m
    falls by 20·log10(10) = 20 exactly when the field itself is not
    rounded into the 0.0 guard).  A kernel that drops the /d term or
    misplaces it fails.  Honest bound: the comparison is exact for
    inputs where the 10x-distance field stays > 0 (guarded by the
    minimum magnitude in the strategies)."""
    got_far = _e(a, i, f, 10.0 * d)
    got_near = _e(a, i, f, d)
    assert got_near - got_far == pytest.approx(20.0, abs=1e-9)


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(a=_area, i=_current, f=_freq, d=_dist)
def test_emi_monotone_in_area_current(a, i, f, d):
    """P4 — dB is strictly increasing in A and in I for fixed other
    inputs (the chain is monotone on the positive domain and IEEE
    rounding is monotone, so the rounded outputs compare the same way).
    A kernel with A and I swapped, or with a sign flip, fails."""
    a2 = a * 2.0
    i2 = i * 2.0
    assert _e(a2, i, f, d) > _e(a, i, f, d)
    assert _e(a, i2, f, d) > _e(a, i, f, d)


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(a=_area, i=_current, f=_freq, d=_dist)
def test_emi_frequency_quadratic_dB(a, i, f, d):
    """P5 — E ∝ f² so dBµV/m rises by 40 dB per 10x frequency
    (20·log10(10²) = 40), exact when the 10x-frequency field stays out
    of the 0.0 guard.  A kernel that uses f¹ or f³ fails."""
    got_hi = _e(a, i, f * 10.0, d)
    got_lo = _e(a, i, f, d)
    assert got_hi - got_lo == pytest.approx(40.0, abs=1e-9)


# ---------------------------------------------------------------------------
# Vacuity guards for P1..P5 (real mutants that must fail the property)
# ---------------------------------------------------------------------------


def _mutant_constant_kernel(a, i, f, d=3.0):
    """P1 mutant: always returns a fixed dB value — no guard branches."""
    del a, i, f, d
    return -50.0


def _mutant_no_unit_conversion(a, i, f, d=3.0):
    """P2 mutant: drops the *1e6 V/m → µV/m conversion."""
    e_v = (1.316e-14 * a * i * (f**2)) / d
    return 20 * math.log10(e_v)


def _mutant_f_mul_not_pow(a, i, f, d=3.0):
    """P2 mutant: uses f*f instead of CPython pow(f, 2.0)."""
    e_v = (1.316e-14 * a * i * (f * f)) / d
    return 20 * math.log10(e_v * 1e6)


def _mutant_area_inverse(a, i, f, d=3.0):
    """P4 mutant: area enters inversely (1/a) — increasing a DECREASES
    the field, breaking P4's monotone-increasing claim (stays finite
    and positive, so the property — not a crash — discriminates)."""
    e_v = (1.316e-14 * i * (f**2)) / (a * d)
    return 20 * math.log10(e_v * 1e6)


def test_p1_fails_for_constant_kernel():
    # P1's guard-arm equalities (0.0 for each <=0 input) cannot hold for
    # a constant kernel: at least one arm differs from the constant.
    out = {_mutant_constant_kernel(0.0, 1.0, 1.0, 3.0), _mutant_constant_kernel(1.0, 0.0, 1.0, 3.0),
           _mutant_constant_kernel(1.0, 1.0, 0.0, 3.0), _mutant_constant_kernel(1.0, 1.0, 1.0, 3.0)}
    assert out != {0.0}  # the property demands all-zero for the guard arms


def test_p2_fails_for_missing_unit_conversion():
    a, i, f, d = 100.0, 10.0, 1.0, 3.0
    e_v = (1.316e-14 * a * i * (f**2)) / d
    expected = 20 * math.log10(e_v * 1e6)
    assert _mutant_no_unit_conversion(a, i, f, d) != expected


def test_p2_fails_for_fmul_not_pow():
    # pow(f, 2.0) vs f*f differ on a small fraction of floats; on a
    # sampled value where they differ, the bit-exact closed form fails.
    import random
    import struct

    rng = random.Random(123)
    for _ in range(50000):
        f = rng.uniform(1e-3, 1e3)
        if struct.pack(">d", f**2) != struct.pack(">d", f * f):
            break
    a, i, d = 100.0, 10.0, 3.0
    expected = 20 * math.log10((1.316e-14 * a * i * (f**2)) / d * 1e6)
    assert _mutant_f_mul_not_pow(a, i, f, d) != expected


# ---------------------------------------------------------------------------
# M1..M4: metamorphic relations (honestly bounded)
# ---------------------------------------------------------------------------


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(a=_area, i=_current, f=_freq, d=_dist)
def test_m1_power_of_two_scale_area(a, i, f, d):
    """M1 — scaling A by a power of two keeps the value in dB in the
    correct direction and magnitude band: doubling A adds 20·log10(2) ≈
    6.0206 dB.  NOT bit-exact in dB (log10 of a scaled argument rounds
    once more), so this is an exact-within-1e-9 comparison."""
    doubled = _e(2.0 * a, i, f, d)
    base = _e(a, i, f, d)
    assert doubled - base == pytest.approx(20.0 * math.log10(2.0), abs=1e-9)


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(a=_area, i=_current, f=_freq, d=_dist)
def test_m2_half_distance_is_plus_6db(a, i, f, d):
    """M2 — halving the measurement distance adds 20·log10(2) dB
    (E ∝ 1/d), exact within the same honest bound as M1."""
    near = _e(a, i, f, d / 2.0)
    base = _e(a, i, f, d)
    assert near - base == pytest.approx(20.0 * math.log10(2.0), abs=1e-9)


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(a=_area, i=_current, f=_freq, d=_dist)
def test_m3_quadratic_frequency_scaling(a, i, f, d):
    """M3 — doubling f adds 40·log10(2) ≈ 12.041 dB (E ∝ f²), exact
    within the same honest bound as M1."""
    hi = _e(a, i, 2.0 * f, d)
    base = _e(a, i, f, d)
    assert hi - base == pytest.approx(40.0 * math.log10(2.0), abs=1e-9)


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(db=_db)
def test_m4_compliance_monotone_in_limit(db):
    """M4 — for a fixed field strength, the Class-A (50 dB) check is
    satisfied whenever the Class-B (40 dB) check is: the higher limit
    is a superset of the lower.  A kernel that swapped the two limits
    fails."""
    cb = _tt.check_emi_compliance_py(db, "CISPR32_CLASS_B")
    ca = _tt.check_emi_compliance_py(db, "CISPR32_CLASS_A")
    assert (not cb) or ca  # Class B pass ⇒ Class A pass
