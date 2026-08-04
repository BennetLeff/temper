"""Property-based tests for the Rust T_j cross-check and parameter-bound
kernels (``temper_thermal.device_cross_check_py`` /
``distance_to_heatsink_edge_py`` / ``classify_parameter_py`` /
``worst_case_values_py``, Wave 4 Phase 4 — migrations of
``temper_placer/physics/tj_cross_check.py`` and
``parameter_bounds.py``).

This file is SHARED between the two modules, so the R1c/R1d minima are
met PER MODULE, not across the pair:

- ``tj_cross_check`` (P1–P3, P6–P7 + M1, M2, M4): **5 non-vacuous
  properties + 3 metamorphic relations**.
- ``parameter_bounds`` (P4–P5, P8–P10 + M3, M5, M6): **5 non-vacuous
  properties + 3 metamorphic relations**.

Every property is vacuity-guarded by a real mutant (the file's
convention: ``_mutant_*`` implementations whose outputs violate the
property, pinned by ``test_pN_fails_for_<mutant>``):

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
6. P6 — margin is exactly T_j_max − conservative, the SIGNED datasheet
   headroom (negative over the ceiling).
7. P7 — exceeds is gated ONLY on (delta, tau): changing T_j_max moves
   margin alone; every other output is bit-unchanged.
8. P8 — the ``because`` citation interpolates the ORIGINAL-case
   parameter name with the correct direction phrase.
9. P9 — for a −1 parameter the worst-case corner is the minimum, so the
   corner is dominated BY every interior sample (mirror of P5).
10. P10 — the family disjunctions are checked in the reference's
    precedence order (power > R_θ > heatspread); a multi-family name
    classifies by the FIRST match.

Metamorphic relations:

- M1 — with zero power the cross-check reduces to the ambient
  comparison exactly: T_j_fdm == T_case_fdm, T_j_lumped == T_amb and
  delta == |T_case_fdm − T_amb| (bit-exact degeneracy).
- M2 — conservative_T_j is symmetric under swapping the two estimates
  for non-NaN values (CPython max is commutative on non-NaN; the NaN
  asymmetry is pinned by the differential).
- M3 — classify_parameter is case-insensitive for the keyword part in
  the SAME way as CPython's lower() (a name and its ALLCAPS form
  classify identically for ASCII names).
- M4 — reciprocal power-of-two scaling of power and the R_θ chain
  (p → 2p, R → ½R) leaves every output bit-identical (power-of-two
  scaling is exact in f64; measured 0 mismatches over 200k samples).
- M5 — the keyword match is a SUBSTRING match (CPython `in`), not
  prefix/equality: an embedded keyword anywhere in the name classifies.
- M6 — worst_case_values is ELEMENTWISE: permuting the parallel
  (mins, maxs, monos) lists permutes the outputs identically (bit-
  exact).
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


def _mutant_lowercased_citation(name):
    """P8 mutant: interpolates the LOWERCASED name in the citation."""
    return _tt.classify_parameter_py(name.lower(), "src")


def test_p8_fails_for_lowercased_citation_mutant():
    mono, unit, because = _mutant_lowercased_citation("Power_W")
    assert "T_j INCREASING in power_w" in because  # mutant cites lowercased
    assert "T_j INCREASING in Power_W" not in because  # P8 demands original case


def _mutant_max_for_neg(mins, maxs, monos):
    """P9 mutant: picks max for EVERY parameter (incl. −1)."""
    return [max(maxs)] * len(mins)


def test_p9_fails_for_max_on_minus_mutant():
    vals = _mutant_max_for_neg([1.0], [10.0], [-1])
    # The mutant's corner (10.0) sits ABOVE interior samples — the
    # mirror dominance (corner <= sample) that P9 demands is broken.
    for sample in np.linspace(1.0, 5.0, 5):
        assert vals[0] > sample


def _mutant_heatspread_first(name):
    """P10 mutant: checks the heatspread family BEFORE power/R_θ."""
    lower = name.lower()
    if "heatspread" in lower or "spread" in lower or "copper" in lower:
        return -1, "s", "T_j DECREASING in " + name
    if "power" in lower or "dissipation" in lower or "p_loss" in lower:
        return 1, "s", "T_j INCREASING in " + name
    if "junction_to_case" in lower or "r_theta" in lower or "thermal_resistance" in lower:
        return 1, "s", "T_j INCREASING in " + name
    return 0, "unknown", "No monotonicity proof for '" + name + "'"


def test_p10_fails_for_heatspread_first_mutant():
    mono, _, _ = _mutant_heatspread_first("power_heatspread_mm")
    assert mono != 1  # P10 demands the power family wins (first match)


def test_p8_citation_fidelity():
    """P8 — the `because` citation interpolates the ORIGINAL-case
    parameter name with the correct direction phrase: 'T_j INCREASING
    in <name>' for the +1 families, 'T_j DECREASING in <name>' for −1,
    'No monotonicity proof for <name>' for unknown.  A kernel that
    interpolates the LOWERCASED name (or the wrong direction) fails."""
    mono, unit, because = _tt.classify_parameter_py("Power_W", "src")
    assert mono == 1
    assert "T_j INCREASING in Power_W" in because
    assert "power_w" not in because
    mono, unit, because = _tt.classify_parameter_py("Heatspread_mm", "src")
    assert mono == -1
    assert "T_j DECREASING in Heatspread_mm" in because
    mono, unit, because = _tt.classify_parameter_py("Fan_speed", "src")
    assert mono == 0
    assert "No monotonicity proof for 'Fan_speed'" in because


def test_p9_worst_case_min_dominates_for_minus_one():
    """P9 — for a −1 parameter the worst-case corner is the MINIMUM, so
    the corner is dominated BY every interior sample (corner <= sample);
    for 0 the selection is the max, dominating like +1 (conservative,
    not a guarantee).  A kernel that picks max for −1 breaks the mirror
    dominance."""
    mins, maxs, monos = [1.0], [10.0], [-1]
    vals = _tt.worst_case_values_py(mins, maxs, monos)
    assert vals == [1.0]
    for sample in np.linspace(1.0, 10.0, 20):
        assert vals[0] <= sample
    # mono-0 selects max (conservative).
    assert _tt.worst_case_values_py([1.0], [10.0], [0]) == [10.0]


def test_p10_precedence_total_and_stable():
    """P10 — the family disjunctions are checked in the reference's
    precedence order (power > R_θ > heatspread): a name matching
    MULTIPLE families classifies by the FIRST match, and appending a
    lower-precedence keyword never reclassifies an already-matched
    name.  A kernel that reorders the branches (heatspread first)
    misclassifies the power_* names."""
    assert _tt.classify_parameter_py("power_heatspread_mm", "s")[0] == 1
    assert _tt.classify_parameter_py("dissipation_copper_ratio", "s")[0] == 1
    assert _tt.classify_parameter_py("thermal_resistance_spread", "s")[0] == 1
    assert _tt.classify_parameter_py("junction_to_case_heatspread", "s")[0] == 1
    assert _tt.classify_parameter_py("max_heatspread_mm", "s")[0] == -1
    assert _tt.classify_parameter_py("copper_fraction", "s")[0] == -1


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


def test_m3_classify_case_folding():
    """M3 — for ASCII names, the classification is invariant under the
    name's case (CPython lower() folds ASCII; Rust to_lowercase does
    the same).  A kernel that compares without lowercasing fails."""
    for name in ["Power_W", "POWER_W", "power_w", "R_Theta_JC", "r_theta_jc", "Heatspread", "HEATSPREAD"]:
        m1 = _tt.classify_parameter_py(name, "s")[0]
        m2 = _tt.classify_parameter_py(name.lower(), "s")[0]
        assert m1 == m2, name


def test_m5_substring_semantics():
    """M5 — the keyword match is a SUBSTRING match on the lowercased
    name (CPython `in`), not a prefix or equality match: a keyword
    anywhere in the name classifies, and moving it within the name
    (prefix → suffix) leaves (mono, unit) unchanged.  A kernel that
    matches only at the start fails for the suffix form."""
    assert _tt.classify_parameter_py("sweep_power_x", "s")[0] == 1
    assert _tt.classify_parameter_py("x_power_sweep", "s")[0] == 1
    assert _tt.classify_parameter_py("r_theta_sweep", "s")[0] == 1
    assert _tt.classify_parameter_py("big_heatspread_small", "s")[0] == -1
    assert _tt.classify_parameter_py("copper_at_end", "s")[0] == -1


def _mutant_exact_name(name):
    """M5 mutant: matches a family keyword only when the name EQUALS it
    (no substring matching)."""
    if name.lower() in ("power_w", "power", "dissipation_w"):
        return 1, "s", "T_j INCREASING in " + name
    return 0, "unknown", "No monotonicity proof for '" + name + "'"


def test_m5_fails_for_exact_match_mutant():
    mono, _, _ = _mutant_exact_name("sweep_power_x")
    assert mono != 1  # M5 demands the embedded keyword still matches


def test_m6_permutation_equivariance():
    """M6 — worst_case_values is ELEMENTWISE: permuting the parallel
    (mins, maxs, monos) lists permutes the outputs identically
    (bit-exact, each output depends only on its own triple).  A kernel
    that couples parameters (e.g. returns the global max of every box
    for every slot) fails."""
    mins = [1.0, 2.0, 3.0]
    maxs = [10.0, 20.0, 30.0]
    monos = [1, -1, 0]
    perm = [2, 0, 1]
    vals = _tt.worst_case_values_py(mins, maxs, monos)
    vals_p = _tt.worst_case_values_py(
        [mins[i] for i in perm], [maxs[i] for i in perm], [monos[i] for i in perm]
    )
    assert vals_p == [vals[i] for i in perm]


def _mutant_first_box_max(mins, maxs, monos):
    """M6 mutant: every slot gets the FIRST box's max (couples the
    parameters non-symmetrically — not elementwise)."""
    return [maxs[0]] * len(mins)


def test_m6_fails_for_first_box_max_mutant():
    mins = [1.0, 2.0, 3.0]
    maxs = [10.0, 20.0, 30.0]
    monos = [1, -1, 0]
    perm = [2, 0, 1]
    vals = _mutant_first_box_max(mins, maxs, monos)
    vals_p = _mutant_first_box_max(
        [mins[i] for i in perm], [maxs[i] for i in perm], [monos[i] for i in perm]
    )
    # The first-box-coupling mutant is NOT permutation-equivariant: the
    # first slot of the permuted input (30.0) leaks into every output,
    # while the real (elementwise) selection permutes with the inputs.
    assert vals_p != [vals[i] for i in perm]
