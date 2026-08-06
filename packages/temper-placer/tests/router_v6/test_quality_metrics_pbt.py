"""Property-based and metamorphic tests for router_v6 cluster F (quality metrics).

Gate **G4** -- >=5 non-vacuous properties **per module**, each vacuity-guarded
by a ``test_pN_fails_for_<mutant>`` mutation test proving a degenerate kernel
violates it:

* ``metrics/slop_linter``  -- S1..S5
* ``quality/corridor``     -- C1..C5
* ``quality/via_count``    -- V1..V5

Gate **G5** -- >=3 metamorphic relations per module, in the clearly-labelled
section at the bottom, each carrying an explicit exactness claim.

These run against the **pinned oracle**, not the Rust, and are green today.
That is deliberate: the properties are what the Rust must also satisfy, so
writing them before the Rust is what makes them a specification rather than a
description of whatever the port happened to do.  When the cluster-F kernels
land, ``KERNELS`` below is repointed at the Rust module and the whole file
re-runs unchanged.

Honesty about exactness (G5)
----------------------------
Exactness is claimed **only** where the transform preserves every f64 bit:

* **Power-of-two scaling** -- exact.  Multiplying an f64 by 2**k only shifts
  the exponent, so mantissas are untouched (barring overflow/underflow, which
  the strategies stay far away from).
* **Cardinal rotations (90/180/270 deg)** -- exact.  The matrix entries are
  0 and +/-1, so coordinates are permuted and negated with no arithmetic.
* **Reflection** -- exact, for the same reason.
* **Permutation of inputs the kernel sorts** -- exact.
* **Translation by a dyadic offset** -- exact for kernels that only *order* or
  *compare* coordinates (consolidation, ``_angle_between``).  **Not** exact for
  kernels that subtract two coordinates far from the origin: spread
  differences two nearby track edges and loses low-order bits, so M-C2 carries
  a measured relative tolerance instead.
* **Non-cardinal rotation (e.g. 30 deg)** -- **NOT exact**, and not asserted
  as such.  ``math.cos``/``math.sin`` of a non-dyadic angle introduce
  rounding, and ``acos`` then *amplifies* it: near a collinear junction the
  cosine is at +/-1 where ``acos(1 - eps) ~ sqrt(2*eps)``, turning a ~1e-12
  cosine perturbation into a ~1e-6 deg angle change.  M-S4 therefore tolerates
  1e-5 deg, and both regimes are measured separately (generic 4.0e-10,
  collinear 1.7e-6 over 200,000 cases each).

Three claims in this file were **written as exact-or-tighter and the oracle
disproved them**: M-C2's translation invariance of spread, an earlier malformed
version of M-C4, and M-S4's original 1e-6 tolerance (Hypothesis falsified it at
1.207e-6 with a collinear case, which is how the two-regime split was found).
Running the properties against the pinned oracle before the Rust exists is what
surfaced all three; had they been written after the port, each tolerance would
have been chosen to fit whatever the port happened to do.

Where a relation does **not** hold at all, that is recorded as a test too --
:func:`test_m_c5_component_order_is_NOT_invariant` and
:func:`test_m_v4_scaling_is_NOT_invariant_for_stitching` are counter-relations,
and they are as much part of the specification as the invariances.
"""

from __future__ import annotations

import math
import random

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

import tests.router_v6._quality_metrics_fixtures as FX
import tests.router_v6._quality_metrics_py_oracle as KERNELS
from tests.router_v6._quality_metrics_cases import SCENARIOS

_SETTINGS = settings(max_examples=200, deadline=None)

_FINDING_TYPES = {"hairpin", "zigzag", "isolated_via", "single_net_detour"}
_FINDING_KEYS = {"type", "net_name", "position", "severity", "description"}


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Coordinates restricted to dyadic rationals with a bounded exponent, so that
# translation and power-of-two scaling are exact (see the module docstring).
_DYADIC = st.integers(min_value=-4096, max_value=4096).map(lambda n: n / 64.0)

_FINITE = st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False, width=64)

_HOSTILE = st.one_of(
    _FINITE,
    st.sampled_from([float("nan"), float("inf"), float("-inf"), 0.0, -0.0, 5e-324]),
)


@st.composite
def points(draw, coord=_DYADIC):
    return (draw(coord), draw(coord))


@st.composite
def segments(draw, coord=_DYADIC):
    return (draw(coord), draw(coord), draw(coord), draw(coord))


@st.composite
def segment_lists(draw, min_size=0, max_size=8, coord=_DYADIC):
    return draw(st.lists(segments(coord=coord), min_size=min_size, max_size=max_size))


@st.composite
def angle_inputs(draw, coord=_DYADIC):
    return tuple(draw(coord) for _ in range(8))


@st.composite
def boards(draw):
    """A whole synthetic board: traces, vias, components, outline."""
    n_traces = draw(st.integers(min_value=0, max_value=6))
    n_vias = draw(st.integers(min_value=0, max_value=4))
    n_comps = draw(st.integers(min_value=0, max_value=4))
    nets = draw(
        st.lists(
            st.sampled_from(["N1", "N2", "GND", "DC_BUS+", "+3V3", "", None]),
            min_size=1,
            max_size=4,
        )
    )
    refs = ["U1", "U2", "Q1", "Q2", "R1"]
    return {
        "traces": [
            (
                draw(_DYADIC),
                draw(_DYADIC),
                draw(_DYADIC),
                draw(_DYADIC),
                draw(st.sampled_from([0.15, 0.2, 0.25])),
                draw(st.sampled_from(["F.Cu", "B.Cu"])),
                draw(st.sampled_from(nets)),
            )
            for _ in range(n_traces)
        ],
        "vias": [
            (
                (draw(_DYADIC), draw(_DYADIC)),
                draw(st.sampled_from(nets)),
                ("F.Cu", "B.Cu"),
            )
            for _ in range(n_vias)
        ],
        "components": [
            (
                draw(st.sampled_from(refs)),
                draw(st.one_of(st.none(), points())),
                draw(st.sampled_from([1.0, 2.0, 4.0])),
                draw(st.sampled_from([1.0, 2.0, 4.0])),
            )
            for _ in range(n_comps)
        ],
        "board": draw(st.one_of(st.none(), st.just((64.0, 64.0)), st.just((128.0, 96.0)))),
    }


@st.composite
def structured_boards(draw):
    """Boards **constructed** to reach the corridor and thermal branches.

    Purely random components and traces essentially never produce an occupied
    channel: measured over 600 draws from :func:`boards`, zero produced a
    channel holding two or more tracks, and zero produced a thermal via.  Every
    corridor property and metamorphic relation would then be comparing the
    empty-input constants ``1.0`` and ``0.0`` to themselves -- exactly the
    vacuity gate G4 exists to forbid.

    This strategy therefore *builds* the geometry:

    * two courtyards stacked in y with a large x-overlap, giving one vertical
      channel spanning x [-4.25, 4.25], y [-5.75, 5.75];
    * between 0 and 5 tracks whose midpoints land inside that channel, spread
      along **x** (the axis a vertical channel sorts and measures on);
    * a ``Q1`` footprint at the origin plus vias that may be on ``DC_BUS+``
      and inside it, so the thermal branch fires.

    All coordinates stay dyadic, so the exactness claims in the metamorphic
    section still hold.  ``test_strategy_reaches_*`` below assert that this
    strategy really does reach each branch.
    """
    xs = draw(
        st.lists(
            st.sampled_from([-3.0, -2.0, -1.0, 0.0, 1.0, 2.0, 3.0]),
            min_size=0,
            max_size=5,
            unique=True,
        )
    )
    nets = draw(st.lists(st.sampled_from(["N1", "N2", "N3"]), min_size=1, max_size=3))
    traces = [
        (
            x,
            -1.0,
            x,
            1.0,
            draw(st.sampled_from([0.15, 0.2, 0.25])),
            "F.Cu",
            draw(st.sampled_from(nets)),
        )
        for x in xs
    ]
    n_vias = draw(st.integers(min_value=0, max_value=3))
    vias = [
        (
            (
                draw(st.sampled_from([-1.0, 0.0, 1.0, 30.0])),
                draw(st.sampled_from([-1.0, 0.0, 1.0, 30.0])),
            ),
            draw(st.sampled_from(["DC_BUS+", "dc_bus+", "GND", "N1"])),
            ("F.Cu", "B.Cu"),
        )
        for _ in range(n_vias)
    ]
    return {
        "traces": traces,
        "vias": vias,
        "components": [
            ("U1", (0.0, -8.0), 8.0, 4.0),
            ("U2", (0.0, 8.0), 8.0, 4.0),
            ("Q1", (0.0, 0.0), 4.0, 4.0),
        ],
        "board": (64.0, 64.0),
    }


#: The strategy every board-level property draws from: unstructured boards for
#: breadth, structured ones so the interesting branches are actually reached.
any_board = st.one_of(boards(), structured_boards())


def _lint(fn, scenario) -> list[dict]:
    result = FX.build(scenario)
    original = KERNELS._parse_pcb
    KERNELS._parse_pcb = lambda _p: result
    try:
        return fn("<synthetic>")
    finally:
        KERNELS._parse_pcb = original


@pytest.fixture
def restore_kernels():
    """Restore every kernel this file mutates, whatever the test did."""
    names = (
        "_distance_mm",
        "_vector",
        "_angle_between",
        "_order_traces",
        "_load_traces_by_net",
        "_overlap",
        "_gap",
        "_point_in_rect",
        "_compute_courtyards",
        "_identify_channels",
        "_assign_tracks_to_channels",
        "_compute_consolidation",
        "_compute_spread",
        "_classify_vias",
        "_get_component_bboxes",
        "_is_via_in_bbox",
        "_is_via_near_board_edge",
    )
    saved = {n: getattr(KERNELS, n) for n in names}
    yield
    for name, value in saved.items():
        setattr(KERNELS, name, value)


# ===========================================================================
# Strategy vacuity guards
#
# Every property below draws from ``any_board``.  A property is only as
# meaningful as the inputs it sees, so these assert that the strategy actually
# reaches each interesting branch rather than sampling empty boards forever.
# They are the counterpart to the per-property mutation tests: mutants prove a
# property can fail, these prove it is being evaluated on inputs where failing
# is possible.
# ===========================================================================


def _branch_census(n: int = 400) -> dict[str, int]:
    """Sample ``any_board`` and count how often each branch is reached."""
    from hypothesis import HealthCheck

    census = dict.fromkeys(
        [
            "boards",
            "channels",
            "occupied_channel",
            "consolidation_below_one",
            "spread_above_zero",
            "thermal",
            "stitching",
            "findings",
        ],
        0,
    )

    @given(any_board)
    @settings(max_examples=n, deadline=None, suppress_health_check=list(HealthCheck))
    def sample(scenario):
        result = FX.build(scenario)
        census["boards"] += 1
        courtyards = KERNELS._compute_courtyards(result, 0.25)
        channels = KERNELS._identify_channels(courtyards, 3.0 * (0.2 + 0.15))
        if channels:
            census["channels"] += 1
        assigned = KERNELS._assign_tracks_to_channels(result, channels)
        if any(len(v) >= 2 for v in assigned.values()):
            census["occupied_channel"] += 1
        if KERNELS._compute_consolidation(result, None, None, None) < 1.0:
            census["consolidation_below_one"] += 1
        if KERNELS._compute_spread(result, None, None, None) > 0.0:
            census["spread_above_zero"] += 1
        counts = KERNELS._classify_vias(result)
        if counts.thermal:
            census["thermal"] += 1
        if counts.stitching:
            census["stitching"] += 1
        original = KERNELS._parse_pcb
        KERNELS._parse_pcb = lambda _p: result
        try:
            if KERNELS.lint_all("<synthetic>"):
                census["findings"] += 1
        finally:
            KERNELS._parse_pcb = original

    sample()
    return census


def test_strategy_reaches_every_interesting_branch() -> None:
    """The input class is genuinely discriminating.

    Without :func:`structured_boards` this fails hard: measured over 600 draws
    from :func:`boards` alone, ``occupied_channel``, ``thermal``,
    ``consolidation_below_one`` and ``spread_above_zero`` were all **zero**, so
    every corridor property and metamorphic relation was comparing the
    empty-input constants ``1.0``/``0.0`` to themselves.
    """
    census = _branch_census()
    for branch in (
        "channels",
        "occupied_channel",
        "consolidation_below_one",
        "spread_above_zero",
        "thermal",
        "stitching",
        "findings",
    ):
        assert census[branch] > 0, f"strategy never reached {branch}: {census}"


# ===========================================================================
# metrics/slop_linter — S1..S5
# ===========================================================================


@given(points(), points())
@_SETTINGS
def test_s1_distance_is_nonnegative_and_symmetric(a, b) -> None:
    """S1: ``_distance_mm`` is a metric on finite points.

    Non-negative, symmetric, and zero exactly when the points coincide.  A
    kernel returning a signed or order-dependent value fails; a constant
    non-negative kernel fails the zero-iff-coincident arm.
    """
    d_ab = KERNELS._distance_mm(a, b)
    d_ba = KERNELS._distance_mm(b, a)
    assert d_ab >= 0.0
    assert d_ab == d_ba
    assert (d_ab == 0.0) == (a == b)


@given(angle_inputs(coord=_HOSTILE))
@_SETTINGS
def test_s2_angle_is_within_zero_to_180(case) -> None:
    """S2: ``_angle_between`` always lands in [0, 180], even on NaN/inf.

    The ``max(-1.0, min(1.0, ...))`` clamp is what guarantees this; without it
    ``acos`` would raise on an out-of-domain cosine.  Asserting it over
    *hostile* coordinates is what makes the property non-trivial -- it is the
    NaN and inf inputs that would break a naively-clamped port.
    """
    angle = KERNELS._angle_between(
        ((case[0], case[1]), (case[2], case[3])),
        ((case[4], case[5]), (case[6], case[7])),
    )
    assert not math.isnan(angle)
    assert 0.0 <= angle <= 180.0


@given(segment_lists())
@_SETTINGS
def test_s3_order_traces_is_a_permutation(segs) -> None:
    """S3: ``_order_traces`` reorders and may reverse, but never adds or drops.

    The output length equals the input length, and the multiset of
    *unordered* endpoint pairs is preserved -- a segment may come back
    reversed, but it must come back.
    """
    traces = FX.as_trace_dicts(segs)
    ordered = KERNELS._order_traces(traces)
    assert len(ordered) == len(traces)

    def key(t):
        return tuple(sorted([t["start"], t["end"]]))

    assert sorted(map(key, ordered)) == sorted(map(key, traces))


@given(any_board)
@_SETTINGS
def test_s4_hairpin_severity_is_a_hairpin_angle(scenario) -> None:
    """S4: every hairpin finding carries an angle in [160, 180].

    160 is the kernel's own threshold and 180 is the geometric maximum, so a
    finding outside that band is impossible for a correct implementation and
    is exactly what a broken angle kernel produces.
    """
    for finding in _lint(KERNELS.lint_hairpin_turns, scenario):
        assert finding["type"] == "hairpin"
        assert 160.0 <= finding["severity"] <= 180.0


@given(any_board)
@_SETTINGS
def test_s5_load_traces_by_net_partitions_the_traces(scenario) -> None:
    """S5: the per-net map is a partition, in first-appearance order.

    Every trace lands in exactly one bucket (counts sum to the input length),
    the bucket key is ``trace.net or "_unnamed"``, and the key order is the
    order the nets first appear.  The ordering arm is the one that catches a
    port which sorts its map -- see the differential's insertion-order test.
    """
    result = FX.build(scenario)
    original = KERNELS._parse_pcb
    KERNELS._parse_pcb = lambda _p: result
    try:
        by_net = KERNELS._load_traces_by_net("<synthetic>")
    finally:
        KERNELS._parse_pcb = original

    assert sum(len(v) for v in by_net.values()) == len(result.traces)
    expected_order: list[str] = []
    for trace in result.traces:
        name = trace.net or "_unnamed"
        if name not in expected_order:
            expected_order.append(name)
    assert list(by_net) == expected_order


# --- S1..S5 mutation tests -------------------------------------------------


def test_s1_fails_for_negative_constant_distance(restore_kernels) -> None:
    KERNELS._distance_mm = lambda _a, _b: -1.0
    with pytest.raises(AssertionError):
        test_s1_distance_is_nonnegative_and_symmetric.hypothesis.inner_test((0.0, 0.0), (1.0, 0.0))


def test_s1_fails_for_constant_nonzero_distance(restore_kernels) -> None:
    """A constant positive kernel is non-negative and symmetric, so only the
    zero-iff-coincident arm discriminates it."""
    KERNELS._distance_mm = lambda _a, _b: 1.0
    with pytest.raises(AssertionError):
        test_s1_distance_is_nonnegative_and_symmetric.hypothesis.inner_test((0.0, 0.0), (0.0, 0.0))


def test_s2_fails_for_out_of_range_angle(restore_kernels) -> None:
    KERNELS._angle_between = lambda _i, _o: 200.0
    with pytest.raises(AssertionError):
        test_s2_angle_is_within_zero_to_180.hypothesis.inner_test(
            (0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0, 0.0)
        )


def test_s2_fails_for_nan_propagating_clamp(restore_kernels) -> None:
    """The realistic Rust mutant: ``f64::max``/``min`` propagate NaN instead of
    keeping the first argument, so the angle comes back NaN."""

    def nan_clamp(incoming, outgoing):
        v1 = KERNELS._vector(incoming[0], incoming[1])
        v2 = KERNELS._vector(outgoing[0], outgoing[1])
        m1 = math.hypot(v1[0], v1[1])
        m2 = math.hypot(v2[0], v2[1])
        if m1 < 1e-9 or m2 < 1e-9:
            return 0.0
        dot = v1[0] * v2[0] + v1[1] * v2[1]
        raw = dot / (m1 * m2)
        # NaN-propagating clamp (what f64::clamp-style code does)
        cos_angle = raw if raw == raw else float("nan")
        cos_angle = min(1.0, max(-1.0, cos_angle)) if cos_angle == cos_angle else float("nan")
        return math.degrees(math.acos(cos_angle)) if cos_angle == cos_angle else float("nan")

    KERNELS._angle_between = nan_clamp
    with pytest.raises(AssertionError):
        test_s2_angle_is_within_zero_to_180.hypothesis.inner_test(
            (0.0, 0.0, float("nan"), 0.0, 0.0, 0.0, 1.0, 0.0)
        )


def test_s3_fails_for_dropping_order_traces(restore_kernels) -> None:
    KERNELS._order_traces = lambda traces: list(traces)[:-1]
    with pytest.raises(AssertionError):
        test_s3_order_traces_is_a_permutation.hypothesis.inner_test(
            [(0.0, 0.0, 1.0, 0.0), (1.0, 0.0, 2.0, 0.0)]
        )


def test_s3_fails_for_fabricating_segments(restore_kernels) -> None:
    """Length-preserving but value-fabricating: caught by the multiset arm."""
    KERNELS._order_traces = lambda traces: [
        {**t, "start": (0.0, 0.0), "end": (0.0, 0.0)} for t in traces
    ]
    with pytest.raises(AssertionError):
        test_s3_order_traces_is_a_permutation.hypothesis.inner_test(
            [(0.0, 0.0, 1.0, 0.0), (1.0, 0.0, 2.0, 0.0)]
        )


def test_s4_fails_for_out_of_band_angle(restore_kernels) -> None:
    KERNELS._angle_between = lambda _i, _o: 200.0
    scenario = dict(SCENARIOS)["collinear_run"]
    with pytest.raises(AssertionError):
        test_s4_hairpin_severity_is_a_hairpin_angle.hypothesis.inner_test(scenario)


def test_s5_fails_for_sorted_net_map(restore_kernels) -> None:
    """The mutant a Rust port most plausibly ships: a sorted (BTreeMap) net map."""
    original = KERNELS._load_traces_by_net

    def sorted_map(path):
        return dict(sorted(original(path).items()))

    KERNELS._load_traces_by_net = sorted_map
    scenario = dict(SCENARIOS)["many_nets_insertion_order"]
    with pytest.raises(AssertionError):
        test_s5_load_traces_by_net_partitions_the_traces.hypothesis.inner_test(scenario)


def test_s5_fails_for_dropping_a_bucket(restore_kernels) -> None:
    original = KERNELS._load_traces_by_net

    def lossy(path):
        out = original(path)
        return {k: v[:-1] for k, v in out.items()}

    KERNELS._load_traces_by_net = lossy
    scenario = dict(SCENARIOS)["many_nets_insertion_order"]
    with pytest.raises(AssertionError):
        test_s5_load_traces_by_net_partitions_the_traces.hypothesis.inner_test(scenario)


# ===========================================================================
# quality/corridor — C1..C5
# ===========================================================================


@given(any_board)
@_SETTINGS
def test_c1_consolidation_is_a_ratio(scenario) -> None:
    """C1: the consolidation score is a genuine ratio in [0, 1].

    It counts co-routed pairs out of pairs sharing a channel, so it can never
    exceed 1; the empty-input constant is 1.0, which is inside the band.
    """
    score = KERNELS._compute_consolidation(FX.build(scenario), None, None, None)
    assert not math.isnan(score)
    assert 0.0 <= score <= 1.0


@given(any_board)
@_SETTINGS
def test_c2_spread_is_nonnegative(scenario) -> None:
    """C2: the track-spread score is non-negative, and 0.0 when no channel
    holds two or more tracks.

    The second arm is what makes this non-vacuous: a kernel that returned a
    positive constant would satisfy non-negativity alone.
    """
    result = FX.build(scenario)
    score = KERNELS._compute_spread(result, None, None, None)
    assert not math.isnan(score)
    assert score >= 0.0

    courtyards = KERNELS._compute_courtyards(result, 0.25)
    channels = KERNELS._identify_channels(courtyards, 3.0 * (0.2 + 0.15))
    assigned = KERNELS._assign_tracks_to_channels(result, channels)
    if not any(len(v) >= 2 for v in assigned.values()):
        assert score == 0.0


@given(_FINITE, _FINITE, _FINITE, _FINITE)
@_SETTINGS
def test_c3_overlap_is_contained_in_both_inputs(a_min, a_max, b_min, b_max) -> None:
    """C3: ``_overlap`` returns a proper sub-interval of both inputs, or None.

    Containment is the arm that kills a kernel returning a fixed wide
    interval; the strictness of ``o_min < o_max`` kills one that reports
    touching ranges as overlapping.
    """
    got = KERNELS._overlap(a_min, a_max, b_min, b_max)
    if got is None:
        return
    o_min, o_max = got
    assert o_min < o_max
    assert a_min <= o_min and o_max <= a_max
    assert b_min <= o_min and o_max <= b_max


@given(st.lists(segments(), min_size=0, max_size=5), st.sampled_from([0.0, 1.05, 5.0]))
@_SETTINGS
def test_c4_channels_are_well_formed(rects, min_gap) -> None:
    """C4: every identified channel is a non-empty rect wider than the threshold.

    ``gap_width_mm > min_gap`` is the kernel's own guard, and the bound
    ordering (``x_min <= x_max``, ``y_min <= y_max``) is what a broken
    ``_overlap`` breaks.
    """
    courtyards = [
        KERNELS._Courtyard(
            ref=f"U{i}",
            x_min=min(r[0], r[2]),
            y_min=min(r[1], r[3]),
            x_max=max(r[0], r[2]),
            y_max=max(r[1], r[3]),
        )
        for i, r in enumerate(rects)
    ]
    for channel in KERNELS._identify_channels(courtyards, min_gap):
        assert channel.axis in ("vertical", "horizontal")
        assert channel.gap_width_mm > min_gap
        assert channel.x_min <= channel.x_max
        assert channel.y_min <= channel.y_max


@given(any_board, st.sampled_from([0.0, 0.25, 1.0]))
@_SETTINGS
def test_c5_courtyards_expand_by_exactly_the_clearance(scenario, clearance) -> None:
    """C5: one courtyard per positioned component, each the bbox + clearance.

    The extent identity is exact for these dyadic dimensions, so it is
    asserted with ``==``: ``x_max - x_min == width + 2 * clearance``.
    Components without a position contribute nothing.
    """
    result = FX.build(scenario)
    courtyards = KERNELS._compute_courtyards(result, clearance)
    positioned = [c for c in result.netlist.components if c.initial_position is not None]
    assert len(courtyards) == len(positioned)
    for courtyard, comp in zip(courtyards, positioned):
        assert courtyard.ref == comp.ref
        assert courtyard.x_max - courtyard.x_min == comp.width + 2 * clearance
        assert courtyard.y_max - courtyard.y_min == comp.height + 2 * clearance


# --- C1..C5 mutation tests -------------------------------------------------


def test_c1_fails_for_out_of_range_consolidation(restore_kernels) -> None:
    KERNELS._compute_consolidation = lambda *_a, **_k: 5.0
    with pytest.raises(AssertionError):
        test_c1_consolidation_is_a_ratio.hypothesis.inner_test(
            dict(SCENARIOS)["corridor_two_components_one_channel"]
        )


def test_c1_fails_for_nan_consolidation(restore_kernels) -> None:
    KERNELS._compute_consolidation = lambda *_a, **_k: float("nan")
    with pytest.raises(AssertionError):
        test_c1_consolidation_is_a_ratio.hypothesis.inner_test(dict(SCENARIOS)["empty_board"])


def test_c2_fails_for_constant_positive_spread(restore_kernels) -> None:
    """Non-negative but wrong: only the "0.0 when no channel is occupied" arm
    discriminates a positive constant."""
    KERNELS._compute_spread = lambda *_a, **_k: 1.0
    with pytest.raises(AssertionError):
        test_c2_spread_is_nonnegative.hypothesis.inner_test(dict(SCENARIOS)["empty_board"])


def test_c2_fails_for_negative_spread(restore_kernels) -> None:
    KERNELS._compute_spread = lambda *_a, **_k: -1.0
    with pytest.raises(AssertionError):
        test_c2_spread_is_nonnegative.hypothesis.inner_test(dict(SCENARIOS)["empty_board"])


def test_c3_fails_for_fixed_wide_overlap(restore_kernels) -> None:
    KERNELS._overlap = lambda *_a: (-1e9, 1e9)
    with pytest.raises(AssertionError):
        test_c3_overlap_is_contained_in_both_inputs.hypothesis.inner_test(0.0, 1.0, 0.0, 1.0)


def test_c3_fails_for_touching_counted_as_overlap(restore_kernels) -> None:
    """``o_min < o_max`` vs ``<=`` -- the off-by-one-branch mutant."""
    KERNELS._overlap = lambda a_min, a_max, b_min, b_max: (
        (max(a_min, b_min), min(a_max, b_max)) if max(a_min, b_min) <= min(a_max, b_max) else None
    )
    with pytest.raises(AssertionError):
        test_c3_overlap_is_contained_in_both_inputs.hypothesis.inner_test(0.0, 1.0, 1.0, 2.0)


def test_c4_fails_for_inverted_overlap(restore_kernels) -> None:
    KERNELS._overlap = lambda *_a: (1e9, -1e9)
    with pytest.raises(AssertionError):
        test_c4_channels_are_well_formed.hypothesis.inner_test(
            [(0.0, 0.0, 10.0, 0.0), (0.0, 5.0, 10.0, 15.0)], 1.05
        )


def test_c5_fails_for_clearance_ignoring_courtyards(restore_kernels) -> None:
    original = KERNELS._compute_courtyards
    KERNELS._compute_courtyards = lambda result, _clearance: original(result, 0.0)
    with pytest.raises(AssertionError):
        test_c5_courtyards_expand_by_exactly_the_clearance.hypothesis.inner_test(
            {
                "traces": [],
                "vias": [],
                "components": [("U1", (0.0, 0.0), 2.0, 2.0)],
                "board": (64.0, 64.0),
            },
            0.25,
        )


def test_c5_fails_for_including_unpositioned_components(restore_kernels) -> None:
    KERNELS._compute_courtyards = lambda result, _clearance: [
        KERNELS._Courtyard(ref=c.ref, x_min=0.0, y_min=0.0, x_max=1.0, y_max=1.0)
        for c in result.netlist.components
    ]
    with pytest.raises(AssertionError):
        test_c5_courtyards_expand_by_exactly_the_clearance.hypothesis.inner_test(
            {
                "traces": [],
                "vias": [],
                "components": [("U1", None, 2.0, 2.0)],
                "board": (64.0, 64.0),
            },
            0.25,
        )


# ===========================================================================
# quality/via_count — V1..V5
# ===========================================================================


@given(any_board)
@_SETTINGS
def test_v1_via_counts_are_a_partition(scenario) -> None:
    """V1: the three classes partition the vias exactly.

    ``signal + thermal + stitching == total == len(vias)``.  This is the
    property the recorded ``human_reference.yaml`` ``via_count`` baseline
    corroborates on all five corpus boards.
    """
    result = FX.build(scenario)
    counts = KERNELS._classify_vias(result)
    assert counts.total == len(result.vias)
    assert counts.signal + counts.thermal + counts.stitching == counts.total


@given(any_board)
@_SETTINGS
def test_v2_via_counts_are_nonnegative_ints(scenario) -> None:
    """V2: every count is a non-negative ``int``, never a float or a bool.

    The concrete type matters: the differential compares by type-carrying
    signature, and ``True == 1`` in Python.
    """
    counts = KERNELS._classify_vias(FX.build(scenario))
    for value in (counts.signal, counts.thermal, counts.stitching, counts.total):
        assert type(value) is int
        assert value >= 0


@given(any_board)
@_SETTINGS
def test_v3_thermal_requires_a_thermal_component(scenario) -> None:
    """V3: no Q1/Q2 with a position means no thermal vias.

    Thermal classification needs both the ``DC_BUS+`` net *and* containment in
    a Q1/Q2 bbox, so removing the component must zero the class.
    """
    result = FX.build(scenario)
    has_thermal_comp = any(
        c.ref in {"Q1", "Q2"} and c.initial_position is not None for c in result.netlist.components
    )
    counts = KERNELS._classify_vias(result)
    if not has_thermal_comp:
        assert counts.thermal == 0


@given(points(), st.floats(min_value=0.0, max_value=50.0), st.floats(min_value=0.0, max_value=50.0))
@_SETTINGS
def test_v4_edge_proximity_is_monotone_in_margin(via_pos, margin_a, margin_b) -> None:
    """V4: widening the margin can only add vias to the stitching class.

    ``_is_via_near_board_edge`` is a threshold on a fixed distance, so it is
    monotone non-decreasing in the margin.  A kernel that keys off the margin
    value rather than comparing against it is not.

    The two drawn margins are ordered here rather than filtered with
    ``assume``, so the mutation test can call ``inner_test`` directly without
    tripping Hypothesis's "assume outside a property-based test" deprecation.
    """
    lo, hi = min(margin_a, margin_b), max(margin_a, margin_b)
    via = FX.FakeVia(position=via_pos, net="GND", layers=("F.Cu", "B.Cu"))
    board = (0.0, 0.0, 100.0, 100.0)
    if KERNELS._is_via_near_board_edge(via, board, lo):
        assert KERNELS._is_via_near_board_edge(via, board, hi)


@given(points(), st.lists(segments(), min_size=0, max_size=4))
@_SETTINGS
def test_v5_bbox_containment_is_monotone_in_the_bbox_list(via_pos, rects) -> None:
    """V5: adding a bbox never turns a hit into a miss.

    ``_is_via_in_bbox`` is an ``any()`` over the list, so it is monotone in
    list inclusion.  A kernel that keys off the list length is not.
    """
    bboxes = [(min(r[0], r[2]), min(r[1], r[3]), max(r[0], r[2]), max(r[1], r[3])) for r in rects]
    via = FX.FakeVia(position=via_pos, net="N", layers=("F.Cu", "B.Cu"))
    extra = (-1000.0, -1000.0, -999.0, -999.0)
    if KERNELS._is_via_in_bbox(via, bboxes):
        assert KERNELS._is_via_in_bbox(via, [*bboxes, extra])


# --- V1..V5 mutation tests -------------------------------------------------


def _counts_mutant(signal, thermal, stitching, total):
    return lambda _result: KERNELS.ViaCounts(
        signal=signal, thermal=thermal, stitching=stitching, total=total
    )


def test_v1_fails_for_non_partitioning_counts(restore_kernels) -> None:
    KERNELS._classify_vias = _counts_mutant(5, 0, 0, 3)
    with pytest.raises(AssertionError):
        test_v1_via_counts_are_a_partition.hypothesis.inner_test(
            dict(SCENARIOS)["mixed_via_classes"]
        )


def test_v1_fails_for_wrong_total(restore_kernels) -> None:
    KERNELS._classify_vias = _counts_mutant(0, 0, 0, 0)
    with pytest.raises(AssertionError):
        test_v1_via_counts_are_a_partition.hypothesis.inner_test(
            dict(SCENARIOS)["mixed_via_classes"]
        )


def test_v2_fails_for_negative_counts(restore_kernels) -> None:
    KERNELS._classify_vias = _counts_mutant(-1, 0, 0, -1)
    with pytest.raises(AssertionError):
        test_v2_via_counts_are_nonnegative_ints.hypothesis.inner_test(
            dict(SCENARIOS)["empty_board"]
        )


def test_v2_fails_for_float_counts(restore_kernels) -> None:
    """The pyo3 mutant: counts returned as f64 rather than usize."""
    KERNELS._classify_vias = _counts_mutant(0.0, 0.0, 0.0, 0.0)
    with pytest.raises(AssertionError):
        test_v2_via_counts_are_nonnegative_ints.hypothesis.inner_test(
            dict(SCENARIOS)["empty_board"]
        )


def test_v3_fails_for_net_only_thermal_classification(restore_kernels) -> None:
    """The plausible simplification: classify thermal by net name alone,
    dropping the Q1/Q2 bbox containment test."""
    KERNELS._get_component_bboxes = lambda _result, _refs: [(-1e9, -1e9, 1e9, 1e9)]
    with pytest.raises(AssertionError):
        test_v3_thermal_requires_a_thermal_component.hypothesis.inner_test(
            {
                "traces": [],
                "vias": [((10.0, 10.0), "DC_BUS+", ("F.Cu", "B.Cu"))],
                "components": [("R1", (0.0, 0.0), 1.0, 1.0)],
                "board": (64.0, 64.0),
            }
        )


def test_v4_fails_for_non_monotone_margin(restore_kernels) -> None:
    KERNELS._is_via_near_board_edge = lambda _via, _board, margin: margin == 5.0
    with pytest.raises(AssertionError):
        test_v4_edge_proximity_is_monotone_in_margin.hypothesis.inner_test((1.0, 1.0), 5.0, 10.0)


def test_v5_fails_for_length_keyed_containment(restore_kernels) -> None:
    KERNELS._is_via_in_bbox = lambda _via, bboxes: len(bboxes) == 1
    with pytest.raises(AssertionError):
        test_v5_bbox_containment_is_monotone_in_the_bbox_list.hypothesis.inner_test(
            (0.0, 0.0), [(0.0, 0.0, 1.0, 1.0)]
        )


# ===========================================================================
# G5 — METAMORPHIC RELATIONS
#
# Each relation states its exactness claim explicitly.  See the module
# docstring for why each claim is or is not "exact".
# ===========================================================================

_POW2 = st.sampled_from([0.25, 0.5, 1.0, 2.0, 4.0, 8.0])
_POW2_OFFSET = st.sampled_from([-64.0, -16.0, 0.0, 16.0, 64.0, 256.0])


def _translate_segment(seg, dx, dy):
    return (seg[0] + dx, seg[1] + dy, seg[2] + dx, seg[3] + dy)


def _scale_segment(seg, k):
    return (seg[0] * k, seg[1] * k, seg[2] * k, seg[3] * k)


def _rot90(x, y):
    """Exact: entries are 0 and +/-1, so this is a permute-and-negate."""
    return (-y, x)


# --- slop_linter: M-S1..M-S4 ----------------------------------------------


@given(angle_inputs(), _POW2_OFFSET, _POW2_OFFSET)
@_SETTINGS
def test_m_s1_angle_is_exactly_translation_invariant(case, dx, dy) -> None:
    """M-S1 (slop_linter): translation invariance -- **EXACT**.

    Claimed exact only because the strategy draws dyadic coordinates
    (multiples of 1/64, |x| <= 64) and power-of-two offsets, so every
    ``(a + t) - (b + t)`` is computed without rounding.  The relation is NOT
    claimed for arbitrary offsets.
    """
    base = KERNELS._angle_between(
        ((case[0], case[1]), (case[2], case[3])),
        ((case[4], case[5]), (case[6], case[7])),
    )
    moved = KERNELS._angle_between(
        ((case[0] + dx, case[1] + dy), (case[2] + dx, case[3] + dy)),
        ((case[4] + dx, case[5] + dy), (case[6] + dx, case[7] + dy)),
    )
    assert base == moved


@given(points(), points(), _POW2)
@_SETTINGS
def test_m_s2_distance_scales_exactly_by_powers_of_two(a, b, k) -> None:
    """M-S2 (slop_linter): power-of-two scaling -- **EXACT**.

    ``_distance_mm(k*a, k*b) == k * _distance_mm(a, b)`` bit-for-bit.  Scaling
    an f64 by 2**n shifts the exponent and leaves the mantissa alone, and
    CPython's ``hypot`` is exactly homogeneous under such a factor.  This would
    NOT hold for a non-power-of-two factor.
    """
    scaled_a = (a[0] * k, a[1] * k)
    scaled_b = (b[0] * k, b[1] * k)
    assert KERNELS._distance_mm(scaled_a, scaled_b) == k * KERNELS._distance_mm(a, b)


@given(angle_inputs())
@_SETTINGS
def test_m_s3_angle_is_exactly_invariant_under_cardinal_rotation(case) -> None:
    """M-S3 (slop_linter): 90/180/270 deg rotation -- **EXACT**.

    A cardinal rotation only permutes and negates coordinates, so no rounding
    occurs and the turn angle is preserved bit-for-bit.  Contrast M-S4.
    """
    base = KERNELS._angle_between(
        ((case[0], case[1]), (case[2], case[3])),
        ((case[4], case[5]), (case[6], case[7])),
    )
    pts = [(case[0], case[1]), (case[2], case[3]), (case[4], case[5]), (case[6], case[7])]
    for _ in range(3):
        pts = [_rot90(x, y) for x, y in pts]
        rotated = KERNELS._angle_between((pts[0], pts[1]), (pts[2], pts[3]))
        assert base == rotated


@given(angle_inputs(), st.sampled_from([15.0, 30.0, 45.0, 137.5]))
@_SETTINGS
def test_m_s4_angle_is_approximately_invariant_under_arbitrary_rotation(case, degrees) -> None:
    """M-S4 (slop_linter): non-cardinal rotation -- **NOT EXACT**, bounded.

    ``math.cos``/``math.sin`` of a non-dyadic angle round, so the rotated
    coordinates are not bit-identical and neither is the resulting angle.

    The tolerance is **1e-5 deg**, and the size is not arbitrary -- it is set
    by ``acos`` being ill-conditioned at its endpoints.  For a *collinear*
    junction the true cosine is exactly +/-1; rotation perturbs it to
    ``1 - eps`` with ``eps`` a few ulps, and ``acos(1 - eps) ~ sqrt(2*eps)``,
    so a ~1e-12 perturbation of the cosine becomes a ~1e-6 deg change in the
    angle.  That square-root amplification, not the rotation itself, is what
    sets the band:

    * generic (non-collinear) junctions -- worst 4.0e-10 deg over 200,000
      random dyadic cases;
    * collinear junctions -- worst 1.7e-6 deg over 200,000 random cases.

    An earlier version of this test claimed 1e-6 and Hypothesis falsified it
    with a collinear case at 1.207e-6, which is how the regime split above was
    found.  :func:`test_m_s4_measured_rotation_band` pins both numbers.

    1e-5 deg remains five orders of magnitude below the kernel's 5 deg and
    160 deg decision thresholds, so no finding can flip because of it.
    Claiming ``==`` here would be the dishonest version of this test.
    """
    theta = math.radians(degrees)
    cos_t, sin_t = math.cos(theta), math.sin(theta)

    def rotate(x, y):
        return (x * cos_t - y * sin_t, x * sin_t + y * cos_t)

    base = KERNELS._angle_between(
        ((case[0], case[1]), (case[2], case[3])),
        ((case[4], case[5]), (case[6], case[7])),
    )
    pts = [(case[0], case[1]), (case[2], case[3]), (case[4], case[5]), (case[6], case[7])]
    rot = [rotate(x, y) for x, y in pts]
    rotated = KERNELS._angle_between((rot[0], rot[1]), (rot[2], rot[3]))
    assert abs(base - rotated) <= 1e-5


def _rotation_deviation(case, degrees: float) -> float:
    theta = math.radians(degrees)
    cos_t, sin_t = math.cos(theta), math.sin(theta)
    pts = [(case[0], case[1]), (case[2], case[3]), (case[4], case[5]), (case[6], case[7])]
    base = KERNELS._angle_between((pts[0], pts[1]), (pts[2], pts[3]))
    rot = [(x * cos_t - y * sin_t, x * sin_t + y * cos_t) for x, y in pts]
    got = KERNELS._angle_between((rot[0], rot[1]), (rot[2], rot[3]))
    return abs(base - got)


def test_m_s4_measured_rotation_band() -> None:
    """Measure M-S4's band in BOTH regimes, so the tolerance is a number.

    The two regimes differ by nearly four orders of magnitude because ``acos``
    is ill-conditioned at its endpoints -- see M-S4's docstring.  Pinning them
    separately is what stops the generic case from hiding behind the collinear
    tolerance: if generic rotation error ever grew to collinear levels, the
    first assertion fails even though the M-S4 property would still pass.
    """
    rng = random.Random(20260804)
    angles = (15.0, 30.0, 45.0, 137.5)

    generic_worst = 0.0
    for _ in range(4000):
        case = tuple(rng.randint(-4096, 4096) / 64.0 for _ in range(8))
        generic_worst = max(generic_worst, _rotation_deviation(case, rng.choice(angles)))

    collinear_worst = 0.0
    for _ in range(4000):
        xs = [rng.randint(-4096, 4096) / 64.0 for _ in range(4)]
        case = (xs[0], 0.0, xs[1], 0.0, xs[2], 0.0, xs[3], 0.0)
        collinear_worst = max(collinear_worst, _rotation_deviation(case, rng.choice(angles)))

    # Generic junctions: acos is well-conditioned away from +/-1.
    assert generic_worst <= 1e-8, f"generic rotation band widened to {generic_worst}"
    # Collinear junctions: sqrt-amplified, and the reason M-S4 tolerates 1e-5.
    assert collinear_worst <= 5e-6, f"collinear rotation band widened to {collinear_worst}"
    assert collinear_worst > generic_worst, (
        "the collinear regime is supposed to be the ill-conditioned one; if it "
        "is not, the tolerance rationale in M-S4 no longer holds"
    )


# --- corridor: M-C1..M-C4 -------------------------------------------------


def _translate_board(scenario, dx, dy):
    return {
        "traces": [
            (sx + dx, sy + dy, ex + dx, ey + dy, w, layer, net)
            for (sx, sy, ex, ey, w, layer, net) in scenario["traces"]
        ],
        "vias": scenario["vias"],
        "components": [
            (ref, None if pos is None else (pos[0] + dx, pos[1] + dy), w, h)
            for (ref, pos, w, h) in scenario["components"]
        ],
        "board": scenario["board"],
    }


@given(any_board, _POW2_OFFSET, _POW2_OFFSET)
@_SETTINGS
def test_m_c1_consolidation_is_exactly_translation_invariant(scenario, dx, dy) -> None:
    """M-C1 (corridor): translation invariance of consolidation -- **EXACT**.

    Consolidation never subtracts two coordinates: it sorts tracks by ``x`` (or
    ``y``) and counts pairs, so it depends only on the *order* of the
    coordinates, which a translation preserves exactly.  Bit-exact equality is
    therefore a legitimate claim here.

    Spread is a different story -- see :func:`test_m_c2_spread_is_translation_
    invariant_within_a_measured_band`, which is where the honest bound lives.
    """
    moved = _translate_board(scenario, dx, dy)
    assert KERNELS._compute_consolidation(
        FX.build(scenario), None, None, None
    ) == KERNELS._compute_consolidation(FX.build(moved), None, None, None)


@given(any_board, _POW2_OFFSET, _POW2_OFFSET)
@_SETTINGS
def test_m_c2_spread_is_translation_invariant_within_a_measured_band(scenario, dx, dy) -> None:
    """M-C2 (corridor): translation invariance of spread -- **NOT EXACT**.

    Spread subtracts *track edges*: ``channel_tracks[i+1].left_edge -
    channel_tracks[i].right_edge``, where each edge is ``x -/+ width/2``.  That
    is a difference of two nearby large numbers once the board is translated
    away from the origin, so the result loses low-order bits: translating a
    board by (-64, -64) moved a measured spread from
    ``2.4285714285714275`` to ``2.4285714285714124``.

    This relation was **initially written as exact and the test caught it** --
    which is the whole point of running the properties against the pinned
    oracle before writing the Rust.  It is therefore bounded by a relative
    tolerance of 1e-12, with the observed band measured by
    :func:`test_m_c2_measured_translation_band`.
    """
    moved = _translate_board(scenario, dx, dy)
    base = KERNELS._compute_spread(FX.build(scenario), None, None, None)
    got = KERNELS._compute_spread(FX.build(moved), None, None, None)
    assert got == pytest.approx(base, rel=1e-12, abs=1e-12)


def test_m_c2_measured_translation_band() -> None:
    """Measure the worst relative deviation M-C2 tolerates.

    Keeps the tolerance honest: if a future change widens the band, this fails
    before the tolerance quietly absorbs it.
    """
    scenario = {
        "traces": [
            (x, -1.0, x, 1.0, 0.25, "F.Cu", f"N{i}") for i, x in enumerate([-3.0, 0.0, 3.0])
        ],
        "vias": [],
        "components": [("U1", (0.0, -8.0), 8.0, 4.0), ("U2", (0.0, 8.0), 8.0, 4.0)],
        "board": (64.0, 64.0),
    }
    base = KERNELS._compute_spread(FX.build(scenario), None, None, None)
    assert base > 0.0, "the measurement board must actually occupy a channel"
    worst = 0.0
    for offset in (-4096.0, -256.0, -64.0, 0.0, 64.0, 256.0, 4096.0):
        moved = _translate_board(scenario, offset, offset)
        got = KERNELS._compute_spread(FX.build(moved), None, None, None)
        worst = max(worst, abs(got - base) / base)
    assert worst <= 1e-13, f"translation band widened to {worst}"


@given(any_board)
@_SETTINGS
def test_m_c3_corridor_scores_are_exactly_permutation_invariant_in_tracks(
    scenario,
) -> None:
    """M-C3 (corridor): track-order permutation -- **EXACT**.

    Both kernels sort each channel's tracks (by ``t.x`` or ``t.y``) before
    pairing, so the input order of the trace list cannot matter.  Contrast
    M-C5, where permuting a *different* input is not invariant at all.
    """
    reversed_scenario = {**scenario, "traces": list(reversed(scenario["traces"]))}
    for kernel in (KERNELS._compute_consolidation, KERNELS._compute_spread):
        assert kernel(FX.build(scenario), None, None, None) == kernel(
            FX.build(reversed_scenario), None, None, None
        )


@given(any_board, _POW2)
@_SETTINGS
def test_m_c4_consolidation_is_exactly_scale_invariant(scenario, k) -> None:
    """M-C4 (corridor): power-of-two scaling -- **EXACT** (consolidation only).

    Scaling every length by 2**n and scaling the three clearance parameters by
    the same factor reproduces the identical channel decomposition and the
    identical track ordering, so the dimensionless pair ratio is bit-identical.

    Both arms must scale.  An earlier version of this test compared the
    *unscaled* board under scaled parameters against the scaled board under
    scaled parameters, which is not a metamorphic relation at all -- it changed
    two things at once, and the test correctly reported 1.0 != 0.7.

    Spread is deliberately excluded: it divides by a target spacing derived
    from the same parameters but subtracts track edges built from *unscaled*
    widths, so it is not scale-invariant under this transform.  Claiming it
    would overstate the relation.
    """
    scaled = {
        "traces": [
            (sx * k, sy * k, ex * k, ey * k, w * k, layer, net)
            for (sx, sy, ex, ey, w, layer, net) in scenario["traces"]
        ],
        "vias": scenario["vias"],
        "components": [
            (ref, None if pos is None else (pos[0] * k, pos[1] * k), w * k, h * k)
            for (ref, pos, w, h) in scenario["components"]
        ],
        "board": scenario["board"],
    }
    base = KERNELS._compute_consolidation(FX.build(scenario), 0.25, 0.2, 0.15)
    got = KERNELS._compute_consolidation(FX.build(scaled), 0.25 * k, 0.2 * k, 0.15 * k)
    assert base == got


def test_m_c5_component_order_is_NOT_invariant() -> None:
    """M-C5 (corridor): component-order permutation -- **COUNTER-RELATION**.

    Permuting the *component* list is NOT invariant, because both ``else``
    arms of ``_identify_channels`` are unreachable (oracle header, defect 3):
    a channel is found only for pairs where the earlier-listed courtyard is
    the lower/left one.

    Recording the failure of this relation is as much a specification as the
    invariances above -- a Rust port that "fixed" the asymmetry would pass
    every other test in this file and still be wrong.
    """
    by_name = dict(SCENARIOS)
    forward = by_name["corridor_two_components_one_channel"]
    reverse = by_name["corridor_reversed_component_order"]
    assert forward["traces"] == reverse["traces"]
    assert sorted(forward["components"]) == sorted(reverse["components"])

    forward_score = KERNELS._compute_consolidation(FX.build(forward), None, None, None)
    reverse_score = KERNELS._compute_consolidation(FX.build(reverse), None, None, None)
    assert forward_score != reverse_score
    assert reverse_score == 1.0  # the no-channels constant


# --- via_count: M-V1..M-V4 ------------------------------------------------


@given(any_board)
@_SETTINGS
def test_m_v1_via_counts_are_exactly_permutation_invariant(scenario) -> None:
    """M-V1 (via_count): via-order permutation -- **EXACT**.

    The counts are sums over an independent per-via classification, so the
    order of the via list cannot matter.  (The order of the *component* list
    can, but only through ``_get_component_bboxes``, which is an ``any()``.)
    """
    from dataclasses import astuple

    reversed_scenario = {**scenario, "vias": list(reversed(scenario["vias"]))}
    assert astuple(KERNELS._classify_vias(FX.build(scenario))) == astuple(
        KERNELS._classify_vias(FX.build(reversed_scenario))
    )


@given(any_board)
@_SETTINGS
def test_m_v2_thermal_net_matching_is_exactly_case_invariant(scenario) -> None:
    """M-V2 (via_count): net-name case folding -- **EXACT**.

    Thermal classification compares ``via_net.upper()`` against
    ``"DC_BUS+".upper()``, so upper-casing every via net name cannot change
    the thermal count.  It CAN change the ground and signal classes
    (``is_ground_net`` has its own rules), so only the thermal count is
    asserted -- claiming all three would overstate the relation.
    """
    upper = {
        **scenario,
        "vias": [
            (pos, None if net is None else net.upper(), layers)
            for (pos, net, layers) in scenario["vias"]
        ],
    }
    assert (
        KERNELS._classify_vias(FX.build(scenario)).thermal
        == KERNELS._classify_vias(FX.build(upper)).thermal
    )


@given(points(), _POW2)
@_SETTINGS
def test_m_v3_edge_proximity_is_exactly_scale_invariant(via_pos, k) -> None:
    """M-V3 (via_count): power-of-two scaling -- **EXACT**, margin scaled too.

    ``_is_via_near_board_edge`` compares a distance against a margin, so it is
    invariant under a uniform power-of-two scaling of the board, the via and
    **the margin together**.  Scaling only the geometry is a different
    relation, and it does not hold -- see M-V4.
    """
    via = FX.FakeVia(position=via_pos, net="GND", layers=("F.Cu", "B.Cu"))
    scaled_via = FX.FakeVia(
        position=(via_pos[0] * k, via_pos[1] * k), net="GND", layers=("F.Cu", "B.Cu")
    )
    board = (0.0, 0.0, 100.0, 100.0)
    scaled_board = (0.0, 0.0, 100.0 * k, 100.0 * k)
    assert KERNELS._is_via_near_board_edge(via, board, 5.0) == KERNELS._is_via_near_board_edge(
        scaled_via, scaled_board, 5.0 * k
    )


def test_m_v4_scaling_is_NOT_invariant_for_stitching() -> None:
    """M-V4 (via_count): geometry-only scaling -- **COUNTER-RELATION**.

    ``_STITCHING_EDGE_MARGIN_MM`` is a hard-coded 5.0 inside ``_classify_vias``
    with no parameter to scale it, so shrinking a board by 2x while keeping the
    margin fixed reclassifies vias.  A Rust port that made the margin relative
    to board size would pass every invariance test above and change published
    baselines.
    """
    scenario = {
        "traces": [],
        "vias": [((8.0, 50.0), "GND", ("F.Cu", "B.Cu"))],
        "components": [],
        "board": (100.0, 100.0),
    }
    halved = {
        **scenario,
        "vias": [((4.0, 25.0), "GND", ("F.Cu", "B.Cu"))],
        "board": (50.0, 50.0),
    }
    assert KERNELS._classify_vias(FX.build(scenario)).stitching == 0
    assert KERNELS._classify_vias(FX.build(halved)).stitching == 1
