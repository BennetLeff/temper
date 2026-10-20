"""Validate the FD solver against the Hammerstad-Jensen microstrip formula.

Synthetic geometry: solid In1 plane, two isolated F.Cu traces of width w and
lengths 10 mm and 20 mm (12 mm apart).  Per-length capacitance = (C20 - C10)/10
removes end effects.  Run at the grid spacings used for the board.
Writes fd_results/fd_validate.json.
"""
import json
import os
import sys

from common import HERE

W = [0.2, 0.3]


def synth():
    items = []
    y = 0.0
    for w in W:
        for L, name in ((10.0, f'T{w}_10'), (20.0, f'T{w}_20')):
            items.append({'kind': 'track', 'net': name, 'layer': 'F.Cu', 'x1': 3.0, 'y1': y,
                          'x2': 3.0 + L, 'y2': y, 'w': w})
            y += 4.0
    plane = [[[[-5, -5], [40, -5], [40, y + 5], [-5, y + 5], [-5, -5]]]]
    g = {'board_sha256': 'synthetic', 'items': items,
         'zones': [{'net': 'GND', 'layer': 'In1.Cu', 'filled': plane}]}
    (HERE / 'geometry_synth.json').write_text(json.dumps(g))
    return [it['net'] for it in items], y


if __name__ == '__main__':
    nets, ymax = synth()
    os.environ['LP_GEOMETRY'] = 'geometry_synth.json'
    os.environ['LP_CONDUCTORS'] = ','.join(nets)
    import fd3d
    from closed_form import microstrip
    from common import STACKUPS, NOMINAL_STACKUP
    fd3d.WINDOWS['synth'] = (0.0, 26.0, -2.0, ymax - 2.0)
    st = STACKUPS[NOMINAL_STACKUP]
    out = {}
    for dx in [float(a) for a in sys.argv[1:]] or [0.1, 0.05]:
        r = fd3d.solve(dx, 'neumann', NOMINAL_STACKUP, 'synth')
        for w in W:
            c10 = r['maxwell_pF'][f'T{w}_10'][f'T{w}_10']
            c20 = r['maxwell_pF'][f'T{w}_20'][f'T{w}_20']
            per = (c20 - c10) / 10
            hj = microstrip(w, st['prepreg'], st['t_outer'], st['er_prepreg'])[2]
            hj0 = microstrip(w, st['prepreg'], 0.0, st['er_prepreg'])[2]
            out[f'dx={dx}/w={w}'] = {'fd_pF_per_mm': per, 'hammerstad_t0_pF_per_mm': hj0,
                                     'hammerstad_t35um_pF_per_mm': hj, 'fd_over_hj_t0': per / hj0}
            print(dx, w, out[f'dx={dx}/w={w}'])
    (HERE / 'fd_results' / 'fd_validate.json').write_text(json.dumps(out, indent=1))
    os.remove(HERE / 'geometry_synth.json')
