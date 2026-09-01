"""Property-based tests for the migrated kicad-write geometry kernels.

Wave 4 — companion to ``test_write_geometry_rust_differential.py`` (which
pins fixed inputs); this suite searches the input space for a divergence the
fixtures did not think of. The verification unit is the CLUSTER: the four
write/export modules ``io/_write_tracks.py``, ``io/_write_zones.py``,
``io/_write_modules.py`` and ``io/placement_exporter.py``, whose kernels live
in ``temper-io-types::kicad_write_geometry``.

Module → property map (G4 condition 1):

- ``_write_tracks.py``    P1, P2 (stable_tstamp), P3 (net-index ordering),
                          P4 (layer stackup ordering), MR2, MR3
- ``_write_modules.py``   P5 (bounds containment), P6 (single-pad exactness),
                          MR1 (size-growth monotonicity)
- ``placement_exporter.py`` P7 (origin add), P8 (rotation degrees), MR4
- ``_write_zones.py``     P9 (skip + last-wins), MR5 (order independence)

Properties:

- P1. ``stable_tstamp`` is a total function over distinct keys: distinct keys
  (with equal reprs being the identity) map to distinct UUIDs, and repeated
  application is deterministic. A constant-returning kernel satisfies none.
- P2. The derived string is a genuine RFC 4122 version-4 UUID: the version
  nibble is stamped in and the variant is RFC 4122, regardless of the digest.
  A kernel that merely renders a sha256 (no version stamping) fails.
- P3. Trace emission keys order by BOARD NET INDEX first, not by net name: for
  any net-name→index assignment, ``key(n1) < key(n2)`` iff ``index[n1] <
  index[n2]`` (name order may disagree; that is the point).
- P4. Within a net, trace emission keys order by physical STACKUP position
  (F.Cu < In1.Cu < In2.Cu < B.Cu), not lexicographic layer name (B.Cu < F.Cu
  < ...). A lexicographic-layer mutant fails.
- P5. The component bounds contain every pad: each pad's world-space
  half-extent box lies inside ``[x_min, x_max] × [y_min, y_max]``. A
  fixed-box kernel fails for any pad outside it.
- P6. Single-pad bounds are bit-exact: with a zero angle the bounds equal
  ``(fp + local ± size/2)`` exactly (same operation order, IEEE doubles). A
  margin-adding mutant fails.
- P7. ``placement_coordinate`` adds the origin bit-exactly: the returned pair
  equals ``x + origin_x`` / ``y + origin_y`` on the exact bits. An
  origin-ignoring mutant fails.
- P8. ``rotation_index_to_degrees`` maps 0..3 to exactly 0/90/180/270. A
  wrong-multiplier mutant fails.
- P9. The net-index map skips nets missing ``name`` or ``number`` and resolves
  duplicate names last-wins. A first-wins mutant fails.

Metamorphic relations (R1d), each honestly bounded:

- MR1. Component-bounds size-growth monotonicity (exact, no float caveat):
  growing a pad's width/height can only shrink ``x_min``/``y_min`` and grow
  ``x_max``/``y_max`` — ``min``/``max`` are monotone in their arguments.
- MR2. Emission-key permutation invariance (exact): the sorted key order is a
  pure function of the route set, so permuting the input list leaves the
  sorted-by-key order unchanged. An insertion-index-dependent key fails.
- MR3. ``stable_tstamp`` key-class invariance (exact): keys that are ``==``
  (same repr) produce equal UUIDs; keys whose reprs differ produce different
  UUIDs — the digest is over the repr, so the map is 1:1 on reprs.
- MR4. Placement-origin associativity (bounded: exact for dyadic halves, where
  every partial sum is exact): applying origin o1 then o2 equals applying
  ``o1 + o2`` once. An origin-drop mutant fails.
- MR5. Net-index-map order independence (bounded to distinct names, where the
  map is a pure function of the assignment): reordering the pairs leaves the
  map unchanged. Duplicate names are excluded — last-wins is positional by
  design (P9 pins it against a fixed-order list). A last-pair-only mutant
  fails.

Every property carries a G4 vacuity mutant through the ``_kernels``
indirection, and every MR carries a breakability test proving it is not
vacuously satisfied.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from temper_io_types import kicad_write_geometry as _GEOM

from temper_placer.core.board import Trace
from temper_placer.geometry.kicad_transform import rotate_local_to_world
from temper_placer.io import _write_modules as shipped_modules
from temper_placer.io import _write_tracks as shipped_tracks
from temper_placer.io.placement_exporter import (
    rotation_index_to_degrees as shipped_rotation_index_to_degrees,
)

MAX_EXAMPLES = 40
SETTINGS = settings(
    max_examples=MAX_EXAMPLES,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow],
)

# ---------------------------------------------------------------------------
# strategies
# ---------------------------------------------------------------------------

_COORD = st.floats(min_value=-100.0, max_value=100.0, allow_nan=False, allow_infinity=False)
_DIM = st.floats(min_value=0.05, max_value=10.0, allow_nan=False, allow_infinity=False)
_NAME = st.text(st.sampled_from(list("abcXYZ019_.-")), min_size=1, max_size=6)
_LAYERS = ["F.Cu", "In1.Cu", "In2.Cu", "B.Cu"]


def _route(net: str, layer: str = "F.Cu", start=(0.0, 0.0), end=(1.0, 1.0), width: float = 0.25):
    return Trace(start=start, end=end, width=width, layer=layer, net=net)


def _pad(local_x, local_y, pad_w, pad_h, position=None, size=None):
    return SimpleNamespace(
        position=position if position is not None else SimpleNamespace(X=local_x, Y=local_y),
        size=size if size is not None else SimpleNamespace(X=pad_w, Y=pad_h),
    )


@st.composite
def _keys(draw):
    i = draw(st.integers(min_value=0, max_value=1000))
    name = draw(_NAME)
    x = draw(_COORD)
    y = draw(_COORD)
    w = draw(_DIM)
    return (i, name, x, y, w)


@st.composite
def _pads(draw, min_size=1, max_size=5):
    n = draw(st.integers(min_value=min_size, max_value=max_size))
    return [_pad(draw(_COORD), draw(_COORD), draw(_DIM), draw(_DIM)) for _ in range(n)]


@st.composite
def _net_pairs(draw):
    """(has_name, name, has_number, number) tuples where a missing attribute
    is represented by the net object simply not carrying it."""
    has_name = draw(st.booleans())
    has_number = draw(st.booleans())
    name = draw(_NAME) if has_name else ""
    number = draw(st.integers(min_value=0, max_value=9))
    return (has_name, name, has_number, number)


def _net_from_pair(pair):
    has_name, name, has_number, number = pair
    d = {}
    if has_name:
        d["name"] = name
    if has_number:
        d["number"] = number
    return SimpleNamespace(**d)


def _expected_net_map(pairs):
    expected = {}
    for has_name, name, has_number, number in pairs:
        if has_name and has_number:
            expected[name] = number
    return expected


# ---------------------------------------------------------------------------
# kernel indirection (G4 vacuity-guard seam)
# ---------------------------------------------------------------------------


class _Kernels:
    def __init__(self):
        self.stable_tstamp = shipped_tracks._stable_tstamp
        self.trace_key = shipped_tracks._trace_emission_key
        self.bounds = shipped_modules._component_bounds
        self.placement_coord = _GEOM.placement_coordinate_py
        self.rot_deg = shipped_rotation_index_to_degrees
        self.net_index_map = _GEOM.build_net_name_to_index_map_py


_kernels = _Kernels()

_KERNEL_NAMES = ("stable_tstamp", "trace_key", "bounds", "placement_coord", "rot_deg", "net_index_map")


@pytest.fixture
def _restore_kernels():
    saved = {name: getattr(_kernels, name) for name in _KERNEL_NAMES}
    yield
    for name, fn in saved.items():
        setattr(_kernels, name, fn)


def _assert_property_fails(property_fn, *args):
    """Run a hypothesis-wrapped property's inner test and require a failure.

    A mutant that the property tolerates means the property is vacuous.
    """
    with pytest.raises((AssertionError, ValueError, TypeError, KeyError, AttributeError, IndexError)):
        property_fn.hypothesis.inner_test(*args)


# ---------------------------------------------------------------------------
# P1 / P2 — stable_tstamp
# ---------------------------------------------------------------------------


@SETTINGS
@given(
    kind=st.sampled_from(["segment", "via"]),
    keys=st.lists(_keys(), min_size=2, max_size=8, unique_by=lambda k: repr(k)),
)
def test_p1_stable_tstamp_unique_and_deterministic(kind, keys):
    """P1: distinct keys map to distinct UUIDs; repeated application agrees."""
    stamps = [_kernels.stable_tstamp(kind, k) for k in keys]
    assert len(set(stamps)) == len(stamps), f"distinct keys collided: {keys} -> {stamps}"
    for k in keys:
        assert _kernels.stable_tstamp(kind, k) in stamps


@SETTINGS
@given(kind=st.sampled_from(["segment", "via"]), key=_keys())
def test_p2_stable_tstamp_is_rfc4122_version4(kind, key):
    """P2: the string parses as an RFC 4122 v4 UUID with the version nibble."""
    s = _kernels.stable_tstamp(kind, key)
    parsed = uuid.UUID(s, version=4)
    assert parsed.variant == uuid.RFC_4122
    assert s[14] == "4"


def test_p1_fails_for_constant_kernel(_restore_kernels):
    _kernels.stable_tstamp = lambda _kind, _key: "00000000-0000-0000-0000-000000000000"
    _assert_property_fails(
        test_p1_stable_tstamp_unique_and_deterministic,
        "segment",
        [(0, "a", 1.0, 2.0, 0.5), (1, "b", 3.0, 4.0, 0.5)],
    )


def test_p2_fails_for_unstamped_kernel(_restore_kernels):
    _kernels.stable_tstamp = lambda _kind, _key: "00000000-0000-0000-0000-000000000000"
    _assert_property_fails(
        test_p2_stable_tstamp_is_rfc4122_version4,
        "segment",
        (0, "a", 1.0, 2.0, 0.5),
    )


# ---------------------------------------------------------------------------
# P3 — net-index ordering
# ---------------------------------------------------------------------------


@SETTINGS
@given(indices=st.permutations(list(range(4))))
def test_p3_trace_keys_order_by_net_index(indices):
    """P3: keys order by board net index, whatever the net names say."""
    names = ["GND", "VBUS", "AVDD", "5V"]
    mapping = dict(zip(names, indices))
    for i in range(4):
        for j in range(4):
            ni, nj = mapping[names[i]], mapping[names[j]]
            if ni == nj:
                continue
            ki = _kernels.trace_key(_route(names[i]), mapping)
            kj = _kernels.trace_key(_route(names[j]), mapping)
            assert (ki < kj) == (ni < nj), (
                f"keys for {names[i]}(idx {ni}) / {names[j]}(idx {nj}) did not order by net index"
            )


def test_p3_fails_for_name_ordering_kernel(_restore_kernels):
    def _by_name(route, net_name_to_index):
        net = route.net or ""
        return (net,)

    _kernels.trace_key = _by_name
    _assert_property_fails(
        test_p3_trace_keys_order_by_net_index,
        [0, 1, 2, 3],  # GND<VBUS<AVDD<5V by index; AVDD/5V disagree lexically
    )


# ---------------------------------------------------------------------------
# P4 — layer stackup ordering
# ---------------------------------------------------------------------------


@SETTINGS
@given(perm=st.permutations(list(range(4))))
def test_p4_trace_keys_order_layers_by_stackup(perm):
    """P4: within a net, layer order is the physical stackup, not the name."""
    routes = [_route("GND", layer=_LAYERS[i]) for i in perm]
    keyed = sorted((_kernels.trace_key(r, {"GND": 1}), r.layer) for r in routes)
    assert [layer for _, layer in keyed] == _LAYERS, (
        "sorted-by-key layer order is not F.Cu < In1.Cu < In2.Cu < B.Cu"
    )


def test_p4_fails_for_lexicographic_layer_kernel(_restore_kernels):
    def _lex_layer(route, net_name_to_index):
        net = route.net or ""
        return (net, str(route.layer))

    _kernels.trace_key = _lex_layer
    _assert_property_fails(
        test_p4_trace_keys_order_layers_by_stackup,
        [2, 0, 3, 1],  # scrambled input; lexicographic order would be B.Cu first
    )


# ---------------------------------------------------------------------------
# P5 / P6 — component bounds
# ---------------------------------------------------------------------------


def _pad_tuple(p):
    """Project a kiutils-shaped pad onto the production tuple contract."""
    return (
        p.position.X if p.position else 0.0,
        p.position.Y if p.position else 0.0,
        p.size.X if p.size else 1.0,
        p.size.Y if p.size else 1.0,
    )


def _world_pad(pad, fp_angle):
    lx = pad.position.X if pad.position else 0.0
    ly = pad.position.Y if pad.position else 0.0
    if abs(fp_angle) > 0.1:
        import math

        rx, ry = rotate_local_to_world(lx, ly, math.radians(fp_angle))
    else:
        rx, ry = lx, ly
    return (rx, ry)


@SETTINGS
@given(
    fp_x=_COORD,
    fp_y=_COORD,
    fp_angle=st.floats(min_value=-180.0, max_value=180.0, allow_nan=False, allow_infinity=False),
    pads=_pads(),
)
def test_p5_component_bounds_contain_every_pad(fp_x, fp_y, fp_angle, pads):
    """P5: every pad's world half-extent box is inside the returned bounds."""
    x_min, y_min, x_max, y_max = _kernels.bounds(
        fp_x, fp_y, fp_angle, [_pad_tuple(p) for p in pads]
    )
    for pad in pads:
        rx, ry = _world_pad(pad, fp_angle)
        w = pad.size.X if pad.size else 1.0
        h = pad.size.Y if pad.size else 1.0
        assert x_min <= fp_x + rx - w / 2
        assert y_min <= fp_y + ry - h / 2
        assert fp_x + rx + w / 2 <= x_max
        assert fp_y + ry + h / 2 <= y_max


@SETTINGS
@given(fp_x=_COORD, fp_y=_COORD, lx=_COORD, ly=_COORD, w=_DIM, h=_DIM)
def test_p6_single_pad_bounds_bit_exact(fp_x, fp_y, lx, ly, w, h):
    """P6: at a zero angle the single-pad bounds are the exact closed form."""
    pad = _pad(lx, ly, w, h)
    x_min, y_min, x_max, y_max = _kernels.bounds(fp_x, fp_y, 0.0, [_pad_tuple(pad)])
    assert x_min == fp_x + lx - w / 2
    assert y_min == fp_y + ly - h / 2
    assert x_max == fp_x + lx + w / 2
    assert y_max == fp_y + ly + h / 2


def test_p5_fails_for_fixed_box_kernel(_restore_kernels):
    _kernels.bounds = lambda *_a, **_k: (0.0, 0.0, 1.0, 1.0)
    _assert_property_fails(
        test_p5_component_bounds_contain_every_pad,
        50.0, 50.0, 0.0, [_pad(10.0, 10.0, 1.0, 1.0)],
    )


def test_p6_fails_for_margin_adding_kernel(_restore_kernels):
    def _margined(fp_x, fp_y, fp_angle, pads):
        return (fp_x - 0.5, fp_y - 0.5, fp_x + 0.5, fp_y + 0.5)

    _kernels.bounds = _margined
    _assert_property_fails(
        test_p6_single_pad_bounds_bit_exact,
        1.0, 2.0, 3.0, 4.0, 1.0, 1.0,
    )


# ---------------------------------------------------------------------------
# P7 / P8 — placement exporter
# ---------------------------------------------------------------------------


@SETTINGS
@given(x=_COORD, y=_COORD, ox=_COORD, oy=_COORD)
def test_p7_placement_coordinate_adds_origin_bit_exactly(x, y, ox, oy):
    """P7: the kernel's pair equals the plain Python sum on the exact bits."""
    rx, ry = _kernels.placement_coord(x, y, ox, oy)
    assert rx == x + ox
    assert ry == y + oy


@SETTINGS
@given(idx=st.integers(min_value=0, max_value=3))
def test_p8_rotation_index_to_degrees_is_exact(idx):
    """P8: 0..3 map to exactly 0/90/180/270 degrees."""
    assert _kernels.rot_deg(idx) == idx * 90.0


def test_p7_fails_for_origin_ignoring_kernel(_restore_kernels):
    _kernels.placement_coord = lambda x, y, _ox, _oy: (x, y)
    _assert_property_fails(test_p7_placement_coordinate_adds_origin_bit_exactly, 10.0, 20.0, 5.0, 7.0)


def test_p8_fails_for_wrong_multiplier_kernel(_restore_kernels):
    _kernels.rot_deg = lambda idx: float(idx) * 45.0
    _assert_property_fails(test_p8_rotation_index_to_degrees_is_exact, 2)


# ---------------------------------------------------------------------------
# P9 — net index map
# ---------------------------------------------------------------------------


@SETTINGS
@given(pairs=st.lists(_net_pairs(), min_size=0, max_size=10))
def test_p9_net_index_map_skips_and_last_wins(pairs):
    """P9: nets missing name/number are skipped; duplicates resolve last-wins."""
    nets = [_net_from_pair(p) for p in pairs]
    result = _kernels.net_index_map(nets)
    assert dict(result) == _expected_net_map(pairs)


def test_p9_fails_for_first_wins_kernel(_restore_kernels):
    def _first_wins(nets):
        out = {}
        for net in nets:
            if hasattr(net, "name") and hasattr(net, "number"):
                out.setdefault(net.name, net.number)
        return out

    _kernels.net_index_map = _first_wins
    _assert_property_fails(
        test_p9_net_index_map_skips_and_last_wins,
        [(True, "GND", True, 1), (True, "GND", True, 2)],
    )


# ---------------------------------------------------------------------------
# MR1 — bounds size-growth monotonicity (exact)
# ---------------------------------------------------------------------------


@SETTINGS
@given(fp_x=_COORD, fp_y=_COORD, fp_angle=_COORD, pads=_pads(min_size=1, max_size=3), growth=_DIM)
def test_mr1_pad_growth_never_shrinks_bounds(fp_x, fp_y, fp_angle, pads, growth):
    base = _kernels.bounds(fp_x, fp_y, fp_angle, [_pad_tuple(p) for p in pads])
    grown_pads = [
        _pad(p.position.X, p.position.Y, p.size.X + growth, p.size.Y + growth) for p in pads
    ]
    grown = _kernels.bounds(fp_x, fp_y, fp_angle, [_pad_tuple(p) for p in grown_pads])
    assert grown[0] <= base[0] + 1e-12  # x_min can only shrink (or stay)
    assert grown[1] <= base[1] + 1e-12  # y_min
    assert grown[2] >= base[2] - 1e-12  # x_max can only grow
    assert grown[3] >= base[3] - 1e-12  # y_max


def test_mr1_breakable(_restore_kernels):
    def _shrinking(fp_x, fp_y, fp_angle, pads):
        max_w = max((p.size.X if p.size else 1.0) for p in pads)
        max_h = max((p.size.Y if p.size else 1.0) for p in pads)
        return (fp_x - max_w, fp_y - max_h, fp_x - max_w, fp_y - max_h)

    _kernels.bounds = _shrinking
    _assert_property_fails(
        test_mr1_pad_growth_never_shrinks_bounds,
        0.0, 0.0, 0.0, [_pad(10.0, 10.0, 1.0, 1.0)], 2.0,
    )


# ---------------------------------------------------------------------------
# MR2 — emission-key permutation invariance (exact)
# ---------------------------------------------------------------------------


@SETTINGS
@given(nets=st.lists(st.sampled_from(["GND", "VBUS", "AVDD"]), min_size=1, max_size=6))
def test_mr2_sorted_key_order_is_input_order_invariant(nets):
    mapping = {"GND": 1, "VBUS": 2, "AVDD": 3}
    routes = [_route(net) for net in nets]
    forward = sorted((_kernels.trace_key(r, mapping), r) for r in routes)
    reverse = sorted((_kernels.trace_key(r, mapping), r) for r in reversed(routes))
    assert forward == reverse


def test_mr2_breakable(_restore_kernels):
    counter = [0]

    def _order_sensitive(route, net_name_to_index):
        counter[0] += 1
        return (route.net or "", counter[0])

    _kernels.trace_key = _order_sensitive
    _assert_property_fails(
        test_mr2_sorted_key_order_is_input_order_invariant,
        ["GND", "AVDD", "VBUS"],
    )


# ---------------------------------------------------------------------------
# MR3 — stable_tstamp key-class invariance (exact)
# ---------------------------------------------------------------------------


@SETTINGS
@given(kind=st.sampled_from(["segment", "via"]), key=_keys())
def test_mr3_stable_tstamp_is_a_function_of_the_repr(kind, key):
    twin = tuple(list(key)[:])
    assert _kernels.stable_tstamp(kind, key) == _kernels.stable_tstamp(kind, twin)
    assert _kernels.stable_tstamp(kind, key) != _kernels.stable_tstamp("via" if kind == "segment" else "segment", key)
    # A key that differs in any element (different repr) must differ.
    other = list(key)
    other[-1] = other[-1] + 1.0
    assert _kernels.stable_tstamp(kind, key) != _kernels.stable_tstamp(kind, tuple(other))


def test_mr3_breakable(_restore_kernels):
    _kernels.stable_tstamp = lambda _kind, _key: "11111111-1111-4111-8111-111111111111"
    _assert_property_fails(test_mr3_stable_tstamp_is_a_function_of_the_repr, "segment", (0, "a", 1.0, 2.0, 0.5))


# ---------------------------------------------------------------------------
# MR4 — placement-origin associativity (exact for dyadic halves)
# ---------------------------------------------------------------------------


_DYADIC = st.integers(min_value=-100, max_value=100).map(lambda n: n / 2)


@SETTINGS
@given(
    x=_DYADIC, y=_DYADIC,
    o1x=_DYADIC, o1y=_DYADIC,
    o2x=_DYADIC, o2y=_DYADIC,
)
def test_mr4_placement_origin_associates(x, y, o1x, o1y, o2x, o2y):
    """MR4 (bounded: dyadic halves, exact): o1 then o2 == o1+o2 once."""
    once = _kernels.placement_coord(x, y, o1x + o2x, o1y + o2y)
    step = _kernels.placement_coord(*_kernels.placement_coord(x, y, o1x, o1y), o2x, o2y)
    assert once == step


def test_mr4_breakable(_restore_kernels):
    _kernels.placement_coord = lambda _x, _y, ox, oy: (ox, oy)
    _assert_property_fails(test_mr4_placement_origin_associates, 10.0, 20.0, 5.0, 7.0, 3.0, 1.0)


# ---------------------------------------------------------------------------
# MR5 — net-index map order independence (exact)
# ---------------------------------------------------------------------------


@SETTINGS
@given(
    pairs=st.lists(
        _net_pairs(),
        min_size=0,
        max_size=8,
        unique_by=lambda p: (p[0], p[1] if p[0] else None),
    )
)
def test_mr5_net_index_map_is_order_independent(pairs):
    """MR5 (bounded to DISTINCT names, where the map is a pure function of the
    name→number assignment): the map ignores insertion order. With a duplicate
    name the map is deliberately order-dependent (last-wins is a positional
    semantic — P9 pins it against a fixed-order list)."""
    a = _kernels.net_index_map([_net_from_pair(p) for p in pairs])
    b = _kernels.net_index_map([_net_from_pair(p) for p in reversed(pairs)])
    assert dict(a) == dict(b) == _expected_net_map(pairs)


def test_mr5_breakable(_restore_kernels):
    def _last_pair_only(nets):
        if not nets:
            return {}
        last = nets[-1]
        return {last.name: last.number} if hasattr(last, "name") else {}

    _kernels.net_index_map = _last_pair_only
    _assert_property_fails(
        test_mr5_net_index_map_is_order_independent,
        [(True, "GND", True, 1), (True, "VBUS", True, 2), (True, "AVDD", True, 3)],
    )
