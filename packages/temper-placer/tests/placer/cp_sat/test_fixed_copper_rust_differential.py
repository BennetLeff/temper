"""R1a differential: `fixed_copper.py`'s pad-rotation / half-extent /
item-geometry / exact-clearance-oracle kernels vs the pinned Python oracle.

Wave 4 -- carve-out of `fixed_copper.py` from the `placer/cp_sat/**`
whole-subtree JUSTIFIED-KEEP, per `docs/evidence/2026-08-06-never-port-triage.md`
section 4 ("the geometry, not the final AddNoOverlap2D call, is the
substance"). `encode_fixed_copper_constraints` / `_pad_rotation_tables_with` /
`_add_no_overlap` build `ortools.CpModel` calls directly and are the solver
boundary itself -- they stay in Python and are NOT covered by this file.

Arms
----
* **oracle** -- ``_fixed_copper_py_oracle.py``, a verbatim ``git show`` copy
  of ``fixed_copper.py`` at commit ``1dd54e3f2cc58e9dd6cbc5b3c54d68b4d0374ae9``
  (origin/main).
* **rust** -- ``temper_geometry.fixed_copper_*_py`` pyfunctions
  (``packages/temper-geometry/src/fixed_copper.rs``).

Comparison is by **type-carrying signature**
(``tests.router_v6._signature.sig``): ``float.hex()`` per float, concrete
type name per leaf, no tolerance anywhere.

Traps this file exercises
--------------------------
* ``_mm_to_units``/``_mm_to_fine_units``: ``round()`` (no ndigits) is
  round-half-to-even, converted to an ``int`` -- NOT ``f64::round``/
  ``round_ties_even`` alone (sign-of-zero, non-finite raising).
* ``_local_pad_half``: ``pad_rotation_deg % 180.0`` is Python float modulo
  (sign of the DIVISOR), not Rust's ``%`` (sign of the dividend); the
  degenerate ``phi == 0.0`` fast path must trigger for exact multiples of
  180.
* ``_point_segment_distance`` in this module is a DIFFERENT function from
  the one in ``creepage_check.rs``/``drc_constraints_geometry.rs`` (exact
  ``dx == 0.0 and dy == 0.0`` degenerate check here, vs an epsilon
  threshold there) -- ``test_segment_slack_mm_degenerate_segment`` pins the
  boundary this file's own convention requires.
* ``_convex_polygon_edges``'s diagonal-edge branch: ``math.ceil`` raises on
  non-finite (unreachable for finite polygon input, but the fine-unit
  ``round()`` calls inside it are the same round-half-even trap).
* ``exact_clearance_mm``'s zone branch is NOT a reimplementation of shapely
  bit-for-bit (see the Rust module's header for the documented gap: the
  ``poly.buffer(0)`` self-intersection repair). This file's own sweeps stay
  within valid-simple-polygon inputs, where
  ``test_fixed_copper.py``'s pre-existing 150k+-case BMC suite is the
  stronger proof that the from-scratch Rust geometry agrees with shapely.
"""

from __future__ import annotations

import math
import random

import pytest
import temper_geometry as _tg

import tests.placer.cp_sat._fixed_copper_py_oracle as _oracle
from tests.router_v6._signature import sig

# Rust symbols under test -- import at module scope so a missing symbol
# fails collection (RED) rather than surfacing as a per-test skip.
_RUST_MM_TO_UNITS = _tg.fixed_copper_mm_to_units_py
_RUST_MM_TO_FINE_UNITS = _tg.fixed_copper_mm_to_fine_units_py
_RUST_PIN_COPPER_LAYERS = _tg.fixed_copper_pin_copper_layers_py
_RUST_LOCAL_PAD_HALF = _tg.fixed_copper_local_pad_half_py
_RUST_ROTATED = _tg.fixed_copper_rotated_py
_RUST_PAD_WORLD_RECT = _tg.fixed_copper_pad_world_rect_py
_RUST_ENCODED_PAD_WORLD_RECT = _tg.fixed_copper_encoded_pad_world_rect_py
_RUST_SEGMENT_SLACK_MM = _tg.fixed_copper_segment_slack_mm_py
_RUST_RECTILINEAR_CONVEX_EDGES = _tg.fixed_copper_rectilinear_convex_edges_py
_RUST_CONVEX_POLYGON_EDGES = _tg.fixed_copper_convex_polygon_edges_py
_RUST_SEGMENT_ITEM_GEOM = _tg.fixed_copper_segment_item_geom_py
_RUST_VIA_ITEM_GEOM = _tg.fixed_copper_via_item_geom_py
_RUST_ZONE_ITEM_RECT = _tg.fixed_copper_zone_item_rect_py
_RUST_OTHER_PAD_ITEM_GEOM = _tg.fixed_copper_other_pad_item_geom_py
_RUST_EXACT_CLEARANCE_MM = _tg.fixed_copper_exact_clearance_mm_py

_SEED = 20260806


def _rng(offset: int) -> random.Random:
    return random.Random(_SEED + offset)


def _rand_mm(rng: random.Random) -> float:
    return rng.uniform(-500.0, 500.0)


# ---------------------------------------------------------------------------
# mm_to_units / mm_to_fine_units
# ---------------------------------------------------------------------------


def test_mm_to_units_matches_oracle():
    rng = _rng(1)
    # Half-integer boundaries (the round-half-even trap) plus random mm.
    boundaries = [0.0, 0.005, -0.005, 0.015, -0.015, 0.025, -0.025, 0.125, -0.125]
    values = boundaries + [_rand_mm(rng) for _ in range(2000)]
    for mm in values:
        assert sig(_RUST_MM_TO_UNITS(mm)) == sig(_oracle._mm_to_units(mm)), mm


def test_mm_to_fine_units_matches_oracle():
    rng = _rng(2)
    boundaries = [0.0, 0.00005, -0.00005, 0.00015, -0.00015]
    values = boundaries + [_rand_mm(rng) for _ in range(2000)]
    for mm in values:
        assert sig(_RUST_MM_TO_FINE_UNITS(mm)) == sig(_oracle._mm_to_fine_units(mm)), mm


def test_mm_to_units_raises_on_nonfinite_like_oracle():
    for bad in (float("nan"), float("inf"), float("-inf")):
        with pytest.raises(Exception) as rust_exc:
            _RUST_MM_TO_UNITS(bad)
        with pytest.raises(Exception) as oracle_exc:
            _oracle._mm_to_units(bad)
        assert type(rust_exc.value) in (ValueError, OverflowError)
        assert type(oracle_exc.value) in (ValueError, OverflowError)


# ---------------------------------------------------------------------------
# pin copper layers
# ---------------------------------------------------------------------------


class _Pin:
    def __init__(self, is_pth=False, layer=None):
        self.is_pth = is_pth
        self.layer = layer


def test_pin_copper_layers_matches_oracle():
    cases = [
        (True, None),
        (True, "F.Cu"),
        (False, "all"),
        (False, "F.Cu"),
        (False, "B.Cu"),
        (False, "In1.Cu"),
        (False, "In2.Cu"),
        (False, "Silkscreen"),
        (False, None),
    ]
    for is_pth, layer in cases:
        pin = _Pin(is_pth=is_pth, layer=layer)
        oracle_layers = frozenset(_oracle._pin_copper_layers(pin))
        rust_layers = frozenset(_RUST_PIN_COPPER_LAYERS(is_pth, layer))
        assert rust_layers == oracle_layers, (is_pth, layer)


# ---------------------------------------------------------------------------
# local pad half-extent (rotation-aware AABB)
# ---------------------------------------------------------------------------


class _PadDims:
    def __init__(self, width, height, pad_rotation_deg):
        self.width = width
        self.height = height
        self.pad_rotation_deg = pad_rotation_deg


def test_local_pad_half_matches_oracle():
    rng = _rng(3)
    degrees = [0.0, 45.0, 90.0, 135.0, 180.0, 270.0, -45.0, -90.0, 360.0, 0.1, 179.9]
    degrees += [rng.uniform(-720.0, 720.0) for _ in range(500)]
    for deg in degrees:
        w = rng.uniform(0.01, 10.0)
        h = rng.uniform(0.01, 10.0)
        pin = _PadDims(w, h, deg)
        oracle_val = _oracle._local_pad_half(pin)
        rust_val = _RUST_LOCAL_PAD_HALF(w, h, deg)
        assert sig(rust_val) == sig(oracle_val), (w, h, deg)


# ---------------------------------------------------------------------------
# quadrant rotation / world rect
# ---------------------------------------------------------------------------


def test_rotated_matches_oracle():
    rng = _rng(4)
    for _ in range(1000):
        lx, ly = rng.uniform(-50, 50), rng.uniform(-50, 50)
        hw, hh = rng.uniform(0.0, 20.0), rng.uniform(0.0, 20.0)
        for rot in range(4):

            class _P:
                center = (lx, ly)
                half = (hw, hh)

            oracle_val = _oracle._rotated(_P(), rot)
            rust_val = _RUST_ROTATED(lx, ly, hw, hh, rot)
            assert sig(rust_val) == sig(oracle_val), (lx, ly, hw, hh, rot)


def test_pad_world_rect_matches_oracle():
    rng = _rng(5)
    for _ in range(1000):
        lx, ly = rng.uniform(-50, 50), rng.uniform(-50, 50)
        hw, hh = rng.uniform(0.0, 20.0), rng.uniform(0.0, 20.0)
        cx, cy = rng.uniform(-200, 200), rng.uniform(-200, 200)
        rot = rng.randrange(4)

        class _P:
            center = (lx, ly)
            half = (hw, hh)

        oracle_val = _oracle.pad_world_rect(_P(), (cx, cy), rot)
        rust_val = _RUST_PAD_WORLD_RECT(lx, ly, hw, hh, rot, cx, cy)
        assert sig(rust_val) == sig(oracle_val), (lx, ly, hw, hh, rot, cx, cy)


def test_encoded_pad_world_rect_matches_oracle():
    rng = _rng(6)
    # Include degenerate (0-half) pads -- exercises the _MIN_HALF_MM clamp.
    for _ in range(1000):
        lx, ly = rng.uniform(-50, 50), rng.uniform(-50, 50)
        hw, hh = rng.choice([0.0, rng.uniform(0.0, 20.0)]), rng.choice([0.0, rng.uniform(0.0, 20.0)])
        cx, cy = rng.uniform(-200, 200), rng.uniform(-200, 200)
        rot = rng.randrange(4)

        class _P:
            center = (lx, ly)
            half = (hw, hh)

        oracle_val = _oracle.encoded_pad_world_rect(_P(), (cx, cy), rot)
        rust_val = _RUST_ENCODED_PAD_WORLD_RECT(lx, ly, hw, hh, rot, cx, cy)
        assert sig(rust_val) == sig(oracle_val), (lx, ly, hw, hh, rot, cx, cy)


# ---------------------------------------------------------------------------
# segment_slack_mm (this file's own point-segment-distance convention)
# ---------------------------------------------------------------------------


def test_segment_slack_mm_matches_oracle():
    rng = _rng(7)
    for _ in range(1000):
        p0 = (rng.uniform(-20, 20), rng.uniform(-20, 20))
        p1 = (rng.uniform(-20, 20), rng.uniform(-20, 20))
        width = rng.uniform(0.05, 2.0)
        margin = rng.uniform(0.0, 0.5)
        oracle_val = _oracle.segment_slack_mm(p0, p1, width, margin)
        rust_val = _RUST_SEGMENT_SLACK_MM(p0, p1, width, margin)
        assert sig(rust_val) == sig(oracle_val), (p0, p1, width, margin)


def test_segment_slack_mm_degenerate_segment_matches_oracle():
    """p0 == p1: this file's `_point_segment_distance` takes the
    `dx == 0.0 and dy == 0.0` fast path, distinct from the epsilon-threshold
    version elsewhere in this crate."""
    p = (3.5, -2.25)
    width = 0.3
    margin = 0.05
    oracle_val = _oracle.segment_slack_mm(p, p, width, margin)
    rust_val = _RUST_SEGMENT_SLACK_MM(p, p, width, margin)
    assert sig(rust_val) == sig(oracle_val)


# ---------------------------------------------------------------------------
# convex zone edges (#567 rectilinear + #651 general convex)
# ---------------------------------------------------------------------------


def _edges_sig(edges):
    if edges is None:
        return sig(None)
    return sig(tuple(edges))


_POLYGONS = [
    [(0.0, 0.0), (4.0, 0.0), (4.0, 4.0), (0.0, 4.0)],  # square, CCW
    [(0.0, 0.0), (0.0, 3.0), (5.0, 3.0), (5.0, 0.0)],  # rect, CW
    [(0.0, 0.0), (4.0, 0.0), (4.0, 2.0), (2.0, 2.0), (2.0, 4.0), (0.0, 4.0)],  # L, non-convex
    [(0.0, 0.0), (4.0, 1.0), (4.0, 4.0), (0.0, 4.0)],  # one diagonal edge
    [(0.0, 0.0), (4.0, 0.0), (0.0, 4.0)],  # right triangle, diagonal hyp
    [(0.0, 0.0), (5.0, 0.0), (3.0, 4.0), (0.0, 4.0)],  # quad, CW, diagonal
    [(0.0, 0.0), (3.0, 0.0), (4.0, 2.0), (3.0, 4.0), (0.0, 4.0), (-1.0, 2.0)],  # hexagon
    [(0.0, 0.0), (6.0, 0.0), (0.8, 0.44)],  # sharp 28.7deg triangle
    [(44.0, 10.0), (30.0, -3.0), (-4.0, 8.0), (2.0, 33.0), (20.0, 28.0)],  # board-spanning pentagon
    [],
    [(0.0, 0.0), (1.0, 1.0)],
    [(0.0, 0.0), (4.0, 0.0), (4.0, 0.0)],  # degenerate zero-area
]


def test_rectilinear_convex_edges_matches_oracle():
    for poly in _POLYGONS:
        for margin in (0.0, 0.05, 0.2):
            oracle_val = _oracle._rectilinear_convex_edges(poly, margin)
            rust_val = _RUST_RECTILINEAR_CONVEX_EDGES(poly, margin)
            assert _edges_sig(rust_val) == _edges_sig(oracle_val), (poly, margin)


def test_convex_polygon_edges_matches_oracle():
    for poly in _POLYGONS:
        for margin in (0.0, 0.05, 0.2):
            oracle_val = _oracle._convex_polygon_edges(poly, margin)
            rust_val = _RUST_CONVEX_POLYGON_EDGES(poly, margin)
            assert _edges_sig(rust_val) == _edges_sig(oracle_val), (poly, margin)


def test_convex_polygon_edges_capsule_short_edges_matches_oracle():
    """The +15V_LS-class capsule (sub-0.05mm arc edges) -- the regression
    the fine-unit direction computation exists for."""
    r = 0.25
    half = 5.0
    n_arc = 24
    pts = [(-half, r), (half, r)]
    for i in range(1, n_arc):
        a = math.pi / 2.0 - math.pi * i / n_arc
        pts.append((half + r * math.cos(a), r * math.sin(a)))
    pts.append((half, -r))
    pts.append((-half, -r))
    for i in range(1, n_arc):
        a = 3 * math.pi / 2.0 - math.pi * i / n_arc
        pts.append((-half + r * math.cos(a), r * math.sin(a)))
    oracle_val = _oracle._convex_polygon_edges(pts, 0.05)
    rust_val = _RUST_CONVEX_POLYGON_EDGES(pts, 0.05)
    assert _edges_sig(rust_val) == _edges_sig(oracle_val)


# ---------------------------------------------------------------------------
# item geometry (segment / via / zone rect / other-component pad)
# ---------------------------------------------------------------------------


def test_segment_item_geom_matches_oracle():
    rng = _rng(8)
    for _ in range(500):
        start = (rng.uniform(-50, 50), rng.uniform(-50, 50))
        end = (rng.uniform(-50, 50), rng.uniform(-50, 50))
        width = rng.uniform(0.05, 2.0)
        margin = rng.uniform(0.0, 0.5)
        oracle_item = _oracle._segment_item(start, end, width, "N1", frozenset({"F.Cu"}), margin)
        rust_val = _RUST_SEGMENT_ITEM_GEOM(start, end, width, margin)
        assert sig(rust_val) == sig((oracle_item.rect, oracle_item.slack_mm)), (start, end, width, margin)


def test_via_item_geom_matches_oracle():
    rng = _rng(9)
    for _ in range(500):
        pos = (rng.uniform(-50, 50), rng.uniform(-50, 50))
        diameter = rng.uniform(0.1, 3.0)
        margin = rng.uniform(0.0, 0.5)
        oracle_item = _oracle._via_item(pos, diameter, "N1", frozenset({"F.Cu"}), margin)
        rust_val = _RUST_VIA_ITEM_GEOM(pos, diameter, margin)
        assert sig(rust_val) == sig((oracle_item.rect, oracle_item.slack_mm)), (pos, diameter, margin)


class _Zone:
    def __init__(self, polygon, layers=("F.Cu",), net_classes=("N1",), name="Z1"):
        self.polygon = polygon
        self.layers = layers
        self.net_classes = net_classes
        self.name = name


def test_zone_item_rect_matches_oracle():
    for poly in _POLYGONS:
        if len(poly) < 3:
            continue
        for margin in (0.0, 0.05, 0.2):
            oracle_item = _oracle._zone_item(_Zone(poly), margin)
            rust_val = _RUST_ZONE_ITEM_RECT(poly, margin)
            assert sig(rust_val) == sig(oracle_item.rect), (poly, margin)


class _OtherPin:
    def __init__(self, position, width, height, pad_rotation_deg, net, number="1", is_pth=False, layer="F.Cu"):
        self.position = position
        self.width = width
        self.height = height
        self.pad_rotation_deg = pad_rotation_deg
        self.net = net
        self.number = number
        self.is_pth = is_pth
        self.layer = layer


class _OtherComp:
    def __init__(self, ref, initial_position, initial_rotation_quadrant):
        self.ref = ref
        self.initial_position = initial_position
        self.initial_rotation_quadrant = initial_rotation_quadrant


def test_other_pad_item_geom_matches_oracle():
    rng = _rng(10)
    for _ in range(500):
        lx, ly = rng.uniform(-10, 10), rng.uniform(-10, 10)
        w, h = rng.uniform(0.1, 5.0), rng.uniform(0.1, 5.0)
        deg = rng.choice([0.0, 90.0, 180.0, 270.0])  # matches the model's quadrant convention
        cx, cy = rng.uniform(-100, 100), rng.uniform(-100, 100)
        rot = rng.randrange(4)
        margin = rng.uniform(0.0, 0.5)
        pin = _OtherPin((lx, ly), w, h, deg, "N2")
        comp = _OtherComp("U2", (cx, cy), rot)
        oracle_item = _oracle._other_component_pad_item(comp, pin, margin, _oracle.COPPER_LAYERS)
        assert oracle_item is not None
        hw, hh = _oracle._local_pad_half(pin)
        rust_val = _RUST_OTHER_PAD_ITEM_GEOM(lx, ly, hw, hh, rot, cx, cy, margin)
        oracle_tuple = (oracle_item.exact["rect"], oracle_item.rect, oracle_item.slack_mm)
        assert sig(rust_val) == sig(oracle_tuple), (lx, ly, w, h, deg, cx, cy, rot, margin)


# ---------------------------------------------------------------------------
# exact_clearance_mm dispatch (segment / via / pad / zone)
# ---------------------------------------------------------------------------


def _rust_exact_clearance(pad_rect, item):
    if item.kind == "segment":
        return _RUST_EXACT_CLEARANCE_MM(pad_rect, "segment", p0=item.exact["p0"], p1=item.exact["p1"], width=item.exact["width"])
    if item.kind == "via":
        return _RUST_EXACT_CLEARANCE_MM(pad_rect, "via", center=item.exact["center"], diameter=item.exact["diameter"])
    if item.kind == "pad":
        return _RUST_EXACT_CLEARANCE_MM(pad_rect, "pad", other_rect=item.exact["rect"])
    if item.kind == "zone":
        return _RUST_EXACT_CLEARANCE_MM(pad_rect, "zone", polygon=item.exact["polygon"])
    raise AssertionError(item.kind)


def test_exact_clearance_mm_segment_matches_oracle():
    rng = _rng(15)
    for _ in range(500):
        p0 = (rng.uniform(-20, 20), rng.uniform(-20, 20))
        p1 = (rng.uniform(-20, 20), rng.uniform(-20, 20))
        width = rng.uniform(0.05, 1.0)
        item = _oracle._segment_item(p0, p1, width, "N1", frozenset({"F.Cu"}), 0.05)
        x0, y0 = rng.uniform(-20, 20), rng.uniform(-20, 20)
        pad_rect = (x0, y0, x0 + rng.uniform(0.1, 3.0), y0 + rng.uniform(0.1, 3.0))
        oracle_val = _oracle.exact_clearance_mm(pad_rect, item)
        rust_val = _rust_exact_clearance(pad_rect, item)
        assert sig(rust_val) == sig(oracle_val), (pad_rect, p0, p1, width)


def test_exact_clearance_mm_via_matches_oracle():
    rng = _rng(16)
    for _ in range(500):
        pos = (rng.uniform(-20, 20), rng.uniform(-20, 20))
        diameter = rng.uniform(0.1, 2.0)
        item = _oracle._via_item(pos, diameter, "N1", frozenset({"F.Cu"}), 0.05)
        x0, y0 = rng.uniform(-20, 20), rng.uniform(-20, 20)
        pad_rect = (x0, y0, x0 + rng.uniform(0.1, 3.0), y0 + rng.uniform(0.1, 3.0))
        oracle_val = _oracle.exact_clearance_mm(pad_rect, item)
        rust_val = _rust_exact_clearance(pad_rect, item)
        assert sig(rust_val) == sig(oracle_val), (pad_rect, pos, diameter)


def test_exact_clearance_mm_pad_matches_oracle():
    rng = _rng(17)

    class _PadItem:
        kind = "pad"
        margin_mm = 0.05

        def __init__(self, rect):
            self.exact = {"rect": rect}

    for _ in range(500):
        x0, y0 = rng.uniform(-20, 20), rng.uniform(-20, 20)
        other_rect = (x0, y0, x0 + rng.uniform(0.1, 3.0), y0 + rng.uniform(0.1, 3.0))
        item = _PadItem(other_rect)
        x1, y1 = rng.uniform(-20, 20), rng.uniform(-20, 20)
        pad_rect = (x1, y1, x1 + rng.uniform(0.1, 3.0), y1 + rng.uniform(0.1, 3.0))
        oracle_val = _oracle.exact_clearance_mm(pad_rect, item)
        rust_val = _rust_exact_clearance(pad_rect, item)
        assert sig(rust_val) == sig(oracle_val), (pad_rect, other_rect)


def test_exact_clearance_mm_zone_matches_oracle():
    """Zone clearance is the ONE documented exception to the file's
    otherwise bit-exact contract: `zone_exact_clearance` is a from-scratch
    Rust geometric distance (point-in-polygon + per-edge rect-segment
    distance), not a reimplementation of shapely/GEOS's internal distance
    algorithm, so the two can differ in the last ulp even though both are
    the mathematically correct answer (this file's own `_rect_rect_gap`,
    `_point_rect_distance` etc. carry the SAME "operation order must match
    exactly" bar, but there is no operation-order to match here -- GEOS's
    algorithm is opaque). `test_fixed_copper.py`'s pre-existing 150k+-case
    BMC suite is the authoritative soundness/conservatism proof for this
    kernel; this test's job is only to confirm the two arms agree to within
    float noise, mirroring that suite's own `eps = 1e-9` convention (its
    own comment: "a pad edge EXACTLY at the margin boundary ... computes to
    margin - ~1e-16").
    """
    rng = _rng(18)
    eps = 1e-9
    # Excludes the zero-area 3-point degenerate polygon from `_POLYGONS`:
    # shapely's `Polygon(...).is_valid` is False for it, which triggers the
    # documented-out-of-scope `poly.buffer(0)` repair path on the oracle
    # side (yielding NaN here) that `zone_exact_clearance` does not
    # replicate -- see the Rust module header and this test's docstring.
    for poly in _POLYGONS:
        if len(poly) < 3:
            continue
        if len(set(poly)) < 3:  # duplicate vertices -> zero area / invalid
            continue
        item = _oracle._zone_item(_Zone(poly), 0.05)
        if item is None:
            continue
        for _ in range(50):
            x0, y0 = rng.uniform(-10, 15), rng.uniform(-10, 15)
            pad_rect = (x0, y0, x0 + rng.uniform(0.1, 3.0), y0 + rng.uniform(0.1, 3.0))
            oracle_val = _oracle.exact_clearance_mm(pad_rect, item)
            rust_val = _rust_exact_clearance(pad_rect, item)
            # Zero-ness (touching/overlapping) must still be bit-exact: that
            # is the soundness-critical branch, not float noise.
            assert (rust_val == 0.0) == (oracle_val == 0.0), (pad_rect, poly)
            assert abs(rust_val - oracle_val) <= eps, (pad_rect, poly, rust_val, oracle_val)


def test_exact_clearance_mm_zone_intersecting_matches_oracle():
    """Rect fully inside the polygon, and polygon fully inside the rect --
    the containment cases `zone_exact_clearance`'s point-in-polygon fallback
    exists for. Both are zero-distance (intersecting) cases, so bit-exact
    equality applies here (no GEOS distance-algorithm divergence possible
    when the answer is exactly 0.0)."""
    square = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
    item = _oracle._zone_item(_Zone(square), 0.05)
    cases = [
        (4.0, 4.0, 6.0, 6.0),  # rect fully inside polygon
        (-5.0, -5.0, 15.0, 15.0),  # polygon fully inside rect
    ]
    for pad_rect in cases:
        oracle_val = _oracle.exact_clearance_mm(pad_rect, item)
        rust_val = _rust_exact_clearance(pad_rect, item)
        assert sig(rust_val) == sig(oracle_val), pad_rect
