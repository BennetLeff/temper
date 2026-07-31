"""Property-based + metamorphic tests for the U3 fence sample geometry
(``temper-geometry``'s ``fence_samples_py``, Wave 3 candidate #1).

Five invariants (per the migration roadmap's R4 gate):

1. **Ring boundedness** (circle pads): every sample lies on the boundary
   ring of radius ``pad_radius + eff_creep - inset`` around the pad centre
   (``dist(sample, centre) == r`` up to the cos²+sin² rounding).
2. **Expanded-rect boundary** (rect pads): the 8 samples sit on the
   corners and edge midpoints of the rect expanded by ``eff``, i.e. all
   within the expanded rect's bounds and on its outline.
3. **Sample-count linearity**: the circle branch returns exactly
   ``sample_count_circle`` samples; doubling the count keeps the
   even-indexed samples bit-identical (2π·2i/2n == 2π·i/n exactly, since
   doubling and halving are exact in binary).
4. **Monotonicity in eff_creep** (rect pads): growing ``eff_creep`` moves
   every sample away from the centre coordinate-wise (float subtraction
   and addition are monotone).
5. **Shape fallthrough**: any non-rect shape (including unknown ones)
   uses the same circle computation as ``"circle"``.

Metamorphic relations:

- MR1: sample-count doubling preserves even-indexed samples (bit-exact).
- MR2: rect-sample outward monotonicity under ``eff_creep`` growth
  (coordinate-wise, exact as an inequality).
- MR3: unknown-shape fallthrough equals the circle branch (bit-exact).
"""

from __future__ import annotations

import math

import temper_geometry as _tg
from hypothesis import given, settings
from hypothesis import strategies as st

MAX_EXAMPLES = 100

_pos = st.floats(min_value=-50.0, max_value=50.0, allow_nan=False, allow_infinity=False)
_dim = st.floats(min_value=0.5, max_value=30.0, allow_nan=False, allow_infinity=False)
_eff = st.floats(min_value=1.0, max_value=20.0, allow_nan=False, allow_infinity=False)
_inset = st.floats(min_value=0.0, max_value=0.5, allow_nan=False, allow_infinity=False)
_count = st.integers(min_value=1, max_value=64)
_shape = st.sampled_from(["circle", "rect", "roundrect", "oval", "custom", ""])


def _samples(shape, cx, cy, radius, w, h, eff, inset, count):
    raw = _tg.fence_samples_py(shape, cx, cy, radius, w, h, eff, inset, count)
    return [(raw[2 * i], raw[2 * i + 1]) for i in range(len(raw) // 2)]


@given(_pos, _pos, _dim, _eff, _inset, _count)
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_p1_circle_samples_lie_on_boundary_ring(cx, cy, radius, eff, inset, count):
    r = radius + eff - inset
    if r <= 0.0:  # strategies keep r >= 1.0; defensive guard
        return
    samples = _samples("circle", cx, cy, radius, 0.0, 0.0, eff, inset, count)
    assert len(samples) == count
    scale = max(1.0, abs(r))
    for x, y in samples:
        d = math.hypot(x - cx, y - cy)
        assert abs(d - r) <= 1e-9 * scale, f"sample ({x}, {y}) off the ring: d={d}, r={r}"
    if r > 0.0:
        # vacuity: the samples actually sample the ring, not the centre
        assert any(math.hypot(x - cx, y - cy) > 0.5 * r for x, y in samples)


@given(_pos, _pos, _dim, _dim, _eff, _inset)
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_p2_rect_samples_on_expanded_rect_boundary(cx, cy, w, h, eff, inset):
    # The kernel's net expansion is eff_creep - inset; pass it in one piece.
    net_eff = eff + inset
    samples = _samples("rect", cx, cy, 0.0, w, h, net_eff, 0.0, 16)
    assert len(samples) == 8
    half_w, half_h = w / 2.0 + net_eff, h / 2.0 + net_eff
    tol = 1e-9 * max(1.0, half_w, half_h)
    for x, y in samples:
        # on the boundary: within the expanded rect AND on its outline
        assert abs(x - cx) <= half_w + tol and abs(y - cy) <= half_h + tol
        on_vertical = abs(abs(x - cx) - half_w) <= tol
        on_horizontal = abs(abs(y - cy) - half_h) <= tol
        assert on_vertical or on_horizontal, f"sample ({x}, {y}) not on the rect outline"
    # vacuity: samples are spread over the whole outline, not one point
    xs = {round(x, 6) for x, y in samples}
    ys = {round(y, 6) for x, y in samples}
    assert len(xs) >= 3 and len(ys) >= 3


@given(_pos, _pos, _dim, _eff, _inset, _count)
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_p3_doubling_count_preserves_even_samples(cx, cy, radius, eff, inset, count):
    base = _samples("circle", cx, cy, radius, 0.0, 0.0, eff, inset, count)
    doubled = _samples("circle", cx, cy, radius, 0.0, 0.0, eff, inset, 2 * count)
    assert len(doubled) == 2 * count
    for i, (bx, by) in enumerate(base):
        dx, dy = doubled[2 * i]
        assert bx == dx and by == dy
    # vacuity: the doubled set is genuinely larger
    assert len(doubled) > len(base)


@given(_pos, _pos, _dim, _dim, _inset)
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_p4_rect_samples_move_outward_with_eff(cx, cy, w, h, inset):
    e1, e2 = 1.0, 4.0
    s1 = _samples("rect", cx, cy, 0.0, w, h, e1, inset, 16)
    s2 = _samples("rect", cx, cy, 0.0, w, h, e2, inset, 16)
    for (x1, y1), (x2, y2) in zip(s1, s2):
        assert abs(x2 - cx) >= abs(x1 - cx)
        assert abs(y2 - cy) >= abs(y1 - cy)
        assert (x2 - cx) * (x1 - cx) >= 0  # same side of the centre
        assert (y2 - cy) * (y1 - cy) >= 0
    assert any(
        abs(x2 - cx) > abs(x1 - cx) or abs(y2 - cy) > abs(y1 - cy)
        for (x1, y1), (x2, y2) in zip(s1, s2)
    )  # vacuity: eff growth actually moves at least one sample


@given(_pos, _pos, _dim, _eff, _inset, _count)
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_p5_nonrect_shapes_fall_through_to_circle(cx, cy, radius, eff, inset, count):
    reference = _samples("circle", cx, cy, radius, 4.0, 4.0, eff, inset, count)
    for shape in ("custom", "", "thru_hole"):
        other = _samples(shape, cx, cy, radius, 4.0, 4.0, eff, inset, count)
        assert len(other) == len(reference)
        for (ox, oy), (rx, ry) in zip(other, reference):
            assert ox == rx and oy == ry
    assert len(reference) == count  # vacuity: the branch really runs


# ---------------------------------------------------------------------------
# Metamorphic relations (explicit tests, ~100 runs each)
# ---------------------------------------------------------------------------


@given(_pos, _pos, _dim, _eff, _inset)
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_mr_fence_samples_count_doubling_bit_exact(cx, cy, radius, eff, inset):
    base = _samples("circle", cx, cy, radius, 0.0, 0.0, eff, inset, 8)
    doubled = _samples("circle", cx, cy, radius, 0.0, 0.0, eff, inset, 16)
    for i, (bx, by) in enumerate(base):
        # theta_{2i}(2n) == theta_i(n): (2.0*pi*2i)/(2n) == (2.0*pi*i)/n
        # exactly, since doubling is exact in binary.
        assert doubled[2 * i] == (bx, by)


@given(_pos, _pos, _dim, _dim, _inset)
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_mr_rect_samples_monotone_in_eff(cx, cy, w, h, inset):
    lo = _samples("rect", cx, cy, 0.0, w, h, 0.5, inset, 16)
    hi = _samples("rect", cx, cy, 0.0, w, h, 3.0, inset, 16)
    for (lx, ly), (hx, hy) in zip(lo, hi):
        assert abs(hx - cx) >= abs(lx - cx)
        assert abs(hy - cy) >= abs(ly - cy)
    assert any(
        abs(hx - cx) > abs(lx - cx) or abs(hy - cy) > abs(ly - cy)
        for (lx, ly), (hx, hy) in zip(lo, hi)
    )


@given(_pos, _pos, _dim, _eff, _inset, _count)
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_mr_unknown_shape_matches_circle(cx, cy, radius, eff, inset, count):
    circle = _samples("circle", cx, cy, radius, 3.0, 3.0, eff, inset, count)
    custom = _samples("custom", cx, cy, radius, 3.0, 3.0, eff, inset, count)
    empty = _samples("", cx, cy, radius, 3.0, 3.0, eff, inset, count)
    assert circle == custom == empty
