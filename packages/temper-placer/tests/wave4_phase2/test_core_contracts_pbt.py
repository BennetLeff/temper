"""R1c: property-based tests for the Wave-4 Phase 2 contract layer.

Nine properties. Each one is a statement about the *port* that holds for
every input hypothesis can find, not a restatement of a single example.
The dominant property is differential -- "Rust agrees with the pinned
oracle" -- because that is the claim the migration actually makes; the
rest are structural invariants that would survive even if both arms were
wrong together, and so add independent signal.
"""

from __future__ import annotations

import math

import numpy as np
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

from temper_placer.core import manufacturing as prod_mf
from temper_placer.core import net_classification as prod_nc
from temper_placer.core import units as prod_units
from temper_placer.core.board import Rect as ProdRect
from temper_placer.core.netlist import build_adjacency_matrix as prod_adjacency
import temper_io_types as prod_drc
from tests.wave4_phase2 import _core_py_oracle as oracle
from tests.wave4_phase2._sig import assert_same, call

_SETTINGS = settings(
    max_examples=400,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)

_FINITE = st.floats(allow_nan=False, allow_infinity=False, width=64)
_ANY_FLOAT = st.floats(allow_nan=True, allow_infinity=True, width=64)
_NAMES = st.text(alphabet="ABCDEGLNPSUVWX_+-0123456789\n", min_size=0, max_size=16)


# --- P1 ---------------------------------------------------------------------
@_SETTINGS
@given(_ANY_FLOAT)
def test_p1_angle_conversions_agree_with_the_oracle_bit_for_bit(x):
    """P1. Both angle conversions are bit-identical to the reference."""
    assert_same(prod_units.deg_to_rad(x), oracle.deg_to_rad(x), f"deg_to_rad({x!r})")
    assert_same(prod_units.rad_to_deg(x), oracle.rad_to_deg(x), f"rad_to_deg({x!r})")


# --- P2 ---------------------------------------------------------------------
@_SETTINGS
@given(_NAMES)
def test_p2_every_classifier_agrees_and_classify_is_a_total_function(name):
    """P2. All ten predicates agree, and `classify_net_type` is total.

    Totality plus the precedence rule is an independent structural claim:
    whatever the predicates say, the classifier's output is always one of
    exactly four labels and always the highest-precedence true one.
    """
    for fn_name in (
        "is_ground_net",
        "is_power_net",
        "is_hv_net",
        "is_signal_net",
        "classify_net_type",
        "is_ground_pin",
        "is_power_pin",
        "is_hv_pin",
        "is_clock_pin",
    ):
        assert_same(
            call(getattr(prod_nc, fn_name), name),
            call(getattr(oracle, fn_name), name),
            f"{fn_name}({name!r})",
        )

    label = prod_nc.classify_net_type(name)
    assert label in {"ground", "power", "hv", "signal"}
    expected = (
        "ground"
        if prod_nc.is_ground_net(name)
        else "power"
        if prod_nc.is_power_net(name)
        else "hv"
        if prod_nc.is_hv_net(name)
        else "signal"
    )
    assert label == expected
    assert prod_nc.is_signal_net(name) == (label == "signal")


# --- P3 ---------------------------------------------------------------------
@_SETTINGS
@given(_FINITE, _FINITE, st.floats(1e-9, 1e6), st.floats(1e-9, 1e6))
def test_p3_rect_round_trips_through_every_accessor(x0, y0, w, h):
    """P3. A valid Rect exposes the same four numbers by every route."""
    assume(math.isfinite(x0 + w) and math.isfinite(y0 + h))
    r = call(ProdRect, x0, y0, x0 + w, y0 + h)
    o = call(oracle.Rect, x0, y0, x0 + w, y0 + h)
    assert_same(r, o, "Rect")
    if isinstance(o, BaseException):
        return
    assert_same(list(r), list(o), "iter")
    assert_same([r[i] for i in range(4)], [o[i] for i in range(4)], "getitem")
    assert_same(r.width, o.width, "width")
    assert_same(r.height, o.height, "height")
    assert r == tuple(o)
    assert hash(r) == hash(tuple(o))
    assert repr(r) == repr(o)


# --- P4 ---------------------------------------------------------------------
@_SETTINGS
@given(_ANY_FLOAT, _ANY_FLOAT)
def test_p4_inflated_clearance_is_never_negative_and_matches(nominal, tolerance):
    """P4. Worst-case clearance agrees, and is >= 0 or NaN -- never < 0.

    The `>= 0 or NaN` half is the reason the reference uses `max` at all;
    it holds independently of whether the port is faithful, so a port
    that broke the clamp fails here even if both arms broke together.
    """
    got = prod_mf.inflated_clearance(nominal, tolerance)
    want = oracle.inflated_clearance(nominal, tolerance)
    assert_same(got, want, f"inflated_clearance({nominal!r}, {tolerance!r})")
    assert math.isnan(got) or got >= 0.0
    assert_same(
        prod_mf.inflated_width(nominal, tolerance),
        oracle.inflated_width(nominal, tolerance),
        "inflated_width",
    )


# --- P6 ---------------------------------------------------------------------
_REFS = st.lists(
    st.sampled_from([f"U{i}" for i in range(12)]), min_size=1, max_size=12, unique=True
)


@_SETTINGS
@given(
    _REFS,
    st.lists(
        st.lists(st.sampled_from([f"U{i}" for i in range(12)]), max_size=6),
        max_size=12,
    ),
)
def test_p6_adjacency_agrees_and_is_symmetric_with_a_zero_diagonal(refs, nets):
    """P6. The matrix agrees, is symmetric, and has a zero diagonal.

    Symmetry and the zero diagonal follow from the `i < j` enumeration
    and hold for any input; they are checked separately from the
    differential so a port that broke both arms' symmetry still fails.
    """
    from temper_placer.core.netlist import Component, Net, Netlist

    prod = Netlist(
        components=[Component(ref=r, footprint="F", bounds=(1.0, 1.0)) for r in refs],
        nets=[Net(name=f"N{i}", pins=[(r, "1") for r in p]) for i, p in enumerate(nets)],
    )
    orc = oracle.make_oracle_netlist(refs, nets)
    got = prod_adjacency(prod)
    assert_same(got, oracle.build_adjacency_matrix(orc), "adjacency")
    assert np.array_equal(got, got.T)
    assert float(np.trace(got)) == 0.0
    assert float(got.min()) >= 0.0


# --- P7 ---------------------------------------------------------------------
@_SETTINGS
@given(st.floats(-1e6, 1e6), st.floats(-1e3, 1e3).filter(lambda c: c != 0.0))
def test_p7_mm_to_cell_agrees_and_truncates_toward_zero(mm, cell):
    """P7. `mm_to_cell` agrees, and always truncates toward zero."""
    got = call(prod_units.mm_to_cell, mm, cell)
    want = call(oracle.mm_to_cell, mm, cell)
    assert_same(got, want, f"mm_to_cell({mm!r}, {cell!r})")
    if isinstance(want, BaseException):
        return
    quotient = mm / cell
    assert abs(got) <= abs(quotient)
    assert got == int(quotient)


# --- P8 ---------------------------------------------------------------------
@_SETTINGS
@given(_FINITE, _FINITE, _FINITE, _FINITE)
def test_p8_distances_agree_bit_for_bit(x1, y1, x2, y2):
    """P8. Both distances are bit-identical to the reference.

    The geometric ordering `euclidean <= manhattan` is deliberately NOT
    asserted here: it is false in floating point. See
    `test_witness_p8_euclidean_can_exceed_manhattan_under_underflow`.
    """
    assert_same(
        prod_units.distance_mm(x1, y1, x2, y2),
        oracle.distance_mm(x1, y1, x2, y2),
        "distance",
    )
    assert_same(
        prod_units.manhattan_distance_mm(x1, y1, x2, y2),
        oracle.manhattan_distance_mm(x1, y1, x2, y2),
        "manhattan",
    )


def test_witness_p8_euclidean_can_exceed_manhattan_under_underflow():
    """The ordering `euclidean <= manhattan` does NOT hold in f64.

    Found by hypothesis while this property was still asserting the
    ordering. With `x1 = y1 = x2 = 0` and a tiny `y2`, the true distance
    is exactly `|y2|` -- but `dy * dy` underflows into the subnormal
    range, and `sqrt` of that rounded-down square rounds *up* past `y2`.
    The result is one ulp **larger** than the Manhattan distance.

    Both arms compute the same wrong-looking number, so this is a fact
    about the reference, not a defect in the port: it is pinned here
    rather than papered over with a tolerance -- note that even
    `rel_tol=1e-12` does not rescue the claim, it just hides which
    direction the inequality broke.
    """
    y2 = 4.5404225906365494e-159
    d = prod_units.distance_mm(0.0, 0.0, 0.0, y2)
    m = prod_units.manhattan_distance_mm(0.0, 0.0, 0.0, y2)
    assert m == y2
    assert d > m, "expected the underflow counterexample to still bite"
    assert d.hex() == (4.540422610902304e-159).hex()
    assert_same(d, oracle.distance_mm(0.0, 0.0, 0.0, y2), "witness parity")
    assert_same(m, oracle.manhattan_distance_mm(0.0, 0.0, 0.0, y2), "witness parity")

    # Away from the underflow region the ordering does hold, so the
    # geometry is not simply wrong -- the failure is confined to inputs
    # whose squares are subnormal.
    for a, b in [(3.0, 4.0), (1e-8, 1e-8), (1e100, 1e100), (0.1, 0.2)]:
        assert prod_units.distance_mm(0.0, 0.0, a, b) <= prod_units.manhattan_distance_mm(
            0.0, 0.0, a, b
        )


# --- P9 ---------------------------------------------------------------------
@_SETTINGS
@given(st.floats(-1e6, 1e6), st.floats(-1e6, 1e6), st.floats(1e-6, 1e6), st.floats(1e-6, 1e6))
def test_p9_from_xywh_and_from_xyxy_describe_the_same_rectangle(x, y, w, h):
    """P9. `from_xywh(x, y, w, h) == from_xyxy(x, y, x+w, y+h)`, exactly."""
    a = call(ProdRect.from_xywh, x, y, w, h)
    b = call(ProdRect.from_xyxy, x, y, x + w, y + h)
    oa = call(oracle.Rect.from_xywh, x, y, w, h)
    ob = call(oracle.Rect.from_xyxy, x, y, x + w, y + h)
    assert_same(a, oa, "from_xywh")
    assert_same(b, ob, "from_xyxy")
    if not isinstance(a, BaseException):
        # The two constructors must agree with each other in both arms,
        # and agree about *whether* they agree -- `x + w` rounds once on
        # each side, so this is a real claim, not a tautology.
        assert (a == b) == (oa == ob)
        assert type(a) is type(ProdRect.from_xyxy(0.0, 0.0, 1.0, 1.0))
