"""Synthetic cases for craft.py: every pass and every check, one passing and one failing case each.

python3 -m pytest cad/tools/test_craft.py
"""
import copy
import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import craft  # noqa: E402

BOARD = {'outline': [0, 0, 20, 20]}


def T(net, *pts, layer='F.Cu', w=0.2):
    return {'net': net, 'layer': layer, 'width': w, 'points': [list(p) for p in pts]}


def V(net, x, y, d=0.45):
    return {'net': net, 'at': [x, y], 'diameter': d, 'drill': 0.3}


def PAD(ref, num, net, x, y, w=1.0, h=0.6, shape='rect', angle=0.0, layers=('F.Cu',), smd=True):
    return {'ref': ref, 'pad': num, 'net': net, 'at': [x, y], 'size': [w, h], 'shape': shape, 'angle': angle,
            'layers': list(layers), 'smd': smd}


def R(tracks=(), vias=()):
    return {'tracks': [copy.deepcopy(t) for t in tracks], 'vias': [copy.deepcopy(v) for v in vias], 'keepouts': []}


def idx(routing, pads=()):
    return craft.Index(list(pads), [], BOARD, routing)


# ------------------------------------------------------------------ geometry from plain pads
def test_pad_geom_rotation():
    g = craft.pad_geom(PAD('R1', '1', 'A', 5, 5, w=2.0, h=1.0, angle=90))
    x0, y0, x1, y1 = g.bounds
    assert x1 - x0 == pytest.approx(1.0) and y1 - y0 == pytest.approx(2.0)


# ------------------------------------------------------------------ T-junctions
def test_tjunction_split_and_check():
    r = R([T('A', (2, 5), (10, 5)), T('A', (6, 8), (6, 5))])
    assert len(craft.tjunction_checks(r)) == 1
    assert craft.split_tjunctions(r) == 1
    assert craft.tjunction_checks(r) == []


def test_tjunction_clean():
    r = R([T('A', (2, 5), (6, 5)), T('A', (6, 5), (10, 5)), T('A', (6, 8), (6, 5))])
    assert craft.split_tjunctions(r) == 0
    assert craft.tjunction_checks(r) == []


# ------------------------------------------------------------------ pad entries
def test_entry_fixed():
    pads = [PAD('R1', '1', 'A', 5, 5)]
    r = R([T('A', (5, 5), (9, 7.5))])
    v = craft.entry_checks(r, pads)
    assert len(v) == 1 and v[0]['kind'] == 'pad_entry' and 'where' in v[0]
    craft.run(r, pads, [], BOARD)
    assert craft.entry_checks(r, pads, r['craft_exceptions']) == []
    assert r['craft_exceptions'] == []
    # the first leg now leaves the land along an axis
    first = next(t for t in r['tracks'] if t['points'][0] == [5, 5] or t['points'][1] == [5, 5])
    (x0, y0), (x1, y1) = first['points']
    assert abs(x1 - x0) < 1e-6 or abs(y1 - y0) < 1e-6


def test_entry_on_axis():
    pads = [PAD('R1', '1', 'A', 5, 5)]
    assert craft.entry_checks(R([T('A', (5, 5), (9, 5))]), pads) == []


def test_entry_exception_when_blocked():
    # other-net copper on every side of the land: no stub fits, so the entry is listed, not changed
    pads = [PAD('R1', '1', 'A', 5, 5)]
    walls = [T('B', (3.9, 3), (3.9, 7)), T('B', (6.3, 3), (6.3, 7)), T('B', (3, 4.45), (7, 4.45)),
             T('B', (3, 5.55), (7, 5.55))]
    r = R([T('A', (5, 5), (5.8, 5.3))] + walls)
    craft.run(r, pads, [], BOARD)
    assert [x['kind'] for x in r['craft_exceptions']] == ['pad_entry']
    assert craft.entry_checks(r, pads, r['craft_exceptions']) == []


# ------------------------------------------------------------------ merge
def test_merge_overlaps():
    r = R([T('A', (2, 5), (6, 5)), T('A', (2, 5), (10, 5), w=0.3)])
    assert craft.merge_overlaps(r) == 1
    assert sorted(t['points'] for t in r['tracks']) == [[[2, 5], [6, 5]], [[6, 5], [10, 5]]]


def test_merge_nothing():
    r = R([T('A', (2, 5), (6, 5)), T('A', (2, 5), (2, 9))])
    assert craft.merge_overlaps(r) == 0


# ------------------------------------------------------------------ chamfer
def test_corner_chamfered():
    r = R([T('A', (2, 10), (8, 10)), T('A', (8, 10), (8, 16))])
    v = craft.corner_checks(r, [])
    assert len(v) == 1 and v[0]['kind'] == 'corner90'
    n, exc = craft.chamfer(r, idx(r))
    assert n == 1 and exc == []
    assert craft.corner_checks(r, []) == []
    assert craft.angle_checks(r) == []


def test_corner_45_is_clean():
    r = R([T('A', (2, 10), (8, 10)), T('A', (8, 10), (12, 14))])
    assert craft.corner_checks(r, []) == []
    assert craft.chamfer(r, idx(r)) == (0, [])


def test_corner_at_via_is_a_joint():
    r = R([T('A', (2, 10), (8, 10)), T('A', (8, 10), (8, 16))], [V('A', 8, 10)])
    assert craft.corner_checks(r, []) == []


# ------------------------------------------------------------------ via pads
def test_via_grown():
    r = R(vias=[V('A', 10, 10)])
    assert len(craft.via_checks(r, idx(r))) == 1
    assert craft.grow_vias(r, idx(r)) == (1, 0)
    assert r['vias'][0]['diameter'] == 0.6
    assert craft.via_checks(r, idx(r)) == []


def test_via_kept_small_when_blocked():
    # other-net track 0.15 + 0.225 + 0.1 from the via centre: a 0.45 mm via clears, a 0.6 mm one would not
    r = R([T('B', (10.475, 5), (10.475, 15))], [V('A', 10, 10)])
    assert craft.grow_vias(r, idx(r)) == (0, 1)
    assert craft.via_checks(r, idx(r)) == []


# ------------------------------------------------------------------ angles
def test_angle_acute():
    r = R([T('A', (2, 10), (8, 10)), T('A', (2, 10), (8, 12))])
    v = craft.angle_checks(r)
    assert len(v) == 1 and v[0]['kind'] == 'angle' and v[0]['mm'] < 45


def test_angle_foldback():
    r = R([T('A', (2, 10), (8, 10)), T('A', (8, 10), (5, 10))])
    assert [x['mm'] for x in craft.angle_checks(r)] == [0.0]


def test_angle_ok():
    r = R([T('A', (2, 10), (8, 10)), T('A', (2, 10), (2, 16))])
    assert craft.angle_checks(r) == []


# ------------------------------------------------------------------ stitching vias
SQUARE = [[[1, 1], [19, 1], [19, 19], [1, 19]]]


def test_stitch_grid():
    r = R()
    rep = craft.stitch_vias(r, [], [], BOARD, SQUARE, plan={'grid_pitch': 5.0})
    assert rep['stitch_grid'] == len(r['vias']) > 0
    pts = [tuple(v['at']) for v in r['vias']]
    assert min(math.dist(a, b) for i, a in enumerate(pts) for b in pts[i + 1:]) >= 0.6


def test_stitch_avoid_and_clearance():
    r = R([T('SIG', (1, 7.5), (19, 7.5))])
    rep = craft.stitch_vias(r, [], [], BOARD, SQUARE, avoid=[[[0, 10], [20, 10], [20, 20], [0, 20]]],
                            plan={'grid_pitch': 5.0})
    for v in r['vias']:
        assert v['at'][1] < 10 - 0.3                         # outside the avoid region
        assert abs(v['at'][1] - 7.5) >= 0.1 + 0.15 + 0.3     # clears the signal track
    assert rep['stitch_grid'] == len(r['vias'])


def test_stitch_rows_follow_a_net():
    r = R([T('CLK', (2, 10), (18, 10), layer='B.Cu')])
    rep = craft.stitch_vias(r, [], [], BOARD, SQUARE, plan={'follow_nets': ['CLK'], 'row_layers': ['B.Cu'],
                                                            'grid_pitch': 50.0})
    assert rep['stitch_rows'] > 0
    assert all(abs(abs(v['at'][1] - 10) - 1.0) < 1e-6 for v in r['vias'])


# ------------------------------------------------------------------ IPC-2152
def test_ipc2152_fit_check_point():
    # the fit's published check point: 10 A at a 20 C rise -> 513 mil^2
    assert craft.ipc2152_area_mil2(10, 20) == pytest.approx(513, rel=0.01)


def _supply(width):
    pads = [PAD('U1', '1', 'P', 2, 10), PAD('R1', '1', 'P', 18, 10)]
    r = R([T('P', (2, 10), (18, 10), w=width)])
    return craft.current_checks('P', r, pads, [('U1', '1')], [('R1', 2.0)], 2.0)


def test_current_fail():
    res = _supply(0.1)
    assert res['violations'] and res['violations'][0]['kind'] == 'current'
    assert res['segments'][0]['current_a'] == pytest.approx(2.0, rel=1e-3)


def test_current_pass():
    res = _supply(2.0)
    assert res['violations'] == [] and res['unjoined'] == []


def test_current_via_capacity():
    pads = [PAD('U1', '1', 'P', 2, 10), PAD('R1', '1', 'P', 18, 10, layers=('B.Cu',))]
    r = R([T('P', (2, 10), (10, 10), w=2.0), T('P', (10, 10), (18, 10), w=2.0, layer='B.Cu')], [V('P', 10, 10, 0.6)])
    ok = craft.current_checks('P', r, pads, [('U1', '1')], [('R1', 1.0)], 1.0)
    bad = craft.current_checks('P', r, pads, [('U1', '1')], [('R1', 2.0)], 2.0)
    assert [x['layer'] for x in ok['violations']] == []
    assert [x['layer'] for x in bad['violations']] == ['via']


# ------------------------------------------------------------------ teardrops
def test_teardrops():
    assert craft.teardrop_checks([{'where': 'via GND (1, 1)', 'enabled': True}]) == []
    v = craft.teardrop_checks([{'where': {'pad': 'R1.1'}, 'enabled': False}])
    assert len(v) == 1 and v[0]['where'] == 'pad R1.1'


# ------------------------------------------------------------------ the driver keeps a clean board clean
def test_run_and_checks_clean():
    pads = [PAD('R1', '1', 'A', 4, 4), PAD('R2', '1', 'A', 12, 12)]
    r = R([T('A', (4, 4), (12, 4)), T('A', (12, 4), (12, 12))], [V('B', 16, 16)])
    craft.run(r, pads, [], BOARD)
    assert craft.checks(r, pads, [], BOARD) == []
    assert craft.angle_checks(r) == []
