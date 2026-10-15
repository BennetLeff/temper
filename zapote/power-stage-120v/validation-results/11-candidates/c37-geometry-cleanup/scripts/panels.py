"""Before/after panels of cleanup edits.  python3 panels.py BEFORE.json AFTER.json REPORT.json STEP OUT.png [N]"""
import json, sys, math, gzip
sys.path.insert(0, '.')
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
from shapely.geometry import LineString, Polygon, Point
before, after, rep, step, out = sys.argv[1:6]
N = int(sys.argv[6]) if len(sys.argv) > 6 else 24
pads = json.load(open('pads.json')); PXY = {f"{p['ref']}.{p['pad']}": (p['x'], p['y']) for p in pads}
ex = json.load(gzip.open('../verification/native21s35-all-copper.json.gz'))
xy = lambda q: PXY[q] if isinstance(q, str) else tuple(q)
B, A = json.load(open(before)), json.load(open(after))
R = json.load(open(rep))
log = [l for l in R['log'] if l[0] == step]
import random; random.seed(1); random.shuffle(log); log = log[:N]
cols = 6; rows = math.ceil(len(log) / cols)
fig, axs = plt.subplots(rows, cols, figsize=(cols * 3.2, rows * 3.2))
for ax, l in zip(axs.flat, log):
    net, layer = l[1], l[2]
    if step == 'any':
        a_, b_ = eval(l[3]), eval(l[4]); cx, cy = (a_[0]+b_[0])/2, (a_[1]+b_[1])/2
    else:
        cx, cy = eval(l[3])
    win = 2.0
    for p in ex['primitives']:
        if p['kind'] == 'pad' and p['layer'] == layer and abs(p['centre'][0]-cx) < 4 and abs(p['centre'][1]-cy) < 4:
            g = Polygon(p['shell'])
            ax.fill(*g.exterior.xy, color='#f3c' if p['net'] == net else '#ccc', alpha=0.4, lw=0)
    for vv in B['vias']:
        if abs(vv['at'][0]-cx) < 4 and abs(vv['at'][1]-cy) < 4:
            c = plt.Circle(vv['at'], vv['size']/2, color='#c80' if vv['net']==net else '#aaa', alpha=0.5); ax.add_patch(c)
    for src, col, alpha in ((B, '#888', 0.35), (A, '#06c', 0.55)):
        for t in src['tracks']:
            if t['layer'] != layer: continue
            P = [xy(q) for q in t['points']]
            if not any(abs(x-cx) < 4 and abs(y-cy) < 4 for x, y in P): continue
            g = LineString(P).buffer(t['width']/2) if len(P) > 1 else Point(P[0]).buffer(t['width']/2)
            c = col if t['net'] == net else ('#999' if src is B else '#6a6')
            for gg in getattr(g, 'geoms', [g]):
                ax.fill(*gg.exterior.xy, color=c, alpha=alpha if t['net']==net else 0.15, lw=0)
            if t['net'] == net and src is A:
                ax.plot(*zip(*P), color='k', lw=0.4)
    ax.set_xlim(cx-win, cx+win); ax.set_ylim(cy+win, cy-win); ax.set_aspect('equal')
    ax.set_title(f"{net[:18]} {layer}\n{l[4] if len(l)>4 else ''}", fontsize=6); ax.tick_params(labelsize=5)
for ax in list(axs.flat)[len(log):]: ax.axis('off')
plt.tight_layout(); plt.savefig(out, dpi=110)
