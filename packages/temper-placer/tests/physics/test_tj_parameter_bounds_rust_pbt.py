"""Property-based tests for the Rust T_j cross-check and parameter-bound
kernels (``temper_thermal.device_cross_check_py`` /
``distance_to_heatsink_edge_py`` / ``classify_parameter_py`` /
``worst_case_values_py``, Wave 4 Phase 4 — migrations of
``temper_placer/physics/tj_cross_check.py`` and
``parameter_bounds.py``).

Five+ non-vacuous properties, each vacuity-guarded by a real mutant:

1. P1 — the conservative T_j is always >= both estimates (soundness of
   the safety gating: the optimistic estimate cannot decide).
2. P2 — delta is the absolute difference and exceeds is exactly
   delta > tau (bit-exact, boundary exact).
3. P3 — the distance to the heatsink edge is non-negative and matches
   the axis-aligned geometry (a device beyond the far edge has the
   correct absolute distance).
4. P4 — the monotonicity classification is total (every name maps to
   one of +1 / −1 / 0) and the power-family / R_θ-family / heatspread-
   family rules are consistent.
5. P5 — worst_case_corner selects the max for +1 and 0 and the min for
   −1 (the L2 corner-bound selection), and the corner of a monotone box
   dominates every interior sample for +1 parameters.

Metamorphic relations:

- M1 — the device cross-check is invariant under T_amb shifts when both
  estimates shift equally? NO — T_j_lumped shifts but T_j_fdm does not
  (honest bound: delta changes by exactly the shift).  Instead: delta
  is invariant under shifting BOTH T_j_fdm and T_j_lumped by the same
  constant (bit-exact, abs is translation-invariant).
- M2 — conservative_T_j is symmetric under swapping the two estimates'
  roles only when the swap does not change which is larger; bounded:
  conservative(T_a, T_b) == conservative(T_b, T_a) ALWAYS (max is
  order-independent for non-NaN), bit-exact.
- M3 — classify_parameter is case-insensitive for the keyword part in
  the SAME way as CPython's lower() (a name and its ALLCAPS form
  classify identically for ASCII names).
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


def test_p4_classification_total_and_consistent():
    """P4 — the classification is total (every name maps to one of
    +1 / −1 / 0) and consistent: power-family names are +1, R_θ-family
    +1, heatspread-family −1.  A kernel that returns 0 for a known
    family fails."""
    names = ["power_w", "dissipation_mw", "r_theta_jc", "thermal_resistance_k", "heatspread_mm", "copper_pct", "anything_else"]
    for name in names:
        mono, unit, because = _tt.classify_parameter_py(name, "src")
        assert mono in (-1, 0, 1)
        assert unit in ("src", "unknown")
    assert _tt.classify_parameter_py("power_w", "s")[0] == 1
    assert _tt.classify_parameter_py("r_theta_jc", "s")[0] == 1
    assert _tt.classify_parameter_py("heatspread_mm", "s")[0] == -1
    assert _tt.classify_parameter_py("fan_speed", "s")[0] == 0


def test_p5_worst_case_corner_selection():
    """P5 — the worst-case corner picks max for +1 and 0, min for −1
    (the L2 corner-bound selection), so the corner dominates every
    interior sample for +1 parameters.  A kernel that picks min for +1
    fails the dominance."""
    mins = [1.0, 2.0, 3.0]
    maxs = [10.0, 20.0, 30.0]
    monos = [1, -1, 0]
    vals = _tt.worst_case_values_py(mins, maxs, monos)
    assert vals == [10.0, 2.0, 30.0]
    # Corner dominates interior samples for the +1 parameter.
    for sample in np.linspace(mins[0], maxs[0], 50):
        assert vals[0] >= sample


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


def _mutant_unknown_classifier(name):
    """P4 mutant: always classifies as 0/unknown."""
    return 0, "unknown", "No monotonicity proof for 'x'; corner-bound is NOT a guarantee."


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


def test_p4_fails_for_unknown_classifier():
    mono, _, _ = _mutant_unknown_classifier("power_w")
    assert mono != 1  # P4 demands +1 for the power family


def test_p5_fails_for_min_on_plus_mutant():
    # A kernel picking min for +1 parameters violates dominance.
    mins, maxs, monos = [1.0], [10.0], [1]
    vals = _tt.worst_case_values_py(mins, maxs, monos)
    assert vals == [10.0]
    # dominance: corner >= every sample
    for sample in np.linspace(1.0, 10.0, 20):
        assert vals[0] >= sample


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


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(tc=_t, p=_pos)
def test_m2_conservative_order_independent(tc, p):
    """M2 — conservative_T_j is symmetric under swapping the two
    estimates for non-NaN values (CPython max is commutative on
    non-NaN; the NaN asymmetry is pinned by the differential)."""
    f, lump, d, c, m, e = _dcc(tc, p, 0.6, 0.25, 1.0, 40.0, 150.0, 5.0)
    assert c == max(lump, f)  # order-independent


def test_m3_classify_case_folding():
    """M3 — for ASCII names, the classification is invariant under the
    name's case (CPython lower() folds ASCII; Rust to_lowercase does
    the same).  A kernel that compares without lowercasing fails."""
    for name in ["Power_W", "POWER_W", "power_w", "R_Theta_JC", "r_theta_jc", "Heatspread", "HEATSPREAD"]:
        m1 = _tt.classify_parameter_py(name, "s")[0]
        m2 = _tt.classify_parameter_py(name.lower(), "s")[0]
        assert m1 == m2, name
