#!/usr/bin/env python3
"""Enclosure surface temperature rise, Rev E vs Rev F box, natural convection + radiation.

  python3 validation/rev-f/enclosure_thermal.py      -> validation/rev-f/enclosure-thermal.json

Model (an ESTIMATE of the box wall, not a bound, and not a part temperature):
  - the 2.3 W board dissipation (rev-f-plan.md, risk 7) all leaves through the enclosure walls;
  - the aluminium box is isothermal (k ~ 150-200 W/m K, 2-3 mm walls: wall gradients << 1 K at 2.3 W);
  - ambient air and surroundings at 25 C, still air, sea-level air properties at the film temperature;
  - vertical walls: Churchill & Chu (1975), all-Ra form, L = box height;
    top face: hot surface facing up, Nu = 0.54 Ra^1/4 (1e4 < Ra < 1e7), 0.15 Ra^1/3 above, L = A/P;
    bottom face: two cases, (a) on a table, adiabatic (no convection, no radiation: the
    conservative case), (b) on feet, hot surface facing down, Nu = 0.27 Ra^1/4 (Incropera 9.32);
  - radiation from every exposed face to 25 C surroundings, emissivity from
    sources/thermal/emissivity-engineeringtoolbox.txt: anodised 0.77 (nominal), black 0.88, bare 0.09.
Not modelled: the board-to-wall path inside the box (internal air convection, radiation, conduction
through standoffs), so the part temperatures are not computed; see the 'parts' entry for the
datasheet RthJA rise of the hottest parts above their local air, which is what remains to add.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
SIGMA = 5.670374419e-8
T_AMB = 298.15
P_W = 2.3
BOXES = {'rev_e': (0.150, 0.115, 0.036), 'rev_f': (0.110, 0.110, 0.036)}   # outside L x W x H, m
EMISSIVITY = {'anodised 0.77': 0.77, 'black anodise 0.88': 0.88, 'bare sheet 0.09': 0.09}


def air(t_film):
    """Dry air at 1 atm, linear fits to Incropera Table A.4 between 300 and 350 K."""
    f = (t_film - 300.0) / 50.0
    k = 0.0263 + f * (0.0300 - 0.0263)
    nu = 15.89e-6 + f * (20.92e-6 - 15.89e-6)
    alpha = 22.5e-6 + f * (29.9e-6 - 22.5e-6)
    return k, nu, alpha, nu / alpha


def h_conv(face, L, dT, t_film):
    k, nu, alpha, pr = air(t_film)
    ra = 9.81 * (1 / t_film) * dT * L ** 3 / (nu * alpha)
    if face == 'vertical':
        nu_ = (0.825 + 0.387 * ra ** (1 / 6) / (1 + (0.492 / pr) ** (9 / 16)) ** (8 / 27)) ** 2
    elif face == 'up':
        nu_ = 0.54 * ra ** 0.25 if ra < 1e7 else 0.15 * ra ** (1 / 3)
    else:  # hot face down
        nu_ = 0.27 * ra ** 0.25
    return nu_ * k / L, ra


def heat(box, eps, dT, feet):
    l, w, h = box
    t_s = T_AMB + dT
    t_f = T_AMB + dT / 2
    faces = [('vertical', 2 * (l + w) * h, h), ('up', l * w, l * w / (2 * (l + w)))]
    if feet:
        faces.append(('down', l * w, l * w / (2 * (l + w))))
    q, detail = 0.0, {}
    for face, area, L in faces:
        hc, ra = h_conv(face, L, dT, t_f)
        qc = hc * area * dT
        qr = eps * SIGMA * area * (t_s ** 4 - T_AMB ** 4)
        q += qc + qr
        detail[face] = {'area_cm2': round(area * 1e4, 1), 'h_conv': round(hc, 2), 'Ra': f'{ra:.2e}',
                        'q_conv_W': round(qc, 3), 'q_rad_W': round(qr, 3)}
    return q, detail


def solve(box, eps, feet):
    lo, hi = 0.01, 200.0
    for _ in range(80):
        mid = (lo + hi) / 2
        if heat(box, eps, mid, feet)[0] > P_W:
            hi = mid
        else:
            lo = mid
    return lo, heat(box, eps, lo, feet)[1]


def main():
    out = {'power_W': P_W, 'ambient_C': T_AMB - 273.15, 'boxes_mm': {k: [v * 1e3 for v in b] for k, b in BOXES.items()},
           'cases': {}}
    print(f'{P_W} W, ambient 25 C, isothermal box wall rise (K)')
    print(f'{"emissivity":20s} {"bottom":8s} {"Rev E":>7s} {"Rev F":>7s} {"F - E":>6s}')
    for en, eps in EMISSIVITY.items():
        for feet in (False, True):
            key = f'{en}, {"on feet" if feet else "on table (bottom adiabatic)"}'
            res = {r: solve(b, eps, feet) for r, b in BOXES.items()}
            out['cases'][key] = {r: {'wall_rise_K': round(dt, 2), 'faces': d} for r, (dt, d) in res.items()}
            e, f = res['rev_e'][0], res['rev_f'][0]
            print(f'{en:20s} {"feet" if feet else "table":8s} {e:7.1f} {f:7.1f} {f - e:+6.1f}')
    # hottest parts: datasheet / regulator_check figures, rise above their LOCAL air (not added up)
    out['parts'] = {
        'U11/U12 TPS7A49/TPS7A30 LDO': {'dissipation_W': [0.239, 0.257], 'RthJA_C_per_W': 63,
                                       'rise_above_local_air_K': [round(0.239 * 63, 1), round(0.257 * 63, 1)],
                                       'basis': 'validation/power-spurs/regulator_check-rev-f.json rows "dissipation at max raw / min out" '
                                                '(2x estimated load); RthJA is the JEDEC-board figure the check quotes'},
        'not_modelled': 'internal air rise between the board and the wall (needs a cavity model or a bench '
                        'thermocouple); part temperature = ambient + wall rise + internal air rise + RthJA x P'}
    (HERE / 'enclosure-thermal.json').write_text(json.dumps(out, indent=1) + '\n')
    print('LDO rise above local air: 15.1 / 16.2 K (RthJA x P, regulator_check figures)')
    print('->', HERE / 'enclosure-thermal.json')


if __name__ == '__main__':
    main()
