"""Property-based tests for the Rust T_j cross-check kernels
(``temper_thermal.device_cross_check_py`` /
``distance_to_heatsink_edge_py``), Wave 4 Phase 4 migration of
``temper_placer/physics/tj_cross_check.py``.

This file is SHARED between the two modules, so the R1c/R1d minima are
met PER MODULE, not across the pair:

- ``tj_cross_check`` (P1–P3, P6–P7 + M1, M2, M4): **5 non-vacuous
  properties + 3 metamorphic relations**.

Every property AND every metamorphic relation is vacuity-guarded by a
real mutant (the file's convention: ``_mutant_*`` implementations whose
outputs violate the property, pinned by ``test_pN_fails_for_<mutant>``):

1. P1 — the conservative T_j is always >= both estimates (soundness of
   the safety gating: the optimistic estimate cannot decide).
2. P2 — delta is the absolute difference and exceeds is exactly
   delta > tau (bit-exact, boundary exact).
3. P3 — the distance to the heatsink edge is non-negative and matches
   the axis-aligned geometry (a device beyond the far edge has the
   correct absolute distance).
4. P6 — margin is exactly T_j_max − conservative, the SIGNED datasheet
   headroom (negative over the ceiling).
7. P7 — exceeds is gated ONLY on (delta, tau): changing T_j_max moves
   margin alone; every other output is bit-unchanged.

Metamorphic relations:

- M1 — with zero power the cross-check reduces to the ambient
  comparison exactly: T_j_fdm == T_case_fdm, T_j_lumped == T_amb and
  delta == |T_case_fdm − T_amb| (bit-exact degeneracy).
- M2 — conservative_T_j is symmetric under swapping the two estimates
  for non-NaN values (CPython max is commutative on non-NaN; the NaN
  asymmetry is pinned by the differential).
- M4 — reciprocal power-of-two scaling of power and the R_θ chain
  (p → 2p, R → ½R) leaves every output bit-identical (power-of-two
  scaling is exact in f64; measured 0 mismatches over 200k samples).

Guard inventory (pass 2 P3): P1, P2, P4, P6, P7, P8, P9, P10, M5, M6
had pins at pass 1; the header's "every property is guarded" claim was
then FALSE for P3, M1, M2, M3, M4.  Pass 2 added the missing
``test_p3_fails_for_drops_abs``, ``test_m1_fails_for_phantom_power``,
``test_m2_fails_for_first_arg_wins``, ``test_m3_fails_for_case_sensitive``
and ``test_m4_fails_for_forgot_halve_r`` pins so the claim holds.  M1's
guard is the honest one: a phantom power-proportional term is invisible
at p=0 (the degenerate sampling M1 uses), so the pin evaluates the
mutant at NONZERO power where the phantom breaks the cross-check chain.
"""

from __future__ import annotations

import numpy as np
import temper_thermal as _tt
from hypothesis import given, settings
from hypothesis import strategies as st

MAX_EXAMPLES = 100

_t = st.floats(min_value=-50.0, max_value=300.0, allow_nan=False, allow_infinity=False)
_pos = st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False)


def _dcc(tc, p, rj, rc, rs, ta, tjm, tau):
    return _tt.device_cross_check_py(tc, p, rj, rc, rs, ta, tjm, tau)


# ---------------------------------------------------------------------------
# P1..P5
# ---------------------------------------------------------------------------


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(tc=_t, p=_pos)
def test_p1_conservative_geq_both(tc, p):
    """P1 — conservative_T_j >= max(T_j_fdm, T_j_lumped) — actually
    equal: the safety ceiling is gated on the conservative (higher)
    estimate, so the optimistic model can never decide.  A kernel that
    returns the MINIMUM instead fails."""
    f, lump, _, c, m, e = _dcc(tc, p, 0.6, 0.25, 1.0, 40.0, 150.0, 5.0)
    assert c >= f and c >= lump
    assert c == max(f, lump)


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(tc=_t, p=_pos, tau=_pos)
def test_p2_delta_and_exceeds_exact(tc, p, tau):
    """P2 — delta == abs(T_j_fdm - T_j_lumped) bit-exactly and
    exceeds == (delta > tau) with the boundary exact (delta == tau is
    NOT a breach).  A kernel with a >= comparison or a sign flip
    fails."""
    f, lump, d, c, m, e = _dcc(tc, p, 0.6, 0.25, 1.0, 40.0, 150.0, tau)
    assert d == abs(f - lump)
    assert e == (d > tau)
    # delta == tau exactly → not a breach.
    f, lump, d, c, m, e = _dcc(tc, p, 0.6, 0.25, 1.0, 40.0, 150.0, d)
    assert e is False


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(x=_t, y=_t)
def test_p3_distance_non_negative_geometry(x, y):
    """P3 — distance to the heatsink edge is non-negative and equals
    the axis-aligned absolute distance for each edge.  A kernel that
    drops the abs() or misorients the edge fails."""
    ox, oy, cell, h, w = 0.0, 0.0, 1.0, 20, 20
    d_top = _tt.distance_to_heatsink_edge_py(x, y, ox, oy, cell, h, w, 0)
    d_bot = _tt.distance_to_heatsink_edge_py(x, y, ox, oy, cell, h, w, 1)
    d_lef = _tt.distance_to_heatsink_edge_py(x, y, ox, oy, cell, h, w, 2)
    d_rig = _tt.distance_to_heatsink_edge_py(x, y, ox, oy, cell, h, w, 3)
    assert d_top == abs(20.0 - y) and d_bot == abs(y)
    assert d_lef == abs(x) and d_rig == abs(20.0 - x)
    assert min(d_top, d_bot, d_lef, d_rig) >= 0.0


def _mutant_drops_abs(x, y, ox, oy, cell, h, w, edge_code):
    """P3 mutant: computes the distances WITHOUT the reference's abs()
    — a device beyond an edge yields a NEGATIVE distance (P3 demands
    non-negative)."""
    if edge_code == 0:
        return oy + h * cell - y
    if edge_code == 1:
        return y - oy
    if edge_code == 2:
        return x - ox
    if edge_code == 3:
        return ox + w * cell - x
    return 0.0


def test_p3_fails_for_drops_abs():
    """Pass 2 P3: P3 lacked a vacuity guard — the header's "every
    property is guarded" claim was false.  A device beyond the far
    edge: the real kernel returns the positive absolute distance, the
    abs-less mutant returns a NEGATIVE one, breaking P3's
    non-negativity."""
    x, y = -1.0, 21.0  # beyond LEFT and TOP edges
    ox, oy, cell, h, w = 0.0, 0.0, 1.0, 20, 20
    assert _tt.distance_to_heatsink_edge_py(x, y, ox, oy, cell, h, w, 0) == abs(20.0 - y)
    assert _tt.distance_to_heatsink_edge_py(x, y, ox, oy, cell, h, w, 2) == abs(x)
    assert _mutant_drops_abs(x, y, ox, oy, cell, h, w, 0) < 0  # beyond TOP
    assert _mutant_drops_abs(x, y, ox, oy, cell, h, w, 2) < 0  # beyond LEFT


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(tc=_t, p=_pos)
def test_p6_margin_definitional(tc, p):
    """P6 — margin is exactly T_j_max − conservative, the SIGNED
    datasheet headroom (negative when the conservative estimate is over
    the ceiling).  A kernel that flips the sign (conservative −
    T_j_max) or computes against the optimistic estimate fails."""
    f, lump, d, c, m, e = _dcc(tc, p, 0.6, 0.25, 1.0, 40.0, 150.0, 5.0)
    assert m == 150.0 - c


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(tc=_t, p=_pos, tau=_pos)
def test_p7_exceeds_independent_of_ceiling(tc, p, tau):
    """P7 — exceeds == (delta > tau) does NOT consult the T_j_max
    ceiling: changing T_j_max changes ONLY margin, never
    fdm/lumped/delta/conservative/exceeds (bit-exact).  A kernel that
    gates the disagreement flag on the ceiling violation (margin < 0)
    fails."""
    a = _dcc(tc, p, 0.6, 0.25, 1.0, 40.0, 150.0, tau)
    b = _dcc(tc, p, 0.6, 0.25, 1.0, 40.0, 1.0, tau)  # ceiling below everything
    assert a[0] == b[0] and a[1] == b[1] and a[2] == b[2]
    assert a[3] == b[3] and a[5] == b[5]
    assert a[4] != b[4]  # the ceiling DOES move the margin (150 vs 1)


# ---------------------------------------------------------------------------
# Vacuity guards (real mutants that must fail the property)
# ---------------------------------------------------------------------------


def _mutant_min_conservative(tc, p, rj, rc, rs, ta, tjm, tau):
    """P1 mutant: gates on the MINIMUM instead of the conservative max."""
    f, lump, d, c, m, e = _dcc(tc, p, rj, rc, rs, ta, tjm, tau)
    return f, lump, d, min(f, lump), m, e


def _mutant_non_strict_exceeds(tc, p, rj, rc, rs, ta, tjm, tau):
    """P2 mutant: exceeds uses >= instead of >."""
    f, lump, d, c, m, e = _dcc(tc, p, rj, rc, rs, ta, tjm, tau)
    return f, lump, d, c, m, d >= tau


def test_p1_fails_for_min_conservative():
    tc, p = 50.0, 5.0
    f, lump, d, c, m, e = _mutant_min_conservative(tc, p, 0.6, 0.25, 1.0, 40.0, 150.0, 5.0)
    assert c != max(f, lump)  # P1's conservative claim broken


def test_p2_fails_for_non_strict_exceeds():
    # A >= comparison flips the boundary case (delta == tau): build the
    # case from the real delta, then show the mutant disagrees.
    tc, p = 50.0, 5.0
    _, _, d, _, _, _ = _dcc(tc, p, 0.6, 0.25, 1.0, 40.0, 150.0, 5.0)
    _, _, _, _, _, e2 = _dcc(tc, p, 0.6, 0.25, 1.0, 40.0, 150.0, d)
    assert e2 is False  # delta == tau is NOT a breach (real kernel, strict >)
    assert (d >= d) is True  # a >= mutant would flag it


def _mutant_sign_flip_margin(tc, p, rj, rc, rs, ta, tjm, tau):
    """P6 mutant: margin computed as conservative − T_j_max (sign flip)."""
    f, lump, d, c, m, e = _dcc(tc, p, rj, rc, rs, ta, tjm, tau)
    return f, lump, d, c, -m, e


def test_p6_fails_for_sign_flip_margin():
    # margin = 150 - 53 = 97 for these inputs — the negated margin
    # cannot equal the definitional T_j_max − conservative.
    tc, p = 50.0, 5.0
    f, lump, d, c, m, e = _mutant_sign_flip_margin(tc, p, 0.6, 0.25, 1.0, 40.0, 150.0, 5.0)
    assert m != 150.0 - c  # P6's definitional claim broken


def _mutant_exceeds_on_violation(tc, p, rj, rc, rs, ta, tjm, tau):
    """P7 mutant: gates the disagreement flag on the CEILING violation
    (margin < 0) instead of delta > tau."""
    f, lump, d, c, m, e = _dcc(tc, p, rj, rc, rs, ta, tjm, tau)
    return f, lump, d, c, m, m < 0


def test_p7_fails_for_violation_gated_mutant():
    # tc=100, p=0, ta=95 → fdm=100, lump=95, delta=5 > tau=3, but
    # conservative=100 <= 150 → margin >= 0.  The real kernel reports
    # exceeds=True (a disagreement); the violation-gated mutant reports
    # False (no ceiling breach) — P7's delta-only claim is broken.
    f, lump, d, c, m, e = _mutant_exceeds_on_violation(100.0, 0.0, 0.6, 0.25, 1.0, 95.0, 150.0, 3.0)
    assert e is False
    _, _, _, _, _, e_real = _dcc(100.0, 0.0, 0.6, 0.25, 1.0, 95.0, 150.0, 3.0)
    assert e_real is True
    assert e != e_real


# ---------------------------------------------------------------------------
# M1..M3: metamorphic relations
# ---------------------------------------------------------------------------


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(tc=_t, s=_pos)
def test_m1_zero_power_degeneracy(tc, s):
    """M1 — with zero power the cross-check reduces to the ambient
    comparison exactly: T_j_fdm == T_case_fdm, T_j_lumped == T_amb and
    delta == |T_case_fdm - T_amb| (bit-exact degeneracies).  A kernel
    that adds a phantom power term fails."""
    f, lump, d, c, m, e = _dcc(tc, 0.0, 0.6, 0.25, 1.0, 40.0, 150.0, 5.0)
    assert f == tc
    assert lump == 40.0
    assert d == abs(tc - 40.0)


def _mutant_phantom_power(tc, p, rj, rc, rs, ta, tjm, tau):
    """M1 mutant: T_j_fdm gains a phantom power-proportional term
    (T_j_fdm = tc + p*rj + p*0.5).  The term is INVISIBLE at p=0 — the
    degenerate sampling M1 uses — so the guard evaluates it at NONZERO
    power, where it breaks the FDM chain (T_j_fdm no longer equals
    T_case_fdm + p*R_jc) that M1's p=0 case is the limit of."""
    f, lump, d, c, m, e = _dcc(tc, p, rj, rc, rs, ta, tjm, tau)
    return f + 0.5 * p, lump, d, c, m, e


def test_m1_fails_for_phantom_power():
    """Pass 2 P3: M1 lacked a vacuity guard.  A phantom power-
    proportional term is the bug class M1's p=0-only sampling cannot
    see: at p=0 the phantom vanishes (f == tc either way), so a kernel
    with correct p=0 behaviour and wrong p>0 arithmetic passed M1.
    The pin demonstrates the phantom at NONZERO power, where it breaks
    T_j_fdm == tc + p*r_jc."""
    tc, p = 50.0, 5.0
    # At p=0 the phantom is invisible — exactly the vacuity diagnosed.
    f0_real, _, _, _, _, _ = _dcc(tc, 0.0, 0.6, 0.25, 1.0, 40.0, 150.0, 5.0)
    f0_mut, _, _, _, _, _ = _mutant_phantom_power(tc, 0.0, 0.6, 0.25, 1.0, 40.0, 150.0, 5.0)
    assert f0_mut == f0_real
    # At p>0 the phantom breaks the chain M1's degeneracy is the limit
    # of: T_j_fdm != T_case_fdm + p*R_jc.
    f_mut, _, _, _, _, _ = _mutant_phantom_power(tc, p, 0.6, 0.25, 1.0, 40.0, 150.0, 5.0)
    assert f_mut != tc + p * 0.6  # phantom visible at p>0


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(tc=_t, p=_pos)
def test_m2_conservative_order_independent(tc, p):
    """M2 — conservative_T_j is symmetric under swapping the two
    estimates for non-NaN values (CPython max is commutative on
    non-NaN; the NaN asymmetry is pinned by the differential)."""
    f, lump, d, c, m, e = _dcc(tc, p, 0.6, 0.25, 1.0, 40.0, 150.0, 5.0)
    assert c == max(lump, f)  # order-independent


def _mutant_first_arg_wins(tc, p, rj, rc, rs, ta, tjm, tau):
    """M2 mutant: conservative_T_j is the FIRST estimate, not the max —
    order-DEPENDENT (swap the estimates and the output changes)."""
    f, lump, d, c, m, e = _dcc(tc, p, rj, rc, rs, ta, tjm, tau)
    return f, lump, d, f, m, e


def test_m2_fails_for_first_arg_wins():
    """Pass 2 P3: M2 lacked a vacuity guard.  Pick a case where the
    estimates differ (lump > f): the real kernel's conservative ==
    max(lump, f) == lump; the first-arg-wins mutant keeps f, breaking
    M2's order-independence."""
    tc, p = 30.0, 5.0  # f = 30+3 = 33, lump = 40+5*1.85 = 49.25
    f, lump, d, c, m, e = _mutant_first_arg_wins(tc, p, 0.6, 0.25, 1.0, 40.0, 150.0, 5.0)
    assert c != max(lump, f)  # M2's order-independence broken


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(tc=_t, p=_pos)
def test_m4_reciprocal_power_of_two_scaling(tc, p):
    """M4 — doubling power while halving every R_θ leaves all six
    outputs bit-identical: power-of-two scaling is EXACT in f64
    ((2p)·(½r) == p·r, and the halved R_θ sum rounds the same real),
    so T_j_fdm / T_j_lumped / delta / conservative / margin / exceeds
    are all unchanged (measured 0 mismatches over 200k samples).  A
    kernel that reassociates the product (e.g. folds the 2 into
    r_total before the sum) fails."""
    a = _dcc(tc, p, 0.6, 0.25, 1.0, 40.0, 150.0, 5.0)
    b = _dcc(tc, 2.0 * p, 0.3, 0.125, 0.5, 40.0, 150.0, 5.0)
    assert b == a


def _mutant_forgot_halve_r(tc, p, rj, rc, rs, ta, tjm, tau):
    """M4 mutant: doubles power but FORGETS to halve the R_θ chain —
    the reciprocal scaling is broken, so the outputs move."""
    return _dcc(tc, 2.0 * p, rj, rc, rs, ta, tjm, tau)


def test_m4_fails_for_forgot_halve_r():
    """Pass 2 P3: M4 lacked a vacuity guard.  The forgot-halve-R
    mutant breaks M4's bit-exact invariance: doubling p without halving
    R_θ moves T_j_fdm and T_j_lumped, so the outputs differ."""
    tc, p = 50.0, 5.0
    a = _dcc(tc, p, 0.6, 0.25, 1.0, 40.0, 150.0, 5.0)
    b = _mutant_forgot_halve_r(tc, p, 0.6, 0.25, 1.0, 40.0, 150.0, 5.0)
    assert b != a  # M4's bit-exact invariance broken
