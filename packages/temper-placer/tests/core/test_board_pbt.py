"""Property-based tests for the Rust board contracts (Wave 4 Phase 3 / R1c, R1d).

Nine non-vacuous properties (P1-P9) and four metamorphic relations
(MR1-MR4), each stated against the pinned Python oracle
(``_board_py_oracle.py``) so a property can only pass by the Rust *agreeing
with Python*. Every property whose generator could degenerate carries a
``test_*_is_non_vacuous`` companion that proves the interesting region is
actually reached.
"""

from __future__ import annotations

import numpy as np
import temper_design_bundle_python as _tdb
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

import tests.core._board_py_oracle as _oracle
from tests.core._contract_canon import canon, canon_call

_rs = _tdb.board_contracts

SETTINGS = settings(
    max_examples=200,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)

finite = st.floats(
    allow_nan=False, allow_infinity=False, min_value=-1e6, max_value=1e6, width=64
)
# ints AND floats: the dataclass never coerces, so both must survive.
coords = st.one_of(st.integers(min_value=-10**5, max_value=10**5), finite)
names = st.text(alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ_", min_size=1, max_size=6)


@st.composite
def valid_rect_args(draw):
    """`(x_min, y_min, x_max, y_max)` satisfying the strict min<max invariant."""
    x_min = draw(coords)
    y_min = draw(coords)
    x_max = draw(coords.filter(lambda v: v > x_min))
    y_max = draw(coords.filter(lambda v: v > y_min))
    return (x_min, y_min, x_max, y_max)


@st.composite
def any_rect_args(draw):
    """Unconstrained -- roughly half violate the invariant."""
    return (draw(coords), draw(coords), draw(coords), draw(coords))


@st.composite
def zone_args(draw):
    return (draw(names), draw(valid_rect_args()))


@st.composite
def board_spec(draw):
    return {
        "width": draw(coords),
        "height": draw(coords),
        "origin": (draw(coords), draw(coords)),
        "zones": draw(st.lists(zone_args(), max_size=4)),
        "holes": draw(st.lists(st.tuples(coords, coords, finite), max_size=3)),
        "keepouts": draw(st.lists(valid_rect_args(), max_size=3)),
        "grounds": draw(st.lists(st.tuples(names, valid_rect_args()), max_size=2)),
        "outline": draw(st.one_of(st.none(), st.lists(st.tuples(coords, coords), max_size=5))),
    }


def _build(spec, mod):
    return mod.Board(
        width=spec["width"],
        height=spec["height"],
        origin=spec["origin"],
        zones=[mod.Zone(n, b) for n, b in spec["zones"]],
        mounting_holes=[mod.MountingHole((x, y), d) for x, y, d in spec["holes"]],
        keepouts=list(spec["keepouts"]),
        ground_domains=[mod.GroundDomain(n, b) for n, b in spec["grounds"]],
        outline_polygon=spec["outline"],
    )


def _both(spec):
    return _build(spec, _oracle), _build(spec, _rs)


# ---------------------------------------------------------------------------
# P1-P9
# ---------------------------------------------------------------------------


@SETTINGS
@given(args=any_rect_args())
def test_p1_rect_construction_agrees_including_the_failure_path(args):
    """P1. `Rect(...)` agrees on value AND on the ValueError text, for
    arbitrary (mostly invalid) coordinates."""
    assert canon_call(_oracle.Rect, *args) == canon_call(_rs.Rect, *args)


def test_p1_is_non_vacuous():
    """Both outcomes of P1 are reachable."""
    assert canon_call(_rs.Rect, 0, 0, 1, 1)[0] == "ok"
    assert canon_call(_rs.Rect, 1, 0, 0, 1)[0] == "raised"


@SETTINGS
@given(args=valid_rect_args())
def test_p2_rect_never_widens_an_int_but_from_xyxy_always_floats(args):
    """P2. Direct construction preserves the input type exactly; the
    `from_xyxy` constructor always produces `float`. Both hold on both sides."""
    py, rs = _oracle.Rect(*args), _rs.Rect(*args)
    assert canon(py) == canon(rs)
    for field, supplied in zip(("x_min", "y_min", "x_max", "y_max"), args, strict=True):
        assert type(getattr(rs, field)) is type(supplied)
    coerced = _rs.Rect.from_xyxy(*args)
    assert canon(coerced) == canon(_oracle.Rect.from_xyxy(*args))
    assert all(isinstance(getattr(coerced, f), float) for f in ("x_min", "y_min", "x_max", "y_max"))


def test_p2_is_non_vacuous():
    """The int corpus really occurs, so P2's type check is not trivially
    satisfied by an all-float generator."""
    assert isinstance(_rs.Rect(0, 0, 1, 1).x_min, int)


@SETTINGS
@given(args=valid_rect_args())
def test_p3_rect_sequence_protocol_agrees(args):
    """P3. `len`, iteration, indexing (incl. negative and out-of-range) and
    hashing all agree."""
    py, rs = _oracle.Rect(*args), _rs.Rect(*args)
    assert len(py) == len(rs) == 4
    assert canon(tuple(py)) == canon(tuple(rs))
    assert hash(py) == hash(rs)
    for index in (-5, -1, 0, 3, 4):
        assert canon_call(py.__getitem__, index) == canon_call(rs.__getitem__, index)


@SETTINGS
@given(args=valid_rect_args())
def test_p4_rect_equals_its_own_coordinate_tuple(args):
    """P4. The documented tuple-compatibility contract: a `Rect` compares
    equal to the bare 4-tuple it projects to, on both sides."""
    py, rs = _oracle.Rect(*args), _rs.Rect(*args)
    assert (py == tuple(args)) is (rs == tuple(args)) is True
    assert (py == list(args)) is (rs == list(args)) is True
    assert (py == tuple(args) + (0,)) is (rs == tuple(args) + (0,)) is False


@SETTINGS
@given(args=zone_args())
def test_p5_zone_geometry_agrees(args):
    """P5. width/height/center/area agree bit-for-bit and type-for-type."""
    name, bounds = args
    py, rs = _oracle.Zone(name, bounds), _rs.Zone(name, bounds)
    assert canon(py) == canon(rs)
    assert canon(py.width) == canon(rs.width)
    assert canon(py.height) == canon(rs.height)
    assert canon(py.center) == canon(rs.center)
    assert canon(py.area) == canon(rs.area)


@SETTINGS
@given(args=zone_args(), x=coords, y=coords)
def test_p6_zone_contains_point_agrees(args, x, y):
    """P6. The inclusive point test agrees for arbitrary probes."""
    name, bounds = args
    py, rs = _oracle.Zone(name, bounds), _rs.Zone(name, bounds)
    assert canon_call(py.contains_point, x, y) == canon_call(rs.contains_point, x, y)


def test_p6_is_non_vacuous():
    zone = _rs.Zone("Z", (0.0, 0.0, 1.0, 1.0))
    assert zone.contains_point(0.5, 0.5) is True
    assert zone.contains_point(5.0, 0.5) is False


@SETTINGS
@given(spec=board_spec())
def test_p7_board_construction_and_repr_agree(spec):
    """P7. The whole aggregate -- including `_zone_map` -- agrees."""
    py, rs = _both(spec)
    assert canon(py) == canon(rs)
    assert repr(py) == repr(rs)


@SETTINGS
@given(spec=board_spec())
def test_p8_board_arrays_agree_bit_for_bit_including_dtype(spec):
    """P8. Every float32 surface agrees on dtype, shape and raw bytes."""
    py, rs = _both(spec)
    assert canon(py.get_bounds_array()) == canon(rs.get_bounds_array())
    assert canon(py.get_relative_bounds_array()) == canon(rs.get_relative_bounds_array())
    assert canon(py.polygon_array()) == canon(rs.polygon_array())
    assert py.get_bounds_array().dtype == np.float32


def test_p8_is_non_vacuous():
    """`polygon_array` really returns BOTH `None` and an array."""
    assert _rs.Board(1.0, 2.0).polygon_array() is None
    arr = _rs.Board(1.0, 2.0, outline_polygon=[(0.0, 0.0), (1.0, 1.0)]).polygon_array()
    assert arr is not None and arr.dtype == np.float32


@SETTINGS
@given(spec=board_spec(), x=coords, y=coords)
def test_p9_board_point_queries_agree(spec, x, y):
    """P9. All four point queries agree for arbitrary probes."""
    py, rs = _both(spec)
    assert canon_call(py.contains_point, x, y) == canon_call(rs.contains_point, x, y)
    assert canon_call(py.point_in_keepout, x, y) == canon_call(rs.point_in_keepout, x, y)
    assert canon_call(py.get_zone_for_point, x, y) == canon_call(rs.get_zone_for_point, x, y)
    assert canon_call(py.get_ground_domain, x, y) == canon_call(rs.get_ground_domain, x, y)


def test_p9_is_non_vacuous():
    board = _rs.Board(100.0, 100.0, mounting_holes=[_rs.MountingHole((50.0, 50.0), 3.2)])
    assert board.point_in_keepout(50.0, 50.0) is True
    assert board.point_in_keepout(0.0, 0.0) is False


# ---------------------------------------------------------------------------
# MR1-MR4
# ---------------------------------------------------------------------------


def _rotate_n(board, times: int):
    for _ in range(times):
        board = board.rotated_90()
    return board


@SETTINGS
@given(spec=board_spec(), times=st.integers(min_value=1, max_value=4))
def test_mr1_repeated_rotation_agrees_including_the_degenerate_raise(spec, times):
    """MR1. Rotating N times agrees on BOTH sides -- value or exception.

    `rotated_90` maps a zone's y-bounds through `h - y`, which can collapse a
    rectangle whose y-extent is subnormal into a degenerate one; the oracle
    then raises from `Rect.__post_init__`. That raise is part of the
    contract, so it is compared as a value rather than filtered out.
    """
    py, rs = _both(spec)
    assert canon_call(_rotate_n, py, times) == canon_call(_rotate_n, rs, times)


def test_mr1_is_non_vacuous():
    """Both MR1 outcomes are reachable: a clean rotation, and the degenerate
    raise the property is written to tolerate."""
    ok = _rs.Board(10.0, 20.0, zones=[_rs.Zone("A", (0.0, 0.0, 5.0, 5.0))])
    assert canon_call(_rotate_n, ok, 4)[0] == "ok"
    degenerate = _rs.Board(
        0, 1.0, zones=[_rs.Zone("A", (-1, -8.740327170903494e-236, 0, 0))]
    )
    assert canon_call(_rotate_n, degenerate, 1)[0] == "raised"


@SETTINGS
@given(spec=board_spec())
def test_mr2_four_rotations_restore_the_board_envelope(spec):
    """MR2. When rotation succeeds, four applications are the identity on the
    board envelope, and one application transposes it -- on both sides."""
    py, rs = _both(spec)
    once_py, once_rs = canon_call(_rotate_n, py, 1), canon_call(_rotate_n, rs, 1)
    assert once_py == once_rs
    assume(once_rs[0] == "ok")

    rs1 = rs.rotated_90()
    assert canon(rs1.width) == canon(rs.height)
    assert canon(rs1.height) == canon(rs.width)

    four_py, four_rs = canon_call(_rotate_n, py, 4), canon_call(_rotate_n, rs, 4)
    assert four_py == four_rs
    assume(four_rs[0] == "ok")
    rs4 = _rotate_n(rs, 4)
    assert canon(rs4.width) == canon(rs.width)
    assert canon(rs4.height) == canon(rs.height)


@SETTINGS
@given(args=valid_rect_args())
def test_mr3_from_xywh_and_from_xyxy_agree_on_the_same_rectangle(args):
    """MR3. `from_xywh(x, y, w, h)` and `from_xyxy(x, y, x+w, y+h)` describe
    the same rectangle -- and the two constructors agree across languages."""
    x_min, y_min, x_max, y_max = args
    width, height = float(x_max) - float(x_min), float(y_max) - float(y_min)
    assume(width > 0 and height > 0)
    py_xywh = canon_call(_oracle.Rect.from_xywh, x_min, y_min, width, height)
    rs_xywh = canon_call(_rs.Rect.from_xywh, x_min, y_min, width, height)
    assert py_xywh == rs_xywh
    assert canon_call(_oracle.Rect.from_xyxy, *args) == canon_call(_rs.Rect.from_xyxy, *args)


@SETTINGS
@given(spec=board_spec())
def test_mr4_build_indices_is_idempotent_and_zone_order_decides_collisions(spec):
    """MR4. Rebuilding `_zone_map` is a no-op; and when two zones share a
    name the LAST one wins -- so reversing the zone list changes the map in
    exactly the same way on both sides."""
    py, rs = _both(spec)
    before_py, before_rs = canon(py), canon(rs)
    py.build_indices()
    rs.build_indices()
    assert canon(py) == before_py
    assert canon(rs) == before_rs

    py.zones = list(reversed(py.zones))
    rs.zones = list(reversed(rs.zones))
    py.build_indices()
    rs.build_indices()
    assert canon(py._zone_map) == canon(rs._zone_map)


def test_mr4_is_non_vacuous():
    """Name collisions really are resolved last-wins, so MR4's reversal
    assertion is testing something."""
    a, b = _rs.Zone("Z", (0, 0, 1, 1)), _rs.Zone("Z", (0, 0, 2, 2))
    board = _rs.Board(10.0, 10.0, zones=[a, b])
    assert board.get_zone("Z") is b
    board.zones = [b, a]
    board.build_indices()
    assert board.get_zone("Z") is a


# ---------------------------------------------------------------------------
# LayerStackup
# ---------------------------------------------------------------------------


@SETTINGS
@given(grid_size=finite, net_class=st.sampled_from(["Signal", "Power", "HighVoltage", "Other"]))
def test_tracks_per_cell_agrees_bit_for_bit(grid_size, net_class):
    """IEEE-754 division and multiplication in the same association order."""
    py = _oracle.LayerStackup.default_4layer()
    rs = _rs.LayerStackup.default_4layer()
    assert canon_call(py.tracks_per_cell, grid_size, net_class) == canon_call(
        rs.tracks_per_cell, grid_size, net_class
    )


@SETTINGS
@given(idx=st.integers(min_value=-10, max_value=10))
def test_is_plane_layer_agrees(idx):
    py = _oracle.LayerStackup.default_4layer()
    rs = _rs.LayerStackup.default_4layer()
    assert canon_call(py.is_plane_layer, idx) == canon_call(rs.is_plane_layer, idx)


def test_is_plane_layer_is_non_vacuous():
    rs = _rs.LayerStackup.default_4layer()
    assert [rs.is_plane_layer(i) for i in range(4)] == [False, True, True, False]
