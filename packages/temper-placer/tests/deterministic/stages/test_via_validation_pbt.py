"""Property-based tests for the migrated via_validation compute.

Wave 4, Phase 5, final leaves. Properties exercise the migrated
``temper_drc_rs.count_connected_layers_py`` and
``temper_drc_rs.dedup_via_positions_py`` (the delegation shims in
``deterministic/stages/via_validation.py`` call them); bit-identical parity
against the pinned pre-migration Python is asserted separately by
``test_via_validation_rust_differential.py``.

Five properties (R1c) for the count kernel:

- P1. Bounded: `0 <= count <= len(via_layers)`.
- P2. Zero when far: no trace/pin point within tolerance -> 0.
- P3. Plane-layer auto-connect: a plane net whose layers are all plane layers
  connects all of them.
- P4. Monotone in tolerance: a larger tolerance never disconnects a layer.
- P5. Determinism.

Three metamorphic relations (R1d):

- MR1. Layer relabeling: renaming layers consistently preserves the count.
- MR2. Far-point irrelevance: adding a point far outside the tolerance does
  not change the count.
- MR3. Dedup coverage: every deduped position is within tolerance of a kept
  position, and the kept list is a prefix-free (pairwise > tol) subsequence.
"""

from __future__ import annotations

import math

import temper_drc_rs as _drc
from hypothesis import given, settings
from hypothesis import strategies as st

RS_COUNT = _drc.count_connected_layers_py
RS_DEDUP = _drc.dedup_via_positions_py

_COORD = st.floats(min_value=-20.0, max_value=20.0, allow_nan=False, allow_infinity=False)
_POS = st.tuples(_COORD, _COORD)
_LAYERS = st.sampled_from(["F.Cu", "In1.Cu", "In2.Cu", "B.Cu"])
_PLANE = ["In1.Cu", "In2.Cu"]


def _count(pos, layers, tol, trace, pin, is_plane, plane=None):
    return RS_COUNT(pos, list(layers), tol, trace, pin, is_plane, list(plane or _PLANE))


@given(
    _POS,
    st.lists(_LAYERS, max_size=4, unique=True),
    st.floats(min_value=0.01, max_value=2.0, allow_nan=False, allow_infinity=False),
    st.dictionaries(_LAYERS, st.lists(_POS, max_size=6), max_size=4),
    st.dictionaries(_LAYERS, st.lists(_POS, max_size=6), max_size=4),
    st.booleans(),
)
@settings(max_examples=200, deadline=None)
def test_p1_count_bounded(pos, layers, tol, trace, pin, is_plane):
    assert 0 <= _count(pos, layers, tol, trace, pin, is_plane) <= len(layers)


@given(_POS, st.lists(_LAYERS, max_size=4, unique=True))
@settings(max_examples=200, deadline=None)
def test_p2_zero_when_far(pos, layers):
    if not layers:
        return
    # Every trace point placed 100+ mm away from the via: no layer connects.
    trace = {layer: [(pos[0] + 100.0 + i, pos[1] - 100.0)] for i, layer in enumerate(layers)}
    assert _count(pos, layers, 0.1, trace, {}, False) == 0


@given(_POS, st.lists(st.sampled_from(_PLANE), max_size=2, unique=True))
@settings(max_examples=200, deadline=None)
def test_p3_plane_auto_connect(pos, layers):
    if not layers:
        return
    assert _count(pos, layers, 0.1, {}, {}, True) == len(layers)


@given(_POS, st.lists(_LAYERS, max_size=3, unique=True), _COORD, _COORD, st.booleans())
@settings(max_examples=200, deadline=None)
def test_p4_monotone_in_tolerance(pos, layers, px, py, is_plane):
    if not layers:
        return
    t_small = 0.05
    t_large = 2.0
    trace = {layers[0]: [(px, py)]}
    small = _count(pos, layers, t_small, trace, {}, is_plane)
    large = _count(pos, layers, t_large, trace, {}, is_plane)
    assert large >= small


@given(
    _POS,
    st.lists(_LAYERS, max_size=4, unique=True),
    st.dictionaries(_LAYERS, st.lists(_POS, max_size=6), max_size=4),
    st.dictionaries(_LAYERS, st.lists(_POS, max_size=6), max_size=4),
    st.booleans(),
)
@settings(max_examples=200, deadline=None)
def test_p5_determinism(pos, layers, trace, pin, is_plane):
    a = _count(pos, layers, 0.1, trace, pin, is_plane)
    b = _count(pos, layers, 0.1, trace, pin, is_plane)
    assert a == b


@given(
    _POS,
    st.lists(_LAYERS, max_size=4, unique=True),
    st.dictionaries(_LAYERS, st.lists(_POS, max_size=6), max_size=4),
    st.booleans(),
)
@settings(max_examples=200, deadline=None)
def test_mr1_layer_relabeling(pos, layers, trace, is_plane):
    if not layers:
        return
    renaming = {"F.Cu": "TOP", "In1.Cu": "IN_1", "In2.Cu": "IN_2", "B.Cu": "BOT"}
    relabeled = {renaming.get(layer, layer): pts for layer, pts in trace.items()}
    rel_layers = [renaming.get(layer, layer) for layer in layers]
    base = _count(pos, layers, 0.1, trace, {}, is_plane)
    got = RS_COUNT(pos, rel_layers, 0.1, relabeled, {}, is_plane, [renaming.get(layer, layer) for layer in _PLANE])
    assert got == base


@given(_POS, st.lists(_LAYERS, max_size=3, unique=True), _COORD, _COORD)
@settings(max_examples=200, deadline=None)
def test_mr2_far_point_irrelevance(pos, layers, fx, fy):
    if not layers:
        return
    layer = layers[0]
    near = {layer: [(pos[0] + 0.01, pos[1] + 0.01)]}
    far = {layer: [(pos[0] + 0.01, pos[1] + 0.01), (fx + 1000.0, fy - 1000.0)]}
    assert _count(pos, layers, 0.1, near, {}, False) == _count(pos, layers, 0.1, far, {}, False)


@given(st.lists(_POS, max_size=15), st.floats(min_value=0.0, max_value=2.0, allow_nan=False, allow_infinity=False))
@settings(max_examples=200, deadline=None)
def test_mr3_dedup_coverage_and_separation(positions, tol):
    kept_idx, dupes = RS_DEDUP(list(positions), tol)
    kept = [positions[i] for i in kept_idx]
    assert len(kept) + dupes == len(positions)
    # pairwise separation: any two kept positions are > tol apart.
    # The kernel's boundary is `tol_sq = pow(tol, 2.0)` (host libm), and every
    # distance term is `pow(dx, 2.0)` -- NOT `tol * tol` / `x * x`: CPython
    # folds `** 2` into a multiply, and a non-correctly-rounded host libm
    # `pow` can disagree with that multiply by 1 ulp (the exact pair the
    # mutation-sweep doc documents). math.pow is the Python spelling of the
    # host libm the kernel dlsym-resolves, so these assertions reproduce the
    # kernel's arithmetic exactly.
    for i in range(len(kept)):
        for j in range(i + 1, len(kept)):
            (x1, y1), (x2, y2) = kept[i], kept[j]
            assert math.pow(x1 - x2, 2.0) + math.pow(y1 - y2, 2.0) > math.pow(tol, 2.0)
    # coverage: every rejected position is within tol of SOME kept position.
    rejected = [p for i, p in enumerate(positions) if i not in kept_idx]
    for (x, y) in rejected:
        assert any(
            math.pow(x - kx, 2.0) + math.pow(y - ky, 2.0) <= math.pow(tol, 2.0)
            for (kx, ky) in kept
        )
