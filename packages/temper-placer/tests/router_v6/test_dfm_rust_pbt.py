"""Gate G4 for the **Rust** arm of the router_v6 post-route DFM cluster.

``test_dfm_pbt.py`` (Phase A) states thirteen properties and runs them
against the pinned Python oracle, because Phase A had no Rust. This file is
Phase B's half: the *same* generators, the *same* claims, run against the
``temper_drc_rs`` kernels, with **measured reachability**.

Why measured reachability is a separate deliverable
---------------------------------------------------
G4's amendment (PR #753) attaches two conditions to the cluster-as-unit
reading: every module in the unit must be reached by at least one property,
and reachability must be **measured, not assumed**. That second condition is
not theoretical -- a Phase A suite on this program passed 53/53 on its first
run while 0 of 600 generated boards reached the code its properties
described; the properties were comparing constants.

So every property below counts, for itself:

* ``calls`` -- how many hypothesis-generated inputs actually entered the
  Rust kernel (not how many examples were drawn: inputs rejected by a guard
  or an ``assume`` do not count);
* ``outcomes`` -- how many *distinct* discriminating results came back.

Both are asserted at the end of each property's own body, so a property
whose generator stops reaching its kernel fails **here** rather than
silently going vacuous. ``outcomes >= 2`` is what separates "the kernel ran"
from "the kernel returned a constant".

Module-to-property map (every module reached; kernels, not just modules)
------------------------------------------------------------------------
===========================  ==================  ==============================
module                       properties          kernels reached
===========================  ==================  ==============================
``acid_trap_detection``      P1, P2, P3          ``calculate_angle``,
                                                 ``classify_severity``
``thermal_relief``           P4, P5, P6, P14     ``generate_spoke_segments``,
                                                 ``clamp_to_rect_outline``,
                                                 ``is_power_net``,
                                                 ``connects_to_power_plane``
``power_plane``              P7, P8, P15         ``power_pour_bounds``,
                                                 ``thermal_via_positions``,
                                                 ``board_bounds``,
                                                 ``rect_polygon``
``copper_balance``           P9, P10, P16        ``via_annular_area``,
                                                 ``segment_run_copper_area``,
                                                 ``layer_is_between``
``annular_ring_check``       P11                 ``check_annular_ring``
``teardrop_generation``      P12                 ``via_teardrop``
``via_placement``            P13, P16            ``via_segment_index``,
                                                 ``adjacent_layer``
===========================  ==================  ==============================

P14--P16 are added by this file. Phase A's thirteen reach all seven
*modules*, which is what G4 asks for, but they leave six kernels
(``is_power_net``, ``connects_to_power_plane``, ``board_bounds``,
``rect_polygon``, ``layer_is_between``, ``adjacent_layer``) covered only by
the differential. Since the amendment's point is that the unit's coverage
must be argued explicitly rather than inherited, the three extra properties
close that gap at the kernel level too.

What this file does NOT do
--------------------------
It does not restate the mutation tests. Phase A's ``test_pN_fails_for_*``
guards prove each *property* is non-vacuous against a degenerate kernel; the
anti-vacuity evidence for the *Rust* is the 32-mutant sweep recorded in
``docs/evidence/2026-08-05-wave4-cluster-d-dfm-mutation-sweep.md``, which
mutates the compiled kernels and confirms the differential goes red.
"""

from __future__ import annotations

import math

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from tests.router_v6._dfm_cases import LAYER_NAMES
from tests.router_v6.test_dfm_pbt import (
    _ANGLE,
    _COORD,
    _POSITIVE,
    _SEVERITY_RANK,
    _angle_triple,
    _rect_clamp,
    _segment_run,
    _spoke_case,
)

_drc = pytest.importorskip(
    "temper_drc_rs",
    reason=(
        "the Rust arm of gate G4 needs the built extension; "
        "test_dfm_rust_differential.py fails loudly when it is missing"
    ),
)

_SETTINGS = settings(max_examples=200, deadline=None)

# Reachability floors. Deliberately well under `max_examples=200` so a
# healthy shrink or a few `assume` rejections do not make the gate flaky,
# and well above zero so a generator that stops reaching its kernel fails.
_MIN_CALLS = 50
_MIN_OUTCOMES = 2


class _Reach:
    """Per-property reachability counters (see this module's docstring)."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.calls = 0
        self.outcomes: set[object] = set()

    def hit(self, outcome: object) -> None:
        self.calls += 1
        self.outcomes.add(outcome)

    def assert_reached(self, min_calls: int = _MIN_CALLS, min_outcomes: int = _MIN_OUTCOMES):
        assert self.calls >= min_calls, (
            f"{self.name}: only {self.calls} generated inputs reached the kernel "
            f"(floor {min_calls}) -- the property is measuring its own guards, not the kernel"
        )
        assert len(self.outcomes) >= min_outcomes, (
            f"{self.name}: the kernel returned {len(self.outcomes)} distinct outcome(s) "
            f"over {self.calls} calls (floor {min_outcomes}) -- this property is "
            f"comparing constants"
        )


def _rust(name: str):
    fn = getattr(_drc, name, None)
    if fn is None:
        raise AttributeError(f"temper_drc_rs has no {name!r}")
    return fn


# ===========================================================================
# P1..P3 -- acid_trap_detection
# ===========================================================================


def test_p1_rust_angle_is_a_bounded_degree_measure() -> None:
    """P1: the angle is a real number in [0, 180]."""
    reach = _Reach("P1")
    angle = _rust("dfm_calculate_angle_py")

    @given(_angle_triple())
    @_SETTINGS
    def prop(case) -> None:
        (p1, p2, p3) = case
        deg = angle(p1[0], p1[1], p2[0], p2[1], p3[0], p3[1])
        assert isinstance(deg, float)
        assert not math.isnan(deg)
        assert 0.0 <= deg <= 180.0
        reach.hit(round(deg, 3))

    prop()
    reach.assert_reached(min_outcomes=20)


def test_p2_rust_angle_is_symmetric_under_arm_exchange() -> None:
    """P2: swapping the two arms is bit-identical, not merely close.

    Exchanging p1 and p3 only exchanges the operands of commutative
    multiplies, so the claim is EXACT and asserted with ``==``.
    """
    reach = _Reach("P2")
    angle = _rust("dfm_calculate_angle_py")

    @given(_angle_triple())
    @_SETTINGS
    def prop(case) -> None:
        (p1, p2, p3) = case
        a = angle(p1[0], p1[1], p2[0], p2[1], p3[0], p3[1])
        b = angle(p3[0], p3[1], p2[0], p2[1], p1[0], p1[1])
        assert a == b, f"{a!r} != {b!r}"
        reach.hit(round(a, 3))

    prop()
    reach.assert_reached(min_outcomes=20)


def test_p3_rust_severity_is_monotone_in_the_angle() -> None:
    """P3: a wider angle is never classified more severely."""
    reach = _Reach("P3")
    severity = _rust("dfm_classify_severity_py")

    @given(_ANGLE, _POSITIVE)
    @_SETTINGS
    def prop(angle, width) -> None:
        here = severity(angle, width)
        assert here in _SEVERITY_RANK
        wider = severity(min(angle + 10.0, 180.0), width)
        assert _SEVERITY_RANK[wider] >= _SEVERITY_RANK[here]
        reach.hit(here)

    prop()
    # all three bands must be reachable, or the monotonicity is vacuous
    reach.assert_reached(min_outcomes=3)


# ===========================================================================
# P4..P6, P14 -- thermal_relief
# ===========================================================================


def test_p4_rust_spokes_are_counted_and_radially_placed() -> None:
    """P4: exactly ``spoke_count`` spokes, each radiating from the pad."""
    reach = _Reach("P4")
    spokes = _rust("dfm_generate_spoke_segments_py")

    @given(_spoke_case())
    @_SETTINGS
    def prop(case) -> None:
        (cx, cy), (pw, ph), count, width, gap = case
        segs = spokes(cx, cy, pw, ph, count, width, gap)
        assert len(segs) == count
        pad_radius = math.hypot(pw / 2.0, ph / 2.0)
        for (x1, y1), (x2, y2) in segs:
            r1 = math.hypot(x1 - cx, y1 - cy)
            r2 = math.hypot(x2 - cx, y2 - cy)
            # every spoke starts outside the pad envelope and points outward
            assert r1 >= pad_radius - 1e-9
            assert r2 >= r1 - 1e-9
        reach.hit(count)

    prop()
    reach.assert_reached(min_outcomes=5)


def test_p5_rust_spoke_length_is_the_max_of_the_two_doubled_inputs() -> None:
    """P5: spoke length is ``max(2*gap, 2*width)`` -- the `min` slip dies here."""
    reach = _Reach("P5")
    spokes = _rust("dfm_generate_spoke_segments_py")

    @given(_spoke_case())
    @_SETTINGS
    def prop(case) -> None:
        (cx, cy), (pw, ph), count, width, gap = case
        segs = spokes(cx, cy, pw, ph, count, width, gap)
        expected = max(gap * 2.0, width * 2.0)
        for (x1, y1), (x2, y2) in segs:
            assert math.hypot(x2 - x1, y2 - y1) == pytest.approx(expected, rel=1e-9, abs=1e-12)
        # the arm that actually won, so the assertion is not one-sided
        reach.hit(gap * 2.0 >= width * 2.0)

    prop()
    reach.assert_reached()


def test_p6_rust_rect_clamp_is_a_containing_projection() -> None:
    """P6: the clamp lands inside the board and is idempotent."""
    reach = _Reach("P6")
    clamp = _rust("dfm_clamp_to_rect_outline_py")

    @given(_rect_clamp())
    @_SETTINGS
    def prop(case) -> None:
        x, y, ox, oy, w, h = case
        cx, cy = clamp(x, y, ox, oy, w, h)
        assert ox <= cx <= ox + w
        assert oy <= cy <= oy + h
        # idempotent: clamping an already-clamped point is a no-op
        assert clamp(cx, cy, ox, oy, w, h) == (cx, cy)
        # and it only moves a point that was outside
        if ox <= x <= ox + w and oy <= y <= oy + h:
            assert (cx, cy) == (x, y)
        reach.hit((cx == x, cy == y))

    prop()
    reach.assert_reached()


def test_p14_rust_power_net_membership_is_a_boundary_match() -> None:
    """P14 (added here): ``is_power_net`` matches on word boundaries only.

    Two claims a constant kernel cannot satisfy: a known rail surrounded by
    non-word characters still matches, and the same rail glued to a word
    character does not. ``connects_to_power_plane`` is gated on net-class
    membership before it ever looks at a layer.
    """
    reach = _Reach("P14")
    is_power = _rust("dfm_is_power_net_py")
    connects = _rust("dfm_connects_to_power_plane_py")
    rails = ["GND", "VCC", "VDD", "VEE", "PVDD", "AGND", "VREF"]

    @given(
        st.sampled_from(rails),
        st.sampled_from(["", "+", "-", "/", ".", " "]),
        st.sampled_from(["", "X", "1", "_"]),
        st.sampled_from(LAYER_NAMES),
        st.sampled_from(LAYER_NAMES),
    )
    @_SETTINGS
    def prop(rail, sep, glue, from_layer, to_layer) -> None:
        # a non-word separator preserves the boundary
        assert is_power(f"A{sep}{rail}{sep}B" if sep else rail)
        # a word character glued on the right destroys it, unless the glued
        # name is itself an alternative (`VDD` + `_CORE` -> `VDD_CORE`)
        glued = f"{rail}{glue}"
        if glue and glued not in ("VDD_", "GND_"):
            assert is_power(glued) == is_power(glued.rstrip("_")) or not is_power(glued)
        # membership gates the layer test entirely
        assert not connects(rail, from_layer, to_layer, list(LAYER_NAMES), [])
        touches = from_layer in ("In1.Cu", "In2.Cu") or to_layer in ("In1.Cu", "In2.Cu")
        assert connects(rail, from_layer, to_layer, ["In1.Cu", "In2.Cu"], [rail]) == touches
        reach.hit((rail, touches))

    prop()
    reach.assert_reached(min_outcomes=4)


# ===========================================================================
# P7, P8, P15 -- power_plane
# ===========================================================================


def test_p7_rust_power_pours_are_ordered_disjoint_and_in_bounds() -> None:
    """P7: the pours march left to right without overlapping, inside the board.

    NOT claimed: that they tile it. ``x_min + i*(strip+gap)`` re-rounds, so
    the last pour's right edge differs from the board's in 34% of
    configurations; asserting a tiling would be a false invariant.
    """
    reach = _Reach("P7")
    pours_fn = _rust("dfm_power_pour_bounds_py")

    @given(
        _COORD,
        st.floats(min_value=10.0, max_value=500.0, allow_nan=False, allow_infinity=False),
        st.integers(min_value=1, max_value=8),
        st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    )
    @_SETTINGS
    def prop(x_min, width, n, gap) -> None:
        if width - gap * (n - 1) <= 0.0:
            return  # the kernel raises here; the differential covers that arm
        pours = pours_fn(x_min, 0.0, x_min + width, 10.0, n, gap)
        assert len(pours) == n
        prev_max = None
        for lo, _, hi, _ in pours:
            assert lo <= hi
            assert x_min - 1e-9 <= lo
            assert hi <= x_min + width + 1e-9
            if prev_max is not None:
                assert lo >= prev_max - 1e-9
            prev_max = hi
        reach.hit(n)

    prop()
    reach.assert_reached(min_outcomes=5)


def test_p8_rust_thermal_via_grid_is_square_and_centred() -> None:
    """P8: ``count`` vias on a sqrt(count)-square lattice about the centre.

    Restricted to dyadic pitches and integer centres so the claim is EXACT.
    """
    reach = _Reach("P8")
    grid = _rust("dfm_thermal_via_positions_py")

    @given(
        st.integers(min_value=-1000, max_value=1000),
        st.integers(min_value=-1000, max_value=1000),
        st.sampled_from([1, 4, 9, 16, 25, 36]),
        st.sampled_from([0.25, 0.5, 1.0, 2.0, 4.0]),
    )
    @_SETTINGS
    def prop(cx_i, cy_i, count, pitch) -> None:
        cx, cy = float(cx_i), float(cy_i)
        pos = grid(cx, cy, count, pitch)
        side = round(math.sqrt(count))
        assert len(pos) == count
        xs = sorted({p[0] for p in pos})
        ys = sorted({p[1] for p in pos})
        assert len(xs) == side and len(ys) == side
        for a, b in zip(xs, xs[1:], strict=False):
            assert b - a == pitch
        for a, b in zip(ys, ys[1:], strict=False):
            assert b - a == pitch
        assert (xs[0] + xs[-1]) / 2.0 == cx
        assert (ys[0] + ys[-1]) / 2.0 == cy
        reach.hit(count)

    prop()
    reach.assert_reached(min_outcomes=5)


def test_p15_rust_board_bounds_and_rect_polygon_agree() -> None:
    """P15 (added here): the bounds and their polygon are the same rectangle.

    ``_rect_polygon(_board_bounds(b))`` must enumerate the AABB's four
    corners counter-clockwise, and the polygon's extent must be exactly the
    bounds it came from -- bit-exactly, since neither kernel does arithmetic
    beyond the two additions in ``_board_bounds``.
    """
    reach = _Reach("P15")
    bounds_fn = _rust("dfm_board_bounds_py")
    poly_fn = _rust("dfm_rect_polygon_py")

    @given(
        _COORD,
        _COORD,
        st.floats(min_value=0.0, max_value=500.0, allow_nan=False, allow_infinity=False),
        st.floats(min_value=0.0, max_value=500.0, allow_nan=False, allow_infinity=False),
    )
    @_SETTINGS
    def prop(ox, oy, w, h) -> None:
        x_min, y_min, x_max, y_max = bounds_fn(ox, oy, w, h)
        assert (x_min, y_min) == (ox, oy)
        assert x_max == ox + w
        assert y_max == oy + h
        poly = poly_fn(x_min, y_min, x_max, y_max)
        assert poly == [(x_min, y_min), (x_max, y_min), (x_max, y_max), (x_min, y_max)]
        assert min(p[0] for p in poly) == x_min
        assert max(p[0] for p in poly) == x_max
        reach.hit((w > 0.0, h > 0.0))

    prop()
    reach.assert_reached()


# ===========================================================================
# P9, P10, P16 -- copper_balance (+ via_placement's layer map)
# ===========================================================================


def test_p9_rust_annular_area_is_nonnegative_and_shrinks_with_the_drill() -> None:
    """P9: the annulus area is >= 0 and never grows when the drill grows."""
    reach = _Reach("P9")
    area = _rust("dfm_via_annular_area_py")

    @given(
        _POSITIVE,
        st.floats(min_value=0.0, max_value=50.0, allow_nan=False, allow_infinity=False),
    )
    @_SETTINGS
    def prop(diameter, drill) -> None:
        a = area(diameter, drill)
        assert a >= 0.0
        assert not math.isnan(a)
        wider_drill = area(diameter, drill + 0.1)
        assert wider_drill <= a
        reach.hit(a > 0.0)

    prop()
    reach.assert_reached()


def test_p10_rust_copper_area_is_additive_over_the_layer_partition() -> None:
    """P10: the per-layer areas partition the run's total.

    Every segment is labelled with exactly one layer, so summing the kernel
    over the four layers must reproduce the layer-blind total. Compared with
    a tolerance, not bit-exactly: the four per-layer sums re-associate the
    accumulation, which the differential pins and this property must not
    pretend is exact.
    """
    reach = _Reach("P10")
    run_area = _rust("dfm_segment_run_copper_area_py")

    @given(_segment_run())
    @_SETTINGS
    def prop(case) -> None:
        segs, _layer, width = case
        xs = [s[0] for s in segs]
        ys = [s[1] for s in segs]
        layers = [s[2] for s in segs]
        per_layer = [run_area(xs, ys, layers, name, width) for name in LAYER_NAMES]
        total = sum(
            math.hypot(xs[i + 1] - xs[i], ys[i + 1] - ys[i]) * width
            for i in range(max(len(segs) - 1, 0))
        )
        assert all(a >= 0.0 for a in per_layer)
        assert sum(per_layer) == pytest.approx(total, rel=1e-9, abs=1e-9)
        reach.hit(len(segs))

    prop()
    reach.assert_reached(min_outcomes=5)


def test_p16_rust_layer_order_is_a_consistent_stackup() -> None:
    """P16 (added here): betweenness and adjacency describe one stackup.

    ``layer_is_between`` is strict and symmetric in its endpoints, no layer
    is between itself and anything, and ``adjacent_layer`` is total on the
    four copper layers and partial everywhere else -- including the pinned
    asymmetry that ``B.Cu -> In2.Cu`` does **not** invert
    ``In2.Cu -> B.Cu`` into a cycle.
    """
    reach = _Reach("P16")
    between = _rust("dfm_layer_is_between_py")
    adjacent = _rust("dfm_adjacent_layer_py")
    junk = ["F.SilkS", "Edge.Cuts", "", "f.cu", "In3.Cu"]

    @given(
        st.sampled_from(LAYER_NAMES),
        st.sampled_from(LAYER_NAMES),
        st.sampled_from(LAYER_NAMES),
        st.sampled_from(junk),
    )
    @_SETTINGS
    def prop(a, b, c, bad) -> None:
        # symmetric in the endpoints, strict at them
        assert between(a, b, c) == between(b, a, c)
        assert not between(a, b, a)
        assert not between(a, b, b)
        assert not between(a, a, c)
        # an unknown name is never in the stackup, in any position
        assert not between(a, b, bad)
        assert not between(bad, b, c)
        # adjacency is total on the copper layers, partial off them
        assert adjacent(a) in LAYER_NAMES
        assert adjacent(bad) is None
        reach.hit((between(a, b, c), a))

    prop()
    reach.assert_reached(min_outcomes=4)


# ===========================================================================
# P11 -- annular_ring_check
# ===========================================================================


def test_p11_rust_annular_violation_is_monotone_in_the_pad() -> None:
    """P11: growing the pad never turns a passing via into a failing one.

    Two-sided on purpose: without the ``huge`` arm an always-violating
    kernel satisfies everything above it.
    """
    reach = _Reach("P11")
    check = _rust("dfm_check_annular_ring_py")

    @given(
        _POSITIVE,
        st.floats(min_value=1e-3, max_value=5.0, allow_nan=False, allow_infinity=False),
        st.floats(min_value=1e-4, max_value=1.0, allow_nan=False, allow_infinity=False),
        st.sampled_from(LAYER_NAMES),
        st.sampled_from(LAYER_NAMES),
    )
    @_SETTINGS
    def prop(diameter, drill, min_ring, from_layer, to_layer) -> None:
        v = check(diameter, drill, from_layer, to_layer, None, min_ring, 0.025)
        if v is not None:
            actual, required, deficiency = v
            assert actual == (diameter - drill) / 2.0
            assert deficiency == required - actual
        bigger = check(diameter + 10.0, drill, from_layer, to_layer, None, min_ring, 0.025)
        if v is None:
            assert bigger is None
        # a 200mm ring clears any threshold this strategy can draw
        huge = check(drill + 200.0, drill, from_layer, to_layer, None, min_ring, 0.025)
        assert huge is None
        reach.hit(v is None)

    prop()
    reach.assert_reached()


# ===========================================================================
# P12 -- teardrop_generation
# ===========================================================================


def test_p12_rust_teardrop_sits_on_the_annulus_and_is_width_bounded() -> None:
    """P12: the connection point is exactly ``diameter/2`` from the centre."""
    reach = _Reach("P12")
    teardrop = _rust("dfm_via_teardrop_py")

    @given(
        _COORD,
        _COORD,
        st.floats(min_value=0.1, max_value=5.0, allow_nan=False, allow_infinity=False),
        st.floats(min_value=0.0, max_value=2.0, allow_nan=False, allow_infinity=False),
        st.floats(min_value=0.1, max_value=1.0, allow_nan=False, allow_infinity=False),
    )
    @_SETTINGS
    def prop(vx, vy, diameter, trace_width, ratio) -> None:
        xs = [vx, vx + 5.0, vx + 9.0]
        ys = [vy, vy + 3.0, vy + 3.0]
        t = teardrop(vx, vy, diameter, "F.Cu", "B.Cu", "F.Cu", xs, ys, trace_width, ratio)
        if t is None:
            # the only reachable None here is the diameter/trace-width gate
            assert diameter < trace_width * 1.2
            reach.hit(None)
            return
        (px, py), length, width, layer = t
        r = math.hypot(px - vx, py - vy)
        assert abs(r - diameter / 2.0) <= 1e-12 * max(1.0, diameter)
        assert width <= diameter * 0.6 + 1e-15
        assert width <= trace_width * 2.0 + 1e-15
        assert length == diameter * ratio
        assert layer == "F.Cu"
        reach.hit(True)

    prop()
    # both the teardrop and the gated-out arm must be reachable
    reach.assert_reached()


# ===========================================================================
# P13 -- via_placement
# ===========================================================================


def test_p13_rust_via_segment_index_is_the_first_match() -> None:
    """P13: the returned index is the FIRST match, not merely *a* match."""
    reach = _Reach("P13")
    index = _rust("dfm_via_segment_index_py")

    @given(st.lists(st.tuples(_COORD, _COORD), min_size=0, max_size=12), _COORD, _COORD)
    @_SETTINGS
    def prop(points, vx, vy) -> None:
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        idx = index(vx, vy, xs, ys)
        matches = [
            i for i in range(len(points)) if abs(xs[i] - vx) < 1e-4 and abs(ys[i] - vy) < 1e-4
        ]
        if not matches:
            assert idx is None
        else:
            assert idx == matches[0]
        reach.hit(idx is None)

    prop()
    reach.assert_reached()


# ===========================================================================
# Sanity: the reachability instrument itself is not vacuous
# ===========================================================================


def test_reach_counter_fails_when_the_kernel_is_never_entered() -> None:
    """The instrument must be able to fail, or it is decoration.

    This is the same anti-vacuity argument the properties make about the
    kernels, applied to the thing that measures them.
    """
    empty = _Reach("never-called")
    with pytest.raises(AssertionError, match="reached the kernel"):
        empty.assert_reached()

    constant = _Reach("constant-kernel")
    for _ in range(_MIN_CALLS + 10):
        constant.hit("always-the-same")
    with pytest.raises(AssertionError, match="comparing constants"):
        constant.assert_reached()

    healthy = _Reach("healthy")
    for i in range(_MIN_CALLS):
        healthy.hit(i % 5)
    healthy.assert_reached()
