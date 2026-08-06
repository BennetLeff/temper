"""Property-based tests for the migrated _phase_rotation compute.

Wave 4, Phase 5, final leaves. Properties exercise the migrated
``temper_design_bundle_python.deterministic_phase.effective_ghost_pad_radius``
(the delegation shim ``deterministic/stages/_phase_rotation.py`` calls it);
bit-identical parity against the pinned pre-migration Python is asserted
separately by ``test_phase_rotation_rust_differential.py``.

Five properties (R1c):

- P1. Clamped output: `0.0 <= result <= base_radius` (the max(0, ...) clamp
  and the non-negative projection accumulation).
- P2. Empty-slot invariance: no isolation slots -> `base_radius` unchanged.
- P3. Perpendicular-slot invariance: for an axis-aligned creepage direction,
  a slot exactly perpendicular to it contributes a bit-exact zero projection
  and the radius is unchanged.
- P4. Coincident-pin early-out: `current == nearest` -> `base_radius`.
- P5. Determinism: the same input produces the identical radius.

Three metamorphic relations (R1d):

- MR1. Slot-order independence: permuting the slot list does not change the
  radius (the reduction is a commutative sum).
- MR2. Power-of-two scale invariance: scaling all inputs by `2^n` scales the
  radius by `2^n` to a tight tolerance (the Dekker hypot normalizes, so the
  result carries the scale; stated tolerance).
- MR3. Translation invariance: translating current/nearest/slots together
  leaves the radius unchanged (only differences enter the kernel).
"""

from __future__ import annotations

import random

import temper_design_bundle_python as _tdb
from hypothesis import given, settings
from hypothesis import strategies as st

_DP = _tdb.deterministic_phase
RS = _DP.effective_ghost_pad_radius_py

_COORD = st.floats(
    min_value=-50.0, max_value=50.0, allow_nan=False, allow_infinity=False, allow_subnormal=False
)
_RADIUS = st.floats(min_value=0.1, max_value=25.0, allow_nan=False, allow_infinity=False)
_SLOT = st.tuples(_COORD, _COORD, _COORD, _COORD)


def _slots(list_of_tuples):
    return list(list_of_tuples)


@given(_RADIUS, _COORD, _COORD, _COORD, _COORD, st.lists(_SLOT, max_size=5))
@settings(max_examples=200, deadline=None)
def test_p1_result_clamped(base, cx, cy, nx, ny, slots):
    r = RS(base, (cx, cy), (nx, ny), _slots(slots))
    assert 0.0 <= r <= base


@given(_RADIUS, _COORD, _COORD, _COORD, _COORD)
@settings(max_examples=200, deadline=None)
def test_p2_empty_slots_unchanged(base, cx, cy, nx, ny):
    assert RS(base, (cx, cy), (nx, ny), []) == base


@given(_RADIUS, st.floats(min_value=0.01, max_value=40.0))
@settings(max_examples=100, deadline=None)
def test_p3_perpendicular_slot_no_reduction(base, dist):
    """Creepage direction along +x (nearest on the x-axis); a slot exactly
    perpendicular (pure +/-y) has sdx == 0 -> projection == 0.0 bit-exactly."""
    for sign in (1.0, -1.0):
        r = RS(base, (0.0, 0.0), (dist, 0.0), [(0.0, 0.0, 0.0, sign * 5.0)])
        assert r == base


@given(_RADIUS, _COORD, _COORD, st.lists(_SLOT, max_size=4))
@settings(max_examples=200, deadline=None)
def test_p4_coincident_pins_unchanged(base, cx, cy, slots):
    assert RS(base, (cx, cy), (cx, cy), _slots(slots)) == base


@given(_RADIUS, _COORD, _COORD, _COORD, _COORD, st.lists(_SLOT, max_size=5))
@settings(max_examples=200, deadline=None)
def test_p5_determinism(base, cx, cy, nx, ny, slots):
    s = _slots(slots)
    assert RS(base, (cx, cy), (nx, ny), s) == RS(base, (cx, cy), (nx, ny), s)


@given(_RADIUS, _COORD, _COORD, _COORD, _COORD, st.lists(_SLOT, max_size=4))
@settings(max_examples=100, deadline=None)
def test_mr1_slot_order_independent(base, cx, cy, nx, ny, slots):
    s = _slots(slots)
    shuffled = list(s)
    rng = random.Random(42)
    rng.shuffle(shuffled)
    assert RS(base, (cx, cy), (nx, ny), s) == RS(base, (cx, cy), (nx, ny), shuffled)


@given(
    _RADIUS,
    _COORD, _COORD, _COORD, _COORD,
    st.lists(_SLOT, max_size=4),
    st.integers(min_value=-5, max_value=5),
)
@settings(max_examples=100, deadline=None)
def test_mr2_pow2_scale(base, cx, cy, nx, ny, slots, n):
    k = 2.0**n
    s = _slots(slots)
    scaled = [(k * a, k * b, k * c, k * d) for (a, b, c, d) in s]
    exp = RS(base, (cx, cy), (nx, ny), s)
    got = RS(k * base, (k * cx, k * cy), (k * nx, k * ny), scaled)
    # The Dekker hypot is exact under power-of-two scaling, but the
    # normalization / projection products are not; honest tight tolerance.
    assert abs(got - k * exp) <= 1e-9 * max(1.0, abs(k * exp))


@given(_RADIUS, _COORD, _COORD, _COORD, _COORD, st.lists(_SLOT, max_size=4), _COORD, _COORD)
@settings(max_examples=100, deadline=None)
def test_mr3_translation_invariance(base, cx, cy, nx, ny, slots, tx, ty):
    s = _slots(slots)
    exp = RS(base, (cx, cy), (nx, ny), s)
    shifted = [(a + tx, b + ty, c + tx, d + ty) for (a, b, c, d) in s]
    got = RS(base, (cx + tx, cy + ty), (nx + tx, ny + ty), shifted)
    # Translation is exact in real arithmetic but NOT bit-exact in IEEE:
    # (a + t) - (b + t) can differ from a - b by 1 ulp, which perturbs
    # d_len/ux/uy/projection. Honest tight tolerance.
    assert abs(got - exp) <= 1e-9 * max(1.0, abs(exp))
