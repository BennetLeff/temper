"""USB hot-plug overshoot at U16 IN (TPS2553), ngspice transient over cable and capacitor corners (audit PE-1).

python3 validation/power-spurs/hotplug_spice.py [--jobs N]  ->  hotplug_spice.json   (needs ngspice on PATH)

Circuit (cad/design.json, net USB_VBUS): J1 VBUS -> C113 (ceramic, + ESR), C15 100 nF, R5 100 k, D1 SRV05-4 pin 5,
U16 IN.  U16 is off for the whole event (turn-on time up to 3 ms, TPS2553 SLVS841F 7.5), so IN carries no load.
Source: an ideal VBUS source (a host port has >= 120 uF behind it) through the cable's loop R and L.
  * 'a_to_c': a USB-A port is always live, so plugging in closes a hard step (1 ns edge).
  * 'c_to_c': a Type-C source turns VBUS on only after it sees R1/R2 (5.1 k Rd) and ramps it; tr is the ramp.
Limits: TPS2553 SLVS841F 7.1 abs max IN 7 V, 7.3 recommended IN <= 6.5 V.
D1: SRV05-4 (Hongjiacheng rev 2.1) gives VBR >= 6.0 V at 1 mA with no maximum, and VC 13.5 typ / 15 V max at
4 A (8/20 us).  So the pass/fail row is 'no_d1' (a part whose breakdown is above the peak never conducts);
'd1_at_min_vbr' (BV 6.0 V, RS (15 - 6) / 4 = 2.25 ohm) shows the most D1 can do.
As built since 2026-10-30: R121 1.5 ohm in C113's ground leg (net VBUS_DAMP), read from cad/design.json.
Fix candidates (rows starting 'fix:') keep every other part and the same corners; they are how R121 was sized.
Assumed ranges (no committed source; stated here so the result can be re-run with others): cable loop
inductance 0.3-1.5 uH (about 0.5-2 m of power pair), loop resistance 0.05-0.30 ohm (a Type-C 3 A cable allows
500 mV VBUS + 250 mV GND drop at 3 A = 0.25 ohm, plus contacts); C113 DC-bias retention 0.6-1.0 at 5-5.5 V with
+-10 % tolerance; ESR 3 mOhm; C15 100 nF.
"""

import argparse
import concurrent.futures as cf
import itertools
import json
import pathlib
import re
import shutil
import subprocess
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
ABS_MAX, REC_MAX = 7.0, 6.5
VBUS = (5.0, 5.25, 5.5)                      # Type-C vSafe5V upper range; USB 2.0 5.25 V
L_CAB = (0.3e-6, 0.6e-6, 1.0e-6, 1.5e-6)
R_CAB = (0.05, 0.10, 0.20, 0.30)
C_RET = (0.6 * 0.9, 1.0 * 1.1)               # retention x tolerance extremes


def deck(v, l, r, c113, d1, edge, snub=None, esr=3e-3):
    lines = [
        '* hot-plug corner',
        f'Vs src 0 PWL(0 0 {edge:g} {v:g} 1 {v:g})',
        f'Rcab src n1 {r:g}',
        f'Lcab n1 vbus {l:g}',
        f'C113 vbus c1 {c113:g}',
        f'Resr c1 0 {esr:g}',
        'C15 vbus 0 100n',
        'R5 vbus 0 100k',
    ]
    if snub:
        lines += [f'Csn vbus s1 {snub[1]:g}', f'Rsn s1 0 {snub[0]:g}']
    if d1:
        lines += ['D1 0 vbus DZ', '.model DZ D(BV=6.0 IBV=1m RS=2.25 CJO=1p)']
    stop = max(60e-6, 3 * edge)
    lines += [f'.tran {min(2e-9, edge / 20):g} {stop:g} 0 {min(5e-9, edge / 10):g}',
              '.meas tran vpk MAX v(vbus)', '.meas tran vend FIND v(vbus) AT=' + f'{stop:g}', '.end']
    return '\n'.join(lines) + '\n'


def run(case):
    with tempfile.TemporaryDirectory() as td:
        p = pathlib.Path(td) / 'c.cir'
        p.write_text(deck(**case['args']))
        out = subprocess.run(['ngspice', '-b', str(p)], capture_output=True, text=True, timeout=120).stdout
    m = {k: float(v) for k, v in re.findall(r'^(vpk|vend)\s*=\s*([-\d.eE+]+)', out, re.M)}
    assert 'vpk' in m, out[-2000:]
    return {**case['meta'], 'vpk': round(m['vpk'], 3), 'vend': round(m['vend'], 3)}


def corners(c_nom, d1, edge, snub=None, esr=3e-3, label=''):
    for v, l, r, ret in itertools.product(VBUS, L_CAB, R_CAB, C_RET):
        yield {'args': dict(v=v, l=l, r=r, c113=c_nom * ret, d1=d1, edge=edge, snub=snub, esr=esr),
               'meta': dict(set=label, vbus=v, l_uh=l * 1e6, r_ohm=r, c113_uf=round(c_nom * ret * 1e6, 3))}


def summary(rows):
    w = max(rows, key=lambda x: x['vpk'])
    return {'corners': len(rows), 'over_abs_max_7v': sum(x['vpk'] >= ABS_MAX for x in rows),
            'over_recommended_6v5': sum(x['vpk'] > REC_MAX for x in rows),
            'pass': all(x['vpk'] < ABS_MAX for x in rows), 'worst': w,
            'best': min(rows, key=lambda x: x['vpk'])}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--jobs', type=int, default=4)
    a = ap.parse_args()
    assert shutil.which('ngspice'), 'ngspice not on PATH'
    design = {p['ref']: p for p in json.loads((HERE.parents[1] / 'cad/design.json').read_text())['parts']}
    c113 = float(design['C113']['value'].split('uF')[0]) * 1e-6
    assert design['C113']['pins']['1'] == design['U16']['pins']['1'] == 'USB_VBUS'
    # As built: C113's ground leg runs through R121 (net VBUS_DAMP) when the board has it
    leg = design['C113']['pins']['2']
    r121 = 0.0
    if leg != 'GND':
        assert leg == 'VBUS_DAMP' and design['R121']['pins'] == {'1': 'VBUS_DAMP', '2': 'GND'}
        r121 = float(design['R121']['value'].rstrip('R'))
    esr = 3e-3 + r121
    sets = {
        'as_built a_to_c no_d1 (pass/fail row)': corners(c113, False, 1e-9, esr=esr),
        'as_built a_to_c d1_at_min_vbr': corners(c113, True, 1e-9, esr=esr),
        'as_built c_to_c no_d1, 100 us ramp': corners(c113, False, 100e-6, esr=esr),
        'before R121 (C113 4.7 uF straight to GND) a_to_c no_d1': corners(c113, False, 1e-9),
        'before_audit (C113 1 uF) a_to_c no_d1': corners(1e-6, False, 1e-9),
    }
    # Candidate fixes, all no_d1 a_to_c, total VBUS capacitance <= 10 uF (USB 2.0 7.2.4.1).  The snubber's
    # 4.7 uF takes the same retention corner as C113 (same part).
    for rs in (0.22, 0.47, 0.68, 1.0, 1.5, 2.2):
        sets[f'fix: {rs:g} ohm in series with C113'] = corners(c113, False, 1e-9, esr=rs)
    for rs in (0.47, 1.0):
        sets[f'fix: snubber {rs:g} ohm + 4.7 uF beside C113'] = [
            dict(c, args=dict(c['args'], snub=(rs, c['args']['c113']))) for c in corners(c113, False, 1e-9)]
    out = {'ngspice': subprocess.run(['ngspice', '--version'], capture_output=True, text=True).stdout.split('\n')[1]
           .strip(), 'limits_v': {'abs_max': ABS_MAX, 'recommended_max': REC_MAX}}
    with cf.ProcessPoolExecutor(a.jobs) as ex:
        for name, gen in sets.items():
            cases = [dict(c, meta=dict(c['meta'], set=name)) for c in gen]
            out[name] = summary(list(ex.map(run, cases)))
    (HERE / 'hotplug_spice.json').write_text(json.dumps(out, indent=1) + '\n')
    print(json.dumps({k: (v if not isinstance(v, dict) or 'worst' not in v else
                          {kk: v[kk] for kk in ('corners', 'over_abs_max_7v', 'over_recommended_6v5', 'pass', 'worst')})
                      for k, v in out.items()}, indent=1))


if __name__ == '__main__':
    main()
