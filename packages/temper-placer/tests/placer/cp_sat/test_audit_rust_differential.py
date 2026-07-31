"""Differential tests: Rust audit geometry (bbox + Chebyshev gap) vs the
pure-Python reference (temper_placer/placer/cp_sat/audit.py, Wave 3 #5 —
the R24 post-solve audit's pure compute).

The pre-migration implementations of ``_bbox`` and ``_chebyshev_gap`` are
pinned here as oracles (verbatim semantics, including Python-builtin
``max`` NaN handling and the exact f64 operation order).  Any change to
the Rust core (packages/temper-geometry/src/audit.rs) or the Python
delegation that disagrees with the oracle fails here, bit-exactly.

The direct ``temper_geometry`` pins fail first (the crate is not yet
built / the functions do not exist); the module-level pins exercise the
full delegation path once wired.
"""

from __future__ import annotations

import math
import random

import temper_geometry as _tg

from temper_placer.placer.cp_sat.audit import _bbox, _chebyshev_gap

# ---------------------------------------------------------------------------
# Oracles (pre-migration implementations, verbatim)
# ---------------------------------------------------------------------------


def _oracle_bbox(cx: float, cy: float, sw: float, sh: float):
    hw, hh = sw / 2, sh / 2
    return (cx - hw, cy - hh, cx + hw, cy + hh)


def _oracle_chebyshev_gap(bbox_a, bbox_b):
    ax1, ay1, ax2, ay2 = bbox_a
    bx1, by1, bx2, by2 = bbox_b
    dx = max(ax1 - bx2, bx1 - ax2)
    dy = max(ay1 - by2, by1 - ay2)
    return max(dx, dy)


# ---------------------------------------------------------------------------
# Random bbox / gap helpers
# ---------------------------------------------------------------------------


def _random_bbox(rng):
    cx, cy = rng.uniform(-50.0, 50.0), rng.uniform(-50.0, 50.0)
    sw, sh = rng.uniform(0.0, 20.0), rng.uniform(0.0, 20.0)
    return _oracle_bbox(cx, cy, sw, sh)


# ---------------------------------------------------------------------------
# bbox parity
# ---------------------------------------------------------------------------


def _placement_with(positions, sizes):
    from temper_placer.placer.cp_sat.audit import Placement

    return Placement(
        positions_mm=positions,
        sizes_mm=sizes,
        rotations={},
    )


def test_bbox_matches_oracle_bit_exact():
    rng = random.Random(20260731)
    for _ in range(500):
        ref = f"R{_}"
        cx, cy = rng.uniform(-50.0, 50.0), rng.uniform(-50.0, 50.0)
        sw, sh = rng.uniform(0.0, 20.0), rng.uniform(0.0, 20.0)
        p = _placement_with({ref: (cx, cy)}, {ref: (sw, sh)})
        assert _bbox(p, ref) == _oracle_bbox(cx, cy, sw, sh)


def test_bbox_rust_direct_pin():
    """Direct Rust pin — fails before the crate exposes bbox_from_center."""
    rng = random.Random(11)
    for _ in range(300):
        cx, cy = rng.uniform(-50.0, 50.0), rng.uniform(-50.0, 50.0)
        sw, sh = rng.uniform(0.0, 20.0), rng.uniform(0.0, 20.0)
        assert _tg.bbox_from_center_py(cx, cy, sw, sh) == _oracle_bbox(cx, cy, sw, sh)


def test_bbox_zero_size():
    """Zero-size component (hw = hh = 0) collapses to the center point."""
    for cx, cy in [(0.0, 0.0), (3.0, -7.0), (-1e6, 1e6)]:
        assert _tg.bbox_from_center_py(cx, cy, 0.0, 0.0) == (cx, cy, cx, cy)
        p = _placement_with({"A": (cx, cy)}, {"A": (0.0, 0.0)})
        assert _bbox(p, "A") == (cx, cy, cx, cy)


def test_bbox_missing_ref_defaults_to_origin():
    """A ref absent from both dicts defaults to a zero-size box at origin."""
    p = _placement_with({}, {})
    assert _bbox(p, "NOPE") == (0.0, 0.0, 0.0, 0.0)
    assert _oracle_bbox(0.0, 0.0, 0.0, 0.0) == (0.0, 0.0, 0.0, 0.0)


# ---------------------------------------------------------------------------
# chebyshev_gap parity
# ---------------------------------------------------------------------------


def test_chebyshev_gap_matches_oracle_bit_exact():
    rng = random.Random(20260731)
    for _ in range(500):
        a, b = _random_bbox(rng), _random_bbox(rng)
        assert _chebyshev_gap(a, b) == _oracle_chebyshev_gap(a, b)


def test_chebyshev_gap_rust_direct_pin():
    """Direct Rust pin — fails before the crate exposes chebyshev_gap."""
    rng = random.Random(13)
    for _ in range(300):
        a, b = _random_bbox(rng), _random_bbox(rng)
        assert (
            _tg.chebyshev_gap_py(*a, *b) == _oracle_chebyshev_gap(a, b)
        )


def test_chebyshev_gap_edge_cases():
    """Zero-size boxes, touching boxes, nested boxes, identical boxes."""
    zero = (0.0, 0.0, 0.0, 0.0)
    # Two zero-size boxes at the same point: gap 0.
    assert _chebyshev_gap(zero, zero) == 0.0
    assert _tg.chebyshev_gap_py(*zero, *zero) == 0.0
    # Zero-size boxes separated by 3 mm on x: gap 3.
    other = (3.0, 0.0, 3.0, 0.0)
    assert _chebyshev_gap(zero, other) == 3.0
    assert _tg.chebyshev_gap_py(*zero, *other) == 3.0
    # Touching boxes (shared edge): gap 0.
    a = (0.0, 0.0, 1.0, 1.0)
    b = (1.0, 0.0, 2.0, 1.0)
    assert _chebyshev_gap(a, b) == 0.0
    assert _tg.chebyshev_gap_py(*a, *b) == 0.0
    # One box fully inside the other: negative gap (deep overlap).
    big = (0.0, 0.0, 10.0, 10.0)
    small = (4.0, 4.0, 6.0, 6.0)
    assert _chebyshev_gap(big, small) < 0.0
    assert _tg.chebyshev_gap_py(*big, *small) == _chebyshev_gap(big, small)
    # Identical boxes: gap = -width (deep overlap).
    assert _chebyshev_gap(a, a) == -1.0
    assert _tg.chebyshev_gap_py(*a, *a) == -1.0
    # Diagonal separation: gap is max of per-axis gaps, not Euclidean.
    d = (3.0, 4.0, 3.0, 4.0)  # point 5 mm away (euclid), gap = max(3,4) = 4
    assert _chebyshev_gap(zero, d) == 4.0
    assert _tg.chebyshev_gap_py(*zero, *d) == 4.0


def test_chebyshev_gap_nan_matches_python_builtin_max():
    """Python builtin max(NaN, x) == NaN but max(x, NaN) == x; Rust must
    replicate the builtin (f64::max would discard NaN)."""
    nan = float("nan")
    a = (nan, 0.0, 1.0, 1.0)
    b = (2.0, 0.0, 3.0, 1.0)
    # dx = max(nan - 3.0, 2.0 - 1.0) = max(nan, 1.0) = nan (builtin semantics)
    # dy = max(0.0 - 1.0, 0.0 - 1.0) = -1.0; result max(nan, -1.0) = nan
    assert math.isnan(_oracle_chebyshev_gap(a, b))
    assert math.isnan(_chebyshev_gap(a, b))
    assert math.isnan(_tg.chebyshev_gap_py(*a, *b))
    # NaN in the second position of each builtin max: builtin returns the
    # non-NaN first argument, so the result stays finite.
    a2 = (0.0, 0.0, 1.0, 1.0)
    b2 = (2.0, 0.0, 3.0, nan)
    # dx = max(0.0 - 3.0, 2.0 - 1.0) = 1.0; dy = max(0.0 - nan, 0.0 - 1.0)
    #   = max(nan, -1.0) = nan → result max(1.0, nan) = 1.0 (builtin).
    assert _oracle_chebyshev_gap(a2, b2) == 1.0
    assert _chebyshev_gap(a2, b2) == 1.0
    assert _tg.chebyshev_gap_py(*a2, *b2) == 1.0


def test_chebyshev_gap_inf():
    inf = float("inf")
    a = (0.0, 0.0, 1.0, 1.0)
    b = (2.0, 0.0, inf, 1.0)
    # dx = max(0.0 - inf, 2.0 - 1.0) = max(-inf, 1.0) = 1.0
    assert _chebyshev_gap(a, b) == 1.0
    assert _tg.chebyshev_gap_py(*a, *b) == 1.0
    b2 = (-inf, 0.0, 3.0, 1.0)
    # dx = max(0.0 - 3.0, -inf - 1.0) = max(-3.0, -inf) = -3.0
    # dy = max(0.0 - 1.0, 0.0 - 1.0) = -1.0; result max(-3.0, -1.0) = -1.0
    assert _chebyshev_gap(a, b2) == -1.0
    assert _tg.chebyshev_gap_py(*a, *b2) == -1.0
