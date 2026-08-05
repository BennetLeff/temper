"""Property-based + metamorphic tests for the migrated slot_generation compute.

Wave 4, Phase 5, first slice (deterministic leaf stages). These properties
exercise the migrated
``temper_design_bundle_python.deterministic_stages.generate_slots_for_zone``
(the delegation shim ``deterministic/stages/slot_generation.py`` calls it);
bit-identical parity against the pinned pre-migration Python is asserted
separately by ``test_slot_generation_rust_differential.py``.

Five hypothesis properties (R1c):

- P1. In-zone: every slot satisfies ``x_min <= x < x_max`` and
  ``y_min <= y < y_max`` (strict upper bounds, as the loop predicates).
- P2. Row-major order: the slot sequence is lexicographically
  non-decreasing in ``(x, y)``.
- P3. First-slot anchor: the first slot is exactly
  ``(x_min + spacing/2, y_min + spacing/2)`` (bit-exact).
- P4. Determinism: the same input produces the identical sequence
  (there is no set/dict iteration anywhere in the kernel).
- P5. Row-step bound: consecutive slots in the same row differ in ``y`` by
  ``spacing`` to within a tight float tolerance (the ``+=`` accumulation
  drifts, but only by rounding, never by an algorithmic difference).

Three metamorphic relations (R1d):

- MR1. Square-zone transpose: for ``x_min == y_min`` and equal extents, the
  slot multiset of the transposed zone is the transposed multiset (exact
  after canon-sorting — both loops run the identical arithmetic).
- MR2. Power-of-two scale invariance: scaling all extents and the spacing
  by ``2^n`` scales every slot by ``2^n``, bit-exactly (IEEE scaling by a
  power of two is exact and commutes with the additions).
- MR3. Y-axis independence: two zones sharing ``y``-extent and spacing
  produce identical ``y``-value sets regardless of their ``x`` extents
  (the inner loop does not depend on ``x``).
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

import temper_design_bundle_python as _tdb

_RS = _tdb.deterministic_stages

_SPACING = st.floats(min_value=1e-3, max_value=8.0, allow_nan=False, allow_infinity=False)
_DIM = st.floats(min_value=0.0, max_value=200.0, allow_nan=False, allow_infinity=False)
_ZONE = st.tuples(_DIM, _DIM, _DIM, _DIM).filter(lambda b: b[2] >= b[0] and b[3] >= b[1])


def _slots(x_min, y_min, x_max, y_max, spacing):
    return list(_RS.generate_slots_for_zone(x_min, y_min, x_max, y_max, spacing))


@given(_ZONE, _SPACING)
@settings(max_examples=200, deadline=None)
def test_p1_slots_inside_zone(b, spacing):
    x_min, y_min, x_max, y_max = b
    for sx, sy in _slots(x_min, y_min, x_max, y_max, spacing):
        assert x_min <= sx < x_max
        assert y_min <= sy < y_max


@given(_ZONE, _SPACING)
@settings(max_examples=200, deadline=None)
def test_p2_row_major_order(b, spacing):
    x_min, y_min, x_max, y_max = b
    slots = _slots(x_min, y_min, x_max, y_max, spacing)
    for (x1, y1), (x2, y2) in zip(slots, slots[1:]):
        assert (x1, y1) <= (x2, y2)


@given(_ZONE, _SPACING)
@settings(max_examples=200, deadline=None)
def test_p3_first_slot_anchor(b, spacing):
    x_min, y_min, x_max, y_max = b
    slots = _slots(x_min, y_min, x_max, y_max, spacing)
    if slots:
        assert slots[0] == (x_min + spacing / 2, y_min + spacing / 2)


@given(_ZONE, _SPACING)
@settings(max_examples=200, deadline=None)
def test_p4_determinism(b, spacing):
    x_min, y_min, x_max, y_max = b
    assert _slots(x_min, y_min, x_max, y_max, spacing) == _slots(x_min, y_min, x_max, y_max, spacing)


@given(_ZONE, _SPACING)
@settings(max_examples=200, deadline=None)
def test_p5_row_step_bound(b, spacing):
    x_min, y_min, x_max, y_max = b
    slots = _slots(x_min, y_min, x_max, y_max, spacing)
    # Group by row (x value): consecutive slots share x until x changes.
    for (x1, y1), (x2, y2) in zip(slots, slots[1:]):
        if x1 == x2:
            assert abs((y2 - y1) - spacing) <= 1e-9 * max(1.0, abs(spacing))


@given(_ZONE, _SPACING)
@settings(max_examples=100, deadline=None)
def test_mr1_square_transpose(b, spacing):
    x_min, y_min, x_max, y_max = b
    if x_max - x_min != y_max - y_min or x_min != y_min:
        return  # only square zones anchored at the diagonal
    slots = _slots(x_min, y_min, x_max, y_max, spacing)
    transposed = [(sy, sx) for sx, sy in slots]
    # Transposed zone (swap roles of x and y): the two loops are identical
    # arithmetic, so the slot multiset transposes exactly.
    slots_t = _slots(y_min, x_min, y_max, x_max, spacing)
    assert sorted(transposed) == sorted(slots_t)


@given(_ZONE, _SPACING, st.integers(min_value=-8, max_value=8))
@settings(max_examples=150, deadline=None)
def test_mr2_pow2_scale(b, spacing, n):
    k = 2.0**n
    x_min, y_min, x_max, y_max = b
    slots = _slots(x_min, y_min, x_max, y_max, spacing)
    scaled = _slots(k * x_min, k * y_min, k * x_max, k * y_max, k * spacing)
    assert len(scaled) == len(slots)
    for (sx, sy), (kx, ky) in zip(slots, scaled):
        assert kx.hex() == (k * sx).hex()
        assert ky.hex() == (k * sy).hex()


@given(_ZONE, _ZONE, _SPACING)
@settings(max_examples=100, deadline=None)
def test_mr3_y_axis_independence(b1, b2, spacing):
    x_min, y_min, x_max, y_max = b1
    if (b2[1], b2[3]) != (y_min, y_max):
        return  # requires equal y-extent
    slots1 = _slots(x_min, y_min, x_max, y_max, spacing)
    slots2 = _slots(b2[0], y_min, b2[2], y_max, spacing)
    ys1 = sorted({y for _, y in slots1})
    ys2 = sorted({y for _, y in slots2})
    assert ys1 == ys2
