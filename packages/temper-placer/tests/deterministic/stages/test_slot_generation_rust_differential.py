"""Differential test: deterministic slot_generation compute, Rust vs oracle.

Wave 4, **Phase 5, first slice** (deterministic leaf stages). The pure
compute of ``temper_placer/deterministic/stages/slot_generation.py``
moves to the ``temper-design-bundle`` crate
(``temper_design_bundle_python.deterministic_stages``); the Python module
becomes a delegation shim. The pre-migration implementation is pinned
VERBATIM as the oracle (``_slot_generation_py_oracle.py``).

Bit-exactness (R1a): floats compare via ``float.hex()``, every non-float
leaf carries its concrete type, ``canon`` canonicalizes.

Numerical traps pinned here:
- the grid walk is a **naive `+=` accumulation** (NOT compensated): the
  generated ``y`` values drift from ``y_min + k*spacing`` by the
  accumulated rounding error, and the Rust must accumulate identically;
- the loop bounds are strict ``< x_max`` / ``< y_max``, starting at
  ``min + spacing / 2`` — so ``spacing`` larger than the zone produces an
  EMPTY slot list (asserted explicitly, vacuity guard);
- ``spacing / 2`` is computed once, before the loop.
"""

from __future__ import annotations

import random

import pytest
import temper_design_bundle_python as _tdb

import tests.deterministic.stages._slot_generation_py_oracle as _oracle
from tests.core._contract_canon import canon

_RS = _tdb.deterministic_stages
RS_SLOTS = _RS.generate_slots_for_zone


class _FakeZone:
    """Minimal zone exposing the same ``bounds`` surface the oracle reads."""

    def __init__(self, bounds):
        self.bounds = bounds


def _assert_slots_equal(bounds, spacing):
    zone = _FakeZone(bounds)
    exp = _oracle.generate_slots_for_zone(zone, spacing)
    (x_min, y_min), (x_max, y_max) = bounds
    got = list(RS_SLOTS(x_min, y_min, x_max, y_max, spacing))
    assert canon(exp) == canon(got), f"slot mismatch bounds={bounds} spacing={spacing}"


def test_slots_basic_grid():
    _assert_slots_equal(((0, 0), (10, 10)), 2.0)
    _assert_slots_equal(((0, 0), (10, 10)), 5.0)
    _assert_slots_equal(((1.5, -2.5), (12.5, 7.5)), 2.5)


def test_slots_empty_inputs():
    """Vacuity guards: spacing >= zone extent -> no slots."""
    assert _oracle.generate_slots_for_zone(_FakeZone(((0, 0), (1, 1))), 5.0) == []
    assert list(RS_SLOTS(0.0, 0.0, 1.0, 1.0, 5.0)) == []
    # Zero-extent zone.
    assert _oracle.generate_slots_for_zone(_FakeZone(((2, 2), (2, 2))), 1.0) == []
    assert list(RS_SLOTS(2.0, 2.0, 2.0, 2.0, 1.0)) == []


def test_slots_strict_upper_bound():
    """A slot exactly at x_max / y_max is NOT emitted (strict `<`)."""
    # spacing 2, x from 1 to 10: 1, 3, 5, 7, 9 (not 11).
    _assert_slots_equal(((0, 0), (10, 10)), 2.0)


def test_slots_float_accumulation():
    """The naive += accumulation is bit-pinned (spacing 0.1 is not exact)."""
    _assert_slots_equal(((0, 0), (1, 1)), 0.1)
    _assert_slots_equal(((0.05, 0.05), (0.95, 0.95)), 0.1)


def test_slots_randomized():
    rng = random.Random(21)
    for _ in range(120):
        x_min = rng.uniform(-50, 0)
        y_min = rng.uniform(-50, 0)
        w = rng.uniform(0.0, 50)
        h = rng.uniform(0.0, 50)
        spacing = rng.choice([0.1, 0.25, 0.5, 1.0, 2.0, 3.0, 5.0, 7.5])
        _assert_slots_equal(((x_min, y_min), (x_min + w, y_min + h)), spacing)


def test_slots_negative_origin():
    """Negative origins produce slots starting at min + spacing/2."""
    _assert_slots_equal(((-5, -5), (5, 5)), 2.0)
    _assert_slots_equal(((-1.3, -2.7), (0.1, 3.3)), 0.5)
