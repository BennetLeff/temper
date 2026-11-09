"""Rev G jack protection, phase 1: surge screen of candidate networks (parametric clamps, no part numbers yet).

python3 validation/rev-g-protection/protection_screen.py [--jobs N] [--only NAME ...]  ->  protection-screen.json
python3 validation/rev-g-protection/protection_screen.py --esd [--only NAME ...]   IEC 61000-4-2 contact discharge
python3 validation/rev-g-protection/protection_screen.py --check-readme   README tables == the JSON

Each candidate is a network between the four BNC jacks (jk_hcur, jk_hpot, jk_lpot, jk_lcur) and the Rev F board
nodes (dut_hi, hpot, lpot, dut_lo), dropped into the charged-DUT model (../charged-dut/charged_dut_spice.py,
deck(prot=...)) and judged by its judge(): every OPA2810, LDO, TAC5112, BAT54S and passive rating of Rev F.
The network's own parts are reported (peak current, energy), not judged: phase 2 picks parts with datasheet
ratings to cover them.

Target (charged-dut README, "Rev G requirements"): class A, powered and unpowered, for 1 uF at 30 V on every
connection pattern; the stretch is the E4980A's 1 J.

ESD (--esd): the charged-DUT deck's IEC 61000-4-2 gun (charged_dut_spice.GUN, checked against the standard's
waveform table by gun_check()) in contact discharge on each centre pin, no leads plugged in, every meter state,
both polarities, 2 to 30 kV. Judged the same way. IEC 61326-1 (laboratory equipment) asks 4 kV contact.

Clamp model (parametric): a bidirectional TVS as two back-to-back diodes, breakdown BV, dynamic resistance RD,
junction capacitance CJ (each diode 2 x CJ, so the pair is CJ). Values are stated per candidate, not taken from
a datasheet; phase 2 replaces them with real parts.
"""

import argparse
import concurrent.futures as cf
import json
import os
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'charged-dut'))
import charged_dut_spice as cd  # noqa: E402

JACKS = {'hcur': 'dut_hi', 'hpot': 'hpot', 'lpot': 'lpot', 'lcur': 'dut_lo'}
SCREEN_V = [0.5, 1, 2, 3, 5, 7, 10, 13, 16, 20, 30, 50, 100, 200, 400, 1000]
SCREEN_C = [1e-6]
STATES = cd.STATES


def network(cfg, power):
    """cfg keys (all optional):
      tvs  {jack: (bv, rd, cj)}  bidirectional TVS to GND at the jack
      iso  True | {ron, coff, roff}  a normally-open isolation switch after the jack clamp: open (coff || roff)
                                 when the meter is unpowered, closed (ron) when powered; True = ISO_PARAM
      sch2 {jack: True | dict}   (below) True = the parametric Schottky DSCH, a dict = a diode model (IS, N, RS,
                                 CJO, BV, IBV) for a part
      r    {jack: ohms}          series resistor after the relay
      tvs2 {jack: (bv, rd, cj)}  second-stage TVS to GND after the series resistor
      sch2 {jack: True}          second-stage antiparallel Schottky pair to GND after the series resistor
      cap2 {jack: farads}        second-stage capacitor (C0G) to GND after the series resistor
      rcp_jack True              R105 / R106 (CUR-POT 1k) between the jacks instead of the board nodes: the board
                                 POT node then never sees the current path's series drop through the 1k
      sense {jack: ohms}         the residual-voltage sense divider's top resistor from the jack (drive_budget.py),
                                 to ground here (its far end is a 10 ms-filtered pin near 1.65 V)
      ref_jack True              the K4 + R107 reference branch across the CUR jacks (phasor model and the stability
                                 matrix; the surge deck has no K4)
      esd_is A                   the OPA2810 ESD-cell saturation current (charged_dut_spice.ESD_IS by default)
      ref_bypass True            the phasor model's reference check with K4's free pole shorting HCUR to HPOT on the
                                 jack side (normal_operation.py; the surge deck has no K4)
      sch_sum True               antiparallel Schottky pair from the TIA summing node (tia_sum, behind R94 22 ohm)
                                 to GND, instead of at DUT_LO: DUT_LO carries I x 22 ohm in use, tia_sum ~0 V
    jack -> TVS -> relay -> R -> second stage -> board node."""
    lines, vecs, parts = [SCH_MODEL], [], []
    models = {}
    iso = ISO_PARAM if cfg.get('iso') is True else cfg.get('iso')
    for stage in ('tvs', 'tvs2'):
        for j, (bv, rd, cj) in cfg.get(stage, {}).items():
            models[(bv, rd, cj)] = f'DT{len(models)}' if (bv, rd, cj) not in models else models[(bv, rd, cj)]
    for (bv, rd, cj), name in models.items():
        lines.append(f'.model {name} D(IS=1e-12 N=1 RS={rd:g} BV={bv:g} IBV=1m CJO={2 * cj:g})')
    for j, node in JACKS.items():
        a = f'jk_{j}'
        vecs.append(f'v({a})')
        if j in cfg.get('sense', {}):
            lines.append(f"Rsense_{j} {a} 0 {cfg['sense'][j]:g}")
        if j in cfg.get('tvs', {}):
            m = models[cfg['tvs'][j]]
            lines += [f'Vam_t1_{j} {a} t1_{j} 0', f'Dt1a_{j} t1_{j} t1m_{j} {m}', f'Dt1b_{j} 0 t1m_{j} {m}']
            vecs.append(f'i(Vam_t1_{j})')
            parts.append(('tvs1', j))
        if iso:
            lines += ([f"Riso_{j} {a} rl_{j} {iso['ron']:g}"] if power == 'powered' else
                      [f"Ciso_{j} {a} rl_{j} {iso['coff']:g}", f"Riso_{j} {a} rl_{j} {iso['roff']:g}"])
            a = f'rl_{j}'
        r = cfg.get('r', {}).get(j, 0.0)
        second = any(j in cfg.get(k, {}) for k in ('tvs2', 'sch2', 'cap2'))
        b = f'mid_{j}' if second else node
        lines.append(f'Rs_{j} {a} {b} {max(r, 1e-3):g}')
        vecs += [f'v({a})', f'v({b})'] if b != node else [f'v({a})']
        if second and j not in cfg.get('tvs2', {}):
            lines.append(f'Rl_{j} {b} {node} 1e-3')
        if j in cfg.get('sch2', {}):
            m = cfg['sch2'][j]
            if m is not True:
                lines.append(f'.model DS2_{j} D(' + ' '.join(f'{q}={v:g}' for q, v in m.items()) + ')')
            m = 'DSCH' if m is True else f'DS2_{j}'
            lines += [f'Vam_s2_{j} {b} s2_{j} 0', f'Ds2a_{j} s2_{j} 0 {m}', f'Ds2b_{j} 0 s2_{j} {m}']
            vecs.append(f'i(Vam_s2_{j})')
            parts.append(('sch2', j))
        if j in cfg.get('cap2', {}):
            lines.append(f'Cs2_{j} {b} 0 {cfg["cap2"][j]:g}')
        if j in cfg.get('tvs2', {}):
            m = models[cfg['tvs2'][j]]
            lines += [f'Vam_t2_{j} {b} t2_{j} 0', f'Dt2a_{j} t2_{j} t2m_{j} {m}', f'Dt2b_{j} 0 t2m_{j} {m}',
                      f'Rl_{j} {b} {node} 1e-3']
            vecs.append(f'i(Vam_t2_{j})')
            parts.append(('tvs2', j))
    if cfg.get('sch_sum'):
        lines += ['Vam_s2_sum tia_sum s2_sum 0', 'Ds2a_sum s2_sum 0 DSCH', 'Ds2b_sum 0 s2_sum DSCH']
        vecs.append('i(Vam_s2_sum)')
        parts.append(('sch2', 'sum'))
    return {'lines': lines, 'vecs': vecs, 'parts': parts, 'rcp_jack': bool(cfg.get('rcp_jack'))}


# Parametric clamp sets. TVS5: a 5 V-standoff 400 W-class bidirectional TVS (BV 6.4 V, RD 0.06 ohm, 2 nF).
TVS5 = (6.4, 0.06, 2e-9)
TVS3 = (4.0, 0.1, 0.5e-9)   # a 3.3 V-standoff low-capacitance second stage: passes the 1.7 V source with margin
# A 1-3 A-class Schottky (parametric): 0.31 V at 10 mA, 0.5 V at 1 A.
SCH_MODEL = '.model DSCH D(IS=1e-6 N=1.3 RS=0.03 CJO=200p)'
ISO_PARAM = dict(ron=0.1, coff=1e-12, roff=1e12)    # parametric switch (phase 1)

# Parts (part-selection/parts.json, datasheet fits, ngspice DC): TVS tuples as above, the pair C typical.
H4V5HD3B = (5.433, 0.0436, 100e-12)    # HJC, C20615803, SOD-323, 40 A 8/20; jack
H3V3LD5B = (4.397, 0.4092, 12.5e-12)   # HJC, C20615817, SOD-523, 8 A 8/20; second stage (25 pF max)
BAV99 = dict(IS=7.802e-10, N=1.964, RS=1.857, CJO=1.5e-12, BV=100, IBV=1e-7)   # Nexperia, C2500 (basic)
TLP172AM = dict(ron=1.0, coff=20e-12, roff=60e9)   # Toshiba photoMOS, C2152276: RON 1 typ / 2 max, COFF 20 pF
CANDIDATES = {
    'links': {'note': 'zero-ohm links only: must reproduce the Rev F baseline (harness check)'},
    'tvs_all': {'tvs': {j: TVS5 for j in JACKS},
                'note': 'TVS5 at all four jacks, no series R'},
    'tvs_all_r1k_pot': {'tvs': {j: TVS5 for j in JACKS}, 'r': {'hpot': 1e3, 'lpot': 1e3},
                        'note': 'TVS5 at all four jacks; 1 k at HPOT and LPOT (option A behind the clamp)'},
    'iso_tvs': {'tvs': {j: TVS5 for j in JACKS}, 'iso': True,
                'note': 'TVS5 at all four jacks and a normally-open isolation relay (open when unpowered)'},
    'two_stage': {'tvs': {j: TVS5 for j in JACKS}, 'r': {'hcur': 10.0, 'lcur': 10.0, 'hpot': 100.0, 'lpot': 100.0},
                  'tvs2': {'hcur': TVS3, 'hpot': TVS3, 'lpot': TVS3}, 'sch2': {'lcur': True},
                  'cap2': {'hpot': 1e-9, 'lpot': 1e-9},
                  'note': 'TVS5 at the jacks; 10 ohm on HCUR/LCUR, 100 ohm + 1 nF C0G on HPOT/LPOT; second stage '
                          'TVS3 on HCUR/HPOT/LPOT and a Schottky pair at DUT_LO (a virtual ground)'},
    'iso_two_stage': {'tvs': {j: TVS5 for j in JACKS}, 'iso': True,
                      'r': {'hcur': 10.0, 'lcur': 10.0, 'hpot': 100.0, 'lpot': 100.0},
                      'tvs2': {'hcur': TVS3, 'hpot': TVS3, 'lpot': TVS3}, 'sch2': {'lcur': True},
                      'cap2': {'hpot': 1e-9, 'lpot': 1e-9}, 'note': 'two_stage plus the isolation relay'},
    'iso_two_stage_sum': {'tvs': {j: TVS5 for j in JACKS}, 'iso': True,
                          'r': {'hcur': 10.0, 'lcur': 10.0, 'hpot': 100.0, 'lpot': 100.0},
                          'tvs2': {'hcur': TVS3, 'hpot': TVS3, 'lpot': TVS3}, 'sch_sum': True,
                          'cap2': {'hpot': 1e-9, 'lpot': 1e-9},
                          'note': 'iso_two_stage with the Schottky pair at the TIA summing node, behind R94, '
                                  'not at DUT_LO (which sits at I x 22 ohm in use: the pair would conduct)'},
    'parts': {'tvs': {j: H4V5HD3B for j in JACKS}, 'iso': TLP172AM,
              'r': {'hcur': 10.0, 'lcur': 10.0, 'hpot': 100.0, 'lpot': 100.0},
              'tvs2': {'hcur': H3V3LD5B, 'hpot': H3V3LD5B, 'lpot': H3V3LD5B}, 'sch2': {'lcur': BAV99},
              'cap2': {'hpot': 1e-9, 'lpot': 1e-9},
              'note': 'iso_two_stage with the chosen parts (part-selection/PARTS.md): H4V5HD3B at the jacks, '
                      'TLP172AM switches, CRCW-HP 10 / 100 ohm, H3V3LD5B + 1 nF C0G second stage, a BAV99 pair '
                      'at DUT_LO (silicon: no conduction at the I x 22 ohm DUT_LO carries in use)'},
    'parts_ron_max': {'tvs': {j: H4V5HD3B for j in JACKS}, 'iso': dict(TLP172AM, ron=2.0),
                      'r': {'hcur': 10.0, 'lcur': 10.0, 'hpot': 100.0, 'lpot': 100.0},
                      'tvs2': {'hcur': H3V3LD5B, 'hpot': H3V3LD5B, 'lpot': H3V3LD5B}, 'sch2': {'lcur': BAV99},
                      'cap2': {'hpot': 1e-9, 'lpot': 1e-9}, 'note': '`parts` with the switch at RON max (2 ohm)'},
    'parts_rcp_jack': {'tvs': {j: H4V5HD3B for j in JACKS}, 'iso': TLP172AM,
                       'r': {'hcur': 10.0, 'lcur': 10.0, 'hpot': 100.0, 'lpot': 100.0},
                       'tvs2': {'hcur': H3V3LD5B, 'hpot': H3V3LD5B, 'lpot': H3V3LD5B}, 'sch2': {'lcur': BAV99},
                       'cap2': {'hpot': 1e-9, 'lpot': 1e-9}, 'rcp_jack': True,
                       'note': '`parts` with R105 / R106 moved to the jack side of the network'},
    'parts_jackside': {'tvs': {j: H4V5HD3B for j in JACKS}, 'iso': TLP172AM,
                       'r': {'hcur': 10.0, 'lcur': 10.0, 'hpot': 100.0, 'lpot': 100.0},
                       'tvs2': {'hcur': H3V3LD5B, 'hpot': H3V3LD5B, 'lpot': H3V3LD5B}, 'sch2': {'lcur': BAV99},
                       'cap2': {'hpot': 1e-9, 'lpot': 1e-9}, 'rcp_jack': True, 'ref_jack': True,
                       'sense': {'hcur': 1e6, 'lcur': 1e6}, 'ref_bypass': True,
                       'note': '`parts` with R105 / R106 and the K4 + R107 reference on the jack side: the reference '
                               'current then takes the LCUR switch and 10 ohm, and the session check tracks them '
                               '(the surge deck has no K4; open, it is ~1 pF across the jacks); K4\'s free pole shorts '
                               'the HCUR and HPOT jacks during the check, so the HPOT side\'s capacitance drops out of '
                               'it (no part added); plus the 1 MOhm residual-voltage sense on HCUR and LCUR'},
    'iso_tvs2_lo': {'tvs': {j: TVS5 for j in JACKS}, 'iso': True,
                    'r': {'hcur': 10.0, 'lcur': 10.0, 'hpot': 100.0, 'lpot': 100.0},
                    'tvs2': {j: TVS3 for j in JACKS}, 'cap2': {'hpot': 1e-9, 'lpot': 1e-9},
                    'note': 'iso_two_stage with a TVS3 at DUT_LO instead of the Schottky pair: no clamp that '
                            'conducts at the I x 22 ohm DUT_LO carries in use'},
}


def variant(base, note, **change):
    cfg = {k: v for k, v in CANDIDATES[base].items() if k != 'note'}
    cfg.update(change)
    return dict(cfg, note=note)


# Sensitivity to what Rev F bring-up was to measure, and the two HPOT reference-check options (README "Open items").
# The datasheets give COFF and CJ at 0 V only, which is their largest value (both fall with reverse bias); x2 covers
# the part spread with no max given. ESD_IS_ALT is the charged-DUT study's stronger (lower-knee) ESD cell.
_JS = CANDIDATES['parts_jackside']
CANDIDATES.update({
    'jackside_coff2x': variant('parts_jackside', '`parts_jackside` with the switch COFF at 40 pF (2 x typical)',
                               iso=dict(TLP172AM, coff=40e-12)),
    'jackside_tvs_c2x': variant('parts_jackside', '`parts_jackside` with both TVS junction capacitances x2',
                                tvs={j: (bv, rd, 2 * cj) for j, (bv, rd, cj) in _JS['tvs'].items()},
                                tvs2={j: (bv, rd, 2 * cj) for j, (bv, rd, cj) in _JS['tvs2'].items()}),
    'jackside_esd_alt': variant('parts_jackside', '`parts_jackside` with the stronger ESD cell (IS 1e-12)',
                                esd_is=cd.ESD_IS_ALT),
    'jackside_ron_max': variant('parts_jackside', '`parts_jackside` with the switch at RON max (2 ohm)',
                                iso=dict(TLP172AM, ron=2.0)),
    'jackside_pot470p': variant('parts_jackside', '`parts_jackside` with 470 pF instead of 1 nF on HPOT / LPOT',
                                cap2={'hpot': 470e-12, 'lpot': 470e-12}),
    'jackside_no_bypass': variant('parts_jackside', '`parts_jackside` without the K4 bypass: the reference check '
                                  'reaches HPOT through R105 only', ref_bypass=False),
})
ACCURACY_ONLY = ['jackside_ron_max', 'jackside_no_bypass']   # the surge deck does not see these
SENSITIVITY = ['jackside_coff2x', 'jackside_tvs_c2x', 'jackside_esd_alt', 'jackside_pot470p']
GUN_KV = [2, 4, 6, 8, 12, 15, 20, 30]
ESD_NAMES = ['links', 'parts_jackside', 'jackside_coff2x', 'jackside_esd_alt']
ESD_TARGET_KV = 8   # IEC 61326-1 asks 4 kV contact; 8 kV is the standard's top contact level

# The chosen network (README "Decision") and what each of its parts is rated for, at the pulse lengths
# the screen produces (~1-3 us): TVS at 8/20 us, the BAV99 at 1 us, the resistors' single-pulse curves at 1 us.
CHOSEN = 'parts_jackside'
RATINGS = {'tvs1': ('H4V5HD3B IPP 40 A (8/20 µs)', 40.0), 'tvs2': ('H3V3LD5B IPP 8 A (8/20 µs)', 8.0),
           'sch2': ('BAV99 IFSM 4 A (1 µs)', 4.0), 'iso': ('TLP172AM VOFF 60 V', 60.0)}   # resistors: in render()
ESD_RATINGS = {'tvs1': ('H4V5HD3B ±30 kV contact', 30.0), 'tvs2': ('H3V3LD5B ±20 kV contact', 20.0)}


def run(case):
    """scn 'gun_<jack>' is an IEC 61000-4-2 contact discharge of v kV on that jack (c unused)."""
    scn, power, rng, c, v, name = case
    cfg = CANDIDATES[name]
    prot = network(cfg, power)
    gun = (scn[4:], v) if scn.startswith('gun_') else None
    text, t_end = cd.deck(scn, power, rng, c, v, 0.0, cfg.get('esd_is', cd.ESD_IS), prot, gun=gun)
    col, opt = cd.spice(text, t_end)
    if col is None:
        return {'case': case, 'error': opt}
    r = {'case': case, 'options': opt,
         **cd.metrics(col, col['time'], rng, 0.0, cd.RCP_JACK if prot['rcp_jack'] else cd.RCP_BOARD)}
    t = col['time']
    r['prot'] = {}
    for stage, j in prot['parts']:
        i = col[f'i(vam_{ {"tvs1": "t1", "tvs2": "t2", "sch2": "s2"}[stage] }_{j})']
        # each clamp's energy is its current times its own node voltage (jack, second-stage node or tia_sum)
        vj = col['v(tia_sum)' if j == 'sum' else f'v(jk_{j})' if stage == 'tvs1' else f'v(mid_{j})']
        r['prot'][f'{stage}_{j}'] = {'i_pk_a': max(map(abs, i)), 'i2t': cd.i2t(t, i),
                                     'e_j': cd.integ(t, [a * b for a, b in zip(i, vj)])}
    for j in JACKS:
        rr = CANDIDATES[name].get('r', {}).get(j)
        if rr:
            cfg = CANDIDATES[name]
            a = f'rl_{j}' if cfg.get('iso') else f'jk_{j}'
            b = f'mid_{j}' if any(j in cfg.get(k, {}) for k in ('tvs2', 'sch2', 'cap2')) else JACKS[j]
            dv = [x - y for x, y in zip(col[f'v({a})'], col[f'v({b})'])]
            p = [d * d / rr for d in dv]
            r['prot'][f'r_{j}'] = {'v_pk': max(map(abs, dv)), 'p_pk_w': max(p), 'e_j': cd.integ(t, p)}
        if CANDIDATES[name].get('iso') and power == 'unpowered':
            r['prot'][f'iso_{j}'] = {'v_pk': max(abs(x - y) for x, y in zip(col[f'v(jk_{j})'], col[f'v(rl_{j})']))}
    return r


def thresholds(res, name):
    out = {}
    for s in cd.SCENARIOS:
        for p, rg in STATES:
            for c in SCREEN_C:
                row = {}
                for want, key in (({'A'}, 'v_within_ratings'), ({'A', 'B'}, 'v_hbm_scale')):
                    ok, first = 0.0, None
                    for v in SCREEN_V:
                        bad = []
                        for sgn in (1, -1):
                            r = res[(s, p, rg, c, sgn * v, name)]
                            if 'error' in r:
                                bad.append('simulation error')
                            else:
                                cls, lims, _, _ = cd.judge(r)
                                if cls not in want:
                                    bad += lims
                        if bad:
                            first = {'v': v, 'limits': sorted(set(bad))[:4]}
                            break
                        ok = v
                    row[key], row[key + '_ends_at'] = ok, first
                out[f'{s} {p}/{rg} {c:g}'] = row
    return out


def render(out):
    """README tables from protection-screen.json."""
    lines = ['| Candidate | Lowest class-A voltage, 1 µF, any pattern and state | Powered | Unpowered | 30 V target | '
             'What ends it |', '|---|---|---|---|---|---|']
    for n, x in out['candidates'].items():
        th = x['thresholds']
        pw = min(v['v_within_ratings'] for k, v in th.items() if ' powered/' in k)
        up = min(v['v_within_ratings'] for k, v in th.items() if ' unpowered/' in k)
        k_min = min(th, key=lambda k: th[k]['v_within_ratings'])
        end = th[k_min]['v_within_ratings_ends_at']
        why = f"{k_min.rsplit(' ', 1)[0]}: {'; '.join(end['limits'][:2])}" if end else 'nothing up to 1000 V'
        lines.append(f"| `{n}` | {x['min_v_within_ratings']:g} V | {pw:g} V | {up:g} V | "
                     f"{'met' if x['target_met_1uF_30V'] else 'no'} | {why} |")
    tables = {'screen': '\n'.join(lines)}
    lines = ['| Part | At 1 µF, 30 V (the target) | Worst case in the screen (up to 1000 V) |', '|---|---|---|']
    for part, w in out['candidates']['iso_two_stage']['part_stress_worst'].items():
        a = w['at_30v_1uF']
        if part.startswith('r_'):
            t = f"{a['v_pk']:.3g} V, {a['p_pk_w']:.3g} W peak, {a['e_j'] * 1e6:.3g} µJ"
            u = f"{w['v_pk']:.3g} V, {w['p_pk_w']:.3g} W peak, {w['e_j'] * 1e3:.3g} mJ"
        else:
            t = f"{a['i_pk_a']:.3g} A peak, {a['e_j'] * 1e6:.3g} µJ"
            u = f"{w['i_pk_a']:.3g} A peak, {w['e_j'] * 1e3:.3g} mJ"
        lines.append(f'| `{part}` | {t} | {u} |')
    tables['stress'] = '\n'.join(lines)
    lines = ['| Part | At 1 µF, 30 V | Rating (part-selection/PARTS.md) | Margin |', '|---|---|---|---|']
    for part, w in out['candidates'][CHOSEN]['part_stress_worst'].items():
        a = w['at_30v_1uF']
        if part.startswith('r_'):   # by package: 10 ohm 0805 on CUR, 100 ohm 0603 on POT
            what, limit = (('CRCW0805-HP ~450 W at 1 µs', 450.0) if part in ('r_hcur', 'r_lcur') else
                           ('CRCW0603-HP ~250 W at 1 µs', 250.0))
        else:
            what, limit = RATINGS[part.split('_')[0]]
        value = a['p_pk_w'] if part.startswith('r_') else a['v_pk'] if part.startswith('iso_') else a['i_pk_a']
        unit = 'W peak' if part.startswith('r_') else 'V off-state' if part.startswith('iso_') else 'A peak'
        m = limit / value
        lines.append(f"| `{part}` | {value:.3g} {unit} | {what} | ×{m:.2g} |" if m < 10 else
                     f"| `{part}` | {value:.3g} {unit} | {what} | ×{m:.0f} |")
    a = out['candidates'][CHOSEN]['part_stress_worst']['r_lcur']['at_30v_1uF']
    lines.append(f"| LCUR switch (TLP172AM, in series with `r_lcur`) | {a['v_pk'] / 10.0:.3g} A peak | "
                 f"IONP 1.5 A (100 ms) | ×{1.5 / (a['v_pk'] / 10.0):.1f} |")
    tables['stress_parts'] = '\n'.join(lines)
    if 'esd' in out:
        tables.update(render_esd(out['esd']))
    return tables


def esd_thresholds(res, name):
    """Per jack and power state: the highest kV (both polarities, every range) that is class A, and class A or B."""
    out = {}
    for j in JACKS:
        for power in ('powered', 'unpowered'):
            row = {}
            for want, key in (({'A'}, 'kv_class_a'), ({'A', 'B'}, 'kv_hbm_scale')):
                ok, first = 0, None
                for kv in GUN_KV:
                    bad = []
                    for (p, rg) in STATES:
                        if p != power:
                            continue
                        for sgn in (1, -1):
                            r = res[(f'gun_{j}', p, rg, 0.0, sgn * kv, name)]
                            if 'error' in r:
                                bad.append('simulation error')
                            else:
                                cls, lims, _, _ = cd.judge(r)
                                if cls not in want:
                                    bad += lims
                    if bad:
                        first = {'kv': kv, 'limits': sorted(set(bad))[:4]}
                        break
                    ok = kv
                row[key], row[key + '_ends_at'] = ok, first
            out[f'{j} {power}'] = row
    return out


def esd_main(names, jobs):
    cases = [(f'gun_{j}', p, rg, 0.0, sgn * kv, n) for n in names for j in JACKS for p, rg in STATES
             for kv in GUN_KV for sgn in (1, -1)]
    with cf.ThreadPoolExecutor(jobs) as ex:
        res = dict(zip(cases, ex.map(run, cases)))
    path = HERE / 'protection-screen.json'
    out = json.loads(path.read_text())
    esd = out.setdefault('esd', {'candidates': {}})
    esd['gun_check'] = cd.gun_check()
    esd['gun'] = cd.GUN
    for n in names:
        th = esd_thresholds(res, n)
        stress = {}
        for k, r in res.items():
            if k[-1] != n or 'error' in r:
                continue
            for part, x in r['prot'].items():
                for at in ('target', 'max'):
                    if at == 'target' and abs(k[4]) != ESD_TARGET_KV:
                        continue
                    w = stress.setdefault(part, {}).setdefault(at, {})
                    for q in ('i_pk_a', 'p_pk_w', 'v_pk'):
                        if q in x:
                            w[q] = max(w.get(q, 0.0), x[q])
        esd['candidates'][n] = {'thresholds': th, 'kv_class_a': min(x['kv_class_a'] for x in th.values()),
                                'kv_hbm_scale': min(x['kv_hbm_scale'] for x in th.values()), 'part_stress': stress,
                                'errors': [list(k) for k, r in res.items() if k[-1] == n and 'error' in r]}
        c = esd['candidates'][n]
        print(f"{n:22} ESD class A to {c['kv_class_a']} kV, A or B to {c['kv_hbm_scale']} kV, errors {len(c['errors'])}")
    path.write_text(json.dumps(out, indent=1, default=str) + '\n')


def render_esd(esd):
    g = esd['gun_check']
    lines = [f"Gun into the standard's 2 Ω target, per kV: first peak {g['peak_a_per_kv']['value']:.2f} A "
             f"(3.75 ± 15 %), rise {g['rise_ns']['value']:.2f} ns (0.8 ± 25 %), {g['i30_a_per_kv']['value']:.2f} A at "
             f"30 ns (2 ± 30 %), {g['i60_a_per_kv']['value']:.2f} A at 60 ns (1 ± 30 %): "
             f"{'all inside' if all(x['ok'] for x in g.values()) else 'OUTSIDE'} the IEC 61000-4-2 table.", '',
             '| Candidate | Class A, powered | Class A, unpowered | A or B (nothing past the HBM pulse), any state | '
             'Where class A ends first |', '|---|---|---|---|---|']
    kv = lambda v: (f'{v} kV' + (' (the sweep top)' if v == GUN_KV[-1] else '')) if v else f'below {GUN_KV[0]} kV'
    for n, c in esd['candidates'].items():
        th = c['thresholds']
        a = {pw: min(v['kv_class_a'] for k, v in th.items() if k.endswith(' ' + pw)) for pw in ('powered', 'unpowered')}
        k = min(th, key=lambda q: th[q]['kv_class_a'])
        end = th[k]['kv_class_a_ends_at']
        why = f"{k} at {end['kv']} kV: {'; '.join(end['limits'][:2])}" if end else f'nothing up to {GUN_KV[-1]} kV'
        lines.append(f"| `{n}` | {kv(a['powered'])} | {kv(a['unpowered'])} | {kv(c['kv_hbm_scale'])} | {why} |")
    t = {'esd': '\n'.join(lines)}
    if CHOSEN in esd['candidates']:
        lines = [f'| Part | At {ESD_TARGET_KV} kV | At {GUN_KV[-1]} kV | Rating |', '|---|---|---|---|']
        for part, w in esd['candidates'][CHOSEN]['part_stress'].items():
            kind = part.split('_')[0]
            if kind == 'r':
                q, unit = 'p_pk_w', 'W peak'
                rating = (('CRCW0805-HP ~450 W at 1 µs' if part in ('r_hcur', 'r_lcur') else 'CRCW0603-HP ~250 W at 1 µs')
                          + '; a ns pulse is allowed more')
            elif kind == 'iso':
                q, unit, rating = 'v_pk', 'V off-state', RATINGS['iso'][0]
            else:
                q, unit = 'i_pk_a', 'A peak'
                rating = ESD_RATINGS[kind][0] if kind in ESD_RATINGS else RATINGS[kind][0]
            lines.append(f"| `{part}` | {w['target'][q]:.3g} {unit} | {w['max'][q]:.3g} {unit} | {rating} |")
        t['esd_parts'] = '\n'.join(lines)
    return t


def check_readme(write=False):
    import re
    tables = render(json.loads((HERE / 'protection-screen.json').read_text()))
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
    print('README tables:', 'match protection-screen.json' if not bad else f'MISMATCH in {bad}')
    return not bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--jobs', type=int, default=max(1, (os.cpu_count() or 2) - 2))
    ap.add_argument('--only', nargs='*')
    ap.add_argument('--esd', action='store_true')
    ap.add_argument('--check-readme', action='store_true')
    ap.add_argument('--write-readme', action='store_true')
    a = ap.parse_args()
    if a.check_readme or a.write_readme:
        sys.exit(0 if check_readme(a.write_readme) else 1)
    if a.esd:
        esd_main(a.only or ESD_NAMES, a.jobs)
        return
    names = a.only or [n for n in CANDIDATES if n not in ACCURACY_ONLY]
    cases = [(s, p, rg, c, sgn * v, n) for n in names for s in cd.SCENARIOS for p, rg in STATES for c in SCREEN_C
             for v in SCREEN_V for sgn in (1, -1)]
    with cf.ThreadPoolExecutor(a.jobs) as ex:
        res = dict(zip(cases, ex.map(run, cases)))
    path = HERE / 'protection-screen.json'
    out = json.loads(path.read_text()) if path.exists() else {}
    out.setdefault('candidates', {})
    for n in names:
        th = thresholds(res, n)
        worst = {}
        for k, r in res.items():
            if k[-1] != n or 'error' in r:
                continue
            for part, x in r['prot'].items():
                w = worst.setdefault(part, {'i_pk_a': 0.0, 'e_j': 0.0, 'p_pk_w': 0.0, 'v_pk': 0.0, 'at_30v_1uF': {}})
                for q in ('i_pk_a', 'e_j', 'p_pk_w', 'v_pk'):
                    if q in x:
                        w[q] = max(w[q], x[q])
                if abs(k[4]) == 30 and k[3] == 1e-6:
                    for q, val in x.items():
                        w['at_30v_1uF'][q] = max(w['at_30v_1uF'].get(q, 0.0), val)
        out['candidates'][n] = {'config': {k: v for k, v in CANDIDATES[n].items()}, 'thresholds': th,
                                'min_v_within_ratings': min(x['v_within_ratings'] for x in th.values()),
                                'target_met_1uF_30V': all(x['v_within_ratings'] >= 30 for x in th.values()),
                                'part_stress_worst': worst,
                                'errors': [list(k) for k, r in res.items() if k[-1] == n and 'error' in r]}
        print(f"{n:22} min class-A {out['candidates'][n]['min_v_within_ratings']:g} V  target "
              f"{out['candidates'][n]['target_met_1uF_30V']}  errors {len(out['candidates'][n]['errors'])}")
    out['generated_by'] = 'validation/rev-g-protection/protection_screen.py'
    path.write_text(json.dumps(out, indent=1, default=str) + '\n')


if __name__ == '__main__':
    main()
