"""Differential test: deterministic zone_aware_slot_generation geometry compute,
Rust vs oracle.

Wave 4, **Phase 5, final leaves**. The pure geometry kernels of
``temper_placer/deterministic/stages/zone_aware_slot_generation.py``
(``_point_in_polygon`` ray casting, ``_slot_intersects_iso`` AABB, and the
``RoutingChannelAwareSlotStage`` ``_point_to_segment_distance`` /
``_min_distance_to_polygon``) move to the ``temper-design-bundle`` crate
(``temper_design_bundle_python.deterministic_phase``); the Python stage keeps
its orchestration (zone walking, bounds-margin branch) and delegates the
kernels. The pre-migration implementations are pinned VERBATIM as the oracle
(``_zone_aware_slot_generation_py_oracle.py``).

Numerical traps pinned here:
- ``_point_to_segment_distance`` closes with ``** 0.5`` (libm ``pow``), NOT
  ``math.sqrt`` — they differ by 1 ulp on a measurable input class; the
  differential includes a ``pow``-vs-``sqrt`` discriminating operand search.
- ``t = max(0, min(1, ((px - x1) * dx + (py - y1) * dy) / l2))`` — Python
  ``max``/``min`` (first argument on ties).
- ``_point_in_polygon``: half-open y tests (``y > min``, ``y <= max``),
  ``x <= max(p1x, p2x)``, and the ``p1y != p2y`` ternary for ``xinters``.
- ``_min_distance_to_polygon``: ``float('inf')`` sentinel, ``< 2`` -> inf.
"""

from __future__ import annotations

import random

import pytest
import temper_design_bundle_python as _tdb
import tests.deterministic.stages._zone_aware_slot_generation_py_oracle as _oracle
from tests.core._contract_canon import canon

# Rust symbols under test -- must exist or this file fails to collect (RED).
_DP = _tdb.deterministic_phase
RS_PIP = _DP.point_in_polygon_py
RS_ISO = _DP.slot_intersects_iso_py
RS_PTSD = _DP.point_to_segment_distance_py
RS_MDP = _DP.min_distance_to_polygon_py


def _pip_equal(x, y, polygon):
    exp = _oracle.point_in_polygon(x, y, polygon)
    got = RS_PIP(x, y, list(polygon))
    assert got == exp, f"point_in_polygon divergence ({x},{y}) {polygon}: {got} vs {exp}"


def _iso_equal(slot, aabbs):
    exp = _oracle.slot_intersects_iso(slot, aabbs)
    got = RS_ISO(slot, list(aabbs))
    assert got == exp, f"slot_intersects_iso divergence {slot} {aabbs}: {got} vs {exp}"


def _ptsd_equal(px, py, p1, p2):
    exp = _oracle.point_to_segment_distance(px, py, p1, p2)
    got = RS_PTSD(px, py, tuple(p1), tuple(p2))
    assert canon(got) == canon(exp), (
        f"point_to_segment_distance divergence ({px},{py}) {p1}->{p2}: "
        f"{canon(got)} vs {canon(exp)}"
    )


def _mdp_equal(x, y, polygon):
    exp = _oracle.min_distance_to_polygon(x, y, polygon)
    got = RS_MDP(x, y, list(polygon))
    assert canon(got) == canon(exp), f"min_distance_to_polygon divergence ({x},{y}): {got} vs {exp}"


# --- point_in_polygon -------------------------------------------------------

_SQUARE = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]


def test_pip_inside_outside():
    _pip_equal(5.0, 5.0, _SQUARE)
    _pip_equal(-1.0, 5.0, _SQUARE)
    _pip_equal(5.0, 11.0, _SQUARE)
    _pip_equal(11.0, 5.0, _SQUARE)


def test_pip_boundary_semantics():
    """Ray-casting half-open edges: y on the upper edge counts, y on the lower
    edge does not (the `y > min` / `y <= max` pair)."""
    _pip_equal(5.0, 10.0, _SQUARE)  # top edge -> boundary, ray-cast treats as inside
    _pip_equal(5.0, 0.0, _SQUARE)   # bottom edge
    _pip_equal(0.0, 5.0, _SQUARE)   # left edge
    _pip_equal(10.0, 5.0, _SQUARE)  # right edge


def test_pip_vertex():
    _pip_equal(0.0, 0.0, _SQUARE)
    _pip_equal(10.0, 10.0, _SQUARE)


def test_pip_degenerate_short_polygon():
    _pip_equal(5.0, 5.0, [(0.0, 0.0), (10.0, 10.0)])
    _pip_equal(5.0, 5.0, [(0.0, 0.0)])
    _pip_equal(5.0, 5.0, [])


def test_pip_concave_polygon():
    _concave = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (5.0, 5.0), (0.0, 10.0)]
    _pip_equal(2.0, 8.0, _concave)
    _pip_equal(5.0, 5.0, _concave)  # on the notch vertex
    _pip_equal(7.0, 8.0, _concave)


def test_pip_horizontal_edge():
    """p1y == p2y triggers the `else x` branch of the xinters ternary."""
    _pent = [(0.0, 0.0), (10.0, 0.0), (10.0, 4.0), (5.0, 8.0), (0.0, 4.0)]
    _pip_equal(5.0, 2.0, _pent)
    _pip_equal(1.0, 4.0, _pent)   # exactly on the horizontal edge y=4
    _pip_equal(9.0, 4.0, _pent)


def test_pip_negative_coords():
    _tri = [(-5.0, -5.0), (5.0, -5.0), (0.0, 5.0)]
    _pip_equal(0.0, 0.0, _tri)
    _pip_equal(-4.0, -4.9, _tri)
    _pip_equal(0.0, -5.0, _tri)


def test_pip_randomized():
    rng = random.Random(13)
    for _ in range(150):
        n = rng.randint(0, 8)
        polygon = [(rng.uniform(-20, 20), rng.uniform(-20, 20)) for _ in range(n)]
        _pip_equal(rng.uniform(-25, 25), rng.uniform(-25, 25), polygon)


# --- slot_intersects_iso ------------------------------------------------------

def test_iso_inside():
    _iso_equal((2.0, 2.0), [((0.0, 0.0), (4.0, 4.0))])


def test_iso_outside():
    _iso_equal((5.0, 5.0), [((0.0, 0.0), (4.0, 4.0))])


def test_iso_boundary_inclusive():
    """AABB containment is inclusive: x == x_hi or y == y_hi is a hit."""
    _iso_equal((4.0, 2.0), [((0.0, 0.0), (4.0, 4.0))])
    _iso_equal((2.0, 4.0), [((0.0, 0.0), (4.0, 4.0))])
    _iso_equal((4.0, 4.0), [((0.0, 0.0), (4.0, 4.0))])


def test_iso_multiple_aabbs():
    _iso_equal((6.0, 6.0), [((0.0, 0.0), (4.0, 4.0)), ((5.0, 5.0), (9.0, 9.0))])
    _iso_equal((4.5, 4.5), [((0.0, 0.0), (4.0, 4.0)), ((5.0, 5.0), (9.0, 9.0))])


def test_iso_empty():
    _iso_equal((2.0, 2.0), [])


def test_iso_randomized():
    rng = random.Random(17)
    for _ in range(120):
        aabbs = []
        for _ in range(rng.randint(0, 5)):
            x0, y0 = rng.uniform(-10, 10), rng.uniform(-10, 10)
            aabbs.append(((x0, y0), (x0 + rng.uniform(0, 10), y0 + rng.uniform(0, 10))))
        _iso_equal((rng.uniform(-12, 22), rng.uniform(-12, 22)), aabbs)


# --- point_to_segment_distance -------------------------------------------------

def test_ptsd_degenerate_segment():
    _ptsd_equal(0.0, 0.0, (1.0, 1.0), (1.0, 1.0))
    _ptsd_equal(3.0, 4.0, (0.0, 0.0), (0.0, 0.0))


def test_ptsd_projection_interior():
    _ptsd_equal(0.0, 1.0, (0.0, 0.0), (2.0, 0.0))
    _ptsd_equal(0.5, 0.5, (0.0, 0.0), (1.0, 1.0))


def test_ptsd_projection_clamped_before():
    _ptsd_equal(-1.0, 1.0, (0.0, 0.0), (1.0, 0.0))


def test_ptsd_projection_clamped_after():
    _ptsd_equal(2.0, 1.0, (0.0, 0.0), (1.0, 0.0))


def test_ptsd_vertical_segment():
    _ptsd_equal(1.0, 0.5, (0.0, 0.0), (0.0, 2.0))


def test_ptsd_negative_coords():
    _ptsd_equal(-5.0, -5.0, (-10.0, 0.0), (0.0, -10.0))


def test_ptsd_pow_vs_sqrt_discriminating_operand():
    """pow(s, 0.5) != math.sqrt(s) for the constructed sum s on this host:
    a Rust port that closes with sqrt() diverges on such an operand. The
    segment is degenerate so the sum is exactly ((px-x1)**2 + (py-y1)**2)."""
    import math

    candidates = []
    rng = random.Random(23)
    for _ in range(200000):
        px, py = rng.uniform(-1e3, 1e3), rng.uniform(-1e3, 1e3)
        s = math.pow(px, 2.0) + math.pow(py, 2.0)
        if math.pow(s, 0.5) != math.sqrt(s):
            candidates.append((px, py, s))
            break
    assert candidates, "host libm agrees pow(s,0.5)==sqrt(s) everywhere sampled"
    px, py, s = candidates[0]
    _ptsd_equal(px, py, (0.0, 0.0), (0.0, 0.0))


def test_ptsd_randomized():
    rng = random.Random(19)
    for _ in range(200):
        px, py = rng.uniform(-50, 50), rng.uniform(-50, 50)
        p1 = (rng.uniform(-50, 50), rng.uniform(-50, 50))
        p2 = (rng.uniform(-50, 50), rng.uniform(-50, 50))
        _ptsd_equal(px, py, p1, p2)


# --- min_distance_to_polygon ---------------------------------------------------

def test_mdp_triangle():
    _mdp_equal(0.0, 1.0, [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0)])
    _mdp_equal(0.5, 0.5, [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0)])


def test_mdp_inside_polygon_positive():
    """Distance to the boundary from inside a polygon is still the nearest
    edge distance (the kernel is min over segments, not containment)."""
    _mdp_equal(5.0, 5.0, _SQUARE)


def test_mdp_degenerate():
    _mdp_equal(0.0, 0.0, [(0.0, 0.0)])
    _mdp_equal(0.0, 0.0, [])


def test_mdp_collinear():
    _mdp_equal(5.0, 1.0, [(0.0, 0.0), (10.0, 0.0)])


def test_mdp_randomized():
    rng = random.Random(29)
    for _ in range(150):
        n = rng.randint(0, 8)
        polygon = [(rng.uniform(-20, 20), rng.uniform(-20, 20)) for _ in range(n)]
        _mdp_equal(rng.uniform(-25, 25), rng.uniform(-25, 25), polygon)


def test_mdp_non_vacuity_guard():
    assert RS_MDP(0.0, 1.0, [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0)]) == pytest.approx(
        _oracle.min_distance_to_polygon(0.0, 1.0, [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0)])
    )
