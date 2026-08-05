"""R1a differential: ``router_v6/constraints_geometry`` vs its pinned oracle.

Arms
----
* **oracle** -- ``tests/router_v6/_constraints_geometry_py_oracle.py``, a
  verbatim copy of the module as of ``c5875adad`` (origin/main).
* **shim** -- the shipped ``temper_placer.router_v6.constraints_geometry``,
  whose bodies now delegate to ``temper_geometry``'s
  ``drc_constraints_geometry`` kernel.

Comparison is by **type-carrying signature** (``tests/router_v6/_signature``):
``float.hex()`` per float, ``dtype`` + ``shape`` per array, concrete type name
per leaf.  **No tolerance anywhere.**  The comparator's own discrimination
power is proven by ``test_signature_self_test.py``.

Traps this file pins explicitly
-------------------------------
``math.hypot`` is CPython's compensated ``vector_norm``, not
``sqrt(x*x + y*y)`` -- measured here, 17.1% of random 2-vectors disagree
(:func:`test_trap_hypot_is_not_naive_sqrt`).

``math.radians`` is ``x * (pi/180)``, not ``(x * pi) / 180`` -- measured
here, 27.9% of random angles disagree
(:func:`test_trap_radians_association`).

CPython's two-argument ``min``/``max`` propagate NaN from the **left**
operand only, and return the **first** argument when the two compare equal
(so ``max(0.0, -0.0)`` is ``+0.0`` but ``max(-0.0, 0.0)`` is ``-0.0``).
``f64::max``/``f64::min``/``f64::clamp`` do none of those things.

``math.cos``/``math.sin`` raise ``ValueError('math domain error')`` on an
infinite argument; libm returns NaN silently.  Error parity is asserted, not
assumed.
"""

from __future__ import annotations

import math
import random

import numpy as np
import pytest

import tests.router_v6._constraints_geometry_py_oracle as ORACLE
from temper_placer.router_v6 import constraints_geometry as SHIM
from tests.router_v6._constraints_geometry_cases import (
    BENCH_POINT_RECTS,
    BENCH_POINT_SEGMENTS,
    BENCH_SEGMENT_PAIRS,
    BENCH_SEGMENT_RECTS,
    CIRCLES,
    POINT_RECTS,
    POINT_SEGMENTS,
    SEGMENT_PAIRS,
    SEGMENT_RECTS,
    random_point_rects,
    random_segment_pairs,
)
from tests.router_v6._signature import sig

# The Rust symbols under test. Importing them at module scope means a missing
# or stale extension fails COLLECTION loudly rather than silently skipping --
# the failure mode `scripts/check_stale_extensions.py` exists to catch.
import temper_geometry as _tg  # isort: skip

REQUIRED_RUST_SYMBOLS = (
    "drc_point_to_segment_distance_py",
    "drc_segment_to_segment_distance_py",
    "drc_segments_intersect_py",
    "drc_closest_points_segment_segment_py",
    "drc_point_to_circle_distance_py",
    "drc_rotated_rect_corners_py",
    "drc_rotated_rect_bounding_radius_py",
    "drc_point_to_rotated_rect_distance_py",
    "drc_segment_to_rotated_rect_distance_py",
    "drc_segment_length_py",
    "drc_segment_direction_py",
    "drc_segment_midpoint_py",
)


def test_rust_symbols_exist():
    missing = [n for n in REQUIRED_RUST_SYMBOLS if not hasattr(_tg, n)]
    assert not missing, f"temper_geometry is missing {missing}"


# ---------------------------------------------------------------------------
# helpers: build the parallel object graphs, one per arm
# ---------------------------------------------------------------------------


def _seg(mod, x1, y1, x2, y2):
    return mod.LineSegment(mod.Point(x1, y1), mod.Point(x2, y2))


def _rect(mod, cx, cy, w, h, rot):
    return mod.RotatedRect(mod.Point(cx, cy), (w, h), rot)


def _both(fn):
    """Run ``fn(module)`` on each arm, returning ``(oracle_result, shim_result)``.

    Exceptions are captured and compared as values, so error parity (type and
    message) is part of the differential rather than an unasserted side
    channel.
    """
    out = []
    for mod in (ORACLE, SHIM):
        try:
            out.append(fn(mod))
        except BaseException as exc:  # noqa: BLE001 - error parity is the point
            out.append(exc)
    return out[0], out[1]


def _assert_same(fn, label):
    a, b = _both(fn)
    assert sig(a) == sig(b), f"{label}: oracle={a!r} shim={b!r}"


# ---------------------------------------------------------------------------
# oracle integrity
# ---------------------------------------------------------------------------


def test_oracle_is_not_the_shim():
    """Anti-vacuity: the two arms must be genuinely different modules.

    If the oracle ever accidentally re-exports the shipped module (an import
    typo is enough), every assertion in this file becomes a tautology.
    """
    assert ORACLE is not SHIM
    assert ORACLE.__file__ != SHIM.__file__
    assert ORACLE.point_to_segment_distance is not SHIM.point_to_segment_distance
    assert ORACLE.LineSegment is not SHIM.LineSegment
    assert ORACLE.RotatedRect is not SHIM.RotatedRect
    # The oracle must NOT reach the Rust kernel by any path.
    src = open(ORACLE.__file__).read()
    assert "temper_geometry" not in src
    assert "_tg" not in src


def test_oracle_still_computes_in_python():
    """The oracle arm must contain the real arithmetic, not a delegation.

    A oracle that had been "helpfully" refactored to call the shim would make
    the differential vacuous while still looking green.
    """
    src = open(ORACLE.__file__).read()
    assert "math.hypot" in src
    assert "math.radians" in src
    assert "def point_to_segment_distance" in src
    assert "seg_len_sq = sx * sx + sy * sy" in src


# ---------------------------------------------------------------------------
# trap measurements -- these fail loudly if the platform stops exhibiting the
# behaviour the port was written against
# ---------------------------------------------------------------------------


def test_trap_hypot_is_not_naive_sqrt():
    rng = random.Random(11)
    n = 200_000
    bad = sum(
        1
        for _ in range(n)
        if math.hypot(x := rng.uniform(-100, 100), y := rng.uniform(-100, 100))
        != math.sqrt(x * x + y * y)
    )
    # Measured 34_178/200_000 = 17.1% on darwin/arm64 CPython 3.12.
    assert bad > n // 100, (
        "math.hypot now agrees with sqrt(x*x+y*y) everywhere; the port's "
        "vector_norm replication may no longer be the right reference"
    )


def test_trap_radians_association():
    rng = random.Random(13)
    n = 200_000
    pi = math.pi
    mul_bad = 0
    div_bad = 0
    for _ in range(n):
        d = rng.uniform(-720.0, 720.0)
        r = math.radians(d)
        if r != d * (pi / 180.0):
            mul_bad += 1
        if r != (d * pi) / 180.0:
            div_bad += 1
    # math.radians IS `x * (pi/180)` -- 0 mismatches -- and is NOT
    # `(x * pi) / 180` -- 55_817/200_000 = 27.9%.  The Rust port uses the
    # former association; this test is what pins that choice.
    assert mul_bad == 0, f"math.radians is no longer x*(pi/180): {mul_bad} mismatches"
    assert div_bad > n // 100, "the (x*pi)/180 association no longer differs"


def test_trap_cpython_min_max_semantics():
    nan = float("nan")
    assert math.isnan(min(nan, 1.0)) and min(1.0, nan) == 1.0
    assert math.isnan(max(nan, 0.0)) and max(0.0, nan) == 0.0
    assert math.copysign(1.0, max(0.0, -0.0)) == 1.0
    assert math.copysign(1.0, max(-0.0, 0.0)) == -1.0
    assert math.copysign(1.0, min(0.0, -0.0)) == 1.0
    assert math.copysign(1.0, min(-0.0, 0.0)) == -1.0


def test_trap_hypot_matches_the_fma_vector_norm_the_port_replicates():
    """Condition on the parity claim, not an unconditional assertion.

    ``py_hypot`` in the Rust kernel replicates CPython's ``vector_norm`` in
    its default, fma-using configuration (``dl_mul`` = ``fma(x, y, -x*y)``).
    A CPython built with ``UNRELIABLE_FMA`` takes a Dekker-split path whose
    last bit can differ.  Rather than claim platform-independent parity, this
    test *asserts the condition holds here*, so the parity claim elsewhere in
    this file is provably scoped rather than assumed.
    """
    rng = random.Random(17)
    for _ in range(2_000):
        x = rng.uniform(-1e3, 1e3)
        y = rng.uniform(-1e3, 1e3)
        assert math.hypot(x, y) == _fma_vector_norm_2(x, y), (x, y)
    # ... and at the scales where the scale factor itself is extreme
    for x, y in ((1e308, 1e308), (5e-324, 5e-324), (1.0, 0.0), (0.0, 0.0)):
        assert math.hypot(x, y) == _fma_vector_norm_2(x, y), (x, y)


def _exact_fma(a: float, b: float, c: float) -> float:
    """``fma(a, b, c)`` — ``a*b + c`` with a single rounding.

    ``math.fma`` only exists from CPython 3.13; this repo runs 3.12.  The
    exact rational value is computed with ``Fraction`` and rounded once by
    ``Fraction.__float__`` (correctly-rounded int division), which is
    definitionally what fma does for finite inputs.
    """
    from fractions import Fraction

    if not (math.isfinite(a) and math.isfinite(b) and math.isfinite(c)):
        return a * b + c
    return float(Fraction(a) * Fraction(b) + Fraction(c))


def _fma_vector_norm_2(x: float, y: float) -> float:
    """Pure-Python transcription of CPython ``vector_norm`` for n == 2."""
    if math.isnan(x) or math.isnan(y):
        return float("nan")
    if math.isinf(x) or math.isinf(y):
        return float("inf")
    x, y = abs(x), abs(y)
    mx = max(x, y)
    if mx == 0.0:
        return 0.0
    _, max_e = math.frexp(mx)
    if max_e < -1023:  # pragma: no cover - subnormal rescale, unreachable here
        tiny = 2.0**-1022
        return tiny * _fma_vector_norm_2(x / tiny, y / tiny)
    scale = 2.0 ** (-max_e)
    csum = 1.0
    frac1 = 0.0
    frac2 = 0.0
    for v in (x * scale, y * scale):
        z = v * v
        pr_lo = _exact_fma(v, v, -z)
        s = csum + z
        sm_lo = (csum - s) + z
        csum = s
        frac1 += pr_lo
        frac2 += sm_lo
    h = math.sqrt(csum - 1.0 + (frac1 + frac2))
    z = -h * h
    pr_lo = _exact_fma(-h, h, -z)
    s = csum + z
    sm_lo = (csum - s) + z
    csum = s
    frac1 += pr_lo
    frac2 += sm_lo
    h += (csum - 1.0 + (frac1 + frac2)) / (2.0 * h)
    return h / scale


# ---------------------------------------------------------------------------
# point_to_segment_distance
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("case", POINT_SEGMENTS, ids=range(len(POINT_SEGMENTS)))
def test_point_to_segment_distance_corpus(case):
    px, py, x1, y1, x2, y2 = case
    _assert_same(
        lambda m: m.point_to_segment_distance(m.Point(px, py), _seg(m, x1, y1, x2, y2)),
        f"point_to_segment_distance{case}",
    )


def test_point_to_segment_distance_random():
    rng = random.Random(101)
    for _ in range(4000):
        vals = [rng.uniform(-100, 100) for _ in range(6)]
        px, py, x1, y1, x2, y2 = vals
        _assert_same(
            lambda m, v=vals: m.point_to_segment_distance(
                m.Point(v[0], v[1]), _seg(m, v[2], v[3], v[4], v[5])
            ),
            f"random point_to_segment_distance{tuple(vals)}",
        )


# ---------------------------------------------------------------------------
# segment_to_segment_distance / _segments_intersect / closest_points
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("case", SEGMENT_PAIRS, ids=range(len(SEGMENT_PAIRS)))
def test_segment_to_segment_distance_corpus(case):
    a = case[:4]
    b = case[4:]
    _assert_same(
        lambda m: m.segment_to_segment_distance(_seg(m, *a), _seg(m, *b)),
        f"segment_to_segment_distance{case}",
    )


@pytest.mark.parametrize("case", SEGMENT_PAIRS, ids=range(len(SEGMENT_PAIRS)))
def test_segments_intersect_corpus(case):
    a = case[:4]
    b = case[4:]
    _assert_same(
        lambda m: m._segments_intersect(_seg(m, *a), _seg(m, *b)),
        f"_segments_intersect{case}",
    )


@pytest.mark.parametrize("case", SEGMENT_PAIRS, ids=range(len(SEGMENT_PAIRS)))
def test_closest_points_segment_segment_corpus(case):
    a = case[:4]
    b = case[4:]
    _assert_same(
        lambda m: m.closest_points_segment_segment(_seg(m, *a), _seg(m, *b)),
        f"closest_points_segment_segment{case}",
    )


def test_segment_pair_functions_random():
    for vals in random_segment_pairs(3000, seed=202):
        a, b = vals[:4], vals[4:]
        _assert_same(
            lambda m, a=a, b=b: m.segment_to_segment_distance(_seg(m, *a), _seg(m, *b)),
            f"random s2s{vals}",
        )
        _assert_same(
            lambda m, a=a, b=b: m._segments_intersect(_seg(m, *a), _seg(m, *b)),
            f"random intersect{vals}",
        )
        _assert_same(
            lambda m, a=a, b=b: m.closest_points_segment_segment(_seg(m, *a), _seg(m, *b)),
            f"random closest{vals}",
        )


def test_segment_pair_functions_random_near_collinear():
    """Random sweep biased onto the collinear/parallel branches.

    A uniform sweep almost never produces ``denom == 0.0`` or ``orientation
    == 0``; without this the parallel and collinear arms are covered only by
    the hand-written corpus.
    """
    rng = random.Random(303)
    for _ in range(3000):
        x1, y1 = rng.uniform(-50, 50), rng.uniform(-50, 50)
        dx, dy = rng.uniform(-20, 20), rng.uniform(-20, 20)
        t0, t1 = rng.uniform(-2, 2), rng.uniform(-2, 2)
        jitter = rng.choice([0.0, 0.0, 1e-12, -1e-12, 1e-9])
        a = (x1, y1, x1 + dx, y1 + dy)
        b = (x1 + t0 * dx, y1 + t0 * dy + jitter, x1 + t1 * dx, y1 + t1 * dy + jitter)
        _assert_same(
            lambda m, a=a, b=b: m.segment_to_segment_distance(_seg(m, *a), _seg(m, *b)),
            f"collinear s2s{a}{b}",
        )
        _assert_same(
            lambda m, a=a, b=b: m.closest_points_segment_segment(_seg(m, *a), _seg(m, *b)),
            f"collinear closest{a}{b}",
        )


# ---------------------------------------------------------------------------
# RotatedRect + point/segment-to-rect
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("case", POINT_RECTS, ids=range(len(POINT_RECTS)))
def test_point_to_rotated_rect_distance_corpus(case):
    px, py, cx, cy, w, h, rot = case
    _assert_same(
        lambda m: m.point_to_rotated_rect_distance(m.Point(px, py), _rect(m, cx, cy, w, h, rot)),
        f"point_to_rotated_rect_distance{case}",
    )


@pytest.mark.parametrize("case", POINT_RECTS, ids=range(len(POINT_RECTS)))
def test_rotated_rect_corners_corpus(case):
    _, _, cx, cy, w, h, rot = case
    _assert_same(lambda m: _rect(m, cx, cy, w, h, rot).corners, f"corners{case}")


@pytest.mark.parametrize("case", POINT_RECTS, ids=range(len(POINT_RECTS)))
def test_rotated_rect_bounding_radius_corpus(case):
    _, _, cx, cy, w, h, rot = case
    _assert_same(lambda m: _rect(m, cx, cy, w, h, rot).bounding_radius, f"bounding_radius{case}")


def test_point_rect_functions_random():
    for vals in random_point_rects(3000, seed=404):
        px, py, cx, cy, w, h, rot = vals
        _assert_same(
            lambda m, v=vals: m.point_to_rotated_rect_distance(
                m.Point(v[0], v[1]), _rect(m, *v[2:])
            ),
            f"random p2rr{vals}",
        )
        _assert_same(lambda m, v=vals: _rect(m, *v[2:]).corners, f"random corners{vals}")
        _assert_same(
            lambda m, v=vals: _rect(m, *v[2:]).bounding_radius, f"random br{vals}"
        )


@pytest.mark.parametrize("case", SEGMENT_RECTS, ids=range(len(SEGMENT_RECTS)))
def test_segment_to_rotated_rect_distance_corpus(case):
    sx, sy, ex, ey, cx, cy, w, h, rot = case
    _assert_same(
        lambda m: m.segment_to_rotated_rect_distance(
            _seg(m, sx, sy, ex, ey), _rect(m, cx, cy, w, h, rot)
        ),
        f"segment_to_rotated_rect_distance{case}",
    )


def test_segment_to_rotated_rect_distance_random():
    rng = random.Random(505)
    for _ in range(3000):
        seg = tuple(rng.uniform(-30, 30) for _ in range(4))
        rect = (
            rng.uniform(-30, 30),
            rng.uniform(-30, 30),
            rng.uniform(0.0, 15.0),
            rng.uniform(0.0, 15.0),
            rng.uniform(-720, 720),
        )
        _assert_same(
            lambda m, s=seg, r=rect: m.segment_to_rotated_rect_distance(
                _seg(m, *s), _rect(m, *r)
            ),
            f"random s2rr{seg}{rect}",
        )


# ---------------------------------------------------------------------------
# circle + LineSegment properties
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("case", CIRCLES, ids=range(len(CIRCLES)))
def test_point_to_circle_distance_corpus(case):
    px, py, cx, cy, r = case
    _assert_same(
        lambda m: m.point_to_circle_distance(m.Point(px, py), m.Point(cx, cy), r),
        f"point_to_circle_distance{case}",
    )


@pytest.mark.parametrize("case", POINT_SEGMENTS, ids=range(len(POINT_SEGMENTS)))
def test_line_segment_properties_corpus(case):
    _, _, x1, y1, x2, y2 = case
    _assert_same(lambda m: _seg(m, x1, y1, x2, y2).length, f"length{case}")
    _assert_same(lambda m: _seg(m, x1, y1, x2, y2).direction, f"direction{case}")
    _assert_same(lambda m: _seg(m, x1, y1, x2, y2).midpoint(), f"midpoint{case}")


def test_line_segment_properties_random():
    rng = random.Random(606)
    for _ in range(4000):
        v = [rng.uniform(-100, 100) for _ in range(4)]
        _assert_same(lambda m, v=v: _seg(m, *v).length, f"random length{v}")
        _assert_same(lambda m, v=v: _seg(m, *v).direction, f"random direction{v}")
        _assert_same(lambda m, v=v: _seg(m, *v).midpoint(), f"random midpoint{v}")


def test_direction_degenerate_threshold():
    """The ``length < 1e-10`` arm of ``LineSegment.direction``, at the exact
    boundary and one ulp either side."""
    for d in (0.0, 1e-11, math.nextafter(1e-10, 0.0), 1e-10, math.nextafter(1e-10, 1.0), 1e-9):
        _assert_same(lambda m, d=d: _seg(m, 0.0, 0.0, d, 0.0).direction, f"direction len={d!r}")


def test_direction_is_a_float64_array():
    """dtype/shape are part of the contract, not incidental."""
    got = SHIM.LineSegment(SHIM.Point(0.0, 0.0), SHIM.Point(3.0, 4.0)).direction
    want = ORACLE.LineSegment(ORACLE.Point(0.0, 0.0), ORACLE.Point(3.0, 4.0)).direction
    assert isinstance(got, np.ndarray)
    assert got.dtype == np.float64 == want.dtype
    assert got.shape == (2,) == want.shape
    assert sig(got) == sig(want)


# ---------------------------------------------------------------------------
# error parity (exception type AND message)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("rot", [float("inf"), float("-inf")])
def test_infinite_rotation_raises_math_domain_error_on_both_arms(rot):
    """``math.cos(inf)`` raises ``ValueError('math domain error')``; libm just
    returns NaN.  If the Rust arm forgot to replicate the raise this is the
    only test that would notice."""
    for build in (
        lambda m: _rect(m, 0.0, 0.0, 2.0, 3.0, rot).corners,
        lambda m: m.point_to_rotated_rect_distance(m.Point(1.0, 1.0), _rect(m, 0.0, 0.0, 2.0, 3.0, rot)),
        lambda m: m.segment_to_rotated_rect_distance(
            _seg(m, 5.0, 5.0, 6.0, 6.0), _rect(m, 0.0, 0.0, 2.0, 3.0, rot)
        ),
    ):
        a, b = _both(build)
        assert isinstance(a, ValueError), f"oracle did not raise: {a!r}"
        assert isinstance(b, ValueError), f"shim did not raise: {b!r}"
        assert str(a) == str(b) == "math domain error"


def test_bad_size_tuple_raises_identically():
    for size in [(1.0,), (1.0, 2.0, 3.0), ()]:
        a, b = _both(lambda m, s=size: m.RotatedRect(m.Point(0.0, 0.0), s, 0.0).corners)
        assert type(a) is type(b) is ValueError
        a2, b2 = _both(
            lambda m, s=size: m.point_to_rotated_rect_distance(
                m.Point(0.0, 0.0), m.RotatedRect(m.Point(0.0, 0.0), s, 0.0)
            )
        )
        assert type(a2) is type(b2), f"{a2!r} vs {b2!r}"


def test_non_numeric_coordinate_raises_same_exception_type():
    a, b = _both(lambda m: m.point_to_segment_distance(m.Point("x", 0.0), _seg(m, 0.0, 0.0, 1.0, 1.0)))
    assert type(a) is TypeError and type(b) is TypeError, f"{a!r} vs {b!r}"


# ---------------------------------------------------------------------------
# public-API surface parity (attributes, repr, eq, hash, pickle, deepcopy)
# ---------------------------------------------------------------------------


def test_public_api_names_unchanged():
    assert SHIM.__all__ == ORACLE.__all__ == ["Point", "LineSegment", "RotatedRect"]
    for name in (
        "Point",
        "LineSegment",
        "RotatedRect",
        "point_to_segment_distance",
        "segment_to_segment_distance",
        "closest_points_segment_segment",
        "point_to_circle_distance",
        "point_to_rotated_rect_distance",
        "segment_to_rotated_rect_distance",
        "_segments_intersect",
    ):
        assert hasattr(SHIM, name), name


def test_types_are_still_plain_frozen_dataclasses():
    """PR #724's vacuity trap: a pyclass is unpicklable by default and nothing
    in a differential suite necessarily pickles anything.  These types are
    stored on ``Pad``/``Track`` objects and travel through ``copy.deepcopy``
    in the router, so the surface is asserted directly rather than inferred.
    """
    import copy
    import pickle
    from dataclasses import fields, is_dataclass

    for name in ("LineSegment", "RotatedRect"):
        o = getattr(ORACLE, name)
        s = getattr(SHIM, name)
        assert is_dataclass(s) and is_dataclass(o)
        assert [f.name for f in fields(s)] == [f.name for f in fields(o)]
        assert s.__dataclass_params__.frozen == o.__dataclass_params__.frozen

    seg_s = _seg(SHIM, 1.0, 2.0, 3.0, 4.0)
    seg_o = _seg(ORACLE, 1.0, 2.0, 3.0, 4.0)
    rect_s = _rect(SHIM, 1.0, 2.0, 3.0, 4.0, 45.0)
    rect_o = _rect(ORACLE, 1.0, 2.0, 3.0, 4.0, 45.0)

    for s, o in ((seg_s, seg_o), (rect_s, rect_o)):
        # repr differs only in the module-qualified class name, which the
        # dataclass repr does not include -- so these must match verbatim.
        assert repr(s) == repr(o)
        # value equality and hashability (frozen dataclasses are hashable;
        # a pyclass would not be, and RotatedRect is used as a dict key in
        # the DRC oracle's per-pad caches)
        rebuilt = type(s)(**{f.name: getattr(s, f.name) for f in fields(s)})
        assert s == rebuilt
        assert hash(s) == hash(rebuilt)
        assert pickle.loads(pickle.dumps(s)) == s
        assert copy.deepcopy(s) == s
        assert copy.copy(s) == s

    assert seg_s == _seg(SHIM, 1.0, 2.0, 3.0, 4.0)
    assert seg_s != _seg(SHIM, 1.0, 2.0, 3.0, 5.0)
    assert rect_s == _rect(SHIM, 1.0, 2.0, 3.0, 4.0, 45.0)
    assert rect_s != _rect(SHIM, 1.0, 2.0, 3.0, 4.0, 46.0)


def test_point_is_the_same_object_as_core_geometry_types_point():
    """``Point`` is re-exported, not redefined.  Redefining it would break
    ``isinstance`` for every caller that imports it from ``core``."""
    from temper_placer.core.geometry_types import Point as CorePoint

    assert SHIM.Point is CorePoint


# ---------------------------------------------------------------------------
# benchmark-coverage containment (the #714 lesson, made structural)
# ---------------------------------------------------------------------------


def test_benchmark_corpus_is_covered_by_differential():
    """Every tuple ``benchmarks/perf_ab.py`` times is compared here first."""
    assert set(BENCH_POINT_SEGMENTS) <= set(POINT_SEGMENTS)
    assert set(BENCH_SEGMENT_PAIRS) <= set(SEGMENT_PAIRS)
    assert set(BENCH_POINT_RECTS) <= set(POINT_RECTS)
    assert set(BENCH_SEGMENT_RECTS) <= set(SEGMENT_RECTS)
    # ... and none of them is empty, which would make the containment vacuous.
    for corpus in (
        BENCH_POINT_SEGMENTS,
        BENCH_SEGMENT_PAIRS,
        BENCH_POINT_RECTS,
        BENCH_SEGMENT_RECTS,
    ):
        assert len(corpus) >= 9


def test_perf_ab_benchmarks_agree_with_their_oracle():
    """Run the registered R1b benchmarks' own in-harness parity assertions.

    The perf harness asserts parity itself; calling it from the test suite is
    what stops a perf-only divergence from living undetected between CI perf
    runs.
    """
    import importlib.util
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[4]
    spec = importlib.util.spec_from_file_location(
        "_perf_ab_for_test", repo_root / "benchmarks" / "perf_ab.py"
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    for key in (
        ("drc-geometry", "point_segment"),
        ("drc-geometry", "segment_segment"),
        ("drc-geometry", "point_rect"),
        ("drc-geometry", "segment_rect"),
    ):
        assert key in mod._BENCHMARKS, f"{key} is not registered in perf_ab.py"
        mod._BENCHMARKS[key]()  # raises AssertionError if the arms disagree
