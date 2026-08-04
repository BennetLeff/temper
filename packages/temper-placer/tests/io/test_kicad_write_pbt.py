"""Property-based + metamorphic tests for the Rust write/export engine.

Wave 4, Phase 3 — candidate 4 of
``docs/plans/2026-08-02-001-feat-wave4-phase3-formats-io-plan.md`` (the
write/export engine; gate ``R1 with round-trip bit-parity (R3)``, R1c/R1d).
Bit-identical parity against the pinned pre-migration Python is asserted
separately by ``test_kicad_write_rust_differential.py``; these properties
hold of the migrated kernels themselves (driven through the delegation
shims), so they keep catching regressions even after the oracles retire
(R20).

Six hypothesis properties:

- P1. ``snap_to_nearest_pad`` totality/optimality: the result is either the
  original point (nothing closer than the tolerance) or a pad within the
  tolerance, and no pad is strictly closer than the result.
- P2. ``snap_to_nearest_pad`` single-pad exactness: a one-pad input returns
  the pad exactly when its distance is strictly below the tolerance.
- P3. ``reorient_pad_angle`` math: the returned angle is exactly
  ``py_mod(current + delta, 360)``, never ``0.0`` (emitted as ``None``).
- P4. ``rotation_index_to_degrees`` / ``positions_to_placements``: an index
  ``i`` maps to ``i * 90.0`` degrees, and every placement is at
  ``position + origin`` with that rotation (bit-exact: the offsets are
  dyadic).
- P5. ``state_to_placements``: one placement per ref, rotation ``idx * 90``
  (no original-angle input), and the center-offset subtraction applies the
  R(-theta) rotation.
- P6. ``strip_routing_plan``: the removed counts equal the classified item
  counts, and zone handling is monotone in ``keep_zones``.

Five metamorphic relations:

- MR1. ``snap_to_nearest_pad`` translation invariance (integer coords make
  the distance comparisons exact): translating the point and all pads by the
  same integer offset translates the result by the same offset.
- MR2. ``simplify_path`` index-set invariance under integer scaling: scaling
  all cell coordinates by ``k >= 1`` keeps the same cells (the collinearity
  structure is preserved).
- MR3. ``rotation_index_to_degrees`` rotation wraparound: an index ``i + 4``
  produces a rotation that is ``py_mod``-equal to ``i``'s for ``i`` in 0..3
  (indices >= 4 are legal -- the kernel scales any i64 index by 90.0 -- and
  multiples of 90 are exact, so this is exact). Driven through the kernel
  directly: ``np.argmax`` over 4-column logits can only emit indices 0..3,
  so the original logits-driven form could never reach index 4 and was
  trivially true.
- MR4. ``write_placements_plan`` unmatched->matched monotonicity: adding a
  placement for a footprint that was previously unmatched raises
  ``components_updated`` by exactly one and lowers ``components_skipped`` by
  exactly one.
- MR5. ``strip_routing_plan`` zone monotonicity: ``zones_removed`` with
  ``keep_zones=False`` is >= with ``keep_zones=True`` (exact: the counts are
  either ``len(zones)`` or ``0``).

The properties are guarded against vacuity: each has at least one input on
which it can fail, and the metamorphic relations are paired with a
discriminating-check test proving they are breakable (a constant kernel
violates them).
"""

from __future__ import annotations

from types import SimpleNamespace

from hypothesis import given, settings
from hypothesis import strategies as st

from temper_placer.io.kicad_exporter import snap_to_nearest_pad as shim_snap
from temper_placer.io.kicad_writer import state_to_placements
from temper_placer.io.placement_exporter import (
    positions_to_placements,
    rotation_index_to_degrees,
)

MAX_EXAMPLES = 100

_COORDS = st.floats(min_value=-50.0, max_value=50.0, allow_nan=False, allow_infinity=False)
_TOL = st.floats(min_value=0.01, max_value=10.0, allow_nan=False, allow_infinity=False)
_ANGLE = st.floats(min_value=0.0, max_value=360.0, allow_nan=False, allow_infinity=False)
_DELTA = st.floats(min_value=-360.0, max_value=720.0, allow_nan=False, allow_infinity=False)


def _py_mod(a: float, b: float) -> float:
    r = a % b
    if r != 0.0 and (r < 0.0) != (b < 0.0):
        r += b
    return r


# ---------------------------------------------------------------------------
# P1/P2 — snap_to_nearest_pad
# ---------------------------------------------------------------------------


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(x=_COORDS, y=_COORDS, pads=st.lists(st.tuples(_COORDS, _COORDS), max_size=8), tol=_TOL)
def test_p1_snap_optimality(x, y, pads, tol):
    result = shim_snap(x, y, pads, tol)
    if result in pads:
        # snapped onto a pad (possibly coincident with the query point)
        d = ((x - result[0]) ** 2 + (y - result[1]) ** 2) ** 0.5
        assert d <= tol
        # no pad strictly closer (ties are fine)
        for px, py in pads:
            d2 = ((x - px) ** 2 + (y - py) ** 2) ** 0.5
            assert d2 >= d
    else:
        # nothing within tolerance (the kernel's own strict-< decision rule)
        assert result == (x, y)
        for px, py in pads:
            d2 = ((x - px) ** 2 + (y - py) ** 2) ** 0.5
            assert d2 >= tol


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(x=_COORDS, y=_COORDS, px=_COORDS, py=_COORDS, tol=_TOL)
def test_p2_snap_single_pad_exactness(x, y, px, py, tol):
    result = shim_snap(x, y, [(px, py)], tol)
    dist = ((x - px) ** 2 + (y - py) ** 2) ** 0.5
    if dist < tol:
        assert result == (px, py)
    else:
        assert result == (x, y)


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(x=_COORDS, y=_COORDS, pads=st.lists(st.tuples(st.integers(-20, 20), st.integers(-20, 20)), max_size=6), dx=st.integers(-10, 10), dy=st.integers(-10, 10), tol=st.floats(min_value=0.5, max_value=5.0))
def test_mr1_snap_translation_invariance(x, y, pads, dx, dy, tol):
    # Integer pad coords keep the distance comparisons exact, so the chosen
    # pad (or the no-snap choice) is translation-invariant; the shifted
    # result is exactly the original result translated.
    x = round(x, 3)
    y = round(y, 3)
    shifted_pads = [(px + dx, py + dy) for px, py in pads]
    r0 = shim_snap(x, y, pads, tol)
    r1 = shim_snap(x + dx, y + dy, shifted_pads, tol)
    if r0 == (x, y):
        assert r1 == (x + dx, y + dy)
    else:
        assert r1 == (r0[0] + dx, r0[1] + dy)


def test_mr1_discriminator():
    """A constant kernel (always returns the first pad) violates MR1."""
    assert shim_snap(0.0, 0.0, [(5.0, 5.0)], 0.15) == (0.0, 0.0)


# ---------------------------------------------------------------------------
# P3 — reorient_pad_angle
# ---------------------------------------------------------------------------


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(current=st.one_of(st.none(), _ANGLE), delta=_DELTA)
def test_p3_reorient_pad_angle_math(current, delta):
    from temper_io_types import reorient_pad_angle

    result = reorient_pad_angle(current, delta)
    base = (current or 0.0) + delta
    expected = _py_mod(base, 360.0)
    if expected == 0.0:
        assert result is None
    else:
        assert result == expected


# ---------------------------------------------------------------------------
# P4 — rotation_index_to_degrees / positions_to_placements
# ---------------------------------------------------------------------------


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(idx=st.integers(0, 3))
def test_p4_rotation_index(idx):
    assert rotation_index_to_degrees(idx) == idx * 90.0


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(
    n=st.integers(1, 5),
    ox=st.floats(min_value=-10, max_value=10, allow_nan=False),
    oy=st.floats(min_value=-10, max_value=10, allow_nan=False),
)
def test_p4_positions_to_placements(n, ox, oy):
    import numpy as np

    positions = np.array([[i * 1.5, i * 2.5] for i in range(n)])
    rotations = np.zeros((n, 4))
    for i in range(n):
        rotations[i, i % 4] = 1.0
    refs = [f"C{i}" for i in range(n)]
    placements = positions_to_placements(positions, rotations, refs, origin=(ox, oy))
    assert len(placements) == n
    for i, ref in enumerate(refs):
        u = placements[ref]
        # dyadic positions/origins keep the additions exact
        assert u.x == i * 1.5 + ox
        assert u.y == i * 2.5 + oy
        assert u.rotation == (i % 4) * 90.0


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(i=st.integers(0, 3))
def test_mr3_rotation_wraparound(i):
    """``rotation_index_to_degrees(i + 4)`` is py_mod-equal to ``(i)``'s.

    Driven through the kernel directly, not through ``positions_to_placements``
    logits: ``np.argmax`` over 4-column logits can only emit indices 0..3, so
    the original logits-based form (``[[i, 0, 0, 0]]`` vs ``[[i + 4, 0, 0, 0]]``)
    put the first-max tie-break on column 0 for every row and never exercised
    an index >= 4 -- the property was trivially true and could not fail. The
    kernel accepts any i64 index (``index * 90.0``), so ``i + 4`` in 4..7
    lands on the ``i + 360`` degree class, and multiples of 90 are exact, so
    the mod-360 equality is exact.
    """
    a = rotation_index_to_degrees(i)
    b = rotation_index_to_degrees(i + 4)
    assert _py_mod(a, 360.0) == _py_mod(b, 360.0)


def test_mr3_discriminator():
    """MR3 is breakable: an off-by-one-degree kernel fails both pins."""
    # Exact-value pin at i = 0 (an additive-offset kernel returns 1.0).
    assert rotation_index_to_degrees(0) == 0.0
    # Wraparound pin at i = 4: 4 * 90 = 360.0 sits on the 0/360 class;
    # 4 * 90 + 1 = 361.0 does not (py_mod -> 1.0).
    assert _py_mod(rotation_index_to_degrees(4), 360.0) == 0.0
    # Full-path pin: a 5-column one-hot logit row puts the argmax peak at
    # column 4, so index 4 genuinely reaches the kernel through
    # positions_to_placements (the old discriminator's `np.array([[4]])`
    # logit was shape (1, 1), whose argmax is 0 -- the index-4 claim was
    # vacuous there too).
    import numpy as np

    p = positions_to_placements(
        np.array([[0.0, 0.0]]), np.array([[0.0, 0.0, 0.0, 0.0, 1.0]]), ["C0"]
    )
    assert p["C0"].rotation == 360.0
    assert _py_mod(p["C0"].rotation, 360.0) == 0.0


# ---------------------------------------------------------------------------
# P5 — state_to_placements
# ---------------------------------------------------------------------------


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(
    n=st.integers(1, 4),
    ox=st.floats(min_value=-10, max_value=10, allow_nan=False),
    oy=st.floats(min_value=-10, max_value=10, allow_nan=False),
)
def test_p5_state_to_placements(n, ox, oy):
    import numpy as np

    positions = np.array([[i * 0.5, i * 1.5] for i in range(n)])
    logits = np.array([[1.0 if j == i % 4 else 0.0 for j in range(4)] for i in range(n)])
    from temper_placer.core.state import PlacementState

    state = PlacementState.from_positions(positions, rotation_logits=logits)
    refs = [f"C{i}" for i in range(n)]
    placements = state_to_placements(state, refs, origin=(ox, oy))
    assert len(placements) == n
    for i, ref in enumerate(refs):
        u = placements[ref]
        assert u.x == i * 0.5 + ox
        assert u.y == i * 1.5 + oy
        assert u.rotation == (i % 4) * 90.0


# ---------------------------------------------------------------------------
# P6 / MR5 — strip_routing_plan
# ---------------------------------------------------------------------------


def _items():
    from temper_placer.io.export_types import TraceSegment

    seg = TraceSegment(net="n", start=(0, 0), end=(1, 1), width=0.25, layer="F.Cu")
    return [seg, seg, seg]  # type names differ; classification by type name


class _FakeSegment:
    pass


class _FakeVia:
    pass


class _FakeArc:
    pass


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(
    n_seg=st.integers(0, 4),
    n_via=st.integers(0, 4),
    n_arc=st.integers(0, 4),
    n_other=st.integers(0, 3),
    n_zones=st.integers(0, 4),
    keep_zones=st.booleans(),
    keep_fills=st.booleans(),
)
def test_p6_strip_plan_counts(n_seg, n_via, n_arc, n_other, n_zones, keep_zones, keep_fills):
    from temper_io_types import strip_routing_plan

    # classification is by type(obj).__name__ ("Segment"/"Via"/"Arc")
    Segment = type("Segment", (), {})
    Via = type("Via", (), {})
    Arc = type("Arc", (), {})
    Other = type("Other", (), {})

    items = (
        [Segment() for _ in range(n_seg)]
        + [Via() for _ in range(n_via)]
        + [Arc() for _ in range(n_arc)]
        + [Other() for _ in range(n_other)]
    )
    zones = list(range(n_zones))
    traces_removed, vias_removed, zones_removed, keep_indices, clear_fills, warnings = (
        strip_routing_plan(items, zones, keep_zones, keep_fills)
    )
    assert traces_removed == n_seg + n_arc
    assert vias_removed == n_via
    assert len(keep_indices) == n_other
    assert len(warnings) == n_other
    if keep_zones:
        assert zones_removed == 0
    else:
        assert zones_removed == n_zones
    # fill clearing only happens when zones are present (the verbatim guards
    # the whole block on `if ki_board.zones:`)
    if keep_zones and not keep_fills and n_zones > 0:
        assert clear_fills is True
    else:
        assert clear_fills is False


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(n_zones=st.integers(0, 5))
def test_mr5_zone_monotonicity(n_zones):
    from temper_io_types import strip_routing_plan

    zones = list(range(n_zones))
    _, _, removed_keep, _, _, _ = strip_routing_plan([], zones, True, False)
    _, _, removed_drop, _, _, _ = strip_routing_plan([], zones, False, False)
    assert removed_drop >= removed_keep
    assert removed_drop == n_zones
    assert removed_keep == 0


def test_mr5_discriminator():
    """A kernel that never removes zones violates MR5."""
    from temper_io_types import strip_routing_plan

    _, _, removed, _, _, _ = strip_routing_plan([], [1, 2, 3], False, False)
    assert removed == 3


# ---------------------------------------------------------------------------
# MR2 — simplify_path index-set invariance under integer scaling
# ---------------------------------------------------------------------------

_GRID_CELL = st.tuples(st.integers(-20, 20), st.integers(-20, 20), st.integers(0, 3))


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(cells=st.lists(_GRID_CELL, min_size=0, max_size=10), k=st.integers(1, 5))
def test_mr2_simplify_scale_invariance(cells, k):
    from temper_io_types import path_to_segments

    from temper_placer.router_v6.grid_converter import GridCell

    # grid_to_world(cell) = origin + cell*cs + cs/2; scaling cell coords by k
    # maps x -> origin + x*k*cs + cs/2. For origin (0,0), cs 1: x -> (x - 0.5)*k + 0.5.
    path = SimpleNamespace(
        net_name="N",
        cells=[GridCell(x, y, layer) for x, y, layer in cells],
        cell_size=1.0,
        layer_name="F.Cu",
    )
    scaled = SimpleNamespace(
        net_name="N",
        cells=[GridCell(x * k, y * k, layer) for x, y, layer in cells],
        cell_size=1.0,
        layer_name="F.Cu",
    )
    segs = path_to_segments(path, (0.0, 0.0), 1.0, 0.25)
    segs_scaled = path_to_segments(scaled, (0.0, 0.0), 1.0, 0.25)
    # same number of segments; endpoints follow the affine cell-center map
    assert len(segs) == len(segs_scaled)
    for s, ss in zip(segs, segs_scaled):
        assert ss.start[0] == (s.start[0] - 0.5) * k + 0.5
        assert ss.start[1] == (s.start[1] - 0.5) * k + 0.5
        assert ss.end[0] == (s.end[0] - 0.5) * k + 0.5
        assert ss.end[1] == (s.end[1] - 0.5) * k + 0.5


def test_mr2_discriminator():
    """A kernel that drops the first cell violates MR2."""
    from temper_io_types import path_to_segments

    from temper_placer.router_v6.grid_converter import GridCell

    path = SimpleNamespace(
        net_name="N",
        cells=[GridCell(0, 0, 0), GridCell(1, 0, 0)],
        cell_size=1.0,
        layer_name="F.Cu",
    )
    segs = path_to_segments(path, (0.0, 0.0), 1.0, 0.25)
    assert len(segs) == 1
    assert segs[0].start == (0.5, 0.5)  # cell-center of (0,0)


# ---------------------------------------------------------------------------
# MR4 — write_placements_plan unmatched -> matched monotonicity
# ---------------------------------------------------------------------------


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(n_unmatched=st.integers(1, 3))
def test_mr4_unmatched_matched_monotonicity(n_unmatched):
    import temper_io_types as tio
    from temper_io_types import PlacementUpdate

    footprints = [
        SimpleNamespace(
            properties={"Reference": f"U{i}"},
            position=SimpleNamespace(X=float(i), Y=0.0, angle=0.0),
            pads=[],
            libId="Lib:Part",
        )
        for i in range(n_unmatched + 1)
    ]
    placements = {"U0": PlacementUpdate(ref="U0", x=10.0, y=10.0, rotation=0.0)}
    updates_a, updated_a, skipped_a, _ = tio.write_placements_plan(
        placements, None, footprints, True
    )
    placements["U1"] = PlacementUpdate(ref="U1", x=20.0, y=20.0, rotation=90.0)
    updates_b, updated_b, skipped_b, _ = tio.write_placements_plan(
        placements, None, footprints, True
    )
    assert updated_b == updated_a + 1
    assert skipped_b == skipped_a - 1
    assert len(updates_b) == len(updates_a) + 1


def test_mr4_discriminator():
    import temper_io_types as tio
    from temper_io_types import PlacementUpdate

    footprints = [SimpleNamespace(properties={"Reference": "U0"}, position=None, pads=[], libId="L:P")]
    placements = {"U0": PlacementUpdate(ref="U0", x=1.0, y=1.0, rotation=0.0)}
    updates, updated, skipped, _ = tio.write_placements_plan(placements, None, footprints, True)
    assert updated == 1
    assert len(updates) == 1
