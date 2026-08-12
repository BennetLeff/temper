"""Differential tests: Rust geometry kernels vs the pre-migration
pure-Python reference (``temper_placer/requirements/validators/_geometry.py``,
Wave 4).

All 12 kernels migrated to ``packages/temper-geometry/src/geometry_kernels.rs``
are pinned bit-exactly against a VERBATIM copy of the pre-migration module
(the ``_oracle_*`` block below, ``git show 47349a50:.../_geometry.py``):

- ``_distance`` (``math.dist`` = CPython's Dekker double-double ``vector_norm``)
- ``_point_in_rect`` / ``_rects_overlap``
- ``_point_to_segment_distance`` (degenerate threshold ``len2 < 1e-12``,
  DIFFERENT from ``drc_constraints_geometry.rs``'s ``1e-10`` — not de-duped)
- ``_point_to_polyline_distance`` / ``_orientation`` / ``_on_segment``
- ``_segments_intersect`` (sign-based orientation test + ``1e-9`` epsilon,
  DIFFERENT from the DRC port's 0/1/2 code + ``1e-10`` — not de-duped)
- ``_segment_to_segment_distance`` / ``_polyline_min_distance`` /
  ``_polylines_intersect`` / ``_polyline_length`` (builtin ``sum()`` =
  Neumaier-compensated, NOT a naive fold)

Bit-exactness classes exercised (docs/wave4-discipline-contract.md section 2):
B4 (``math.dist``/``math.hypot`` = ``py_hypot``, not libm hypot), B5
(``max(0.0, min(1.0, t))`` min-then-max NaN clamp), B7 (arithmetic order
preserved verbatim), B12 (builtin ``sum()`` = compensated Neumaier).

Note on ``_polyline_length``: for <2 points the reference's guarded branch
returns the float ``0.0`` (the ``sum()`` itself is never reached), and the
Rust kernel returns ``0.0`` too — the degenerate case is pinned by
``test_polyline_length_degenerate_type``.
"""

from __future__ import annotations

import math
import random

import pytest

from temper_placer.requirements.validators import _geometry as geom

# ---------------------------------------------------------------------------
# Verbatim pre-migration oracles (copied from the module AS COMMITTED at
# 47349a50 before the Wave 4 migration; do not edit — they are the
# reference).  Only the ``_oracle_`` name prefix and the internal references
# to oracle names differ from the committed file.
# ---------------------------------------------------------------------------


def _oracle_distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.dist(a, b)


def _oracle_point_in_rect(
    pt: tuple[float, float],
    rect: tuple[float, float, float, float],
) -> bool:
    x, y = pt
    rx, ry, rw, rh = rect
    return rx <= x <= rx + rw and ry <= y <= ry + rh


def _oracle_rects_overlap(
    r1: tuple[float, float, float, float],
    r2: tuple[float, float, float, float],
) -> bool:
    x1, y1, w1, h1 = r1
    x2, y2, w2, h2 = r2
    return not (x1 + w1 < x2 or x2 + w2 < x1 or y1 + h1 < y2 or y2 + h2 < y1)


def _oracle_point_to_segment_distance(
    p: tuple[float, float],
    a: tuple[float, float],
    b: tuple[float, float],
) -> float:
    """Closest (perpendicular, clamped) distance from point ``p`` to segment ``a``-``b``."""
    ax, ay = a
    bx, by = b
    px, py = p
    abx, aby = bx - ax, by - ay
    len2 = abx * abx + aby * aby
    if len2 < 1e-12:
        return _oracle_distance(p, a)
    t = ((px - ax) * abx + (py - ay) * aby) / len2
    t = max(0.0, min(1.0, t))
    cx, cy = ax + t * abx, ay + t * aby
    return _oracle_distance(p, (cx, cy))


def _oracle_point_to_polyline_distance(
    p: tuple[float, float], polyline: list[tuple[float, float]]
) -> float:
    """Minimum distance from a point to any segment of a polyline (or to the
    single point of a degenerate one-point polyline)."""
    if not polyline:
        return math.inf
    if len(polyline) == 1:
        return _oracle_distance(p, polyline[0])
    return min(
        _oracle_point_to_segment_distance(p, polyline[i], polyline[i + 1])
        for i in range(len(polyline) - 1)
    )


def _oracle_orientation(
    a: tuple[float, float], b: tuple[float, float], c: tuple[float, float]
) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _oracle_on_segment(
    a: tuple[float, float], b: tuple[float, float], p: tuple[float, float]
) -> bool:
    return (min(a[0], b[0]) - 1e-9 <= p[0] <= max(a[0], b[0]) + 1e-9) and (
        min(a[1], b[1]) - 1e-9 <= p[1] <= max(a[1], b[1]) + 1e-9
    )


def _oracle_segments_intersect(
    a: tuple[float, float],
    b: tuple[float, float],
    c: tuple[float, float],
    d: tuple[float, float],
) -> bool:
    """Standard orientation-based segment intersection test.

    Includes touching endpoints and collinear-overlap cases.
    """
    o1 = _oracle_orientation(a, b, c)
    o2 = _oracle_orientation(a, b, d)
    o3 = _oracle_orientation(c, d, a)
    o4 = _oracle_orientation(c, d, b)

    if ((o1 > 0) != (o2 > 0)) and ((o3 > 0) != (o4 > 0)):
        return True

    eps = 1e-9
    if abs(o1) < eps and _oracle_on_segment(a, b, c):
        return True
    if abs(o2) < eps and _oracle_on_segment(a, b, d):
        return True
    if abs(o3) < eps and _oracle_on_segment(c, d, a):
        return True
    return bool(abs(o4) < eps and _oracle_on_segment(c, d, b))


def _oracle_segment_to_segment_distance(
    a: tuple[float, float],
    b: tuple[float, float],
    c: tuple[float, float],
    d: tuple[float, float],
) -> float:
    """Minimum distance between segment ``a``-``b`` and segment ``c``-``d``.

    Returns 0.0 if the segments intersect (including touching/collinear-overlap).
    """
    if _oracle_segments_intersect(a, b, c, d):
        return 0.0
    return min(
        _oracle_point_to_segment_distance(a, c, d),
        _oracle_point_to_segment_distance(b, c, d),
        _oracle_point_to_segment_distance(c, a, b),
        _oracle_point_to_segment_distance(d, a, b),
    )


def _oracle_polyline_min_distance(
    poly1: list[tuple[float, float]],
    poly2: list[tuple[float, float]],
) -> float:
    """Minimum distance between two polylines (0.0 if any segments cross)."""
    if not poly1 or not poly2:
        return math.inf
    if len(poly1) == 1:
        return _oracle_point_to_polyline_distance(poly1[0], poly2)
    if len(poly2) == 1:
        return _oracle_point_to_polyline_distance(poly2[0], poly1)
    best = math.inf
    for i in range(len(poly1) - 1):
        for j in range(len(poly2) - 1):
            d = _oracle_segment_to_segment_distance(
                poly1[i], poly1[i + 1], poly2[j], poly2[j + 1]
            )
            if d < best:
                best = d
            if best <= 0.0:
                return 0.0
    return best


def _oracle_polylines_intersect(
    poly1: list[tuple[float, float]],
    poly2: list[tuple[float, float]],
) -> bool:
    """Whether any segment of poly1 crosses any segment of poly2."""
    if len(poly1) < 2 or len(poly2) < 2:
        return False
    for i in range(len(poly1) - 1):
        for j in range(len(poly2) - 1):
            if _oracle_segments_intersect(poly1[i], poly1[i + 1], poly2[j], poly2[j + 1]):
                return True
    return False


def _oracle_polyline_length(polyline: list[tuple[float, float]]) -> float:
    """Total path length along a polyline."""
    if len(polyline) < 2:
        return 0.0
    return sum(_oracle_distance(polyline[i], polyline[i + 1]) for i in range(len(polyline) - 1))


def test_oracle_is_verbatim_semantics() -> None:
    """Sanity: the oracle block reproduces the module's own answers on a
    hand-computed fixture (guards against a transcription slip in the
    ``_oracle_`` rename)."""
    assert _oracle_distance((3.0, 4.0), (0.0, 0.0)) == 5.0
    assert _oracle_point_in_rect((5.0, 5.0), (0.0, 0.0, 10.0, 10.0))
    assert not _oracle_point_in_rect((10.5, 5.0), (0.0, 0.0, 10.0, 10.0))
    assert _oracle_rects_overlap((0.0, 0.0, 10.0, 10.0), (10.0, 0.0, 5.0, 5.0))
    assert not _oracle_rects_overlap((0.0, 0.0, 10.0, 10.0), (10.1, 0.0, 5.0, 5.0))
    assert _oracle_point_to_segment_distance((5.0, 3.0), (0.0, 0.0), (10.0, 0.0)) == 3.0
    assert _oracle_segments_intersect(
        (0.0, 0.0), (10.0, 10.0), (0.0, 10.0), (10.0, 0.0)
    )
    assert not _oracle_segments_intersect(
        (0.0, 0.0), (10.0, 10.0), (0.0, 12.0), (10.0, 22.0)
    )
    assert _oracle_segment_to_segment_distance(
        (0.0, 0.0), (10.0, 10.0), (0.0, 10.0), (10.0, 0.0)
    ) == 0.0
    assert _oracle_polyline_min_distance([(0.0, 0.0)], [(0.0, 5.0)]) == 5.0
    assert not _oracle_polylines_intersect([(0.0, 0.0)], [(0.0, 5.0)])
    assert _oracle_polyline_length([(0.0, 0.0), (3.0, 4.0)]) == 5.0


# ---------------------------------------------------------------------------
# Bit-exact comparison helpers
# ---------------------------------------------------------------------------


def key(value):
    if isinstance(value, float):
        if math.isnan(value):
            return ("float", "nan", math.copysign(1.0, value))
        return ("float", value.hex())
    if isinstance(value, bool):
        return ("bool", value)
    return (type(value).__name__, value)


def assert_bits(got, expected, label: str) -> None:
    assert key(got) == key(expected), f"{label}: rust={got!r} ({key(got)}) oracle={expected!r} ({key(expected)})"


# ---------------------------------------------------------------------------
# Marshalling helpers (mirror the delegation in ``_geometry.py``)
# ---------------------------------------------------------------------------


def flatten(points):
    out = []
    for x, y in points:
        out.append(x)
        out.append(y)
    return out


# ---------------------------------------------------------------------------
# Randomised point/rect kernels
# ---------------------------------------------------------------------------


def rng_rect(rng, lo=0.0, hi=20.0, wh_lo=0.0, wh_hi=8.0):
    return (rng.uniform(lo, hi), rng.uniform(lo, hi), rng.uniform(wh_lo, wh_hi), rng.uniform(wh_lo, wh_hi))


def rng_point(rng, lo=-10.0, hi=30.0):
    return (rng.uniform(lo, hi), rng.uniform(lo, hi))


class TestDistance:
    @pytest.mark.parametrize("seed", range(30))
    def test_distance_random(self, seed):
        rng = random.Random(seed)
        a = rng_point(rng)
        b = rng_point(rng)
        expected = _oracle_distance(a, b)
        import temper_geometry as tg

        got = tg.geom_point_distance_py(a[0], a[1], b[0], b[1])
        assert_bits(got, expected, f"distance {a} {b}")
        assert_bits(geom._distance(a, b), expected, f"shim distance {a} {b}")

    @pytest.mark.parametrize("seed", range(10))
    def test_distance_adversarial_magnitudes(self, seed):
        rng = random.Random(1000 + seed)
        a = (rng.choice([1e-6, 1e6, -1e6, rng.uniform(-1e4, 1e4)]), rng.uniform(-1e4, 1e4))
        b = (rng.choice([1e-6, 1e6, -1e6, rng.uniform(-1e4, 1e4)]), rng.uniform(-1e4, 1e4))
        expected = _oracle_distance(a, b)
        import temper_geometry as tg

        got = tg.geom_point_distance_py(a[0], a[1], b[0], b[1])
        assert_bits(got, expected, f"distance {a} {b}")

    def test_distance_nan_inf_parity(self):
        import temper_geometry as tg

        pairs = [
            (float("nan"), 1.0, 0.0, 0.0),
            (1.0, float("nan"), 0.0, 0.0),
            (float("inf"), 1.0, 0.0, 0.0),
            (float("-inf"), 1.0, 0.0, 0.0),
            (float("inf"), float("nan"), 0.0, 0.0),
            (0.0, 0.0, float("inf"), float("-inf")),
            (1e308, 1e308, 0.0, 0.0),
        ]
        for ax, ay, bx, by in pairs:
            a = (ax, ay)
            b = (bx, by)
            expected = _oracle_distance(a, b)
            got = tg.geom_point_distance_py(ax, ay, bx, by)
            assert_bits(got, expected, f"distance {a} {b}")

    def test_distance_subnormal_band(self):
        """B8: denormal inputs must not flush to zero (no fast-math)."""
        import temper_geometry as tg

        rng = random.Random(7)
        for _ in range(50):
            a = (rng.choice([5e-324, 1e-320, 1e-315, 2.5e-310]), rng.uniform(-1, 1))
            b = (0.0, 0.0)
            expected = _oracle_distance(a, b)
            got = tg.geom_point_distance_py(a[0], a[1], b[0], b[1])
            assert_bits(got, expected, f"distance {a} {b}")


class TestPointInRect:
    @pytest.mark.parametrize("seed", range(30))
    def test_point_in_rect_random(self, seed):
        rng = random.Random(2000 + seed)
        pt = rng_point(rng)
        rect = rng_rect(rng)
        expected = _oracle_point_in_rect(pt, rect)
        import temper_geometry as tg

        x, y = pt
        rx, ry, rw, rh = rect
        got = tg.geom_point_in_rect_py(x, y, rx, ry, rw, rh)
        assert got == expected
        assert geom._point_in_rect(pt, rect) == expected

    @pytest.mark.parametrize("seed", range(10))
    def test_point_in_rect_negative_size_and_boundary(self, seed):
        rng = random.Random(3000 + seed)
        for _ in range(20):
            rect = (rng.uniform(0, 10), rng.uniform(0, 10), rng.choice([-3.0, 0.0, 3.0]), rng.uniform(-3, 3))
            pt = (rng.uniform(-5, 15), rng.uniform(-5, 15))
            expected = _oracle_point_in_rect(pt, rect)
            import temper_geometry as tg

            x, y = pt
            rx, ry, rw, rh = rect
            got = tg.geom_point_in_rect_py(x, y, rx, ry, rw, rh)
            assert got == expected
            assert geom._point_in_rect(pt, rect) == expected

    def test_point_in_rect_exact_edge_and_nan(self):
        import temper_geometry as tg

        cases = [
            ((5.0, 5.0), (0.0, 0.0, 10.0, 10.0)),
            ((10.0, 0.0), (0.0, 0.0, 10.0, 10.0)),  # exactly on edge
            ((0.0, 10.0), (0.0, 0.0, 10.0, 10.0)),
            ((float("nan"), 5.0), (0.0, 0.0, 10.0, 10.0)),
            ((5.0, float("inf")), (0.0, 0.0, 10.0, 10.0)),
            ((float("-inf"), 5.0), (0.0, 0.0, 10.0, 10.0)),
        ]
        for pt, rect in cases:
            expected = _oracle_point_in_rect(pt, rect)
            x, y = pt
            rx, ry, rw, rh = rect
            got = tg.geom_point_in_rect_py(x, y, rx, ry, rw, rh)
            assert got == expected


class TestRectsOverlap:
    @pytest.mark.parametrize("seed", range(30))
    def test_rects_overlap_random(self, seed):
        rng = random.Random(4000 + seed)
        r1 = rng_rect(rng)
        r2 = rng_rect(rng)
        expected = _oracle_rects_overlap(r1, r2)
        import temper_geometry as tg

        got = tg.geom_rects_overlap_py(*r1, *r2)
        assert got == expected
        assert geom._rects_overlap(r1, r2) == expected

    def test_rects_overlap_edges_and_nan(self):
        import temper_geometry as tg

        cases = [
            ((0.0, 0.0, 10.0, 10.0), (10.0, 0.0, 5.0, 5.0)),  # touching edge
            ((0.0, 0.0, 10.0, 10.0), (9.9999999, 0.0, 5.0, 5.0)),  # overlapping
            ((0.0, 0.0, 10.0, 10.0), (10.0000001, 0.0, 5.0, 5.0)),  # separated
            ((0.0, 0.0, 10.0, 10.0), (-5.0, -5.0, 100.0, 100.0)),  # containment
            ((0.0, 0.0, 10.0, 10.0), (0.0, 0.0, 10.0, 10.0)),  # identical
            ((float("nan"), 0.0, 10.0, 10.0), (0.0, 0.0, 5.0, 5.0)),  # NaN -> True
            ((0.0, 0.0, float("inf"), 10.0), (0.0, 0.0, 5.0, 5.0)),  # inf -> True
        ]
        for r1, r2 in cases:
            expected = _oracle_rects_overlap(r1, r2)
            got = tg.geom_rects_overlap_py(*r1, *r2)
            assert got == expected
            assert geom._rects_overlap(r1, r2) == expected


# ---------------------------------------------------------------------------
# Segment kernels
# ---------------------------------------------------------------------------


def rng_segment(rng, lo=-10.0, hi=30.0):
    return rng_point(rng, lo, hi), rng_point(rng, lo, hi)


class TestPointToSegmentDistance:
    @pytest.mark.parametrize("seed", range(30))
    def test_point_to_segment_random(self, seed):
        rng = random.Random(5000 + seed)
        p = rng_point(rng)
        a, b = rng_segment(rng)
        expected = _oracle_point_to_segment_distance(p, a, b)
        import temper_geometry as tg

        got = tg.geom_point_to_segment_distance_py(p[0], p[1], a[0], a[1], b[0], b[1])
        assert_bits(got, expected, f"ptseg {p} {a} {b}")
        assert_bits(geom._point_to_segment_distance(p, a, b), expected, f"shim ptseg {p} {a} {b}")

    @pytest.mark.parametrize("seed", range(15))
    def test_point_to_segment_degenerate_boundary(self, seed):
        """Pins the ``len2 < 1e-12`` threshold: len2 == 1e-12 takes the
        projection arm, len2 == 0.81e-12 the degenerate arm."""
        rng = random.Random(6000 + seed)
        p = rng_point(rng)
        for seg_len in (1e-6, 0.9e-6, 1e-9, 0.0, -0.0):
            a = (0.0, 0.0)
            b = (seg_len, 0.0)
            expected = _oracle_point_to_segment_distance(p, a, b)
            import temper_geometry as tg

            got = tg.geom_point_to_segment_distance_py(p[0], p[1], a[0], a[1], b[0], b[1])
            assert_bits(got, expected, f"ptseg degenerate {p} {a} {b}")

    def test_point_to_segment_nan(self):
        import temper_geometry as tg

        cases = [
            ((5.0, 5.0), (0.0, 0.0), (float("nan"), 0.0)),
            ((5.0, 5.0), (0.0, 0.0), (0.0, float("nan"))),
            ((float("nan"), 5.0), (0.0, 0.0), (10.0, 0.0)),
            ((5.0, 5.0), (0.0, 0.0), (float("inf"), 0.0)),
            ((5.0, 5.0), (0.0, 0.0), (0.0, 0.0)),
        ]
        for p, a, b in cases:
            expected = _oracle_point_to_segment_distance(p, a, b)
            got = tg.geom_point_to_segment_distance_py(p[0], p[1], a[0], a[1], b[0], b[1])
            assert_bits(got, expected, f"ptseg nan {p} {a} {b}")


class TestPointToPolylineDistance:
    @pytest.mark.parametrize("seed", range(30))
    def test_point_to_polyline_random(self, seed):
        rng = random.Random(7000 + seed)
        p = rng_point(rng)
        n = rng.randint(1, 8)
        poly = [rng_point(rng) for _ in range(n)]
        expected = _oracle_point_to_polyline_distance(p, poly)
        import temper_geometry as tg

        got = tg.geom_point_to_polyline_distance_py(p[0], p[1], flatten(poly))
        assert_bits(got, expected, f"ptpoly {p} {poly}")
        assert_bits(geom._point_to_polyline_distance(p, poly), expected, f"shim ptpoly {p} {poly}")

    def test_point_to_polyline_degenerate(self):
        import temper_geometry as tg

        p = (5.0, 5.0)
        assert _oracle_point_to_polyline_distance(p, []) == math.inf
        assert tg.geom_point_to_polyline_distance_py(5.0, 5.0, []) == math.inf
        assert geom._point_to_polyline_distance(p, []) == math.inf
        assert _oracle_point_to_polyline_distance(p, [(0.0, 0.0)]) == math.dist(p, (0.0, 0.0))
        assert tg.geom_point_to_polyline_distance_py(5.0, 5.0, [0.0, 0.0]) == math.dist(p, (0.0, 0.0))
        # NaN polyline coordinate
        expected = _oracle_point_to_polyline_distance(p, [(0.0, 0.0), (float("nan"), 1.0)])
        got = tg.geom_point_to_polyline_distance_py(5.0, 5.0, flatten([(0.0, 0.0), (float("nan"), 1.0)]))
        assert_bits(got, expected, "ptpoly nan")


class TestOrientation:
    @pytest.mark.parametrize("seed", range(20))
    def test_orientation_random(self, seed):
        rng = random.Random(8000 + seed)
        a, b, c = rng_point(rng), rng_point(rng), rng_point(rng)
        expected = _oracle_orientation(a, b, c)
        import temper_geometry as tg

        got = tg.geom_orientation_py(a[0], a[1], b[0], b[1], c[0], c[1])
        assert_bits(got, expected, f"orientation {a} {b} {c}")
        assert_bits(geom._orientation(a, b, c), expected, f"shim orientation {a} {b} {c}")

    def test_orientation_collinear_and_signed_zero(self):
        import temper_geometry as tg

        cases = [
            ((0.0, 0.0), (10.0, 10.0), (5.0, 5.0)),
            ((0.0, 0.0), (10.0, 0.0), (5.0, 0.0)),
            ((0.0, 0.0), (10.0, 0.0), (5.0, 1.0)),
            ((0.0, 0.0), (10.0, 0.0), (5.0, -1.0)),
            ((-0.0, 0.0), (0.0, -0.0), (-0.0, -0.0)),
        ]
        for a, b, c in cases:
            expected = _oracle_orientation(a, b, c)
            got = tg.geom_orientation_py(a[0], a[1], b[0], b[1], c[0], c[1])
            assert_bits(got, expected, f"orientation {a} {b} {c}")


class TestOnSegment:
    @pytest.mark.parametrize("seed", range(20))
    def test_on_segment_random(self, seed):
        rng = random.Random(9000 + seed)
        a, b = rng_segment(rng)
        p = rng_point(rng)
        expected = _oracle_on_segment(a, b, p)
        import temper_geometry as tg

        got = tg.geom_on_segment_py(a[0], a[1], b[0], b[1], p[0], p[1])
        assert got == expected
        assert geom._on_segment(a, b, p) == expected

    def test_on_segment_edges(self):
        import temper_geometry as tg

        cases = [
            ((0.0, 0.0), (10.0, 0.0), (0.0, 0.0)),  # endpoint
            ((0.0, 0.0), (10.0, 0.0), (10.0, 0.0)),
            ((0.0, 0.0), (10.0, 0.0), (5.0, 1e-9)),  # within epsilon
            ((0.0, 0.0), (10.0, 0.0), (5.0, 1.1e-9)),  # outside epsilon
            ((10.0, 0.0), (0.0, 0.0), (5.0, 0.0)),  # reversed segment
            ((0.0, 0.0), (10.0, 0.0), (float("nan"), 0.0)),
        ]
        for a, b, p in cases:
            expected = _oracle_on_segment(a, b, p)
            got = tg.geom_on_segment_py(a[0], a[1], b[0], b[1], p[0], p[1])
            assert got == expected


class TestSegmentsIntersect:
    @pytest.mark.parametrize("seed", range(30))
    def test_segments_intersect_random(self, seed):
        rng = random.Random(10000 + seed)
        a, b = rng_segment(rng)
        c, d = rng_segment(rng)
        expected = _oracle_segments_intersect(a, b, c, d)
        import temper_geometry as tg

        got = tg.geom_segments_intersect_py(a[0], a[1], b[0], b[1], c[0], c[1], d[0], d[1])
        assert got == expected
        assert geom._segments_intersect(a, b, c, d) == expected

    def test_segments_intersect_structured(self):
        import temper_geometry as tg

        cases = [
            # proper crossing
            ((0.0, 0.0), (10.0, 10.0), (0.0, 10.0), (10.0, 0.0)),
            # shared endpoint
            ((0.0, 0.0), (10.0, 0.0), (10.0, 0.0), (10.0, 10.0)),
            # T junction (endpoint on segment)
            ((0.0, 0.0), (10.0, 0.0), (5.0, 0.0), (5.0, 5.0)),
            # collinear overlap
            ((0.0, 0.0), (10.0, 0.0), (5.0, 0.0), (15.0, 0.0)),
            # collinear disjoint
            ((0.0, 0.0), (10.0, 0.0), (15.0, 0.0), (25.0, 0.0)),
            # collinear touching endpoints
            ((0.0, 0.0), (10.0, 0.0), (10.0, 0.0), (20.0, 0.0)),
            # parallel disjoint
            ((0.0, 0.0), (10.0, 0.0), (0.0, 3.0), (10.0, 3.0)),
            # degenerate segment
            ((5.0, 5.0), (5.0, 5.0), (0.0, 0.0), (10.0, 10.0)),
            # NaN
            ((0.0, 0.0), (10.0, 0.0), (float("nan"), 0.0), (10.0, 10.0)),
        ]
        for a, b, c, d in cases:
            expected = _oracle_segments_intersect(a, b, c, d)
            got = tg.geom_segments_intersect_py(a[0], a[1], b[0], b[1], c[0], c[1], d[0], d[1])
            assert got == expected


class TestSegmentToSegmentDistance:
    @pytest.mark.parametrize("seed", range(30))
    def test_segment_to_segment_random(self, seed):
        rng = random.Random(11000 + seed)
        a, b = rng_segment(rng)
        c, d = rng_segment(rng)
        expected = _oracle_segment_to_segment_distance(a, b, c, d)
        import temper_geometry as tg

        got = tg.geom_segment_to_segment_distance_py(a[0], a[1], b[0], b[1], c[0], c[1], d[0], d[1])
        assert_bits(got, expected, f"segseg {a} {b} {c} {d}")
        assert_bits(geom._segment_to_segment_distance(a, b, c, d), expected, f"shim segseg {a} {b} {c} {d}")

    def test_segment_to_segment_structured(self):
        import temper_geometry as tg

        cases = [
            # crossing -> 0.0
            ((0.0, 0.0), (10.0, 10.0), (0.0, 10.0), (10.0, 0.0)),
            # separated parallel
            ((0.0, 0.0), (10.0, 0.0), (0.0, 3.0), (10.0, 3.0)),
            # collinear overlap -> 0.0
            ((0.0, 0.0), (10.0, 0.0), (5.0, 0.0), (15.0, 0.0)),
            # collinear gap
            ((0.0, 0.0), (10.0, 0.0), (15.0, 0.0), (25.0, 0.0)),
            # degenerate both
            ((1.0, 1.0), (1.0, 1.0), (4.0, 5.0), (4.0, 5.0)),
        ]
        for a, b, c, d in cases:
            expected = _oracle_segment_to_segment_distance(a, b, c, d)
            got = tg.geom_segment_to_segment_distance_py(a[0], a[1], b[0], b[1], c[0], c[1], d[0], d[1])
            assert_bits(got, expected, f"segseg {a} {b} {c} {d}")


# ---------------------------------------------------------------------------
# Polyline kernels
# ---------------------------------------------------------------------------


def rng_polyline(rng, lo=-10.0, hi=30.0, max_len=8):
    n = rng.randint(1, max_len)
    return [rng_point(rng, lo, hi) for _ in range(n)]


class TestPolylineMinDistance:
    @pytest.mark.parametrize("seed", range(30))
    def test_polyline_min_distance_random(self, seed):
        rng = random.Random(12000 + seed)
        poly1 = rng_polyline(rng)
        poly2 = rng_polyline(rng)
        expected = _oracle_polyline_min_distance(poly1, poly2)
        import temper_geometry as tg

        got = tg.geom_polyline_min_distance_py(flatten(poly1), flatten(poly2))
        assert_bits(got, expected, f"polymin {poly1} {poly2}")
        assert_bits(geom._polyline_min_distance(poly1, poly2), expected, f"shim polymin {poly1} {poly2}")

    def test_polyline_min_distance_structured(self):
        import temper_geometry as tg

        cases = [
            ([], [(0.0, 0.0), (1.0, 1.0)]),  # empty -> inf
            ([(0.0, 0.0)], []),
            ([(0.0, 0.0)], [(0.0, 5.0)]),  # single points
            ([(0.0, 0.0), (10.0, 10.0)], [(0.0, 10.0), (10.0, 0.0)]),  # crossing -> 0
            ([(0.0, 0.0), (10.0, 0.0)], [(0.0, 3.0), (10.0, 3.0)]),  # separated
            ([(-5.0, 5.0), (5.0, 5.0)], [(0.0, 0.0)]),  # point-to-polyline arm
        ]
        for poly1, poly2 in cases:
            expected = _oracle_polyline_min_distance(poly1, poly2)
            got = tg.geom_polyline_min_distance_py(flatten(poly1), flatten(poly2))
            assert_bits(got, expected, f"polymin {poly1} {poly2}")
            assert_bits(geom._polyline_min_distance(poly1, poly2), expected, f"shim polymin {poly1} {poly2}")


class TestPolylinesIntersect:
    @pytest.mark.parametrize("seed", range(30))
    def test_polylines_intersect_random(self, seed):
        rng = random.Random(13000 + seed)
        poly1 = rng_polyline(rng, max_len=6)
        poly2 = rng_polyline(rng, max_len=6)
        expected = _oracle_polylines_intersect(poly1, poly2)
        import temper_geometry as tg

        got = tg.geom_polylines_intersect_py(flatten(poly1), flatten(poly2))
        assert got == expected
        assert geom._polylines_intersect(poly1, poly2) == expected

    def test_polylines_intersect_structured(self):
        import temper_geometry as tg

        cases = [
            ([], [(0.0, 0.0), (1.0, 1.0)]),  # short -> False
            ([(0.0, 0.0)], [(0.0, 5.0)]),
            ([(0.0, 0.0), (10.0, 10.0)], [(0.0, 10.0), (10.0, 0.0)]),  # crossing
            ([(0.0, 0.0), (10.0, 0.0)], [(0.0, 3.0), (10.0, 3.0)]),  # separated
            ([(0.0, 0.0), (10.0, 0.0), (10.0, 10.0)], [(5.0, 5.0), (5.0, 20.0)]),  # 2nd seg crosses
        ]
        for poly1, poly2 in cases:
            expected = _oracle_polylines_intersect(poly1, poly2)
            got = tg.geom_polylines_intersect_py(flatten(poly1), flatten(poly2))
            assert got == expected


class TestPolylineLength:
    @pytest.mark.parametrize("seed", range(30))
    def test_polyline_length_random(self, seed):
        rng = random.Random(14000 + seed)
        poly = rng_polyline(rng)
        expected = _oracle_polyline_length(poly)
        import temper_geometry as tg

        got = tg.geom_polyline_length_py(flatten(poly))
        assert_bits(got, expected, f"polylen {poly}")
        assert_bits(geom._polyline_length(poly), expected, f"shim polylen {poly}")

    def test_polyline_length_degenerate_type(self):
        """For <2 points the reference's ``sum()`` is empty but the guarded
        branch returns the float ``0.0``; the shim delegates fully and the
        Rust kernel floats the degenerate case as ``0.0`` too — all three
        agree bit-exactly (and by type)."""
        import temper_geometry as tg

        for poly in ([], [(0.0, 0.0)]):
            expected = _oracle_polyline_length(poly)
            assert expected == 0.0 and isinstance(expected, float)
            got_shim = geom._polyline_length(poly)
            assert key(got_shim) == key(expected)
            got_rust = tg.geom_polyline_length_py(flatten(poly))
            assert got_rust == 0.0 and isinstance(got_rust, float)

    def test_polyline_length_neumaier_discriminator(self):
        """Pins that the builtin ``sum()`` oracle is compensated (B12): a
        naive fold would differ on cancellation-heavy inputs."""
        import temper_geometry as tg

        poly = [(0.0, 0.0), (1e16, 1.0), (1e16, -1.0)]
        expected = _oracle_polyline_length(poly)
        got = tg.geom_polyline_length_py(flatten(poly))
        assert_bits(got, expected, "neumaier")
        assert got == expected  # compensated, bit-exact

    def test_polyline_length_collinear_and_nan(self):
        import temper_geometry as tg

        cases = [
            [(0.0, 0.0), (3.0, 4.0), (6.0, 8.0), (9.0, 12.0)],
            [(0.0, 0.0), (0.0, 0.0), (0.0, 0.0)],
            [(0.0, 0.0), (float("nan"), 1.0)],
            [(float("nan"), 0.0), (1.0, 1.0), (2.0, 2.0)],
            [(0.0, 0.0), (1e308, 1e308), (0.0, 0.0)],
        ]
        for poly in cases:
            expected = _oracle_polyline_length(poly)
            got = tg.geom_polyline_length_py(flatten(poly))
            assert_bits(got, expected, f"polylen {poly}")
