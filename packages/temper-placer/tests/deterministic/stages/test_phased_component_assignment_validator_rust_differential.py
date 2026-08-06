"""Differential test: validator slot-grid kernels, Rust vs oracle.

Wave 4, Phase 5, batch 2 (deterministic leaf stages). The four pure slot-grid
kernels of ``deterministic/stages/phased_component_assignment_validator.py``
move to the ``temper-design-bundle`` crate
(``temper_design_bundle_python.deterministic_leaves``); the Python module
becomes a delegation shim. The pre-migration implementation is pinned
VERBATIM as the oracle (``_phased_component_assignment_validator_py_oracle.py``).

R1a: slot-spacing inference, the bucketed cell index (`int(round(x/spacing))`
— CPython round-half-to-even), and the radius scan (`ceil`, `math.hypot`,
exact (di, dj) raster order) compare bit-identically. Cell keys are i64 and
slots compare via `float.hex()`.
"""

from __future__ import annotations

import temper_design_bundle_python as _tdb
import tests.deterministic.stages._phased_component_assignment_validator_py_oracle as _oracle

_RS = _tdb.deterministic_leaves


def _slots_to_pylist(slots):
    return [(x, y) for x, y in slots]


def _assert_spacing(slots):
    exp = _oracle._infer_slot_spacing(slots)
    got = _RS.infer_slot_spacing_py(slots)
    assert got.hex() == exp.hex(), f"slots={slots}"


def test_infer_spacing_regular_grid():
    _assert_spacing([(0.0, 0.0), (1.0, 0.0), (2.0, 0.0), (0.0, 1.0), (1.0, 1.0)])
    _assert_spacing([(0.0, 0.0), (5.0, 0.0), (10.0, 0.0), (0.0, 5.0)])


def test_infer_spacing_degenerate():
    _assert_spacing([])
    _assert_spacing([(1.0, 1.0)])
    _assert_spacing([(1.0, 1.0), (2.0, 2.0)])
    # Uniform single-column grid: no x candidates, y candidates only.
    _assert_spacing([(0.0, 0.0), (0.0, 3.0), (0.0, 6.0)])


def test_infer_spacing_irregular():
    """Non-uniform spacing -> the minimum non-zero difference."""
    _assert_spacing([(0.0, 0.0), (3.0, 0.0), (8.0, 0.0), (0.0, 5.0)])


def test_infer_spacing_float_irregular():
    """0.1-spaced grid pins the min-difference bits (0.1 not exact)."""
    slots = [(round(0.1 * i, 6), 0.0) for i in range(5)]
    _assert_spacing(slots)


def _hex_index(idx):
    return {(i, j): [(x.hex(), y.hex()) for x, y in lst] for (i, j), lst in idx.items()}


def _assert_index(slots, spacing):
    exp = _oracle._build_slot_index(slots, spacing)
    got = _RS.build_slot_index_py(slots, spacing)
    assert set(got.keys()) == set(exp.keys()), f"keys differ: {set(got.keys())} vs {set(exp.keys())}"
    for k in exp:
        assert _hex_index({k: exp[k]}) == _hex_index({k: got[k]}), f"cell {k}"


def test_index_basic():
    slots = [(0.0, 0.0), (5.0, 0.0), (10.0, 0.0), (0.0, 5.0), (5.1, 5.1)]
    _assert_index(slots, 5.0)


def test_index_rounding_half_even():
    """x/spacing = 2.5 rounds to 2 (half-to-even), not 3."""
    slots = [(12.5, 0.0), (12.6, 0.0), (-12.5, 0.0), (-2.5, 0.0)]
    _assert_index(slots, 5.0)
    got = _RS.build_slot_index_py(slots, 5.0)
    assert (2, 0) in got  # 12.5/5 = 2.5 -> round -> 2
    assert (-2, 0) in got  # -12.5/5 = -2.5 -> round -> -2


def test_index_empty():
    _assert_index([], 5.0)
    assert _RS.build_slot_index_py([], 5.0) == {}


def _assert_within(center, radius, slots, spacing):
    exp_index = _oracle._build_slot_index(slots, spacing)
    got_index = _RS.build_slot_index_py(slots, spacing)
    exp = _oracle._slots_within_radius(center, radius, exp_index, spacing)
    got = _RS.slots_within_radius_py(center, radius, got_index, spacing)
    assert [(x.hex(), y.hex()) for x, y in got] == [(x.hex(), y.hex()) for x, y in exp], (
        f"center={center} radius={radius}"
    )


def test_within_radius_basic():
    slots = [(0.0, 0.0), (5.0, 0.0), (10.0, 0.0), (0.0, 5.0), (5.0, 5.0)]
    _assert_within((0.0, 0.0), 6.0, slots, 5.0)
    _assert_within((0.0, 0.0), 4.9, slots, 5.0)
    _assert_within((5.0, 5.0), 8.0, slots, 5.0)


def test_within_radius_edge():
    """radius <= 0 or an empty index yields []."""
    slots = [(0.0, 0.0), (5.0, 5.0)]
    idx = _oracle._build_slot_index(slots, 5.0)
    assert _oracle._slots_within_radius((0.0, 0.0), 0.0, idx, 5.0) == []
    assert _RS.slots_within_radius_py((0.0, 0.0), 0.0, _RS.build_slot_index_py(slots, 5.0), 5.0) == []
    assert _oracle._slots_within_radius((0.0, 0.0), 1.0, {}, 5.0) == []
    assert _RS.slots_within_radius_py((0.0, 0.0), 1.0, {}, 5.0) == []


def test_within_radius_hypot_parity():
    """A 3-4-5 right triangle distance is exactly 5.0 on both sides."""
    slots = [(3.0, 4.0), (10.0, 10.0)]
    _assert_within((0.0, 0.0), 5.0, slots, 5.0)


def test_within_radius_dedup_order():
    """The output order matches the oracle's (di, dj) raster walk."""
    slots = [(0.0, 0.0), (5.0, 0.0), (0.0, 5.0), (5.0, 5.0), (10.0, 10.0)]
    _assert_within((2.5, 2.5), 10.0, slots, 5.0)
