"""
Differential oracle tests: geometry_types (Point, Track, Via, Pad).

Wave 4, unit ``geometry_types``: the four pure dataclass types from
``temper_placer/core/geometry_types.py``, migrated to Rust pyclasses in the
``temper-design-bundle`` crate (submodule ``geometry_contracts``).

This test pins the pre-migration Python dataclass implementations VERBATIM
as oracle blocks and compares the production imports against them.

G1 (TDD): In identity mode (before Rust), the shim imports ARE the Python
dataclasses and the test compares them against the oracles — the test is
trivially green. After migration, the shim imports become the Rust pyclasses
and the test compares Rust vs Python oracle. The same assertions must stay
green.

G3 (perf): N/A — pure data-contract classes with no significant compute
outside the already-migrated temper_geometry kernels.

G4 (PBT): Covered by the existing cluster PBT
(``test_core_graph_cluster_pbt.py`` — P8, MR6, MR19). G4 module-to-property
map recorded there.

G5 (metamorphic): Covered by the existing cluster metamorphic suite.

G6 (induction): Structural proof (data-only delegation pyclasses) recorded
in ``packages/temper-design-bundle/VERIFICATION.md``.

G7 (Rust practices): ``cargo clippy --all-features --all-targets -- -D warnings``
clean.

G8 (physics): N/A — no physics-gated surfaces.

Comparison conventions:
- scalar floats compared via ``float.hex()`` — bit-exact;
- repr compared byte-for-byte after class-name normalization;
- equality asserted via ``==``, field-by-field.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pytest

# ============================================================================
# Oracle block — verbatim copy of `temper_placer/core/geometry_types.py`
# (origin/main, 1be60090, pre-migration). DO NOT EDIT — these are the
# reference implementations, name-suffixed _Oracle.
# ============================================================================

# The oracle must import temper_geometry for the numeric methods it delegates.
# In identity mode this is the same extension; after migration the oracles
# remain Python-side and continue calling the same extension.
import temper_geometry as _tg_oracle


@dataclass(frozen=True)
class _OraclePoint:
    """A 2D point."""

    x: float
    y: float

    def to_array(self) -> np.ndarray:
        """Convert to numpy array."""
        return np.array([self.x, self.y])

    def distance_to(self, other: _OraclePoint) -> float:
        """Euclidean distance to another point."""
        return _tg_oracle.point_distance_py(self.x, self.y, other.x, other.y)


@dataclass
class _OracleTrack:
    """A routed track segment."""

    start: _OraclePoint
    end: _OraclePoint
    width: float
    net: str
    layer: int
    id: str = ""
    diff_pair_companion: str | None = None

    def is_diff_pair_with(self, other: _OracleTrack) -> bool:
        """Check if this track and another are companions in a differential pair."""
        return self.diff_pair_companion is not None and self.diff_pair_companion == other.net

    def midpoint(self) -> _OraclePoint:
        """Get the midpoint of the track."""
        mx, my = _tg_oracle.track_midpoint_py(
            self.start.x, self.start.y, self.end.x, self.end.y
        )
        return _OraclePoint(mx, my)


@dataclass
class _OracleVia:
    """A via connecting layers."""

    center: _OraclePoint
    diameter: float
    drill: float
    net: str
    id: str = ""


@dataclass
class _OraclePad:
    """A component pad for DRC/spatial queries."""

    center: _OraclePoint
    shape: str  # "circle", "rect", "oval"
    size: tuple[float, float]  # (width, height) in mm
    net: str
    layer: int
    id: str = ""
    rotation: float = 0.0  # Degrees counter-clockwise
    mask_expansion: float = 0.1  # Solder mask clearance expansion
    is_pth: bool = False  # Plated Through-Hole flag (all layers)

    @property
    def radius(self) -> float:
        """Bounding radius for broad-phase checks."""
        w, h = self.size
        return _tg_oracle.pad_radius_py(w, h)


# ============================================================================
# Production imports — these are the shim exports; in identity mode they ARE
# the Python dataclasses; after migration they ARE the Rust pyclasses.
# ============================================================================

from temper_placer.core.geometry_types import Pad, Point, Track, Via  # noqa: E402


# ============================================================================
# Helper: compare two objects field-by-field
# ============================================================================


def _assert_float_bit_exact(a: float, b: float) -> None:
    assert float(a).hex() == float(b).hex(), f"{a!r} != {b!r}"


def _assert_points_equal(p_prod: Any, p_oracle: _OraclePoint) -> None:
    """Assert a production Point matches an oracle Point field-by-field."""
    _assert_float_bit_exact(p_prod.x, p_oracle.x)
    _assert_float_bit_exact(p_prod.y, p_oracle.y)


def _assert_tracks_equal(t_prod: Any, t_oracle: _OracleTrack) -> None:
    """Assert a production Track matches an oracle Track field-by-field."""
    _assert_points_equal(t_prod.start, t_oracle.start)
    _assert_points_equal(t_prod.end, t_oracle.end)
    _assert_float_bit_exact(t_prod.width, t_oracle.width)
    assert t_prod.net == t_oracle.net
    assert t_prod.layer == t_oracle.layer
    assert t_prod.id == t_oracle.id
    assert t_prod.diff_pair_companion == t_oracle.diff_pair_companion


def _assert_vias_equal(v_prod: Any, v_oracle: _OracleVia) -> None:
    """Assert a production Via matches an oracle Via field-by-field."""
    _assert_points_equal(v_prod.center, v_oracle.center)
    _assert_float_bit_exact(v_prod.diameter, v_oracle.diameter)
    _assert_float_bit_exact(v_prod.drill, v_oracle.drill)
    assert v_prod.net == v_oracle.net
    assert v_prod.id == v_oracle.id


def _assert_pads_equal(p_prod: Any, p_oracle: _OraclePad) -> None:
    """Assert a production Pad matches an oracle Pad field-by-field."""
    _assert_points_equal(p_prod.center, p_oracle.center)
    assert p_prod.shape == p_oracle.shape
    assert p_prod.size == p_oracle.size
    assert p_prod.net == p_oracle.net
    assert p_prod.layer == p_oracle.layer
    assert p_prod.id == p_oracle.id
    _assert_float_bit_exact(p_prod.rotation, p_oracle.rotation)
    _assert_float_bit_exact(p_prod.mask_expansion, p_oracle.mask_expansion)
    assert p_prod.is_pth == p_oracle.is_pth


def _normalize_repr(r: str, prod_class_name: str, oracle_class_name: str) -> str:
    """Replace production class names with oracle class names in repr strings.

    In identity mode: production is ``Point``, oracle is ``_OraclePoint``.
    After migration: production may be ``GeometryPoint``, oracle stays ``_OraclePoint``.
    Normalize so repr comparisons pass.
    """
    return r.replace(prod_class_name, oracle_class_name)


def _extract_class_name(repr_str: str) -> str:
    """Extract the class name from a repr string (everything before first '(')."""
    paren = repr_str.find("(")
    if paren <= 0:
        return repr_str
    return repr_str[:paren]


# ============================================================================
# Point tests
# ============================================================================


class TestPoint:
    """Point: frozen dataclass with x, y fields, to_array, distance_to."""

    def test_construction_and_fields(self):
        p = Point(1.5, -2.5)
        o = _OraclePoint(1.5, -2.5)
        _assert_points_equal(p, o)

    def test_frozen_raises_on_setattr(self):
        p = Point(1.0, 2.0)
        with pytest.raises((AttributeError, TypeError)):
            p.x = 3.0

    def test_hash_equivalence(self):
        """Point is frozen=True, so it must be hashable."""
        p = Point(1.0, 2.0)
        assert hash(p) == hash(p)

        # Hash should match the oracle's hash
        o = _OraclePoint(1.0, 2.0)
        assert hash(p) == hash(o)

    def test_eq_identity(self):
        p1 = Point(1.0, 2.0)
        p2 = Point(1.0, 2.0)
        assert p1 == p2
        assert p1 != Point(1.0, 3.0)

    def test_eq_cross_type(self):
        """Cross-type equality: a Point should NOT equal a non-Point."""
        p = Point(1.0, 2.0)
        o = _OraclePoint(1.0, 2.0)
        # The dataclass eq only considers same type
        # The Rust pyclass delegates to CPython tuple comparison, so
        # cross-type is NotImplemented -> False.
        assert p != o  # type-identity comparison

    def test_repr(self):
        p = Point(1.5, -2.5)
        r = repr(p)
        o = _OraclePoint(1.5, -2.5)
        expected = repr(o)
        # Normalize: production class name -> oracle class name
        prod_name = _extract_class_name(r)
        r_norm = _normalize_repr(r, prod_name, "_OraclePoint")
        assert r_norm == expected, f"repr mismatch: {r_norm!r} != {expected!r}"

    def test_to_array(self):
        p = Point(3.0, 4.0)
        arr = p.to_array()
        assert isinstance(arr, np.ndarray)
        assert arr.dtype == np.float64
        assert arr.shape == (2,)
        _assert_float_bit_exact(arr[0], 3.0)
        _assert_float_bit_exact(arr[1], 4.0)

    def test_distance_to(self):
        p1 = Point(0.0, 0.0)
        p2 = Point(3.0, 4.0)
        _assert_float_bit_exact(p1.distance_to(p2), 5.0)

    def test_distance_to_random(self):
        import random

        rng = random.Random(20260810)
        for _ in range(40):
            a = Point(round(rng.uniform(-100, 100), 6), round(rng.uniform(-100, 100), 6))
            b = Point(round(rng.uniform(-100, 100), 6), round(rng.uniform(-100, 100), 6))
            prod = a.distance_to(b)
            oracle = _tg_oracle.point_distance_py(a.x, a.y, b.x, b.y)
            _assert_float_bit_exact(prod, oracle)


# ============================================================================
# Track tests
# ============================================================================


class TestTrack:
    """Track: mutable dataclass with start/end Point fields, midpoint, is_diff_pair_with."""

    def test_construction_and_fields(self):
        t = Track(
            start=Point(0.0, 0.0),
            end=Point(10.0, 0.0),
            width=0.5,
            net="N1",
            layer=1,
            id="t1",
        )
        o = _OracleTrack(
            start=_OraclePoint(0.0, 0.0),
            end=_OraclePoint(10.0, 0.0),
            width=0.5,
            net="N1",
            layer=1,
            id="t1",
        )
        _assert_tracks_equal(t, o)

    def test_default_fields(self):
        t = Track(
            start=Point(0.0, 0.0),
            end=Point(1.0, 1.0),
            width=0.3,
            net="N2",
            layer=2,
        )
        assert t.id == ""
        assert t.diff_pair_companion is None

    def test_mutable_setattr(self):
        t = Track(
            start=Point(0.0, 0.0),
            end=Point(1.0, 1.0),
            width=0.3,
            net="N2",
            layer=2,
        )
        t.id = "modified"
        assert t.id == "modified"

    def test_not_hashable(self):
        t = Track(
            start=Point(0.0, 0.0),
            end=Point(1.0, 1.0),
            width=0.3,
            net="N2",
            layer=2,
        )
        with pytest.raises(TypeError):
            hash(t)

    def test_eq_identity(self):
        t1 = Track(
            start=Point(0.0, 0.0),
            end=Point(10.0, 0.0),
            width=0.5,
            net="N1",
            layer=1,
        )
        t2 = Track(
            start=Point(0.0, 0.0),
            end=Point(10.0, 0.0),
            width=0.5,
            net="N1",
            layer=1,
        )
        assert t1 == t2
        assert t1 != Track(
            start=Point(0.0, 0.0),
            end=Point(10.0, 0.0),
            width=0.5,
            net="N1",
            layer=2,
        )

    def test_repr(self):
        t = Track(
            start=Point(0.0, 0.0),
            end=Point(1.0, 1.0),
            width=0.3,
            net="N2",
            layer=2,
        )
        r = repr(t)
        o = _OracleTrack(
            start=_OraclePoint(0.0, 0.0),
            end=_OraclePoint(1.0, 1.0),
            width=0.3,
            net="N2",
            layer=2,
        )
        expected = repr(o)
        prod_name = _extract_class_name(r)
        r_norm = _normalize_repr(r, prod_name, "_OracleTrack")
        r_norm = r_norm.replace("Point(", "_OraclePoint(")
        assert r_norm == expected, f"repr mismatch:\n  got: {r}\n  expected: {expected}"

    def test_midpoint(self):
        t = Track(
            start=Point(0.0, 0.0),
            end=Point(10.0, 0.0),
            width=0.5,
            net="N1",
            layer=1,
        )
        m = t.midpoint()
        assert isinstance(m, Point)
        _assert_float_bit_exact(m.x, 5.0)
        _assert_float_bit_exact(m.y, 0.0)

    def test_midpoint_random(self):
        import random

        rng = random.Random(20260810)
        for _ in range(30):
            sx = round(rng.uniform(-50, 50), 6)
            sy = round(rng.uniform(-50, 50), 6)
            ex = round(rng.uniform(-50, 50), 6)
            ey = round(rng.uniform(-50, 50), 6)
            t = Track(
                start=Point(sx, sy),
                end=Point(ex, ey),
                width=0.5,
                net="N",
                layer=1,
            )
            m = t.midpoint()
            ox, oy = _tg_oracle.track_midpoint_py(sx, sy, ex, ey)
            _assert_float_bit_exact(m.x, ox)
            _assert_float_bit_exact(m.y, oy)

    def test_is_diff_pair_with(self):
        t1 = Track(
            start=Point(0.0, 0.0),
            end=Point(1.0, 1.0),
            width=0.3,
            net="DP_P",
            layer=1,
            diff_pair_companion="DP_N",
        )
        t2 = Track(
            start=Point(0.0, 0.0),
            end=Point(1.0, 1.0),
            width=0.3,
            net="DP_N",
            layer=1,
        )
        t3 = Track(
            start=Point(0.0, 0.0),
            end=Point(1.0, 1.0),
            width=0.3,
            net="OTHER",
            layer=1,
        )

        assert t1.is_diff_pair_with(t2) is True
        assert t1.is_diff_pair_with(t3) is False
        # t1 has no companion set
        t_no = Track(
            start=Point(0.0, 0.0),
            end=Point(1.0, 1.0),
            width=0.3,
            net="X",
            layer=1,
        )
        assert t_no.is_diff_pair_with(t2) is False


# ============================================================================
# Via tests
# ============================================================================


class TestVia:
    """Via: mutable dataclass with center Point, diameter, drill, net, id."""

    def test_construction_and_fields(self):
        v = Via(
            center=Point(5.0, 5.0),
            diameter=0.6,
            drill=0.3,
            net="GND",
            id="v1",
        )
        o = _OracleVia(
            center=_OraclePoint(5.0, 5.0),
            diameter=0.6,
            drill=0.3,
            net="GND",
            id="v1",
        )
        _assert_vias_equal(v, o)

    def test_default_fields(self):
        v = Via(
            center=Point(0.0, 0.0),
            diameter=0.6,
            drill=0.3,
            net="N",
        )
        assert v.id == ""

    def test_mutable_setattr(self):
        v = Via(
            center=Point(0.0, 0.0),
            diameter=0.6,
            drill=0.3,
            net="N",
        )
        v.id = "modified"
        assert v.id == "modified"

    def test_not_hashable(self):
        v = Via(
            center=Point(0.0, 0.0),
            diameter=0.6,
            drill=0.3,
            net="N",
        )
        with pytest.raises(TypeError):
            hash(v)

    def test_eq_identity(self):
        v1 = Via(center=Point(5.0, 5.0), diameter=0.6, drill=0.3, net="GND")
        v2 = Via(center=Point(5.0, 5.0), diameter=0.6, drill=0.3, net="GND")
        assert v1 == v2
        assert v1 != Via(center=Point(5.0, 5.0), diameter=0.6, drill=0.3, net="VCC")

    def test_repr(self):
        v = Via(center=Point(5.0, 5.0), diameter=0.6, drill=0.3, net="GND", id="v1")
        r = repr(v)
        o = _OracleVia(
            center=_OraclePoint(5.0, 5.0),
            diameter=0.6,
            drill=0.3,
            net="GND",
            id="v1",
        )
        expected = repr(o)
        prod_name = _extract_class_name(r)
        r_norm = _normalize_repr(r, prod_name, "_OracleVia")
        r_norm = r_norm.replace("Point(", "_OraclePoint(")
        assert r_norm == expected, f"repr mismatch:\n  got: {r}\n  expected: {expected}"


# ============================================================================
# Pad tests
# ============================================================================


class TestPad:
    """Pad: mutable dataclass with center, shape, size, net, layer, radius property."""

    def test_construction_and_fields(self):
        p = Pad(
            center=Point(1.0, 2.0),
            shape="rect",
            size=(1.6, 0.8),
            net="N1",
            layer=1,
            id="p1",
            rotation=90.0,
            mask_expansion=0.15,
            is_pth=True,
        )
        o = _OraclePad(
            center=_OraclePoint(1.0, 2.0),
            shape="rect",
            size=(1.6, 0.8),
            net="N1",
            layer=1,
            id="p1",
            rotation=90.0,
            mask_expansion=0.15,
            is_pth=True,
        )
        _assert_pads_equal(p, o)

    def test_default_fields(self):
        p = Pad(
            center=Point(0.0, 0.0),
            shape="circle",
            size=(0.5, 0.5),
            net="N2",
            layer=2,
        )
        assert p.id == ""
        assert p.rotation == 0.0
        assert p.mask_expansion == 0.1
        assert p.is_pth is False

    def test_mutable_setattr(self):
        p = Pad(
            center=Point(0.0, 0.0),
            shape="circle",
            size=(0.5, 0.5),
            net="N2",
            layer=2,
        )
        p.mask_expansion = 0.2
        assert p.mask_expansion == 0.2

    def test_not_hashable(self):
        p = Pad(
            center=Point(0.0, 0.0),
            shape="circle",
            size=(0.5, 0.5),
            net="N2",
            layer=2,
        )
        with pytest.raises(TypeError):
            hash(p)

    def test_eq_identity(self):
        p1 = Pad(
            center=Point(1.0, 2.0),
            shape="rect",
            size=(1.6, 0.8),
            net="N1",
            layer=1,
        )
        p2 = Pad(
            center=Point(1.0, 2.0),
            shape="rect",
            size=(1.6, 0.8),
            net="N1",
            layer=1,
        )
        assert p1 == p2
        assert p1 != Pad(
            center=Point(1.0, 2.0),
            shape="rect",
            size=(1.6, 0.8),
            net="N1",
            layer=2,
        )

    def test_repr(self):
        p = Pad(
            center=Point(1.0, 2.0),
            shape="rect",
            size=(1.6, 0.8),
            net="N1",
            layer=1,
            id="p1",
        )
        r = repr(p)
        o = _OraclePad(
            center=_OraclePoint(1.0, 2.0),
            shape="rect",
            size=(1.6, 0.8),
            net="N1",
            layer=1,
            id="p1",
        )
        expected = repr(o)
        prod_name = _extract_class_name(r)
        r_norm = _normalize_repr(r, prod_name, "_OraclePad")
        r_norm = r_norm.replace("Point(", "_OraclePoint(")
        assert r_norm == expected, f"repr mismatch:\n  got: {r}\n  expected: {expected}"

    def test_radius(self):
        p = Pad(
            center=Point(0.0, 0.0),
            shape="rect",
            size=(3.0, 4.0),
            net="N1",
            layer=1,
        )
        _assert_float_bit_exact(p.radius, 2.5)  # hypot(3,4)/2 = 5/2

    def test_radius_random(self):
        import random

        rng = random.Random(20260810)
        for w, h in [(0.0, 0.0), (1.0, 1.0), (3.0, 4.0), (0.5, 2.0)] + [
            (round(rng.uniform(0.0, 10.0), 6), round(rng.uniform(0.0, 10.0), 6))
            for _ in range(30)
        ]:
            p = Pad(center=Point(0.0, 0.0), shape="rect", size=(w, h), net="N", layer=1)
            _assert_float_bit_exact(p.radius, _tg_oracle.pad_radius_py(w, h))


# ============================================================================
# Cross-type construction: Track stores Point fields
# ============================================================================


def test_track_stores_point_instances():
    """Track.start and Track.end should be Point instances (Rust pyclass)."""
    t = Track(
        start=Point(0.0, 0.0),
        end=Point(10.0, 0.0),
        width=0.5,
        net="N1",
        layer=1,
    )
    assert isinstance(t.start, Point)
    assert isinstance(t.end, Point)


def test_via_stores_point_instance():
    v = Via(center=Point(5.0, 5.0), diameter=0.6, drill=0.3, net="GND")
    assert isinstance(v.center, Point)


def test_pad_stores_point_instance():
    p = Pad(center=Point(1.0, 2.0), shape="rect", size=(1.6, 0.8), net="N1", layer=1)
    assert isinstance(p.center, Point)


# ============================================================================
# Regression: ensure the old nptyping references don't break
# ============================================================================


def test_to_array_returns_numpy():
    """Point.to_array() must return a numpy array."""
    p = Point(1.0, 2.0)
    arr = p.to_array()
    assert isinstance(arr, np.ndarray)
    np.testing.assert_array_equal(arr, np.array([1.0, 2.0]))


# ============================================================================
# Helper utilities
# ============================================================================



