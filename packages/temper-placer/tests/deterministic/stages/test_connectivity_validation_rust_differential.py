"""Differential tests: connectivity_validation leaf kernel, Rust vs oracle.

Wave 4, Phase 5, batch 2 (deterministic leaf stages). The per-net
connectivity compute of ``deterministic/stages/connectivity_validation.py``
(UnionFind over pads/tracks/vias, the touch predicates, component
classification, the dangling-track scan) moves to the ``temper-drc-rs``
crate; the Python module becomes a delegation shim. The pre-migration
implementation is pinned VERBATIM as the oracle
(``_connectivity_validation_py_oracle.py``).

R1a: violation list (type, location, description) bit-identical — location
is an input coordinate (never recomputed), descriptions are plain string
interpolation, and the pad-touch predicate calls the same temper-geometry
``point_to_rotated_rect_distance`` both arms use.
"""

from __future__ import annotations

import temper_drc_rs as _drc
import tests.deterministic.stages._connectivity_validation_py_oracle as _oracle
from temper_placer.router_v6.constraints_spatial_index import Pad, Point, Track, Via


def _mk_pads(*specs):
    return [Pad(Point(x, y), shape, size, net, layer, id=pid, rotation=rot) for (x, y, shape, size, net, layer, pid, rot) in specs]


def _mk_tracks(*specs):
    return [Track(Point(sx, sy), Point(ex, ey), w, net, layer, id=tid) for (sx, sy, ex, ey, w, net, layer, tid) in specs]


def _mk_vias(*specs):
    return [Via(Point(x, y), dia, drill, net, id=vid) for (x, y, dia, drill, net, vid) in specs]


def _flatten_pads(pads):
    return [(p.center.x, p.center.y, p.layer, p.id, p.size[0], p.size[1], p.rotation) for p in pads]


def _flatten_tracks(tracks):
    return [(t.start.x, t.start.y, t.end.x, t.end.y, t.layer) for t in tracks]


def _flatten_vias(vias):
    return [(v.center.x, v.center.y) for v in vias]


def _canon(v):
    loc = v.location
    return (v.type, loc.x, loc.y, v.description)


def _assert_same(net, pads, tracks, vias):
    exp = [_canon(v) for v in _oracle.validate_net(net, pads, tracks, vias)]
    got = list(_drc.connectivity_validate_net_py(net, _flatten_pads(pads), _flatten_tracks(tracks), _flatten_vias(vias)))
    assert got == exp, f"net={net}\n  exp={exp}\n  got={got}"


def test_empty_net():
    _assert_same("A", [], [], [])


def test_clean_chain_pad_track_pad():
    pads = _mk_pads(
        (0, 0, "circle", (1, 1), "A", 0, "P1", 0),
        (10, 0, "circle", (1, 1), "A", 0, "P2", 0),
    )
    tracks = _mk_tracks((0, 0, 10, 0, 0.25, "A", 0, "T1"))
    _assert_same("A", pads, tracks, [])


def test_unconnected_pads():
    pads = _mk_pads(
        (0, 0, "circle", (1, 1), "A", 0, "P1", 0),
        (10, 0, "circle", (1, 1), "A", 0, "P2", 0),
    )
    _assert_same("A", pads, [], [])


def test_orphan_island():
    tracks = _mk_tracks((10, 10, 15, 10, 0.25, "A", 0, "T1"))
    _assert_same("A", [], tracks, [])


def test_orphan_via_island():
    vias = _mk_vias((3, 3, 0.6, 0.3, "A", "V1"))
    _assert_same("A", [], [], vias)


def test_dangling_track():
    pads = _mk_pads((0, 0, "circle", (1, 1), "A", 0, "P1", 0))
    tracks = _mk_tracks((0, 0, 5, 0, 0.25, "A", 0, "T1"))
    _assert_same("A", pads, tracks, [])


def test_via_connection_bridges_layers():
    pads = _mk_pads(
        (0, 0, "circle", (1, 1), "A", 0, "P1", 0),
        (5, 0, "circle", (1, 1), "A", 1, "P2", 0),
    )
    tracks = _mk_tracks((0, 0, 5, 0, 0.25, "A", 0, "T1"))
    vias = _mk_vias((5, 0, 0.6, 0.3, "A", "V1"))
    _assert_same("A", pads, tracks, vias)


def test_mixed_violations():
    pads = _mk_pads(
        (0, 0, "circle", (1, 1), "A", 0, "P1", 0),
        (10, 0, "circle", (1, 1), "A", 0, "P2", 0),
        (0, 10, "circle", (1, 1), "A", 0, "P3", 0),
    )
    tracks = _mk_tracks(
        (0, 0, 10, 0, 0.25, "A", 0, "T1"),
        (10, 10, 15, 10, 0.25, "A", 0, "T2"),
    )
    _assert_same("A", pads, tracks, [])


def test_track_track_chain_no_pads():
    tracks = _mk_tracks(
        (0, 0, 5, 0, 0.25, "A", 0, "T1"),
        (5, 0, 10, 0, 0.25, "A", 0, "T2"),
    )
    _assert_same("A", [], tracks, [])


def test_same_layer_requirement_for_pads():
    """A track endpoint inside a pad on a DIFFERENT layer is not a touch."""
    pads = _mk_pads((0, 0, "rect", (4, 4), "A", 2, "P1", 0))
    tracks = _mk_tracks((0, 0, 8, 0, 0.25, "A", 0, "T1"))
    _assert_same("A", pads, tracks, [])


def test_pad_inside_rotated_rect():
    """A rotated pad: the endpoint lies inside the rotated rectangle."""
    pads = _mk_pads((5, 0, "rect", (6, 2), "A", 0, "P1", 90))
    tracks = _mk_tracks((0, 0, 10, 0, 0.25, "A", 0, "T1"))
    _assert_same("A", pads, tracks, [])


def test_pad_touch_boundary_1e4():
    """Distance exactly 1e-4 is a touch (`<=`), just past it is not."""
    pads = _mk_pads((0, 0, "rect", (4, 4), "A", 0, "P1", 0))
    # endpoint at distance 1e-4 from the rect edge (inside -> negative dist,
    # so a point on the boundary at (2.0+1e-4, 0))
    tracks = _mk_tracks((2.0 + 1e-4, 0, 10, 0, 0.25, "A", 0, "T1"))
    _assert_same("A", pads, tracks, [])


def test_float_bit_coords():
    pads = _mk_pads((0.1, 0.2, "rect", (1.3, 0.7), "N", 0, "P1", 15.5))
    tracks = _mk_tracks((0.100000001, 0.200000001, 3.3, 4.4, 0.25, "N", 0, "T1"))
    vias = _mk_vias((3.3, 4.4, 0.6, 0.3, "N", "V1"))
    _assert_same("N", pads, tracks, vias)
