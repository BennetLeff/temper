"""Western BUS_P neck, In2 plus the B.Cu parallel (D4 condition 1); a screen, not a rating.

Per x-section, sum the nominal IPC-2221B 20 C-rise currents of the In2 strip
(inner k) and the B.Cu strip (outer k). Summing parallel screens assumes each
layer is independently at its screen limit; it is not a thermal model.
"""
import json, sys
from pathlib import Path
from shapely.geometry import LineString, Polygon
from shapely.ops import unary_union

board = json.loads(Path(sys.argv[1]).read_text())
def zone(net, layer):
    return unary_union([Polygon(i['polygon']) for i in board['items']
                        if i['kind'] == 'zone' and i['net'] == net and layer in i['layers']])
def width(g, x, y0=.5, y1=15.0):
    c = g.intersection(LineString([(x, y0), (x, y1)]))
    return sum(p.length for p in (c.geoms if hasattr(c, 'geoms') else [c]) if p.geom_type == 'LineString')
def ipc(w, external):
    return (.048 if external else .024) * 20**.44 * (w * 39.3701 * 2 * 1.37)**.725
in2, bcu = zone('bus_p', 'In2.Cu'), zone('bus_p', 'B.Cu')
rows = []
for x10 in range(600, 841):
    x = x10 / 10
    wi, wb = width(in2, x), width(bcu, x)
    rows.append({'x_mm': x, 'in2_mm': round(wi, 3), 'bcu_mm': round(wb, 3),
                 'screen_a': round(ipc(wi, False) + ipc(wb, True), 2)})
# Stitch banks at x 58.5 and 81.5 bound the parallel section.
span = [r for r in rows if 60.0 <= r['x_mm'] <= 80.0]
worst = min(span, key=lambda r: r['screen_a'])
print(json.dumps({'board_sha256': board['board_sha256'], 'demand_a': 15.0,
                  'worst_between_stitch_banks': worst,
                  'utilization': round(15.0 / worst['screen_a'], 3),
                  'in2_only_worst': min(span, key=lambda r: r['in2_mm'])}, indent=1))
