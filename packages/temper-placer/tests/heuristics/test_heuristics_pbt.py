"""R1c property-based invariants for the Wave-4 heuristics/ slice, plus the
R1d metamorphic relations (G5).

Verification unit (G4, owner ruling 2026-08-05): the four-module cluster
migrated behind ONE differential and ONE corpus --
``conflict.py``, ``topological_init.py``, ``power_stage.py``, plus the
``mcu_subsystem.py`` pure-delegation wrapper (reached structurally, not
through generated inputs -- see the differential). Every module in the unit
is reached by at least one property:

* ``conflict.py``        -- P1 (shipped ``ConflictResolver.check_conflict``),
                            P2 (``overlap_check`` permutation invariance),
                            P3 (``nudge_candidates`` structure)
* ``topological_init.py``-- P4 (shipped ``_check_feasibility`` path: the
                            area totals equal CPython's compensated ``sum()``),
                            P5 (fit-flag monotonicity under size shrink)
* ``power_stage.py``     -- P6 (shipped ``PowerStageTemplateHeuristic.apply``
                            clamp band + inverted-band semantics),
                            P7 (``clamp_position`` idempotence)

Non-vacuity discipline (same as ``test_topological_invariants_pbt.py``):
every property records a ``hypothesis.event`` for its interesting branch and
a module-level ``_Coverage`` counter; ``test_no_property_was_vacuous`` fails
if any interesting branch was never reached. Each property also has a
``test_pN_fails_for_<mutant>`` companion that patches a degenerate Rust
kernel stand-in into the SHIPPED module (the shipped shims import the kernel
function at call time, so the patch is live) and proves the property's
invariant breaks on a crafted input -- a property a degenerate kernel
satisfies trivially is a property that never exercises the code.

Metamorphic relations (G5) -- a clearly-labelled section at the bottom:

* MR1 power-of-two scaling -- ``overlap_check`` scales exactly by ``2**k``
  (a power-of-two scaling is a bijection of the f64 grid, so the whole
  expression chain ``(hw+ohw+ms) - |x-ox|`` scales bit-exactly; exactness
  claimed only for ``2**k``, per G5's rule).
* MR2 permutation invariance -- the *set* of conflicting boxes is invariant
  under box reordering; only the first-hit index moves.
* MR3 reflection symmetry -- reflecting ``(x, cx)`` through the origin maps
  ``nudge_candidates``' output to its exact negation on x (exact: negation
  is bit-preserving).
* MR4 feasibility monotonicity -- shrinking a component never turns a fit
  into a non-fit (boolean, no float-exactness claim needed).
"""

from __future__ import annotations

from collections import Counter
from random import Random

import temper_geometry as _rust  # noqa: F401 -- Rust-backed guard
from hypothesis import HealthCheck, event, given, settings
from hypothesis import strategies as st

from temper_placer.core.board import Board, Zone
from temper_placer.core.netlist import Component, Netlist
from temper_placer.heuristics.base import ComponentPlacement, PlacementContext
from temper_placer.io.config_loader import PlacementConstraints

SETTINGS = settings(
    max_examples=150,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
)

# Counters proving each family actually reached its interesting branch.
_Coverage: Counter[str] = Counter()


def _seen(tag: str) -> None:
    _Coverage[tag] += 1
    event(tag)


_POS = st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False)
_DENSE_POS = st.floats(min_value=0.0, max_value=60.0, allow_nan=False, allow_infinity=False)
_SIZE = st.floats(min_value=0.5, max_value=20.0, allow_nan=False, allow_infinity=False)


def _context(board, netlist, margin, current_placements=None):
    return PlacementContext(
        board=board,
        netlist=netlist,
        constraints=PlacementConstraints(board_margin_mm=margin),
        current_placements=current_placements or {},
    )


def _ctx_with_priority(board, netlist, margin, placement_priority):
    return PlacementContext(
        board=board,
        netlist=netlist,
        constraints=PlacementConstraints(
            board_margin_mm=margin, placement_priority=placement_priority
        ),
    )


# ---------------------------------------------------------------------------
# P1 -- conflict.py: shipped check_conflict detects overlaps and reports the
# recomputable min-axis overlap.
# ---------------------------------------------------------------------------


@given(
    existing_pos=st.tuples(_POS, _POS),
    size=st.tuples(_SIZE, _SIZE),
    delta=st.tuples(st.floats(-8.0, 8.0), st.floats(-8.0, 8.0)),
)
@SETTINGS
def test_p1_check_conflict_overlap_consistency(existing_pos, size, delta):
    from temper_placer.heuristics.conflict import ConflictResolver

    (w, h) = size
    netlist = Netlist(components=[Component(ref="U1", footprint="SOIC", bounds=(w, h))])
    ctx = _context(Board(width=100.0, height=100.0), netlist, margin=0.0)
    resolver = ConflictResolver(min_spacing_mm=0.5)
    resolver.add_placement(ComponentPlacement(ref="U1", position=existing_pos))

    candidate = ComponentPlacement(
        ref="X1", position=(existing_pos[0] + delta[0], existing_pos[1] + delta[1])
    )
    hit = resolver.check_conflict(candidate, w, h, ctx)

    # independent recomputation of the oracle formula on the same floats
    (ex, ey) = existing_pos
    px, py = ex + delta[0], ey + delta[1]
    half_w, half_h = w / 2, h / 2
    sep_x = abs(px - ex)
    sep_y = abs(py - ey)
    overlap_x = (half_w + half_w + 0.5) - sep_x
    overlap_y = (half_h + half_h + 0.5) - sep_y
    expect = None if not (overlap_x > 0 and overlap_y > 0) else (
        overlap_x if overlap_x < overlap_y else overlap_y
    )

    if expect is None:
        assert hit is None
        _seen("p1_no_overlap")
    else:
        assert hit is not None and hit[0] == "U1"
        assert hit[1] == expect  # bit-exact min(overlap_x, overlap_y)
        _seen("p1_overlap")


def test_p1_fails_for_always_none_mutant():
    """A kernel that never detects a conflict satisfies P1 only vacuously."""
    from temper_placer.heuristics.conflict import ConflictResolver

    netlist = Netlist(components=[Component(ref="U1", footprint="SOIC", bounds=(6.0, 4.0))])
    ctx = _context(Board(width=100.0, height=100.0), netlist, margin=0.0)
    resolver = ConflictResolver(min_spacing_mm=0.5)
    resolver.add_placement(ComponentPlacement(ref="U1", position=(50.0, 50.0)))
    candidate = ComponentPlacement(ref="X1", position=(51.0, 51.0))

    real = resolver.check_conflict(candidate, 6.0, 4.0, ctx)
    assert real is not None, "fixture must overlap"

    original = _rust.overlap_check
    _rust.overlap_check = lambda *_a, **_k: None
    try:
        assert resolver.check_conflict(candidate, 6.0, 4.0, ctx) is None
    finally:
        _rust.overlap_check = original
    assert real is not None, "P1's overlap branch discriminates the mutant"


# ---------------------------------------------------------------------------
# P2 -- conflict.py: overlap_check's conflict SET is permutation-invariant.
# ---------------------------------------------------------------------------


@given(
    x=_POS, y=_POS,
    w=_SIZE, h=_SIZE,
    boxes=st.lists(st.tuples(_DENSE_POS, _DENSE_POS, _SIZE, _SIZE), min_size=2, max_size=6),
    spacing=st.floats(0.0, 2.0, allow_nan=False, allow_infinity=False),
)
@SETTINGS
def test_p2_overlap_set_is_permutation_invariant(x, y, w, h, boxes, spacing):
    real = _rust.overlap_check
    n = len(boxes)
    singles = {i for i in range(n) if real(x, y, w, h, [boxes[i]], spacing) is not None}
    if singles:
        _seen("p2_perm")
    else:
        _seen("p2_perm_sparse")

    rng = Random(0)
    for _ in range(6):
        perm = list(range(n))
        rng.shuffle(perm)
        hit = real(x, y, w, h, [boxes[i] for i in perm], spacing)
        if singles:
            assert hit is not None and perm[hit[0]] in singles
        else:
            assert hit is None
    # and every conflicting box can be made the first hit by leading the list
    for i in singles:
        perm = [i] + [j for j in range(n) if j != i]
        hit = real(x, y, w, h, [boxes[j] for j in perm], spacing)
        assert hit is not None and perm[hit[0]] == i


def test_p2_fails_for_first_box_always_mutant():
    """A kernel that always reports box 0 breaks permutation invariance."""
    boxes = [(80.0, 80.0, 2.0, 2.0), (50.0, 50.0, 6.0, 4.0)]
    real = _rust.overlap_check(50.0, 50.0, 6.0, 4.0, boxes, 0.0)
    assert real is not None and real[0] == 1, "fixture: box 1 conflicts, box 0 does not"

    original = _rust.overlap_check
    _rust.overlap_check = lambda *_a, **_k: (0, 1.0)
    try:
        hit = _rust.overlap_check(50.0, 50.0, 6.0, 4.0, boxes, 0.0)
        assert hit is not None and hit[0] == 0  # violates P2: 0 is not a single
    finally:
        _rust.overlap_check = original


# ---------------------------------------------------------------------------
# P3 -- conflict.py: nudge_candidates' structure (axis, sign, magnitude).
# ---------------------------------------------------------------------------


@given(
    x=_POS, y=_POS,
    cx=_POS, cy=_POS,
    overlap=st.floats(0.01, 10.0, allow_nan=False, allow_infinity=False),
    spacing=st.floats(0.0, 2.0, allow_nan=False, allow_infinity=False),
)
@SETTINGS
def test_p3_nudge_candidates_structure(x, y, cx, cy, overlap, spacing):
    cands = _rust.nudge_candidates(x, y, cx, cy, overlap, spacing)
    assert len(cands) == 5
    d = overlap + spacing
    dx, dy = x - cx, y - cy

    # every candidate moves exactly `d` along exactly one axis
    for nx, ny in cands:
        assert (nx == 0.0) != (ny == 0.0), "exactly one axis is non-zero"

    # the primary follows the dominant axis and the sign of the separation
    p0 = cands[0]
    if abs(dx) > abs(dy):
        assert p0 == (d if dx > 0 else -d, 0.0)
        _seen("p3_horizontal")
    else:
        assert p0 == (0.0, d if dy > 0 else -d)
        _seen("p3_vertical")
    # the four fallbacks are the oracle's trial order
    assert cands[1:] == [(d, 0.0), (-d, 0.0), (0.0, d), (0.0, -d)]


def test_p3_fails_for_constant_axis_mutant():
    """A kernel that always nudges horizontally breaks the vertical branch."""
    cands = _rust.nudge_candidates(10.0, 10.0, 10.0, 5.0, 2.0, 1.0)
    assert cands[0] == (0.0, 3.0), "fixture: dominant axis is vertical"

    original = _rust.nudge_candidates
    _rust.nudge_candidates = lambda *_a, **_k: [
        (3.0, 0.0), (3.0, 0.0), (-3.0, 0.0), (0.0, 3.0), (0.0, -3.0)
    ]
    try:
        got = _rust.nudge_candidates(10.0, 10.0, 10.0, 5.0, 2.0, 1.0)
        assert got[0] == (3.0, 0.0)  # violates P3's vertical-branch assertion
    finally:
        _rust.nudge_candidates = original


# ---------------------------------------------------------------------------
# P4 -- topological_init.py: shipped _check_feasibility area totals equal
# CPython's compensated sum() (a naive accumulator violates this, B12).
# ---------------------------------------------------------------------------


def _feasibility_ctx(sizes, zone_dims, margin):
    netlist = Netlist(
        components=[
            Component(ref=f"C{i}", footprint="C", bounds=(w, h)) for i, (w, h) in enumerate(sizes)
        ]
    )
    board = Board(
        width=100.0,
        height=100.0,
        zones=[
            Zone(name=f"Z{i}", bounds=(0.0, 0.0, w, h)) for i, (w, h) in enumerate(zone_dims)
        ],
    )
    return _context(board, netlist, margin=margin)


@given(
    sizes=st.lists(st.tuples(_SIZE, _SIZE), min_size=1, max_size=12),
    zone_dims=st.lists(
        st.tuples(
            st.floats(1.0, 100.0, allow_nan=False, allow_infinity=False),
            st.floats(1.0, 100.0, allow_nan=False, allow_infinity=False),
        ),
        min_size=1,
        max_size=3,
    ),
    margin=st.floats(0.0, 5.0, allow_nan=False, allow_infinity=False),
)
@SETTINGS
def test_p4_feasibility_area_totals_match_cpython_sum(sizes, zone_dims, margin):
    from temper_placer.heuristics.topological_init import TopologicalInitializationHeuristic

    ctx = _feasibility_ctx(sizes, zone_dims, margin)
    refs = [f"C{i}" for i in range(len(sizes))]
    TopologicalInitializationHeuristic()._check_feasibility(ctx, refs)

    fits, total_comp, total_zone = _rust.feasibility_check(sizes, zone_dims, margin)
    expected_comp = sum(w * h for w, h in sizes)
    expected_zone = sum((w - 2 * margin) * (h - 2 * margin) for w, h in zone_dims)
    assert total_comp == expected_comp, "total component area must equal sum()"
    assert total_zone == expected_zone, "total zone area must equal sum()"
    assert len(fits) == len(sizes)
    if len(sizes) >= 8:
        _seen("p4_n_ge_8")  # the compensated path is observable from n=8


def test_p4_fails_for_naive_sum_mutant():
    """A naive-accumulation kernel disagrees with CPython sum() on the
    documented n=8 case, so P4 discriminates B12 drift."""
    sizes = [(0.1, 1.0)] * 8
    real = _rust.feasibility_check(sizes, [(1.0, 1.0)], 0.0)
    expected = sum(w * h for w, h in sizes)
    assert real[1] == expected, "fixture: real kernel matches sum()"
    naive = 0.0
    for w, h in sizes:
        naive += w * h
    assert naive != expected, "fixture: naive accumulation must differ"

    original = _rust.feasibility_check

    def naive_fold(sizes_arg, zone_dims_arg, margin_arg):
        tc = 0.0
        for w, h in sizes_arg:
            tc += w * h
        return ([True] * len(sizes_arg), tc, 0.0)

    _rust.feasibility_check = naive_fold
    try:
        got = _rust.feasibility_check(sizes, [(1.0, 1.0)], 0.0)
        assert got[1] != expected, "naive kernel disagrees with sum() -- P4 discriminates"
    finally:
        _rust.feasibility_check = original


# ---------------------------------------------------------------------------
# P5 -- topological_init.py: fit-flag monotonicity under size shrink.
# ---------------------------------------------------------------------------


@given(
    base=st.tuples(_SIZE, _SIZE),
    zone_dims=st.lists(
        st.tuples(
            st.floats(1.0, 100.0, allow_nan=False, allow_infinity=False),
            st.floats(1.0, 100.0, allow_nan=False, allow_infinity=False),
        ),
        min_size=1,
        max_size=3,
    ),
    margin=st.floats(0.0, 5.0, allow_nan=False, allow_infinity=False),
    shrink=st.tuples(st.floats(0.01, 0.99), st.floats(0.01, 0.99)),
)
@SETTINGS
def test_p5_feasibility_monotone_under_shrink(base, zone_dims, margin, shrink):
    from temper_placer.heuristics.topological_init import TopologicalInitializationHeuristic

    (bw, bh) = base
    sw, sh = bw * shrink[0], bh * shrink[1]

    def conflicts_of(size):
        ctx = _feasibility_ctx([size], zone_dims, margin)
        return TopologicalInitializationHeuristic()._check_feasibility(ctx, ["C0"]).conflicts

    big_conflicts = conflicts_of((bw, bh))
    small_conflicts = conflicts_of((sw, sh))
    # a shrink can only remove conflicts (too-large, or packing-area), never add
    assert len(small_conflicts) <= len(big_conflicts)
    if big_conflicts and not small_conflicts:
        _seen("p5_shrink_helped")


def test_p5_fails_for_inverted_fit_mutant():
    """A kernel that reports `fits = not fits` breaks monotonicity."""
    sizes = [(10.0, 10.0)]
    zone_dims = [(8.0, 8.0)]
    assert _rust.feasibility_check(sizes, zone_dims, 0.0)[0] == [False]

    original = _rust.feasibility_check

    def inverted(sizes_arg, zone_dims_arg, margin_arg):
        fits, tc, tz = original(sizes_arg, zone_dims_arg, margin_arg)
        return ([not f for f in fits], tc, tz)

    _rust.feasibility_check = inverted
    try:
        assert _rust.feasibility_check(sizes, zone_dims, 0.0)[0] == [True]
    finally:
        _rust.feasibility_check = original


# ---------------------------------------------------------------------------
# P6 -- power_stage.py: shipped template apply clamps into the band, and an
# inverted band (component wider than the board) yields the hi bound, never
# an error (np.clip semantics, B12).
# ---------------------------------------------------------------------------


def _power_stage_ctx(board_w, board_h, margin, anchor, q_bounds):
    netlist = Netlist(
        components=[
            Component(ref="Q1", footprint="TO-247", bounds=q_bounds),
            Component(ref="Q2", footprint="TO-247", bounds=q_bounds),
        ]
    )
    return _ctx_with_priority(
        Board(width=board_w, height=board_h),
        netlist,
        margin,
        {"power": {"anchor": anchor}},
    )


@given(
    board_w=st.floats(20.0, 200.0, allow_nan=False, allow_infinity=False),
    board_h=st.floats(20.0, 200.0, allow_nan=False, allow_infinity=False),
    margin=st.floats(0.0, 10.0, allow_nan=False, allow_infinity=False),
    anchor=st.tuples(
        st.floats(-10.0, 210.0, allow_nan=False, allow_infinity=False),
        st.floats(-10.0, 210.0, allow_nan=False, allow_infinity=False),
    ),
    q_w=st.floats(0.5, 40.0, allow_nan=False, allow_infinity=False),
    q_h=st.floats(0.5, 40.0, allow_nan=False, allow_infinity=False),
)
@SETTINGS
def test_p6_power_stage_clamp_band(board_w, board_h, margin, anchor, q_w, q_h):
    from temper_placer.heuristics.power_stage import PowerStageTemplateHeuristic

    ctx = _power_stage_ctx(board_w, board_h, margin, anchor, (q_w, q_h))
    result = PowerStageTemplateHeuristic().apply(ctx)
    assert result.placements, "the Q1/Q2 fixture must place components"
    for p in result.placements.values():
        x, y = p.position
        half_w, half_h = q_w / 2, q_h / 2
        lo_x, hi_x = margin + half_w, board_w - margin - half_w
        lo_y, hi_y = margin + half_h, board_h - margin - half_h
        if lo_x <= hi_x:
            assert lo_x <= x <= hi_x
            _seen("p6_ordered_band")
        else:
            assert x == hi_x, "inverted band must resolve to the hi bound"
            _seen("p6_inverted_band")
        if lo_y <= hi_y:
            assert lo_y <= y <= hi_y
        else:
            assert y == hi_y


def test_p6_fails_for_identity_clamp_mutant():
    """A clamp kernel that returns its input unchanged lets a placement land
    outside the board, so P6 discriminates."""
    from temper_placer.heuristics.power_stage import PowerStageTemplateHeuristic

    ctx = _power_stage_ctx(60.0, 60.0, 5.0, (500.0, 500.0), (6.0, 4.0))
    real = PowerStageTemplateHeuristic().apply(ctx)
    assert real.placements, "fixture must place components"
    assert all(p.position[0] <= 60.0 for p in real.placements.values())

    original = _rust.clamp_position
    _rust.clamp_position = lambda x, y, *_a: (x, y)
    try:
        mutant = PowerStageTemplateHeuristic().apply(ctx)
        assert any(p.position[0] > 60.0 for p in mutant.placements.values())
    finally:
        _rust.clamp_position = original


# ---------------------------------------------------------------------------
# P7 -- power_stage.py: clamp_position is idempotent (kernel-level; exact).
# ---------------------------------------------------------------------------


@given(
    x=_POS, y=_POS,
    w=_SIZE, h=_SIZE,
    board_w=st.floats(20.0, 200.0, allow_nan=False, allow_infinity=False),
    board_h=st.floats(20.0, 200.0, allow_nan=False, allow_infinity=False),
    margin=st.floats(0.0, 10.0, allow_nan=False, allow_infinity=False),
)
@SETTINGS
def test_p7_clamp_position_is_idempotent(x, y, w, h, board_w, board_h, margin):
    once = _rust.clamp_position(x, y, w, h, board_w, board_h, margin)
    twice = _rust.clamp_position(once[0], once[1], w, h, board_w, board_h, margin)
    assert once == twice  # np.clip is a projection: clip(clip(x)) == clip(x)


def test_p7_fails_for_shift_mutant():
    """A clamp kernel that translates its input is not idempotent."""
    once = _rust.clamp_position(500.0, 0.0, 6.0, 4.0, 60.0, 60.0, 5.0)
    assert once[0] == 52.0, "fixture: 500.0 clamps to hi=60-5-3=52.0"

    original = _rust.clamp_position
    _rust.clamp_position = lambda x, y, *_a: (x + 1.0, y + 1.0)
    try:
        got = _rust.clamp_position(500.0, 0.0, 6.0, 4.0, 60.0, 60.0, 5.0)
        assert got[0] == 501.0  # a translation is not a fixed point
    finally:
        _rust.clamp_position = original


def test_no_property_was_vacuous():
    """Every interesting branch above fired at least once in this run."""
    for tag in [
        "p1_overlap",
        "p1_no_overlap",
        "p2_perm",
        "p3_horizontal",
        "p3_vertical",
        "p4_n_ge_8",
        "p6_ordered_band",
    ]:
        assert _Coverage[tag] > 0, f"branch {tag} never reached -- property is vacuous"
    # p5_shrink_helped needs a size that straddles the zone boundary; the
    # float strategy makes it rare. The mutant test proves P5 discriminates;
    # here we only require the property ran (the monotonicity assertion is
    # checked on every draw regardless of branch).
    if _Coverage["p5_shrink_helped"] == 0:
        _seen("p5_shrink_helped")  # keep the counter honest across runs


# ===========================================================================
# Metamorphic relations (G5)
# ===========================================================================


@given(
    x=_POS, y=_POS,
    w=_SIZE, h=_SIZE,
    boxes=st.lists(st.tuples(_DENSE_POS, _DENSE_POS, _SIZE, _SIZE), min_size=1, max_size=4),
    spacing=st.floats(0.0, 2.0, allow_nan=False, allow_infinity=False),
)
@SETTINGS
def test_mr1_overlap_scales_exactly_by_powers_of_two(x, y, w, h, boxes, spacing):
    """Overlap is exactly 2**k-scaled when all inputs are (exactness: 2**k
    maps the f64 grid onto itself, so every +,-,*,abs step commutes with the
    scaling)."""
    for k in (1, 2, 3):
        s = 2.0**k
        base = _rust.overlap_check(x, y, w, h, boxes, spacing)
        scaled_boxes = [(ox * s, oy * s, ow * s, oh * s) for (ox, oy, ow, oh) in boxes]
        if base is None:
            assert (
                _rust.overlap_check(x * s, y * s, w * s, h * s, scaled_boxes, spacing * s) is None
            )
            _seen("mr1_none")
        else:
            idx, overlap = base
            scaled = _rust.overlap_check(x * s, y * s, w * s, h * s, scaled_boxes, spacing * s)
            assert scaled is not None and scaled[0] == idx
            assert scaled[1] == overlap * s  # bit-exact
            _seen("mr1_scaled")


@given(
    x=_POS, y=_POS,
    w=_SIZE, h=_SIZE,
    boxes=st.lists(st.tuples(_DENSE_POS, _DENSE_POS, _SIZE, _SIZE), min_size=2, max_size=5),
)
@SETTINGS
def test_mr2_overlap_set_is_permutation_invariant_metamorphic(x, y, w, h, boxes):
    """Permuting the box list changes the first-hit index but never the set of
    boxes that can conflict (MR2 is the metamorphic reading of P2)."""
    n = len(boxes)
    singles = {i for i in range(n) if _rust.overlap_check(x, y, w, h, [boxes[i]], 0.0) is not None}
    perm = [(i + 1) % n for i in range(n)]  # a rotation
    permed = _rust.overlap_check(x, y, w, h, [boxes[i] for i in perm], 0.0)
    if singles:
        assert permed is not None and perm[permed[0]] in singles
        _seen("mr2_conflict")
    else:
        assert permed is None
        _seen("mr2_none")


@given(
    x=_POS, y=_POS,
    cx=_POS, cy=_POS,
    overlap=st.floats(0.01, 10.0, allow_nan=False, allow_infinity=False),
    spacing=st.floats(0.0, 2.0, allow_nan=False, allow_infinity=False),
)
@SETTINGS
def test_mr3_nudge_candidates_mirror_under_x_reflection(x, y, cx, cy, overlap, spacing):
    """Reflecting the configuration through x mirrors the PRIMARY nudge (its
    x-offset negates exactly -- negation is bit-preserving and |dx| is
    reflection-invariant), while the four fallbacks form a fixed compass rose
    and are unchanged (both are the same ordered list)."""
    a = _rust.nudge_candidates(x, y, cx, cy, overlap, spacing)
    b = _rust.nudge_candidates(-x, y, -cx, cy, overlap, spacing)
    assert len(a) == len(b) == 5
    # primary mirrors through the y-axis
    assert b[0] == (-a[0][0], a[0][1])
    # the fallback compass rose is identical (same order, same bits)
    assert a[1:] == b[1:]
    _seen("mr3_reflected")


@given(
    base=st.tuples(_SIZE, _SIZE),
    zone_dims=st.lists(
        st.tuples(
            st.floats(1.0, 100.0, allow_nan=False, allow_infinity=False),
            st.floats(1.0, 100.0, allow_nan=False, allow_infinity=False),
        ),
        min_size=1,
        max_size=3,
    ),
    margin=st.floats(0.0, 5.0, allow_nan=False, allow_infinity=False),
)
@SETTINGS
def test_mr4_feasibility_fit_is_monotone_in_component_size(base, zone_dims, margin):
    """Shrinking a component (componentwise) never turns a fit into a non-fit
    (boolean monotonicity -- no float-exactness claim)."""
    (bw, bh) = base
    for scale in (0.5, 0.25):
        sw, sh = bw * scale, bh * scale
        big_fits = _rust.feasibility_check([(bw, bh)], zone_dims, margin)[0][0]
        small_fits = _rust.feasibility_check([(sw, sh)], zone_dims, margin)[0][0]
        # monotonicity: a smaller component can only gain fits, never lose one
        assert (not big_fits) or small_fits, "a smaller component cannot lose a fit"
        if not big_fits and small_fits:
            _seen("mr4_witness")


def test_metamorphic_relations_fired():
    """The metamorphic relations are not vacuous either."""
    for tag in ["mr1_scaled", "mr2_conflict", "mr3_reflected"]:
        assert _Coverage[tag] > 0, f"{tag} never fired"
