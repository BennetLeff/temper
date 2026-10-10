"""Plot zones on one layer plus selected nets' tracks in a region. usage: plot_region.py layer x0 x1 y0 y1 out.png net1,net2,..."""
import json, sys, matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon
S = '/private/tmp/claude-501/-Users-bennet-Desktop-temper/5a71b9c0-fe6f-4b0a-a3af-0c109a4e3165/scratchpad'
d = json.load(open(S + '/s13b/copper-dump.json'))
layer, x0, x1, y0, y1, out, nets = sys.argv[1], *map(float, sys.argv[2:6]), sys.argv[6], sys.argv[7].split(',')
fig, ax = plt.subplots(figsize=(14, 14 * (y1 - y0) / (x1 - x0) + 1))
cols = plt.cm.tab20.colors
zn = sorted(set(z['net'] for z in d['zones'] if z['layer'] == layer))
for z in d['zones']:
    if z['layer'] != layer: continue
    c = cols[zn.index(z['net']) % 20]
    ax.add_patch(Polygon(z['pts'], closed=True, fc=c, ec='k', lw=0.3, alpha=0.35))
    for h in z.get('holes') or []:
        ax.add_patch(Polygon(h, closed=True, fc='w', ec='k', lw=0.2))
    xs = [p[0] for p in z['pts']]; ys = [p[1] for p in z['pts']]
    ax.text(sum(xs) / len(xs), sum(ys) / len(ys), z['net'], fontsize=7)
ls = {'F.Cu': '-', 'In1.Cu': '--', 'In2.Cu': ':', 'B.Cu': '-.'}
nc = plt.cm.Set1.colors
for t in d['tracks']:
    if t['net'] in nets:
        ax.plot([t['a'][0], t['b'][0]], [t['a'][1], t['b'][1]], ls[t['layer']], color=nc[nets.index(t['net']) % 9], lw=1.2)
for p in d['pads']:
    if p['net'] in nets or p['ref'] in ('R5', 'U6', 'T1', 'U36', 'J4'):
        ax.add_patch(Polygon(p['pts'], closed=True, fc='none', ec='k', lw=0.4))
for i, n in enumerate(nets):
    ax.plot([], [], color=nc[i % 9], label=n)
ax.legend(fontsize=7, loc='lower right')
ax.set_xlim(x0, x1); ax.set_ylim(y1, y0); ax.set_aspect('equal'); ax.set_title(layer)
fig.savefig(out, dpi=110, bbox_inches='tight')
