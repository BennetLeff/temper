#!/usr/bin/env python3
"""Sink-model sensitivity for the task 04 res_a / coil_feed cases at the coil terminals J5 / J2.

    python3 -I scripts/terminal_sink.py POWER_COPPER.json.gz [--json OUT.json]

Task 04 (round5-native21/run_board.py) before candidate 35 made each physical F.Cu pad of the sink part one equipotential
node at the pad's centre. For the THR 74650074 that is its four soldered leads. For the SMT 7466004R the one pad is the Ø8.5 / Ø5.7 ring,
whose exported "centre" is the custom-pad anchor on the ring's east side (x + 3.55 mm), so the whole terminal current is
forced into one point. The real part is a brass body (Ø7 face) reflowed over the whole ring; brass is ~1000x thicker than
the 70 um foil, so the ring is close to equipotential.

This script re-solves both cases with run_board's own load_net / solve / sheet_and_heat and three sink models:
- as_run: the pre-c35 task 04 sinks (pad centres; the first s35 chain ran this);
- ring_N: for a pad with a hole and no drill (the SMT ring only), N equipotential points on the ring's mid radius
  round the hole centroid; drilled pads (THR leads) keep their centres, so a THR board gives as_run unchanged.
  ring_24 is what run_board.sink_contacts does from candidate 35 on;
- face: every F.Cu grid point inside the Ø7.0 body footprint that is copper (the soldered contact face, equipotential).
It reports the path resistance, total loss and the copper loss within R_NEAR of the terminal (sheet cells + barrel
network), all scaled to the 29.4 A trip as terminal_heat.py does. 18 and 12 um plating; pitch 0.125 mm as task 04.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import importlib.util
import json
import math
import tempfile
from pathlib import Path

import numpy as np
from shapely.geometry import Point, Polygon

UNIT = Path(__file__).resolve().parents[4]
RB = UNIT / 'validation-results/04-board-current-thermal/round5-native21/run_board.py'
spec = importlib.util.spec_from_file_location('run_board', RB)
rb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rb)

FIFTH = 3.74
BANK = ('C21', 'C22', 'C23', 'C151', 'C152')
CASES = {  # run_cases.py: same sources, sink part and current
    'res_a': ('res_a', [(f'{c}.1', FIFTH) for c in BANK], 'J5.1', (132.0, 70.5)),
    'coil_feed': ('coil_feed', [('T1.2', 18.7)], 'J2.1', (132.0, 85.5)),
}
R_NEAR = 7.0
TRIP = 29.4 / 18.7
BODY_R = 3.5     # 7466004R body Ø7.0 (datasheet rev 001.003 p.1)


def sink_points(pads, ref, model, grid_xy):
    out = []
    for p in pads[ref]:
        drilled = max(p.get('drill_mm') or [0]) > 0
        if model == 'as_run' or drilled or not p['holes']:
            out.append(('F.Cu', *p['centre']))
            continue
        shell, hole = Polygon(p['shell']), Polygon(p['holes'][0])
        cx, cy = hole.centroid.x, hole.centroid.y
        r_in = math.sqrt(hole.area / math.pi)
        r_out = math.sqrt(shell.area / math.pi)
        if model.startswith('ring_'):
            n = int(model.split('_')[1])
            rm = (r_in + r_out) / 2
            out.extend(('F.Cu', cx + rm * math.cos(2 * math.pi * k / n), cy + rm * math.sin(2 * math.pi * k / n))
                       for k in range(n))
        elif model == 'face':
            pad = Polygon(p['shell'], p['holes'])
            xs, ys = grid_xy
            for x in xs[(xs > cx - BODY_R) & (xs < cx + BODY_R)]:
                for y in ys[(ys > cy - BODY_R) & (ys < cy + BODY_R)]:
                    if (x - cx) ** 2 + (y - cy) ** 2 <= BODY_R ** 2 and pad.contains(Point(x, y)):
                        out.append(('F.Cu', float(x), float(y)))
        else:
            raise ValueError(model)
    return out


def near_loss(npz_path, heat, centre):
    z = np.load(npz_path)
    sheet = 0.0
    for k in z.files:
        if k.endswith('_joule_w'):
            lay = k[:-len('_joule_w')]
            X, Y = np.meshgrid(z[f'{lay}_x_mm'], z[f'{lay}_y_mm'], indexing='ij')
            m = (X - centre[0]) ** 2 + (Y - centre[1]) ** 2 <= R_NEAR ** 2
            sheet += float(z[k][m].sum())
    # sheet_and_heat already folds half of each barrel-to-sheet radial edge into the sheet cells; add the barrel's own share
    barrel = sum(sum(r['layer_joule_w'].values()) for r in heat['barrel_heat_by_layer']
                 if (r['xy_mm'][0] - centre[0]) ** 2 + (r['xy_mm'][1] - centre[1]) ** 2 <= R_NEAR ** 2)
    return sheet, barrel


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('copper')
    ap.add_argument('--json')
    ap.add_argument('--models', default='as_run,ring_8,ring_24,face')
    a = ap.parse_args()
    src = Path(a.copper)
    data = json.load(gzip.open(src, 'rt'))
    res = {'board_sha256': data['board_sha256'], 'input_sha256': hashlib.sha256(src.read_bytes()).hexdigest(),
           'run_board_sha256': hashlib.sha256(RB.read_bytes()).hexdigest(),
           'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
           'pitch_mm': 0.125, 'r_near_mm': R_NEAR, 'scale_to_29p4A': TRIP ** 2, 'cases': {}}
    for case, (net_name, sources, sink, centre) in CASES.items():
        for pl in (18, 12):
            net, barrels, pads = rb.load_net(data, net_name, 0.125, pl)
            grids = net._build()[0]
            g = grids['F.Cu']
            srcs = []
            for ref, amps in sources:
                srcs.extend(('F.Cu', *p['centre'], amps / len(pads[ref])) for p in pads[ref])
            for model in a.models.split(','):
                sinks = sink_points(pads, sink, model, (g['xs'], g['ys']))
                solved = net.solve(srcs, sinks)
                with tempfile.TemporaryDirectory() as td:
                    npz = Path(td) / 'h.npz'
                    heat = rb.sheet_and_heat(net, solved, npz)
                    sheet, barrel = near_loss(npz, heat, centre)
                vias = [v for v in solved['via_currents'] if (v['xy'][0] - centre[0]) ** 2 + (v['xy'][1] - centre[1]) ** 2 <= R_NEAR ** 2
                        and math.isfinite(v['amps'])]
                row = {'sink_points': len(sinks), 'r_path_mohm': round(solved['r_ohm'] * 1e3, 4),
                       'path_loss_w_at_29p4A': round(solved['loss_w'] * TRIP ** 2, 4),
                       'near_terminal_loss_w_at_29p4A': round((sheet + barrel) * TRIP ** 2, 4),
                       'near_sheet_w_at_29p4A': round(sheet * TRIP ** 2, 4),
                       'near_barrel_w_at_29p4A': round(barrel * TRIP ** 2, 4),
                       'max_via_or_lead_amps_at_29p4A': round(max((abs(v['amps']) for v in vias), default=0) * TRIP, 3),
                       'energy_balance_error_w': heat['energy_balance_error_w']}
                res['cases'][f'{case}_pl{pl}_{model}'] = row
                print(case, pl, model, json.dumps(row), flush=True)
    if a.json:
        Path(a.json).write_text(json.dumps(res, indent=1) + '\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
