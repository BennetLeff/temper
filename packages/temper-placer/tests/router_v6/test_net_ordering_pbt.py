"""R1c/R1d property + metamorphic tests for ``router_v6/net_ordering`` (cluster G, split).

**GREEN.**  These run against the pinned oracle
(``tests/router_v6/_net_ordering_py_oracle.py``) -- the pre-migration
behaviour -- so that "the Phase-B Rust satisfies the properties" is a claim
about properties that existed before the Rust did.

Gate G4 -- **6 non-vacuous properties** (P1-P6), each with at least one
``test_pN_fails_for_<mutant>`` mutation test proving a degenerate kernel
violates it.

One bound here was **found by these tests, not assumed**: P4's natural
companion "``area == 0`` iff a span is zero" is false, because two pins
``3.88e-259`` apart have a span *product* that underflows to ``+0.0`` while
neither span is zero.  Recorded as
:func:`test_p4_area_underflows_where_hpwl_does_not` -- B8's standing denormal
class, and the same one the cluster-E suite's P3 hit independently.

Gate G5 -- **3 metamorphic relations** (M1-M3), honestly bounded:

* **M1 permutation invariance** -- the sharpest relation this module has, and
  the one the brief singled out as the place a real determinism bug would
  show.  **It holds, bit-exactly**, and the exactness is not a floating-point
  claim at all: the sort key is a total order over distinct names with finite
  wirelengths, so reordering the input cannot change the output.  Measured
  exhaustively over every permutation of the corpus designs, plus randomized
  permutations here.  **No determinism bug found.**
* **M2 translation** -- translating every pin by the same offset leaves the
  ordering unchanged.  **Exactness is claimed only for dyadic offsets**
  (``k * 2**-4`` over coordinates below 2**20), where ``x + dx`` is exact and
  therefore so is ``max(xs) - min(xs)``.  For a general offset the HPWL
  *values* shift by a rounding step and the relation is about the induced
  ORDER, which is the weaker statement actually asserted.
* **M3 power-of-two scaling** -- scaling every coordinate by ``2**k`` scales
  every HPWL by exactly ``2**k`` and leaves the ordering identical.
  **Bit-exact**, because multiplying by a power of two only shifts the
  exponent.

The one place the total order breaks -- a NaN wirelength -- is deliberately
excluded from the strategies here and pinned by name in
``test_net_ordering_rust_differential.py::test_nan_wirelength_breaks_the_total_order``
instead.  Encoding it as a weakened property would bury a real finding.
"""

from __future__ import annotations

import math

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

import tests.router_v6._net_ordering_py_oracle as ORACLE
from tests.router_v6._net_ordering_builders import (
    build_loops,
    build_netlist,
    build_order_netlist,
)

_SETTINGS = settings(max_examples=100, deadline=None)

_COORD = st.floats(min_value=-1e5, max_value=1e5, allow_nan=False, allow_infinity=False, width=64)
_NAME = st.text(alphabet="ABCDEFGHJKLMNPQRSTUVWXYZ_0123456789", min_size=1, max_size=6)


@st.composite
def _designs(draw, min_nets: int = 1, max_nets: int = 6):
    """``(components, nets)`` with **unique** net names and finite coords.

    Unique names are what make the 6-tuple key a total order; NaN is excluded
    for the same reason.  Both exclusions are load-bearing and both are
    covered elsewhere (duplicate names and NaN each have a named differential
    test).
    """
    names = draw(st.lists(_NAME, min_size=min_nets, max_size=max_nets, unique=True))
    components = []
    nets = []
    for i, name in enumerate(names):
        npins = draw(st.integers(min_value=1, max_value=4))
        pins = [(str(p), (draw(_COORD), draw(_COORD)), name) for p in range(npins)]
        components.append((f"U{i}", (draw(_COORD), draw(_COORD)), 0, pins))
        nets.append((name, [(f"U{i}", str(p)) for p in range(npins)], None))
    return components, nets


@st.composite
def _pin_lists(draw, min_pins: int = 0, max_pins: int = 6):
    n = draw(st.integers(min_value=min_pins, max_value=max_pins))
    pins = [(str(p), (draw(_COORD), draw(_COORD)), "N") for p in range(n)]
    return [("U0", (0.0, 0.0), 0, pins)]


def _order(components, nets, loop_specs=(), config=None):
    return ORACLE.order_nets(
        build_order_netlist(components, nets), build_loops(list(loop_specs)), config
    )


# ===========================================================================
# P1 -- order_nets returns a permutation of the input net names.
# ===========================================================================


@given(_designs())
@_SETTINGS
def test_p1_output_is_a_permutation_of_the_input(design):
    """Nothing is dropped, nothing is invented, nothing is duplicated.

    A kernel that filters, truncates or de-duplicates fails this; the
    mutation test proves it.
    """
    components, nets = design
    ordered = _order(components, nets)
    assert sorted(ordered) == sorted(n for n, _p, _c in nets)
    assert len(ordered) == len(nets)


# ===========================================================================
# P2 -- the output is sorted by the 6-tuple key, non-decreasing.
# ===========================================================================


@given(_designs(min_nets=2))
@_SETTINGS
def test_p2_output_is_sorted_by_the_composite_key(design):
    """Consecutive pairs are non-decreasing under ``NetPriority._key()``.

    This is the contract ``order_nets``'s docstring states, expressed over
    the same key the module builds -- so a kernel that sorts by a *different*
    field (say, name only) is caught.
    """
    components, nets = design
    netlist = build_order_netlist(components, nets)
    loops = build_loops([])
    ordered = _order(components, nets)

    by_name = {}
    for name, pins, _cls in nets:
        by_name[name] = ORACLE.NetPriority(
            config_priority=5,
            loop_criticality=ORACLE.get_loop_criticality(name, loops),
            net_class=ORACLE.get_net_class_from_string("Signal"),
            pin_count=len(pins),
            estimated_wirelength=ORACLE.compute_hpwl(name, netlist),
            name=name,
        )._key()

    keys = [by_name[n] for n in ordered]
    assert keys == sorted(keys), f"not sorted by the composite key: {keys}"


# ===========================================================================
# P3 -- HPWL is non-negative, and dominated by the bounding-box diagonal.
# ===========================================================================


@given(_pin_lists())
@_SETTINGS
def test_p3_hpwl_is_nonnegative_and_bounds_each_axis(components):
    """``(max_x - min_x) + (max_y - min_y)``: never negative, at least as
    large as either axis span, and exactly ``0.0`` below two pins."""
    netlist = build_netlist(components)
    hpwl = ORACLE.compute_hpwl("N", netlist)
    pins = components[0][3]

    if len(pins) < 2:
        assert hpwl == 0.0
        return

    assert hpwl >= 0.0
    xs = [p.position[0] for c in netlist.components for p in c.pins]
    ys = [p.position[1] for c in netlist.components for p in c.pins]
    span_x = max(xs) - min(xs)
    span_y = max(ys) - min(ys)
    assert hpwl >= span_x
    assert hpwl >= span_y
    assert hpwl == span_x + span_y


# ===========================================================================
# P4 -- bbox area and HPWL agree on their bounding box.
# ===========================================================================


@given(_pin_lists(min_pins=2))
@_SETTINGS
def test_p4_area_and_hpwl_share_one_bounding_box(components):
    """The two functions differ by exactly one operator.

    ``hpwl == 0`` iff *both* spans are zero, which is what separates
    ``w + h`` from ``w * h`` and catches a kernel that computes one and
    derives the other.

    **Bounded honestly, and the bound was found by this test.**  The natural
    companion "``area == 0`` iff a span is zero" is **false**: hypothesis
    produced two pins ``3.88e-259`` apart on both axes, whose span *product*
    **underflows to +0.0** while neither span is zero.  That is B8's standing
    denormal class again -- the same one P3 of the cluster-E suite hit -- and
    it is asserted as the weaker implication plus an explicit underflow
    witness rather than papered over.
    """
    netlist = build_netlist(components)
    hpwl = ORACLE.compute_hpwl("N", netlist)
    area = ORACLE.compute_bbox_area("N", netlist)
    xs = [p.position[0] for c in netlist.components for p in c.pins]
    ys = [p.position[1] for c in netlist.components for p in c.pins]
    span_x = max(xs) - min(xs)
    span_y = max(ys) - min(ys)

    assert area >= 0.0
    assert area == span_x * span_y
    assert hpwl == span_x + span_y
    # one direction survives unconditionally ...
    if span_x == 0.0 or span_y == 0.0:
        assert area == 0.0
    # ... the converse only outside the underflow band
    if area == 0.0 and span_x != 0.0 and span_y != 0.0:
        assert span_x * span_y == 0.0, "a zero area with two non-zero spans must be underflow"
    assert (hpwl == 0.0) == (span_x == 0.0 and span_y == 0.0)


def test_p4_area_underflows_where_hpwl_does_not():
    """P4's bounded claim, with the witness hypothesis found.

    Two pins ``3.88e-259`` apart: ``w + h`` is a perfectly ordinary denormal-
    adjacent value, ``w * h`` underflows to ``+0.0``.  So a zero bbox area
    does **not** imply a degenerate bounding box, and code that treats it as
    "these pins are coincident" is wrong for a whole magnitude band.
    """
    eps = 3.875775732178223e-259
    components = [("U0", (0.0, 0.0), 0, [("0", (0.0, 0.0), "N"), ("1", (eps, eps), "N")])]
    netlist = build_netlist(components)
    assert ORACLE.compute_bbox_area("N", netlist) == 0.0
    assert ORACLE.compute_hpwl("N", netlist) == eps + eps
    assert ORACLE.compute_hpwl("N", netlist) != 0.0


# ===========================================================================
# P5 -- loop criticality is the minimum over the containing loops, in [0, 3].
# ===========================================================================


@given(
    st.lists(
        st.tuples(_NAME, st.sampled_from(["CRITICAL", "HIGH", "MEDIUM", "LOW"])),
        min_size=0,
        max_size=6,
        unique_by=lambda t: t[0],
    )
)
@_SETTINGS
def test_p5_loop_criticality_is_the_minimum_and_bounded(loops):
    """0 <= criticality <= 3, equal to the best containing loop's rank, and
    exactly 3 when the net is in no loop."""
    rank = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    specs = [(name, prio, ["TARGET"]) for name, prio in loops]
    got = ORACLE.get_loop_criticality("TARGET", build_loops(specs))

    assert 0 <= got <= 3
    if not loops:
        assert got == 3
    else:
        assert got == min(rank[p] for _n, p in loops)

    # a net in none of the loops is always 3, whatever the loops say
    assert ORACLE.get_loop_criticality("NOT_IN_ANY", build_loops(specs)) == 3


# ===========================================================================
# P6 -- the net-class table is total and exact-match.
# ===========================================================================


@given(st.text(max_size=12))
@_SETTINGS
def test_p6_net_class_lookup_is_total_and_exact(text):
    """Every string maps to some ``NetClass``, and anything not a literal key
    maps to ``SIGNAL``.

    Non-vacuous because the six members really are reachable -- asserted at
    the end so a constant-SIGNAL kernel cannot satisfy it.
    """
    got = ORACLE.get_net_class_from_string(text)
    assert isinstance(got, ORACLE.NetClass)

    keys = {
        "HighVoltage",
        "highvoltage",
        "HV",
        "Differential",
        "differential",
        "DiffPair",
        "Power",
        "power",
        "GateDrive",
        "gatedrive",
        "Gate",
        "GateDriveHV",
        "gatedrivehv",
        "GateDriveSELV",
        "gatedriveselv",
        "Signal",
        "signal",
        "FinePitch",
        "finepitch",
        "Ground",
        "ground",
        "GND",
    }
    if text not in keys:
        assert got is ORACLE.NetClass.SIGNAL

    reachable = {ORACLE.get_net_class_from_string(k) for k in keys}
    assert reachable == set(ORACLE.NetClass), f"unreachable NetClass members: {reachable}"


# ===========================================================================
# METAMORPHIC RELATIONS (gate G5)
# ===========================================================================


@given(_designs(min_nets=2), st.data())
@_SETTINGS
def test_m1_ordering_is_permutation_invariant(design, data):
    """M1 -- permuting ``netlist.nets`` does not change the output.

    **Exact, and not a floating-point claim.**  With unique names and finite
    wirelengths the 6-tuple key is a total order, so ``list.sort`` has
    exactly one correct answer and the input order is unobservable.

    This is the property the brief asked about by name.  **It holds.**  If it
    ever fails here, that is a real determinism bug in ``net_ordering`` and
    the correct response is to report it, not to relax this test.
    """
    components, nets = design
    base = _order(components, nets)
    for _ in range(4):
        permuted = data.draw(st.permutations(nets))
        assert _order(components, list(permuted)) == base, (
            "order_nets is NOT permutation invariant -- this is a real "
            "determinism bug; report it rather than weakening the property"
        )


@given(
    _designs(min_nets=2),
    st.integers(min_value=-64, max_value=64),
    st.integers(min_value=-64, max_value=64),
)
@_SETTINGS
def test_m2_dyadic_translation_preserves_the_ordering(design, kx, ky):
    """M2 -- translating every pin by a dyadic offset preserves the ordering.

    **Bounded**: the assertion is about the induced ORDER, which is exact.
    The HPWL *values* are not claimed to be translation-invariant -- for
    coordinates near the top of the drawn range, ``max(x + dx) - min(x + dx)``
    can differ from ``max(x) - min(x)`` by a rounding step, and this test does
    not pretend otherwise.  The offsets are ``k / 16`` so that ``x + dx`` is
    exact for the magnitudes drawn (|x| < 2**20), which is what makes the
    order stable rather than merely usually stable.
    """
    dx = kx / 16.0
    dy = ky / 16.0
    components, nets = design
    moved = [
        (ref, (px + dx, py + dy), rot, [(num, (x, y), net) for (num, (x, y), net) in pins])
        for (ref, (px, py), rot, pins) in components
    ]
    assert _order(moved, nets) == _order(components, nets)


@given(_designs(min_nets=2), st.integers(min_value=-8, max_value=8))
@_SETTINGS
def test_m3_power_of_two_scaling_is_bit_exact(design, exponent):
    """M3 -- scaling every coordinate by ``2**k`` scales every HPWL by
    exactly ``2**k`` and leaves the ordering identical.

    **Bit-exact.**  Multiplying by a power of two only changes the exponent
    field, so every ``max``/``min``/subtraction/addition in ``compute_hpwl``
    commutes with it, with no rounding anywhere.  A non-dyadic scale is not
    claimed and not tested.
    """
    scale = 2.0**exponent
    components, nets = design
    scaled = [
        (
            ref,
            (px * scale, py * scale),
            rot,
            [(num, (x * scale, y * scale), net) for (num, (x, y), net) in pins],
        )
        for (ref, (px, py), rot, pins) in components
    ]

    plain_netlist = build_netlist(components)
    scaled_netlist = build_netlist(scaled)
    for name, _pins, _cls in nets:
        plain = ORACLE.compute_hpwl(name, plain_netlist)
        got = ORACLE.compute_hpwl(name, scaled_netlist)
        assert got == plain * scale, f"{name}: {got!r} != {plain!r} * {scale!r}"

    assert _order(scaled, nets) == _order(components, nets)


# ===========================================================================
# Mutation tests (gate G4 vacuity guard)
# ===========================================================================


@pytest.fixture
def restore_kernels():
    saved = {
        name: getattr(ORACLE, name)
        for name in (
            "compute_hpwl",
            "compute_bbox_area",
            "get_loop_criticality",
            "get_net_class_from_string",
            "order_nets",
        )
    }
    yield
    for name, fn in saved.items():
        setattr(ORACLE, name, fn)


_SAMPLE = (
    [
        ("U0", (0.0, 0.0), 0, [("0", (0.0, 0.0), "AAA"), ("1", (3.0, 4.0), "AAA")]),
        ("U1", (0.0, 0.0), 0, [("0", (0.0, 0.0), "BBB"), ("1", (9.0, 1.0), "BBB")]),
        ("U2", (0.0, 0.0), 0, [("0", (0.0, 0.0), "CCC"), ("1", (1.0, 1.0), "CCC")]),
    ],
    [
        ("AAA", [("U0", "0"), ("U0", "1")], None),
        ("BBB", [("U1", "0"), ("U1", "1")], None),
        ("CCC", [("U2", "0"), ("U2", "1")], None),
    ],
)
_SAMPLE_PINS = [
    ("U0", (0.0, 0.0), 0, [("0", (0.0, 0.0), "N"), ("1", (3.0, 4.0), "N")]),
]

#: A design that straddles the origin, so an ``abs()``-based mutant really
#: does reorder under a +4 translation (see the M2 mutation test).
_M2_SAMPLE = (
    [
        ("U0", (-5.0, 0.0), 0, [("0", (0.0, 0.0), "AAA"), ("1", (3.0, 4.0), "AAA")]),
        ("U1", (1.0, 0.0), 0, [("0", (0.0, 0.0), "BBB"), ("1", (9.0, 1.0), "BBB")]),
        ("U2", (3.0, 0.0), 0, [("0", (0.0, 0.0), "CCC"), ("1", (1.0, 1.0), "CCC")]),
    ],
    [
        ("AAA", [("U0", "0"), ("U0", "1")], None),
        ("BBB", [("U1", "0"), ("U1", "1")], None),
        ("CCC", [("U2", "0"), ("U2", "1")], None),
    ],
)


class _FixedData:
    """A stand-in for ``st.data()`` that always returns the same permutation."""

    def __init__(self, value):
        self._value = value

    def draw(self, _strategy):
        return self._value


def test_p1_fails_for_a_truncating_kernel(restore_kernels):
    """Dropping the last net is still a *sorted* answer -- only P1 sees it."""
    original = ORACLE.order_nets
    ORACLE.order_nets = lambda netlist, loops, cfg=None: original(netlist, loops, cfg)[:-1]
    with pytest.raises(AssertionError):
        test_p1_output_is_a_permutation_of_the_input.hypothesis.inner_test(_SAMPLE)


def test_p1_fails_for_a_duplicating_kernel(restore_kernels):
    """Emitting a net twice keeps the sorted-ness and breaks the bijection."""
    original = ORACLE.order_nets

    def duplicate(netlist, loops, cfg=None):
        out = original(netlist, loops, cfg)
        return out + out[:1]

    ORACLE.order_nets = duplicate
    with pytest.raises(AssertionError):
        test_p1_output_is_a_permutation_of_the_input.hypothesis.inner_test(_SAMPLE)


def test_p2_fails_for_a_name_only_sort(restore_kernels):
    """Sorting alphabetically is a valid permutation, so only P2 catches it."""

    def by_name(netlist, loops, cfg=None):  # noqa: ARG001
        return sorted(n.name for n in netlist.nets)

    ORACLE.order_nets = by_name
    with pytest.raises(AssertionError):
        test_p2_output_is_sorted_by_the_composite_key.hypothesis.inner_test(_SAMPLE)


def test_p3_fails_for_a_hypot_hpwl(restore_kernels):
    """A diagonal-distance HPWL is smaller than the axis-span sum, so it
    stops dominating each axis and stops equalling ``w + h``."""

    def diagonal(net_name, netlist):
        positions = [p.position for c in netlist.components for p in c.pins if p.net == net_name]
        if len(positions) < 2:
            return 0.0
        xs = [p[0] for p in positions]
        ys = [p[1] for p in positions]
        return math.hypot(max(xs) - min(xs), max(ys) - min(ys))

    ORACLE.compute_hpwl = diagonal
    with pytest.raises(AssertionError):
        test_p3_hpwl_is_nonnegative_and_bounds_each_axis.hypothesis.inner_test(_SAMPLE_PINS)


def test_p4_fails_when_area_is_derived_from_hpwl(restore_kernels):
    """``(hpwl / 2) ** 2`` has the right units and the wrong value; it is
    also non-zero on a degenerate box, which is the assertion that bites."""

    def derived(net_name, netlist):
        return (ORACLE.compute_hpwl(net_name, netlist) / 2.0) ** 2

    ORACLE.compute_bbox_area = derived
    with pytest.raises(AssertionError):
        test_p4_area_and_hpwl_share_one_bounding_box.hypothesis.inner_test(_SAMPLE_PINS)


def test_p5_fails_for_a_maximising_criticality(restore_kernels):
    """Taking the worst loop instead of the best inverts the priority."""
    rank = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}

    def worst(net_name, loops):
        containing = loops.get_loops_for_net(net_name)
        if not containing:
            return 3
        return max(rank[loop.priority.name] for loop in containing)

    ORACLE.get_loop_criticality = worst
    with pytest.raises(AssertionError):
        test_p5_loop_criticality_is_the_minimum_and_bounded.hypothesis.inner_test(
            [("A", "CRITICAL"), ("B", "LOW")]
        )


def test_p6_fails_for_a_constant_signal_lookup(restore_kernels):
    """Returning ``SIGNAL`` for everything satisfies the fall-through half of
    P6 and fails its reachability half -- which is why both halves are there."""
    ORACLE.get_net_class_from_string = lambda s: ORACLE.NetClass.SIGNAL  # noqa: ARG005
    with pytest.raises(AssertionError):
        test_p6_net_class_lookup_is_total_and_exact.hypothesis.inner_test("anything")


def test_p6_fails_for_a_case_insensitive_lookup(restore_kernels):
    """A ``.lower()``-normalising lookup resolves ``'HIGHVOLTAGE'``, which
    the reference sends to ``SIGNAL``."""
    original = ORACLE.get_net_class_from_string
    ORACLE.get_net_class_from_string = lambda s: original(s if s in ("",) else s.lower())
    with pytest.raises(AssertionError):
        test_p6_net_class_lookup_is_total_and_exact.hypothesis.inner_test("HIGHVOLTAGE")


def test_m1_fails_for_an_input_order_preserving_kernel(restore_kernels):
    """A kernel that returns the input order unchanged is trivially "sorted"
    for an already-sorted input and fails the moment the input is permuted."""

    def as_given(netlist, loops, cfg=None):  # noqa: ARG001
        return [n.name for n in netlist.nets]

    ORACLE.order_nets = as_given
    _components, nets = _SAMPLE
    with pytest.raises(AssertionError):
        test_m1_ordering_is_permutation_invariant.hypothesis.inner_test(
            _SAMPLE, _FixedData(list(reversed(nets)))
        )


def test_m2_fails_for_an_absolute_position_tiebreak(restore_kernels):
    """A wirelength that depends on absolute position, not span, reorders
    under translation.

    ``_M2_SAMPLE`` straddles the origin on purpose: with nets at x = -5, 1, 3
    the mutant ranks them 5 < 1 < 3 -> ``B, C, A``, and a ``+4`` translation
    moves them to 1, 5, 7 -> ``A, B, C``.  A sample entirely on one side of
    zero would leave ``abs`` order-preserving and the mutant would survive,
    which is exactly the kind of accidentally-toothless mutation test this
    gate exists to prevent.
    """

    def absolute(net_name, netlist):
        positions = [
            ORACLE.pin_world_position(p, c)
            for c in netlist.components
            for p in c.pins
            if p.net == net_name
        ]
        if len(positions) < 2:
            return 0.0
        xs = [p[0] for p in positions]
        ys = [p[1] for p in positions]
        # `abs(min(...))` instead of a span: identical units, but anchored to
        # the origin rather than to the net's own extent.
        return abs(min(xs)) + (max(ys) - min(ys))

    ORACLE.compute_hpwl = absolute
    with pytest.raises(AssertionError):
        test_m2_dyadic_translation_preserves_the_ordering.hypothesis.inner_test(_M2_SAMPLE, 64, 0)


def test_m3_fails_for_an_additive_offset(restore_kernels):
    """Adding a constant makes the HPWL affine rather than homogeneous, so it
    stops commuting with scaling."""
    original = ORACLE.compute_hpwl
    ORACLE.compute_hpwl = lambda net_name, netlist: original(net_name, netlist) + 1.0
    with pytest.raises(AssertionError):
        test_m3_power_of_two_scaling_is_bit_exact.hypothesis.inner_test(_SAMPLE, 3)


# ---------------------------------------------------------------------------
# Sanity: the input classes are genuinely discriminating.
# ---------------------------------------------------------------------------


def test_strategies_are_discriminating():
    """Guards against the properties all passing on one degenerate example."""
    components, nets = _SAMPLE
    ordered = _order(components, nets)
    assert len(ordered) == 3
    assert ordered != sorted(n for n, _p, _c in nets), (
        "the sample design is broken by name alone -- it would not exercise "
        "the wirelength tiebreak that P2 and M1 rely on"
    )

    netlist = build_netlist(components)
    hpwls = {ORACLE.compute_hpwl(n, netlist) for n, _p, _c in nets}
    assert len(hpwls) == 3, f"the sample nets do not have distinct HPWLs: {hpwls}"

    areas = {ORACLE.compute_bbox_area(n, netlist) for n, _p, _c in nets}
    assert areas != hpwls, "area and hpwl coincide on every sample net"

    assert len(set(ORACLE.NetClass)) == 6
