"""Differential: Rust board pyclasses vs the verbatim Python oracle.

The Rust port (packages/temper-design-bundle/src/board.rs) must be
bit-identical to the pinned pre-migration module
(tests/core/_board_py_oracle.py, origin/main f2b09d846): construction,
field mapping, dunders (Rect's tuple drop-in), and repr byte-parity
(B9/B10). The numpy float32 surface (polygon_array/get_bounds_array/
get_relative_bounds_array) is shim-kept (R10) and asserted for dtype
explicitly. The oracle's classes are plain dataclasses; the migrated ones
are pyclasses — canonicalization compares field state, and repr compares
bytes.

RED guard: this suite fails to collect before the pyclasses exist.
"""

from __future__ import annotations

import numpy as np
import pytest
from temper_design_bundle_python import (
    Board as RustBoard,
)
from temper_design_bundle_python import (
    Component as RustComponent,
)
from temper_design_bundle_python import (
    GroundDomain as RustGroundDomain,
)
from temper_design_bundle_python import (
    Layer as RustLayer,
)
from temper_design_bundle_python import (
    LayerIndex as RustLayerIndex,
)
from temper_design_bundle_python import (
    LayerStackup as RustLayerStackup,
)
from temper_design_bundle_python import (
    MountingHole as RustMountingHole,
)
from temper_design_bundle_python import (
    Pad as RustPad,
)
from temper_design_bundle_python import (
    Rect as RustRect,
)
from temper_design_bundle_python import (
    Trace as RustTrace,
)
from temper_design_bundle_python import (
    Via as RustVia,
)
from temper_design_bundle_python import (
    Zone as RustZone,
)

from tests.core import _board_py_oracle as oracle


def _f(value):
    if value is None or isinstance(value, str):
        return value
    return float(value).hex()


def _point_canonical(p):
    return tuple(_f(v) for v in p)


def _rect_canonical(rect):
    return tuple(_f(getattr(rect, f)) for f in ("x_min", "y_min", "x_max", "y_max"))


def _mh_canonical(mh):
    return {
        "position": _point_canonical(mh.position),
        "diameter": _f(mh.diameter),
        "keepout_radius": _f(mh.keepout_radius),
    }


def _pad_canonical(pad):
    return {
        "position": _point_canonical(pad.position),
        "size": _point_canonical(pad.size),
        "shape": pad.shape,
        "layer": pad.layer,
        "number": pad.number,
        "net_name": pad.net_name,
    }


def _component_canonical(comp):
    return {
        "ref": comp.ref,
        "position": _point_canonical(comp.position),
        "rotation": _f(comp.rotation),
        "width": _f(comp.width),
        "height": _f(comp.height),
        "footprint": comp.footprint,
        "pads": [_pad_canonical(p) for p in comp.pads],
        "layer": comp.layer,
        "fixed": comp.fixed,
    }


def _layer_canonical(layer):
    return {
        "name": layer.name,
        "layer_type": layer.layer_type,
        "copper_weight": _f(layer.copper_weight),
        "is_routable": layer.is_routable,
    }


def _stackup_canonical(ls):
    return {
        "layers": tuple(_layer_canonical(layer) for layer in ls.layers),
        "thickness": _f(ls.thickness),
    }


def _zone_canonical(zone):
    return {
        "name": zone.name,
        "bounds": _rect_canonical(zone.bounds),
        "net_classes": list(zone.net_classes),
        "components": list(zone.components),
        "weight": _f(zone.weight),
        "polygon": (
            [_point_canonical(p) for p in zone.polygon] if zone.polygon is not None else None
        ),
        "layers": list(zone.layers),
        "max_size": (
            _point_canonical(zone.max_size) if zone.max_size is not None else None
        ),
        "can_expand": list(zone.can_expand),
        "zone_type": zone.zone_type,
    }


def _gd_canonical(gd):
    return {
        "name": gd.name,
        "bounds": tuple(_f(v) for v in gd.bounds),
        "star_point": (
            _point_canonical(gd.star_point) if gd.star_point is not None else None
        ),
    }


def _board_canonical(board):
    return {
        "width": _f(board.width),
        "height": _f(board.height),
        "origin": _point_canonical(board.origin),
        "zones": [_zone_canonical(z) for z in board.zones],
        "mounting_holes": [_mh_canonical(m) for m in board.mounting_holes],
        "keepouts": [tuple(_f(v) for v in k) for k in board.keepouts],
        "ground_domains": [_gd_canonical(g) for g in board.ground_domains],
        "layer_stackup": _stackup_canonical(board.layer_stackup),
        "outline_polygon": (
            [_point_canonical(p) for p in board.outline_polygon]
            if board.outline_polygon is not None
            else None
        ),
    }


def _temper_board_kwargs():
    """The shared fixture: the canonical Temper board, both sides."""
    return {
        "width": 100.0,
        "height": 150.0,
        "origin": (0.0, 0.0),
        "zones": [
            oracle.Zone("HV_ZONE", (0, 0, 50, 80)),
            oracle.Zone(
                "POLY_ZONE",
                (10, 10, 40, 60),
                net_classes=["Power", "Signal"],
                components=["U1"],
                weight=2.0,
                polygon=[(10, 10), (40, 10), (40, 60)],
                can_expand=["left"],
                zone_type="keepout",
            ),
        ],
        "mounting_holes": [
            oracle.MountingHole((5, 5), 3.2),
            oracle.MountingHole((95, 5), 3.2, keepout_radius=4.0),
        ],
        "keepouts": [(0, 0, 10, 10), (90, 140, 100, 150)],
        "ground_domains": [
            oracle.GroundDomain("PGND", (0, 0, 50, 150), star_point=(50, 75)),
            oracle.GroundDomain("CGND", (50, 0, 100, 150)),
        ],
        "layer_stackup": oracle.LayerStackup.default_4layer(),
        "outline_polygon": [(0, 0), (100, 0), (100, 150), (0, 150)],
    }


class TestLeafTypes:
    def test_mounting_hole_parity(self):
        o = oracle.MountingHole((1.5, 2.5), 3.0)
        r = RustMountingHole((1.5, 2.5), 3.0)
        assert _mh_canonical(r) == _mh_canonical(o)
        assert repr(r) == repr(o)
        o2 = oracle.MountingHole((1, 2), 3.0, keepout_radius=2.0)
        r2 = RustMountingHole((1, 2), 3.0, keepout_radius=2.0)
        assert repr(r2) == repr(o2)

    def test_pad_parity(self):
        o = oracle.Pad((0.0, 0.0), (1.0, 2.0), shape="oval", layer="B.Cu", number="1", net_name="GND")
        r = RustPad((0.0, 0.0), (1.0, 2.0), shape="oval", layer="B.Cu", number="1", net_name="GND")
        assert _pad_canonical(r) == _pad_canonical(o)
        assert repr(r) == repr(o)
        o2 = oracle.Pad((0, 0), (1, 2))
        r2 = RustPad((0, 0), (1, 2))
        assert repr(r2) == repr(o2)

    def test_component_parity(self):
        pads = [oracle.Pad((0.0, 0.0), (1.0, 1.0))]
        o = oracle.Component("U1", (10.0, 20.0), 90.0, 5.0, 4.0, footprint="SOIC-8", pads=pads, layer="B.Cu", fixed=True)
        r = RustComponent("U1", (10.0, 20.0), 90.0, 5.0, 4.0, footprint="SOIC-8", pads=pads, layer="B.Cu", fixed=True)
        assert _component_canonical(r) == _component_canonical(o)
        assert repr(r) == repr(o)

    def test_trace_parity(self):
        o = oracle.Trace((0.0, 0.0), (10.0, 10.0), 0.4, "F.Cu", net="AC_L")
        r = RustTrace((0.0, 0.0), (10.0, 10.0), 0.4, "F.Cu", net="AC_L")
        assert repr(r) == repr(o)
        o2 = oracle.Trace((0, 0), (10, 10), 0.2, "B.Cu")
        r2 = RustTrace((0, 0), (10, 10), 0.2, "B.Cu")
        assert repr(r2) == repr(o2)

    def test_via_parity(self):
        o = oracle.Via((5.0, 5.0), 0.4, 0.8)
        r = RustVia((5.0, 5.0), 0.4, 0.8)
        assert repr(r) == repr(o)
        o2 = oracle.Via((5, 5), 0.4, 0.8, layers=("F.Cu", "In1.Cu"), net="PWR", is_diff_pair=True)
        r2 = RustVia((5, 5), 0.4, 0.8, layers=("F.Cu", "In1.Cu"), net="PWR", is_diff_pair=True)
        assert repr(r2) == repr(o2)

    def test_layer_parity(self):
        o = oracle.Layer("F.Cu", "signal", copper_weight=2.0)
        r = RustLayer("F.Cu", "signal", copper_weight=2.0)
        assert _layer_canonical(r) == _layer_canonical(o)
        assert repr(r) == repr(o)


class TestLayerIndex:
    def test_members_and_attributes(self):
        for name in ("F_CU", "IN1_CU", "IN2_CU", "B_CU"):
            member = getattr(RustLayerIndex, name)
            oracle_member = getattr(oracle.LayerIndex, name)
            assert member.name == oracle_member.name
            assert member.value == int(oracle_member.value)

    def test_str_is_kicad_name(self):
        assert str(RustLayerIndex.F_CU) == "F.Cu"
        assert str(RustLayerIndex.B_CU) == "B.Cu"
        assert str(RustLayerIndex.F_CU) == str(oracle.LayerIndex.F_CU)

    def test_repr(self):
        assert repr(RustLayerIndex.IN1_CU) == repr(oracle.LayerIndex.IN1_CU)

    def test_from_name(self):
        assert RustLayerIndex.from_name("In2.Cu").name == "IN2_CU"
        with pytest.raises(KeyError):
            RustLayerIndex.from_name("nope")

    def test_members_iteration(self):
        rust_names = [m.name for m in RustLayerIndex.members()]
        assert rust_names == ["F_CU", "IN1_CU", "IN2_CU", "B_CU"]


class TestRect:
    def test_construction_and_fields(self):
        o = oracle.Rect(0.0, 0.0, 10.0, 20.0)
        r = RustRect(0.0, 0.0, 10.0, 20.0)
        assert _rect_canonical(r) == _rect_canonical(o)
        assert repr(r) == repr(o)

    def test_tuple_drop_in(self):
        r = RustRect(1.0, 2.0, 3.0, 4.0)
        assert tuple(r) == (1.0, 2.0, 3.0, 4.0)
        assert list(r) == [1.0, 2.0, 3.0, 4.0]
        assert len(r) == 4
        assert r[0] == 1.0
        assert r[3] == 4.0
        assert r[-1] == 4.0
        with pytest.raises(IndexError):
            r[4]

    def test_tuple_equality(self):
        r = RustRect(1.0, 2.0, 3.0, 4.0)
        assert r == (1.0, 2.0, 3.0, 4.0)
        assert r == (1.0, 2.0, 3.0, 4.0)
        assert r == [1.0, 2.0, 3.0, 4.0]
        assert r != (1.0, 2.0, 3.0, 5.0)
        assert r != (1.0, 2.0, 3.0)
        assert r != "nope"

    def test_invariant_validation(self):
        with pytest.raises(ValueError) as rust_exc:
            RustRect(5.0, 0.0, 5.0, 10.0)
        with pytest.raises(ValueError) as oracle_exc:
            oracle.Rect(5.0, 0.0, 5.0, 10.0)
        assert str(rust_exc.value) == str(oracle_exc.value)
        with pytest.raises(ValueError) as rust_exc2:
            RustRect(0.0, 5.0, 10.0, 5.0)
        with pytest.raises(ValueError) as oracle_exc2:
            oracle.Rect(0.0, 5.0, 10.0, 5.0)
        assert str(rust_exc2.value) == str(oracle_exc2.value)

    def test_classmethods(self):
        assert _rect_canonical(RustRect.from_xyxy(0, 0, 10, 20)) == _rect_canonical(
            oracle.Rect.from_xyxy(0, 0, 10, 20)
        )
        assert _rect_canonical(RustRect.from_xywh(0, 0, 10, 20)) == _rect_canonical(
            oracle.Rect.from_xywh(0, 0, 10, 20)
        )
        r = RustRect(0.0, 0.0, 10.0, 20.0)
        assert RustRect.coerce(r) is r
        coerced = RustRect.coerce((0.0, 0.0, 10.0, 20.0))
        assert _rect_canonical(coerced) == _rect_canonical(r)

    def test_properties(self):
        r = RustRect(0.0, 0.0, 10.0, 20.0)
        assert r.width == 10.0
        assert r.height == 20.0
        assert hash(r) == hash((0.0, 0.0, 10.0, 20.0))


class TestZone:
    def test_construction_and_coercion(self):
        o = oracle.Zone("A", (0, 0, 10, 10))
        r = RustZone("A", (0, 0, 10, 10))
        assert _zone_canonical(r) == _zone_canonical(o)
        assert repr(r) == repr(o)

    def test_inverted_bounds_raise_at_construction(self):
        with pytest.raises(ValueError):
            RustZone("A", (10, 0, 0, 10))

    def test_properties(self):
        o = oracle.Zone("A", (0, 0, 10, 20))
        r = RustZone("A", (0, 0, 10, 20))
        assert r.width == o.width == 10.0
        assert r.height == o.height == 20.0
        assert r.center == o.center == (5.0, 10.0)
        assert r.area == o.area == 200.0
        assert r.contains_point(5.0, 10.0) == o.contains_point(5.0, 10.0) is True
        assert r.contains_point(50.0, 10.0) == o.contains_point(50.0, 10.0) is False

    def test_defaults(self):
        o = oracle.Zone("A", (0, 0, 10, 10))
        r = RustZone("A", (0, 0, 10, 10))
        assert list(r.net_classes) == list(o.net_classes) == ["Signal"]
        assert list(r.can_expand) == list(o.can_expand)


class TestGroundDomain:
    def test_parity(self):
        o = oracle.GroundDomain("PGND", (0, 0, 50, 150), star_point=(50, 75))
        r = RustGroundDomain("PGND", (0, 0, 50, 150), star_point=(50, 75))
        assert _gd_canonical(r) == _gd_canonical(o)
        assert repr(r) == repr(o)
        o2 = oracle.GroundDomain("CGND", (0, 0, 50, 150))
        r2 = RustGroundDomain("CGND", (0, 0, 50, 150))
        assert repr(r2) == repr(o2)


class TestLayerStackup:
    def test_default_4layer_parity(self):
        o = oracle.LayerStackup.default_4layer()
        r = RustLayerStackup.default_4layer()
        assert _stackup_canonical(r) == _stackup_canonical(o)
        assert repr(r) == repr(o)

    def test_is_plane_layer(self):
        r = RustLayerStackup.default_4layer()
        assert r.is_plane_layer(1)
        assert r.is_plane_layer(2)
        assert not r.is_plane_layer(0)
        assert not r.is_plane_layer(9)

    def test_routable_layers(self):
        r = RustLayerStackup.default_4layer()
        assert r.routable_layers("HighVoltage") == [0]
        assert r.routable_layers("Signal") == [0, 3]

    def test_tracks_per_cell(self):
        r = RustLayerStackup.default_4layer()
        o = oracle.LayerStackup.default_4layer()
        assert r.tracks_per_cell(1.0) == pytest.approx(o.tracks_per_cell(1.0))


class TestBoard:
    def test_temper_default_parity(self):
        o = oracle.Board.temper_default()
        r = RustBoard.temper_default()
        assert _board_canonical(r) == _board_canonical(o)
        assert repr(r) == repr(o)

    def test_full_kwargs_parity(self):
        kwargs = _temper_board_kwargs()
        o = oracle.Board(**kwargs)
        r = RustBoard(**kwargs)
        assert _board_canonical(r) == _board_canonical(o)
        assert repr(r) == repr(o)

    def test_repr_byte_identical(self):
        o = oracle.Board.temper_default()
        r = RustBoard.temper_default()
        assert repr(r) == repr(o)

    def test_default_stackup_and_enforcement(self):
        o = oracle.Board(100.0, 150.0)
        r = RustBoard(100.0, 150.0)
        assert len(r.layer_stackup.layers) == len(o.layer_stackup.layers) == 4
        with pytest.raises(ValueError) as rust_exc:
            RustBoard(100.0, 150.0, layer_stackup=oracle.LayerStackup(layers=(oracle.Layer("F.Cu", "signal"),)))
        with pytest.raises(ValueError) as oracle_exc:
            oracle.Board(100.0, 150.0, layer_stackup=oracle.LayerStackup(layers=(oracle.Layer("F.Cu", "signal"),)))
        assert str(rust_exc.value) == str(oracle_exc.value)

    def test_get_zone_and_miss(self):
        r = RustBoard.temper_default()
        assert r.get_zone("HV_ZONE").name == "HV_ZONE"
        with pytest.raises(KeyError):
            r.get_zone("NOPE")

    def test_point_queries(self):
        o = oracle.Board.temper_default()
        r = RustBoard.temper_default()
        assert r.contains_point(50.0, 75.0) == o.contains_point(50.0, 75.0) is True
        assert r.contains_point(500.0, 75.0) == o.contains_point(500.0, 75.0) is False
        assert r.get_zone_for_point(25.0, 25.0).name == o.get_zone_for_point(25.0, 25.0).name
        assert r.get_zone_for_point(25.0, 145.0).name == o.get_zone_for_point(25.0, 145.0).name
        assert r.get_ground_domain(25.0, 25.0).name == o.get_ground_domain(25.0, 25.0).name
        assert r.get_ground_domain(25.0, 25.0).star_point == o.get_ground_domain(25.0, 25.0).star_point
        # point inside a mounting-hole keepout
        assert r.point_in_keepout(5.0, 5.0) == o.point_in_keepout(5.0, 5.0) is True
        assert r.point_in_keepout(50.0, 50.0) == o.point_in_keepout(50.0, 50.0) is False

    def test_area(self):
        r = RustBoard(100.0, 150.0)
        assert r.area == 15000.0

    def test_keepout_regions_alias(self):
        o = oracle.Board.temper_default()
        r = RustBoard.temper_default()
        assert list(r.keepout_regions) == list(o.keepout_regions)
        assert r.has_polygon_outline == o.has_polygon_outline is False

    def test_from_polygon(self):
        o = oracle.Board.from_polygon([(0, 0), (100, 0), (100, 150), (0, 150)])
        r = RustBoard.from_polygon([(0, 0), (100, 0), (100, 150), (0, 150)])
        assert _board_canonical(r) == _board_canonical(o)

    def test_rotated_90_parity(self):
        kwargs = _temper_board_kwargs()
        o = oracle.Board(**kwargs).rotated_90()
        r = RustBoard(**kwargs).rotated_90()
        assert _board_canonical(r) == _board_canonical(o)
        assert repr(r) == repr(o)

    def test_rotated_90_twice_is_180(self):
        kwargs = _temper_board_kwargs()
        r = RustBoard(**kwargs).rotated_90().rotated_90()
        o = oracle.Board(**kwargs).rotated_90().rotated_90()
        assert _board_canonical(r) == _board_canonical(o)

    def test_build_indices_after_mutation(self):
        r = RustBoard.temper_default()
        r.zones.append(RustZone("NEW", (0, 0, 5, 5)))
        with pytest.raises(KeyError):
            r.get_zone("NEW")
        r.build_indices()
        assert r.get_zone("NEW").name == "NEW"


class TestNumpyShimSurface:
    def test_float32_dtype_explicit(self):
        """KTD6: dtype is asserted, not just values — np.float32(10.0) ==
        10.0 hides dtype loss."""
        from temper_placer.core.board import get_bounds_array, polygon_array

        r = RustBoard.temper_default()
        bounds = get_bounds_array(r)
        assert bounds.dtype == np.float32
        assert bounds.shape == (4,)
        rel = get_bounds_array.__globals__  # noqa: B018
        assert rel is not None
        assert polygon_array(r) is None
        outlined = RustBoard(100.0, 150.0, outline_polygon=[(0, 0), (100, 0), (100, 150)])
        pa = polygon_array(outlined)
        assert pa.dtype == np.float32
        assert pa.shape == (3, 2)
