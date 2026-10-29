#!/usr/bin/env python3
"""Rev E vs Rev F at the same scale: outline, mounting holes, routed copper and part centres.

  python3 validation/rev-f/before_after.py [REV_E_COMMIT]   (default 48b012771)
Reads Rev E's cad/design.json and cad/routing.json from git and Rev F's from this tree.
Writes validation/rev-f/before-after.png. 2-D only (matplotlib); copper colour per layer:
F.Cu red, In2.Cu gold, B.Cu blue (In1.Cu is the GND plane and is not drawn).
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
REV_E = sys.argv[1] if len(sys.argv) > 1 else '48b012771'
COL = {'F.Cu': '#c0392b', 'In2.Cu': '#c9a227', 'B.Cu': '#2e6fbd'}
SPECIAL = {'J1': 'USB-C', 'J3': 'HCUR', 'J7': 'HPOT', 'J8': 'LPOT', 'J9': 'LCUR', 'U1': 'RP2040',
           'U7': 'TIA', 'U13': 'TPS65131', 'U14': 'codec', 'K1': 'K1', 'K4': 'K4'}


def git_json(path):
    return json.loads(subprocess.check_output(['git', 'show', f'{REV_E}:instruments/lcr-meter/{path}'], cwd=ROOT))


def board(design):
    b = design['board']
    if 'outline' in b:  # Rev F: build_cad.py takes the outline and holes from design.json
        x0, y0, x1, y1 = b['outline']
        return x0, y0, x1 - x0, y1 - y0, b['holes']
    # Rev E: build_cad.py hard-codes the edge (50,45)-(190,150) and the holes; its design.json
    # "board" entry (140 x 100 at y 50) predates the BNC move of the top edge to y 45.
    return 50, 45, 140, 105, [(54, 54), (186, 54), (54, 146), (186, 146)]


def draw(ax, design, routing, title):
    x0, y0, w, h, holes = board(design)
    ax.add_patch(Rectangle((x0, y0), w, h, fill=True, fc='#f4f1e8', ec='k', lw=1.2))
    for hx, hy in holes:
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
        if p['ref'] in SPECIAL:
            ax.annotate(SPECIAL[p['ref']], (x, y), fontsize=6, ha='center', va='center',
                        bbox=dict(boxstyle='round,pad=0.15', fc='white', ec='none', alpha=0.8))
    ax.set_title(f'{title}: {w:g} x {h:g} mm ({w * h / 100:.0f} cm2)', fontsize=9)
    ax.set_xlim(x0 - 3, x0 + 143)
    ax.set_ylim(y0 + 108, y0 - 3)
    ax.set_aspect('equal')
    ax.set_xlabel('mm (board frame)', fontsize=7)
    ax.tick_params(labelsize=6)


def main():
    de, re_ = git_json('cad/design.json'), git_json('cad/routing.json')
    df = json.loads((ROOT / 'cad/design.json').read_text())
    rf = json.loads((ROOT / 'cad/routing.json').read_text())
    fig, axes = plt.subplots(1, 2, figsize=(14, 5.6))
    draw(axes[0], de, re_, f'Rev E ({REV_E})')
    draw(axes[1], df, rf, 'Rev F (hand-routed, this tree)')
    fig.suptitle('Same scale. Copper: F.Cu red, In2.Cu gold, B.Cu blue; In1.Cu GND plane not drawn', fontsize=8)
    fig.tight_layout()
    out = HERE / 'before-after.png'
    fig.savefig(out, dpi=170)
    print(out)


if __name__ == '__main__':
    main()
