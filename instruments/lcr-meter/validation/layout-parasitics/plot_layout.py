"""Plan view of the extracted nets over the actual In1.Cu GND fill (2-D, read-only).

Left: Rev C as routed.  Right: the Rev D R_ISO candidate (geometry_riso.json).
Writes layout.png.
"""
import json
import os

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from shapely.geometry import box

from common import HERE, LAYERS, item_shape, rings_to_polys

WIN = box(153.0, 97.5, 181.0, 126.5)
COL = {'DUT_LO': '#d62728', 'TIA_SUM': '#ff7f0e', 'TIA_OUT': '#1f77b4', 'DUT_HI': '#bcbd22',
       'RF100': '#2ca02c', 'RF5K': '#2ca02c', 'RF100K': '#2ca02c', 'LOW_BUF': '#9467bd',
       'GND': '#555555'}


def draw(ax, gfile, title):
    g = json.loads((HERE / gfile).read_text())
    z = [z for z in g['zones'] if z['layer'] == 'In1.Cu'][0]
    plane = rings_to_polys(z['filled'])
    for cut in g.get('in1_cuts', []):
        plane = plane.difference(rings_to_polys([cut]))
    pl = plane.intersection(WIN)
    for gg in getattr(pl, 'geoms', [pl]):
        x, y = gg.exterior.xy; ax.fill(x, y, color='#e4e4e4', lw=0)
        for h in gg.interiors:
            x, y = h.xy; ax.fill(x, y, color='white', lw=0)
    for it in g['items']:
        c = COL.get(it['net'], '#aab4ff')
        for layer in LAYERS:
            if layer == 'In1.Cu':
                continue
            s = item_shape(it, layer)
            if s is None or not s.intersects(WIN):
                continue
            s = s.intersection(WIN)
            for gg in getattr(s, 'geoms', [s]):
                if gg.geom_type != 'Polygon':
                    continue
                x, y = gg.exterior.xy
                if layer == 'F.Cu':
                    ax.fill(x, y, color=c, lw=0, alpha=0.85)
                else:
                    ax.plot(x, y, color=c, lw=0.6, ls='--')
        if it['kind'] == 'pad' and WIN.contains(item_shape(it, list(it['polys'])[0]).centroid) and \
                it['ref'] in ('U7', 'C104', 'R43', 'R44', 'R45', 'JP4', 'JP5', 'JP6', 'J3', 'R_ISO', 'C53', 'C47'):
            if it['ref'] != 'U7' or it['pad'] in ('1', '2', '4', '5'):
                ax.annotate(f"{it['ref']}.{it['pad']}", (it['x'], it['y']), fontsize=5, ha='center', va='center')
    ax.set_xlim(WIN.bounds[0], WIN.bounds[2]); ax.set_ylim(WIN.bounds[3], WIN.bounds[1])
    ax.set_aspect('equal'); ax.set_title(title, fontsize=8); ax.tick_params(labelsize=6)


fig, axs = plt.subplots(1, 2, figsize=(11, 6.2))
draw(axs[0], 'geometry.json', 'Rev C as routed (grey = In1 GND fill, white = voids/antipads)')
if (HERE / 'geometry_riso.json').exists():
    draw(axs[1], 'geometry_riso.json', 'Rev D candidate: R_ISO at (167.0,105.4); B.Cu star from J3.2 (dashed)')
handles = [plt.Line2D([], [], color=c, lw=4, label=n) for n, c in
           [('DUT_LO (J3 side in Rev D)', COL['DUT_LO']), ('TIA_SUM (Rev D)', COL['TIA_SUM']),
            ('TIA_OUT', COL['TIA_OUT']), ('DUT_HI', COL['DUT_HI']), ('RF nets', COL['RF100']),
            ('LOW_BUF', COL['LOW_BUF']), ('GND', COL['GND'])]]
fig.legend(handles=handles, loc='lower center', ncol=7, fontsize=7, frameon=False)
fig.tight_layout(rect=(0, 0.05, 1, 1))
fig.savefig(HERE / 'layout.png', dpi=130)
print('layout.png', os.path.getsize(HERE / 'layout.png'))
