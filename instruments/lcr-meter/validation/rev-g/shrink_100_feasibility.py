"""Can Rev G go back to 100 x 100 mm? Courtyard and copper density of the analog core against the rest of the board.

    sh validation/rev-g/shrink_100_feasibility.sh      -> validation/rev-g/shrink-100-feasibility.json

dump (KiCad Python): every footprint's F.CrtYd bounding box from cad/temper-lcr.kicad_pcb.
compare (Python + shapely): the board split by cad/tools/pour.py ANALOG_CORE (Rev F coordinates, +10 mm south of
y 57 on Rev G, as cad/tools/rev_g.py moves it) into the analog core (with the protection band) and the rest; per
region the courtyard fraction, track length per cm2 (cad/routing.json) and vias per cm2; then the rest's
courtyard fraction if 10 mm x 100 mm came out of it, and the full-width courtyard-free rows (a rigid cut needs one).
"""
import json
import sys

CUT, SHIFT = 57.0, 10.0


def dump(path):
    import pcbnew
    b, mm = pcbnew.LoadBoard(path), 1e-6
    out = []
    for fp in b.GetFootprints():
        cy = fp.GetCourtyard(pcbnew.F_CrtYd)
        bb = cy.BBox() if cy.OutlineCount() else fp.GetBoundingBox(False, False)
        out.append({'ref': fp.GetReference(), 'side': 'B' if fp.IsFlipped() else 'F',
                    'box': [round(v * mm, 3) for v in (bb.GetLeft(), bb.GetTop(), bb.GetRight(), bb.GetBottom())]})
    return out


def compare(parts, root):
    from shapely.geometry import LineString, Point, Polygon, box
    from shapely.ops import unary_union
    sys.path.insert(0, f'{root}/cad/tools')
    import pour
    design = json.load(open(f'{root}/cad/design.json'))
    routing = json.load(open(f'{root}/cad/routing.json'))
    x0, y0, x1, y1 = design['board']['outline']
    board = box(x0, y0, x1, y1)
    core = Polygon([(x, y + SHIFT if y > CUT else y) for x, y in pour.ANALOG_CORE]).intersection(board)
    rest = board.difference(core)
    crt = unary_union([box(*p['box']) for p in parts])

    def stats(region):
        a = region.area
        length = sum(LineString(t['points']).intersection(region).length for t in routing['tracks'] if len(t['points']) > 1)
        return {'area_mm2': round(a), 'courtyard_fraction': round(crt.intersection(region).area / a, 3),
                'track_mm_per_cm2': round(length / a * 100, 1),
                'vias_per_cm2': round(sum(region.contains(Point(*v['at'])) for v in routing['vias']) / a * 100, 2),
                'parts': sum(region.contains(box(*p['box']).centroid) for p in parts)}
    r = stats(rest)
    shrunk = r['area_mm2'] - 10 * (x1 - x0)
    free_rows = sum(1 for k in range(int((y1 - y0) / 0.25))
                    if not crt.intersects(box(x0, y0 + k * 0.25, x1, y0 + (k + 1) * 0.25)))
    return {'board_mm': [x1 - x0, y1 - y0], 'sides': sorted({p['side'] for p in parts}),
            'courtyard_fraction_board': round(crt.area / board.area, 3),
            'analog_core_with_band': stats(core), 'rest': r,
            'rest_after_10mm_out': {'area_mm2': shrunk,
                                    'courtyard_fraction': round(crt.intersection(rest).area / shrunk, 3),
                                    'track_mm_per_cm2_if_no_track_shortens': round(r['track_mm_per_cm2'] * r['area_mm2'] / shrunk, 1)},
            'full_width_courtyard_free_rows_mm': free_rows * 0.25}


if __name__ == '__main__':
    if sys.argv[1] == 'dump':
        json.dump(dump(sys.argv[2]), open(sys.argv[3], 'w'))
    else:
        print(json.dumps(compare(json.load(open(sys.argv[2])), sys.argv[3]), indent=1))
