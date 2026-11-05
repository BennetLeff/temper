"""A charged capacitor connected to the four DUT jacks: what the front end sees (audit AFE-01 to AFE-04).

python3 validation/charged-dut/charged_dut_spice.py [--jobs N] [--quick]  ->  charged-dut.json   (needs ngspice)

Question: how much charged capacitor (C, V) can a user connect before any datasheet limit in the front end is
crossed, and how does that compare with a professional LCR meter? The Keysight/Agilent E4980A manual
(Measurement circuit protection, Table 52) lists 1000 V below 2 uF and sqrt(2/C) V above, i.e. 1 J.

Circuit (cad/design.json nets, Rev F as built):
  J3 HCUR = DUT_HI -> RG (R40 100 R / R41 5 k / R42 100 k via K1/K2/K3) -> SOURCE_BUF -> R104 47 R -> SRC_DRV = U6A out
            (unity follower of EXCITE; the source is off, EXCITE = 0 V)
  J9 LCUR = DUT_LO -> R94 22 R -> TIA_SUM = U7A -IN (+IN = GND); Rf (R43 100 R / R44 5 k / R45 100 k) and C104 100 pF
            from TIA_OUT; C78 100 pF DUT_LO to GND
  J7 HPOT -> U6B +IN directly; R105 1 k HPOT-DUT_HI.  J8 LPOT -> U7B +IN directly; R106 1 k LPOT-DUT_LO.
  Follower outputs see the 1 k + 1 k codec divider (2 k to GND at DC).
  Relays latch, so an unpowered meter keeps its last range: unpowered rows are run for 100 R and 100 k.

Op-amp model (behavioural, one per OPA2810 channel; TI's macromodel uses 50-ohm switches for the ESD cells, which
would understate the current, so it is not used here):
  * input and output ESD cells: diodes to VCC/VEE, IS 1e-15, RS 2 ohm (conduct about 0.6 V beyond a rail);
  * differential input clamp: 300 uA max bias current (SBOS789C 8.3.1, Fig. 57);
  * gain: A0 1e5, GBWP 70 MHz, slew rate 187 V/us (SBOS789C 7.5, 24 V table);
  * output: rail swing VS - 0.23 V (7.5 at 667 ohm), short-circuit current 108 mA (24 V table), drawn from the
    rail it flows from; the output stage is off while VS < 4 V (unpowered meter: only the ESD cells conduct).
Rails: TPS7A49 / TPS7A30 source only (an LDO cannot sink), 11.86 / -11.87 V nominal (regulator_check.json),
  5 uF each (C95/C100 10 uF X7R at about 50 % bias retention plus 3 x 1 uF and the small parts, low side
  taken), loads 35.8 / 39.9 mA (regulator_check.json loads_a) as resistors.  Unpowered: no regulator, rails start
  at 0 V with the same capacitance and load resistors.
Leads (assumed, stated): each BNC lead 1 m RG-58, 100 pF to GND at the jack, 0.3 uH and 0.05 ohm to the clip.
DUT: C with 10 mOhm ESR and 5 nH ESL, charged to V; contact closes at 1 us in 5 ns, after the operating point.

Connection scenarios:
  kelvin       H clip on HCUR + HPOT, L clip on LCUR + LPOT (normal four-terminal use)
  sense_first  only HPOT and LPOT touch (a Kelvin clip's sense jaw lands first)
  current_only only HCUR and LCUR (two-terminal leads; HPOT/LPOT reach the DUT through R105/R106)
  h_to_gnd     C from the H clip (HCUR + HPOT) to GND/shield (an in-circuit, ground-referenced part)
  l_to_gnd     C from the L clip (LCUR + LPOT) to GND/shield

Datasheet limits (pass = every limit held at every instant; there are no pulse ratings to lean on):
  OPA2810 SBOS789C 7.1: input current 10 mA (also 8.3.2: ESD cells "typically 10-mA continuous input and output
    currents"), output current 40 mA, differential input 7 V, total supply 28 V (+-14 V);
  TPS7A49 OUT >= -0.3 V, TPS7A30 OUT <= +0.3 V (abs max, SBVS121 / SBVS125);
  resistors: Yageo RT0603 (R40-R45, R94) working 75 V, UNI-ROYAL 0603WAF (R104-R106) working 50 V (the value used
    by passive_ratings_check.py); peak power <= 0.625 W, the 5 s short-time overload (2.5 x rated voltage, i.e.
    6.25 x 0.1 W), the only overload figure either datasheet gives;
  C78 / C104 C0G 50 V.
Context numbers (not ratings): HBM 2500 V (OPA2810 7.2) is 100 pF through 1.5 k: 1.67 A peak, 0.25 uC.
"""

import argparse
import concurrent.futures as cf
import itertools
import json
import math
import os
import pathlib
import shutil
import subprocess
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
NGSPICE = os.environ.get('NGSPICE') or shutil.which('ngspice') or '/opt/homebrew/bin/ngspice'

VCC_NOM, VEE_NOM = 11.86, -11.87
I_LOAD_P, I_LOAD_N = 0.0358, 0.0399
C_RAIL = 5e-6
L_LEAD, R_LEAD, C_CABLE = 0.3e-6, 0.05, 100e-12
ESR, ESL = 0.01, 5e-9
C_GBW = 1e-3 / (2 * math.pi * 70e6)   # gm 1 mS: GBWP 70 MHz
I_SLEW = 187e6 * C_GBW                # 187 V/us
T_CLOSE, T_RISE = 1e-6, 5e-9   # contact closes in 5 ns

RG = {'100R': 100.0, '5k': 5e3, '100k': 100e3, 'reset': None}
RF = RG
STATES = [('powered', '100R'), ('powered', '5k'), ('powered', '100k'), ('powered', 'reset'),
          ('unpowered', '100R'), ('unpowered', '100k')]
SCENARIOS = ['kelvin', 'sense_first', 'current_only', 'h_to_gnd', 'l_to_gnd']
C_GRID = [10e-9, 1e-6, 100e-6]
V_GRID = [1, 2, 3, 5, 7, 10, 13, 16, 20, 30, 50, 100, 200, 400, 1000]

HBM_PEAK_MA, HBM_UC = 1e3 * 2500 / 1500, 100e-12 * 2500 * 1e6
HBM_I2T = (2500 / 1500) ** 2 * 1500 * 100e-12 / 2   # Ipk^2 tau / 2, tau = 150 ns: 2.08e-7 A^2 s
LIM = {'in_ma': 10.0, 'out_ma': 40.0, 'vdiff': 7.0, 'vs_total': 28.0, 'p_pk_w': 0.625, 'c_v': 50.0}
RES = {  # name: (node a, node b, ohms placeholder, working V)
    'R94': ('dut_lo', 'tia_sum', 22.0, 75.0), 'R104': ('src_drv', 'sbuf', 47.0, 50.0),
    'R105': ('dut_hi', 'hpot', 1e3, 50.0), 'R106': ('dut_lo', 'lpot', 1e3, 50.0),
}
OPAMPS = {  # name: (+IN, -IN, OUT, output load to GND)
    'u6a': ('excite', 'src_drv', 'src_drv', None),
    'u6b': ('hpot', 'hbuf', 'hbuf', 2e3),
    'u7a': ('0', 'tia_sum', 'tia_out', None),
    'u7b': ('lpot', 'lbuf', 'lbuf', 2e3),
}


def opamp(n, p, m, o, load):
    pi, mi, x, oo = f'{n}_pi', f'{n}_mi', f'{n}_x', f'{n}_oo'
    lim = f'min(max(v({x}),v(vee)+0.23),max(v(vcc)-0.23,v(vee)+0.23))'
    pw = 'min(1,max(0,v(vcc)-v(vee)-4))'
    iout = f'{pw}*max(-0.108,min(0.108,({lim}-v({oo}))/1))'
    L = [f'Vam_{n}_p {p} {pi} 0', f'D{n}_pp {pi} vcc DESD', f'D{n}_pn vee {pi} DESD',
         f'Vam_{n}_m {m} {mi} 0', f'D{n}_mp {mi} vcc DESD', f'D{n}_mn vee {mi} DESD',
         f'B{n}_cl {pi} {mi} I=3e-4*tanh((v({pi})-v({mi}))/0.3)',
         f'Rleak_{n}_p {pi} 0 1e12', f'Rleak_{n}_m {mi} 0 1e12',
         f'B{n}_g 0 {x} I={I_SLEW:g}*tanh(1e-3*(v({pi})-v({mi}))/{I_SLEW:g})', f'R{n}_x {x} 0 1e8',
         f'C{n}_x {x} 0 {C_GBW:g}',
         f'D{n}_xp {x} xclp DCL', f'D{n}_xn xcln {x} DCL',
         f'B{n}_src vcc {oo} I=max(0,{iout})', f'B{n}_snk {oo} vee I=max(0,-({iout}))',
         f'C{n}_oo {oo} 0 10p', f'Vam_{n}_o {oo} {o} 0',
         f'Vam_{n}_ep {o} {n}_ep 0', f'D{n}_op {n}_ep vcc DESD',
         f'Vam_{n}_en {n}_en {o} 0', f'D{n}_on vee {n}_en DESD', f'R{n}_obl {o} 0 1e9']
    if load:
        L.append(f'R{n}_load {o} 0 {load:g}')
    return L


def deck(scn, power, rng, c, v, res_ser=0.0):
    """res_ser: an optional series resistor at the HPOT and LPOT follower inputs (protection option A)."""
    L = ['* charged DUT', '.model DESD D(IS=1e-15 N=1 RS=2 CJO=1p)', '.model DCL D(IS=1e-12 N=1 RS=0.1)',
         'Vxclp xclp 0 16', 'Vxcln xcln 0 -16', 'Vexc excite 0 0']
    if power == 'powered':
        L += ['Vrp regp 0 %g' % VCC_NOM, 'Brp 0 vcc I=max(0,min(0.2,(v(regp)-v(vcc))/0.01))',
              'Vrn regn 0 %g' % VEE_NOM, 'Brn vee 0 I=max(0,min(0.2,(v(vee)-v(regn))/0.01))',
              f'Cvcc vcc 0 {C_RAIL:g}', f'Cvee vee 0 {C_RAIL:g}']
    else:
        L += [f'Cvcc vcc 0 {C_RAIL:g}', f'Cvee vee 0 {C_RAIL:g}']
    L += [f'Rlp vcc 0 {VCC_NOM / I_LOAD_P:g}', f'Rln vee 0 {-VEE_NOM / I_LOAD_N:g}']
    for n, (p, m, o, load) in OPAMPS.items():
        L += opamp(n, p, m, o, load)
    L += ['R104 src_drv sbuf 47', 'R94 dut_lo tia_sum 22', 'C78 dut_lo 0 100p', 'C104 tia_sum tia_out 100p']
    if res_ser:
        L += [f'R105 dut_hi hpot_j 1k', f'R106 dut_lo lpot_j 1k',
              f'Rsh hpot_j hpot {res_ser:g}', f'Rsl lpot_j lpot {res_ser:g}']
        hp, lp = 'hpot_j', 'lpot_j'
    else:
        L += ['R105 dut_hi hpot 1k', 'R106 dut_lo lpot 1k']
        hp, lp = 'hpot', 'lpot'
    if RG[rng]:
        L += [f'RG sbuf dut_hi {RG[rng]:g}', f'RF tia_out tia_sum {RF[rng]:g}']
    else:
        L += ['RGopen sbuf 0 1e12', 'RFopen tia_out 0 1e12']
    jacks = {'hcur': 'dut_hi', 'hpot': hp, 'lpot': lp, 'lcur': 'dut_lo'}
    touch = {'kelvin': {'hcur': 'h', 'hpot': 'h', 'lcur': 'l', 'lpot': 'l'},
             'sense_first': {'hpot': 'h', 'lpot': 'l'},
             'current_only': {'hcur': 'h', 'lcur': 'l'},
             'h_to_gnd': {'hcur': 'h', 'hpot': 'h'},
             'l_to_gnd': {'lcur': 'l', 'lpot': 'l'}}[scn]
    for j, node in jacks.items():
        L.append(f'Ccab_{j} {node} 0 {C_CABLE:g}')
        if j in touch:
            L += [f'Rld_{j} {node} {j}_m {R_LEAD:g}', f'Lld_{j} {j}_m clip_{touch[j]} {L_LEAD:g}']
    a, b = ('clip_h', 'clip_l')
    if scn == 'h_to_gnd':
        b = '0'
    if scn == 'l_to_gnd':
        a, b = 'clip_l', '0'
    for clip in ('clip_h', 'clip_l'):
        L.append(f'Rbl_{clip} {clip} 0 1e9')
    # A capacitor charged to V that touches at T_CLOSE is the same circuit as an uncharged one in series with a
    # source that steps from 0 to V at T_CLOSE (no switch, so the operating point and the step both converge).
    L += [f'Ldut {a} dm1 {ESL:g}', f'Resr dm1 dm2 {ESR:g}', f'Cdut dm2 dm3 {c:g}',
          f'Vdut dm3 {b} PWL(0 0 {T_CLOSE:g} 0 {T_CLOSE + T_RISE:g} {v:g})']
    t_end = T_CLOSE + min(max(5 * c * 1e3, 50e-6), 0.5)
    vecs = ['v(vcc)', 'v(vee)'] + [f'v({nd})' for nd in ('dut_hi', 'dut_lo', 'hpot', 'lpot', 'tia_sum', 'tia_out',
                                                      'src_drv', 'sbuf', 'hbuf', 'lbuf')]
    for n, (p, m, o, _) in OPAMPS.items():
        vecs += [f'v({n}_pi)', f'v({n}_mi)'] + [f'i(Vam_{n}_{k})' for k in ('p', 'm', 'o', 'ep', 'en')]
    if res_ser:
        vecs += ['v(hpot_j)', 'v(lpot_j)']
    L += ['OPTIONS_LINE',
          '.control', 'set wr_singlescale', 'set wr_vecnames', 'option numdgt=7',
          f'tran {t_end / 4000:g} {t_end:g} 0 {t_end / 2000:g}',
          'wrdata OUT ' + ' '.join(vecs), '.endc', '.end']
    return '\n'.join(L) + '\n', t_end


OPTIONS = ['.options method=gear reltol=1e-3 abstol=1e-9 itl4=200',
           '.options method=trap reltol=3e-3 abstol=1e-8 chgtol=1e-12 itl4=500 gmin=1e-10',
           '.options method=gear reltol=1e-2 abstol=1e-7 itl4=1000 gmin=1e-9 rshunt=1e10']


def run(case):
    """Simulate one case; a run that stops short of t_end is retried with looser options, then reported."""
    scn, power, rng, c, v, rs = case
    text, t_end = deck(scn, power, rng, c, v, rs)
    log = ''
    for opt in OPTIONS:
        with tempfile.TemporaryDirectory() as td:
            out = pathlib.Path(td) / 'out.txt'
            cir = pathlib.Path(td) / 'c.cir'
            cir.write_text(text.replace('wrdata OUT', f'wrdata {out}').replace('OPTIONS_LINE', opt))
            r = subprocess.run([NGSPICE, '-b', str(cir)], capture_output=True, text=True, timeout=900)
            log = (r.stdout + r.stderr)[-600:]
            if not out.exists():
                continue
            rows = out.read_text().split('\n')
        head = rows[0].split()
        data = [list(map(float, ln.split())) for ln in rows[1:] if ln.strip()]
        if not data or data[-1][0] < 0.999 * t_end:
            continue
        col = {h.lower(): [d[i] for d in data] for i, h in enumerate(head)}
        t = col[head[0].lower()]
        return {'case': case, 'options': opt, **metrics(col, t, rng, rs)}
    return {'case': case, 'error': log}


def t_above(t, y, lim):
    return sum(t[i] - t[i - 1] for i in range(1, len(t)) if min(abs(y[i]), abs(y[i - 1])) > lim)


def i2t(t, y):
    return sum(0.5 * (y[i] ** 2 + y[i - 1] ** 2) * (t[i] - t[i - 1]) for i in range(1, len(t)))


def integ(t, y):
    return sum(0.5 * (abs(y[i]) + abs(y[i - 1])) * (t[i] - t[i - 1]) for i in range(1, len(t)))


def metrics(col, t, rng, rs):
    m = {'opamp': {}, 'res': {}}
    v = lambda nd: col[f'v({nd})']
    for n in OPAMPS:
        ip, im = col[f'i(vam_{n}_p)'], col[f'i(vam_{n}_m)']
        io = col[f'i(vam_{n}_o)']
        ie = [a + b for a, b in zip(col[f'i(vam_{n}_ep)'], col[f'i(vam_{n}_en)'])]
        vd = [a - b for a, b in zip(v(f'{n}_pi'), v(f'{n}_mi'))]
        m['opamp'][n] = {'in_ma': 1e3 * max(max(map(abs, ip)), max(map(abs, im))),
                         'in_uc': 1e6 * max(integ(t, ip), integ(t, im)),
                         't_over_10ma_us': 1e6 * max(t_above(t, ip, 0.01), t_above(t, im, 0.01), t_above(t, ie, 0.01)),
                         'in_i2t': max(i2t(t, ip), i2t(t, im)), 'out_esd_i2t': i2t(t, ie),
                         'out_ma': 1e3 * max(map(abs, io)), 'out_esd_ma': 1e3 * max(map(abs, ie)),
                         'out_esd_uc': 1e6 * integ(t, ie), 'vdiff': max(map(abs, vd))}
    res = dict(RES)
    if RG[rng]:
        res['RG'] = ('sbuf', 'dut_hi', RG[rng], 75.0)
        res['RF'] = ('tia_out', 'tia_sum', RF[rng], 75.0)
    if rs:
        res['Rs_hpot'] = ('hpot_j', 'hpot', rs, 50.0)
        res['Rs_lpot'] = ('lpot_j', 'lpot', rs, 50.0)
    for name, (a, b, ohm, vw) in res.items():
        if name in ('R105', 'R106') and rs:
            a, b = (('dut_hi', 'hpot_j') if name == 'R105' else ('dut_lo', 'lpot_j'))
        dv = [x - y for x, y in zip(v(a), v(b))]
        p = [d * d / ohm for d in dv]
        m['res'][name] = {'ohm': ohm, 'v_pk': max(map(abs, dv)), 'p_pk_w': max(p), 'e_j': integ(t, p), 'v_work': vw}
    m['vcc_max'], m['vee_min'] = max(v('vcc')), min(v('vee'))
    m['vcc_min'], m['vee_max'] = min(v('vcc')), max(v('vee'))
    m['vs_max'] = max(a - b for a, b in zip(v('vcc'), v('vee')))
    m['c78_v'] = max(map(abs, v('dut_lo')))
    m['c104_v'] = max(abs(a - b) for a, b in zip(v('tia_sum'), v('tia_out')))
    return m


def judge(r):
    """Classify the case. A: every rating held. B: only the 10 mA continuous input/ESD current is exceeded, by
    pulses no bigger than the HBM pulse the part is rated for (peak 1.67 A and I2t 2.1e-7 A2s per pin; a longer
    pulse of equal I2t heats the junction less, so this is conservative), every absolute-maximum
    voltage held. C: anything else. Output current above 40 mA is reported but not judged: SBOS789C 7.1 note 4
    makes it a long-term electromigration limit, and the part limits itself at about 100 mA (ISC, 7.5)."""
    a_fail, c_fail, notes = [], [], []
    for n, o in r['opamp'].items():
        for key, label in (('in_ma', 'input'), ('out_esd_ma', 'output ESD')):
            q = o['in_i2t'] if key == 'in_ma' else o['out_esd_i2t']
            if o[key] > LIM['in_ma']:
                a_fail.append(f'{n} {label} {o[key]:.3g} mA > 10')
                if o[key] > HBM_PEAK_MA or q > HBM_I2T:
                    c_fail.append(f'{n} {label} {o[key]:.3g} mA, I2t {q:.2g} A2s > HBM')
        if o['out_ma'] > LIM['out_ma']:
            notes.append(f'{n} output {o["out_ma"]:.3g} mA (transient; self-limited)')
        if o['vdiff'] > LIM['vdiff']:
            c_fail.append(f'{n} Vdiff {o["vdiff"]:.3g} V > 7')
    for name, x in r['res'].items():
        if x['p_pk_w'] > LIM['p_pk_w']:
            c_fail.append(f'{name} {x["p_pk_w"]:.3g} W peak > 0.625')
        if x['v_pk'] > x['v_work']:
            c_fail.append(f'{name} {x["v_pk"]:.3g} V > {x["v_work"]:g} working')
    if r['vs_max'] > LIM['vs_total']:
        c_fail.append(f'supply {r["vs_max"]:.3g} V > 28')
    if r['vcc_min'] < -0.3 or r['vee_max'] > 0.3:
        c_fail.append(f'rail reversed (VCC min {r["vcc_min"]:.2f}, VEE max {r["vee_max"]:.2f})')
    if max(r['c78_v'], r['c104_v']) > LIM['c_v']:
        c_fail.append('C78/C104 > 50 V')
    cls = 'C' if c_fail else ('B' if a_fail else 'A')
    return cls, c_fail + a_fail, notes


def summary(r):
    """The biggest ESD-cell stress of the case, for comparison with the HBM pulse."""
    worst = max(r['opamp'].items(), key=lambda kv: max(kv[1]['in_ma'], kv[1]['out_esd_ma']))
    n, o = worst
    return {'worst_pin': n, 'esd_ma': max(o['in_ma'], o['out_esd_ma']), 'esd_uc': max(o['in_uc'], o['out_esd_uc']),
            'esd_i2t': max(max(x['in_i2t'], x['out_esd_i2t']) for x in r['opamp'].values()),
            't_over_10ma_us': max(x['t_over_10ma_us'] for x in r['opamp'].values()),
            'vdiff_max': max(x['vdiff'] for x in r['opamp'].values()),
            'r_energy_max': max(((k, x['e_j']) for k, x in r['res'].items()), key=lambda kv: kv[1])}


EVENTS = [  # (label, C, V): plausible bench events for this instrument's DUT class
    ('film cap left charged by a DMM diode test', 10e-9, 3.0),
    ('ceramic decoupling cap pulled from a live 5 V board', 1e-6, 5.0),
    ('electrolytic after a 12 V bias test', 100e-6, 12.0),
    ('resonant-tank film cap, partly bled', 1e-6, 30.0),
    ('resonant-tank film cap straight off a running cooker', 1e-6, 400.0),
    ('Keysight E4980A limit at 2 uF (1 J)', 2e-6, 1000.0),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--jobs', type=int, default=max(1, (os.cpu_count() or 2) - 2))
    ap.add_argument('--quick', action='store_true', help='kelvin scenario only, for development')
    a = ap.parse_args()
    scns = ['kelvin'] if a.quick else SCENARIOS
    cases = [(s, p, rg, c, sgn * v, 0.0) for s in scns for (p, rg) in STATES for c in C_GRID
             for v in V_GRID for sgn in (1, -1)]
    ev_cases = [('kelvin', p, rg, c, v, 0.0) for (_, c, v) in EVENTS for (p, rg) in
                (('powered', '100k'), ('powered', '100R'), ('unpowered', '100k'))]
    opt_cases = [(s, 'powered', '100k', 1e-6, sgn * v, 1e3) for s in ('kelvin', 'sense_first') for v in V_GRID
                 for sgn in (1, -1)]
    all_cases = list(dict.fromkeys(cases + ev_cases + opt_cases))
    with cf.ThreadPoolExecutor(a.jobs) as ex:
        res = dict(zip(all_cases, ex.map(run, all_cases)))
    errors = [list(k) for k, r in res.items() if 'error' in r]

    def threshold(s, p, rg, c, rs=0.0):
        """Largest grid voltage (both polarities) in class A, and in class A or B; the limits that end each."""
        out = {}
        for want, key in (({'A'}, 'v_within_ratings'), ({'A', 'B'}, 'v_hbm_scale')):
            ok, first = 0.0, None
            for v in V_GRID:
                bad = []
                for sgn in (1, -1):
                    r = res.get((s, p, rg, c, sgn * v, rs))
                    if r is None or 'error' in r:
                        bad.append('simulation error')
                        continue
                    cls, lims, _ = judge(r)
                    if cls not in want:
                        bad += lims
                if bad:
                    first = {'v': v, 'limits': sorted(set(bad))[:6]}
                    break
                ok = v
            out[key] = ok
            out[key + '_ends_at'] = first
        return out

    table = {s: {f'{p}/{rg}': {f'{c:g}': threshold(s, p, rg, c) for c in C_GRID} for (p, rg) in STATES}
             for s in scns}
    events = []
    for (label, c, v) in EVENTS:
        rows = {}
        for (p, rg) in (('powered', '100k'), ('powered', '100R'), ('unpowered', '100k')):
            r = res[('kelvin', p, rg, c, v, 0.0)]
            if 'error' in r:
                rows[f'{p}/{rg}'] = {'error': True}
                continue
            sm = summary(r)
            cls, lims, notes = judge(r)
            rows[f'{p}/{rg}'] = {'class': cls, 'limits_crossed': lims[:6], 'notes': notes[:4],
                                 'esd_peak_ma': round(sm['esd_ma'], 3),
                                 'esd_charge_uc': round(sm['esd_uc'], 4), 'worst_pin': sm['worst_pin'],
                                 'time_over_10ma_us': round(sm['t_over_10ma_us'], 3),
                                 'esd_i2t_a2s': float(f"{sm['esd_i2t']:.3g}"),
                                 'vdiff_max': round(sm['vdiff_max'], 2),
                                 'max_resistor_energy': [sm['r_energy_max'][0], sm['r_energy_max'][1]],
                                 'vcc_max': round(r['vcc_max'], 2), 'vee_min': round(r['vee_min'], 2)}
        events.append({'event': label, 'c_f': c, 'v': v, 'energy_j': 0.5 * c * v * v,
                       'keysight_limit_v': 1000.0 if c < 2e-6 else math.sqrt(2 / c), 'meter': rows})
    option_a = {s: threshold(s, 'powered', '100k', 1e-6, 1e3) for s in ('kelvin', 'sense_first')}
    out = {
        'generated_by': 'validation/charged-dut/charged_dut_spice.py',
        'assumptions': {'rails_v': [VCC_NOM, VEE_NOM], 'rail_c_f': C_RAIL, 'rail_load_a': [I_LOAD_P, I_LOAD_N],
                        'lead': {'l_h': L_LEAD, 'r_ohm': R_LEAD, 'cable_c_f': C_CABLE},
                        'dut': {'esr': ESR, 'esl': ESL}, 'esd_cell': 'diode IS 1e-15, RS 2 ohm',
                        'opamp': 'A0 1e5, GBW 10 MHz, swing VS-0.23, Isc 108 mA, off below VS 4 V'},
        'limits': LIM, 'v_grid': V_GRID, 'c_grid': C_GRID,
        'keysight_e4980a': {'source': 'E4980A user guide, Measurement circuit protection, Table 52',
                            'rule': '1000 V for C < 2 uF; sqrt(2/C) V for C >= 2 uF (1 J)',
                            'at_c': {f'{c:g}': (1000.0 if c < 2e-6 else round(math.sqrt(2 / c), 1)) for c in C_GRID}},
        'classes': judge.__doc__.split('. ', 1)[1].strip(),
        'hbm_reference': {'peak_ma': HBM_PEAK_MA, 'charge_uc': HBM_UC, 'i2t_a2s': HBM_I2T, 'note': 'OPA2810 7.2 HBM 2500 V (100 pF, 1.5 k)'},
        'safe_voltage': table,
        'events_kelvin': events,
        'option_a_1k_at_follower_inputs': {'powered/100k, C 1 uF': option_a},
        'errors': errors,
        'cases_run': len(all_cases),
    }
    (HERE / 'charged-dut.json').write_text(json.dumps(out, indent=1) + '\n')
    for s, t in table.items():
        for st, row in t.items():
            print(f'{s}/{st}'.ljust(28), '  '.join(f"{c}: A {x['v_within_ratings']:g} / B {x['v_hbm_scale']:g}"
                                                  for c, x in row.items()))
    print('errors:', len(errors))


if __name__ == '__main__':
    main()
