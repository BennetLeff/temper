"""Rev D candidate: 22 ohm 0603 R_ISO between J3 DUT-LO and the TIA summing node.

Builds geometry_riso.json, an in-memory edit of the exported Rev C copper (the
CAD is not touched).  Net names in the variant:
  TIA_SUM  summing side: U7.2, C104.1, R43/R44/R45.1, the x=164.4 spine, and
           a new under-body link from U7.2 up to R_ISO.2
  DUT_LO   J3 side: J3.2, the existing J3 -> U7.5 trace (LOW follower tap
           stays on the J3 side), R_ISO.1, and a new star branch from J3.2
           on B.Cu to a via beside R_ISO.1

Edits (all coordinates mm, matching cad/routing.json conventions):
  delete  DUT_LO F.Cu (167.3,107.675)->(168.5,108.875)->(170.1125,108.975)  [under-body link to U7.5]
  add     TIA_SUM F.Cu w0.15 (167.3,107.675)->(167.825,107.15)->(167.825,105.4)
  add     R_ISO 0603 at (167.0,105.4) rot 0: pad1 (166.175,105.4) DUT_LO, pad2 (167.825,105.4) TIA_SUM
  add     DUT_LO F.Cu w0.25 (166.175,105.4)->(166.175,104.35); via 0.6/0.3 at (166.175,104.35)
  add     DUT_LO B.Cu w0.25 (166.175,104.35)->(170.0,104.35)->(173.81,100.54)->(176.0,100.54) [J3.2]
  add     keepout In1/In2/B.Cu rect (167.2,104.9)-(168.6,106.5) under R_ISO.2 (joins the U7 void)
  In1 fill: keepout rect and a 0.5 mm-radius antipad at the new via are cut from
  the exported fill (approximation of a refill; clearance 0.2 mm).
"""
from __future__ import annotations

import copy
import json

from shapely.geometry import Point, box

from common import HERE

SUM_NEW = 'TIA_SUM'


def rect_pad(ref, num, net, x, y, w=0.8, h=0.95):
    b = box(x - w / 2, y - h / 2, x + w / 2, y + h / 2)
    return {'kind': 'pad', 'ref': ref, 'pad': num, 'net': net, 'x': x, 'y': y, 'pth': False,
            'drill': 0.0, 'polys': {'F.Cu': [[list(map(list, b.exterior.coords))]]}}


def track(net, layer, a, b, w):
    return {'kind': 'track', 'net': net, 'layer': layer, 'x1': a[0], 'y1': a[1], 'x2': b[0],
            'y2': b[1], 'w': w}


def main():
    g = json.loads((HERE / 'geometry.json').read_text())
    v = copy.deepcopy(g)
    drop = {((167.3, 107.675), (168.5, 108.875)), ((168.5, 108.875), (170.1125, 108.975)),
            ((168.5, 108.875), (170.112, 108.975))}
    items = []
    removed = 0
    for it in v['items']:
        if it['kind'] == 'track' and it['net'] == 'DUT_LO':
            key = ((round(it['x1'], 4), round(it['y1'], 4)), (round(it['x2'], 4), round(it['y2'], 4)))
            if key in drop or key[::-1] in drop:
                removed += 1
                continue
        items.append(it)
    assert removed == 2, removed
    # relabel the summing-side copper (everything DUT_LO left of the U7 body centre)
    for it in items:
        if it['net'] != 'DUT_LO':
            continue
        x = it['x'] if it['kind'] != 'track' else max(it['x1'], it['x2'])
        if x < 168.0:
            it['net'] = SUM_NEW
    items += [
        track(SUM_NEW, 'F.Cu', (167.3, 107.675), (167.825, 107.15), 0.15),
        track(SUM_NEW, 'F.Cu', (167.825, 107.15), (167.825, 105.4), 0.15),
        rect_pad('R_ISO', '1', 'DUT_LO', 166.175, 105.4),
        rect_pad('R_ISO', '2', SUM_NEW, 167.825, 105.4),
        track('DUT_LO', 'F.Cu', (166.175, 105.4), (166.175, 104.35), 0.25),
        {'kind': 'via', 'net': 'DUT_LO', 'x': 166.175, 'y': 104.35, 'dia': 0.6, 'drill': 0.3,
         'layers': ['F.Cu', 'In1.Cu', 'In2.Cu', 'B.Cu']},
        track('DUT_LO', 'B.Cu', (166.175, 104.35), (170.0, 104.35), 0.25),
        track('DUT_LO', 'B.Cu', (170.0, 104.35), (173.81, 100.54), 0.25),
        track('DUT_LO', 'B.Cu', (173.81, 100.54), (176.0, 100.54), 0.25),
    ]
    v['items'] = items
    ko = box(167.2, 104.9, 168.6, 106.5)
    anti = Point(166.175, 104.35).buffer(0.5, 32)
    v['in1_cuts'] = [[list(map(list, ko.exterior.coords))], [list(map(list, anti.exterior.coords))]]
    v['variant'] = __doc__.strip().split('\n')[0]
    (HERE / 'geometry_riso.json').write_text(json.dumps(v, separators=(',', ':')))
    # clearance audit of the new copper against all other-net copper on the same layer
    from shapely.ops import unary_union
    from common import item_shape
    new = items[-9:]
    report = []
    for n in new:
        for layer in ('F.Cu', 'B.Cu'):
            s = item_shape(n, layer)
            if s is None:
                continue
            others = [item_shape(o, layer) for o in items if o['net'] != n['net'] and o is not n]
            others = unary_union([o for o in others if o is not None])
            report.append((n.get('ref', n['kind']), n['net'], layer, round(s.distance(others), 3)))
    for r in report:
        print('min clearance', r)


if __name__ == '__main__':
    main()
