"""A charged capacitor connected to the four DUT jacks: what the front end sees (audit AFE-01 to AFE-04, AFE-07).

python3 validation/charged-dut/charged_dut_spice.py [--jobs N] [--quick]  ->  charged-dut.json   (needs ngspice)
python3 validation/charged-dut/charged_dut_spice.py --selftest       model checks against datasheet points
python3 validation/charged-dut/charged_dut_spice.py --bench          -> bench-esd-knee.json, the bring-up prediction
python3 validation/charged-dut/charged_dut_spice.py --compare REF    thresholds that differ from charged-dut.json at git REF
python3 validation/charged-dut/charged_dut_spice.py --check-readme   README tables == tables rendered from the JSON
python3 validation/charged-dut/charged_dut_spice.py --write-readme   rewrite the README's generated tables

Question: how much charged capacitor (C, V) can a user connect before any datasheet limit in the front end is
crossed, and how does that compare with a professional LCR meter? The Keysight/Agilent E4980A manual
(Measurement circuit protection, Table 52) lists 1000 V below 2 uF and sqrt(2/C) V above, i.e. 1 J.

Circuit (cad/design.json nets, Rev F as built):
  J3 HCUR = DUT_HI -> RG (R40 100 R / R41 5 k / R42 100 k via K1/K2/K3) -> SOURCE_BUF -> R104 47 R -> SRC_DRV = U6A out
            (unity follower of EXCITE; the source is off, EXCITE = 0 V)
  J9 LCUR = DUT_LO -> R94 22 R -> TIA_SUM = U7A -IN (+IN = GND); Rf (R43 100 R / R44 5 k / R45 100 k, via K1-K3)
            and C104 100 pF from TIA_OUT; C78 100 pF DUT_LO to GND
  J7 HPOT -> U6B +IN directly; R105 1 k HPOT-DUT_HI.  J8 LPOT -> U7B +IN directly; R106 1 k LPOT-DUT_LO.
  Codec inputs (CODEC below): HIGH_BUF -> C1P, LOW_BUF -> C1M and C2P, TIA_OUT -> C2M; each is 1 k (R60/61/66/67)
  into a 1 k (R62-R65) + 560 pF divider node, 1 uF (C74-C77) to the clamp node, BAT54S (D11-D14) to GND and 3V3A,
  then 470 R (R68-R71) to the TAC5112 pin (40 k input, ADC_CHx_IMP = 10, biased at AVDD / 2).
  3V3A: AP2112K (U15) sources only, 3.3 V; 5 uF (C60 10 uF X5R derated, C68, C61); load 2.2 k (1.5 mA, the
  lowest TAC5112 IAVDD in SLASF24A's supply-current table, so the rail is pumped as easily as possible).
  Relays latch, so an unpowered meter keeps its last range: unpowered rows are run for 100 R and 100 k.

Op-amp model (behavioural, one per OPA2810 channel; TI's macromodel uses 50-ohm switches for the ESD cells, which
would understate the current, so it is not used here):
  * input and output ESD cells: diodes to VCC/VEE, IS 1e-15 (sensitivity run at 1e-12), RS 2 ohm;
  * differential input clamp: 300 uA max bias current (SBOS789C 8.3.1, Fig. 57);
  * gain: A0 1e5, GBWP 70 MHz, slew rate 187 V/us (SBOS789C 7.5, 24 V table);
  * output: rail swing VS - 0.23 V (7.5 at 667 ohm), short-circuit current 108 mA (24 V table), drawn from the
    rail it flows from; the output stage is off while VS < 4 V (unpowered meter: only the ESD cells conduct).
Rails: TPS7A49 / TPS7A30 source only (an LDO cannot sink), 11.86 / -11.87 V nominal (regulator_check.json),
  5 uF each (C95/C100 10 uF X7R at about 50 % bias retention plus 3 x 1 uF and the small parts, low side
  taken), loads 35.8 / 39.9 mA (regulator_check.json loads_a) as resistors.  Unpowered: no regulator, rails start
  at 0 V with the same capacitance and load resistors.  Not modelled: an LDO's reverse path when its output is
  pumped above its input.
BAT54S model: IS 6e-8, N 1.25, RS 1 ohm, at or below every maximum VF in the R+O / Hongjiacheng Rev 2.0 table
  (0.24 / 0.32 / 0.40 / 0.50 / 1.0 V at 0.1 / 1 / 10 / 30 / 100 mA); --selftest checks it.
Leads (assumed, stated): each BNC lead 1 m RG-58, 100 pF to GND at the jack, 0.3 uH and 0.05 ohm to the clip.
DUT: C with 10 mOhm ESR and 5 nH ESL, charged to V; contact closes at 1 us in 5 ns, after the operating point.

Connection scenarios:
  kelvin       H clip on HCUR + HPOT, L clip on LCUR + LPOT (normal four-terminal use)
  sense_first  only HPOT and LPOT touch (a Kelvin clip's sense jaw lands first)
  current_only only HCUR and LCUR (two-terminal leads; HPOT/LPOT reach the DUT through R105/R106)
  h_to_gnd     C from the H clip (HCUR + HPOT) to GND/shield (an in-circuit, ground-referenced part)
  l_to_gnd     C from the L clip (LCUR + LPOT) to GND/shield

Datasheet limits (judged at every instant):
  OPA2810 SBOS789C 7.1: input current 10 mA (also 8.3.2: ESD cells "typically 10-mA continuous input and output
    currents"), output current 40 mA (note 4: electromigration, reported only), differential input 7 V, total
    supply 28 V (+-14 V);
  TPS7A49 OUT >= -0.3 V, TPS7A30 OUT <= +0.3 V, and OUT no more than 0.3 V beyond IN (abs max, SBVS121 /
    SBVS125: "OUT pin to IN pin" 0.3 V). IN is RAW_P / RAW_N at their weakest corner from
    validation/power-spurs/regulator_check.json when powered, and 0 V unpowered;
  TAC5112 SLASF24A 6.1: analog input pins -0.3 .. 5.656 V, AVDD -0.3 .. 3.9 V. The BAT54S negative clamp holds a
    pin at -(0.3..0.4) V on any fast negative step at a follower or TIA output, in normal overloads too: that is
    audit AFE-07, accepted with a bench check. Down to -0.45 V it is reported (v_strict counts it as a failure);
    below -0.45 V it is class C;
  BAT54S: IFSM 600 mA (non-repetitive, 8.3 ms half sine; a shorter pulse of the same peak is milder);
  resistors: working voltage, Yageo RT0603 (R40-R45, R60-R67, R94) 75 V, UNI-ROYAL 0603WAF (R68-R71, R104-R106) 50 V;
  capacitors: C78 / C104 / C69-C73 C0G 50 V, C74-C77 X7R 50 V.
Stresses with no datasheet pulse figure are reported as 'unrated', not judged:
  resistor peak power above 0.625 W (the 5 s short-time overload, 2.5 x rated voltage, is the only overload figure
  either resistor datasheet gives, and it is not a pulse rating), with the pulse energy;
  relay contact current above 2 A (TQ2SA: 2 A is the contact carrying current, a continuous figure).
Context numbers (not ratings): HBM 2500 V (OPA2810 7.2) is 100 pF through 1.5 k: 1.67 A peak, 0.25 uC.
"""

import argparse
import concurrent.futures as cf
import json
import math
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
REG = json.loads((HERE.parent / 'power-spurs' / 'regulator_check.json').read_text())
LDO_IN = {'powered': (REG['vpos']['min'], REG['vneg']['min']), 'unpowered': (0.0, 0.0)}  # (TPS7A49 IN, TPS7A30 IN)
NGSPICE = os.environ.get('NGSPICE') or shutil.which('ngspice') or '/opt/homebrew/bin/ngspice'

VCC_NOM, VEE_NOM = 11.86, -11.87
I_LOAD_P, I_LOAD_N = 0.0358, 0.0399
C_RAIL = 5e-6
V3A_NOM, C_3V3A, I_LOAD_3V3A, I_LIM_3V3A = 3.3, 5e-6, 1.5e-3, 0.6
L_LEAD, R_LEAD, C_CABLE = 0.3e-6, 0.05, 100e-12
ESR, ESL = 0.01, 5e-9
C_GBW = 1e-3 / (2 * math.pi * 70e6)   # gm 1 mS: GBWP 70 MHz
I_SLEW = 187e6 * C_GBW                # 187 V/us
T_CLOSE, T_RISE = 1e-6, 5e-9   # contact closes in 5 ns
ESD_IS, ESD_IS_ALT = 1e-15, 1e-12
DBAT = 'D(IS=6e-8 N=1.25 RS=1 CJO=18p)'
BAT54_VF_MAX = [(1e-4, 0.24), (1e-3, 0.32), (1e-2, 0.40), (3e-2, 0.50), (1e-1, 1.00)]  # R+O Rev 2.0, (A, V)

RG = {'100R': 100.0, '5k': 5e3, '100k': 100e3, 'reset': None}
RF = RG
STATES = [('powered', '100R'), ('powered', '5k'), ('powered', '100k'), ('powered', 'reset'),
          ('unpowered', '100R'), ('unpowered', '100k')]
UNPOWERED = [s for s in STATES if s[0] == 'unpowered']
SCENARIOS = ['kelvin', 'sense_first', 'current_only', 'h_to_gnd', 'l_to_gnd']
C_GRID = [10e-9, 1e-6, 100e-6]
V_GRID = [0.5, 1, 2, 3, 5, 7, 10, 13, 16, 20, 30, 50, 100, 200, 400, 1000]

HBM_PEAK_MA, HBM_UC = 1e3 * 2500 / 1500, 100e-12 * 2500 * 1e6
HBM_I2T = (2500 / 1500) ** 2 * 1500 * 100e-12 / 2   # Ipk^2 tau / 2, tau = 150 ns: 2.08e-7 A^2 s
LIM = {'in_ma': 10.0, 'out_ma': 40.0, 'vdiff': 7.0, 'vs_total': 28.0, 'c_v': 50.0,
       'ldo_out_beyond_in_v': 0.3, 'codec_pin_v': [-0.3, 5.656], 'codec_pin_afe07_v': -0.45, 'avdd_v': [-0.3, 3.9], 'bat54_ifsm_ma': 600.0,
       'unrated_r_peak_w': 0.625, 'unrated_relay_a': 2.0}
RES = {  # name: (node a, node b, ohms, working V)
    'R94': ('dut_lo', 'tia_sum', 22.0, 75.0), 'R104': ('src_drv', 'sbuf', 47.0, 50.0),
    'R105': ('dut_hi', 'hpot', 1e3, 50.0), 'R106': ('dut_lo', 'lpot', 1e3, 50.0),
}
OPAMPS = {  # name: (+IN, -IN, OUT)
    'u6a': ('excite', 'src_drv', 'src_drv'),
    'u6b': ('hpot', 'hbuf', 'hbuf'),
    'u7a': ('0', 'tia_sum', 'tia_out'),
    'u7b': ('lpot', 'lbuf', 'lbuf'),
}
CODEC = [  # (channel, source node, top R, bottom R, filter C, coupling C, BAT54S, pin R)
    ('c1p', 'hbuf', 'R60', 'R65', 'C73', 'C77', 'D14', 'R71'),
    ('c1m', 'lbuf', 'R61', 'R64', 'C72', 'C76', 'D13', 'R70'),
    ('c2p', 'lbuf', 'R66', 'R63', 'C70', 'C75', 'D12', 'R69'),
    ('c2m', 'tia_out', 'R67', 'R62', 'C69', 'C74', 'D11', 'R68'),
]


def opamp(n, p, m, o):
    pi, mi, x, oo = f'{n}_pi', f'{n}_mi', f'{n}_x', f'{n}_oo'
    lim = f'min(max(v({x}),v(vee)+0.23),max(v(vcc)-0.23,v(vee)+0.23))'
    pw = 'min(1,max(0,v(vcc)-v(vee)-4))'
    iout = f'{pw}*max(-0.108,min(0.108,({lim}-v({oo}))/1))'
    return [f'Vam_{n}_p {p} {pi} 0', f'D{n}_pp {pi} vcc DESD', f'D{n}_pn vee {pi} DESD',
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


def codec_net(powered):
    """3V3A and the four codec input legs (follower or TIA output -> divider -> 1 uF -> BAT54S clamp -> pin)."""
    L = [f'.model DBAT {DBAT}']
    if powered:
        L += [f'Vr3 reg3 0 {V3A_NOM:g}', f'Br3 0 v3a I=max(0,min({I_LIM_3V3A:g},(v(reg3)-v(v3a))/0.01))']
    L += [f'Cv3a v3a 0 {C_3V3A:g}', f'Rl3 v3a 0 {V3A_NOM / I_LOAD_3V3A:g}', 'Bcm vcm 0 V=0.5*v(v3a)']
    for k, src, *_ in CODEC:
        L += [f'Rtop_{k} {src} div_{k} 1k', f'Rbot_{k} div_{k} 0 1k', f'Cf_{k} div_{k} 0 560p',
              f'Cc_{k} div_{k} clp_{k} 1u',
              f'Vam_bh_{k} clp_{k} bh_{k} 0', f'Dbh_{k} bh_{k} v3a DBAT',
              f'Vam_bl_{k} bl_{k} clp_{k} 0', f'Dbl_{k} 0 bl_{k} DBAT',
              f'Rpin_{k} clp_{k} pin_{k} 470', f'Rin_{k} pin_{k} vcm 40k']
    return L


def codec_vecs():
    vecs = ['v(v3a)']
    for k, *_ in CODEC:
        vecs += [f'v(div_{k})', f'v(clp_{k})', f'v(pin_{k})', f'i(Vam_bh_{k})', f'i(Vam_bl_{k})']
    return vecs


def deck(scn, power, rng, c, v, res_ser=0.0, esd_is=ESD_IS, prot=None):
    """res_ser: an optional series resistor at the HPOT and LPOT follower inputs (protection option A).
    prot: an optional protection network, {'lines': [...], 'vecs': [...]}. The leads and cable capacitance then
    land on jack nodes jk_hcur, jk_hpot, jk_lpot, jk_lcur, and the lines must connect those to the board nodes
    dut_hi, hpot, lpot and dut_lo (validation/rev-g-protection/). Without it the deck is unchanged."""
    L = ['* charged DUT', f'.model DESD D(IS={esd_is:g} N=1 RS=2 CJO=1p)', '.model DCL D(IS=1e-12 N=1 RS=0.1)',
         'Vxclp xclp 0 16', 'Vxcln xcln 0 -16', 'Vexc excite 0 0']
    if power == 'powered':
        L += ['Vrp regp 0 %g' % VCC_NOM, 'Brp 0 vcc I=max(0,min(0.2,(v(regp)-v(vcc))/0.01))',
              'Vrn regn 0 %g' % VEE_NOM, 'Brn vee 0 I=max(0,min(0.2,(v(vee)-v(regn))/0.01))']
    L += [f'Cvcc vcc 0 {C_RAIL:g}', f'Cvee vee 0 {C_RAIL:g}']
    L += [f'Rlp vcc 0 {VCC_NOM / I_LOAD_P:g}', f'Rln vee 0 {-VEE_NOM / I_LOAD_N:g}']
    for n, (p, m, o) in OPAMPS.items():
        L += opamp(n, p, m, o)
    L += codec_net(power == 'powered')
    L += ['R104 src_drv sbuf 47', 'R94 dut_lo tia_sum 22', 'C78 dut_lo 0 100p', 'C104 tia_sum tia_out 100p']
    if res_ser:
        L += ['R105 dut_hi hpot_j 1k', 'R106 dut_lo lpot_j 1k',
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
    if prot:
        jacks = {j: f'jk_{j}' for j in jacks}
        L += prot['lines']
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
    for n in OPAMPS:
        vecs += [f'v({n}_pi)', f'v({n}_mi)'] + [f'i(Vam_{n}_{k})' for k in ('p', 'm', 'o', 'ep', 'en')]
    vecs += codec_vecs()
    if prot:
        vecs += prot.get('vecs', [])
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


def spice(text, t_end):
    """Run a deck whose wrdata target is OUT; returns (columns, options) or (None, log)."""
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
        col['time'] = col[head[0].lower()]
        return col, opt
    return None, log


def run(case):
    """Simulate one case; a run that stops short of t_end is retried with looser options, then reported."""
    scn, power, rng, c, v, rs, esd_is = case
    text, t_end = deck(scn, power, rng, c, v, rs, esd_is)
    col, opt = spice(text, t_end)
    if col is None:
        return {'case': case, 'error': opt}
    return {'case': case, 'options': opt, **metrics(col, col['time'], rng, rs)}


def t_above(t, y, lim):
    return sum(t[i] - t[i - 1] for i in range(1, len(t)) if min(abs(y[i]), abs(y[i - 1])) > lim)


def i2t(t, y):
    return sum(0.5 * (y[i] ** 2 + y[i - 1] ** 2) * (t[i] - t[i - 1]) for i in range(1, len(t)))


def integ(t, y):
    return sum(0.5 * (abs(y[i]) + abs(y[i - 1])) * (t[i] - t[i - 1]) for i in range(1, len(t)))


def metrics(col, t, rng, rs):
    m = {'opamp': {}, 'res': {}, 'codec': {}, 'relay': {}}
    zero = [0.0] * len(t)
    v = lambda nd: zero if nd == '0' else col[f'v({nd})']
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
        res['R105'] = ('dut_hi', 'hpot_j', 1e3, 50.0)
        res['R106'] = ('dut_lo', 'lpot_j', 1e3, 50.0)
        res['Rs_hpot'] = ('hpot_j', 'hpot', rs, 50.0)
        res['Rs_lpot'] = ('lpot_j', 'lpot', rs, 50.0)
    for k, src, rtop, rbot, cf, cc, d, rpin in CODEC:
        res[rtop] = (src, f'div_{k}', 1e3, 75.0)
        res[rbot] = (f'div_{k}', '0', 1e3, 75.0)
        res[rpin] = (f'clp_{k}', f'pin_{k}', 470.0, 50.0)
        ib = [max(abs(a), abs(b)) for a, b in zip(col[f'i(vam_bh_{k})'], col[f'i(vam_bl_{k})'])]
        m['codec'][k] = {'bat': d, 'bat_ma': 1e3 * max(ib), 'pin_v_max': max(v(f'pin_{k}')),
                         'pin_v_min': min(v(f'pin_{k}')), 'cf': cf, 'cf_v': max(map(abs, v(f'div_{k}'))),
                         'cc': cc, 'cc_v': max(abs(a - b) for a, b in zip(v(f'div_{k}'), v(f'clp_{k}')))}
    for name, (a, b, ohm, vw) in res.items():
        dv = [x - y for x, y in zip(v(a), v(b))]
        p = [d * d / ohm for d in dv]
        m['res'][name] = {'ohm': ohm, 'v_pk': max(map(abs, dv)), 'p_pk_w': max(p), 'e_j': integ(t, p), 'v_work': vw}
    for name, rname in (('K1-K3 source contact', 'RG'), ('K1-K3 TIA contact', 'RF')):
        if rname in res:
            a, b, ohm, _ = res[rname]
            i = [(x - y) / ohm for x, y in zip(v(a), v(b))]
            m['relay'][name] = {'i_pk_a': max(map(abs, i)), 't_over_2a_us': 1e6 * t_above(t, i, LIM['unrated_relay_a'])}
    m['vcc_max'], m['vee_min'] = max(v('vcc')), min(v('vee'))
    m['vcc_min'], m['vee_max'] = min(v('vcc')), max(v('vee'))
    m['vs_max'] = max(a - b for a, b in zip(v('vcc'), v('vee')))
    m['v3a_max'], m['v3a_min'] = max(v('v3a')), min(v('v3a'))
    m['c78_v'] = max(map(abs, v('dut_lo')))
    m['c104_v'] = max(abs(a - b) for a, b in zip(v('tia_sum'), v('tia_out')))
    return m


def judge(r):
    """Classify the case. A: every rating held. B: only the 10 mA continuous input/ESD current is exceeded, by
    pulses no bigger than the HBM pulse the part is rated for (peak 1.67 A and I2t 2.1e-7 A2s per pin; a longer
    pulse of equal I2t heats the junction less, so this is conservative), every absolute-maximum voltage held.
    C: anything else. Output current above 40 mA is reported but not judged: SBOS789C 7.1 note 4 makes it a
    long-term electromigration limit, and the part limits itself at about 100 mA (ISC, 7.5). Resistor peak power
    above 0.625 W and relay contact current above 2 A have no datasheet pulse figure: reported as unrated. A
    TAC5112 pin between -0.3 and -0.45 V is the accepted AFE-07 clamp excursion, reported as afe07_pin_v."""
    a_fail, c_fail, notes = [], [], []
    unrated = {'r_peak_w': 0.0, 'r_energy_j': 0.0, 'r_name': None, 'relay_a': 0.0, 'afe07_pin_v': None}
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
        if x['v_pk'] > x['v_work']:
            c_fail.append(f'{name} {x["v_pk"]:.3g} V > {x["v_work"]:g} working')
        if x['p_pk_w'] > LIM['unrated_r_peak_w']:
            notes.append(f'{name} {x["p_pk_w"]:.3g} W peak, {1e6 * x["e_j"]:.3g} uJ (unrated pulse)')
            if x['p_pk_w'] > unrated['r_peak_w']:
                unrated.update(r_peak_w=x['p_pk_w'], r_energy_j=x['e_j'], r_name=name)
    for name, x in r['relay'].items():
        if x['i_pk_a'] > LIM['unrated_relay_a']:
            notes.append(f'{name} {x["i_pk_a"]:.3g} A peak, {x["t_over_2a_us"]:.3g} us over 2 A (unrated pulse)')
            unrated['relay_a'] = max(unrated['relay_a'], x['i_pk_a'])
    for k, x in r['codec'].items():
        if x['bat_ma'] > LIM['bat54_ifsm_ma']:
            c_fail.append(f'{x["bat"]} BAT54S {x["bat_ma"]:.3g} mA > IFSM 600')
        lo, hi = LIM['codec_pin_v']
        if x['pin_v_max'] > hi or x['pin_v_min'] < LIM['codec_pin_afe07_v']:
            c_fail.append(f'TAC5112 {k} pin {x["pin_v_min"]:.3g}..{x["pin_v_max"]:.3g} V outside -0.3..5.656')
        elif x['pin_v_min'] < lo:
            notes.append(f'TAC5112 {k} pin {x["pin_v_min"]:.3g} V (AFE-07 clamp excursion)')
            unrated['afe07_pin_v'] = min(unrated['afe07_pin_v'] or 0.0, x['pin_v_min'])
        if x['cf_v'] > LIM['c_v'] or x['cc_v'] > LIM['c_v']:
            c_fail.append(f'{x["cf"]}/{x["cc"]} > 50 V')
    if r['vs_max'] > LIM['vs_total']:
        c_fail.append(f'supply {r["vs_max"]:.3g} V > 28')
    if r['vcc_min'] < -0.3 or r['vee_max'] > 0.3:
        c_fail.append(f'rail reversed (VCC min {r["vcc_min"]:.2f}, VEE max {r["vee_max"]:.2f})')
    in_p, in_n = LDO_IN[r['case'][1]]
    if r['vcc_max'] > in_p + LIM['ldo_out_beyond_in_v'] or r['vee_min'] < in_n - LIM['ldo_out_beyond_in_v']:
        c_fail.append(f'LDO OUT beyond IN (VCC {r["vcc_max"]:.2f} vs IN {in_p:.2f}, VEE {r["vee_min"]:.2f} vs IN {in_n:.2f})')
    if r['v3a_max'] > LIM['avdd_v'][1] or r['v3a_min'] < LIM['avdd_v'][0]:
        c_fail.append(f'3V3A {r["v3a_min"]:.2f}..{r["v3a_max"]:.2f} V outside TAC5112 AVDD -0.3..3.9')
    if max(r['c78_v'], r['c104_v']) > LIM['c_v']:
        c_fail.append('C78/C104 > 50 V')
    cls = 'C' if c_fail else ('B' if a_fail else 'A')
    return cls, c_fail + a_fail, notes, unrated


def summary(r):
    """The biggest ESD-cell stress of the case, for comparison with the HBM pulse."""
    worst = max(r['opamp'].items(), key=lambda kv: max(kv[1]['in_ma'], kv[1]['out_esd_ma']))
    n, o = worst
    return {'worst_pin': n, 'esd_ma': max(o['in_ma'], o['out_esd_ma']), 'esd_uc': max(o['in_uc'], o['out_esd_uc']),
            'esd_i2t': max(max(x['in_i2t'], x['out_esd_i2t']) for x in r['opamp'].values()),
            't_over_10ma_us': max(x['t_over_10ma_us'] for x in r['opamp'].values()),
            'vdiff_max': max(x['vdiff'] for x in r['opamp'].values()),
            'bat54_ma': max(x['bat_ma'] for x in r['codec'].values()),
            'relay_a': max([x['i_pk_a'] for x in r['relay'].values()] or [0.0]),
            'r_energy_max': max(((k, x['e_j']) for k, x in r['res'].items()), key=lambda kv: kv[1])}


EVENTS = [  # (label, C, V): plausible bench events for this instrument's DUT class
    ('film cap left charged by a DMM diode test', 10e-9, 3.0),
    ('ceramic decoupling cap pulled from a live 5 V board', 1e-6, 5.0),
    ('electrolytic after a 12 V bias test', 100e-6, 12.0),
    ('resonant-tank film cap, partly bled', 1e-6, 30.0),
    ('resonant-tank film cap straight off a running cooker', 1e-6, 400.0),
    ('Keysight E4980A limit at 2 uF (1 J)', 2e-6, 1000.0),
]
EVENT_STATES = (('powered', '100k'), ('powered', '100R'), ('unpowered', '100k'))
OPT_STATES = (('powered', '100k'), ('unpowered', '100R'), ('unpowered', '100k'))


# ---------------------------------------------------------------- self-test: the models against datasheet points

def selftest():
    """1. BAT54S model VF at or below each datasheet maximum, and within 0.1 V of it.
    2. OPA2810 ESD-cell VF at 10 mA for both IS values (README sensitivity row).
    3. Audit AFE-07 hand calculation: an 11 V step on a follower output drives the clamp with
       (11 / 2 + AVDD / 2 - AVDD - VF) / 500 R; the simulated peak must agree within 5 %."""
    out, ok = {'bat54_vf': [], 'esd_vf_10ma': {}, 'afe07_step': {}}, True

    vf = vf_at

    for i, vmax in BAT54_VF_MAX:
        vm = vf(DBAT, i)
        good = vmax - 0.1 <= vm <= vmax or (i >= 0.1 and vm <= vmax)  # 100 mA: the max is loose, 1.0 V
        ok &= good
        out['bat54_vf'].append({'i_a': i, 'model_v': round(vm, 4), 'datasheet_max_v': vmax, 'pass': good})
    for is_ in (ESD_IS, ESD_IS_ALT):
        out['esd_vf_10ma'][f'{is_:g}'] = round(vf(f'D(IS={is_:g} N=1 RS=2)', 0.01), 4)
    # AFE-07: powered 3V3A, one codec leg driven by an ideal 0 -> 11 V step at 1 us.
    k = CODEC[0][0]
    net = [ln.replace(CODEC[0][1], 'drv') if ln.startswith(f'Rtop_{k}') else ln for ln in codec_net(True)]
    net = [ln for ln in net if not any(ln.startswith(f'{p}_{kk}') for kk, *_ in CODEC[1:]
                                       for p in ('Rtop', 'Rbot', 'Cf', 'Cc', 'Vam_bh', 'Dbh', 'Vam_bl', 'Dbl', 'Rpin', 'Rin'))]
    text = '\n'.join(['* afe07'] + net + ['Vdrv drv 0 PWL(0 0 1u 0 1.005u 11)', 'OPTIONS_LINE', '.control',
                      'set wr_singlescale', 'set wr_vecnames', 'tran 1n 20u 0 5n',
                      f'wrdata OUT i(Vam_bh_{k}) v(v3a) v(clp_{k})', '.endc', '.end']) + '\n'
    col, _ = spice(text, 20e-6)
    ib = col[f'i(vam_bh_{k})']
    ipk = max(map(abs, ib))
    v_f = vf(DBAT, ipk)
    v3a = col['v(v3a)'][ib.index(max(ib, key=abs))]
    hand = (11 / 2 + V3A_NOM / 2 - v3a - v_f) / 500
    good = abs(ipk - hand) / hand < 0.05
    ok &= good
    out['afe07_step'] = {'sim_ma': round(1e3 * ipk, 3), 'hand_ma': round(1e3 * hand, 3), 'vf_v': round(v_f, 4),
                         'v3a_at_peak': round(v3a, 4), 'pass': good}
    out['pass'] = bool(ok)
    return out


BENCH_I = (1e-3, -1e-3)
IS_SWEEP = (1e-15, 1e-14, 1e-13, 1e-12, 3e-12, 1e-11, 3e-11, 1e-10)


def vf_at(model, i):
    """Forward voltage of a diode model at current i (A)."""
    text = (f'* vf\n.model DX {model}\nI1 0 a DC {i:g}\nDX a 0 DX\nVt t 0 PWL(0 0 1u 1)\nRt t 0 1\nOPTIONS_LINE\n'
            '.control\nset wr_singlescale\nset wr_vecnames\ntran 0.1u 1u\nwrdata OUT v(a)\n.endc\n.end\n')
    col, _ = spice(text, 1e-6)
    return col['v(a)'][-1]


def bench_prediction():
    """Bring-up check of the unpowered ESD knee: meter unpowered, relays left on 100 k, a current-limited bench
    supply pushes +-1 mA into the HPOT or LPOT centre pin (shell = GND); a DMM reads the pin and the +12 / -12 pad.
    Only 1 mA: unpowered, the LDO inputs are at 0 V and their OUT may not rise more than 0.3 V above IN; at 1 mA
    the rail reaches about 0.25 V. The pin-minus-rail difference is the cell's forward voltage at 1 mA; the sweep
    gives the weakest-knee cell (largest IS) that still keeps the 0.5 V discharge rule."""
    rows = []
    for jack, clip, node in (('HPOT (J7)', 'clip_h', 'hpot'), ('LPOT (J8)', 'clip_l', 'lpot')):
        for i in BENCH_I:
            row = {'jack': jack, 'i_ma': 1e3 * i}
            for is_ in (ESD_IS, ESD_IS_ALT):
                text, _ = deck('sense_first', 'unpowered', '100k', 1e-6, 0.0, 0.0, is_)
                keep = [ln for ln in text.split('\n') if ln.split(' ')[0] not in ('Ldut', 'Resr', 'Cdut', 'Vdut')]
                keep = [('tran 20u 20m 0 20u' if ln.startswith('tran ') else
                         f'wrdata OUT v({node}) v(vcc) v(vee)' if ln.startswith('wrdata ') else ln) for ln in keep]
                keep.insert(1, f'Ibench 0 {clip} DC {i:g}')
                col, _ = spice('\n'.join(keep) + '\n', 20e-3)
                row[f'v_is_{is_:g}'] = round(col[f'v({node})'][-1], 3)
                row[f'rail_is_{is_:g}'] = round(col['v(vcc)' if i > 0 else 'v(vee)'][-1], 3)
                row[f'pin_minus_rail_is_{is_:g}'] = round(row[f'v_is_{is_:g}'] - row[f'rail_is_{is_:g}'], 3)
            rows.append(row)
    # AFE-07 bench check: powered, 100 k range, a 1 uF film cap touched across HCUR-LCUR with two-terminal leads.
    v3a = []
    for v in (5.0, 7.0, 10.0, 13.0):
        r = run(('current_only', 'powered', '100k', 1e-6, v, 0.0, ESD_IS))
        v3a.append({'v_cap': v, 'v3a_max': round(r['v3a_max'], 3), 'class': judge(r)[0]})
    # Which cell strength still keeps the 0.5 V rule: every unpowered scenario, range and C at +-0.5 V in class A.
    sweep = []
    for is_ in IS_SWEEP:
        cases = [(s, p, rg, c, sgn * 0.5, 0.0, is_) for s in SCENARIOS for (p, rg) in UNPOWERED for c in C_GRID
                 for sgn in (1, -1)]
        with cf.ThreadPoolExecutor(max(1, (os.cpu_count() or 2) - 2)) as ex:
            res = list(ex.map(run, cases))
        ok = all('error' not in r and judge(r)[0] == 'A' for r in res)
        vf1 = vf_at(f'D(IS={is_:g} N=1 RS=2)', 1e-3)
        sweep.append({'esd_is': is_, 'vf_1ma': round(vf1, 3), 'rule_0p5v_holds': ok})
    keep = [x for x in sweep if x['rule_0p5v_holds']]
    return {'setup': bench_prediction.__doc__.strip(), 'rows': rows,
            'is_sweep_for_0p5v_rule': sweep,
            'bench_pass_if_pin_minus_rail_at_1ma_above_v': max(keep, key=lambda x: x['esd_is'])['vf_1ma'] if keep else None,
            'v3a_two_terminal_1uF_100k': v3a}


# ---------------------------------------------------------------- README tables, rendered from the JSON

def _g(x):
    return f'{x:g}'


def _span(vals):
    lo, hi = min(vals), max(vals)
    return _g(lo) if lo == hi else f'{_g(lo)}–{_g(hi)}'


def _cell(rows):
    a = [x['v_within_ratings'] for x in rows]
    b = [x['v_hbm_scale'] for x in rows]
    s = _span(a)
    return s if b == a else f'{s} ({_span(b)})'


def render(out):
    sv = out['safe_voltage']
    pw = [f'{p}/{rg}' for p, rg in STATES if p == 'powered']
    up = [f'{p}/{rg}' for p, rg in UNPOWERED]
    cs = [f'{c:g}' for c in C_GRID]
    t = {}
    lines = ['| Scenario | Powered 10 nF | Powered 1 µF | Powered 100 µF | Unpowered 10 nF | Unpowered 1 µF | '
             'Unpowered 100 µF | First limit crossed, powered 1 µF |', '|---|---|---|---|---|---|---|---|']
    for s, rows in sv.items():
        cells = [_cell([rows[st][c] for st in pw]) for c in cs] + [_cell([rows[st][c] for st in up]) for c in cs]
        st = min(pw, key=lambda k: rows[k]['1e-06']['v_within_ratings'])
        end = rows[st]['1e-06']['v_within_ratings_ends_at']
        lim = f"{_g(end['v'])} V ({st.split('/')[1]}): {'; '.join(end['limits'][:2])}" if end else '—'
        lines.append(f'| `{s}` | ' + ' | '.join(cells) + f' | {lim} |')
    t['thresholds'] = '\n'.join(lines)

    lines = ['| Event | C, V, energy | ' + ' | '.join(f'{p.capitalize()} {rg.replace("R", " Ω").replace("k", " kΩ")}'
                                                   for p, rg in EVENT_STATES) + ' |', '|---|---|---|---|---|']
    for e in out['events_kelvin']:
        cells = []
        for p, rg in EVENT_STATES:
            x = e['meter'][f'{p}/{rg}']
            if 'error' in x:
                cells.append('error')
                continue
            ma, q = x['esd_peak_ma'], x['esd_i2t_a2s'] / HBM_I2T
            c = f"{x['class']}: ESD " + (f'{ma:.2g} mA' if ma < 1e3 else f'{ma / 1e3:.2g} A')
            c += ', I²t < 1 % of HBM' if q < 0.01 else f', I²t {q:.2g}× HBM'
            if x['vcc_max'] > 13 or x['vee_min'] < -13 or (p == 'unpowered' and x['vcc_max'] > 0.3):
                c += f"; rails {x['vcc_max']:+.3g} / {x['vee_min']:+.3g} V"
            if x['bat54_peak_ma'] > LIM['bat54_ifsm_ma']:
                c += f"; BAT54S {x['bat54_peak_ma'] / 1e3:.2g} A"
            if x['v3a_max'] > LIM['avdd_v'][1]:
                c += f"; 3V3A {x['v3a_max']:.3g} V"
            if x['relay_peak_a'] > LIM['unrated_relay_a']:
                c += f"; relay {x['relay_peak_a']:.2g} A"
            cells.append(c)
        ej = e['energy_j']
        en = f'{ej * 1e9:.3g} nJ' if ej < 1e-6 else f'{ej * 1e6:.3g} µJ' if ej < 1e-3 else f'{ej * 1e3:.3g} mJ' if ej < 1 else f'{ej:.3g} J'
        cap = f"{e['c_f'] * 1e9:g} nF" if e['c_f'] < 1e-6 else f"{e['c_f'] * 1e6:g} µF"
        lines.append(f"| {e['event'][0].upper() + e['event'][1:]} | {cap}, {_g(e['v'])} V, {en} | " + ' | '.join(cells) + ' |')
    t['events'] = '\n'.join(lines)

    oa = out['option_a_1k_at_follower_inputs']
    lines = ['| Scenario | Meter state (1 µF) | Without | With 1 kΩ |', '|---|---|---|---|']
    for st, rows in oa.items():
        for s, x in rows.items():
            lines.append(f"| `{s}` | {st} | {_cell([sv[s][st]['1e-06']])} | {_cell([x])} |")
    t['option_a'] = '\n'.join(lines)

    es = out['esd_cell_sensitivity']
    vfs = out['selftest']['esd_vf_10ma']
    lines = [f"| Scenario | Meter state (10 nF–100 µF) | IS {_g(ESD_IS)} (VF {vfs[_g(ESD_IS)]:.2f} V at 10 mA) | "
             f"IS {_g(ESD_IS_ALT)} (VF {vfs[_g(ESD_IS_ALT)]:.2f} V) |", '|---|---|---|---|']
    for st, rows in es.items():
        for s, x in rows.items():
            lines.append(f"| `{s}` | {st} | {_cell(list(sv[s][st].values()))} | {_cell(list(x.values()))} |")
    t['esd_sensitivity'] = '\n'.join(lines)

    parts = []
    for s in sv:
        strict = [x['v_strict'] for st in pw for x in sv[s][st].values()]
        within = [x['v_within_ratings'] for st in pw for x in sv[s][st].values()]
        parts.append(f"`{s}` {_span(within)} → {_span(strict)} V")
    t['strict'] = ("Counting the AFE-07 pin excursion as a failure (it happens whenever the TIA or a follower saturates "
                   "negative), the powered limits fall: " + '; '.join(parts) + '.')
    u = out['unrated_in_class_a']
    t['unrated'] = (f"In every case counted as class A, the largest resistor pulse is {u['r_peak_w']:.3g} W peak "
                    f"({u['r_name']}, {u['case']}; {1e3 * u['r_energy_j']:.3g} mJ dissipated over the whole run, an "
                    f"upper bound on the pulse) and the largest relay contact current is {u['relay_a']:.3g} A.")
    st_ = out['selftest']
    t['selftest'] = ('| Check | Model | Datasheet / hand | Pass |\n|---|---|---|---|\n' +
                     '\n'.join(f"| BAT54S VF at {x['i_a'] * 1e3:g} mA | {x['model_v']:.3f} V | ≤ {x['datasheet_max_v']:g} V | "
                               f"{'yes' if x['pass'] else 'NO'} |" for x in st_['bat54_vf']) +
                     f"\n| AFE-07: 11 V step on a follower output, clamp current | {st_['afe07_step']['sim_ma']:.2f} mA | "
                     f"{st_['afe07_step']['hand_ma']:.2f} mA | {'yes' if st_['afe07_step']['pass'] else 'NO'} |")
    return t


def readme_blocks(text):
    return dict(re.findall(r'<!-- generated:(\w+) -->\n((?:(?!<!-- ).)*?)\n?<!-- /generated -->', text, re.S))


def check_readme(write=False):
    out = json.loads((HERE / 'charged-dut.json').read_text())
    tables = render(out)
    path = HERE / 'README.md'
    text = path.read_text()
    have = readme_blocks(text)
    bad = [k for k in tables if have.get(k) != tables[k]]
    if write:
        for k, v in tables.items():
            # (?!<!-- ) keeps a block from running on into the next marker
            text = re.sub(rf'(<!-- generated:{k} -->\n)(?:(?!<!-- ).)*?\n?(<!-- /generated -->)',
                          lambda m: m.group(1) + v + '\n' + m.group(2), text, flags=re.S)
        path.write_text(text)
        bad = [k for k in tables if readme_blocks(text).get(k) != tables[k]]
    missing = [k for k in tables if f'<!-- generated:{k} -->' not in text]
    bad += [k for k in missing if k not in bad]
    print('README tables:', 'match charged-dut.json' if not bad else f'MISMATCH in {bad}')
    return not bad


def compare(ref):
    """Every class-A / HBM-scale threshold that differs from the committed JSON at git ref, with the limits that
    end it now and then, so each change can be traced to a model change."""
    old = json.loads(subprocess.run(['git', 'show', f'{ref}:./charged-dut.json'], cwd=HERE, capture_output=True,
                                    text=True, check=True).stdout)['safe_voltage']
    new = json.loads((HERE / 'charged-dut.json').read_text())['safe_voltage']
    n = 0
    for s, rows in new.items():
        for st, cs in rows.items():
            for c, x in cs.items():
                y = old.get(s, {}).get(st, {}).get(c)
                for key in ('v_within_ratings', 'v_hbm_scale'):
                    if y is None or x[key] != y[key]:
                        n += 1
                        lim = lambda z: (z or {}).get('limits', [])[:2]
                        print(f"{s}/{st} C {c} {key}: {y and y[key]} -> {x[key]}; now ends at "
                              f"{lim(x[key + '_ends_at'])}; was {lim(y and y[key + '_ends_at'])}")
    print(f'{n} thresholds differ from {ref}')


# ---------------------------------------------------------------- main sweep

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--jobs', type=int, default=max(1, (os.cpu_count() or 2) - 2))
    ap.add_argument('--quick', action='store_true', help='kelvin scenario only, for development')
    ap.add_argument('--selftest', action='store_true')
    ap.add_argument('--check-readme', action='store_true')
    ap.add_argument('--write-readme', action='store_true')
    ap.add_argument('--bench', action='store_true')
    ap.add_argument('--compare', metavar='REF')
    a = ap.parse_args()
    if a.compare:
        compare(a.compare)
        sys.exit(0)
    if a.bench:
        b = bench_prediction()
        (HERE / 'bench-esd-knee.json').write_text(json.dumps(b, indent=1) + '\n')
        print(json.dumps(b, indent=1))
        sys.exit(0)
    if a.check_readme or a.write_readme:
        sys.exit(0 if check_readme(a.write_readme) else 1)
    st = selftest()
    print(json.dumps(st, indent=1))
    if a.selftest or not st['pass']:
        sys.exit(0 if st['pass'] else 1)

    scns = ['kelvin'] if a.quick else SCENARIOS
    cases = [(s, p, rg, c, sgn * v, 0.0, ESD_IS) for s in scns for (p, rg) in STATES for c in C_GRID
             for v in V_GRID for sgn in (1, -1)]
    ev_cases = [('kelvin', p, rg, c, v, 0.0, ESD_IS) for (_, c, v) in EVENTS for (p, rg) in EVENT_STATES]
    opt_cases = [(s, p, rg, 1e-6, sgn * v, 1e3, ESD_IS) for s in scns for (p, rg) in OPT_STATES for v in V_GRID
                 for sgn in (1, -1)]
    esd_cases = [(s, p, rg, c, sgn * v, 0.0, ESD_IS_ALT) for s in scns for (p, rg) in UNPOWERED for c in C_GRID
                 for v in V_GRID for sgn in (1, -1)]
    all_cases = list(dict.fromkeys(cases + ev_cases + opt_cases + esd_cases))
    with cf.ThreadPoolExecutor(a.jobs) as ex:
        res = dict(zip(all_cases, ex.map(run, all_cases)))
    errors = [list(k) for k, r in res.items() if 'error' in r]
    unrated_a = {'r_peak_w': 0.0, 'r_energy_j': 0.0, 'r_name': None, 'relay_a': 0.0, 'case': None}

    def threshold(s, p, rg, c, rs=0.0, esd_is=ESD_IS):
        """Largest grid voltage (both polarities) in class A, and in class A or B; the limits that end each."""
        out = {}
        for want, key in (({'A'}, 'v_within_ratings'), ({'A', 'B'}, 'v_hbm_scale'), ({'A'}, 'v_strict')):
            ok, first = 0.0, None
            for v in V_GRID:
                bad = []
                for sgn in (1, -1):
                    r = res.get((s, p, rg, c, sgn * v, rs, esd_is))
                    if r is None or 'error' in r:
                        bad.append('simulation error')
                        continue
                    cls, lims, notes, un = judge(r)
                    if cls not in want:
                        bad += lims
                    elif key == 'v_strict' and un['afe07_pin_v'] is not None:
                        bad += [n for n in notes if 'AFE-07' in n]
                    elif key == 'v_within_ratings' and rs == 0.0 and esd_is == ESD_IS:
                        if un['r_peak_w'] > unrated_a['r_peak_w']:
                            unrated_a.update(r_peak_w=un['r_peak_w'], r_energy_j=un['r_energy_j'], r_name=un['r_name'],
                                             case=f'{s} {p}/{rg} {c * 1e6:g} uF {sgn * v:g} V')
                        unrated_a['relay_a'] = max(unrated_a['relay_a'], un['relay_a'])
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
        for (p, rg) in EVENT_STATES:
            r = res[('kelvin', p, rg, c, v, 0.0, ESD_IS)]
            if 'error' in r:
                rows[f'{p}/{rg}'] = {'error': True}
                continue
            sm = summary(r)
            cls, lims, notes, _ = judge(r)
            rows[f'{p}/{rg}'] = {'class': cls, 'limits_crossed': lims[:8], 'notes': notes[:6],
                                 'esd_peak_ma': round(sm['esd_ma'], 3),
                                 'esd_charge_uc': round(sm['esd_uc'], 4), 'worst_pin': sm['worst_pin'],
                                 'time_over_10ma_us': round(sm['t_over_10ma_us'], 3),
                                 'esd_i2t_a2s': float(f"{sm['esd_i2t']:.3g}"),
                                 'vdiff_max': round(sm['vdiff_max'], 2),
                                 'bat54_peak_ma': round(sm['bat54_ma'], 2), 'relay_peak_a': round(sm['relay_a'], 3),
                                 'max_resistor_energy': [sm['r_energy_max'][0], sm['r_energy_max'][1]],
                                 'vcc_max': round(r['vcc_max'], 2), 'vee_min': round(r['vee_min'], 2),
                                 'v3a_max': round(r['v3a_max'], 3)}
        events.append({'event': label, 'c_f': c, 'v': v, 'energy_j': 0.5 * c * v * v,
                       'keysight_limit_v': 1000.0 if c < 2e-6 else math.sqrt(2 / c), 'meter': rows})
    option_a = {f'{p}/{rg}': {s: threshold(s, p, rg, 1e-6, 1e3) for s in scns} for (p, rg) in OPT_STATES}
    esd_sens = {f'{p}/{rg}': {s: {f'{c:g}': threshold(s, p, rg, c, 0.0, ESD_IS_ALT) for c in C_GRID} for s in scns}
                for (p, rg) in UNPOWERED}
    out = {
        'generated_by': 'validation/charged-dut/charged_dut_spice.py',
        'assumptions': {'rails_v': [VCC_NOM, VEE_NOM], 'rail_c_f': C_RAIL, 'rail_load_a': [I_LOAD_P, I_LOAD_N],
                        '3v3a': {'v': V3A_NOM, 'c_f': C_3V3A, 'load_a': I_LOAD_3V3A, 'source_only': True},
                        'lead': {'l_h': L_LEAD, 'r_ohm': R_LEAD, 'cable_c_f': C_CABLE},
                        'dut': {'esr': ESR, 'esl': ESL}, 'esd_cell': f'diode IS {ESD_IS:g}, RS 2 ohm',
                        'bat54s': DBAT,
                        'opamp': 'A0 1e5, GBWP 70 MHz, slew 187 V/us, swing VS-0.23, Isc 108 mA, off below VS 4 V'},
        'limits': LIM, 'v_grid': V_GRID, 'c_grid': C_GRID,
        'keysight_e4980a': {'source': 'E4980A user guide, Measurement circuit protection, Table 52',
                            'rule': '1000 V for C < 2 uF; sqrt(2/C) V for C >= 2 uF (1 J)',
                            'at_c': {f'{c:g}': (1000.0 if c < 2e-6 else round(math.sqrt(2 / c), 1)) for c in C_GRID}},
        'classes': judge.__doc__.split('. ', 1)[1].strip(),
        'hbm_reference': {'peak_ma': HBM_PEAK_MA, 'charge_uc': HBM_UC, 'i2t_a2s': HBM_I2T, 'note': 'OPA2810 7.2 HBM 2500 V (100 pF, 1.5 k)'},
        'selftest': st,
        'safe_voltage': table,
        'unrated_in_class_a': unrated_a,
        'events_kelvin': events,
        'option_a_1k_at_follower_inputs': option_a,
        'esd_cell_sensitivity': esd_sens,
        'errors': errors,
        'cases_run': len(all_cases),
    }
    (HERE / 'charged-dut.json').write_text(json.dumps(out, indent=1) + '\n')
    for s, t in table.items():
        for st_, row in t.items():
            print(f'{s}/{st_}'.ljust(28), '  '.join(f"{c}: A {x['v_within_ratings']:g} / B {x['v_hbm_scale']:g}"
                                                   for c, x in row.items()))
    print('cases:', len(all_cases), 'errors:', len(errors))


if __name__ == '__main__':
    main()
