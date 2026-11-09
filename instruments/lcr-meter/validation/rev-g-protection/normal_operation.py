"""Rev G jack protection: what a candidate network costs in normal operation (README, "Normal operation").

python3 validation/rev-g-protection/normal_operation.py   ->  normal-operation.json, README tables (~1 min)
python3 validation/rev-g-protection/normal_operation.py --check-readme
python3 validation/rev-g-protection/normal_operation.py --rust NAME   ->  ../stability-full-chain/revg_network.rs

Each candidate in protection_screen.CANDIDATES is taken with the meter powered (isolation switch closed) and
linearized at its operating point:
  - per jack: c1 + g1 at the BNC, r in series (switch on-resistance + series resistor), c2 + g2 at the board
    node (DUT_HI, HPOT, LPOT, DUT_LO); a summing-node clamp (sch_sum) as c + g at tia_sum;
  - TVS: the screen's model, two back-to-back SPICE junctions (IS, N = 1, CJO = 2 CJ, VJ = 1, M = 0.5, FC = 0.5);
    Schottky pair: protection_screen.SCH_MODEL; both with their full junction C(V) and conduction.
Then:
  1. Accuracy: ../rev-e-accuracy-map run_map() with revE_front.PROT set, in three steps:
       linear  the network at 0 V, fixed: only what calibration cannot take out of a linear, fixed network;
       drift   + its temperature drift between calibration and measurement (TC below, ESTIMATE until the parts
               are chosen; the map's own dT: +-5 degC typical, 15 degC corner);
       level   + amplitude dependence: each clamp's fundamental C and G at its node amplitude for that DUT
               (describing function of the junction), so the standards and the DUT see different values.
     Node amplitudes come from the resistive divider (source, series R, DUT, R94), not a full solve (ESTIMATE).
     The report is the change against the committed map (no network) and the LCR-6100 verdict counts.
  2. The summing-node clamp is at the TIA's virtual ground, which the phasor model holds ideal; its drift is
     taken here against the TIA input impedance Z_f / (1 + A), A = GBW / jf with the OPA2810's 70 MHz.
  3. Signal: current into a short per range, with and without the network.
  4. Noise: series-resistor thermal noise against the codec floor (revE_front.S_ADC).
"""

import argparse
import json
import math
import pathlib
import re
import sys

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'rev-e-accuracy-map'))
import accuracy_map as am  # noqa: E402
import protection_screen as ps  # noqa: E402

fe, s = am.fe, am.s
VT = 0.025852                   # kT/q at 300 K
TC_TVS_C = 1e-3                 # ESTIMATE: junction C, /degC (M dVJ/dT / VJ with dVJ/dT ~ -2 mV/K)
TC_C0G = 30e-6                  # C0G, /degC (same as the map's C0G parts)
TC_RON = 6e-3                   # ESTIMATE: MOSFET-output photoMOS on-resistance, /degC (~x2 over 25-125 degC)
TC_R = 100e-6                   # ESTIMATE: series resistors (thick-film pulse type), /degC
LEAK_DOUBLING = 10.0            # ESTIMATE: junction leakage doubles every 10 degC
RON = 0.1                       # protection_screen: isolation switch closed
GBW = 70e6                      # OPA2810 (charged_dut_spice C_GBW)
FREQS = am.FREQS
JK = {'HC': 'hcur', 'HP': 'hpot', 'LP': 'lpot', 'LC': 'lcur'}


# ------------------------------------------------------------------ junction models
# TVS C(V): none of the chosen TVS datasheets gives a curve, and two abrupt (M = 0.5) junctions back to back are
# exactly linear, which would hide the effect. ESTIMATE: every TVS pair follows the Nexperia PESD3V3L1BSL Fig. 4
# typical shape (part-selection/parts.json: 15.5 pF at 0 V, ~13.7 at +-1 V, ~12.9 at +-2 V), flat beyond 2 V.
TVS_CV = ((0.0, 1.0), (1.0, 13.7 / 15.5), (2.0, 12.9 / 15.5), (10.0, 12.9 / 15.5))
SCH = dict(IS=1e-6, N=1.3, CJO=200e-12, VJ=1.0, M=0.5, FC=0.5)
assert ps.SCH_MODEL == '.model DSCH D(IS=1e-6 N=1.3 RS=0.03 CJO=200p)', 'SCH must follow protection_screen'
TH = np.linspace(0, 2 * np.pi, 256, endpoint=False)
AMP = np.concatenate(([0.0], np.geomspace(1e-4, 4.0, 400)))      # amplitude grid for the lookup tables


def fundamental(y):
    return 2 * np.mean(y * np.sin(TH), axis=-1)


def q_junction(v, d):
    """SPICE depletion charge (no transit time), with the FC linear extension."""
    cjo, vj, m, fc = d['CJO'], d.get('VJ', 1.0), d.get('M', 0.5), d.get('FC', 0.5)
    v = np.asarray(v, float)
    lo = cjo * vj / (1 - m) * (1 - (1 - np.minimum(v, fc * vj) / vj) ** (1 - m))
    f1 = (1 - fc) ** (1 + m)
    x = np.maximum(v - fc * vj, 0.0)
    hi = cjo / f1 * ((1 - fc * (1 + m)) * x + m / (2 * vj) * ((fc * vj + x) ** 2 - (fc * vj) ** 2))
    return lo + hi


def table(fn):
    """fn(amplitude) on AMP, for np.interp."""
    return np.array([fn(a) for a in AMP])


def tvs_cv_ratio():
    """Fundamental C / C(0) of a pair with C(|V|) = TVS_CV, against amplitude."""
    xs, ys = np.array(TVS_CV).T
    vv = np.linspace(0, 10, 2001)
    qv = np.concatenate(([0.0], np.cumsum(np.interp((vv[1:] + vv[:-1]) / 2, xs, ys) * np.diff(vv))))
    q = lambda v: np.sign(v) * np.interp(np.abs(v), vv, qv)
    return table(lambda a: 1.0 if a == 0 else fundamental(q(a * np.sin(TH))) / a)


def pair_tables(d):
    """Antiparallel pair (Schottky or silicon): fundamental C and G against amplitude."""
    nvt = d['N'] * VT
    c = table(lambda a: 2 * d['CJO'] if a == 0 else
              fundamental(q_junction(a * np.sin(TH), d) - q_junction(-a * np.sin(TH), d)) / a)
    g = table(lambda a: 2 * d['IS'] / nvt if a == 0 else fundamental(2 * d['IS'] * np.sinh(a * np.sin(TH) / nvt)) / a)
    return c, g


def pair_model(m):
    """protection_screen sch2 entry (True = DSCH, or a part's diode dict) -> junction dict."""
    return SCH if m is True else dict(IS=m['IS'], N=m['N'], CJO=m['CJO'], VJ=1.0, M=0.5, FC=0.5)


# ------------------------------------------------------------------ small-signal network
def small_signal(cfg):
    """Per board jack: element values at 0 V, the parts that make them, and the summing-node clamp."""
    iso = ps.ISO_PARAM if cfg.get('iso') is True else cfg.get('iso')
    out = {}
    for k, j in JK.items():
        e = dict(c1=0.0, g1=0.0, c2=0.0, g2=0.0, c2_c0g=0.0, c2_tvs=0.0, ron=iso['ron'] if iso else 0.0,
                 rser=cfg.get('r', {}).get(j, 0.0), pair=None)
        if j in cfg.get('tvs', {}):
            e['c1'] = cfg['tvs'][j][2]
            e['g1'] = 1e-12 / (2 * VT)          # the screen's TVS junctions: IS 1e-12, N 1, back to back
        e['g1_sense'] = 1 / cfg['sense'][j] if j in cfg.get('sense', {}) else 0.0   # fixed (thin/thick film)
        e['g1'] += e['g1_sense']
        if j in cfg.get('tvs2', {}):
            e['c2_tvs'] = cfg['tvs2'][j][2]
            e['g2'] += 1e-12 / (2 * VT)
        if j in cfg.get('sch2', {}):
            d = pair_model(cfg['sch2'][j])
            e['pair'] = d
            e['c2'] += 2 * d['CJO']
            e['g2'] += 2 * d['IS'] / (d['N'] * VT)
        e['c2_c0g'] = cfg.get('cap2', {}).get(j, 0.0)
        e['c2'] += e['c2_c0g'] + e['c2_tvs']
        e['r'] = e['ron'] + e['rser']
        out[k] = e
    out['sum'] = None
    if cfg.get('sch_sum'):
        d = SCH
        out['sum'] = dict(c=2 * d['CJO'], g=2 * d['IS'] / (d['N'] * VT))
    return out


class Elements:
    """c1, g1, r, c2, g2 of one jack against temperature change dt (N,) and node amplitudes (N,)."""

    TVS = None

    def __init__(self, e):
        self.e = e
        if Elements.TVS is None:
            Elements.TVS = tvs_cv_ratio()
        self.pair = pair_tables(e['pair']) if e['pair'] else None

    def __call__(self, dt, a_jack, a_board):
        e, leak = self.e, 2.0 ** (dt / LEAK_DOUBLING)
        tvs = lambda a: np.interp(a, AMP, Elements.TVS) * (1 + TC_TVS_C * dt)
        c1 = e['c1'] * tvs(a_jack)
        g1 = (e['g1'] - e['g1_sense']) * leak + e['g1_sense']
        r = np.maximum(e['ron'] * (1 + TC_RON * dt) + e['rser'] * (1 + TC_R * dt), 1e-3)   # PROT's floor
        c2 = e['c2_c0g'] * (1 + TC_C0G * dt) + e['c2_tvs'] * tvs(a_board)
        g2 = (e['g2'] - (2 * e['pair']['IS'] / (e['pair']['N'] * VT) if self.pair else 0.0)) * leak
        if self.pair:
            c2 = c2 + np.interp(a_board, AMP, self.pair[0]) * (1 + TC_TVS_C * dt)
            g2 = g2 + np.interp(a_board, AMP, self.pair[1]) * leak
        return c1, g1, r, c2, g2


# ------------------------------------------------------------------ the phasor model with the network
class Patched:
    """revE_front.PROT set from a candidate; draw_drift adds prot_dt; measure() sets the element scales."""

    def __init__(self, cfg, drift, level):
        self.cfg, self.ss, self.drift, self.level = cfg, small_signal(cfg), drift, level
        self.elements = {k: Elements(self.ss[k]) for k in fe.JACKS}

    def __enter__(self):
        self.saved = (fe.PROT, s.draw_drift, fe.measure)
        ss = self.ss
        fe.PROT = {k: dict(c1=max(ss[k]['c1'], 1e-30), g1=max(ss[k]['g1'], 1e-30), r=max(ss[k]['r'], 1e-3),
                           c2=max(ss[k]['c2'], 1e-30), g2=max(ss[k]['g2'], 1e-30)) for k in fe.JACKS}
        fe.PROT['rcp_at_jack'] = bool(self.cfg.get('rcp_jack'))
        fe.PROT['ref_at_jack'] = bool(self.cfg.get('ref_jack'))
        draw0, measure0, me = s.draw_drift, fe.measure, self

        def draw_drift(corner, rng, n, en):
            d = draw0(corner, rng, n, en)
            r2 = np.random.default_rng([99, n, int(corner)])     # own stream: the map's draws are unchanged
            if not me.drift:
                d['prot_dt'] = np.zeros(n)
            elif corner:
                d['prot_dt'] = s.DT[1] * r2.choice([-1.0, 1.0], n)
            else:
                d['prot_dt'] = s.DT[0] * r2.uniform(-1, 1, n)
            return d

        def measure(f, kelvin, zdut, p, d, rsrc=fe.R_SRC, ref=None, **kw):
            n = p['rc'].shape[0]
            dt = d.get('prot_dt', np.zeros(n))
            amp = me.amplitudes(zdut, ref, rsrc, n) if me.level else {k: (np.zeros(n), np.zeros(n)) for k in fe.JACKS}
            sc = np.ones((n, 4, 5))
            for i, k in enumerate(fe.JACKS):
                vals = me.elements[k](dt, *amp[k])
                for m, (name, v) in enumerate(zip(('c1', 'g1', 'r', 'c2', 'g2'), vals)):
                    sc[:, i, m] = np.asarray(v) / fe.PROT[k][name]
            a, b = measure0(f, kelvin, zdut, p, dict(d, prot=sc), rsrc=rsrc, ref=ref, **kw)
            # accuracy_map folds cells with max(0.0, e), which drops a NaN silently: stop here instead
            assert np.isfinite(a).all() and np.isfinite(b).all(), 'non-finite phasor'
            return a, b

        s.draw_drift, fe.measure = draw_drift, measure
        return self

    def amplitudes(self, zdut, ref, rsrc, n):
        """(jack, board) amplitude per jack from the resistive divider (ESTIMATE, see the module doc)."""
        ss, riso = self.ss, fe.NOM['Riso']
        zlo = ss['LC']['r'] + riso
        if zdut is None:
            z = np.full(n, 1e12, complex) if ref is None else np.broadcast_to(ref, (n,)).astype(complex)
            i = fe.VS / np.abs(z + rsrc + riso)
            vh = i * np.abs(z + riso)
            return {'HC': (vh, vh), 'HP': (vh, vh), 'LP': (i * riso, i * riso), 'LC': (i * riso, i * riso)}
        z = np.broadcast_to(zdut, (n,))
        i = fe.VS / np.abs(z + rsrc + ss['HC']['r'] + zlo)
        vj = i * np.abs(z + zlo)
        return {'HC': (vj, i * np.abs(z + zlo + ss['HC']['r'])), 'HP': (vj, vj),
                'LP': (i * zlo, i * zlo), 'LC': (i * zlo, i * riso)}

    def __exit__(self, *exc):
        fe.PROT, s.draw_drift, fe.measure = self.saved


def map_with(cfg, drift, level):
    with Patched(cfg, drift, level):
        return am.run_map(log=False)


USABLE = 0.01    # a cell counts when the committed map has it within 1 % (|Z| and phase, typical and corner)


def compare(base, new):
    """Worst added error per range x frequency over the usable cells (absolute, and relative to the cell's own
    error), and the LCR-6100 verdict counts over every cell."""
    b = {(c['z'], c['f'], c['range']): c for c in base['cells']}
    worst = {}
    for c in new['cells']:
        o = b[(c['z'], c['f'], c['range'])]
        if max(o['z_typ'], o['th_typ'], o['z_corner'], o['th_corner']) > USABLE:
            continue
        for q in ('z_typ', 'th_typ', 'z_corner', 'th_corner'):
            key = (c['range'], c['f'], q.endswith('corner'))
            dlt = c[q] - o[q]
            if dlt > worst.get(key, (-1, None))[0]:
                worst[key] = (dlt, c['z'], q, c[q] / o[q] - 1)
    counts = {}
    for spec in ('gw_1m', 'gw_0m'):
        for name, out in (('base', base), ('new', new)):
            v = [am.verdict(c, spec) for c in out['best']]
            counts[f'{spec}_{name}'] = {m: v.count(m) for m in '✓~✗'}
    return {'worst': {f'{r}|{f:g}|{"corner" if cor else "typ"}': dict(delta=w[0], z=w[1], quantity=w[2], relative=w[3])
                      for (r, f, cor), w in worst.items()}, 'counts': counts}


# ------------------------------------------------------------------ summing node, signal, noise
def sum_node(ss):
    """Added corner error from the summing-node clamp's drift: |dY| |Z_f / (1 + A)| per range and frequency."""
    if ss['sum'] is None:
        return None
    dt = s.DT[1]
    out = {}
    for r in am.RANGES:
        for f in FREQS:
            w = 2 * math.pi * f
            zf = 1 / (1 / r + 1j * w * fe.NOM['CF'])
            zin = zf / (1 + GBW / (1j * f))
            dy = ss['sum']['g'] * (2 ** (dt / LEAK_DOUBLING) - 1) + 1j * w * ss['sum']['c'] * TC_TVS_C * dt
            y0 = ss['sum']['g'] + 1j * w * ss['sum']['c']
            out[f'{r}|{f:g}'] = dict(cal_term=abs(y0 * zin), drift=abs(dy * zin))
    return out


def signal(ss):
    out = {}
    for r in am.RANGES:
        rs = r + am.R104
        i0 = fe.VS / (rs + fe.NOM['Riso'])
        i1 = fe.VS / (rs + ss['HC']['r'] + ss['LC']['r'] + fe.NOM['Riso'])
        out[str(r)] = dict(i_short_ma=[i0 * 1e3, i1 * 1e3], snr_loss_db=20 * math.log10(i0 / i1))
    return out


def noise(ss):
    """Added thermal noise at the codec pins (the legs halve it, 1k / 1k), against the codec floor.
    POT: the HPOT and LPOT series R at the follower inputs (no current flows in them). LCUR: its series R is in
    the current loop, so the TIA sees e_n / (loop impedance); worst with the DUT shorted, where the loop is
    RG + R104 + both CUR series R + R94."""
    k4t = 4 * 1.380649e-23 * 300
    floor = math.sqrt(fe.S_ADC)
    pot = math.sqrt(k4t * (ss['HP']['r'] + ss['LP']['r'])) * 0.5
    out = dict(codec_floor_v_rthz=floor, pot_at_codec_v_rthz=pot, pot_vs_floor=pot / floor)
    worst = 0.0
    for r in am.RANGES:
        loop = r + am.R104 + ss['HC']['r'] + ss['LC']['r'] + fe.NOM['Riso']
        e = math.sqrt(k4t * ss['LC']['r']) * r / loop * 0.5
        out[f'lcur_{r}_at_codec_v_rthz'] = e
        worst = max(worst, e / floor)
    out['lcur_vs_floor'] = worst
    return out


# ------------------------------------------------------------------ stability-matrix network (Rust)
def rust_network(cfg, corner):
    """Small-signal network for loop_matrix.rs: jacks jhc/jhp/jlp/jlc -> board hi/hpot/lpot/low (+ sum).
    corner 'high': junction C x 2 (H3V3LD5B 25 pF max / 12.5 typ; H4V5HD3B gives no max), leakage x 10 (hot,
    ESTIMATE), switch on-resistance x 2 (TLP172AM 2 ohm max / 1 typ)."""
    ss = small_signal(cfg)
    kc, kg, kr = (1.0, 1.0, 1.0) if corner == 'nom' else (2.0, 10.0, 2.0)
    node = {'HC': ('jhc', 'hi'), 'HP': ('jhp', 'hpot'), 'LP': ('jlp', 'lpot'), 'LC': ('jlc', 'low')}
    lines = []
    for k, (a, b) in node.items():
        e = ss[k]
        r = e['ron'] * kr + e['rser']
        lines.append(f'Rgp{k} {a} {b} {max(r, 1e-3):.6g}')
        for tag, nd, c, g, c0g in (('1', a, e['c1'], e['g1'], 0.0), ('2', b, e['c2'], e['g2'], e['c2_c0g'])):
            cj = (c - c0g) * kc + c0g
            if cj > 0:
                lines.append(f'Cgp{tag}{k} {nd} 0 {cj:.6g}')
            if g > 0:
                lines.append(f'Rgpg{tag}{k} {nd} 0 {1 / (g * kg):.6g}')
    if ss['sum']:
        lines += [f"Cgpsum sum 0 {ss['sum']['c'] * kc:.6g}", f"Rgpgsum sum 0 {1 / (ss['sum']['g'] * kg):.6g}"]
    return '\n'.join(lines) + '\n'


def write_rust(name):
    cfg = ps.CANDIDATES[name]
    path = HERE.parent / 'stability-full-chain' / 'revg_network.rs'
    text = (f'// Generated by validation/rev-g-protection/normal_operation.py --rust {name}; do not edit.\n'
            f'// Rev G jack protection, powered (switch closed), linearized at 0 V:\n'
            f'// jacks jhc/jhp/jlp/jlc -> board hi/hpot/lpot/low (+ the summing node sum).\n'
            f'// HIGH: junction C x 2, leakage x 10, switch on-resistance x 2 (rust_network()).\n'
            f'// rcp_jack / ref_jack: R105 / R106 and the K4 + R107 reference on the jack nodes.\n'
            f'const REVG_JACKSIDE: bool = {str(bool(cfg.get("rcp_jack")) and bool(cfg.get("ref_jack"))).lower()};\n'
            f'const REVG_CANDIDATE: &str = "{name}";\n'
            f'const REVG_PROT_NOM: &str = r"{rust_network(cfg, "nom")}";\n'
            f'const REVG_PROT_HIGH: &str = r"{rust_network(cfg, "high")}";\n')
    path.write_text(text)
    print('wrote', path)


# ------------------------------------------------------------------ report
NAMES = ['iso_two_stage', 'iso_two_stage_sum', 'iso_tvs2_lo', 'parts', 'parts_ron_max', 'parts_rcp_jack', 'parts_jackside']
GRID = ['parts', 'parts_jackside']
MODES = {'linear': (False, False), 'drift': (True, False), 'level': (True, True)}


def selfcheck(base):
    """Zero-ohm links (1 mOhm floor, no shunts) must reproduce the committed map: same verdicts, and every cell
    within 1e-3 of its own value (the worst cells, 10 MOhm at 85 kHz, are already 100x off and ill-conditioned)."""
    new = map_with(ps.CANDIDATES['links'], True, True)
    b = {(c['z'], c['f'], c['range']): c for c in base['cells']}
    rel = max(abs(c[q] - b[(c['z'], c['f'], c['range'])][q]) / max(b[(c['z'], c['f'], c['range'])][q], 1e-3)
              for c in new['cells'] for q in ('z_typ', 'th_typ', 'z_corner', 'th_corner'))
    same = compare(base, new)['counts']['gw_1m_new'] == compare(base, base)['counts']['gw_1m_new']
    assert rel < 1e-3 and same, (rel, same)
    return dict(links_max_relative_change=rel, links_same_verdicts=same)


def run(names):
    base = json.loads((am.RES / 'map.json').read_text())
    out = {'tc': dict(tvs_c=TC_TVS_C, c0g=TC_C0G, ron=TC_RON, r=TC_R, leak_doubling_degC=LEAK_DOUBLING),
           'gbw_hz': GBW, 'selfcheck': selfcheck(base), 'candidates': {}}
    for n in names:
        cfg = ps.CANDIDATES[n]
        ss = small_signal(cfg)
        x = {'small_signal': {k: ({q: v for q, v in e.items() if q in ('c1', 'g1', 'r', 'c2', 'g2', 'c2_c0g', 'c2_tvs')}
                                  if k != 'sum' else e) for k, e in ss.items()},
             'signal': signal(ss), 'noise': noise(ss), 'sum_node': sum_node(ss), 'map': {}}
        for mode, (dr, lv) in MODES.items():
            x['map'][mode] = compare(base, map_with(cfg, dr, lv))
            print(f'{n} {mode}: LCR-6100 1 m {x["map"][mode]["counts"]["gw_1m_new"]} '
                  f'(base {x["map"][mode]["counts"]["gw_1m_base"]})', file=sys.stderr)
        out['candidates'][n] = x
    (HERE / 'normal-operation.json').write_text(json.dumps(out, indent=1, default=str) + '\n')
    return out


def pct(x):
    return am.pct(max(x, 0.0)) if x > 5e-6 else '0'


def render(out):
    t = {}
    lines = ['| Candidate | Mode | LCR-6100 (1 m) ✓ / ~ / ✗ (without the network: '
             f"{'{b}'}) | Worst added error, corner, usable cells | Where |", '|---|---|---|---|']
    base = None
    for n, x in out['candidates'].items():
        for mode, m in x['map'].items():
            c, base = m['counts']['gw_1m_new'], m['counts']['gw_1m_base']
            k, w = max(((k, w) for k, w in m['worst'].items() if k.endswith('corner')), key=lambda kw: kw[1]['delta'])
            r, f, _ = k.split('|')
            lines.append(f"| `{n}` | {mode} | {c['✓']} / {c['~']} / {c['✗']} | {pct(w['delta'])} % "
                         f"(×{1 + w['relative']:.2f} of the cell) | {am.rng_label(int(r))} range, "
                         f"{am.flabel(float(f))} Hz, {am.zlabel(w['z'])}, "
                         f"{'phase' if w['quantity'].startswith('th') else '|Z|'} |")
    lines[0] = lines[0].replace('{b}', f"{base['✓']} / {base['~']} / {base['✗']}")
    t['normal_map'] = '\n'.join(lines)
    lines = []
    for n in GRID:
        m = out['candidates'][n]['map']['level']['worst']
        cell = lambda r, f: pct(m[f"{r}|{f:g}|corner"]["delta"]) if f"{r}|{f:g}|corner" in m else '—'
        lines += [f'`{n}`, level mode: worst added corner error over the usable cells (max of |Z| and phase), %; '
                  '— = no usable cell', '',
                  '| Range | ' + ' | '.join(am.flabel(f) for f in FREQS) + ' |', '|---' * (len(FREQS) + 1) + '|']
        for r in am.RANGES:
            lines.append(f'| {am.rng_label(r)} | ' + ' | '.join(cell(r, f) for f in FREQS) + ' |')
        lines.append('')
    t['normal_grid'] = '\n'.join(lines).rstrip()
    lines = ['| Candidate | Short-circuit current, 100 Ω / 5 kΩ / 100 kΩ range (mA, without → with) | SNR loss, '
             '100 Ω range | Added noise vs the codec floor: POT series R / LCUR series R (worst range) | '
             'Summing-node clamp drift, worst (corner) |',
             '|---|---|---|---|---|']
    for n, x in out['candidates'].items():
        sg = x['signal']
        cur = ' / '.join(f"{sg[str(r)]['i_short_ma'][0]:.3g} → {sg[str(r)]['i_short_ma'][1]:.3g}" for r in am.RANGES)
        sm = x['sum_node']
        if sm:
            k, w = max(sm.items(), key=lambda kw: kw[1]['drift'])
            r, f = k.split('|')
            sn = f"{pct(w['drift'])} % ({am.rng_label(int(r))} range, {am.flabel(float(f))} Hz)"
        else:
            sn = 'no summing-node clamp'
        lines.append(f"| `{n}` | {cur} | {sg['100']['snr_loss_db']:.2f} dB | "
                     f"{x['noise']['pot_vs_floor'] * 100:.2g} % / {x['noise']['lcur_vs_floor'] * 100:.2g} % | {sn} |")
    t['normal_signal'] = '\n'.join(lines)
    return t


def check_readme(write=False):
    tables = render(json.loads((HERE / 'normal-operation.json').read_text()))
    path = HERE / 'README.md'
    text = path.read_text()
    for k, v in tables.items():
        pat = rf'(<!-- generated:{k} -->\n)(?:(?!<!-- ).)*?\n?(<!-- /generated -->)'
        if write:
            text = re.sub(pat, lambda m: m.group(1) + v + '\n' + m.group(2), text, flags=re.S)
    if write:
        path.write_text(text)
    have = dict(re.findall(r'<!-- generated:(\w+) -->\n((?:(?!<!-- ).)*?)\n?<!-- /generated -->', text, re.S))
    bad = [k for k in tables if have.get(k) != tables[k]]
    print('README tables:', 'match normal-operation.json' if not bad else f'MISMATCH in {bad}')
    return not bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--only', nargs='*')
    ap.add_argument('--rust')
    ap.add_argument('--check-readme', action='store_true')
    ap.add_argument('--write-readme', action='store_true')
    a = ap.parse_args()
    if a.rust:
        write_rust(a.rust)
        return
    if a.check_readme or a.write_readme:
        sys.exit(0 if check_readme(a.write_readme) else 1)
    run(a.only or NAMES)


if __name__ == '__main__':
    main()
