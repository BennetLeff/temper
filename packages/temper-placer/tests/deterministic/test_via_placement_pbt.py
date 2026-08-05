"""Property-based + metamorphic tests for the migrated via_placement compute.

Wave 4, Phase 5, first slice (deterministic leaf stages). These properties
exercise the migrated ``temper_geometry`` via-placement functions; bit-
identical parity against the pinned pre-migration Python is asserted
separately by ``test_via_placement_rust_differential.py``.

Five hypothesis properties (R1c):

- P1. Self-distance is exactly zero.
- P2. ``is_via_position_valid`` is monotone non-increasing in
  ``min_clearance``: valid at clearance ``c`` implies valid at every
  ``c' <= c`` (required distance grows with clearance).
- P3. ``is_via_position_valid`` is monotone non-decreasing in
  ``via_mask_radius``: valid at radius ``a`` implies valid at every
  ``b <= a``.
- P4. Adding a pad never flips valid -> invalid: ``valid(pads + extra)``
  implies ``valid(pads)``.
- P5. ``place_via_with_clearance`` returns a *valid* position whenever it
  returns non-``None``, and returns the target unchanged when the target
  is already valid.

Three metamorphic relations (R1d):

- MR1. Pad-order invariance: permuting the pad list does not change any
  result (the validity check is a conjunction over all pads).
- MR2. Reflection symmetry: reflecting the whole scene through the origin
  preserves validity exactly (``pow(-dx, 2.0) == pow(dx, 2.0)``).
- MR3. Spiral candidates only: any non-target returned candidate lies
  exactly on the 8x8 search lattice ``target + r * (cos, sin)`` for
  ``r`` in the fixed radius list and a multiple of 45 degrees.
"""

from __future__ import annotations

import math

import temper_geometry as _tg
from hypothesis import given, settings
from hypothesis import strategies as st

_COORD = st.floats(min_value=-20.0, max_value=20.0, allow_nan=False, allow_infinity=False)
_RAD = st.floats(min_value=1e-3, max_value=2.0, allow_nan=False, allow_infinity=False)
_PADS = st.lists(
    st.tuples(
        st.tuples(_COORD, _COORD),  # position
        _RAD,  # radius
        st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    ),
    max_size=6,
)

_RADII = [0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0]


def _flat(pads):
    out = []
    for (x, y), r, m in pads:
        out.extend([x, y, r, m])
    return out


@given(_COORD, _COORD)
@settings(max_examples=200, deadline=None)
def test_p1_self_distance_zero(x, y):
    assert _tg.via_distance(x, y, x, y) == 0.0
    assert _tg.via_distance(x, y, x, y).hex() == 0.0.hex()


@given(st.tuples(_COORD, _COORD), _PADS, _RAD, st.floats(min_value=0.0, max_value=0.5))
@settings(max_examples=200, deadline=None)
def test_p2_clearance_monotonic(pos, pads, vmr, c):
    if not _tg.is_via_position_valid(pos[0], pos[1], _flat(pads), vmr, c):
        return  # property is one-directional: only constrains valid inputs
    smaller = max(0.0, c - 0.05)
    assert _tg.is_via_position_valid(pos[0], pos[1], _flat(pads), vmr, smaller) is True


@given(st.tuples(_COORD, _COORD), _PADS, st.floats(min_value=0.0, max_value=0.3), _RAD)
@settings(max_examples=200, deadline=None)
def test_p3_mask_radius_monotonic(pos, pads, mc, vmr):
    if not _tg.is_via_position_valid(pos[0], pos[1], _flat(pads), vmr, mc):
        return  # property is one-directional: only constrains valid inputs
    smaller = max(1e-3, vmr - 0.1)
    assert _tg.is_via_position_valid(pos[0], pos[1], _flat(pads), smaller, mc) is True


@given(st.tuples(_COORD, _COORD), _PADS, _RAD, st.floats(min_value=0.0, max_value=0.3))
@settings(max_examples=150, deadline=None)
def test_p4_extra_pad_never_helps(pos, pads, vmr, mc):
    flat = _flat(pads)
    valid_before = _tg.is_via_position_valid(pos[0], pos[1], flat, vmr, mc)
    extra = (pos[0] + 0.7, pos[1] - 0.4, 0.2, 0.1)
    valid_after = _tg.is_via_position_valid(pos[0], pos[1], flat + list(extra), vmr, mc)
    # Adding a pad can only turn True -> False, never False -> True.
    assert (valid_after and not valid_before) is False


@given(st.tuples(_COORD, _COORD), _PADS, _RAD, st.floats(min_value=0.0, max_value=0.3))
@settings(max_examples=150, deadline=None)
def test_p5_place_returns_valid_or_target(pos, pads, vmr, mc):
    flat = _flat(pads)
    result = _tg.place_via_with_clearance(pos[0], pos[1], flat, vmr, mc, 2.0)
    if _tg.is_via_position_valid(pos[0], pos[1], flat, vmr, mc):
        # Target already valid -> returned unchanged.
        assert result == pos
    elif result is not None:
        assert _tg.is_via_position_valid(result[0], result[1], flat, vmr, mc) is True


@given(st.tuples(_COORD, _COORD), _PADS, _RAD, st.floats(min_value=0.0, max_value=0.3))
@settings(max_examples=150, deadline=None)
def test_mr1_pad_order_invariance(pos, pads, vmr, mc):
    flat = _flat(pads)
    shuffled = _flat(list(reversed(pads)))
    a = _tg.place_via_with_clearance(pos[0], pos[1], flat, vmr, mc, 2.0)
    b = _tg.place_via_with_clearance(pos[0], pos[1], shuffled, vmr, mc, 2.0)
    assert a == b
    assert _tg.is_via_position_valid(pos[0], pos[1], flat, vmr, mc) == _tg.is_via_position_valid(
        pos[0], pos[1], shuffled, vmr, mc
    )


@given(st.tuples(_COORD, _COORD), _PADS, _RAD, st.floats(min_value=0.0, max_value=0.3))
@settings(max_examples=150, deadline=None)
def test_mr2_reflection(pos, pads, vmr, mc):
    flat = _flat(pads)
    mirrored = []
    for (x, y), r, m in pads:
        mirrored.extend([-x, -y, r, m])
    a = _tg.is_via_position_valid(pos[0], pos[1], flat, vmr, mc)
    b = _tg.is_via_position_valid(-pos[0], -pos[1], mirrored, vmr, mc)
    assert a == b


@given(st.tuples(_COORD, _COORD), _PADS, _RAD, st.floats(min_value=0.0, max_value=0.3))
@settings(max_examples=150, deadline=None)
def test_mr3_candidates_on_spiral_lattice(pos, pads, vmr, mc):
    flat = _flat(pads)
    result = _tg.place_via_with_clearance(pos[0], pos[1], flat, vmr, mc, 2.0)
    if result is None or (result[0], result[1]) == pos:
        return  # vacuous for these inputs; only non-target candidates are constrained
    rx, ry = result
    found = False
    for r in _RADII:
        for deg in range(0, 360, 45):
            rad = math.radians(deg)
            cand = (pos[0] + r * math.cos(rad), pos[1] + r * math.sin(rad))
            if cand[0].hex() == rx.hex() and cand[1].hex() == ry.hex():
                found = True
                break
        if found:
            break
    assert found, f"candidate {result} not on the 8x8 spiral lattice"
