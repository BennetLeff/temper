"""Property-based tests for the Rust parasitic-loop-inductance kernels
(``temper_thermal.estimate_loop_inductance_py`` /
``temper_thermal.estimate_gate_inductance_py``, Wave 4 Phase A #4 —
migration of ``temper_placer/physics/inductance.py``).

The kernels are pure closed-form f64 arithmetic over a two-branch
structure (the ``h_m > 0`` conditional area term of the loop estimator,
plus the fixed chains of both estimators).  Every property below is a
direct statement about correctly-rounded IEEE-754 operations, and each
is vacuity-guarded (its docstring says why a constant / degenerate
implementation fails it).

Exactness notes:

- The loop estimator is
  ``((4 * math.pi * 1e-7) * area_mm2*1e-6 / h_mm*1e-3) * 1e9 * 0.5 +
  perimeter*0.2) * routing_factor`` with the conditional area term
  (B7 op order; B2 named-constant pi, bit-identical to Rust's PI).
- Power-of-two scaling relations (M1/M3) are exact because scaling by a
  power of two commutes through multiplication without rounding
  (round(2^k·z) == 2^k·round(z) for every intermediate z, barring
  overflow/underflow, which the strategies' magnitudes avoid — the
  same argument as the device-power PBT suite).
- Monotonicity relations (P5/P6/M4/M5) are exact comparisons: every
  operation in the chain is a monotone non-decreasing real function on
  the positive domain, and IEEE rounding is monotone, so the rounded
  outputs compare the same way.
"""

from __future__ import annotations

import math
import random

import pytest
import temper_thermal as _tt
from hypothesis import given, settings
from hypothesis import strategies as st

MAX_EXAMPLES = 200

# --- Input strategies (finite, physically meaningful) ------------------------

_area = st.floats(min_value=1e-3, max_value=1e4, allow_nan=False, allow_infinity=False)
_perim = st.floats(min_value=1e-3, max_value=500.0, allow_nan=False, allow_infinity=False)
# h bounded away from 0 on the positive side so the area term stays in
# the NORMAL f64 range: the power-of-two scale metamorphic relations
# (M1/M3) are exact only for normal-magnitude intermediates — the
# denormal-band B8 parity itself is pinned in the differential suite.
_h = st.floats(min_value=1e-6, max_value=3.0, allow_nan=False, allow_infinity=False)
_rf = st.floats(min_value=0.5, max_value=4.0, allow_nan=False, allow_infinity=False)
_dist = st.floats(min_value=0.0, max_value=50.0, allow_nan=False, allow_infinity=False)


def _l(area, perim, h, rf):
    """Loop kernel call (direct pyfunction, the migrated surface)."""
    return _tt.estimate_loop_inductance_py(area, perim, h, rf)


def _g(a, b):
    """Gate kernel call (direct pyfunction, the migrated surface)."""
    return _tt.estimate_gate_inductance_py(a, b)


# ---------------------------------------------------------------------------
# P1..P6: five+ non-vacuous properties (each vacuity-guarded)
# ---------------------------------------------------------------------------


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(area=_area, perim=_perim, h=_h, rf=_rf)
def test_inductance_non_negative_and_rich(area, perim, h, rf):
    """P1 — positive inputs produce non-negative inductance, and the
    mapping is rich (a constant kernel fails: it cannot stay plausible
    across the range while also separating the input classes)."""
    outs = {
        _l(area, perim, h, rf),
        _l(area, perim, h, 1.0),
        _l(area, perim, 0.0, rf),  # zero-height arm
    }
    assert all(x >= 0.0 for x in outs)
    # area and perimeter both contribute: for fixed h/rf the drawn
    # inputs must not collapse to a single value.
    assert len(outs) >= 2


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(area=_area, perim=_perim, h=_h, rf=_rf)
def test_loop_closed_form_bit_exact(area, perim, h, rf):
    """P2 — closed form, bit-exact: L == ((4*math.pi*1e-7 * area*1e-6 /
    h*1e-3) * 1e9 * 0.5 + perim*0.2) * rf (the same op chain written in
    Python).  A kernel that drops the 0.5 area-weight, the *1e9 unit
    conversion, or the routing factor fails."""
    mu_0 = 4 * math.pi * 1e-7
    l_area_h = mu_0 * (area * 1e-6) / (h * 1e-3)
    l_area_nh = l_area_h * 1e9
    l_self_nh = perim * 0.2
    expected = (l_area_nh * 0.5 + l_self_nh) * rf
    got = _l(area, perim, h, rf)
    assert got == expected, f"loop closed-form: rust={got!r} python={expected!r}"


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(a=_dist, b=_dist)
def test_gate_closed_form_bit_exact(a, b):
    """P3 — gate estimator closed form, bit-exact:
    L == (a + b + 5.0) * 0.8.  A kernel that omits the +5.0 internal
    coupling term or the 0.8 nH/mm factor fails."""
    got = _g(a, b)
    expected = (a + b + 5.0) * 0.8
    assert got == expected, f"gate closed-form: rust={got!r} python={expected!r}"


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(area=_area, perim=_perim, rf=_rf)
def test_zero_height_area_term_vanishes(area, perim, rf):
    """P4 — zero-height degeneracy, bit-exact: with h = 0.0 the
    conditional area term is exactly 0.0, so L == (0.0 + perim*0.2) * rf
    == perim*0.2*rf exactly (adding 0.0 is exact, as in CPython).  A
    kernel that computes the area term unconditionally (e.g. divides by
    a fake h) fails."""
    got = _l(area, perim, 0.0, rf)
    expected = (perim * 0.2) * rf
    assert got == expected, f"zero-height: rust={got!r} python={expected!r}"


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(
    perim=_perim,
    h=_h,
    rf=_rf,
    area1=st.floats(min_value=1e-3, max_value=5e3, allow_nan=False, allow_infinity=False),
    delta=st.floats(min_value=1e-3, max_value=5e3, allow_nan=False, allow_infinity=False),
)
def test_non_decreasing_in_area(perim, h, rf, area1, delta):
    """P5 — non-decreasing in loop_area for fixed (perimeter, h, rf):
    raising the loop area never lowers the inductance (the area term is
    monotone in A for h > 0).  A kernel that decreases in area fails."""
    a1 = min(area1, 1e4 - delta)
    a2 = a1 + delta
    l1 = _l(a1, perim, h, rf)
    l2 = _l(a2, perim, h, rf)
    assert l2 >= l1, f"L({a2})={l2!r} < L({a1})={l1!r}"


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(
    area=_area,
    h=_h,
    rf=_rf,
    perim1=st.floats(min_value=1e-3, max_value=250.0, allow_nan=False, allow_infinity=False),
    delta=st.floats(min_value=1e-3, max_value=250.0, allow_nan=False, allow_infinity=False),
)
def test_non_decreasing_in_perimeter(area, h, rf, perim1, delta):
    """P6 — non-decreasing in perimeter for fixed (area, h, rf): raising
    the loop perimeter never lowers the inductance (L_self = p*0.2 is
    monotone and the area term is perimeter-independent).  A kernel that
    decreases in perimeter fails."""
    p1 = min(perim1, 500.0 - delta)
    p2 = p1 + delta
    l1 = _l(area, p1, h, rf)
    l2 = _l(area, p2, h, rf)
    assert l2 >= l1, f"L({p2})={l2!r} < L({p1})={l1!r}"


# ---------------------------------------------------------------------------
# Metamorphic relations (>= 3 required; 5 provided)
# ---------------------------------------------------------------------------


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(area=_area, perim=_perim, h=_h, rf=_rf)
def test_mr1_power_of_two_routing_factor_scale(area, perim, h, rf):
    """M1 — bit-exact power-of-two routing-factor scaling:
    L(2^k·rf) == 2^k · L(rf), bit-exact.  (Power-of-two scaling
    commutes through the final multiply without rounding:
    round(2^k·z) == 2^k·round(z) for the normal-magnitude sums the
    strategies produce.)"""
    for k in (1, 2, 3):
        c = float(2**k)
        base = _l(area, perim, h, rf)
        scaled = _l(area, perim, h, c * rf)
        assert scaled == c * base, f"rf scale k={k}: L({c}*rf)={scaled!r} vs {c}*L(rf)={c * base!r}"


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(area=_area, perim=_perim, h=_h)
def test_mr2_zero_routing_factor_is_exactly_zero(area, perim, h):
    """M2 — bit-exact zero-routing-factor degeneracy: (finite sum) * 0.0
    == 0.0 exactly, so L(rf=0.0) == 0.0 on the full domain."""
    assert _l(area, perim, h, 0.0) == 0.0


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(area=_area, rf=_rf, perim=_perim)
def test_mr3_zero_height_power_of_two_perimeter_scale(area, rf, perim):
    """M3 — bit-exact zero-height + power-of-two perimeter scaling:
    with h = 0.0 the area term is exactly 0.0, leaving
    L = perim*0.2*rf; doubling the perimeter scales L by exactly 2
    (power-of-two scaling commutes through the *0.2 and *rf multiplies)."""
    for k in (1, 2):
        c = float(2**k)
        base = _l(area, perim, 0.0, rf)
        scaled = _l(area, c * perim, 0.0, rf)
        assert scaled == c * base, (
            f"zero-h perim scale k={k}: L({c}*p)={scaled!r} vs {c}*L(p)={c * base!r}"
        )


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(
    perim=_perim,
    h=_h,
    rf=_rf,
    area1=st.floats(min_value=1e-3, max_value=5e3, allow_nan=False, allow_infinity=False),
    delta=st.floats(min_value=1e-3, max_value=5e3, allow_nan=False, allow_infinity=False),
)
def test_mr4_area_up_height_down_monotone(perim, h, rf, area1, delta):
    """M4 — exact joint monotonicity: for A2 >= A1 and h2 <= h1 (both
    positive), L(A2, h2) >= L(A1, h1).  The area term
    mu_0*A*1e-6/h is monotone non-decreasing in A and monotone
    non-increasing in h on the positive domain, and IEEE rounding is
    monotone — the comparison is exact, not approximate."""
    a1 = min(area1, 1e4 - delta)
    a2 = a1 + delta
    h_lo = max(1e-6, h - delta * 1e-4)
    h_hi = h + delta * 1e-4
    l_lo = _l(a1, perim, h_hi, rf)
    l_hi = _l(a2, perim, h_lo, rf)
    assert l_hi >= l_lo, f"L(A2,h2)={l_hi!r} < L(A1,h1)={l_lo!r}"


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(
    b=_dist,
    a1=st.floats(min_value=0.0, max_value=25.0, allow_nan=False, allow_infinity=False),
    delta=st.floats(min_value=1e-3, max_value=25.0, allow_nan=False, allow_infinity=False),
)
def test_mr5_gate_monotone_in_source_distance(b, a1, delta):
    """M5 — exact gate-estimator monotonicity: L(a2, b) >= L(a1, b) for
    a2 >= a1 (the add chain and the *0.8 multiply are monotone, and IEEE
    rounding preserves the order)."""
    a2 = a1 + delta
    assert _g(a2, b) >= _g(a1, b), f"gate L({a2}) < gate L({a1})"


def test_pbt_smoke_deterministic_seed():
    """The PBT strategies are non-vacuous in aggregate: a quick seeded
    sweep over the property inputs must produce strictly more than one
    distinct inductance (guards against the whole suite silently
    degenerating to a single input class)."""
    rng = random.Random(0x1BAD)  # noqa: S311 — deterministic test seed
    distinct = set()
    for _ in range(300):
        distinct.add(
            _l(
                rng.uniform(1e-3, 1e4),
                rng.uniform(1e-3, 500.0),
                rng.uniform(1e-6, 3.0),
                rng.uniform(0.5, 4.0),
            )
        )
    assert len(distinct) > 50


# ---------------------------------------------------------------------------
# Vacuity mutants (G4 evidence pattern)
# ---------------------------------------------------------------------------


@pytest.fixture
def _restore_kernel():
    original = _tt.estimate_loop_inductance_py
    yield
    _tt.estimate_loop_inductance_py = original


@pytest.fixture
def _restore_gate_kernel():
    original = _tt.estimate_gate_inductance_py
    yield
    _tt.estimate_gate_inductance_py = original


def test_p1_fails_for_constant_kernel(_restore_kernel) -> None:
    """A constant kernel (0.0) cannot be non-negative AND rich (P1)."""
    _tt.estimate_loop_inductance_py = lambda *_a, **_k: 0.0
    with pytest.raises(AssertionError):
        test_inductance_non_negative_and_rich.hypothesis.inner_test(100.0, 40.0, 0.4, 1.2)


def test_p2_fails_for_missing_half_factor(_restore_kernel) -> None:
    """A kernel that drops the 0.5 area-weight
    (L = (L_area_nH + L_self_nH) * rf) breaks the closed form (P2)."""
    _tt.estimate_loop_inductance_py = (
        lambda area, perim, h, rf: (
            ((4 * math.pi * 1e-7) * (area * 1e-6) / (h * 1e-3)) * 1e9 + perim * 0.2
        )
        * rf  # noqa: E501
    )
    with pytest.raises(AssertionError):
        test_loop_closed_form_bit_exact.hypothesis.inner_test(100.0, 40.0, 0.4, 1.2)


def test_p3_fails_for_gate_missing_coupling_term(_restore_gate_kernel) -> None:
    """A gate kernel that omits the +5.0 internal coupling term
    (L = (a + b) * 0.8) breaks the closed form (P3)."""
    _tt.estimate_gate_inductance_py = lambda a, b: (a + b) * 0.8
    with pytest.raises(AssertionError):
        test_gate_closed_form_bit_exact.hypothesis.inner_test(10.0, 10.0)


def test_p4_fails_for_unconditional_area_term(_restore_kernel) -> None:
    """A kernel that computes the area term even when h == 0
    (divides by a fake h = 1e-3) breaks the zero-height degeneracy
    (P4) — the area term no longer vanishes."""
    _tt.estimate_loop_inductance_py = (
        lambda area, perim, h, rf: (  # noqa: ARG005
            ((4 * math.pi * 1e-7) * (area * 1e-6) / (1e-3)) * 1e9 * 0.5 + perim * 0.2
        )
        * rf
    )
    with pytest.raises(AssertionError):
        test_zero_height_area_term_vanishes.hypothesis.inner_test(100.0, 40.0, 1.2)


def test_p5_fails_for_decreasing_kernel(_restore_kernel) -> None:
    """A kernel that DECREASES in loop area (area term = mu_0 / area)
    breaks P5's monotonicity (a constant is trivially monotone, so this
    is the discriminating mutant; P1 covers constants)."""
    _tt.estimate_loop_inductance_py = (
        lambda area, perim, h, rf: ((1.0 / area) * 1e-6 + perim * 0.2) * rf  # noqa: ARG005
    )
    with pytest.raises(AssertionError):
        test_non_decreasing_in_area.hypothesis.inner_test(40.0, 0.4, 1.2, 100.0, 10.0)


def test_p6_fails_for_perimeter_decreasing_kernel(_restore_kernel) -> None:
    """A kernel that DECREASES in perimeter (L_self = -perim*0.2) breaks
    P6's monotonicity."""
    _tt.estimate_loop_inductance_py = (
        lambda area, perim, h, rf: (
            ((4 * math.pi * 1e-7) * (area * 1e-6) / (h * 1e-3)) * 1e9 * 0.5 - perim * 0.2
        )
        * rf  # noqa: E501
    )
    with pytest.raises(AssertionError):
        test_non_decreasing_in_perimeter.hypothesis.inner_test(100.0, 0.4, 1.2, 40.0, 10.0)
