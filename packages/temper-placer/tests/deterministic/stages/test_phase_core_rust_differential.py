"""Differential test: deterministic _phase_core compute, Rust vs oracle.

Wave 4, **Phase 5, final leaves**. The residual arithmetic of
``temper_placer/deterministic/stages/_phase_core.py`` -- ``_get_footprint_radius``
(``math.sqrt(w**2 + h**2) / 2 + 1.0``), ``_reserve_slots`` (the within-radius
distance filter) and ``_distance`` (Euclidean distance) -- moves to the
``temper-design-bundle`` crate
(``temper_design_bundle_python.deterministic_phase``); the Python methods
become delegation shims. The pre-migration implementation is pinned VERBATIM
as the oracle (``_phase_core_py_oracle.py``).

Numerical traps pinned here:
- ``w ** 2`` is exact int pow for int bounds and libm ``pow`` for float bounds
  (they differ in the last ulp) -- the Rust side mirrors ``sq_dim``.
- ``math.sqrt`` is libm ``sqrt``, NOT the Rust intrinsic.
- ``_reserve_slots``'s distance test is inclusive ``<= radius``.
"""

from __future__ import annotations

import random

import temper_design_bundle_python as _tdb
import tests.deterministic.stages._phase_core_py_oracle as _oracle
from tests.core._contract_canon import canon

# Rust symbols under test -- must exist or this file fails to collect (RED).
_DP = _tdb.deterministic_phase
RS_FOOTPRINT = _DP.footprint_radius_py
RS_RESERVE = _DP.reserve_slots_py
RS_DISTANCE = _DP.distance_py


def _assert_footprint(bounds, slot_spacing):
    exp = _oracle.footprint_radius(bounds, slot_spacing)
    got = RS_FOOTPRINT(bounds, slot_spacing)
    assert canon(got) == canon(exp), (
        f"footprint_radius divergence bounds={bounds} spacing={slot_spacing}: "
        f"{canon(got)} vs {canon(exp)}"
    )


def _slot_canon(slots):
    return [(float(s[0]).hex(), float(s[1]).hex()) for s in slots]


def _assert_reserve(center, radius, all_slots):
    exp = _oracle.reserve_slots(center, radius, all_slots)
    got = list(RS_RESERVE(center, radius, all_slots))
    assert _slot_canon(got) == _slot_canon(exp), (
        f"reserve_slots divergence center={center} radius={radius} "
        f"slots={all_slots}: {_slot_canon(got)} vs {_slot_canon(exp)}"
    )


def _assert_distance(p1, p2):
    exp = _oracle.distance(p1, p2)
    got = RS_DISTANCE(p1, p2)
    assert canon(got) == canon(exp), (
        f"distance divergence p1={p1} p2={p2}: {canon(got)} vs {canon(exp)}"
    )


def test_footprint_radius_basic():
    # sqrt(3**2 + 4**2)/2 + 1 = 5/2 + 1 = 3.5.
    _assert_footprint((3.0, 4.0), 12.0)


def test_footprint_radius_no_bounds():
    _assert_footprint(None, 12.0)
    _assert_footprint(None, 7.5)


def test_footprint_radius_float_bounds():
    _assert_footprint((2.0, 2.0), 12.0)
    _assert_footprint((10.5, 24.25), 6.0)
    _assert_footprint((0.1, 0.2), 5.0)


def test_footprint_radius_int_bounds():
    # int bounds exercise the exact int-pow path (w**2 == int arithmetic).
    _assert_footprint((6, 8), 12.0)
    _assert_footprint((3, 4), 12.0)
    _assert_footprint((10, 24), 6.0)


def test_footprint_radius_mixed_int_float_bounds():
    _assert_footprint((6, 8.0), 12.0)
    _assert_footprint((6.0, 8), 12.0)


def test_footprint_radius_large_int_bounds():
    # Ints near the float/exact boundary: int ** 2 is exact, libm pow is not.
    _assert_footprint((1000003, 1000004), 12.0)


def test_reserve_slots_within_radius():
    slots = [(0.0, 0.0), (3.0, 4.0), (10.0, 10.0), (4.0, 3.0)]
    _assert_reserve((0.0, 0.0), 5.0, slots)


def test_reserve_slots_inclusive_boundary():
    # A slot exactly at radius must be reserved (<= is inclusive).
    slots = [(3.0, 4.0), (6.0, 0.0)]
    _assert_reserve((0.0, 0.0), 5.0, slots)


def test_reserve_slots_empty_and_negative_radius():
    _assert_reserve((0.0, 0.0), 0.0, [(0.0, 0.0), (1.0, 0.0)])
    _assert_reserve((0.0, 0.0), -1.0, [(0.0, 0.0), (1.0, 0.0)])
    _assert_reserve((1.0, 1.0), 5.0, [])


def test_reserve_slots_offset_center():
    slots = [(10.0, 10.0), (13.0, 14.0), (0.0, 0.0), (14.0, 13.0)]
    _assert_reserve((10.0, 10.0), 5.0, slots)


def test_distance_basic():
    _assert_distance((0.0, 0.0), (3.0, 4.0))
    _assert_distance((1.0, 2.0), (1.0, 2.0))
    _assert_distance((-1.5, 2.5), (3.5, -4.5))


def test_footprint_radius_randomized():
    rng = random.Random(11)
    for _ in range(200):
        bounds = (rng.uniform(-50, 50), rng.uniform(-50, 50))
        spacing = rng.uniform(0.1, 50)
        _assert_footprint(bounds, spacing)
    for _ in range(50):
        _assert_footprint(None, rng.uniform(0.1, 50))


def test_reserve_slots_randomized():
    rng = random.Random(12)
    for _ in range(200):
        cx, cy = rng.uniform(-20, 20), rng.uniform(-20, 20)
        radius = rng.uniform(0.0, 30.0)
        slots = [
            (rng.uniform(-20, 20), rng.uniform(-20, 20))
            for _ in range(rng.randint(0, 40))
        ]
        _assert_reserve((cx, cy), radius, slots)


def test_distance_randomized():
    rng = random.Random(13)
    for _ in range(200):
        p1 = (rng.uniform(-100, 100), rng.uniform(-100, 100))
        p2 = (rng.uniform(-100, 100), rng.uniform(-100, 100))
        _assert_distance(p1, p2)
