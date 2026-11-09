"""Rev G against Rev F under the Rev G transform: which analog copper did Rev G change, and where?

    sh validation/rev-g/copper_shift_delta.sh [REV_F_GIT_REV]     (default study/lcr-in-box)

Rev G (cad/tools/rev_g.py) is Rev F with every point below y = 57 moved +10 mm (the BNC band stays), plus the jack
protection in the new band and its hookups. Rev F's extraction (layout-parasitics/extracted_revf.json) stays valid for
any window whose analog copper and GND fill are Rev F's moved +10 mm. This script finds the rest.

Two steps, as copper_delta.sh:
  dump    (KiCad Python): analog-net tracks, vias and pads (mm) and GND fills of both boards -> JSON
  compare (Python + shapely): Rev F items moved by the transform, matched to Rev G's to 1 um; unmatched items per net
          with their bounding box; the GND-fill change per layer below y 68 (Rev F below 58 moved +10), its area and
          its distance to the unchanged analog copper. Writes validation/rev-g/copper-shift-delta.json.
Analog nets: cad/tools/pour.py ANALOG (the extraction's nets and their neighbours); fill distances are also given to the
unchanged copper of the extracted nets alone (EXTRACTED).
"""
import json
import os
import sys

CUT, SHIFT = 57.0, 10.0
# the nets the parasitic extraction solves (layout-parasitics/run_reve.sh run_revf N)
EXTRACTED = {'TIA_SUM', 'DUT_LO', 'TIA_OUT', 'DUT_HI', 'RF100', 'RF5K', 'RF100K', 'LOW_BUF', 'HIGH_BUF', 'SOURCE_BUF',
             'RG100', 'RG5K', 'RG100K', 'SRC_DRV', 'HPOT', 'LPOT', 'REF_A'}
ANALOG = set(os.environ.get('ANALOG', '').split(','))


def moved(x, y):
    return x, (y + SHIFT if y > CUT else y)


def dump(path):
    import pcbnew
    b = pcbnew.LoadBoard(path)
    mm = 1e-6
    items, fills = [], {}
    for t in b.GetTracks():
        if t.GetNetname() in ANALOG:
            via = t.Type() == pcbnew.PCB_VIA_T
            w = t.GetWidth(pcbnew.F_Cu) if via else t.GetWidth()
            items.append(['via' if via else 'track', t.GetNetname(), b.GetLayerName(t.GetLayer()),
                          t.GetStart().x * mm, t.GetStart().y * mm, t.GetEnd().x * mm, t.GetEnd().y * mm, w * mm])
    for fp in b.GetFootprints():
        for p in fp.Pads():
            if p.GetNetname() in ANALOG:
                items.append(['pad', p.GetNetname(), f'{fp.GetReference()}.{p.GetNumber()}',
                              p.GetPosition().x * mm, p.GetPosition().y * mm])
    for z in b.Zones():
        if z.GetNetname() == 'GND' and not z.IsTeardropArea():
            for layer in z.GetLayerSet().CuStack():
                ps = z.GetFilledPolysList(layer)
                for i in range(ps.OutlineCount()):
                    o = ps.Outline(i)
                    fills.setdefault(b.GetLayerName(layer), []).append({
                        'o': [[o.CPoint(j).x * mm, o.CPoint(j).y * mm] for j in range(o.PointCount())],
                        'h': [[[ps.Hole(i, k).CPoint(j).x * mm, ps.Hole(i, k).CPoint(j).y * mm]
                               for j in range(ps.Hole(i, k).PointCount())] for k in range(ps.HoleCount(i))]})
    return {'items': items, 'fills': fills}


def key(item, transform):
    r = lambda v: round(v, 4)      # 0.1 um: KiCad's nm grid, without float noise at the last digit
    if item[0] == 'pad':
        x, y = transform(item[3], item[4]) if transform else (item[3], item[4])
        return ('pad', item[1], item[2], r(x), r(y))
    (x1, y1), (x2, y2) = [transform(*p) if transform else p for p in ((item[3], item[4]), (item[5], item[6]))]
    ends = tuple(sorted(((r(x1), r(y1)), (r(x2), r(y2)))))
    return (item[0], item[1], item[2], ends, r(item[7]))


def compare(d, ref_rev):
    from shapely.affinity import translate
    from shapely.geometry import LineString, Point, Polygon, box
    from shapely.ops import unary_union
    f = {key(i, moved): i for i in d['ref']['items']}
    g = {key(i, None): i for i in d['new']['items']}
    added = [g[k] for k in sorted(set(g) - set(f), key=str)]
    removed = [f[k] for k in sorted(set(f) - set(g), key=str)]

    def geom(i, transform=None):
        if i[0] == 'pad':
            return Point(*(transform(i[3], i[4]) if transform else (i[3], i[4])))
        pts = [(transform(i[3], i[4]) if transform else (i[3], i[4])), (transform(i[5], i[6]) if transform else (i[5], i[6]))]
        return LineString(pts) if pts[0] != pts[1] else Point(*pts[0])

    def by_net(rows, transform=None):
        out = {}
        for i in rows:
            out.setdefault(i[1], []).append(geom(i, transform))
        return {n: dict(items=len(gs), bbox=[round(v, 2) for v in unary_union(gs).bounds]) for n, gs in sorted(out.items())}

    same = [geom(g[k]) for k in set(g) & set(f)]
    unchanged = unary_union(same)
    unchanged_extracted = unary_union([geom(g[k]) for k in set(g) & set(f) if g[k][1] in EXTRACTED])
    changed = unary_union([geom(i) for i in added] + [geom(i, moved) for i in removed])
    fill = {}
    for layer in sorted(set(d['ref']['fills']) | set(d['new']['fills'])):
        def union(side):
            return unary_union([Polygon(p['o'], p['h']).buffer(0) for p in d[side]['fills'].get(layer, [])])
        ref = translate(union('ref').intersection(box(0, CUT + 1, 1000, 1000)), 0, SHIFT)
        new = union('new').intersection(box(0, CUT + 1 + SHIFT, 1000, 1000))
        x = ref.symmetric_difference(new).buffer(-0.01).buffer(0.01)
        fill[layer] = {'area_mm2': 0.0} if x.is_empty else {
            'area_mm2': round(x.area, 2), 'nearest_unchanged_analog_mm': round(x.distance(unchanged), 2),
            'nearest_unchanged_extracted_mm': round(x.distance(unchanged_extracted), 2),
            'bbox': [round(v, 2) for v in x.bounds]}
    return {
        'reference_rev': ref_rev, 'transform': f'y > {CUT} moved +{SHIFT} mm',
        'analog_items': {'rev_f': len(f), 'rev_g': len(g), 'identical_after_transform': len(set(g) & set(f))},
        'added_in_rev_g': by_net(added), 'removed_from_rev_f': by_net(removed, moved),
        'changed_bbox': [round(v, 2) for v in changed.bounds] if not changed.is_empty else None,
        'gnd_fill_change_below_y68': fill,
    }


if __name__ == '__main__':
    if sys.argv[1] == 'dump':
        json.dump({'ref': dump(sys.argv[2]), 'new': dump(sys.argv[3])}, open(sys.argv[4], 'w'))
    else:
        print(json.dumps(compare(json.load(open(sys.argv[2])), sys.argv[3]), indent=1))
