"""Differential test: Rust board pyclasses vs the pinned Python oracle.

Wave 4, **Phase 3, candidate 1** (plan
``docs/plans/2026-08-02-001-feat-wave4-phase3-formats-io-plan.md``). The
pyo3 pyclasses in ``temper_design_bundle_python.board_contracts`` must
reproduce the pre-migration ``temper_placer/core/board.py``
bit-identically. That implementation is pinned VERBATIM as the oracle
(``_board_py_oracle.py``, commit ``5a17025b1``).

See ``test_netlist_rust_differential.py`` for the comparison convention.
The board-specific hazards this file is built around:

* ``Rect`` does **no** coercion in ``__init__`` but ``from_xyxy``/
  ``from_xywh``/``coerce`` call ``float()`` — so ``Rect(0, 0, 1, 1).width``
  is ``int`` ``1`` while ``Rect.from_xyxy(0, 0, 1, 1).width`` is ``1.0``.
  Both are asserted with type-carrying canonicalization.
* ``Zone.__post_init__`` coerces ``bounds`` to ``Rect``, but a *later*
  ``zone.bounds = (...)`` assignment does not (there is no setter hook on a
  dataclass). ``deterministic/feedback/orchestrator.py`` relies on that.
* ``Board._zone_map`` is ``init=False`` yet appears in BOTH ``__repr__`` and
  ``__eq__``.
* ``LayerStackup`` is hashable only when empty — ``Layer`` is a non-frozen
  dataclass, so ``hash()`` of a populated stackup raises ``TypeError``.
* ``polygon_array`` / ``get_bounds_array`` / ``get_relative_bounds_array``
  are ``float32``; a widened ``f64`` round-trip fails on dtype here.
"""

from __future__ import annotations

import numpy as np
import pytest
import temper_design_bundle_python as _tdb

import tests.core._board_py_oracle as _oracle
from tests.core._contract_canon import canon, canon_call

# Rust symbols under test -- must exist or this file fails to collect (RED).
_rs = _tdb.board_contracts
RS_MOUNTING_HOLE = _rs.MountingHole
RS_PAD = _rs.Pad
RS_COMPONENT = _rs.Component
RS_TRACE = _rs.Trace
RS_VIA = _rs.Via
RS_LAYER = _rs.Layer
RS_LAYER_STACKUP = _rs.LayerStackup
RS_RECT = _rs.Rect
RS_ZONE = _rs.Zone
RS_GROUND_DOMAIN = _rs.GroundDomain
RS_BOARD = _rs.Board
RS_SIDE_TO_LAYER_NAME = _rs.side_to_layer_name


def _pair(py_cls, rs_cls, *args, **kwargs):
    """Construct the same arguments on both sides."""
    return py_cls(*args, **kwargs), rs_cls(*args, **kwargs)


# ---------------------------------------------------------------------------
# Leaf dataclasses
# ---------------------------------------------------------------------------

MOUNTING_HOLE_ARGS = [
    (((5.0, 5.0), 3.2), {}),
    (((5, 5), 3.2), {}),  # int position must stay int
    (((0.0, 0.0), 1, 0), {}),  # int diameter / zero keepout
    (((1e-8, -1e-8), 5e-324), {"keepout_radius": float("inf")}),
]

PAD_ARGS = [
    (((0.0, 0.0), (1.0, 0.5)), {}),
    (((0, 0), (1, 2)), {"shape": "oval", "layer": "B.Cu", "number": "7", "net_name": "GND"}),
]

BOARD_COMPONENT_ARGS = [
    (("U1", (1.0, 2.0), 90.0, 5.0, 5.0), {}),
    (("R1", (1, 2), 0, 3, 4), {"footprint": "R_0402", "layer": "B.Cu", "fixed": True}),
]

TRACE_ARGS = [
    (((0.0, 0.0), (1.0, 1.0), 0.25, "F.Cu"), {}),
    (((0, 0), (1, 1), 1, "B.Cu"), {"net": "GND"}),
]

VIA_ARGS = [
    (((0.0, 0.0), 0.3, 0.6), {}),
    (((1, 2), 1, 2), {"layers": ("F.Cu", "In1.Cu", "B.Cu"), "net": "VCC", "is_diff_pair": True}),
]

LAYER_ARGS = [
    (("F.Cu", "signal"), {}),
    (("In1.Cu", "plane"), {"copper_weight": 2, "is_routable": False}),
]


@pytest.mark.parametrize(
    "py_cls,rs_cls,corpus",
    [
        (_oracle.MountingHole, RS_MOUNTING_HOLE, MOUNTING_HOLE_ARGS),
        (_oracle.Pad, RS_PAD, PAD_ARGS),
        (_oracle.Component, RS_COMPONENT, BOARD_COMPONENT_ARGS),
        (_oracle.Trace, RS_TRACE, TRACE_ARGS),
        (_oracle.Via, RS_VIA, VIA_ARGS),
        (_oracle.Layer, RS_LAYER, LAYER_ARGS),
    ],
    ids=["MountingHole", "Pad", "Component", "Trace", "Via", "Layer"],
)
def test_leaf_dataclass_construction_and_repr_identical(py_cls, rs_cls, corpus):
    for args, kwargs in corpus:
        py, rs = _pair(py_cls, rs_cls, *args, **kwargs)
        assert canon(py) == canon(rs)
        assert repr(py) == repr(rs)


@pytest.mark.parametrize(
    "py_cls,rs_cls,corpus",
    [
        (_oracle.MountingHole, RS_MOUNTING_HOLE, MOUNTING_HOLE_ARGS),
        (_oracle.Pad, RS_PAD, PAD_ARGS),
        (_oracle.Trace, RS_TRACE, TRACE_ARGS),
        (_oracle.Via, RS_VIA, VIA_ARGS),
        (_oracle.Layer, RS_LAYER, LAYER_ARGS),
    ],
    ids=["MountingHole", "Pad", "Trace", "Via", "Layer"],
)
def test_leaf_dataclass_equality_identical(py_cls, rs_cls, corpus):
    """Equality must agree pairwise across the WHOLE corpus.

    Comparing only corpus[0] vs corpus[1] was not enough: for `MountingHole`
    those two differ solely by `(5.0, 5.0)` vs `(5, 5)`, which Python
    considers *equal*. Driving every ordered pair through both sides makes
    the assertion independent of the corpus ordering.
    """
    py_matrix, rs_matrix = [], []
    for a, ak in corpus:
        for b, bk in corpus:
            py_matrix.append(py_cls(*a, **ak) == py_cls(*b, **bk))
            rs_matrix.append(rs_cls(*a, **ak) == rs_cls(*b, **bk))
    assert py_matrix == rs_matrix
    # Self-equality is present on the diagonal, so the matrix is non-vacuous.
    assert any(py_matrix) and not all(py_matrix)
    a, ak = corpus[0]
    for cls in (py_cls, rs_cls):
        assert (cls(*a, **ak) == object()) is False


@pytest.mark.parametrize(
    "py_cls,rs_cls,corpus",
    [(_oracle.Trace, RS_TRACE, TRACE_ARGS), (_oracle.Via, RS_VIA, VIA_ARGS)],
    ids=["Trace", "Via"],
)
def test_frozen_dataclasses_hash_and_reject_mutation_identically(py_cls, rs_cls, corpus):
    """`Trace`/`Via` are `frozen=True`: hashable, and assignment raises
    `dataclasses.FrozenInstanceError` with an exact message."""
    for args, kwargs in corpus:
        py, rs = _pair(py_cls, rs_cls, *args, **kwargs)
        assert hash(py) == hash(rs)
        field = "width"
        py_out = canon_call(setattr, py, field, 99.0)
        rs_out = canon_call(setattr, rs, field, 99.0)
        assert py_out == rs_out
        assert py_out[0] == "raised"
        assert canon_call(delattr, py, field) == canon_call(delattr, rs, field)


def test_frozen_instances_are_usable_as_set_members():
    """Hash parity has to hold structurally, not just numerically."""
    args, kwargs = VIA_ARGS[0]
    py, rs = _pair(_oracle.Via, RS_VIA, *args, **kwargs)
    assert len({py, _oracle.Via(*args, **kwargs)}) == 1
    assert len({rs, RS_VIA(*args, **kwargs)}) == 1


# ---------------------------------------------------------------------------
# Rect -- the type-preservation centrepiece
# ---------------------------------------------------------------------------

RECT_ARGS = [
    (0.0, 0.0, 1.0, 1.0),
    (0, 0, 1, 1),  # ints stay ints through __init__
    (-5.5, -2.25, 5.5, 2.25),
    (0.0, 0.0, 5e-324, 5e-324),  # smallest positive subnormal extent
    (-1e308, -1e308, 1e308, 1e308),
]

RECT_INVALID = [
    (1, 0, 0, 1),  # x_max < x_min
    (0.0, 0.0, 0.0, 1.0),  # degenerate in x
    (0.0, 1.0, 1.0, 1.0),  # degenerate in y
    (0.0, 5.0, 1.0, 2.0),  # y inverted
]


@pytest.mark.parametrize("args", RECT_ARGS)
def test_rect_direct_construction_preserves_types(args):
    py, rs = _pair(_oracle.Rect, RS_RECT, *args)
    assert canon(py) == canon(rs)
    assert repr(py) == repr(rs)
    assert canon(py.width) == canon(rs.width)
    assert canon(py.height) == canon(rs.height)


def test_rect_int_construction_really_keeps_int():
    """Anchors the property the canonicalizer exists to protect."""
    assert isinstance(RS_RECT(0, 0, 1, 1).width, int)
    assert isinstance(_oracle.Rect(0, 0, 1, 1).width, int)
    assert isinstance(RS_RECT.from_xyxy(0, 0, 1, 1).width, float)


@pytest.mark.parametrize("args", RECT_ARGS)
def test_rect_from_xyxy_identical(args):
    assert canon_call(_oracle.Rect.from_xyxy, *args) == canon_call(RS_RECT.from_xyxy, *args)


@pytest.mark.parametrize(
    "args",
    [(0, 0, 1, 1), (0.0, 0.0, 2.5, 4.0), (10, 20, 5, 5), (-1.5, -2.5, 3.0, 4.0)],
)
def test_rect_from_xywh_identical(args):
    assert canon_call(_oracle.Rect.from_xywh, *args) == canon_call(RS_RECT.from_xywh, *args)


@pytest.mark.parametrize("args", RECT_INVALID)
def test_rect_invariant_violations_raise_identically(args):
    """Error type AND message text must match exactly."""
    py_out = canon_call(_oracle.Rect, *args)
    rs_out = canon_call(RS_RECT, *args)
    assert py_out == rs_out
    assert py_out[0] == "raised"
    assert py_out[1] == "ValueError"


@pytest.mark.parametrize(
    "value",
    [(0, 0, 1, 1), [0.0, 0.0, 2.0, 3.0], (0.0, 0.0, 1.0, 1.0), (1, 1, 0, 0), (0, 0, 1)],
)
def test_rect_coerce_identical(value):
    assert canon_call(_oracle.Rect.coerce, value) == canon_call(RS_RECT.coerce, value)


def test_rect_coerce_passes_through_existing_rect_by_identity():
    for cls in (_oracle.Rect, RS_RECT):
        r = cls(0.0, 0.0, 1.0, 1.0)
        assert cls.coerce(r) is r


@pytest.mark.parametrize("args", RECT_ARGS)
def test_rect_sequence_protocol_identical(args):
    py, rs = _pair(_oracle.Rect, RS_RECT, *args)
    assert len(py) == len(rs)
    assert canon(tuple(py)) == canon(tuple(rs))
    for index in (0, 1, 2, 3, -1, -4):
        assert canon_call(py.__getitem__, index) == canon_call(rs.__getitem__, index)
    for bad in (4, -5, 99):
        assert canon_call(py.__getitem__, bad) == canon_call(rs.__getitem__, bad)
    # Unpacking is what most call sites actually do.
    a, b, c, d = py
    w, x, y, z = rs
    assert canon((a, b, c, d)) == canon((w, x, y, z))


def test_rect_equality_and_hash_identical():
    """`Rect.__eq__` deliberately compares equal to a bare 4-tuple/list."""
    py, rs = _pair(_oracle.Rect, RS_RECT, 0.0, 0.0, 1.0, 1.0)
    for other in [
        (0.0, 0.0, 1.0, 1.0),
        [0.0, 0.0, 1.0, 1.0],
        (0.0, 0.0, 1.0, 2.0),
        (0.0, 0.0, 1.0),
        (0.0, 0.0, 1.0, 1.0, 5.0),
        "nope",
        object(),
        None,
    ]:
        assert (py == other) == (rs == other), f"equality diverged for {other!r}"
        assert (py != other) == (rs != other)
    assert (py == _oracle.Rect(0.0, 0.0, 1.0, 1.0)) is True
    assert (rs == RS_RECT(0.0, 0.0, 1.0, 1.0)) is True
    assert hash(py) == hash(rs) == hash((0.0, 0.0, 1.0, 1.0))


def test_rect_eq_returns_notimplemented_for_foreign_types():
    py, rs = _pair(_oracle.Rect, RS_RECT, 0.0, 0.0, 1.0, 1.0)
    assert py.__eq__("x") is NotImplemented
    assert rs.__eq__("x") is NotImplemented


def test_rect_is_frozen_identically():
    py, rs = _pair(_oracle.Rect, RS_RECT, 0.0, 0.0, 1.0, 1.0)
    assert canon_call(setattr, py, "x_min", 9.0) == canon_call(setattr, rs, "x_min", 9.0)
    assert canon_call(delattr, py, "x_min") == canon_call(delattr, rs, "x_min")


# ---------------------------------------------------------------------------
# LayerStackup
# ---------------------------------------------------------------------------


def test_layer_stackup_defaults_identical():
    py, rs = _pair(_oracle.LayerStackup, RS_LAYER_STACKUP)
    assert canon(py) == canon(rs)
    assert repr(py) == repr(rs)
    assert hash(py) == hash(rs)


def test_layer_stackup_default_4layer_identical():
    py, rs = _oracle.LayerStackup.default_4layer(), RS_LAYER_STACKUP.default_4layer()
    assert canon(py) == canon(rs)
    assert repr(py) == repr(rs)


def test_layer_stackup_populated_is_unhashable_identically():
    """`Layer` is a non-frozen dataclass -> `__hash__ = None` -> hashing a
    populated stackup raises TypeError. A Rust hash that "worked" would be a
    silent behaviour change."""
    py, rs = _oracle.LayerStackup.default_4layer(), RS_LAYER_STACKUP.default_4layer()
    assert canon_call(hash, py) == canon_call(hash, rs)
    assert canon_call(hash, py)[0] == "raised"


@pytest.mark.parametrize("idx", [-1, 0, 1, 2, 3, 4, 99, 1.5, 2.5, True])
def test_layer_stackup_is_plane_layer_identical(idx):
    """Int indexes (in- and out-of-range, negatives), float indexes and bools.

    The float cases pin the tuple-indexing error text: the oracle's guard
    `0 <= 1.5 < len` passes, so `self.layers[1.5]` is reached and raises
    `TypeError: tuple indices must be integers or slices, not float`. The
    out-of-range ints (4, 99, -1) fail the guard and return False without
    ever reaching the index — the Rust must not raise IndexError there.
    """
    py, rs = _oracle.LayerStackup.default_4layer(), RS_LAYER_STACKUP.default_4layer()
    assert canon_call(py.is_plane_layer, idx) == canon_call(rs.is_plane_layer, idx)
    empty_py, empty_rs = _pair(_oracle.LayerStackup, RS_LAYER_STACKUP)
    assert canon_call(empty_py.is_plane_layer, idx) == canon_call(empty_rs.is_plane_layer, idx)


@pytest.mark.parametrize("net_class", ["Signal", "Power", "HighVoltage", "Unknown", ""])
def test_layer_stackup_routable_layers_identical(net_class):
    py, rs = _oracle.LayerStackup.default_4layer(), RS_LAYER_STACKUP.default_4layer()
    assert canon(py.routable_layers(net_class)) == canon(rs.routable_layers(net_class))
    assert canon(py.routable_layers()) == canon(rs.routable_layers())


@pytest.mark.parametrize("grid_size", [1.0, 0.5, 3, 0.001, 1e6])
@pytest.mark.parametrize("net_class", ["Signal", "Power", "HighVoltage"])
def test_layer_stackup_tracks_per_cell_identical(grid_size, net_class):
    """Bit-exact float division, compared as `float.hex()`."""
    py, rs = _oracle.LayerStackup.default_4layer(), RS_LAYER_STACKUP.default_4layer()
    assert canon(py.tracks_per_cell(grid_size, net_class)) == canon(
        rs.tracks_per_cell(grid_size, net_class)
    )
    assert canon(py.tracks_per_cell(grid_size)) == canon(rs.tracks_per_cell(grid_size))


def test_layer_stackup_is_frozen_identically():
    py, rs = _pair(_oracle.LayerStackup, RS_LAYER_STACKUP)
    assert canon_call(setattr, py, "thickness", 2.0) == canon_call(setattr, rs, "thickness", 2.0)


def test_layer_stackup_test_only_2layer_identical_from_a_test_file():
    """The oracle inspects its CALLER's filename via `sys._getframe(1)`; the
    Rust classmethod has no Python frame of its own and uses `_getframe(0)`.
    Called from this test file, both must succeed and warn identically."""
    with pytest.warns(UserWarning) as py_rec:
        py = _oracle.LayerStackup._test_only_2layer()
    with pytest.warns(UserWarning) as rs_rec:
        rs = RS_LAYER_STACKUP._test_only_2layer()
    assert canon(py) == canon(rs)
    assert [str(w.message) for w in py_rec] == [str(w.message) for w in rs_rec]


def test_layer_stackup_test_only_2layer_refuses_non_test_callers_identically():
    """Drive both sides from a synthetic frame whose filename is NOT a test
    path, and require the same RuntimeError text (modulo the filename, which
    is the caller's and therefore identical for both)."""
    source = "def call(fn):\n    return fn()\n"
    namespace: dict = {}
    exec(compile(source, "/opt/production/pipeline.py", "exec"), namespace)  # noqa: S102
    call = namespace["call"]
    py_out = canon_call(call, _oracle.LayerStackup._test_only_2layer)
    rs_out = canon_call(call, RS_LAYER_STACKUP._test_only_2layer)
    assert py_out == rs_out
    assert py_out[0] == "raised"
    assert py_out[1] == "RuntimeError"
    assert "/opt/production/pipeline.py" in py_out[2]


# ---------------------------------------------------------------------------
# Zone
# ---------------------------------------------------------------------------

ZONE_ARGS = [
    (("Z", (0, 0, 1, 1)), {}),
    (("Z", (0.0, 0.0, 50.0, 80.0)), {}),
    (
        ("HV", (0, 0, 10, 10)),
        {
            "net_classes": ["HighVoltage"],
            "components": ["Q1", "Q2"],
            "weight": 2,
            "polygon": [(0.0, 0.0), (10.0, 0.0), (5.0, 10.0)],
            "layers": ["F.Cu", "B.Cu"],
            "max_size": (20.0, 20.0),
            "can_expand": ["up", "left"],
            "zone_type": "keepout",
        },
    ),
]


@pytest.mark.parametrize("args,kwargs", ZONE_ARGS)
def test_zone_construction_and_repr_identical(args, kwargs):
    py, rs = _pair(_oracle.Zone, RS_ZONE, *args, **kwargs)
    assert canon(py) == canon(rs)
    assert repr(py) == repr(rs)


@pytest.mark.parametrize("args,kwargs", ZONE_ARGS)
def test_zone_geometry_properties_identical(args, kwargs):
    py, rs = _pair(_oracle.Zone, RS_ZONE, *args, **kwargs)
    assert canon(py.width) == canon(rs.width)
    assert canon(py.height) == canon(rs.height)
    assert canon(py.center) == canon(rs.center)
    assert canon(py.area) == canon(rs.area)


def test_zone_bounds_are_coerced_to_rect_at_construction():
    py, rs = _pair(_oracle.Zone, RS_ZONE, "Z", (0, 0, 1, 1))
    assert type(py.bounds).__name__ == "Rect"
    assert type(rs.bounds).__name__ == "Rect"
    # ...and the coercion floats them, unlike direct Rect construction.
    assert canon(py.bounds) == canon(rs.bounds)
    assert isinstance(rs.bounds.x_min, float)


def test_zone_bounds_assignment_does_not_recoerce():
    """`__post_init__` runs once. `orchestrator.py` assigns raw tuples and
    the attribute must stay a tuple -- re-coercing would be a behaviour
    change (and would reject the inverted intermediates it writes)."""
    py, rs = _pair(_oracle.Zone, RS_ZONE, "Z", (0, 0, 1, 1))
    for zone in (py, rs):
        zone.bounds = (0, 0, 2, 2)
    assert type(py.bounds) is tuple
    assert type(rs.bounds) is tuple
    assert canon(py.bounds) == canon(rs.bounds)
    assert canon(py.width) == canon(rs.width)


def test_zone_invalid_bounds_raise_identically():
    for bad in [(1, 0, 0, 1), (0, 0, 0, 1), (0, 0, 1)]:
        assert canon_call(_oracle.Zone, "Z", bad) == canon_call(RS_ZONE, "Z", bad)


@pytest.mark.parametrize(
    "point", [(0.0, 0.0), (0.5, 0.5), (1.0, 1.0), (1.5, 0.5), (-0.1, 0.5), (0, 0)]
)
def test_zone_contains_point_identical(point):
    py, rs = _pair(_oracle.Zone, RS_ZONE, "Z", (0.0, 0.0, 1.0, 1.0))
    assert canon_call(py.contains_point, *point) == canon_call(rs.contains_point, *point)


def test_zone_default_containers_are_fresh_per_instance():
    for cls in (_oracle.Zone, RS_ZONE):
        a, b = cls("A", (0, 0, 1, 1)), cls("B", (0, 0, 1, 1))
        a.net_classes.append("X")
        a.components.append("Y")
        a.can_expand.append("Z")
        assert b.net_classes == ["Signal"]
        assert b.components == []
        assert b.can_expand == ["up", "down", "left", "right"]


# ---------------------------------------------------------------------------
# GroundDomain
# ---------------------------------------------------------------------------


def test_ground_domain_construction_and_repr_identical():
    for args, kwargs in [
        (("PGND", (0, 0, 50, 150)), {}),
        (("CGND", (0.0, 0.0, 1.0, 1.0)), {"star_point": (50, 75)}),
    ]:
        py, rs = _pair(_oracle.GroundDomain, RS_GROUND_DOMAIN, *args, **kwargs)
        assert canon(py) == canon(rs)
        assert repr(py) == repr(rs)


def test_ground_domain_bounds_are_not_coerced_to_rect():
    """Unlike `Zone`, `GroundDomain` keeps the raw tuple."""
    py, rs = _pair(_oracle.GroundDomain, RS_GROUND_DOMAIN, "G", (0, 0, 1, 1))
    assert type(py.bounds) is tuple
    assert type(rs.bounds) is tuple


@pytest.mark.parametrize("point", [(0.0, 0.0), (0.5, 0.5), (1.0, 1.0), (2.0, 0.5)])
def test_ground_domain_contains_point_identical(point):
    py, rs = _pair(_oracle.GroundDomain, RS_GROUND_DOMAIN, "G", (0.0, 0.0, 1.0, 1.0))
    assert canon_call(py.contains_point, *point) == canon_call(rs.contains_point, *point)


# ---------------------------------------------------------------------------
# Board
# ---------------------------------------------------------------------------


def _rich_board(zone_cls, hole_cls, ground_cls, board_cls):
    return board_cls(
        width=100.0,
        height=150.0,
        origin=(1.5, -2.5),
        zones=[
            zone_cls("HV_ZONE", (0, 0, 50, 80), zone_type="keepout"),
            zone_cls("MCU_ZONE", (0, 80, 100, 130), polygon=[(0.0, 80.0), (100.0, 130.0)]),
        ],
        mounting_holes=[hole_cls((5, 5), 3.2), hole_cls((95.0, 145.0), 3.2, 4.0)],
        keepouts=[(1.0, 1.0, 2.0, 2.0), (10, 10, 20, 20)],
        ground_domains=[ground_cls("PGND", (0, 0, 50, 150), star_point=(50, 75))],
        outline_polygon=[(0.0, 0.0), (100.0, 0.0), (100.0, 150.0), (0.0, 150.0)],
    )


def _py_board():
    return _rich_board(_oracle.Zone, _oracle.MountingHole, _oracle.GroundDomain, _oracle.Board)


def _rs_board():
    return _rich_board(RS_ZONE, RS_MOUNTING_HOLE, RS_GROUND_DOMAIN, RS_BOARD)


def test_board_minimal_construction_identical():
    py, rs = _pair(_oracle.Board, RS_BOARD, 1.0, 2.0)
    assert canon(py) == canon(rs)
    assert repr(py) == repr(rs)


def test_board_repr_includes_zone_map():
    """`_zone_map` is `init=False` but `repr=True` -- easy to drop silently."""
    assert "_zone_map=" in repr(RS_BOARD(1.0, 2.0))
    assert "_zone_map=" in repr(_oracle.Board(1.0, 2.0))


def test_board_int_dimensions_preserve_type_through_area():
    py, rs = _pair(_oracle.Board, RS_BOARD, 3, 4)
    assert canon(py.area) == canon(rs.area)
    assert isinstance(rs.area, int)


def test_board_rich_construction_identical():
    assert canon(_py_board()) == canon(_rs_board())
    assert repr(_py_board()) == repr(_rs_board())


def test_board_default_stackup_is_applied_identically():
    py, rs = _pair(_oracle.Board, RS_BOARD, 1.0, 2.0)
    assert canon(py.layer_stackup) == canon(rs.layer_stackup)
    assert len(rs.layer_stackup.layers) == 4


def test_board_rejects_non_4layer_stackup_identically():
    for layers in [
        (),
        (_oracle.Layer("a", "signal"),),
        tuple(_oracle.Layer(f"L{i}", "signal") for i in range(5)),
    ]:
        rs_layers = tuple(RS_LAYER(ly.name, ly.layer_type) for ly in layers)
        py_out = canon_call(_oracle.Board, 1.0, 2.0, layer_stackup=_oracle.LayerStackup(layers))
        rs_out = canon_call(RS_BOARD, 1.0, 2.0, layer_stackup=RS_LAYER_STACKUP(rs_layers))
        assert py_out == rs_out, f"stackup arity {len(layers)} diverged"


def test_board_empty_stackup_tuple_falls_back_to_default():
    """`LayerStackup(())` is truthy but has 0 layers -> must RAISE, not
    silently default. (`if not self.layer_stackup` tests the *stackup*, not
    its layer count.)"""
    assert canon_call(_oracle.Board, 1.0, 2.0, layer_stackup=_oracle.LayerStackup())[0] == "raised"
    assert canon_call(RS_BOARD, 1.0, 2.0, layer_stackup=RS_LAYER_STACKUP())[0] == "raised"


def test_board_zone_map_and_get_zone_identical():
    py, rs = _py_board(), _rs_board()
    for name in ("HV_ZONE", "MCU_ZONE", "ABSENT"):
        assert canon_call(py.get_zone, name) == canon_call(rs.get_zone, name)


def test_board_zones_list_is_shared_by_identity():
    """`cli/__init__.py` reassigns `board.zones`; other code appends to it."""
    for zone_cls, board_cls in ((_oracle.Zone, _oracle.Board), (RS_ZONE, RS_BOARD)):
        board = board_cls(10.0, 10.0)
        board.zones.append(zone_cls("Z", (0, 0, 1, 1)))
        assert len(board.zones) == 1
        # ...but `_zone_map` is stale until `build_indices()` is called, in
        # both implementations.
        assert canon_call(board.get_zone, "Z")[0] == "raised"
        board.build_indices()
        assert canon_call(board.get_zone, "Z")[0] == "ok"


def test_board_zones_accepts_duck_typed_objects():
    """`cli/__init__.py:419` assigns a list of anonymous `type("Zone", (), ...)`
    instances. A typed `Vec<Zone>` field would reject them."""
    duck = type("Zone", (), {"name": "duck", "bounds": (0, 0, 1, 1), "components": []})()
    for board_cls in (_oracle.Board, RS_BOARD):
        board = board_cls(10.0, 10.0)
        board.zones = [duck]
        board.build_indices()
        assert board.get_zone("duck") is duck


@pytest.mark.parametrize("point", [(0.0, 0.0), (25.0, 40.0), (99.0, 149.0), (200.0, 0.0)])
def test_board_point_queries_identical(point):
    py, rs = _py_board(), _rs_board()
    assert canon_call(py.contains_point, *point) == canon_call(rs.contains_point, *point)
    assert canon_call(py.point_in_keepout, *point) == canon_call(rs.point_in_keepout, *point)
    assert canon_call(py.get_zone_for_point, *point) == canon_call(rs.get_zone_for_point, *point)
    assert canon_call(py.get_ground_domain, *point) == canon_call(rs.get_ground_domain, *point)


def test_undeclared_attributes_can_be_attached_like_on_a_dataclass():
    """A dataclass is an ordinary Python class with a `__dict__`, and callers
    exploit that: `validation/trace_analyzer.py` and
    `visualization/board_renderer.py` both read `board.traces` -- a field no
    `Board` definition declares, injected by the KiCad parse path.

    A pyclass without `dict` raises `AttributeError` on the assignment. This
    regression was found by the consumer suite, not by the contract
    differential, so it is pinned here.
    """
    for board_cls in (_oracle.Board, RS_BOARD):
        board = board_cls(1.0, 2.0)
        assert canon_call(getattr, board, "traces")[0] == "raised"
        board.traces = ["sentinel"]
        assert board.traces == ["sentinel"]
        del board.traces
        assert canon_call(getattr, board, "traces")[0] == "raised"


@pytest.mark.parametrize(
    "py_cls,rs_cls,args",
    [
        (_oracle.Zone, RS_ZONE, ("Z", (0, 0, 1, 1))),
        (_oracle.MountingHole, RS_MOUNTING_HOLE, ((0.0, 0.0), 1.0)),
        (_oracle.Layer, RS_LAYER, ("F.Cu", "signal")),
        (_oracle.GroundDomain, RS_GROUND_DOMAIN, ("G", (0, 0, 1, 1))),
        (_oracle.Component, RS_COMPONENT, ("U1", (0.0, 0.0), 0.0, 1.0, 1.0)),
        (_oracle.Pad, RS_PAD, ((0.0, 0.0), (1.0, 1.0))),
    ],
    ids=["Zone", "MountingHole", "Layer", "GroundDomain", "Component", "Pad"],
)
def test_mutable_contracts_accept_undeclared_attributes(py_cls, rs_cls, args):
    for cls in (py_cls, rs_cls):
        obj = cls(*args)
        obj._injected = 7
        assert obj._injected == 7


@pytest.mark.parametrize(
    "py_cls,rs_cls,args",
    [
        (_oracle.Trace, RS_TRACE, ((0.0, 0.0), (1.0, 1.0), 0.25, "F.Cu")),
        (_oracle.Via, RS_VIA, ((0.0, 0.0), 0.3, 0.6)),
        (_oracle.Rect, RS_RECT, (0.0, 0.0, 1.0, 1.0)),
        (_oracle.LayerStackup, RS_LAYER_STACKUP, ()),
    ],
    ids=["Trace", "Via", "Rect", "LayerStackup"],
)
def test_frozen_contracts_reject_undeclared_attributes_identically(py_cls, rs_cls, args):
    """`frozen=True` blocks assignment of ANY name, declared or not."""
    py, rs = py_cls(*args), rs_cls(*args)
    assert canon_call(setattr, py, "_injected", 7) == canon_call(setattr, rs, "_injected", 7)
    assert canon_call(setattr, py, "_injected", 7)[0] == "raised"


def test_board_keepout_regions_alias_is_the_same_list_object():
    for board_cls in (_oracle.Board, RS_BOARD):
        board = board_cls(1.0, 2.0)
        assert board.keepout_regions is board.keepouts


def test_board_has_polygon_outline_identical():
    for outline in (None, [], [(0.0, 0.0)], [(0.0, 0.0), (1.0, 0.0)], [(0, 0), (1, 0), (1, 1)]):
        py = _oracle.Board(1.0, 2.0, outline_polygon=outline)
        rs = RS_BOARD(1.0, 2.0, outline_polygon=outline)
        assert canon(py.has_polygon_outline) == canon(rs.has_polygon_outline)


def test_board_polygon_array_is_bit_identical_including_dtype():
    for outline in (None, [], [(0.0, 0.0), (1.0, 0.0), (1.0, 2.0)], [(0, 0), (1, 0), (1, 2)]):
        py = _oracle.Board(1.0, 2.0, outline_polygon=outline).polygon_array()
        rs = RS_BOARD(1.0, 2.0, outline_polygon=outline).polygon_array()
        assert canon(py) == canon(rs)
        if py is not None:
            assert py.dtype == np.float32


def test_board_bounds_arrays_are_bit_identical_including_dtype():
    py, rs = _py_board(), _rs_board()
    assert canon(py.get_bounds_array()) == canon(rs.get_bounds_array())
    assert canon(py.get_relative_bounds_array()) == canon(rs.get_relative_bounds_array())
    assert py.get_bounds_array().dtype == np.float32
    assert rs.get_bounds_array().dtype == np.float32


def test_board_from_polygon_identical():
    for polygon in [
        [(0.0, 0.0), (10.0, 0.0), (10.0, 20.0)],
        [(0, 0), (10, 0), (10, 20)],  # ints -> int width/height
        [(-5.5, -1.5), (5.5, 1.5)],
    ]:
        assert canon_call(_oracle.Board.from_polygon, polygon) == canon_call(
            RS_BOARD.from_polygon, polygon
        )
        assert canon_call(_oracle.Board.from_polygon, polygon, (1.0, 2.0)) == canon_call(
            RS_BOARD.from_polygon, polygon, (1.0, 2.0)
        )


def test_board_temper_default_identical():
    py, rs = _oracle.Board.temper_default(), RS_BOARD.temper_default()
    assert canon(py) == canon(rs)
    assert repr(py) == repr(rs)


def test_board_rotated_90_identical():
    py, rs = _py_board().rotated_90(), _rs_board().rotated_90()
    assert canon(py) == canon(rs)
    assert repr(py) == repr(rs)


def test_board_rotated_90_of_temper_default_identical():
    assert canon(_oracle.Board.temper_default().rotated_90()) == canon(
        RS_BOARD.temper_default().rotated_90()
    )


def test_board_rotated_90_drops_zone_type_identically():
    """The oracle's `rotated_90` rebuilds zones WITHOUT `zone_type`, so a
    'keepout' zone silently becomes 'placement'. Preserved, not fixed."""
    assert _py_board().rotated_90().zones[0].zone_type == "placement"
    assert _rs_board().rotated_90().zones[0].zone_type == "placement"


def test_board_rotated_90_twice_identical():
    assert canon(_py_board().rotated_90().rotated_90()) == canon(
        _rs_board().rotated_90().rotated_90()
    )


def test_board_equality_identical():
    for cls_set in ((_oracle.Zone, _oracle.MountingHole, _oracle.GroundDomain, _oracle.Board),
                    (RS_ZONE, RS_MOUNTING_HOLE, RS_GROUND_DOMAIN, RS_BOARD)):
        a = _rich_board(*cls_set)
        b = _rich_board(*cls_set)
        assert a == b
        assert (a == object()) is False
        b.width = 999.0
        assert a != b


# ---------------------------------------------------------------------------
# side_to_layer_name
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("side", [0, 1, 2, -1, True, False, "0", None, 0.0, 1.0])
def test_side_to_layer_name_identical(side):
    """`side == 0` is a value comparison, so `False`/`0.0` also map to F.Cu --
    preserved rather than tightened."""
    assert canon_call(_oracle.side_to_layer_name, side) == canon_call(
        RS_SIDE_TO_LAYER_NAME, side
    )


# ---------------------------------------------------------------------------
# Delegation + the R3 carve-out
# ---------------------------------------------------------------------------


def test_dataclasses_replace_works_on_the_public_contracts():
    """The deterministic stages rebuild board-side contracts with `replace`."""
    import dataclasses

    from temper_placer.core import board as public

    for py_obj, rs_obj, changes in [
        (
            _oracle.Zone("Z", (0, 0, 1, 1)),
            public.Zone("Z", (0, 0, 1, 1)),
            {"weight": 5.0},
        ),
        (
            _oracle.MountingHole((0.0, 0.0), 1.0),
            public.MountingHole((0.0, 0.0), 1.0),
            {"keepout_radius": 9.0},
        ),
        (
            _oracle.Trace((0.0, 0.0), (1.0, 1.0), 0.25, "F.Cu"),
            public.Trace((0.0, 0.0), (1.0, 1.0), 0.25, "F.Cu"),
            {"net": "GND"},
        ),
        (
            _oracle.Via((0.0, 0.0), 0.3, 0.6),
            public.Via((0.0, 0.0), 0.3, 0.6),
            {"is_diff_pair": True},
        ),
    ]:
        assert canon(dataclasses.replace(py_obj, **changes)) == canon(
            dataclasses.replace(rs_obj, **changes)
        )

    py_board, rs_board = _py_board(), _rs_board()
    assert canon(dataclasses.replace(py_board, width=42.0)) == canon(
        dataclasses.replace(rs_board, width=42.0)
    )


def test_replace_rejects_the_init_false_field_identically():
    """`Board._zone_map` is `init=False`, so `replace()` must refuse it --
    `ValueError`, not a silent accept."""
    import dataclasses

    py_out = canon_call(dataclasses.replace, _py_board(), _zone_map={})
    rs_out = canon_call(dataclasses.replace, _rs_board(), _zone_map={})
    assert py_out == rs_out
    assert py_out[0] == "raised"


def test_dataclass_field_surface_matches_the_oracle():
    import dataclasses

    from temper_placer.core import board as public

    for py_cls, rs_cls in [
        (_oracle.MountingHole, public.MountingHole),
        (_oracle.Pad, public.Pad),
        (_oracle.Component, public.Component),
        (_oracle.Trace, public.Trace),
        (_oracle.Via, public.Via),
        (_oracle.Layer, public.Layer),
        (_oracle.LayerStackup, public.LayerStackup),
        (_oracle.Rect, public.Rect),
        (_oracle.Zone, public.Zone),
        (_oracle.GroundDomain, public.GroundDomain),
        (_oracle.Board, public.Board),
    ]:
        assert dataclasses.is_dataclass(rs_cls)
        assert [(f.name, f.init) for f in dataclasses.fields(py_cls)] == [
            (f.name, f.init) for f in dataclasses.fields(rs_cls)
        ]


def test_public_module_delegates_to_rust():
    from temper_placer.core import board as public

    assert public.Board is RS_BOARD
    assert public.Zone is RS_ZONE
    assert public.Rect is RS_RECT
    assert public.LayerStackup is RS_LAYER_STACKUP
    assert public.Layer is RS_LAYER
    assert public.Trace is RS_TRACE
    assert public.Via is RS_VIA
    assert public.MountingHole is RS_MOUNTING_HOLE
    assert public.Pad is RS_PAD
    assert public.GroundDomain is RS_GROUND_DOMAIN
    assert public.Component is RS_COMPONENT
    assert public.side_to_layer_name is RS_SIDE_TO_LAYER_NAME


def test_layer_index_stays_a_python_intenum_r3():
    """R3 verdict: `LayerIndex` is NOT migrated.

    pyo3 cannot produce a pyclass that subclasses `int`, and this enum's
    int-ness is load-bearing in-repo. Asserting the int-ness here means a
    future attempt to move it into Rust must confront the recorded blocker.
    """
    import enum

    from temper_placer.core import board as public

    assert issubclass(public.LayerIndex, enum.IntEnum)
    assert public.LayerIndex.F_CU == 0
    assert public.LayerIndex.IN1_CU == 1
    assert hash(public.LayerIndex.IN1_CU) == hash(1)
    assert {public.LayerIndex.IN1_CU: "x"}[1] == "x"
    assert not hasattr(_rs, "LayerIndex")


def test_layer_index_surface_matches_the_oracle():
    from temper_placer.core import board as public

    for member in ("F_CU", "IN1_CU", "IN2_CU", "B_CU"):
        py = getattr(_oracle.LayerIndex, member)
        rs = getattr(public.LayerIndex, member)
        assert (py.name, py.value, str(py)) == (rs.name, rs.value, str(rs))
    assert public.STANDARD_LAYER_ORDER == _oracle.STANDARD_LAYER_ORDER
    assert public.PLANE_LAYER_INDICES == _oracle.PLANE_LAYER_INDICES
    assert public.LAYER_NAME_TO_IDX == _oracle.LAYER_NAME_TO_IDX
    assert public.LAYER_IDX_TO_NAME == _oracle.LAYER_IDX_TO_NAME
    assert public.CANONICAL_4LAYER_LAYER_NAMES == _oracle.CANONICAL_4LAYER_LAYER_NAMES
    assert public.CANONICAL_LAYER_COUNT == _oracle.CANONICAL_LAYER_COUNT


@pytest.mark.parametrize("probe", ["F.Cu", "In1.Cu", "In2.Cu", "B.Cu"])
def test_layer_predicate_helpers_identical(probe):
    from temper_placer.core import board as public

    assert canon_call(public.is_plane_layer, probe) == canon_call(_oracle.is_plane_layer, probe)
    assert canon_call(public.is_signal_layer, probe) == canon_call(_oracle.is_signal_layer, probe)
    assert canon_call(public.layer_name_to_index, probe) == canon_call(
        _oracle.layer_name_to_index, probe
    )


def test_explicit_none_literal_defaults_divergence_pinned():
    """The pyo3 Option params cannot distinguish an *omitted* argument from an
    *explicitly passed* `None` (pyo3's extract_argument_with_default turns a
    present `None` into the Rust `None` and only consults the default when the
    argument is absent), so explicit `None` collapses onto the literal default
    on the pyclasses while the dataclasses store what they are given.

    Latent: no in-repo caller passes explicit `None` for any of these fields
    (verified 2026-08-04). Assert each arm's exact behavior (#712 pattern-5
    precedent) so a change to either arm -- or a new caller passing explicit
    `None` -- is caught rather than silently diverging. Recorded in
    VERIFICATION.md (board/netlist documented deviation 6).
    """
    # --- MountingHole.keepout_radius: None -> 3.0 on the pyclass ----------
    py = _oracle.MountingHole((0.0, 0.0), 3.0, keepout_radius=None)
    rs = RS_MOUNTING_HOLE((0.0, 0.0), 3.0, keepout_radius=None)
    assert py.keepout_radius is None  # oracle stores the passed None
    assert canon(rs.keepout_radius) == canon(3.0)  # pyclass collapses to the default
    # Omitted-arg default is identical on both arms.
    assert canon(_oracle.MountingHole((0.0, 0.0), 3.0).keepout_radius) == canon(3.0)
    assert canon(RS_MOUNTING_HOLE((0.0, 0.0), 3.0).keepout_radius) == canon(3.0)
    # An explicit non-None value is stored identically.
    assert canon(
        _oracle.MountingHole((0.0, 0.0), 3.0, keepout_radius=5.0).keepout_radius
    ) == canon(RS_MOUNTING_HOLE((0.0, 0.0), 3.0, keepout_radius=5.0).keepout_radius)

    # --- Zone literal-default fields: None -> default on the pyclass ------
    zone_fields = ["net_classes", "weight", "layers", "can_expand", "zone_type"]
    py = _oracle.Zone("Z", (0, 0, 1, 1), **dict.fromkeys(zone_fields))
    rs = RS_ZONE("Z", (0, 0, 1, 1), **dict.fromkeys(zone_fields))
    for field in zone_fields:
        assert canon(getattr(py, field)) == canon(None), field  # oracle stores None
    # net_classes is the finding's named field; assert its pyclass collapse
    # directly, and the rest by the same rule.
    assert canon(rs.net_classes) == canon(["Signal"])
    assert canon(rs.weight) == canon(1.0)
    assert canon(rs.layers) == canon(["F.Cu"])
    assert canon(rs.can_expand) == canon(["up", "down", "left", "right"])
    assert canon(rs.zone_type) == canon("placement")
    # Omitted-arg defaults agree between the arms.
    assert canon(_oracle.Zone("Z", (0, 0, 1, 1)).net_classes) == canon(
        RS_ZONE("Z", (0, 0, 1, 1)).net_classes
    )
