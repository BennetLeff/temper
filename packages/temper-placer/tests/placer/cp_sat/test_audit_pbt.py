"""Property-based tests for the Rust audit geometry (Wave 3 #5 — the R24
post-solve audit's Chebyshev-gap recomputation).

Five invariants plus three metamorphic relations (the migration
roadmap's R24-gate requirements):

1. Non-negativity for separated boxes
2. Symmetry (bit-exact — the gap formula is symmetric)
3. Monotonicity in box size (expanding a box can only shrink the gap)
4. Translation invariance (closeness — t is not exactly representable)
5. Chebyshev-vs-Euclidean bound (the load-bearing R24 soundness
   property: the Chebyshev gap under-approximates the Euclidean gap,
   so a SEPARATED check using it is conservative, never over-claims
   separation)

Metamorphic relations:
M1. Translating both boxes preserves the Chebyshev gap (and, at the
    auditor level, the SEPARATED verdict)
M2. Swapping the two refs preserves the audit verdict
M3. Uniform scaling of both boxes scales the gap linearly
"""

from __future__ import annotations

import math
import random

from hypothesis import given, settings
from hypothesis import strategies as st
from hypothesis.strategies import composite

from temper_placer.pcl.constraints import ConstraintTier, SeparatedConstraint
from temper_placer.placer.cp_sat.audit import Placement, PlacementAuditor, _chebyshev_gap

MAX_EXAMPLES = 200

_coord = st.floats(min_value=-50.0, max_value=50.0, allow_nan=False, allow_infinity=False)
_size = st.floats(min_value=0.0, max_value=20.0, allow_nan=False, allow_infinity=False)


@composite
def _bbox_pair(draw):
    """Two axis-aligned bboxes as ((x1,y1,x2,y2), (x1,y1,x2,y2))."""
    a = draw(st.tuples(_coord, _coord, _size, _size))
    b = draw(st.tuples(_coord, _coord, _size, _size))
    aa = (a[0] - a[2] / 2, a[1] - a[3] / 2, a[0] + a[2] / 2, a[1] + a[3] / 2)
    bb = (b[0] - b[2] / 2, b[1] - b[3] / 2, b[0] + b[2] / 2, b[1] + b[3] / 2)
    return aa, bb


def _gap(a, b):
    return _chebyshev_gap(a, b)


def _separated(a, b):
    """True when the two bboxes do not overlap in at least one axis."""
    return a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1]


def _euclid_gap(a, b):
    """True Euclidean gap between two separated axis-aligned boxes."""
    dx = max(0.0, a[0] - b[2], b[0] - a[2])
    dy = max(0.0, a[1] - b[3], b[1] - a[3])
    return math.hypot(dx, dy)


# ---------------------------------------------------------------------------
# P1: Non-negativity for separated boxes
# ---------------------------------------------------------------------------


@given(_bbox_pair())
@settings(max_examples=MAX_EXAMPLES)
def test_p1_separated_boxes_have_nonnegative_gap(boxes):
    a, b = boxes
    if _separated(a, b):
        assert _gap(a, b) >= 0.0, f"gap({a}, {b}) = {_gap(a, b)} < 0 for separated boxes"


# ---------------------------------------------------------------------------
# P2: Symmetry (bit-exact)
# ---------------------------------------------------------------------------


@given(_bbox_pair())
@settings(max_examples=MAX_EXAMPLES)
def test_p2_gap_is_symmetric_bit_exact(boxes):
    a, b = boxes
    assert _gap(a, b) == _gap(b, a)


# ---------------------------------------------------------------------------
# P3: Monotonicity in box size — expanding B (in both directions) can
# only shrink or keep the gap: every term in both per-axis maxima moves
# toward overlap, so the outer max is non-increasing.
# ---------------------------------------------------------------------------


@given(_bbox_pair(), st.floats(min_value=0.0, max_value=10.0, allow_nan=False))
@settings(max_examples=MAX_EXAMPLES)
def test_p3_expanding_box_b_is_monotonic(boxes, e):
    a, b = boxes
    before = _gap(a, b)
    # Grow B outward on both sides of both axes.
    grown = (b[0] - e, b[1] - e, b[2] + e, b[3] + e)
    after = _gap(a, grown)
    assert after <= before + 1e-12, f"gap grew: {before} -> {after}"


# ---------------------------------------------------------------------------
# P4: Translation invariance (closeness — integer t is exact, fractional
# t shifts each term by a rounding step, so compare with tolerance)
# ---------------------------------------------------------------------------


@given(_bbox_pair(), st.floats(min_value=-20.0, max_value=20.0, allow_nan=False),
       st.floats(min_value=-20.0, max_value=20.0, allow_nan=False))
@settings(max_examples=MAX_EXAMPLES)
def test_p4_translation_invariance(boxes, tx, ty):
    a, b = boxes
    before = _gap(a, b)
    at = (a[0] + tx, a[1] + ty, a[2] + tx, a[3] + ty)
    bt = (b[0] + tx, b[1] + ty, b[2] + tx, b[3] + ty)
    after = _gap(at, bt)
    if before == 0.0:
        assert after == 0.0 or abs(after) < 1e-9
    else:
        assert abs(after - before) <= 1e-9 * max(1.0, abs(before)), f"{before} -> {after}"


# ---------------------------------------------------------------------------
# P5: Chebyshev-vs-Euclidean bound — the R24 soundness property.
# The Chebyshev gap under-approximates the Euclidean gap for separated
# boxes, so the auditor's SEPARATED check is conservative: it never
# reports a larger separation than the true Euclidean clearance.
# ---------------------------------------------------------------------------


@given(_bbox_pair())
@settings(max_examples=MAX_EXAMPLES)
def test_p5_chebyshev_gap_is_conservative_upper_euclid_bound(boxes):
    a, b = boxes
    if _separated(a, b):
        cheb = _gap(a, b)
        euclid = _euclid_gap(a, b)
        assert 0.0 <= cheb <= euclid + 1e-12, f"cheb={cheb} > euclid={euclid}"


# ---------------------------------------------------------------------------
# Metamorphic relations
# ---------------------------------------------------------------------------


def _scaled_box(cx, cy, sw, sh, s):
    """bbox after scaling center AND size by s (mirrors bbox_from_center)."""
    return (cx * s - sw * s / 2, cy * s - sh * s / 2, cx * s + sw * s / 2, cy * s + sh * s / 2)


def test_meta_uniform_scaling_scales_gap_linearly():
    rng = random.Random(99)
    for _ in range(200):
        cx1, cy1 = rng.uniform(-50, 50), rng.uniform(-50, 50)
        sw1, sh1 = rng.uniform(0, 20), rng.uniform(0, 20)
        cx2, cy2 = rng.uniform(-50, 50), rng.uniform(-50, 50)
        sw2, sh2 = rng.uniform(0, 20), rng.uniform(0, 20)
        s = rng.uniform(0.5, 4.0)
        a = _scaled_box(cx1, cy1, sw1, sh1, 1.0)
        b = _scaled_box(cx2, cy2, sw2, sh2, 1.0)
        a2 = _scaled_box(cx1, cy1, sw1, sh1, s)
        b2 = _scaled_box(cx2, cy2, sw2, sh2, s)
        before = _gap(a, b)
        after = _gap(a2, b2)
        assert abs(after - s * before) <= 1e-9 * max(1.0, abs(s * before)), (
            f"gap({a},{b})={before}; gap({a2},{b2})={after}; s*before={s * before}"
        )


def _auditor_verdict(positions, constraint):
    p = Placement(
        positions_mm=positions,
        sizes_mm=dict.fromkeys(positions, (2.0, 2.0)),
        rotations={},
    )
    return PlacementAuditor(p).audit([constraint])


def test_meta_translation_preserves_audit_verdict():
    """Translating the whole placement (both components) preserves the
    SEPARATED verdict — the gap is translation-invariant."""
    base = {"A": (5.0, 5.0), "B": (12.0, 5.0)}
    c = SeparatedConstraint(
        "A", "B", min_distance_mm=3.0, tier=ConstraintTier.HARD,
        because="Safety isolation requirement for high voltage paths",
    )
    r0 = _auditor_verdict(base, c)
    assert r0.all_pass
    for tx, ty in [(100.0, -200.0), (0.5, 0.25), (-37.0, 41.0)]:
        moved = {r: (x + tx, y + ty) for r, (x, y) in base.items()}
        r1 = _auditor_verdict(moved, c)
        assert r1.all_pass == r0.all_pass
        assert r1.failed == r0.failed


def test_meta_swap_refs_preserves_audit_verdict():
    """SEPARATED(a, b) and SEPARATED(b, a) give identical reports."""
    near = {"A": (5.0, 5.0), "B": (5.6, 5.0)}  # gap 0.6 < 5.0 → violation
    far = {"A": (5.0, 5.0), "B": (20.0, 5.0)}  # gap 15.0 >= 5.0 → pass
    for positions in (near, far):
        c_ab = SeparatedConstraint(
            "A", "B", min_distance_mm=5.0, tier=ConstraintTier.HARD,
            because="Safety isolation requirement for high voltage paths",
        )
        c_ba = SeparatedConstraint(
            "B", "A", min_distance_mm=5.0, tier=ConstraintTier.HARD,
            because="Safety isolation requirement for high voltage paths",
        )
        r_ab = _auditor_verdict(positions, c_ab)
        r_ba = _auditor_verdict(positions, c_ba)
        assert r_ab.failed == r_ba.failed
        assert r_ab.all_pass == r_ba.all_pass
        # The violation records differ only in the human-readable text
        # (constraint id / description embed the ref order); the verdict
        # and the numeric detail (the gap) are identical.
        assert [v.detail for v in r_ab.violations] == [v.detail for v in r_ba.violations]
        assert len(r_ab.violations) == len(r_ba.violations)


def test_meta_scaling_preserves_verdict_when_threshold_scales():
    """Scaling both boxes AND the min_distance by the same s preserves the
    SEPARATED verdict (gap scales with s, so the comparison is unchanged)."""
    rng = random.Random(7)
    for _ in range(100):
        cx1, cy1 = rng.uniform(-50, 50), rng.uniform(-50, 50)
        cx2, cy2 = rng.uniform(-50, 50), rng.uniform(-50, 50)
        sw = rng.uniform(0.5, 10.0)
        sh = rng.uniform(0.5, 10.0)
        min_d = rng.uniform(0.5, 20.0)
        s = rng.uniform(0.5, 4.0)
        base = {"A": (cx1, cy1), "B": (cx2, cy2)}
        sizes = {"A": (sw, sh), "B": (sw, sh)}

        def verdict(positions, mm, sz):
            p = Placement(positions_mm=positions, sizes_mm=sz, rotations={})
            c = SeparatedConstraint(
                "A", "B", min_distance_mm=mm, tier=ConstraintTier.HARD,
                because="Safety isolation requirement for high voltage paths",
            )
            return PlacementAuditor(p).audit([c]).all_pass

        v0 = verdict(base, min_d, sizes)
        scaled_pos = {r: (x * s, y * s) for r, (x, y) in base.items()}
        v1 = verdict(scaled_pos, min_d * s, sizes)
        assert v0 == v1, f"verdict changed under scaling: {v0} vs {v1}"
