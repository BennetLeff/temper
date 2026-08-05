"""Shared input corpus for the ``constraints_geometry`` Wave-4 gates.

**One fixture module, three consumers**: the differential suite (R1a), the
property/metamorphic suite (R1c/R1d), and ``benchmarks/perf_ab.py`` (R1b) all
draw their inputs from here.

That is deliberate and structural, not stylistic.  PR #714 passed its
differential at iterations ``[0, 1, 2, 8, 17, 100]`` and then failed CI on a
benchmark that ran 120 -- the benchmark exercised a parameter the behavioral
gate had never reached.  Sharing the corpus makes that class of gap
impossible to reintroduce: every tuple the benchmark times is, by
construction, a tuple the differential has already compared bit-for-bit
(``test_benchmark_corpus_is_covered_by_differential`` asserts the containment
explicitly, so the property survives future edits to either side).

The corpus is a *fixed* list, not a live random draw, so the perf A/B ratio is
comparable across runs and machines.  The randomized sweeps in the
differential are additional coverage layered on top, never a replacement.

No module in here imports the code under test -- it is pure data, so the
oracle arm and the shim arm can each build their own object types from it.
"""

from __future__ import annotations

import math
import random

__all__ = [
    "SEGMENT_PAIRS",
    "POINT_SEGMENTS",
    "POINT_RECTS",
    "SEGMENT_RECTS",
    "CIRCLES",
    "BENCH_POINT_SEGMENTS",
    "BENCH_SEGMENT_PAIRS",
    "BENCH_POINT_RECTS",
    "BENCH_SEGMENT_RECTS",
    "random_segment_pairs",
    "random_point_rects",
]

NAN = float("nan")
INF = float("inf")

# The exact threshold constants the reference branches on.  Landing *on* them
# (not merely near them) is what makes the branch-boundary mutants killable:
#   seg_len_sq < 1e-10   -> a segment of length 1e-5 has seg_len_sq == 1e-10
#   abs(val) < 1e-10     -> the orientation collinearity epsilon
#   d < 1e-9             -> the segment-vs-rect "intersects" epsilon
_EPS_SEG_LEN = 1e-5  # squares to exactly 1e-10
_EPS_JUST_UNDER = math.nextafter(1e-5, 0.0)
_EPS_JUST_OVER = math.nextafter(1e-5, 1.0)

# ---------------------------------------------------------------------------
# (px, py, x1, y1, x2, y2) -- point_to_segment_distance
# ---------------------------------------------------------------------------
POINT_SEGMENTS: list[tuple[float, float, float, float, float, float]] = [
    # ordinary: projection interior, before-start, past-end
    (5.0, 3.0, 0.0, 0.0, 10.0, 0.0),
    (-4.0, 0.0, 0.0, 0.0, 10.0, 0.0),
    (14.0, 0.0, 0.0, 0.0, 10.0, 0.0),
    (5.0, 0.0, 0.0, 0.0, 10.0, 0.0),  # on the segment
    # exactly-degenerate segment: seg_len_sq == 0.0 -> hypot arm
    (3.0, 4.0, 1.0, 1.0, 1.0, 1.0),
    # AT the 1e-10 branch boundary and one ulp either side of it
    (0.0, 1.0, 0.0, 0.0, _EPS_SEG_LEN, 0.0),
    (0.0, 1.0, 0.0, 0.0, _EPS_JUST_UNDER, 0.0),
    (0.0, 1.0, 0.0, 0.0, _EPS_JUST_OVER, 0.0),
    # signed zeros in every position
    (0.0, 0.0, 0.0, 0.0, 1.0, 0.0),
    (-0.0, -0.0, 0.0, 0.0, 1.0, 0.0),
    (0.0, -0.0, -0.0, 0.0, -0.0, 1.0),
    # values where hypot and sqrt(x*x+y*y) provably differ (17% of random
    # pairs do; these are pinned instances)
    (0.1, 0.2, 0.0, 0.0, 1e-30, 0.0),
    (1.7976931348623157e308, 0.0, 0.0, 0.0, 1.0, 0.0),
    (5e-324, 5e-324, 0.0, 0.0, 1.0, 1.0),
    # NaN in each slot -- exercises the CPython min/max left-propagation rule
    (NAN, 0.0, 0.0, 0.0, 10.0, 0.0),
    (0.0, NAN, 0.0, 0.0, 10.0, 0.0),
    (1.0, 1.0, NAN, 0.0, 10.0, 0.0),
    (1.0, 1.0, 0.0, 0.0, NAN, 0.0),
    # infinities
    (INF, 0.0, 0.0, 0.0, 10.0, 0.0),
    (0.0, 0.0, -INF, 0.0, INF, 0.0),
    # integers (Point/LineSegment do not coerce; callers do pass ints)
    (5, 3, 0, 0, 10, 0),
    (1, 1, 1, 1, 1, 1),
]

# ---------------------------------------------------------------------------
# (a1x, a1y, a2x, a2y, b1x, b1y, b2x, b2y)
#   -- segment_to_segment_distance / closest_points_segment_segment
#      / _segments_intersect
# ---------------------------------------------------------------------------
SEGMENT_PAIRS: list[tuple[float, ...]] = [
    # crossing (general orientation case)
    (0.0, 0.0, 10.0, 10.0, 0.0, 10.0, 10.0, 0.0),
    # parallel, disjoint  -> denom == 0.0 branch in closest_points
    (0.0, 0.0, 10.0, 0.0, 0.0, 3.0, 10.0, 3.0),
    # anti-parallel
    (0.0, 0.0, 10.0, 0.0, 10.0, 2.0, 0.0, 2.0),
    # collinear overlapping  -> every _on_segment arm
    (0.0, 0.0, 10.0, 0.0, 5.0, 0.0, 15.0, 0.0),
    (0.0, 0.0, 10.0, 0.0, 15.0, 0.0, 25.0, 0.0),  # collinear, disjoint
    (0.0, 0.0, 10.0, 0.0, 10.0, 0.0, 20.0, 0.0),  # touching endpoints
    (0.0, 0.0, 10.0, 0.0, -10.0, 0.0, 0.0, 0.0),
    # T-junction (o1 == 0 arm)
    (0.0, 0.0, 10.0, 0.0, 5.0, 0.0, 5.0, 5.0),
    # both degenerate (a <= 1e-10 and e <= 1e-10)
    (1.0, 1.0, 1.0, 1.0, 4.0, 5.0, 4.0, 5.0),
    # first degenerate only / second degenerate only
    (1.0, 1.0, 1.0, 1.0, 0.0, 0.0, 10.0, 0.0),
    (0.0, 0.0, 10.0, 0.0, 3.0, 7.0, 3.0, 7.0),
    # t < 0 and t > 1 clamp arms of closest_points_segment_segment
    (0.0, 0.0, 1.0, 0.0, 5.0, 1.0, 6.0, 1.0),
    (5.0, 0.0, 6.0, 0.0, 0.0, 1.0, 1.0, 1.0),
    # skew, no intersection, minimum at interior points
    (0.0, 0.0, 10.0, 1.0, 3.0, 5.0, 7.0, 4.0),
    # orientation epsilon: nearly-but-not-quite collinear
    (0.0, 0.0, 1.0, 0.0, 0.0, 1e-11, 1.0, 1e-11),
    (0.0, 0.0, 1.0, 0.0, 0.0, 1e-9, 1.0, 1e-9),
    # signed zeros
    (-0.0, -0.0, 0.0, 0.0, -0.0, 0.0, 0.0, -0.0),
    # NaN / inf
    (NAN, 0.0, 1.0, 0.0, 0.0, 1.0, 1.0, 1.0),
    (0.0, 0.0, 1.0, 0.0, NAN, NAN, 1.0, 1.0),
    (0.0, 0.0, INF, 0.0, 0.0, 1.0, INF, 1.0),
    (-INF, 0.0, INF, 0.0, 0.0, -INF, 0.0, INF),
    # very large / very small magnitudes
    (0.0, 0.0, 1e300, 1e300, 1e300, 0.0, 0.0, 1e300),
    (0.0, 0.0, 1e-300, 0.0, 0.0, 1e-300, 1e-300, 1e-300),
    # integers
    (0, 0, 10, 0, 5, 5, 5, -5),
]

# ---------------------------------------------------------------------------
# (px, py, cx, cy, w, h, rotation_deg) -- point_to_rotated_rect_distance
#                                         and RotatedRect.corners
# ---------------------------------------------------------------------------
POINT_RECTS: list[tuple[float, ...]] = [
    (0.0, 0.0, 0.0, 0.0, 2.0, 3.0, 0.0),  # dead centre (interior arm)
    (5.0, 0.0, 0.0, 0.0, 2.0, 3.0, 0.0),  # outside along +x
    (1.0, 1.5, 0.0, 0.0, 2.0, 3.0, 0.0),  # exactly on the corner
    (1.0, 0.0, 0.0, 0.0, 2.0, 3.0, 0.0),  # exactly on an edge
    (0.9, 1.4, 0.0, 0.0, 2.0, 3.0, 0.0),  # just inside
    (1.1, 1.6, 0.0, 0.0, 2.0, 3.0, 0.0),  # just outside, diagonal (hypot arm)
    # the KiCad rotation convention: cardinal angles must be exact
    (2.0, 1.0, 0.0, 0.0, 4.0, 1.0, 90.0),
    (2.0, 1.0, 0.0, 0.0, 4.0, 1.0, 180.0),
    (2.0, 1.0, 0.0, 0.0, 4.0, 1.0, 270.0),
    (2.0, 1.0, 0.0, 0.0, 4.0, 1.0, -90.0),
    # non-cardinal angles: where R(-theta) vs R(+theta) actually separates
    (2.0, 1.0, 0.0, 0.0, 4.0, 1.0, 45.0),
    (2.0, 1.0, 0.0, 0.0, 4.0, 1.0, 30.0),
    (2.0, 1.0, 0.0, 0.0, 4.0, 1.0, -30.0),
    (2.0, 1.0, 0.0, 0.0, 4.0, 1.0, 33.7),
    (2.0, 1.0, 0.0, 0.0, 4.0, 1.0, 359.999),
    (2.0, 1.0, 0.0, 0.0, 4.0, 1.0, 1e6),  # radians() far outside [0, 2pi)
    (2.0, 1.0, 0.0, 0.0, 4.0, 1.0, -1e6),
    # degenerate rects
    (1.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0),
    (1.0, 1.0, 0.0, 0.0, 0.0, 5.0, 17.0),
    (1.0, 1.0, 0.0, 0.0, -2.0, -3.0, 0.0),  # negative size: qx/qy both positive
    # off-origin centres, signed zeros
    (10.0, -7.5, 12.25, -6.75, 1.6, 0.8, 22.5),
    (-0.0, -0.0, 0.0, 0.0, 2.0, 2.0, -0.0),
    # NaN / inf coordinates (rotation stays finite -- inf rotation raises,
    # covered separately by the error-parity tests)
    (NAN, 0.0, 0.0, 0.0, 2.0, 3.0, 0.0),
    (0.0, NAN, 0.0, 0.0, 2.0, 3.0, 45.0),
    (INF, 0.0, 0.0, 0.0, 2.0, 3.0, 0.0),
    (0.0, 0.0, 0.0, 0.0, NAN, 3.0, 0.0),
    (0.0, 0.0, 0.0, 0.0, INF, 3.0, 0.0),
    (1.0, 1.0, 0.0, 0.0, 2.0, 3.0, NAN),
    # integers
    (5, 0, 0, 0, 2, 3, 0),
]

# ---------------------------------------------------------------------------
# (sx, sy, ex, ey, cx, cy, w, h, rotation_deg)
#   -- segment_to_rotated_rect_distance
# ---------------------------------------------------------------------------
SEGMENT_RECTS: list[tuple[float, ...]] = [
    # both endpoints outside, far -> min-edge-distance arm
    (10.0, 10.0, 20.0, 20.0, 0.0, 0.0, 2.0, 3.0, 0.0),
    # segment pierces the rect, endpoints outside -> intersects arm (-1.0)
    (-5.0, 0.0, 5.0, 0.0, 0.0, 0.0, 2.0, 3.0, 0.0),
    # one endpoint inside -> early-return min(d_start, d_end)
    (0.0, 0.0, 5.0, 0.0, 0.0, 0.0, 2.0, 3.0, 0.0),
    (5.0, 0.0, 0.0, 0.0, 0.0, 0.0, 2.0, 3.0, 0.0),
    # endpoint exactly on the boundary (d == 0.0 -> `<= 0` arm)
    (1.0, 0.0, 5.0, 0.0, 0.0, 0.0, 2.0, 3.0, 0.0),
    # grazing: distance just under / just over the 1e-9 "intersects" epsilon
    (1.0 + 1e-10, -5.0, 1.0 + 1e-10, 5.0, 0.0, 0.0, 2.0, 3.0, 0.0),
    (1.0 + 1e-8, -5.0, 1.0 + 1e-8, 5.0, 0.0, 0.0, 2.0, 3.0, 0.0),
    # rotated rects
    (10.0, 10.0, 20.0, 20.0, 0.0, 0.0, 4.0, 1.0, 45.0),
    (-5.0, 0.0, 5.0, 0.0, 0.0, 0.0, 4.0, 1.0, 30.0),
    (3.0, -3.0, 3.0, 3.0, 0.0, 0.0, 4.0, 1.0, 90.0),
    # degenerate segment (a point) against a rect
    (7.0, 7.0, 7.0, 7.0, 0.0, 0.0, 2.0, 3.0, 0.0),
    (0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 2.0, 3.0, 0.0),
    # degenerate rect
    (1.0, 1.0, 2.0, 2.0, 0.0, 0.0, 0.0, 0.0, 0.0),
    # signed zeros / NaN / inf
    (-0.0, -0.0, 0.0, 0.0, -0.0, -0.0, 2.0, 2.0, 0.0),
    (NAN, 0.0, 5.0, 0.0, 0.0, 0.0, 2.0, 3.0, 0.0),
    (0.0, 0.0, NAN, 5.0, 3.0, 3.0, 2.0, 3.0, 15.0),
    (INF, 0.0, -INF, 0.0, 0.0, 0.0, 2.0, 3.0, 0.0),
    (10.0, 10.0, 20.0, 20.0, 0.0, 0.0, 2.0, 3.0, NAN),
    # integers
    (10, 10, 20, 20, 0, 0, 2, 3, 0),
]

# (px, py, cx, cy, radius) -- point_to_circle_distance
CIRCLES: list[tuple[float, ...]] = [
    (3.0, 4.0, 0.0, 0.0, 5.0),  # exactly on the edge
    (0.0, 0.0, 0.0, 0.0, 5.0),  # centre (fully negative)
    (10.0, 0.0, 0.0, 0.0, 5.0),
    (0.1, 0.2, 0.3, 0.4, 0.5),
    (-0.0, -0.0, 0.0, 0.0, 0.0),
    (NAN, 0.0, 0.0, 0.0, 1.0),
    (INF, 0.0, 0.0, 0.0, 1.0),
    (1e308, 1e308, 0.0, 0.0, 1.0),
    (3, 4, 0, 0, 5),
]

# ---------------------------------------------------------------------------
# Benchmark corpora (R1b).  These are STRICT SUBSETS of the corpora above --
# `test_benchmark_corpus_is_covered_by_differential` proves it -- so every
# tuple `benchmarks/perf_ab.py` times has been compared bit-for-bit first.
# ---------------------------------------------------------------------------
BENCH_POINT_SEGMENTS = POINT_SEGMENTS
BENCH_SEGMENT_PAIRS = SEGMENT_PAIRS
BENCH_POINT_RECTS = POINT_RECTS
BENCH_SEGMENT_RECTS = SEGMENT_RECTS


def random_segment_pairs(n: int, seed: int = 20260804) -> list[tuple[float, ...]]:
    """``n`` reproducible random segment pairs over board-scale coordinates."""
    rng = random.Random(seed)
    out: list[tuple[float, ...]] = []
    for _ in range(n):
        out.append(tuple(rng.uniform(-100.0, 100.0) for _ in range(8)))
    return out


def random_point_rects(n: int, seed: int = 20260805) -> list[tuple[float, ...]]:
    """``n`` reproducible random (point, rotated-rect) tuples."""
    rng = random.Random(seed)
    out: list[tuple[float, ...]] = []
    for _ in range(n):
        out.append(
            (
                rng.uniform(-50.0, 50.0),
                rng.uniform(-50.0, 50.0),
                rng.uniform(-50.0, 50.0),
                rng.uniform(-50.0, 50.0),
                rng.uniform(0.0, 20.0),
                rng.uniform(0.0, 20.0),
                rng.uniform(-720.0, 720.0),
            )
        )
    return out
