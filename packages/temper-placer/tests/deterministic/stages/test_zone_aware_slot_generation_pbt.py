"""Property-based tests for the migrated zone_aware_slot_generation geometry.

Wave 4, Phase 5, final leaves. Properties exercise the migrated
``temper_design_bundle_python.deterministic_phase`` geometry kernels
(``point_in_polygon_py``, ``slot_intersects_iso_py``,
``min_distance_to_polygon_py``) plus, since the 2026-08-11 point-to-segment
dedupe (issue #987), the canonical
``temper_geometry.point_to_segment_distance_py`` — the
``deterministic_phase`` binding it replaced was deleted; the
delegation shims in ``deterministic/stages/zone_aware_slot_generation.py``
call it); bit-identical parity against the pinned pre-migration Python is
asserted separately by ``test_zone_aware_slot_generation_rust_differential.py``.

Five properties (R1c):

- P1 (pip). Far-point false: points far outside a polygon's bounding box are
  never inside.
- P2 (pip). Determinism.
- P3 (ptsd). Non-negativity of point-to-segment distance.
- P4 (ptsd). Endpoint distance: the distance to a degenerate segment equals
  the distance to the point.
- P5 (mdp). Composition: min_distance_to_polygon equals the minimum of
  point_to_segment_distance over the edges (cross-checks the shim wiring).

Three metamorphic relations (R1d):

- MR1 (ptsd). Translation invariance (bit-exact).
- MR2 (mdp). Axis swap invariance (bit-exact).
- MR3 (iso). AABB reorder independence (bit-exact).
"""

from __future__ import annotations

import temper_design_bundle_python as _tdb
import temper_geometry as _tg
from hypothesis import given, settings
from hypothesis import strategies as st

_DP = _tdb.deterministic_phase
RS_PIP = _DP.point_in_polygon_py
RS_ISO = _DP.slot_intersects_iso_py
# Issue #987: the deterministic_phase point_to_segment_distance_py binding
# was deleted in the point-to-segment dedupe; the canonical temper-geometry
# kernel is the subject.
RS_PTSD = _tg.point_to_segment_distance_py
RS_MDP = _DP.min_distance_to_polygon_py

_COORD = st.floats(min_value=-50.0, max_value=50.0, allow_nan=False, allow_infinity=False)
_POS = st.tuples(_COORD, _COORD)
_POLY = st.lists(_POS, min_size=3, max_size=10)


@given(_POS, _POLY)
@settings(max_examples=200, deadline=None)
def test_p1_far_point_false(pos, polygon):
    xs = [p[0] for p in polygon]
    ys = [p[1] for p in polygon]
    assert not RS_PIP(min(xs) - 100.0, min(ys) - 100.0, polygon)
    assert not RS_PIP(max(xs) + 100.0, max(ys) + 100.0, polygon)


@given(_POS, _POLY)
@settings(max_examples=200, deadline=None)
def test_p2_determinism(pos, polygon):
    assert RS_PIP(pos[0], pos[1], polygon) == RS_PIP(pos[0], pos[1], polygon)


@given(_COORD, _COORD, _POS, _POS)
@settings(max_examples=200, deadline=None)
def test_p3_distance_non_negative(px, py, p1, p2):
    assert RS_PTSD(px, py, *p1, *p2) >= 0.0


@given(_COORD, _COORD, _POS)
@settings(max_examples=200, deadline=None)
def test_p4_degenerate_segment_equals_point_distance(px, py, p):
    d = RS_PTSD(px, py, *p, *p)
    import math

    # Issue #987: the canonical kernel's degenerate arm is math.hypot (not
    # the sqrt(pow+pow) form the deleted copy C used — ≤1-ulp divergence).
    assert d == math.hypot(px - p[0], py - p[1])


@given(_COORD, _COORD, _POLY)
@settings(max_examples=200, deadline=None)
def test_p5_mdp_is_min_over_edges(x, y, polygon):
    best = float("inf")
    for i in range(len(polygon)):
        d = RS_PTSD(x, y, *polygon[i], *polygon[(i + 1) % len(polygon)])
        best = min(best, d)
    assert RS_MDP(x, y, polygon) == best


@given(_COORD, _COORD, _POS, _POS, _COORD, _COORD)
@settings(max_examples=200, deadline=None)
def test_mr1_ptsd_translation_invariance(px, py, p1, p2, tx, ty):
    base = RS_PTSD(px, py, *p1, *p2)
    got = RS_PTSD(px + tx, py + ty, *(p1[0] + tx, p1[1] + ty), *(p2[0] + tx, p2[1] + ty))
    # Translation is NOT bit-exact in IEEE: (a + t) - (b + t) can differ from
    # a - b by 1 ulp, and the projections are products of those differences.
    # The MR is exact in real arithmetic; state an honest tight tolerance.
    assert abs(got - base) <= 1e-9 * max(1.0, abs(base))


@given(_COORD, _COORD, _POLY)
@settings(max_examples=200, deadline=None)
def test_mr2_mdp_axis_swap(x, y, polygon):
    base = RS_MDP(x, y, polygon)
    swapped = [(py, px) for px, py in polygon]
    got = RS_MDP(y, x, swapped)
    assert got == base


@given(_POS, st.lists(st.tuples(_POS, _POS), max_size=6))
@settings(max_examples=200, deadline=None)
def test_mr3_iso_reorder_independent(slot, aabbs):
    base = RS_ISO(slot, aabbs)
    shuffled = list(aabbs)
    shuffled.reverse()
    assert RS_ISO(slot, shuffled) == base
