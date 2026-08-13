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
  radius to a tight tolerance (the reduction is a commutative sum in real
  arithmetic, but IEEE ``+=`` accumulation is NOT commutative at the last
  ulp, so a stated tolerance is the honest invariant — same convention as
  MR2/MR3).
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
    exp = RS(base, (cx, cy), (nx, ny), s)
    got = RS(base, (cx, cy), (nx, ny), shuffled)
    # IEEE `reduction += projection` accumulation is NOT commutative at the
    # last ulp: a known counterexample is direction (1, 0), base 5.0, slots
    # [(0,0,0.6814738914246666,0), (0,0,0.3441558891527787,0),
    #  (0,0,1.3193222224277148,0)] -> radius 2.65504799699484 vs
    # 2.6550479969948397 after shuffle (~1-in-170 of random draws). The
    # kernel is faithful — the oracle folds in the same order-dependent way —
    # so the invariant is a tight stated tolerance (the MR2/MR3 convention),
    # not a false bit-exact equality.
    assert abs(got - exp) <= 1e-9 * max(1.0, abs(exp))


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
    import math

    s = _slots(slots)
    # Domain guard 1: effective_ghost_pad_radius has a strict ``d_len <=
    # 0.0`` early-out (return base_radius unchanged, no reduction at all --
    # deterministic_phase.rs's effective_ghost_pad_radius). ``_COORD``'s
    # range is [-50, 50] but excludes only subnormals, not merely-tiny
    # NORMAL floats, so cx/cy/nx/ny can differ by ~1e-56: d_len is then a
    # tiny-but-nonzero float, so the pre-translation call takes the normal
    # (non-early-out) branch and computes a real reduction. Translating by a
    # much larger ty/tx (e.g. 1.0) can round-absorb that ~1e-56 difference
    # entirely -- (cy + ty) and (ny + ty) both collapse to the SAME float,
    # making the post-translation d_len EXACTLY 0.0 and flipping the call
    # onto the early-out branch (base_radius, no reduction). That is a
    # discrete jump across the kernel's own documented boundary, not a bug:
    # skip configs whose (real, untranslated) pin-pin distance is already
    # within noise of that boundary -- 1e-6 is many orders of magnitude
    # above the ~1e-14 (ulp-at-50) rounding a translation can introduce, so
    # it only excludes genuinely-degenerate near-coincident pins, never a
    # config where translation invariance is expected to hold.
    dx = nx - cx
    dy = ny - cy
    d_len = math.hypot(dx, dy)
    if d_len <= 1e-6:
        return  # near-zero (or zero) pin-pin distance -- boundary undefined
    # Domain guard 2: the reduction uses a strict ``projection > 0.0``
    # threshold per slot. A slot whose projection onto the pin-pin direction
    # is within ~1 ulp of 0 can flip across that threshold under translation
    # (IEEE (a+t)-(b+t) != a-b), discretely adding or removing the slot's
    # full projection from the reduction. The translation invariance holds
    # only away from that boundary, so skip configs with a near-perpendicular
    # slot. (d_len > 1e-6 here, guard 1 already returned otherwise.)
    ux = dx / d_len
    uy = dy / d_len
    for (sx0, sy0, sx1, sy1) in s:
        proj = (sx1 - sx0) * ux + (sy1 - sy0) * uy
        if abs(proj) <= 1e-9 * max(1.0, abs(sx1 - sx0) + abs(sy1 - sy0)):
            return  # boundary case -- invariant not defined there

    exp = RS(base, (cx, cy), (nx, ny), s)
    shifted = [(a + tx, b + ty, c + tx, d + ty) for (a, b, c, d) in s]
    got = RS(base, (cx + tx, cy + ty), (nx + tx, ny + ty), shifted)
    # Translation is exact in real arithmetic but NOT bit-exact in IEEE:
    # (a + t) - (b + t) can differ from a - b by 1 ulp, which perturbs
    # d_len/ux/uy/projection. Honest tight tolerance.
    assert abs(got - exp) <= 1e-9 * max(1.0, abs(exp))
