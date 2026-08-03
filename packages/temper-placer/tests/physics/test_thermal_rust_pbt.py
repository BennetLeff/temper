"""Property-based tests for the Rust junction-temperature kernel
(``temper_thermal.estimate_junction_temp_py``, Wave 4 Phase A #3 —
migration of ``temper_placer/physics/thermal.py::estimate_junction_temp``).

The kernel is pure closed-form f64 arithmetic over a fixed op chain
(edge penalty ``max(0.0, d-5.0)*0.2``, copper benefit
``min(0.5, (A/1000)*0.1)``, left-to-right resistance sum, and the
parenthesized ``ambient + P * R_total``).  Every property below is a
direct statement about correctly-rounded IEEE-754 operations, and each
is vacuity-guarded (its docstring says why a constant / degenerate
implementation fails it).

Exactness notes:

- ``max(0.0, ...)`` / ``min(0.5, ...)`` keep the CONSTANT as the first
  argument, mirroring CPython's builtin first-argument NaN semantics
  (B5) — the differential suite pins the NaN parity directly.
- Op order is pinned (B7): ``* 0.2`` applies to the max result; the
  benefit is division → ``* 0.1`` → min; ``R_total`` is the left-to-right
  ``((Rjc+Rch)+Rha_base)+penalty-benefit`` chain; final
  ``ambient + (power*R_total)`` has the parenthesized product first.
- Bit-exact closed-form and metamorphic relations (P3, M1/M2/M3/M4)
  hold because both sides evaluate the same op chain; power-of-two
  scaling relations are exact because scaling by a power of two
  commutes through multiplication without rounding (barring
  overflow/underflow, which the strategies' magnitudes avoid).
"""

from __future__ import annotations

import random

import pytest
import temper_thermal as _tt
from hypothesis import given, settings
from hypothesis import strategies as st

MAX_EXAMPLES = 200

# --- Input strategies (finite, physically meaningful, non-degenerate) --------
# Rjc/Rch/Rha_base are bounded so that R_total = Rjc+Rch+Rha+penalty-benefit
# stays strictly positive (min 0.2+0.1+0.5-0.5 = 0.3) — the closed-form and
# monotonicity properties rely on a positive resistance.

_power = st.floats(min_value=0.0, max_value=500.0, allow_nan=False, allow_infinity=False)
_power_pos = st.floats(min_value=0.1, max_value=500.0, allow_nan=False, allow_infinity=False)
_edge = st.floats(min_value=-20.0, max_value=60.0, allow_nan=False, allow_infinity=False)
_copper = st.floats(min_value=0.0, max_value=12000.0, allow_nan=False, allow_infinity=False)
_ambient = st.floats(min_value=-40.0, max_value=100.0, allow_nan=False, allow_infinity=False)
_ambient_nonneg = st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False)
_rjc = st.floats(min_value=0.2, max_value=3.0, allow_nan=False, allow_infinity=False)
_rch = st.floats(min_value=0.1, max_value=2.0, allow_nan=False, allow_infinity=False)
_rha = st.floats(min_value=0.5, max_value=5.0, allow_nan=False, allow_infinity=False)
_delta = st.floats(min_value=1e-3, max_value=50.0, allow_nan=False, allow_infinity=False)


def _tj(power_w, edge_distance_mm, copper_area_mm2=0.0, ambient_c=40.0, rjc=0.6, rch=0.25, rha_base=1.0):
    """Kernel call (direct pyfunction, the migrated surface)."""
    return _tt.estimate_junction_temp_py(
        power_w, edge_distance_mm, copper_area_mm2, ambient_c, rjc, rch, rha_base
    )


# ---------------------------------------------------------------------------
# P1..P5: five non-vacuous properties (each vacuity-guarded)
# ---------------------------------------------------------------------------


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(power=_power_pos, copper=_copper, ambient=_ambient_nonneg, rjc=_rjc, rch=_rch, rha=_rha)
def test_positive_and_rich(power, copper, ambient, rjc, rch, rha):
    """P1 — positive power and non-negative ambient produce a positive
    Tj, and the mapping is RICH: pushing the component 55 mm further
    from the edge (penalty grows by 11.0 K/W) strictly raises Tj.  A
    constant kernel fails: it cannot stay > 0 while also separating the
    input classes."""
    t_near = _tj(power, 5.0, copper, ambient, rjc, rch, rha)
    t_far = _tj(power, 60.0, copper, ambient, rjc, rch, rha)
    assert t_near > 0.0
    assert t_far > 0.0
    # R_total >= 0.3 > 0, so 55 mm of penalty raises Tj by 11.0*power > 0.
    assert t_far > t_near


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(power=_power, edge=_edge, copper=_copper, ambient=_ambient, rjc=_rjc, rch=_rch, rha=_rha,
       delta=_delta)
def test_non_decreasing_in_power(power, edge, copper, ambient, rjc, rch, rha, delta):
    """P2 — non-decreasing in power_W for fixed thermal params: Tj =
    ambient + P*R_total with R_total > 0, so raising the dissipation
    never lowers Tj.  A kernel that decreases in P fails."""
    p1 = min(power, 500.0 - delta)
    p2 = p1 + delta
    t1 = _tj(p1, edge, copper, ambient, rjc, rch, rha)
    t2 = _tj(p2, edge, copper, ambient, rjc, rch, rha)
    assert t2 >= t1, f"Tj({p2})={t2!r} < Tj({p1})={t1!r}"


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(power=_power, edge=_edge, copper=_copper, ambient=_ambient, rjc=_rjc, rch=_rch, rha=_rha)
def test_closed_form_bit_exact(power, edge, copper, ambient, rjc, rch, rha):
    """P3 — bit-exact closed form: Tj == ambient + (power * R_total)
    with R_total evaluated as the same left-to-right op chain written in
    Python (penalty ``max(0.0, edge-5.0)*0.2``, benefit
    ``min(0.5, (copper/1000.0)*0.1)``).  A kernel that drops the edge
    penalty or the copper benefit fails."""
    penalty = max(0.0, edge - 5.0) * 0.2
    benefit = min(0.5, (copper / 1000.0) * 0.1)
    r_total = ((rjc + rch) + rha) + penalty - benefit
    expected = ambient + (power * r_total)
    got = _tj(power, edge, copper, ambient, rjc, rch, rha)
    assert got == expected, f"closed form: rust={got!r} python={expected!r}"


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(power=_power, edge=_edge, copper=_copper, ambient=_ambient, rjc=_rjc, rch=_rch, rha=_rha,
       delta=_delta)
def test_non_decreasing_in_edge_distance(power, edge, copper, ambient, rjc, rch, rha, delta):
    """P4 — non-decreasing in edge_distance_mm: moving away from the
    edge never lowers Tj (penalty = max(0.0, d-5.0)*0.2 is
    non-decreasing in d; nothing else depends on d).  A kernel that
    decreases in d fails (a constant kernel is trivially monotone, so
    this is the discriminating mutant — P1 covers constants)."""
    d1 = min(edge, 60.0 - delta)
    d2 = d1 + delta
    t1 = _tj(power, d1, copper, ambient, rjc, rch, rha)
    t2 = _tj(power, d2, copper, ambient, rjc, rch, rha)
    assert t2 >= t1, f"Tj({d2})={t2!r} < Tj({d1})={t1!r}"


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(power=_power, edge=_edge, copper=_copper, ambient=_ambient, rjc=_rjc, rch=_rch, rha=_rha,
       delta=_delta)
def test_non_increasing_in_copper(power, edge, copper, ambient, rjc, rch, rha, delta):
    """P5 — non-increasing in copper_area_mm2: more copper never raises
    Tj (benefit = min(0.5, (A/1000)*0.1) is non-decreasing in A and is
    SUBTRACTED from R_total; nothing else depends on A).  A kernel whose
    copper term raises Tj fails."""
    a1 = min(copper, 12000.0 - delta)
    a2 = a1 + delta
    t1 = _tj(power, edge, a1, ambient, rjc, rch, rha)
    t2 = _tj(power, edge, a2, ambient, rjc, rch, rha)
    assert t2 <= t1, f"Tj({a2})={t2!r} > Tj({a1})={t1!r}"


# ---------------------------------------------------------------------------
# Metamorphic relations (>= 3 required; all four are bit-exact)
# ---------------------------------------------------------------------------


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(power=_power_pos, edge=_edge, copper=_copper, rjc=_rjc, rch=_rch, rha=_rha)
def test_mr1_power_of_two_power_scale(power, edge, copper, rjc, rch, rha):
    """M1 — bit-exact power-of-two P-scale at ambient = 0.0:
    Tj(2^k * P) == 2^k * Tj(P).  (0.0 + z == z exactly, so the relation
    needs no ambient subtraction; power-of-two scaling commutes through
    the multiply without rounding — round(2^k·z) = 2^k·round(z) for
    every intermediate z, barring overflow/underflow, which the strategy
    magnitudes avoid.)"""
    for k in (1, 2, 3):
        c = float(2**k)
        t_base = _tj(power, edge, copper, 0.0, rjc, rch, rha)
        t_scaled = _tj(c * power, edge, copper, 0.0, rjc, rch, rha)
        assert t_scaled == c * t_base, (
            f"power scale k={k}: Tj({c}*P)={t_scaled!r} vs {c}*Tj(P)={c * t_base!r}"
        )


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(power=_power, copper=_copper, ambient=_ambient, rjc=_rjc, rch=_rch, rha=_rha,
       d1=st.floats(min_value=-50.0, max_value=5.0, allow_nan=False, allow_infinity=False),
       d2=st.floats(min_value=-50.0, max_value=5.0, allow_nan=False, allow_infinity=False))
def test_mr2_edge_distance_saturation(power, copper, ambient, rjc, rch, rha, d1, d2):
    """M2 — bit-exact edge-distance saturation: for any d1, d2 <= 5.0
    the penalty is exactly 0.0 (max(0.0, d-5.0) is exactly 0.0 and
    0.0 * 0.2 == 0.0), so Tj is bit-identical across the whole
    sub-threshold range."""
    t1 = _tj(power, d1, copper, ambient, rjc, rch, rha)
    t2 = _tj(power, d2, copper, ambient, rjc, rch, rha)
    assert t1 == t2, f"edge saturation: Tj({d1})={t1!r} vs Tj({d2})={t2!r}"


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(power=_power, edge=_edge, ambient=_ambient, rjc=_rjc, rch=_rch, rha=_rha,
       a1=st.floats(min_value=5000.0, max_value=1e7, allow_nan=False, allow_infinity=False),
       a2=st.floats(min_value=5000.0, max_value=1e7, allow_nan=False, allow_infinity=False))
def test_mr3_copper_area_saturation(power, edge, ambient, rjc, rch, rha, a1, a2):
    """M3 — bit-exact copper-area saturation: for any a1, a2 >= 5000.0
    the benefit is exactly 0.5 (min(0.5, (A/1000)*0.1) saturates at the
    cap), so Tj is bit-identical across the whole saturating range."""
    t1 = _tj(power, edge, a1, ambient, rjc, rch, rha)
    t2 = _tj(power, edge, a2, ambient, rjc, rch, rha)
    assert t1 == t2, f"copper saturation: Tj({a1})={t1!r} vs Tj({a2})={t2!r}"


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(edge=_edge, copper=_copper, ambient=_ambient, rjc=_rjc, rch=_rch, rha=_rha)
def test_mr4_zero_power_is_ambient(edge, copper, ambient, rjc, rch, rha):
    """M4 — bit-exact zero-power degeneracy: at P = 0.0 the product
    0.0 * R_total is exactly 0.0 (R_total finite), so Tj == ambient
    bit-exactly regardless of the thermal params and geometry."""
    got = _tj(0.0, edge, copper, ambient, rjc, rch, rha)
    assert got == ambient, f"zero-power: Tj={got!r} != ambient={ambient!r}"


def test_pbt_smoke_deterministic_seed():
    """The PBT strategies are non-vacuous in aggregate: a quick seeded
    sweep over the property inputs must produce strictly more than one
    distinct Tj (guards against the whole suite silently degenerating
    to a single input class)."""
    rng = random.Random(0xABCD)
    distinct = set()
    for _ in range(300):
        distinct.add(
            _tj(
                rng.uniform(0.1, 500.0),
                rng.uniform(-20.0, 60.0),
                rng.uniform(0.0, 12000.0),
                rng.uniform(-40.0, 100.0),
                rng.uniform(0.2, 3.0),
                rng.uniform(0.1, 2.0),
                rng.uniform(0.5, 5.0),
            )
        )
    assert len(distinct) > 50


# ---------------------------------------------------------------------------
# Vacuity mutants (G4 evidence pattern)
# ---------------------------------------------------------------------------


@pytest.fixture
def _restore_kernel():
    original = _tt.estimate_junction_temp_py
    yield
    _tt.estimate_junction_temp_py = original


def test_p1_fails_for_constant_kernel(_restore_kernel) -> None:
    """A constant kernel (0.0) cannot be positive AND rich (P1)."""
    _tt.estimate_junction_temp_py = lambda *_a, **_k: 0.0
    with pytest.raises(AssertionError):
        test_positive_and_rich.hypothesis.inner_test(15.0, 0.0, 40.0, 0.6, 0.25, 1.0)


def test_p2_fails_for_power_decreasing_kernel(_restore_kernel) -> None:
    """A kernel that DECREASES in power_W (Tj = ambient - P*R_total)
    breaks P2's monotonicity (a constant is trivially monotone, so this
    is the discriminating mutant; P1 covers constants)."""
    _tt.estimate_junction_temp_py = (
        lambda power_w, edge_distance_mm, copper_area_mm2, ambient_c, rjc, rch, rha: (  # noqa: ARG005
            ambient_c - power_w * (rjc + rch + rha)
        )
    )
    with pytest.raises(AssertionError):
        test_non_decreasing_in_power.hypothesis.inner_test(15.0, 5.0, 0.0, 40.0, 0.6, 0.25, 1.0, 5.0)


def test_p3_fails_for_missing_copper_benefit(_restore_kernel) -> None:
    """A kernel that drops the copper benefit (R_total has no
    min(0.5, ...) term) breaks the bit-exact closed form (P3)."""
    _tt.estimate_junction_temp_py = (
        lambda power_w, edge_distance_mm, copper_area_mm2, ambient_c, rjc, rch, rha: (  # noqa: ARG005
            ambient_c + (power_w * (((rjc + rch) + rha) + max(0.0, edge_distance_mm - 5.0) * 0.2))
        )
    )
    with pytest.raises(AssertionError):
        test_closed_form_bit_exact.hypothesis.inner_test(15.0, 5.0, 2000.0, 40.0, 0.6, 0.25, 1.0)


def test_p4_fails_for_edge_decreasing_kernel(_restore_kernel) -> None:
    """A kernel that DECREASES in edge distance (penalty subtracted)
    breaks P4's monotonicity (a constant is trivially monotone, so this
    is the discriminating mutant; P1 covers constants)."""
    _tt.estimate_junction_temp_py = (
        lambda power_w, edge_distance_mm, copper_area_mm2, ambient_c, rjc, rch, rha: (  # noqa: ARG005
            ambient_c + (power_w * (((rjc + rch) + rha) - max(0.0, edge_distance_mm - 5.0) * 0.2))
        )
    )
    with pytest.raises(AssertionError):
        test_non_decreasing_in_edge_distance.hypothesis.inner_test(15.0, 6.0, 0.0, 40.0, 0.6, 0.25, 1.0, 1.0)


def test_p5_fails_for_copper_increasing_kernel(_restore_kernel) -> None:
    """A kernel whose copper term RAISES Tj (benefit added instead of
    subtracted) breaks P5's non-increasing monotonicity (a constant is
    trivially monotone, so this is the discriminating mutant; P1 covers
    constants)."""
    _tt.estimate_junction_temp_py = (
        lambda power_w, edge_distance_mm, copper_area_mm2, ambient_c, rjc, rch, rha: (  # noqa: ARG005
            ambient_c + (power_w * (((rjc + rch) + rha) + 0.1 * (copper_area_mm2 / 1000.0)))
        )
    )
    with pytest.raises(AssertionError):
        test_non_increasing_in_copper.hypothesis.inner_test(15.0, 5.0, 1000.0, 40.0, 0.6, 0.25, 1.0, 1000.0)
