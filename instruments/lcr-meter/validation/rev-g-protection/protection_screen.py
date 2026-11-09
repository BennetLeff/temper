"""Rev G jack protection, phase 1: surge screen of candidate networks (parametric clamps, no part numbers yet).

python3 validation/rev-g-protection/protection_screen.py [--jobs N] [--only NAME ...]  ->  protection-screen.json
python3 validation/rev-g-protection/protection_screen.py --check-readme   README tables == the JSON

Each candidate is a network between the four BNC jacks (jk_hcur, jk_hpot, jk_lpot, jk_lcur) and the Rev F board
nodes (dut_hi, hpot, lpot, dut_lo), dropped into the charged-DUT model (../charged-dut/charged_dut_spice.py,
deck(prot=...)) and judged by its judge(): every OPA2810, LDO, TAC5112, BAT54S and passive rating of Rev F.
The network's own parts are reported (peak current, energy), not judged: phase 2 picks parts with datasheet
ratings to cover them.

Target (charged-dut README, "Rev G requirements"): class A, powered and unpowered, for 1 uF at 30 V on every
connection pattern; the stretch is the E4980A's 1 J.

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
      iso  True                  a normally-open isolation relay after the jack clamp: open (1 pF across the
                                 contact) when the meter is unpowered, closed (0.1 ohm) when powered
      r    {jack: ohms}          series resistor after the relay
      tvs2 {jack: (bv, rd, cj)}  second-stage TVS to GND after the series resistor
      sch2 {jack: True}          second-stage antiparallel Schottky pair to GND after the series resistor
      cap2 {jack: farads}        second-stage capacitor (C0G) to GND after the series resistor
    jack -> TVS -> relay -> R -> second stage -> board node."""
    lines, vecs, parts = [SCH_MODEL], [], []
    models = {}
    for stage in ('tvs', 'tvs2'):
        for j, (bv, rd, cj) in cfg.get(stage, {}).items():
            models[(bv, rd, cj)] = f'DT{len(models)}' if (bv, rd, cj) not in models else models[(bv, rd, cj)]
    for (bv, rd, cj), name in models.items():
        lines.append(f'.model {name} D(IS=1e-12 N=1 RS={rd:g} BV={bv:g} IBV=1m CJO={2 * cj:g})')
    for j, node in JACKS.items():
        a = f'jk_{j}'
        vecs.append(f'v({a})')
        if j in cfg.get('tvs', {}):
            m = models[cfg['tvs'][j]]
            lines += [f'Vam_t1_{j} {a} t1_{j} 0', f'Dt1a_{j} t1_{j} t1m_{j} {m}', f'Dt1b_{j} 0 t1m_{j} {m}']
            vecs.append(f'i(Vam_t1_{j})')
            parts.append(('tvs1', j))
        if cfg.get('iso'):
            lines += ([f'Riso_{j} {a} rl_{j} 0.1'] if power == 'powered' else
                      [f'Ciso_{j} {a} rl_{j} 1p', f'Riso_{j} {a} rl_{j} 1e12'])
            a = f'rl_{j}'
        r = cfg.get('r', {}).get(j, 0.0)
        second = any(j in cfg.get(k, {}) for k in ('tvs2', 'sch2', 'cap2'))
        b = f'mid_{j}' if second else node
        lines.append(f'Rs_{j} {a} {b} {max(r, 1e-3):g}')
        vecs += [f'v({a})', f'v({b})'] if b != node else [f'v({a})']
        if second and j not in cfg.get('tvs2', {}):
            lines.append(f'Rl_{j} {b} {node} 1e-3')
        if j in cfg.get('sch2', {}):
            lines += [f'Vam_s2_{j} {b} s2_{j} 0', f'Ds2a_{j} s2_{j} 0 DSCH', f'Ds2b_{j} 0 s2_{j} DSCH']
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
    return {'lines': lines, 'vecs': vecs, 'parts': parts}


# Parametric clamp sets. TVS5: a 5 V-standoff 400 W-class bidirectional TVS (BV 6.4 V, RD 0.06 ohm, 2 nF).
TVS5 = (6.4, 0.06, 2e-9)
TVS3 = (4.0, 0.1, 0.5e-9)   # a 3.3 V-standoff low-capacitance second stage: passes the 1.7 V source with margin
# A 1-3 A-class Schottky (parametric): 0.31 V at 10 mA, 0.5 V at 1 A.
SCH_MODEL = '.model DSCH D(IS=1e-6 N=1.3 RS=0.03 CJO=200p)'
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
}


def run(case):
    scn, power, rng, c, v, name = case
    prot = network(CANDIDATES[name], power)
    text, t_end = cd.deck(scn, power, rng, c, v, 0.0, cd.ESD_IS, prot)
    col, opt = cd.spice(text, t_end)
    if col is None:
        return {'case': case, 'error': opt}
    r = {'case': case, 'options': opt, **cd.metrics(col, col['time'], rng, 0.0)}
    t = col['time']
    r['prot'] = {}
    for stage, j in prot['parts']:
        i = col[f'i(vam_{ {"tvs1": "t1", "tvs2": "t2", "sch2": "s2"}[stage] }_{j})']
        vj = col[f'v(jk_{j})']
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
    return tables


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
    ap.add_argument('--check-readme', action='store_true')
    ap.add_argument('--write-readme', action='store_true')
    a = ap.parse_args()
    if a.check_readme or a.write_readme:
        sys.exit(0 if check_readme(a.write_readme) else 1)
    names = a.only or list(CANDIDATES)
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
