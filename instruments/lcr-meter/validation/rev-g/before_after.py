#!/usr/bin/env python3
"""Rev F vs Rev G at the same scale: outline, mounting holes, routed copper, part centres, the protection band.

  python3 validation/rev-g/before_after.py [REV_F_GIT_REV]   (default study/lcr-in-box)
Reads Rev F's cad/design.json and cad/routing.json from git and Rev G's from this tree.
Writes validation/rev-g/before-after.png. As validation/rev-f/before_after.py: 2-D only (matplotlib); copper
F.Cu red, In2.Cu gold, B.Cu blue (In1.Cu is the GND plane and is not drawn). Parts new in Rev G are green rings;
the 10 mm band Rev G adds under the jacks (y 57-67) is shaded.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, Rectangle

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
REV_F = sys.argv[1] if len(sys.argv) > 1 else 'study/lcr-in-box'
COL = {'F.Cu': '#c0392b', 'In2.Cu': '#c9a227', 'B.Cu': '#2e6fbd'}
SPECIAL = {'J1': 'USB-C', 'J3': 'HCUR', 'J7': 'HPOT', 'J8': 'LPOT', 'J9': 'LCUR', 'U1': 'RP2040',
           'U7': 'TIA', 'U13': 'TPS65131', 'U14': 'codec', 'K1': 'K1', 'K4': 'K4'}
BAND = (57.0, 67.0)    # cad/tools/rev_g.py


def git_json(path):
    return json.loads(subprocess.check_output(['git', 'show', f'{REV_F}:./{path}'], cwd=ROOT))


def draw(ax, design, routing, title, new=frozenset(), band=None):
    x0, y0, x1, y1 = design['board']['outline']
    w, h = x1 - x0, y1 - y0
    ax.add_patch(Rectangle((x0, y0), w, h, fill=True, fc='#f4f1e8', ec='k', lw=1.2))
    if band:
        ax.add_patch(Rectangle((x0, band[0]), w, band[1] - band[0], fc='#2e8b57', alpha=0.10, ec='none'))
        ax.annotate('protection band', (x1 - 1, band[1] - 0.8), fontsize=6, ha='right', va='bottom', color='#2e6b47')
    for hx, hy in design['board']['holes']:
        ax.add_patch(Circle((hx, hy), 1.6, fc='white', ec='k', lw=0.6))
    for layer in ('B.Cu', 'In2.Cu', 'F.Cu'):
        for t in routing['tracks']:
            if t['layer'] != layer:
                continue
            xs, ys = zip(*t['points'])
            ax.plot(xs, ys, color=COL[layer], lw=max(0.25, t['width'] * 1.6), alpha=0.85, solid_capstyle='round')
    for v in routing['vias']:
        ax.add_patch(Circle(v['at'], v['diameter'] / 2, fc='#333', ec='none'))
    for p in design['parts']:
        if not p.get('pcb'):
            continue
        x, y = p['pcb'][:2]
        ax.plot(x, y, '.', color='#555', ms=1.5)
        if p['ref'] in new:
            ax.add_patch(Circle((x, y), 1.0, fc='none', ec='#2e8b57', lw=0.9))
        if p['ref'] in SPECIAL:
            ax.annotate(SPECIAL[p['ref']], (x, y), fontsize=6, ha='center', va='center',
                        bbox=dict(boxstyle='round,pad=0.15', fc='white', ec='none', alpha=0.8))
    ax.set_title(f'{title}: {w:g} x {h:g} mm ({w * h / 100:.0f} cm2)', fontsize=9)
    ax.set_xlim(x0 - 3, x0 + 103)
    ax.set_ylim(y0 + 113, y0 - 3)
    ax.set_aspect('equal')
    ax.set_xlabel('mm (board frame)', fontsize=7)
    ax.tick_params(labelsize=6)


def main():
    df, rf = git_json('cad/design.json'), git_json('cad/routing.json')
    dg = json.loads((ROOT / 'cad/design.json').read_text())
    rg = json.loads((ROOT / 'cad/routing.json').read_text())
    on_board = lambda d: {p['ref'] for p in d['parts'] if p.get('pcb')}
    new = on_board(dg) - on_board(df)
    fig, axes = plt.subplots(1, 2, figsize=(11, 6.4))
    draw(axes[0], df, rf, f'Rev F ({REV_F})')
    draw(axes[1], dg, rg, 'Rev G (hand-routed, this tree)', new, BAND)
    fig.suptitle(f'Same scale. Copper: F.Cu red, In2.Cu gold, B.Cu blue; In1.Cu GND plane not drawn. '
                 f'Green rings: the {len(new)} parts new in Rev G', fontsize=8)
    fig.tight_layout()
    out = HERE / 'before-after.png'
    fig.savefig(out, dpi=170)
    print(out)


if __name__ == '__main__':
    main()
