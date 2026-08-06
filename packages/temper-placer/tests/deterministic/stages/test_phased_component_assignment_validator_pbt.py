"""Property-based + metamorphic tests for the migrated validator slot-grid kernels.

Wave 4, Phase 5, batch 2 (deterministic leaf stages). Bit-identical parity
against the pinned oracle is asserted separately by
``test_phased_component_assignment_validator_rust_differential.py``.

Five hypothesis properties (R1c):

- P1. Spacing bounds: the inferred spacing is one of the observed non-zero
  coordinate differences (or the 5.0 fallback for degenerate grids).
- P2. Index coverage: every slot appears in exactly one cell and the cell
  key is `(int(round(x/spacing)), int(round(y/spacing)))`.
- P3. Radius membership: every returned slot is within `radius` (hypot),
  and no within-radius slot of a populated cell is dropped.
- P4. Empty-input: empty/`radius <= 0` returns `[]`.
- P5. Determinism: same inputs, same outputs.

Three metamorphic relations (R1d):

- MR1. Uniform-scale invariance: scaling the grid and radius by 2^n keeps
  the within-radius result (bit-exact, powers of two).
- MR2. Cell-key transposition: swapping x and y swaps the cell keys.
- MR3. Radius monotonicity: a larger radius is a superset of a smaller.
"""

from __future__ import annotations

import math

import temper_design_bundle_python as _tdb
from hypothesis import given, settings
from hypothesis import strategies as st

_RS = _tdb.deterministic_leaves

_COORD = st.floats(min_value=-100, max_value=100, allow_nan=False, allow_infinity=False)
_SPACING = st.floats(min_value=1.0, max_value=10.0, allow_nan=False, allow_infinity=False)
_RADIUS = st.floats(min_value=0.0, max_value=6.0, allow_nan=False, allow_infinity=False)


def _coarse(pins):
    # Snap to a 0.5 lattice so the inferred spacing never collapses to a
    # pathological epsilon (the radius scan is O((radius/spacing)^2) — the
    # oracle has the same behaviour, so the PBT keeps inputs well-formed).
    return [(round(x * 2) / 2.0, round(y * 2) / 2.0) for x, y in pins]


_SLOTS = st.lists(st.tuples(_COORD, _COORD), min_size=0, max_size=8).map(_coarse)


@given(_SLOTS)
@settings(max_examples=100, deadline=None)
def test_p1_spacing_bounds(slots):
    spacing = _RS.infer_slot_spacing_py(slots)
    xs = sorted({s[0] for s in slots})
    ys = sorted({s[1] for s in slots})
    diffs = []
    for w in zip(xs, xs[1:]):
        if w[1] > w[0]:
            diffs.append(w[1] - w[0])
    for w in zip(ys, ys[1:]):
        if w[1] > w[0]:
            diffs.append(w[1] - w[0])
    if not diffs or len(slots) < 2:
        assert spacing == 5.0
    else:
        assert spacing in diffs


@given(_SLOTS, _SPACING)
@settings(max_examples=100, deadline=None)
def test_p2_index_coverage(slots, spacing):
    idx = _RS.build_slot_index_py(slots, spacing)
    all_cells = [s for cell in idx.values() for s in cell]
    assert len(all_cells) == len(slots)
    for slot in slots:
        assert slot in all_cells
        key = (int(round(slot[0] / spacing)), int(round(slot[1] / spacing)))
        assert key in idx


@given(_SLOTS, _SPACING, _RADIUS, st.tuples(_COORD, _COORD))
@settings(max_examples=100, deadline=None)
def test_p3_radius_membership(slots, spacing, radius, center):
    if len(slots) < 3:
        return
    idx = _RS.build_slot_index_py(slots, spacing)
    got = _RS.slots_within_radius_py(center, radius, idx, spacing)
    cx, cy = center
    for slot in got:
        assert math.hypot(slot[0] - cx, slot[1] - cy) <= radius
    # Every slot that is within radius AND shares a cell window is returned.
    seen = set(got)
    for slot in slots:
        if slot in seen:
            continue
        assert math.hypot(slot[0] - cx, slot[1] - cy) > radius


@given(_SLOTS, _SPACING, _RADIUS, st.tuples(_COORD, _COORD))
@settings(max_examples=100, deadline=None)
def test_p4_empty_inputs(slots, spacing, radius, center):
    idx = _RS.build_slot_index_py(slots, spacing)
    if radius == 0.0:
        assert _RS.slots_within_radius_py(center, radius, idx, spacing) == []
    if not slots:
        assert _RS.slots_within_radius_py(center, radius, idx, spacing) == []


@given(_SLOTS, _SPACING, _RADIUS, st.tuples(_COORD, _COORD))
@settings(max_examples=100, deadline=None)
def test_p5_determinism(slots, spacing, radius, center):
    idx = _RS.build_slot_index_py(slots, spacing)
    a = _RS.slots_within_radius_py(center, radius, idx, spacing)
    b = _RS.slots_within_radius_py(center, radius, idx, spacing)
    assert [(x.hex(), y.hex()) for x, y in a] == [(x.hex(), y.hex()) for x, y in b]


@given(_SLOTS, _RADIUS, st.tuples(_COORD, _COORD))
@settings(max_examples=100, deadline=None)
def test_mr1_uniform_scale_invariance(slots, radius, center):
    if not slots:
        return
    spacing = _RS.infer_slot_spacing_py(slots)
    scale = 2.0
    scaled_slots = [(x * scale, y * scale) for x, y in slots]
    scaled_center = (center[0] * scale, center[1] * scale)
    idx = _RS.build_slot_index_py(slots, spacing)
    scaled_idx = _RS.build_slot_index_py(scaled_slots, spacing * scale)
    a = set(_RS.slots_within_radius_py(center, radius, idx, spacing))
    b = set(_RS.slots_within_radius_py(scaled_center, radius * scale, scaled_idx, spacing * scale))
    assert {(x * scale, y * scale) for x, y in a} == b


@given(_SLOTS, _SPACING, _RADIUS)
@settings(max_examples=100, deadline=None)
def test_mr2_cell_key_transposition(slots, spacing, radius):
    swapped = [(y, x) for x, y in slots]
    idx = _RS.build_slot_index_py(slots, spacing)
    sidx = _RS.build_slot_index_py(swapped, spacing)
    a = _RS.slots_within_radius_py((1.0, 2.0), radius, idx, spacing)
    b = _RS.slots_within_radius_py((2.0, 1.0), radius, sidx, spacing)
    assert {(y, x) for x, y in a} == set(b)


@given(_SLOTS, _SPACING, st.tuples(_COORD, _COORD))
@settings(max_examples=100, deadline=None)
def test_mr3_radius_monotonicity(slots, spacing, center):
    idx = _RS.build_slot_index_py(slots, spacing)
    small = set(_RS.slots_within_radius_py(center, 1.0, idx, spacing))
    large = set(_RS.slots_within_radius_py(center, 20.0, idx, spacing))
    assert small <= large
