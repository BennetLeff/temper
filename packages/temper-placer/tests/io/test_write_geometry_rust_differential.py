"""Differential test: Rust kicad-write geometry kernels
(``temper_io_types.kicad_write_geometry``) vs the pinned Python oracle.

Wave 4 — migrates the deterministic geometry/formatting kernels out of
``temper_placer/io/_write_tracks.py``, ``_write_zones.py``,
``_write_modules.py`` and ``placement_exporter.py``. See
``packages/temper-io-types/src/kicad_write_geometry.rs``'s module docstring
for what was and was not ported, and why.

The Rust symbols must reproduce the pre-migration implementations
bit-identically. The pre-migration code is pinned VERBATIM as the
``_oracle_*`` blocks below — copied from the modules AS COMMITTED at
``origin/main 47349a50`` (before this migration). They are the reference.
Floats are compared as exact bit patterns via ``float.hex()``; the emission
keys additionally compare ``repr()`` strings, because ``repr(key)`` is the
input to ``_stable_tstamp``'s sha256 and therefore to the written board's
object IDs.

RED before GREEN: this file is written and committed BEFORE
``kicad_write_geometry.rs`` is registered into the built extension, so
``temper_io_types.kicad_write_geometry`` does not exist and every test here
fails at collection (``AttributeError``). That failure is the proof the
differential was never vacuously green.

The delegation tests at the bottom are a SEPARATE proof from the
bit-exactness tests above: a green differential compares the oracle against
the Rust kernel directly and passes whether or not the SHIPPED modules
actually call it. Monkeypatching the Rust symbols to raise and calling the
shipped entry points is the only thing that proves the production code path
was rewired.
"""

from __future__ import annotations

import hashlib
import math
import uuid
from types import SimpleNamespace

import numpy as np
import pytest
import temper_io_types as _tio

from temper_placer.core.board import LAYER_NAME_TO_IDX, STANDARD_LAYER_ORDER
from temper_placer.geometry.kicad_transform import rotate_local_to_world
from temper_placer.io import _write_modules as shipped_modules
from temper_placer.io import _write_tracks as shipped_tracks
from temper_placer.io import _write_zones as shipped_zones
from temper_placer.io._write_types import PlacementUpdate
from temper_placer.io.placement_exporter import (
    positions_to_placements as shipped_positions_to_placements,
)

# Rust symbols under test — must exist or this file fails to collect (RED).
_GEOM = _tio.kicad_write_geometry

_STABLE_TSTAMP = _GEOM.stable_tstamp_py
_TRACE_KEY = _GEOM.trace_emission_key_py
_VIA_KEY = _GEOM.via_emission_key_py
_RESOLVE_NET = _GEOM.resolve_net_index_py
_RESOLVE_NET_DEFAULT = _GEOM.resolve_net_index_default_py
_NET_INDEX_MAP = _GEOM.build_net_name_to_index_map_py
_COMPONENT_BOUNDS = _GEOM.component_bounds_py
_ROT_DEG = _GEOM.rotation_index_to_degrees_py
_PLACEMENT_COORD = _GEOM.placement_coordinate_py

_UNRANKED_LAYER = len(STANDARD_LAYER_ORDER)


# ---------------------------------------------------------------------------
# VERBATIM oracle blocks — the pre-migration implementations, as committed at
# origin/main 47349a50. DO NOT EDIT — they are the reference.
# ---------------------------------------------------------------------------


def _oracle_stable_tstamp(kind: str, key: tuple) -> str:
    digest = hashlib.sha256(f"{kind}\x00{key!r}".encode()).digest()
    return str(uuid.UUID(bytes=digest[:16], version=4))


def _oracle_layer_rank(layer: object) -> tuple[int, str]:
    name = str(layer)
    idx = LAYER_NAME_TO_IDX.get(name)
    return (_UNRANKED_LAYER if idx is None else int(idx), name)


def _oracle_resolve_net_index(net: object, net_name_to_index: dict[str, int]) -> int:
    if net and net in net_name_to_index:
        return net_name_to_index[str(net)]
    return 0


def _oracle_trace_emission_key(route: object, net_name_to_index: dict[str, int]) -> tuple:
    net = route.net or ""
    return (
        _oracle_resolve_net_index(net, net_name_to_index),
        str(net),
        _oracle_layer_rank(route.layer),
        (float(route.start[0]), float(route.start[1])),
        (float(route.end[0]), float(route.end[1])),
        float(route.width),
    )


def _oracle_via_emission_key(via: object, net_name_to_index: dict[str, int]) -> tuple:
    net = via.net or ""
    return (
        _oracle_resolve_net_index(net, net_name_to_index),
        str(net),
        (float(via.position[0]), float(via.position[1])),
        float(via.drill),
        float(via.width),
        tuple(str(layer) for layer in via.layers),
        bool(getattr(via, "is_diff_pair", False)),
    )


def _oracle_component_bounds(fp_x: float, fp_y: float, fp_angle: float, pads) -> tuple:
    angle_rad = math.radians(fp_angle)

    x_min, y_min = float("inf"), float("inf")
    x_max, y_max = float("-inf"), float("-inf")

    for pad in pads:
        local_x = pad.position.X if pad.position else 0.0
        local_y = pad.position.Y if pad.position else 0.0

        if abs(fp_angle) > 0.1:
            rotated_x, rotated_y = rotate_local_to_world(local_x, local_y, angle_rad)
        else:
            rotated_x, rotated_y = local_x, local_y

        pad_w = pad.size.X if pad.size else 1.0
        pad_h = pad.size.Y if pad.size else 1.0

        abs_x = fp_x + rotated_x
        abs_y = fp_y + rotated_y

        x_min = min(x_min, abs_x - pad_w / 2)
        y_min = min(y_min, abs_y - pad_h / 2)
        x_max = max(x_max, abs_x + pad_w / 2)
        y_max = max(y_max, abs_y + pad_h / 2)

    return x_min, y_min, x_max, y_max


def _oracle_build_net_name_to_index_map(nets) -> dict[str, int]:
    net_map = {}
    for net in nets:
        if hasattr(net, "name") and hasattr(net, "number"):
            net_map[net.name] = net.number

    return net_map


def _oracle_zone_net_index(net_name: str, net_name_to_index: dict[str, int]) -> int:
    net_index = net_name_to_index.get(net_name, 0)
    return net_index


def _oracle_rotation_index_to_degrees(index: int) -> float:
    return float(index) * 90.0


def _oracle_positions_to_placements(
    positions,
    rotations,
    component_refs,
    origin=(0.0, 0.0),
) -> dict[str, PlacementUpdate]:
    n_components = len(component_refs)

    if positions.shape[0] != n_components:
        raise ValueError(
            f"Position count ({positions.shape[0]}) doesn't match component count ({n_components})"
        )

    if rotations.shape[0] != n_components:
        raise ValueError(
            f"Rotation count ({rotations.shape[0]}) doesn't match component count ({n_components})"
        )

    rotation_indices = np.argmax(rotations, axis=-1)

    placements: dict[str, PlacementUpdate] = {}

    for i, ref in enumerate(component_refs):
        x = float(positions[i, 0]) + origin[0]
        y = float(positions[i, 1]) + origin[1]

        rot_idx = int(rotation_indices[i])
        rotation_deg = _oracle_rotation_index_to_degrees(rot_idx)

        placements[ref] = PlacementUpdate(
            ref=ref,
            x=x,
            y=y,
            rotation=rotation_deg,
        )

    return placements


# ---------------------------------------------------------------------------
# canonicalization
# ---------------------------------------------------------------------------


def _f(value) -> str:
    """Bit-exact float key; ``None`` passes through unchanged."""
    return "None" if value is None else float(value).hex()


def _leaf(value):
    """A comparison key that pins both the VALUE and its concrete TYPE."""
    if isinstance(value, bool):
        return ("bool", value)
    if isinstance(value, float):
        return ("float", value.hex())
    if isinstance(value, int):
        return ("int", value)
    return (type(value).__name__, value)


def _canon_elt(value):
    if isinstance(value, tuple):
        return tuple(_canon_elt(v) for v in value)
    return _leaf(value)


def _canon_key(key):
    """Canonicalize an emission key into comparable plain tuples."""
    return tuple(_canon_elt(v) for v in key)


def assert_identical_keys(rust_key, py_key, label: str) -> None:
    """Bit-identical parity on both the value channel and the repr channel.

    ``repr`` is load-bearing, not cosmetic: ``_stable_tstamp`` feeds
    ``repr(key)`` into sha256, so a key that is equal-but-differently-repr'd
    would silently change every derived object ID in the written board.
    """
    assert repr(rust_key) == repr(py_key), f"{label}: key repr differs"
    assert _canon_key(rust_key) == _canon_key(py_key), f"{label}: key value differs"


# ---------------------------------------------------------------------------
# stable_tstamp
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "kind,key",
    [
        ("segment", (1, "GND", (0, "F.Cu"), (0.0, 20.0), (1.0, 20.0), 0.25)),
        ("via", (2, "VBUS", (40.0, 30.0), 0.3, 0.6, ("F.Cu", "B.Cu"), False)),
        ("segment", (0, "", (4, "Some.Weird.Layer"), (0.5, 0.5), (0.5, 1.5), 0.1)),
        ("via", (0, "", (0.0, 0.0), 0.2, 0.4, (), True)),
        # Float repr sensitivity: values that render differently than their
        # neighbours (trailing digits, .0 trimming, scientific notation).
        ("segment", (3, "AVDD", (1, "In1.Cu"), (1.2345678901234567, -0.5), (2.0, 3.5), 0.30000000000000004)),
        ("segment", (3, "AVDD", (1, "In1.Cu"), (1.0, 2.0), (3.0, 4.0), 0.5)),
        # A key whose repr contains characters the sha256 payload must carry
        # byte-for-byte (spaces, quotes, escapes in the net name).
        ("via", (0, "a'b\"c\\d", (1.0, 2.0), 0.3, 0.6, ("F.Cu",), False)),
    ],
)
def test_stable_tstamp_matches_oracle(kind, key):
    py_result = _oracle_stable_tstamp(kind, key)
    rust_result = _STABLE_TSTAMP(kind, key)
    assert rust_result == py_result
    # The UUID must be a genuine RFC 4122 v4, not a string that merely looks
    # like one.
    parsed = uuid.UUID(rust_result, version=4)
    assert parsed.variant == uuid.RFC_4122


def test_stable_tstamp_is_deterministic_and_kind_separated():
    key = (1, "GND", (0, "F.Cu"), (0.0, 0.0), (1.0, 0.0), 0.25)
    assert _STABLE_TSTAMP("segment", key) == _STABLE_TSTAMP("segment", key)
    # Domain separation: the track and via spaces must never collide.
    assert _STABLE_TSTAMP("segment", key) != _STABLE_TSTAMP("via", key)


# ---------------------------------------------------------------------------
# emission keys
# ---------------------------------------------------------------------------


def _route(net, layer, start, end, width):
    from temper_placer.core.board import Trace

    return Trace(start=start, end=end, width=width, layer=layer, net=net)


def _via(net, position, drill, width, layers, is_diff_pair=False):
    from temper_placer.core.board import Via

    return Via(
        position=position,
        drill=drill,
        width=width,
        layers=layers,
        net=net,
        is_diff_pair=is_diff_pair,
    )


NET_INDEX = {"": 0, "GND": 1, "VBUS": 2, "AVDD": 3}


@pytest.mark.parametrize(
    "net,layer,start,end,width",
    [
        ("GND", "F.Cu", (0.0, 20.0), (1.0, 20.0), 0.25),
        ("", "B.Cu", (0.0, 0.0), (0.0, 1.0), 0.1),
        (None, "In1.Cu", (1.5, 2.5), (3.5, 4.5), 0.3),
        ("UNKNOWN_NET", "In2.Cu", (-0.5, -0.5), (0.5, 0.5), 0.2),
        ("AVDD", "Some.Custom.Layer", (1.0, 2.0), (3.0, 4.0), 0.15),
        # numpy-typed geometry: `float(start[0])` must widen exactly.
        ("VBUS", "F.Cu", (np.float32(1.5), np.float64(2.25)), (np.float32(3.0), np.float64(4.5)), np.float32(0.25)),
    ],
)
def test_trace_emission_key_matches_oracle(net, layer, start, end, width):
    route = _route(net, layer, start, end, width)
    py_key = _oracle_trace_emission_key(route, NET_INDEX)
    rust_key = _TRACE_KEY(route, NET_INDEX, LAYER_NAME_TO_IDX, _UNRANKED_LAYER)
    assert_identical_keys(rust_key, py_key, "trace emission key")


def test_trace_emission_key_duck_typed_route_matches_oracle():
    """Routes may be any object exposing the five attributes — the kernel
    reads them through Python's protocol (str(), float(), __getitem__), so a
    plain namespace with numpy geometry behaves exactly like the oracle."""
    route = SimpleNamespace(
        net="GND",
        layer="F.Cu",
        start=np.array([0.0, 20.0]),
        end=(1.0, 20.0),
        width=0.25,
    )
    py_key = _oracle_trace_emission_key(route, NET_INDEX)
    rust_key = _TRACE_KEY(route, NET_INDEX, LAYER_NAME_TO_IDX, _UNRANKED_LAYER)
    assert_identical_keys(rust_key, py_key, "duck-typed trace emission key")


@pytest.mark.parametrize(
    "net,position,drill,width,layers,is_diff_pair",
    [
        ("GND", (10.0, 20.0), 0.3, 0.6, ("F.Cu", "B.Cu"), False),
        ("", (0.0, 0.0), 0.2, 0.4, (), True),
        (None, (1.5, 2.5), 0.25, 0.5, ("F.Cu", "In1.Cu", "In2.Cu", "B.Cu"), False),
        ("AVDD", (-3.0, 7.0), 0.3, 0.6, ("B.Cu", "F.Cu"), True),
        # numpy drill/width must widen through float() exactly.
        ("VBUS", (np.float32(1.0), np.float64(2.0)), np.float32(0.3), np.float64(0.6), ("F.Cu",), False),
    ],
)
def test_via_emission_key_matches_oracle(net, position, drill, width, layers, is_diff_pair):
    via = _via(net, position, drill, width, layers, is_diff_pair)
    py_key = _oracle_via_emission_key(via, NET_INDEX)
    rust_key = _VIA_KEY(via, NET_INDEX)
    assert_identical_keys(rust_key, py_key, "via emission key")


def test_via_emission_key_missing_is_diff_pair_defaults_false():
    """`bool(getattr(via, 'is_diff_pair', False))` must default to False for a
    duck-typed via without the attribute (the oracle's getattr default)."""
    via = SimpleNamespace(
        net="GND", position=(1.0, 2.0), drill=0.3, width=0.6, layers=["F.Cu", "B.Cu"]
    )
    py_key = _oracle_via_emission_key(via, NET_INDEX)
    rust_key = _VIA_KEY(via, NET_INDEX)
    assert_identical_keys(rust_key, py_key, "via emission key (no is_diff_pair)")


# ---------------------------------------------------------------------------
# layer_rank / resolve_net_index
# ---------------------------------------------------------------------------


def test_layer_rank_matches_oracle():
    for layer in ["F.Cu", "In1.Cu", "In2.Cu", "B.Cu", "Unknown.Layer", "", "F.cu"]:
        assert _oracle_layer_rank(layer) == (4 if layer not in ("F.Cu", "In1.Cu", "In2.Cu", "B.Cu") else {"F.Cu": 0, "In1.Cu": 1, "In2.Cu": 2, "B.Cu": 3}[layer], layer)


def test_resolve_net_index_matches_oracle():
    for net in ["GND", "", "UNKNOWN", None]:
        assert _RESOLVE_NET(net, NET_INDEX) == _oracle_resolve_net_index(net, NET_INDEX)


def test_resolve_net_index_default_matches_oracle():
    for net_name in ["GND", "UNKNOWN", "", "AVDD"]:
        assert _RESOLVE_NET_DEFAULT(net_name, NET_INDEX) == _oracle_zone_net_index(net_name, NET_INDEX)


# ---------------------------------------------------------------------------
# component bounds (_write_modules)
# ---------------------------------------------------------------------------


def _pad(local_x, local_y, pad_w, pad_h, position=None, size=None):
    return SimpleNamespace(
        position=position if position is not None else SimpleNamespace(X=local_x, Y=local_y),
        size=size if size is not None else SimpleNamespace(X=pad_w, Y=pad_h),
    )


def _pre_rotate(pad, fp_angle):
    """The shim's rotation step: apply the SSOT only when |angle| > 0.1."""
    local_x = pad.position.X if pad.position else 0.0
    local_y = pad.position.Y if pad.position else 0.0
    pad_w = pad.size.X if pad.size else 1.0
    pad_h = pad.size.Y if pad.size else 1.0
    if abs(fp_angle) > 0.1:
        rotated_x, rotated_y = rotate_local_to_world(local_x, local_y, math.radians(fp_angle))
    else:
        rotated_x, rotated_y = local_x, local_y
    return (rotated_x, rotated_y, pad_w, pad_h)


def _bounds_via_rust(fp_x, fp_y, fp_angle, pads):
    return _COMPONENT_BOUNDS(fp_x, fp_y, [_pre_rotate(p, fp_angle) for p in pads])


@pytest.mark.parametrize(
    "fp_x,fp_y,fp_angle,pads",
    [
        (10.0, 20.0, 0.0, [_pad(0.0, 0.0, 1.0, 1.0)]),
        (10.0, 20.0, 0.0, [_pad(-1.0, -1.0, 1.0, 1.0), _pad(1.0, 1.0, 1.0, 1.0)]),
        (0.0, 0.0, 90.0, [_pad(0.0, 0.0, 2.0, 1.0)]),
        (5.0, 5.0, 45.0, [_pad(1.0, 1.0, 0.5, 0.5), _pad(-1.0, -1.0, 0.5, 0.5)]),
        (1.0, 2.0, 0.05, [_pad(0.5, 0.5, 1.0, 1.0)]),  # below the 0.1 threshold
        (1.0, 2.0, 0.1, [_pad(0.5, 0.5, 1.0, 1.0)]),  # exactly at the threshold
        # Pad with a missing position (defaults to 0.0) and a missing size
        # (defaults to 1.0).
        (0.0, 0.0, 0.0, [_pad(0.0, 0.0, 0.0, 0.0, position=None, size=None)]),
        (0.0, 0.0, 180.0, [_pad(1.0, 1.0, 0.3, 0.7)]),
        # NaN pad position: CPython min/max keep the first argument (B5).
        (1.0, 1.0, 0.0, [_pad(float("nan"), 0.0, 0.5, 0.5)]),
        (1.0, 1.0, 0.0, []),  # empty pad list -> inf/-inf bounds
        (123.456, -78.9, 33.3, [_pad(12.3, -4.5, 2.7, 1.1), _pad(-9.9, 8.8, 0.2, 0.2)]),
    ],
)
def test_component_bounds_matches_oracle(fp_x, fp_y, fp_angle, pads):
    py_bounds = _oracle_component_bounds(fp_x, fp_y, fp_angle, pads)
    rust_bounds = _bounds_via_rust(fp_x, fp_y, fp_angle, pads)
    assert tuple(_f(v) for v in py_bounds) == tuple(_f(v) for v in rust_bounds)


# ---------------------------------------------------------------------------
# net index map (_write_zones)
# ---------------------------------------------------------------------------


def test_build_net_name_to_index_map_matches_oracle():
    nets = [
        SimpleNamespace(name="GND", number=1),
        SimpleNamespace(name="VBUS", number=2),
        SimpleNamespace(name="AVDD", number=3),
        SimpleNamespace(number=0),  # no name -> skipped
        SimpleNamespace(name=""),  # no number -> skipped
        SimpleNamespace(name="GND", number=99),  # duplicate -> last wins
    ]
    py_map = _oracle_build_net_name_to_index_map(nets)
    rust_map = _NET_INDEX_MAP(nets)
    assert rust_map == py_map


def test_build_net_name_to_index_map_empty():
    assert _NET_INDEX_MAP([]) == {}
    assert _oracle_build_net_name_to_index_map([]) == {}


# ---------------------------------------------------------------------------
# placement exporter
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("index", [0, 1, 2, 3, 7, -1])
def test_rotation_index_to_degrees_matches_oracle(index):
    py_result = _oracle_rotation_index_to_degrees(index)
    rust_result = _ROT_DEG(index)
    assert _f(rust_result) == _f(py_result)


@pytest.mark.parametrize(
    "x,y,origin",
    [
        (10.0, 20.0, (0.0, 0.0)),
        (10.0, 20.0, (100.0, 50.0)),
        (-3.5, 7.25, (1.1, -2.2)),
        (0.1, 0.2, (0.3, 0.4)),
        (1e-300, -1e300, (1e-300, 1e300)),
    ],
)
def test_placement_coordinate_matches_oracle(x, y, origin):
    rx, ry = _PLACEMENT_COORD(x, y, origin[0], origin[1])
    assert _f(rx) == _f(x + origin[0])
    assert _f(ry) == _f(y + origin[1])


def test_positions_to_placements_matches_oracle():
    """The shipped `positions_to_placements` must reproduce the verbatim
    pre-migration function (numpy inputs included) bit for bit."""
    positions = np.array(
        [
            [10.0, 20.0],
            [30.0, 40.0],
            [-1.5, 2.5],
        ]
    )
    rotations = np.array(
        [
            [1.0, 0.0, 0.0, 0.0],
            [0.0, 0.0, 1.0, 0.0],
            [0.1, 0.2, 0.3, 0.4],
        ]
    )
    refs = ["U1", "R1", "C1"]
    origin = (100.0, 50.0)

    py_placements = _oracle_positions_to_placements(positions, rotations, refs, origin)
    rust_placements = shipped_positions_to_placements(positions, rotations, refs, origin)

    assert set(rust_placements) == set(py_placements)
    for ref in refs:
        py_pu = py_placements[ref]
        rust_pu = rust_placements[ref]
        assert rust_pu.ref == py_pu.ref
        assert _f(rust_pu.x) == _f(py_pu.x), ref
        assert _f(rust_pu.y) == _f(py_pu.y), ref
        assert _f(rust_pu.rotation) == _f(py_pu.rotation), ref


def test_positions_to_placements_empty():
    positions = np.zeros((0, 2))
    rotations = np.zeros((0, 4))
    assert shipped_positions_to_placements(positions, rotations, []) == {}


# ---------------------------------------------------------------------------
# Shipped-module delegation proof -- NOT a bit-exactness check.
# ---------------------------------------------------------------------------


def test_stable_tstamp_delegates_to_rust():
    sentinel = RuntimeError("REACHED_RUST_STABLE_TSTAMP")

    def boom(*_a, **_k):
        raise sentinel

    original = _STABLE_TSTAMP
    _GEOM.stable_tstamp_py = boom
    try:
        with pytest.raises(RuntimeError, match="REACHED_RUST_STABLE_TSTAMP"):
            shipped_tracks._stable_tstamp("segment", (1, "GND", (0, "F.Cu")))
    finally:
        _GEOM.stable_tstamp_py = original


def test_trace_emission_key_delegates_to_rust():
    sentinel = RuntimeError("REACHED_RUST_TRACE_KEY")

    def boom(*_a, **_k):
        raise sentinel

    original = _TRACE_KEY
    _GEOM.trace_emission_key_py = boom
    route = _route("GND", "F.Cu", (0.0, 0.0), (1.0, 1.0), 0.25)
    try:
        with pytest.raises(RuntimeError, match="REACHED_RUST_TRACE_KEY"):
            shipped_tracks._trace_emission_key(route, NET_INDEX)
    finally:
        _GEOM.trace_emission_key_py = original


def test_via_emission_key_delegates_to_rust():
    sentinel = RuntimeError("REACHED_RUST_VIA_KEY")

    def boom(*_a, **_k):
        raise sentinel

    original = _VIA_KEY
    _GEOM.via_emission_key_py = boom
    via = _via("GND", (1.0, 2.0), 0.3, 0.6, ("F.Cu", "B.Cu"))
    try:
        with pytest.raises(RuntimeError, match="REACHED_RUST_VIA_KEY"):
            shipped_tracks._via_emission_key(via, NET_INDEX)
    finally:
        _GEOM.via_emission_key_py = original


def test_component_bounds_delegates_to_rust():
    sentinel = RuntimeError("REACHED_RUST_COMPONENT_BOUNDS")

    def boom(*_a, **_k):
        raise sentinel

    original = _COMPONENT_BOUNDS
    _GEOM.component_bounds_py = boom
    try:
        with pytest.raises(RuntimeError, match="REACHED_RUST_COMPONENT_BOUNDS"):
            shipped_modules._component_bounds(0.0, 0.0, 0.0, [(0.0, 0.0, 1.0, 1.0)])
    finally:
        _GEOM.component_bounds_py = original


def test_build_net_index_map_delegates_to_rust():
    sentinel = RuntimeError("REACHED_RUST_NET_INDEX_MAP")

    def boom(*_a, **_k):
        raise sentinel

    original = _NET_INDEX_MAP
    _GEOM.build_net_name_to_index_map_py = boom
    try:
        with pytest.raises(RuntimeError, match="REACHED_RUST_NET_INDEX_MAP"):
            shipped_zones._net_index_map_from_nets([SimpleNamespace(name="GND", number=1)])
    finally:
        _GEOM.build_net_name_to_index_map_py = original


def test_positions_to_placements_delegates_to_rust():
    sentinel = RuntimeError("REACHED_RUST_PLACEMENT_COORD")

    def boom(*_a, **_k):
        raise sentinel

    original = _PLACEMENT_COORD
    _GEOM.placement_coordinate_py = boom
    positions = np.array([[10.0, 20.0]])
    rotations = np.array([[1.0, 0.0, 0.0, 0.0]])
    try:
        with pytest.raises(RuntimeError, match="REACHED_RUST_PLACEMENT_COORD"):
            shipped_positions_to_placements(positions, rotations, ["U1"])
    finally:
        _GEOM.placement_coordinate_py = original
