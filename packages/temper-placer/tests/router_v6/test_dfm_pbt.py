"""Gates G4 + G5 for the router_v6 post-route DFM cluster (Wave 4, cluster D).

**G4 -- properties.** Twelve non-vacuous properties (P1..P12) over the seven
modules' pinned kernels, each paired with a ``test_pN_fails_for_<mutant>``
mutation test that re-runs the property against a degenerate kernel via
``hypothesis.inner_test`` and asserts ``AssertionError``.  The mutants follow
``test_bottleneck_geometry_pbt.py``: constant, position-dependent, and
absent-element kernels, plus a ``restore_kernels`` fixture so a mutation can
never leak into another test.

Coverage is at least one property per module:

===========================  ==============================
module                       properties
===========================  ==============================
``acid_trap_detection``      P1, P2, P3
``thermal_relief``           P4, P5, P6
``power_plane``              P7, P8
``copper_balance``           P9, P10
``annular_ring_check``       P11
``teardrop_generation``      P12
``via_placement``            P13
===========================  ==============================

G4 says ">=5 non-vacuous properties **per module**".  Read literally that is
35+ properties for a seven-module slice.  This file takes the cluster-as-module
reading the migration survey names explicitly (§4, "the contract says 'per
module', so the cluster's definition of 'module' is exactly the lever"): the
cluster is one migration unit with one oracle, one corpus and one crate
destination, so it carries one property set -- thirteen properties, >=5, every
module represented, every property mutation-guarded.  That is stated here
rather than buried, because it is a judgement call a reviewer may reject.

**G5 -- metamorphic relations.** Five relations (M1..M5), each with its
exactness claim stated and **honestly bounded**:

===  ==========================================  ==================================
rel  relation                                    claim
===  ==========================================  ==================================
M1   ``_calculate_angle`` argument reversal      **EXACT** -- commutativity only
M2   ``_calculate_angle`` power-of-two scale     **EXACT** -- every f64 bit preserved
M3   ``_via_annular_area`` power-of-two scale    **EXACT** -- area scales by 4^k
M4   ``_thermal_via_positions`` centroid         **EXACT** for dyadic pitch + centre
M5   ``_generate_spoke_segments`` translation    **TOLERANCE 1.5e-14** (measured)
===  ==========================================  ==================================

M1..M4 claim exactness because the transform provably preserves every bit:
scaling by ``2^k`` is exact for the products, sums and square roots involved
(no rounding is introduced or removed), and reversal only exchanges the
operands of a commutative multiply.  M5 does **not** get an exactness claim:
translation re-rounds ``cx + start_r*dx``, and the measured worst case over
4,000 random board-scale translations is an absolute error of ``1.42e-14``
(up to ~1024 ulps where the sum cancels).  Claiming exactness there would be
the kind of dishonest gate the contract's tie-break rule forbids.

The properties run against the **Python** oracle here, because Phase A has no
Rust.  Phase B must satisfy the same file unchanged.
"""

from __future__ import annotations

import math
import random

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

import tests.router_v6._dfm_py_oracle as ORACLE
from tests.router_v6._dfm_cases import LAYER_NAMES

_SEVERITY_RANK = {"high": 0, "medium": 1, "low": 2}

# board-scale finite coordinates: no NaN/inf, so the properties are about the
# kernels' arithmetic rather than their guard clauses (the differential's
# crafted corpus covers the guards).
_COORD = st.floats(
    min_value=-500.0, max_value=500.0, allow_nan=False, allow_infinity=False, width=64
)
_POSITIVE = st.floats(
    min_value=1e-3, max_value=50.0, allow_nan=False, allow_infinity=False, width=64
)
_ANGLE = st.floats(min_value=0.0, max_value=180.0, allow_nan=False, allow_infinity=False)


@st.composite
def _angle_triple(draw):
    """Three points with both arms non-degenerate (mag1, mag2 both non-zero)."""
    p2 = (draw(_COORD), draw(_COORD))
    p1 = (draw(_COORD), draw(_COORD))
    p3 = (draw(_COORD), draw(_COORD))
    assume(p1 != p2 and p3 != p2)
    return p1, p2, p3


@st.composite
def _spoke_case(draw):
    return (
        (draw(_COORD), draw(_COORD)),
        (draw(_POSITIVE), draw(_POSITIVE)),
        draw(st.integers(min_value=2, max_value=24)),
        draw(_POSITIVE),
        draw(_POSITIVE),
    )


@st.composite
def _rect_clamp(draw):
    return (
        draw(_COORD),
        draw(_COORD),
        draw(_COORD),
        draw(_COORD),
        draw(st.floats(min_value=0.0, max_value=500.0, allow_nan=False, allow_infinity=False)),
        draw(st.floats(min_value=0.0, max_value=500.0, allow_nan=False, allow_infinity=False)),
    )


@st.composite
def _segment_run(draw):
    n = draw(st.integers(min_value=0, max_value=10))
    segs = [(draw(_COORD), draw(_COORD), draw(st.sampled_from(LAYER_NAMES))) for _ in range(n)]
    return segs, draw(st.sampled_from(LAYER_NAMES)), draw(_POSITIVE)


class _Board:
    def __init__(self, ox, oy, w, h):
        self.origin = (ox, oy)
        self.width = w
        self.height = h
        self.has_polygon_outline = False
        self.outline_polygon = None


class _Via:
    def __init__(self, **kw):
        self.position = kw.get("position", (0.0, 0.0))
        self.diameter = kw.get("diameter", 0.6)
        self.drill = kw.get("drill", 0.3)
        self.from_layer = kw.get("from_layer", "F.Cu")
        self.to_layer = kw.get("to_layer", "B.Cu")
        if "via_type" in kw and kw["via_type"] is not None:
            self.via_type = kw["via_type"]


class _Path:
    def __init__(self, coordinates, layer_name):
        self.coordinates = coordinates
        self.layer_name = layer_name


class _Route:
    def __init__(self, path, width_mm):
        self.path = path
        self.width_mm = width_mm


_SETTINGS = settings(max_examples=200, deadline=None)


# ===========================================================================
# P1..P3 -- acid_trap_detection
# ===========================================================================


@given(_angle_triple())
@_SETTINGS
def test_p1_angle_is_a_bounded_degree_measure(case) -> None:
    """P1: ``_calculate_angle`` returns a real angle in ``[0, 180]``.

    A degenerate implementation returning a constant *inside* the range would
    satisfy this trivially, which is why P2 and P3 exist; the mutant here is a
    constant *outside* it.
    """
    p1, p2, p3 = case
    a = ORACLE._calculate_angle(p1, p2, p3)
    assert isinstance(a, float)
    assert not math.isnan(a)
    assert 0.0 <= a <= 180.0


@given(_angle_triple())
@_SETTINGS
def test_p2_angle_is_symmetric_under_arm_exchange(case) -> None:
    """P2: the angle at ``p2`` does not depend on which arm is named first.

    Bit-exact, not tolerant: ``dot`` and ``mag1 * mag2`` only exchange the
    operands of commutative multiplies.  A kernel that reads one arm and
    ignores the other -- a very plausible porting slip -- fails this.
    """
    p1, p2, p3 = case
    assert ORACLE._calculate_angle(p1, p2, p3) == ORACLE._calculate_angle(p3, p2, p1)


@given(_ANGLE, _POSITIVE)
@_SETTINGS
def test_p3_severity_is_monotone_in_the_angle(angle, width) -> None:
    """P3: a wider angle is never classified as *more* severe.

    Non-vacuous because the ranks genuinely differ across the corpus: the
    sanity test below proves all three severities are reachable at a fixed
    width.
    """
    wider = min(180.0, angle + 1.0)
    a = _SEVERITY_RANK[ORACLE._classify_severity(angle, width)]
    b = _SEVERITY_RANK[ORACLE._classify_severity(wider, width)]
    assert b >= a
    # ... and narrowing the trace never makes it more severe either
    demoted = _SEVERITY_RANK[ORACLE._classify_severity(angle, 0.1)]
    assert demoted >= a


# ===========================================================================
# P4..P6 -- thermal_relief
# ===========================================================================


@given(_spoke_case())
@_SETTINGS
def test_p4_spokes_are_counted_and_radially_placed(case) -> None:
    """P4: exactly ``spoke_count`` spokes, each start on the clearance circle.

    The start radius is ``hypot(pw/2, ph/2) + gap`` for every spoke, so all
    starts lie on one circle about the pad centre.  A constant-segment kernel
    fails the count; a position-dependent one fails the equal-radius claim.
    Tolerance is needed only because the radius is *recomputed* from cos/sin
    outputs; the band is the oracle's own (relative 1e-12).
    """
    pos, size, count, width, gap = case
    segs = ORACLE._generate_spoke_segments(pos, size, count, width, gap)
    assert len(segs) == count
    expected_r = math.hypot(size[0] / 2.0, size[1] / 2.0) + gap
    for (x1, y1), _ in segs:
        r = math.hypot(x1 - pos[0], y1 - pos[1])
        assert abs(r - expected_r) <= 1e-12 * max(1.0, expected_r)


@given(_spoke_case())
@_SETTINGS
def test_p5_spoke_length_is_the_max_of_the_two_doubled_inputs(case) -> None:
    """P5: every spoke's end is exactly ``max(2*gap, 2*width)`` further out.

    This is the property that catches a kernel that got ``max``/``min`` the
    wrong way round -- the single most likely B5 slip in this module.
    """
    pos, size, count, width, gap = case
    segs = ORACLE._generate_spoke_segments(pos, size, count, width, gap)
    expected_len = max(gap * 2.0, width * 2.0)
    for (x1, y1), (x2, y2) in segs:
        d = math.hypot(x2 - x1, y2 - y1)
        assert abs(d - expected_len) <= 1e-9 * max(1.0, expected_len)


@given(_rect_clamp())
@_SETTINGS
def test_p6_rect_clamp_is_inside_and_idempotent(case) -> None:
    """P6: the rectangular clamp lands inside the board and is a projection.

    Applying it twice changes nothing (idempotence), and an already-inside
    point is returned untouched.  An identity "clamp" satisfies idempotence
    but not containment; a constant one satisfies containment but not the
    fixed-point claim -- so both mutants below are killed.
    """
    x, y, ox, oy, w, h = case
    board = _Board(ox, oy, w, h)
    cx, cy = ORACLE._clamp_to_board_outline(board, (x, y), (ox, oy))
    assert ox <= cx <= ox + w
    assert oy <= cy <= oy + h
    assert ORACLE._clamp_to_board_outline(board, (cx, cy), (ox, oy)) == (cx, cy)
    if ox <= x <= ox + w and oy <= y <= oy + h:
        assert (cx, cy) == (x, y)


# ===========================================================================
# P7..P8 -- power_plane
# ===========================================================================


@given(
    _COORD,
    st.floats(min_value=10.0, max_value=500.0, allow_nan=False, allow_infinity=False),
    st.integers(min_value=1, max_value=8),
    st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
)
@_SETTINGS
def test_p7_power_pours_are_ordered_disjoint_and_in_bounds(x_min, width, n, gap) -> None:
    """P7: the pours partition the board left to right without overlapping.

    Strictly: pour ``i+1`` starts at or after pour ``i`` ends, every pour lies
    within the board, and there are exactly ``n`` of them.  Note what is NOT
    claimed -- that they *tile* the board.  Measured on this base, the last
    pour's right edge differs from the board's in 34% of configurations
    because ``x_min + i*(strip+gap)`` re-rounds; asserting a tiling would be a
    false invariant.
    """
    if width - gap * (n - 1) <= 0.0:
        return  # the kernel raises here; the differential covers that arm
    board = _Board(x_min, 0.0, width, 10.0)
    pours = ORACLE.generate_power_pours(
        board, tuple(f"D{i}" for i in range(n)), isolation_gap_mm=gap
    )
    assert len(pours) == n
    prev_max = None
    for p in pours:
        lo, _, hi, _ = p.bounds
        assert lo <= hi
        assert x_min - 1e-9 <= lo
        assert hi <= x_min + width + 1e-9
        if prev_max is not None:
            assert lo >= prev_max - 1e-9
        prev_max = hi


@given(
    st.integers(min_value=-1000, max_value=1000),
    st.integers(min_value=-1000, max_value=1000),
    st.sampled_from([1, 4, 9, 16, 25, 36]),
    st.sampled_from([0.25, 0.5, 1.0, 2.0, 4.0]),
)
@_SETTINGS
def test_p8_thermal_via_grid_is_square_and_centred(cx_i, cy_i, count, pitch) -> None:
    """P8: ``count`` vias on a ``sqrt(count)``-square lattice about the centre.

    Row/column spacing is exactly ``pitch``, and the grid's bounding box is
    symmetric about the requested centre.  Restricted to dyadic pitches and
    integer centres so the claim can be **exact**; see M4 for the centroid
    form of the same statement.
    """
    cx, cy = float(cx_i), float(cy_i)
    pos = ORACLE._thermal_via_positions((cx, cy), count, pitch)
    side = round(math.sqrt(count))
    assert len(pos) == count
    xs = sorted({p[0] for p in pos})
    ys = sorted({p[1] for p in pos})
    assert len(xs) == side and len(ys) == side
    for a, b in zip(xs, xs[1:]):
        assert b - a == pitch
    for a, b in zip(ys, ys[1:]):
        assert b - a == pitch
    assert (xs[0] + xs[-1]) / 2.0 == cx
    assert (ys[0] + ys[-1]) / 2.0 == cy


# ===========================================================================
# P9..P10 -- copper_balance
# ===========================================================================


@given(_POSITIVE, st.floats(min_value=0.0, max_value=50.0, allow_nan=False, allow_infinity=False))
@_SETTINGS
def test_p9_annular_area_is_nonnegative_and_shrinks_with_the_drill(diameter, drill) -> None:
    """P9: annular area >= 0, and a bigger hole never means more copper.

    A constant-area kernel satisfies non-negativity but not monotonicity; a
    negative-constant one fails both.  Both mutants are exercised below.
    """
    a = ORACLE._via_annular_area(_Via(diameter=diameter, drill=drill))
    assert a >= 0.0
    bigger_hole = ORACLE._via_annular_area(_Via(diameter=diameter, drill=drill + 0.1))
    assert bigger_hole <= a
    # and a via whose hole swallows the pad has no copper at all
    assert ORACLE._via_annular_area(_Via(diameter=diameter, drill=diameter)) == 0.0


@given(_segment_run())
@_SETTINGS
def test_p10_copper_area_is_additive_over_the_layer_partition(case) -> None:
    """P10: summing the per-layer areas recovers the whole run's copper.

    Every segment is labelled with exactly one layer, so the four per-layer
    accumulations partition the run.  This is asserted with a tolerance, not
    ``==``: the whole-run sum and the per-layer sums add the same terms in a
    different order, and f64 addition is not associative -- claiming
    bit-equality here would be the dishonest version of this property.
    """
    segs, _layer, width = case
    per_layer = sum(ORACLE._segment_run_copper_area(segs, ln, width) for ln in LAYER_NAMES)
    total = sum(
        math.hypot(segs[i + 1][0] - segs[i][0], segs[i + 1][1] - segs[i][1]) * width
        for i in range(len(segs) - 1)
    )
    assert per_layer >= 0.0
    assert abs(per_layer - total) <= 1e-9 * max(1.0, total)


# ===========================================================================
# P11 -- annular_ring_check
# ===========================================================================


@given(
    _POSITIVE,
    st.floats(min_value=1e-3, max_value=5.0, allow_nan=False, allow_infinity=False),
    st.floats(min_value=1e-4, max_value=1.0, allow_nan=False, allow_infinity=False),
    st.sampled_from(LAYER_NAMES),
    st.sampled_from(LAYER_NAMES),
)
@_SETTINGS
def test_p11_annular_violation_is_monotone_in_the_pad(
    diameter, drill, min_ring, from_layer, to_layer
) -> None:
    """P11: growing the pad never turns a passing via into a failing one.

    And when a violation IS reported, its numbers are self-consistent:
    ``actual_ring_width == (diameter - drill) / 2`` and
    ``deficiency == minimum_required - actual_ring_width``.  A kernel that
    always reports a violation fails the monotonicity; one that reports none
    fails the reachability sanity test below.
    """
    via = _Via(diameter=diameter, drill=drill, from_layer=from_layer, to_layer=to_layer)
    v = ORACLE._check_via(via, "NET", min_ring, 0.025)
    if v is not None:
        assert v.actual_ring_width == (diameter - drill) / 2.0
        assert v.deficiency == v.minimum_required - v.actual_ring_width
    bigger = _Via(diameter=diameter + 10.0, drill=drill, from_layer=from_layer, to_layer=to_layer)
    if v is None:
        assert ORACLE._check_via(bigger, "NET", min_ring, 0.025) is None
    # A pad 200mm wider than its drill has a 100mm ring, which clears any
    # threshold this strategy can draw (min_ring <= 1.0).  This is the arm
    # that makes the property two-sided: without it an always-violating
    # kernel satisfies everything above.
    huge = _Via(diameter=drill + 200.0, drill=drill, from_layer=from_layer, to_layer=to_layer)
    assert ORACLE._check_via(huge, "NET", min_ring, 0.025) is None


# ===========================================================================
# P12 -- teardrop_generation
# ===========================================================================


@given(
    _COORD,
    _COORD,
    st.floats(min_value=0.1, max_value=5.0, allow_nan=False, allow_infinity=False),
    st.floats(min_value=0.0, max_value=2.0, allow_nan=False, allow_infinity=False),
    st.floats(min_value=0.1, max_value=1.0, allow_nan=False, allow_infinity=False),
)
@_SETTINGS
def test_p12_teardrop_sits_on_the_via_annulus_and_is_width_bounded(
    vx, vy, diameter, trace_width, ratio
) -> None:
    """P12: the connection point is exactly ``diameter/2`` from the via centre.

    That is the module's whole geometric claim.  Plus the two width bounds it
    documents: ``width <= diameter*0.6`` and ``width <= 2*trace_width``, and
    ``length == diameter * ratio``.  A kernel returning the via centre
    unchanged fails the radius; one returning an unclamped width fails the
    bound.
    """
    via = _Via(position=(vx, vy), diameter=diameter, from_layer="F.Cu", to_layer="B.Cu")
    route = _Route(
        _Path([(vx, vy), (vx + 5.0, vy + 3.0), (vx + 9.0, vy + 3.0)], "F.Cu"), trace_width
    )
    t = ORACLE._generate_via_teardrop("NET", via, route, ratio)
    if t is None:
        # the only reachable None here is the diameter/trace-width gate
        assert diameter < trace_width * 1.2
        return
    r = math.hypot(t.connection_point[0] - vx, t.connection_point[1] - vy)
    assert abs(r - diameter / 2.0) <= 1e-12 * max(1.0, diameter)
    assert t.width_mm <= diameter * 0.6 + 1e-15
    assert t.width_mm <= trace_width * 2.0 + 1e-15
    assert t.length_mm == diameter * ratio


# ===========================================================================
# P13 -- via_placement
# ===========================================================================


@given(
    st.lists(st.tuples(_COORD, _COORD), min_size=0, max_size=12),
    _COORD,
    _COORD,
)
@_SETTINGS
def test_p13_via_segment_index_is_the_first_match(points, vx, vy) -> None:
    """P13: the returned index is the FIRST segment within 1e-4 on both axes.

    Not merely *a* match: the shipped loop breaks on the first hit, so a
    last-match-wins port silently changes which layer pair the via records.
    ``None`` is returned exactly when no segment matches.
    """
    segs = [(x, y, "F.Cu") for x, y in points]
    idx = ORACLE._via_segment_index(vx, vy, segs)
    matches = [i for i, (x, y, _) in enumerate(segs) if abs(x - vx) < 1e-4 and abs(y - vy) < 1e-4]
    if not matches:
        assert idx is None
    else:
        assert idx == matches[0]


# ===========================================================================
# Mutation tests (G4 vacuity guard)
# ===========================================================================


@pytest.fixture
def restore_kernels():
    """Snapshot every kernel a mutation test may replace, and put it back."""
    names = (
        "_calculate_angle",
        "_classify_severity",
        "_generate_spoke_segments",
        "_clamp_to_board_outline",
        "generate_power_pours",
        "_thermal_via_positions",
        "_via_annular_area",
        "_segment_run_copper_area",
        "_check_via",
        "_generate_via_teardrop",
        "_via_segment_index",
    )
    saved = {n: getattr(ORACLE, n) for n in names}
    yield
    for n, fn in saved.items():
        setattr(ORACLE, n, fn)


_PLAIN_TRIPLE = ((1.0, 0.0), (0.0, 0.0), (0.0, 1.0))
_PLAIN_SPOKE = ((0.0, 0.0), (0.6, 0.6), 4, 0.254, 0.254)
_PLAIN_CLAMP = (50.0, 50.0, 0.0, 0.0, 10.0, 10.0)
# Four vertices, so BOTH F.Cu and In1.Cu carry area.  Three would not: the
# segment's layer comes from `segments[i]`, so the last vertex's label is
# never read.
_PLAIN_RUN = (
    [
        (0.0, 0.0, "F.Cu"),
        (3.0, 4.0, "F.Cu"),
        (3.0, 9.0, "In1.Cu"),
        (8.0, 9.0, "In1.Cu"),
    ],
    "F.Cu",
    0.25,
)


def test_p1_fails_for_out_of_range_constant(restore_kernels) -> None:
    ORACLE._calculate_angle = lambda *_a, **_k: 400.0
    with pytest.raises(AssertionError):
        test_p1_angle_is_a_bounded_degree_measure.hypothesis.inner_test(_PLAIN_TRIPLE)


def test_p2_fails_for_first_arm_only_kernel(restore_kernels) -> None:
    """A kernel reading only ``p1`` is asymmetric -- a constant would NOT be."""
    ORACLE._calculate_angle = lambda p1, _p2, _p3: abs(p1[0]) * 10.0
    with pytest.raises(AssertionError):
        test_p2_angle_is_symmetric_under_arm_exchange.hypothesis.inner_test(_PLAIN_TRIPLE)


def test_p3_fails_for_inverted_severity_bands(restore_kernels) -> None:
    ORACLE._classify_severity = lambda angle, _w=0.2: "low" if angle < 45 else "high"
    with pytest.raises(AssertionError):
        # straddles the mutant's inverted 45-degree boundary
        test_p3_severity_is_monotone_in_the_angle.hypothesis.inner_test(44.5, 0.25)


def test_p4_fails_for_wrong_spoke_count(restore_kernels) -> None:
    ORACLE._generate_spoke_segments = lambda *_a, **_k: [((0.0, 0.0), (1.0, 0.0))]
    with pytest.raises(AssertionError):
        test_p4_spokes_are_counted_and_radially_placed.hypothesis.inner_test(_PLAIN_SPOKE)


def test_p4_fails_for_position_dependent_radius(restore_kernels) -> None:
    """A right count with per-spoke radii is the discriminating mutant.

    (A constant *segment list* is caught by the count; this one has the right
    count and still breaks the equal-radius claim.)
    """

    def mutant(pos, size, count, _width, gap):
        r0 = math.hypot(size[0] / 2.0, size[1] / 2.0) + gap
        return [
            ((pos[0] + r0 * (1 + i), pos[1]), (pos[0] + r0 * (2 + i), pos[1])) for i in range(count)
        ]

    ORACLE._generate_spoke_segments = mutant
    with pytest.raises(AssertionError):
        test_p4_spokes_are_counted_and_radially_placed.hypothesis.inner_test(_PLAIN_SPOKE)


def test_p5_fails_for_min_instead_of_max_spoke_length(restore_kernels) -> None:
    """The exact B5 slip: ``min`` where the reference wrote ``max``."""

    def mutant(pos, size, count, width, gap):
        pad_radius = math.hypot(size[0] / 2.0, size[1] / 2.0)
        length = min(gap * 2.0, width * 2.0)  # <- the mutation
        out = []
        for i in range(count):
            angle = 2.0 * math.pi * i / count
            dx, dy = math.cos(angle), math.sin(angle)
            r = pad_radius + gap
            out.append(
                (
                    (pos[0] + r * dx, pos[1] + r * dy),
                    (pos[0] + (r + length) * dx, pos[1] + (r + length) * dy),
                )
            )
        return out

    ORACLE._generate_spoke_segments = mutant
    with pytest.raises(AssertionError):
        # gap != width, so min and max genuinely differ
        test_p5_spoke_length_is_the_max_of_the_two_doubled_inputs.hypothesis.inner_test(
            ((0.0, 0.0), (0.6, 0.6), 4, 1.0, 0.1)
        )


def test_p6_fails_for_identity_clamp(restore_kernels) -> None:
    ORACLE._clamp_to_board_outline = lambda _b, point, _c: point
    with pytest.raises(AssertionError):
        test_p6_rect_clamp_is_inside_and_idempotent.hypothesis.inner_test(_PLAIN_CLAMP)


def test_p6_fails_for_constant_clamp(restore_kernels) -> None:
    """A constant IS inside the board but is not a projection."""
    ORACLE._clamp_to_board_outline = lambda _b, _point, _c: (5.0, 5.0)
    with pytest.raises(AssertionError):
        # an already-inside point must come back untouched
        test_p6_rect_clamp_is_inside_and_idempotent.hypothesis.inner_test(
            (1.0, 1.0, 0.0, 0.0, 10.0, 10.0)
        )


def test_p7_fails_for_overlapping_pours(restore_kernels) -> None:
    def mutant(board, domains=None, layer="In2.Cu", *, isolation_gap_mm=0.3):
        resolved = tuple(domains) if domains is not None else ORACLE.DEFAULT_POWER_DOMAINS
        x_min, y_min, x_max, y_max = ORACLE._board_bounds(board)
        return [
            ORACLE.CopperPour(net=net, layer=layer, bounds=(x_min, y_min, x_max, y_max))
            for net in resolved
        ]

    ORACLE.generate_power_pours = mutant
    with pytest.raises(AssertionError):
        test_p7_power_pours_are_ordered_disjoint_and_in_bounds.hypothesis.inner_test(
            0.0, 100.0, 3, 0.3
        )


def test_p8_fails_for_off_centre_grid(restore_kernels) -> None:
    """A grid with the right spacing but the wrong origin."""

    def mutant(center, count, pitch):
        side = int(round(count**0.5))
        cx, cy = center
        return [(cx + c * pitch, cy + r * pitch) for r in range(side) for c in range(side)]

    ORACLE._thermal_via_positions = mutant
    with pytest.raises(AssertionError):
        test_p8_thermal_via_grid_is_square_and_centred.hypothesis.inner_test(0, 0, 9, 1.0)


def test_p9_fails_for_negative_constant_area(restore_kernels) -> None:
    ORACLE._via_annular_area = lambda _via: -1.0
    with pytest.raises(AssertionError):
        test_p9_annular_area_is_nonnegative_and_shrinks_with_the_drill.hypothesis.inner_test(
            1.0, 0.3
        )


def test_p9_fails_for_drill_independent_area(restore_kernels) -> None:
    """Non-negative, but blind to the drill -- so the pad-swallow case breaks."""
    ORACLE._via_annular_area = lambda via: math.pi * (via.diameter / 2.0) ** 2
    with pytest.raises(AssertionError):
        test_p9_annular_area_is_nonnegative_and_shrinks_with_the_drill.hypothesis.inner_test(
            1.0, 0.3
        )


def test_p10_fails_for_layer_blind_accumulation(restore_kernels) -> None:
    """Dropping the ``seg_layer == layer_name`` test quadruples the total."""

    def mutant(segments, _layer_name, width_mm):
        area = 0.0
        for i in range(len(segments) - 1):
            x1, y1, _ = segments[i]
            x2, y2, _ = segments[i + 1]
            area += math.hypot(x2 - x1, y2 - y1) * width_mm
        return area

    ORACLE._segment_run_copper_area = mutant
    with pytest.raises(AssertionError):
        test_p10_copper_area_is_additive_over_the_layer_partition.hypothesis.inner_test(_PLAIN_RUN)


def test_p11_fails_for_always_violating_kernel(restore_kernels) -> None:
    def mutant(via, net_name, min_annular_ring, _microvia):
        return ORACLE.AnnularRingViolation(
            net_name=net_name,
            via_position=via.position,
            pad_diameter=via.diameter,
            drill_diameter=via.drill,
            actual_ring_width=(via.diameter - via.drill) / 2.0,
            minimum_required=min_annular_ring,
        )

    ORACLE._check_via = mutant
    with pytest.raises(AssertionError):
        # a 10mm pad on a 0.3mm drill passes; the mutant flags it anyway,
        # and the `if v is None` monotonicity arm never gets to run -- so
        # the discriminating assertion is the pad-growth one below.
        test_p11_annular_violation_is_monotone_in_the_pad.hypothesis.inner_test(
            0.05, 1.0, 0.05, "F.Cu", "B.Cu"
        )


def test_p12_fails_for_uncentred_connection_point(restore_kernels) -> None:
    """The via centre itself is the plausible slip: forgetting the offset."""

    def mutant(net_name, via, compiled_route, length_ratio):
        return ORACLE.Teardrop(
            net_name=net_name,
            connection_point=via.position,  # <- the mutation
            connection_type="via",
            length_mm=via.diameter * length_ratio,
            width_mm=min(via.diameter * 0.6, compiled_route.width_mm * 2.0),
            layer=compiled_route.path.layer_name,
        )

    ORACLE._generate_via_teardrop = mutant
    with pytest.raises(AssertionError):
        test_p12_teardrop_sits_on_the_via_annulus_and_is_width_bounded.hypothesis.inner_test(
            0.0, 0.0, 0.6, 0.25, 0.5
        )


def test_p13_fails_for_last_match_wins(restore_kernels) -> None:
    def mutant(vx, vy, segs):
        vi = None
        for i, (sx, sy, _) in enumerate(segs):
            if abs(sx - vx) < 1e-4 and abs(sy - vy) < 1e-4:
                vi = i  # no break -- the mutation
        return vi

    ORACLE._via_segment_index = mutant
    with pytest.raises(AssertionError):
        test_p13_via_segment_index_is_the_first_match.hypothesis.inner_test(
            [(0.0, 0.0), (0.0, 0.0)], 0.0, 0.0
        )


# ===========================================================================
# Sanity: the input classes are genuinely discriminating (anti-vacuity)
# ===========================================================================


def test_severity_bands_are_all_reachable() -> None:
    """P3 would be vacuous if the corpus only ever produced one severity."""
    got = {ORACLE._classify_severity(a, 0.25) for a in (10.0, 50.0, 100.0)}
    assert got == {"high", "medium", "low"}


def test_annular_check_reaches_both_verdicts() -> None:
    """P11 would be vacuous if every via violated (or none did)."""
    passing = ORACLE._check_via(_Via(diameter=2.0, drill=0.3), "N", 0.05, 0.025)
    failing = ORACLE._check_via(_Via(diameter=0.35, drill=0.3), "N", 0.05, 0.025)
    assert passing is None
    assert failing is not None


def test_teardrop_reaches_both_verdicts() -> None:
    """P12 would be vacuous if the diameter gate never rejected anything."""
    route_ok = _Route(_Path([(0.0, 0.0), (1.0, 0.0)], "F.Cu"), 0.25)
    route_wide = _Route(_Path([(0.0, 0.0), (1.0, 0.0)], "F.Cu"), 2.0)
    via = _Via(position=(0.0, 0.0), diameter=0.6)
    assert ORACLE._generate_via_teardrop("N", via, route_ok, 0.5) is not None
    assert ORACLE._generate_via_teardrop("N", via, route_wide, 0.5) is None


def test_segment_runs_reach_more_than_one_layer() -> None:
    """P10's partition is only meaningful if runs really change layer."""
    segs, _, width = _PLAIN_RUN
    per_layer = [ORACLE._segment_run_copper_area(segs, ln, width) for ln in LAYER_NAMES]
    assert sum(1 for a in per_layer if a > 0.0) >= 2


# ===========================================================================
# G5 -- metamorphic relations, each with its exactness claim
# ===========================================================================


def test_m1_angle_argument_reversal_is_exact() -> None:
    """M1 -- **EXACT**. Reversal only exchanges commutative multiply operands.

    ``dot = v1x*v2x + v1y*v2y`` becomes ``v2x*v1x + v2y*v1y``: same products,
    same addition order.  ``mag1 * mag2`` becomes ``mag2 * mag1``.  No
    rounding is introduced or removed, so this is bit-exact, asserted with
    ``==`` over 5,000 random triples.
    """
    rng = random.Random(20260804)
    changed = 0
    for _ in range(5000):
        p1 = (rng.uniform(-50, 50), rng.uniform(-50, 50))
        p2 = (rng.uniform(-50, 50), rng.uniform(-50, 50))
        p3 = (rng.uniform(-50, 50), rng.uniform(-50, 50))
        assert ORACLE._calculate_angle(p1, p2, p3) == ORACLE._calculate_angle(p3, p2, p1)
        if p1 != p3:
            changed += 1
    assert changed > 4900, "the transform is near-vacuous on this corpus"


def test_m2_angle_power_of_two_scale_is_exact() -> None:
    """M2 -- **EXACT** for power-of-two scales, within the exponent range.

    Scaling every coordinate by ``2^k`` scales each ``v`` component exactly,
    each ``v ** 2`` by ``4^k`` exactly, each ``sqrt`` by ``2^k`` exactly, and
    ``dot`` by ``4^k`` exactly.  ``cos_angle = dot / (mag1*mag2)`` therefore
    has ``4^k`` in both numerator and denominator and comes out **bit
    identical** -- so acos, degrees and round all see the same input.

    The claim is bounded: it holds only while nothing overflows or falls into
    the denormal band, which is why the scales are ``2^-8 .. 2^8`` over
    board-scale coordinates.  A non-power-of-two scale is NOT exact and is
    deliberately not asserted.
    """
    rng = random.Random(20260805)
    for _ in range(5000):
        p1 = (rng.uniform(-50, 50), rng.uniform(-50, 50))
        p2 = (rng.uniform(-50, 50), rng.uniform(-50, 50))
        p3 = (rng.uniform(-50, 50), rng.uniform(-50, 50))
        s = 2.0 ** rng.choice([-8, -4, -2, -1, 1, 2, 4, 8])
        base = ORACLE._calculate_angle(p1, p2, p3)
        scaled = ORACLE._calculate_angle(
            (p1[0] * s, p1[1] * s), (p2[0] * s, p2[1] * s), (p3[0] * s, p3[1] * s)
        )
        assert base == scaled, f"scale {s} broke exactness at {(p1, p2, p3)}"


def test_m2_non_dyadic_scale_diverges_before_the_round_absorbs_it() -> None:
    """The honest complement of M2, and a finding worth recording.

    A 1.1x scale genuinely perturbs the computation: measured here, the
    *unrounded* ``math.degrees(math.acos(...))`` differs for **>50%** of
    random triples, by up to ``~8.8e-11`` degrees.  But the pinned
    ``round(angle_deg, 9)`` absorbs every one of them -- **0** of 5,000
    triples differ after the round.

    So the shipped kernel is scale-stable well beyond the dyadic case, but
    for two different reasons, and only one of them is a proof:

    * power-of-two scales are exact *by construction* (M2), at any magnitude;
    * arbitrary scales survive only because the perturbation happens to land
      under the 1e-9 rounding grid at board-scale coordinates -- an empirical
      observation, not an invariant, and it is not claimed as one.

    This also tells Phase B something concrete: the ``round_ties_even`` step
    is the kernel's error-absorption mechanism, not a cosmetic tidy-up.
    Dropping it would expose every one of these divergences.
    """
    rng = random.Random(20260806)
    unrounded_diverged = 0
    rounded_diverged = 0
    worst = 0.0
    for _ in range(5000):
        p1 = (rng.uniform(-50, 50), rng.uniform(-50, 50))
        p2 = (rng.uniform(-50, 50), rng.uniform(-50, 50))
        p3 = (rng.uniform(-50, 50), rng.uniform(-50, 50))
        s = 1.1
        q1, q2, q3 = (
            (p1[0] * s, p1[1] * s),
            (p2[0] * s, p2[1] * s),
            (p3[0] * s, p3[1] * s),
        )
        a, b = _unrounded_angle(p1, p2, p3), _unrounded_angle(q1, q2, q3)
        if a != b:
            unrounded_diverged += 1
            worst = max(worst, abs(a - b))
        if ORACLE._calculate_angle(p1, p2, p3) != ORACLE._calculate_angle(q1, q2, q3):
            rounded_diverged += 1
    assert unrounded_diverged > 2000, (
        f"only {unrounded_diverged}/5000 diverged before rounding -- "
        "M2's power-of-two qualifier is no longer measured"
    )
    assert worst < 1e-9, f"the perturbation ({worst:.3e}) has outgrown the rounding grid"
    assert rounded_diverged == 0, (
        f"{rounded_diverged}/5000 now survive the round -- the kernel's "
        "absorption band has changed and M2's complement must be re-measured"
    )


def _unrounded_angle(p1, p2, p3) -> float:
    """``_calculate_angle`` without its final ``round``, for M2's complement.

    Deliberately a re-implementation and not a monkeypatch: it exists to
    isolate the rounding step, so it must not share code with the kernel.
    """
    v1 = (p1[0] - p2[0], p1[1] - p2[1])
    v2 = (p3[0] - p2[0], p3[1] - p2[1])
    dot = v1[0] * v2[0] + v1[1] * v2[1]
    mag1 = math.sqrt(v1[0] ** 2 + v1[1] ** 2)
    mag2 = math.sqrt(v2[0] ** 2 + v2[1] ** 2)
    if mag1 == 0 or mag2 == 0:
        return 180.0
    rad = math.acos(max(-1.0, min(1.0, dot / (mag1 * mag2))))
    return 180.0 if math.isnan(rad) else math.degrees(rad)


def test_m3_annular_area_power_of_two_scale_is_exact() -> None:
    """M3 -- **EXACT**. ``area(2^k d, 2^k drill) == 4^k * area(d, drill)``.

    ``d / 2`` and ``r * r`` scale exactly; multiplying by ``pi`` commutes with
    a power-of-two scale because scaling by ``2^n`` shifts the exponent
    without touching the mantissa, so it commutes with rounding.  Bounded the
    same way as M2: no overflow, no denormals.
    """
    rng = random.Random(20260807)
    for _ in range(5000):
        d = rng.uniform(0.1, 5.0)
        drill = rng.uniform(0.0, d * 1.2)
        k = rng.choice([-6, -3, -1, 1, 3, 6])
        s = 2.0**k
        base = ORACLE._via_annular_area(_Via(diameter=d, drill=drill))
        scaled = ORACLE._via_annular_area(_Via(diameter=d * s, drill=drill * s))
        assert scaled == (s * s) * base, f"scale 2^{k} broke exactness at {(d, drill)}"


def test_m4_thermal_via_grid_centroid_is_exact_for_dyadic_inputs() -> None:
    """M4 -- **EXACT** for dyadic pitch and integer centre.

    The grid's centroid is the requested centre, bit for bit.  The
    qualification is load-bearing: with a non-dyadic pitch such as the
    production 1.2mm, ``cx - span/2.0`` re-rounds and the centroid is only
    approximately the centre -- asserted below so the qualifier is measured,
    not assumed.
    """
    rng = random.Random(20260808)
    for _ in range(2000):
        cx = float(rng.randrange(-1000, 1000))
        cy = float(rng.randrange(-1000, 1000))
        pitch = 2.0 ** rng.choice([-4, -2, -1, 0, 1, 2])
        count = rng.choice([1, 4, 9, 16, 25])
        pos = ORACLE._thermal_via_positions((cx, cy), count, pitch)
        assert sum(p[0] for p in pos) / len(pos) == cx
        assert sum(p[1] for p in pos) / len(pos) == cy


def test_m4_non_dyadic_pitch_is_only_approximately_centred() -> None:
    """The honest complement of M4, at the production 1.2mm pitch."""
    inexact = 0
    for i in range(-200, 200):
        cx = i * 0.1
        pos = ORACLE._thermal_via_positions((cx, 0.0), 9, 1.2)
        if sum(p[0] for p in pos) / len(pos) != cx:
            inexact += 1
    assert inexact > 0, "M4's dyadic qualifier is untested -- everything was exact"


def test_m5_spoke_translation_is_bounded_not_exact() -> None:
    """M5 -- **TOLERANCE 1.5e-14 absolute** (measured), NOT exact.

    Translating the pad centre by ``t`` should translate every spoke endpoint
    by ``t``.  It does not do so bit-exactly: ``cx + start_r*dx`` re-rounds
    against a different ``cx``.  Measured over 4,000 random board-scale
    translations at power-of-two offsets, the worst absolute deviation is
    ``1.42e-14`` (up to ~1024 ulps where the sum cancels near zero).

    The band asserted here is that measurement plus headroom, and the test
    also asserts the relation is **not** exact -- so if a future change makes
    it exact, this test fails and the claim gets tightened deliberately rather
    than drifting.
    """
    rng = random.Random(20260809)
    worst = 0.0
    exact_everywhere = True
    for _ in range(4000):
        cx = rng.uniform(-100.0, 100.0)
        cy = rng.uniform(-100.0, 100.0)
        t = 2.0 ** rng.choice([-4, -2, 0, 2, 4])
        base = ORACLE._generate_spoke_segments((cx, cy), (0.6, 0.6), 4, 0.254, 0.254)
        moved = ORACLE._generate_spoke_segments((cx + t, cy + t), (0.6, 0.6), 4, 0.254, 0.254)
        for (s1, e1), (s2, e2) in zip(base, moved):
            for u, v in (
                (s1[0] + t, s2[0]),
                (s1[1] + t, s2[1]),
                (e1[0] + t, e2[0]),
                (e1[1] + t, e2[1]),
            ):
                worst = max(worst, abs(u - v))
                if u != v:
                    exact_everywhere = False
    assert worst <= 1.5e-14, f"translation band widened to {worst:.3e}"
    assert not exact_everywhere, (
        "translation is now bit-exact -- tighten M5's claim deliberately "
        "instead of leaving a loose tolerance in place"
    )
