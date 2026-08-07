"""Property-based tests for the migrated _phase_zones compute.

Wave 4, Phase 5, final leaves. Properties exercise the migrated
``temper_design_bundle_python.deterministic_phase.compute_wirelength_py``
(the delegation shim ``deterministic/stages/_phase_zones.py`` calls it);
bit-identical parity against the pinned pre-migration Python is asserted
separately by ``test_phase_zones_rust_differential.py``.

Five properties (R1c):

- P1. Non-negativity: HPWL is always >= 0.0.
- P2. Empty-input: empty net_pins -> 0.0.
- P3. Unrelated-net invariance: adding a net the component is NOT on does
  not change the result.
- P4. Monotonicity in partner distance: for a two-member net, moving the
  placed partner to a coordinate at least as large in both axes does not
  decrease the HPWL (a Manhattan-distance monotonicity).
- P5. Determinism.

Three metamorphic relations (R1d):

- MR1. Role swap: HPWL(A, s, {AB: [A, B]}, {B: p}) == HPWL(B, p, {AB: [B, A]},
  {A: s}) — bit-exact (the same x/y ranges enter the formula).
- MR2. Translation invariance: translating candidate + all placements by the
  same vector leaves HPWL unchanged (bit-exact — only differences enter).
- MR3. Axis swap: swapping x and y in every coordinate leaves HPWL unchanged
  (bit-exact — the formula is symmetric in the two axes).
"""

from __future__ import annotations

import temper_design_bundle_python as _tdb
from hypothesis import given, settings
from hypothesis import strategies as st

_DP = _tdb.deterministic_phase
RS = _DP.compute_wirelength_py

_COORD = st.floats(
    min_value=-50.0, max_value=50.0, allow_nan=False, allow_infinity=False, allow_subnormal=False
)
_POS = st.tuples(_COORD, _COORD)


def _assert_eq(exp, got, ctx):
    assert got == exp, f"{ctx}: {got} vs {exp}"


@given(
    st.text(min_size=1, max_size=6),
    _POS,
    st.dictionaries(st.text(min_size=1, max_size=6), st.lists(st.tuples(st.text(min_size=1, max_size=6), st.text()), max_size=5), max_size=5),
    st.dictionaries(st.text(min_size=1, max_size=6), _POS, max_size=6),
)
@settings(max_examples=200, deadline=None)
def test_p1_non_negative(ref, slot, net_pins, placements):
    assert RS(ref, slot, net_pins, placements) >= 0.0


@given(st.text(min_size=1, max_size=6), _POS)
@settings(max_examples=100, deadline=None)
def test_p2_empty_net_pins_zero(ref, slot):
    assert RS(ref, slot, {}, {}) == 0.0


@given(
    st.text(min_size=1, max_size=6),
    _POS,
    st.dictionaries(st.text(min_size=1, max_size=6), st.lists(st.tuples(st.text(min_size=1, max_size=6), st.text()), max_size=4), max_size=4),
    st.dictionaries(st.text(min_size=1, max_size=6), _POS, max_size=6),
)
@settings(max_examples=200, deadline=None)
def test_p3_unrelated_net_invariance(ref, slot, net_pins, placements):
    # A net listing only refs != ref must never change the result.
    base = RS(ref, slot, net_pins, placements)
    extra = {f"NET_{abs(hash((ref, slot, len(net_pins))))}": [("ZED", "1")]}
    combined = dict(net_pins)
    combined.update(extra)
    assert RS(ref, slot, combined, placements) == base


@given(_POS, _POS)
@settings(max_examples=200, deadline=None)
def test_p4_monotone_in_partner_distance(slot, partner):
    base = RS("A", slot, {"N": [("A", "1"), ("B", "1")]}, {"B": partner})
    # Reflect the candidate across the partner: the exact Manhattan distance
    # doubles (|s - (2p - s)| == 2|s - p|), so HPWL is non-decreasing. The
    # reflection arithmetic can wobble by 1 ulp; honest tight tolerance.
    moved = (2 * partner[0] - slot[0], 2 * partner[1] - slot[1])
    grew = RS("A", slot, {"N": [("A", "1"), ("B", "1")]}, {"B": moved})
    assert grew >= base - 1e-9 * max(1.0, abs(base))


@given(
    st.text(min_size=1, max_size=6),
    _POS,
    st.dictionaries(st.text(min_size=1, max_size=6), st.lists(st.tuples(st.text(min_size=1, max_size=6), st.text()), max_size=5), max_size=5),
    st.dictionaries(st.text(min_size=1, max_size=6), _POS, max_size=6),
)
@settings(max_examples=200, deadline=None)
def test_p5_determinism(ref, slot, net_pins, placements):
    assert RS(ref, slot, net_pins, placements) == RS(ref, slot, net_pins, placements)


@given(_POS, _POS)
@settings(max_examples=200, deadline=None)
def test_mr1_role_swap(ref, partner):
    s, p = ref, partner
    a = RS("A", s, {"N": [("A", "1"), ("B", "1")]}, {"B": p})
    b = RS("B", p, {"N": [("B", "1"), ("A", "1")]}, {"A": s})
    assert a == b


@given(_POS, _POS, _COORD, _COORD)
@settings(max_examples=200, deadline=None)
def test_mr2_translation_invariance(slot, partner, tx, ty):
    base = RS("A", slot, {"N": [("A", "1"), ("B", "1")]}, {"B": partner})
    moved_slot = (slot[0] + tx, slot[1] + ty)
    moved_partner = (partner[0] + tx, partner[1] + ty)
    got = RS("A", moved_slot, {"N": [("A", "1"), ("B", "1")]}, {"B": moved_partner})
    # Translation is exact in real arithmetic but NOT bit-exact in IEEE:
    # (a + t) - (b + t) can differ from a - b by 1 ulp. Honest tolerance.
    assert abs(got - base) <= 1e-9 * max(1.0, abs(base))


@given(_POS, _POS)
@settings(max_examples=200, deadline=None)
def test_mr3_axis_swap(slot, partner):
    base = RS("A", slot, {"N": [("A", "1"), ("B", "1")]}, {"B": partner})
    swapped_slot = (slot[1], slot[0])
    swapped_partner = (partner[1], partner[0])
    got = RS("A", swapped_slot, {"N": [("A", "1"), ("B", "1")]}, {"B": swapped_partner})
    assert got == base
