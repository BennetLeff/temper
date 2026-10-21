"""Rev E board parasitics -> extracted_reve.json and the stability-harness include.

Capacitance (pF), same conventions as assemble.py:
  nom  = 3-D FD whole-board solve ('reve' window, JLC04161H-7628, finest dx run)
         corrected by zoom-window grid ratios (ground terms: TIA_OUT ground in the
         'reve_relay' zoom; mutual terms: TIA_SUM-TIA_OUT in the U7 'zoom' window;
         each = finest zoom dx / zoom at the whole-board dx), + nominal part terms.
  low  = nominal FD terms x (1 - U), low part terms, no mask uplift.
  high = nominal FD terms x (1 + U); ground terms replaced by the thin-prepreg
         JLC04161H-1080 solve where larger; mutual terms +15 % mask/copper uplift.
  U = max(10 %, spread of all zoom ratios around the chosen factor).
  The SOURCE_BUF-DUT_HI mutual (a 31 mm broadside In2/B.Cu pair, x 188.8/188.9) is
  corrected by its own zoom ratio ('reve_hiside' window) instead of the mutual factor.
None of these is a mathematical bound.

Per range the selected relay closes Kx.8-Kx.7 and Kx.3-Kx.4, so the selected RF
net merges into TIA_OUT and the selected RG net into SOURCE_BUF.  Unselected RF
and RG nets stay separate nodes (harness ru{k} / rgu{k}).  Every board ground and
mutual term >= 1 fF is emitted as a SPICE capacitor in
../stability-full-chain/reve_extracted.rs, together with the extracted RF-branch
and C104-branch inductances (free-space 'high' values from inductance_reve.json).

LP_VARIANT selects the board: 'reve' (board 2f6486c4, default) or 'reve_r104' (board
cf379f85: R104 47 ohm between the source driver U6A, net SRC_DRV, and SOURCE_BUF; SOURCE_BUF
rerouted to In2 x 185.5).  For reve_r104 the K1-relay and U7 zoom series are reused from
'reve': the copper of every conductor and the In1 fill inside those windows (+3 mm) are
identical on the two boards (only the SOURCE_BUF bus end outside the windows moved).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np

from assemble import EXTRA, add_cap, corrected, headers, matrix
from common import HERE, NOMINAL_STACKUP, THIN_STACKUP

FD = HERE / 'fd_results'
VARIANT = os.environ.get('LP_VARIANT', 'reve')
CFG = {'reve': dict(whole='reve', zoom_variant='reve', hiside='reve_hiside', extra=[]),
       'reve_r104': dict(whole='reve_r104', zoom_variant='reve', hiside='reve_hiside_r104',
                         extra=['SRC_DRV']),
       # four-terminal BNC board (80d44838, uncommitted working tree when extracted): J3/J7/J8/J9
       # HCUR/HPOT/LPOT/LCUR, R105/R106 1k CUR-POT, K4 reference relay (REF_A, R107 1k to DUT_LO).
       # Per-net ground factors and pair factors come from zooms on the new routes.
       'reve_bnc': dict(whole='reve_bnc', zoom_variant='reve_bnc', hiside='reve_hiside_r104',
                        extra=['SRC_DRV', 'HPOT', 'LPOT', 'REF_A'], kelvin=True,
                        net_ground={'HPOT': 'bnc_band', 'DUT_HI': 'bnc_band', 'LPOT': 'bnc_vert',
                                    'DUT_LO': 'bnc_vert', 'REF_A': 'bnc_corner',
                                    'SOURCE_BUF': 'reve_hiside_r104'},
                        pairs=[('SOURCE_BUF', 'DUT_HI', 'reve_hiside_r104'), ('DUT_HI', 'HPOT', 'bnc_band'),
                               ('DUT_LO', 'LPOT', 'bnc_corner'), ('HPOT', 'LPOT', 'bnc_vert'),
                               ('DUT_HI', 'DUT_LO', 'bnc_corner'), ('DUT_HI', 'REF_A', 'bnc_corner')]),
       }[VARIANT]
NAMES = ['TIA_SUM', 'DUT_LO', 'TIA_OUT', 'DUT_HI', 'RF100', 'RF5K', 'RF100K', 'LOW_BUF', 'HIGH_BUF',
         'SOURCE_BUF', 'RG100', 'RG5K', 'RG100K'] + CFG['extra']
# harness RANGES order: r100, r5k, r100k (k = 0, 1, 2)
RANGES = [('r100', '100R', 'RF100', 'RG100'), ('r5k', '5k', 'RF5K', 'RG5K'), ('r100k', '100k', 'RF100K', 'RG100K')]
RF_RES = {'RF100': 'R43', 'RF5K': 'R44', 'RF100K': 'R45'}
RG_RES = {'RG100': 'R40', 'RG5K': 'R41', 'RG100K': 'R42'}
NODE = {'TIA_SUM': 'sum', 'DUT_LO': 'low', 'TIA_OUT': 'tia', 'DUT_HI': 'hi', 'LOW_BUF': 'lowbuf',
        'HIGH_BUF': 'highbuf', 'SOURCE_BUF': 'source',
        'SRC_DRV': 'srcdrv',  # srcdrv: driver side of R104 (loop_matrix.rs maps it to the X6A node)
        'HPOT': 'hpot', 'LPOT': 'lpot', 'REF_A': 'refa'}
# SAMZO BNC-KYWE-295 right-angle jack, centre pin to grounded shell, pF.  ESTIMATE (no datasheet in
# sources/): 50 ohm line of 15 / 22 / 30 mm in PTFE-POM (97-115 pF/m).
BNC_JACK_PF = {'low': 1.5, 'nom': 2.5, 'high': 3.5}
U_MIN = 0.10
REVD_HIGH = {  # loop_matrix.rs REVD_BOARD / RANGES (Rev D extraction, high corner)
    'c_tiaout_gnd_pf': 10.53, 'c_sum_gnd_pf': 1.274, 'c_sum_tiaout_pf': 0.399, 'c_lo_gnd_pf': 5.666,
    'c_hi_gnd_pf': 5.232, 'c_hi_lo_pf': 0.158, 'c_sum_lo_pf': 0.118, 'c_lo_lowbuf_pf': 0.15,
    'l_rf_nh': {'r100': 21.65, 'r5k': 50.46, 'r100k': 33.14}, 'l_c104_nh': 4.87}


def load(name):
    p = FD / name
    return json.loads(p.read_text()) if p.exists() else None


def runs(window, stackup, variant=None):
    v = variant or VARIANT
    out = [json.loads(p.read_text()) for p in FD.glob(f'fd_{window}_{stackup}_*_neumann_{v}.json')]
    return sorted(out, key=lambda d: -d['dx_mm'])


def ground(d, n):
    return sum(d['maxwell_pF'][n].values()) - d['maxwell_pF'][n]['__ground__']


def mutual(d, a, b):
    return -d['maxwell_pF'][a][b]


def ratio_table(series, fn, dx_ref):
    tab = {d['dx_mm']: fn(d) for d in series}
    ref = min(series, key=lambda d: abs(d['dx_mm'] - dx_ref))
    return tab, fn(series[-1]) / fn(ref)


def grid_factors(dx_whole):
    zv = CFG['zoom_variant']
    rel, u7 = runs('reve_relay', NOMINAL_STACKUP, zv), runs('zoom', NOMINAL_STACKUP, zv)
    hs = runs(CFG['hiside'], NOMINAL_STACKUP)
    q = {
        'SOURCE_BUF_ground (reve_hiside)': (hs, lambda d: ground(d, 'SOURCE_BUF')),
        'TIA_OUT_ground (reve_relay)': (rel, lambda d: ground(d, 'TIA_OUT')),
        'SOURCE_BUF_ground (reve_relay)': (rel, lambda d: ground(d, 'SOURCE_BUF')),
        'RF100_ground (reve_relay)': (rel, lambda d: ground(d, 'RF100')),
        'TIA_SUM_ground (zoom U7)': (u7, lambda d: ground(d, 'TIA_SUM')),
        'TIA_OUT_RF100_mutual (reve_relay)': (rel, lambda d: mutual(d, 'TIA_OUT', 'RF100')),
        'RF100_RF100K_mutual (reve_relay)': (rel, lambda d: mutual(d, 'RF100', 'RF100K')),
        'TIA_SUM_TIA_OUT_mutual (zoom U7)': (u7, lambda d: mutual(d, 'TIA_SUM', 'TIA_OUT')),
    }
    table, ratios = {}, {}
    for k, (series, fn) in q.items():
        table[k], ratios[k] = ratio_table(series, fn, dx_whole)
    table['SOURCE_BUF_DUT_HI_mutual (reve_hiside)'], pair = ratio_table(
        hs, lambda d: mutual(d, 'SOURCE_BUF', 'DUT_HI'), dx_whole)
    f_g = ratios['TIA_OUT_ground (reve_relay)']
    f_m = ratios['TIA_SUM_TIA_OUT_mutual (zoom U7)']
    if CFG.get('kelvin'):
        return kelvin_factors(dx_whole, f_g, f_m, table, ratios, rel)
    spread = max(abs(r / (f_g if 'ground' in k else f_m) - 1) for k, r in ratios.items())
    ratios['SOURCE_BUF_DUT_HI_mutual (reve_hiside, applied to that pair only)'] = pair
    return f_g, f_m, max(U_MIN, spread), {'convergence_pF_by_dx': table, 'finest_over_whole_dx_ratio': ratios,
                                          'zoom_dx': [d['dx_mm'] for d in rel], 'pair_factor': pair}


def kelvin_factors(dx_whole, f_g, f_m, table, ratios, rel):
    """Per-net ground factors and per-pair mutual factors from the BNC-route zooms (reve_bnc)."""
    fg = np.full(len(NAMES), f_g)
    applied = {}
    for net, win in CFG['net_ground'].items():
        k = f'{net}_ground ({win})'
        table[k], r = ratio_table(runs(win, NOMINAL_STACKUP), lambda d, n=net: ground(d, n), dx_whole)
        fg[NAMES.index(net)] = ratios[k] = r
        applied[k] = r
    pairs = []
    for a, b, win in CFG['pairs']:
        k = f'{a}_{b}_mutual ({win})'
        series = runs(win, NOMINAL_STACKUP)
        table[k], r = ratio_table(series, lambda d, a=a, b=b: mutual(d, a, b), dx_whole)
        ratios[k] = r
        if mutual(series[-1], a, b) >= 0.01:   # only resolved couplings get their own factor
            pairs.append((a, b, r)); applied[k] = r
    # spread: every ratio not used as its own factor, against the factor that is applied instead
    dev = [abs(r / (f_g if 'ground' in k else f_m) - 1) for k, r in ratios.items() if k not in applied]
    # and, for the quantities that carry their own factor, the change over the last zoom refinement
    for k in applied:
        v = [table[k][dx] for dx in sorted(table[k])[:2]]
        dev.append(abs(v[0] / v[1] - 1))
    return fg, f_m, max(U_MIN, max(dev)), {'convergence_pF_by_dx': table, 'finest_over_whole_dx_ratio': ratios,
                                           'applied_own_factor': applied, 'zoom_dx': [d['dx_mm'] for d in rel],
                                           'pairs': pairs}


def pairs_fix(C, pairs, f_m):
    for a, b, r in pairs:
        C = pair_fix(C, r, f_m, a, b)
    return C


def pair_fix(C, f_pair, f_m, a='SOURCE_BUF', b='DUT_HI'):
    """Rescale one mutual term from the global factor f_m to its own grid factor, ground terms kept."""
    i, j = NAMES.index(a), NAMES.index(b)
    C = C.copy()
    g = C.sum(1)
    C[i, j] = C[j, i] = C[i, j] * f_pair / f_m
    off = C - np.diag(np.diag(C))
    return off + np.diag(g - off.sum(1))


def corner_matrices():
    d7 = runs(CFG['whole'], NOMINAL_STACKUP)[-1]
    d1s = runs(CFG['whole'], THIN_STACKUP)
    d1 = d1s[-1] if d1s else None
    f_g, f_m, U, meta = grid_factors(d7['dx_mm'])
    C7 = matrix(d7, NAMES)
    if CFG.get('kelvin'):
        fix = lambda C: pairs_fix(C, meta['pairs'], f_m)
    else:
        fix = lambda C: pair_fix(C, meta['pair_factor'], f_m)
    out = {'nom': fix(corrected(C7, f_g, f_m)), 'low': fix(corrected(C7, f_g * (1 - U), f_m * (1 - U)))}
    hi = fix(corrected(C7, f_g * (1 + U), f_m * (1 + U)))
    if d1 is not None:
        f_g1 = grid_factors(d1['dx_mm'])[0]
        C1 = corrected(matrix(d1, NAMES), f_g1 * (1 + U), 1.0)
        g = np.maximum(C1.sum(1), hi.sum(1))
        off = hi - np.diag(np.diag(hi))
        hi = off + np.diag(g - off.sum(1))
    out['high'] = hi
    meta.update({'fd_nominal': f"{NOMINAL_STACKUP} dx={d7['dx_mm']} grid={d7['grid']}",
                 'fd_thin': None if d1 is None else f"{THIN_STACKUP} dx={d1['dx_mm']}",
                 'factor_ground': (dict(zip(NAMES, map(float, f_g))) if np.ndim(f_g) else f_g),
                 'factor_mutual': f_m, 'grid_uncertainty': U,
                 'whole_dx_runs': [d['dx_mm'] for d in runs(CFG['whole'], NOMINAL_STACKUP)]})
    # two-dx whole-board check (raw, uncorrected)
    ws = runs(CFG['whole'], NOMINAL_STACKUP)
    meta['whole_board_raw_by_dx'] = {d['dx_mm']: {
        'TIA_OUT_ground': ground(d, 'TIA_OUT'), 'SOURCE_BUF_ground': ground(d, 'SOURCE_BUF'),
        'TIA_SUM_ground': ground(d, 'TIA_SUM'), 'TIA_SUM_TIA_OUT': mutual(d, 'TIA_SUM', 'TIA_OUT'),
        'SOURCE_BUF_DUT_HI': mutual(d, 'SOURCE_BUF', 'DUT_HI')} for d in ws}
    return out, meta


def with_extras(C, case):
    i = {n: k for k, n in enumerate(NAMES)}
    up = EXTRA['mask_uplift'][case]
    off = C - np.diag(np.diag(C)); g = C.sum(1)
    off = off * up
    C = off + np.diag(g - off.sum(1))
    pp, rb = EXTRA['pkg_pin_pair'][case], EXTRA['res_body'][case]
    C = add_cap(C, i['TIA_SUM'], i['TIA_OUT'], pp)     # U7 pin 2-1
    C = add_cap(C, i['TIA_SUM'], None, pp)             # U7 pin 2-3 (GND)
    if CFG.get('kelvin'):
        C = add_cap(C, i['LPOT'], i['LOW_BUF'], pp)    # U7 pin 5-6 (LOW follower +IN = LPOT)
        C = add_cap(C, i['LPOT'], None, pp)            # U7 pin 5-4 (-12V)
        C = add_cap(C, i['HPOT'], i['HIGH_BUF'], pp)   # U6 pin 5-6 (HIGH follower +IN = HPOT)
        C = add_cap(C, i['HPOT'], None, pp)            # U6 pin 5-4 (-12V)
    else:
        C = add_cap(C, i['DUT_LO'], i['LOW_BUF'], pp)  # U7 pin 5-6
    for rf in RF_RES:
        C = add_cap(C, i['TIA_SUM'], i[rf], rb)        # R43-R45 bodies
    for rg in RG_RES:
        C = add_cap(C, i['DUT_HI'], i[rg], rb)         # R40-R42 bodies
    C = add_cap(C, i['TIA_SUM'], i['DUT_LO'], rb)      # R94 (R_iso) body
    if CFG.get('kelvin'):
        C = add_cap(C, i['DUT_HI'], i['HPOT'], rb)     # R105 body
        C = add_cap(C, i['DUT_LO'], i['LPOT'], rb)     # R106 body
        C = add_cap(C, i['REF_A'], i['DUT_LO'], rb)    # R107 body
        for n in ('DUT_HI', 'HPOT', 'LPOT', 'DUT_LO'):  # J3 / J7 / J8 / J9 jack bodies
            C = add_cap(C, i[n], None, BNC_JACK_PF[case])
        return C
    cg, cm = headers(case)
    C = add_cap(C, i['DUT_LO'], None, cg)              # J3 LO post
    C = add_cap(C, i['DUT_HI'], None, cg)              # J3 HI post
    C = add_cap(C, i['DUT_LO'], i['DUT_HI'], cm)       # J3 post pair
    return C


def node_matrix(C, k_sel):
    """Merge conductors into harness nodes for range index k_sel."""
    nodes = []
    owner = {}
    for n in NAMES:
        nd = NODE.get(n)
        if nd is None:
            k = next(j for j, r in enumerate(RANGES) if n in r)
            if k == k_sel:
                nd = 'tia' if n.startswith('RF') else 'source'
            else:
                nd = f'ru{k}' if n.startswith('RF') else f'rgu{k}'
        owner[n] = nd
        if nd not in nodes:
            nodes.append(nd)
    P = np.zeros((len(nodes), len(NAMES)))
    for j, n in enumerate(NAMES):
        P[nodes.index(owner[n]), j] = 1
    return nodes, P @ C @ P.T


def spice(nodes, M, thr=1e-3):
    lines = []
    g = M.sum(1)
    for a, n in enumerate(nodes):
        if g[a] >= thr:
            lines.append(f'Cxg_{n} {n} 0 {g[a]:.4f}p')
    for a in range(len(nodes)):
        for b in range(a + 1, len(nodes)):
            if -M[a, b] >= thr:
                lines.append(f'Cxm_{nodes[a]}_{nodes[b]} {nodes[a]} {nodes[b]} {-M[a, b]:.4f}p')
    return '\n'.join(lines) + '\n'


def summary(nodes, M):
    i = {n: k for k, n in enumerate(nodes)}
    g = M.sum(1)

    def m(a, b):
        return float(-M[i[a], i[b]]) if a in i and b in i else 0.0
    rf_unsel = [n for n in nodes if n.startswith('ru')]
    return {
        'c_tiaout_gnd_pf': float(g[i['tia']]),
        'c_tiaout_all_pf': float(M[i['tia'], i['tia']]),
        'c_source_gnd_pf': float(g[i['source']]),
        'c_source_all_pf': float(M[i['source'], i['source']]),
        'c_sum_gnd_pf': float(g[i['sum']]),
        'c_sum_tiaout_pf': m('sum', 'tia'),
        'c_sum_lo_pf': m('sum', 'low'),
        'c_lo_gnd_pf': float(g[i['low']]),
        'c_lo_lowbuf_pf': m('low', 'lowbuf'),
        'c_hi_gnd_pf': float(g[i['hi']]),
        'c_hi_lo_pf': m('hi', 'low'),
        'c_source_hi_pf': m('source', 'hi'),
        'c_source_tia_pf': m('source', 'tia'),
        'c_source_sum_pf': m('source', 'sum'),
        'c_source_unsel_rf_pf': sum(m('source', r) for r in rf_unsel),
        'c_tia_unsel_rf_pf': sum(m('tia', r) for r in rf_unsel),
        'c_tia_highbuf_pf': m('tia', 'highbuf'),
        **({'c_srcdrv_gnd_pf': float(g[i['srcdrv']]), 'c_srcdrv_all_pf': float(M[i['srcdrv'], i['srcdrv']]),
            'c_srcdrv_source_pf': m('srcdrv', 'source'), 'c_srcdrv_hi_pf': m('srcdrv', 'hi'),
            'c_srcdrv_highbuf_pf': m('srcdrv', 'highbuf')} if 'srcdrv' in i else {}),
        **({'c_hpot_gnd_pf': float(g[i['hpot']]), 'c_lpot_gnd_pf': float(g[i['lpot']]),
            'c_refa_gnd_pf': float(g[i['refa']]),
            'c_hcur_lcur_pf': m('hi', 'low'), 'c_hpot_lpot_pf': m('hpot', 'lpot'),
            'c_hpot_hcur_pf': m('hpot', 'hi'), 'c_lpot_lcur_pf': m('lpot', 'low'),
            'c_hpot_lcur_pf': m('hpot', 'low'), 'c_lpot_hcur_pf': m('lpot', 'hi'),
            'c_source_hcur_pf': m('source', 'hi'), 'c_source_lcur_pf': m('source', 'low'),
            'c_source_hpot_pf': m('source', 'hpot'), 'c_source_lpot_pf': m('source', 'lpot'),
            'c_srcdrv_kelvin_pf': sum(m('srcdrv', n) for n in ('hi', 'low', 'hpot', 'lpot')),
            'c_sum_lcur_pf': m('sum', 'low'), 'c_sum_lpot_pf': m('sum', 'lpot'), 'c_sum_hpot_pf': m('sum', 'hpot'),
            'c_hcur_refa_pf': m('hi', 'refa'), 'c_refa_lcur_pf': m('refa', 'low'),
            'c_hpot_highbuf_pf': m('hpot', 'highbuf'), 'c_lpot_lowbuf_pf': m('lpot', 'lowbuf'),
            'c_tia_kelvin_pf': sum(m('tia', n) for n in ('hi', 'low', 'hpot', 'lpot'))}
           if 'hpot' in i else {}),
    }


def main():
    mats, meta = corner_matrices()
    ind = json.loads((HERE / f'inductance_{VARIANT}.json').read_text())
    geo_sha = json.loads((HERE / f'geometry_{VARIANT}.json').read_text())['board_sha256']
    ext = {'board_sha256': geo_sha, 'units': 'pF, nH', 'fd': meta, 'ranges': {}, 'spice': {},
           'raw_net_ground_pf': {}, 'rev_d_high_in_harness': REVD_HIGH}
    for c in ('low', 'nom', 'high'):
        C = with_extras(mats[c], c)
        ext['raw_net_ground_pf'][c] = {n: round(float(v), 4) for n, v in zip(NAMES, C.sum(1))}
        ext['spice'][c] = {}
        for k, (rng, _, _, _) in enumerate(RANGES):
            nodes, M = node_matrix(C, k)
            ext['ranges'].setdefault(rng, {})[c] = {a: round(b, 4) for a, b in summary(nodes, M).items()}
            ext['spice'][c][rng] = spice(nodes, M)
    L = ind['loops']
    ext['inductance_nh'] = {
        'c104': {k: (round(v, 2) if v is not None else None) for k, v in L['C104']['summary_nH'].items()},
        **{rng: {k: (round(v, 2) if v is not None else None) for k, v in L[f'RF_{key}']['summary_nH'].items()}
           for rng, key, _, _ in RANGES}}
    (HERE / f'extracted_{VARIANT}.json').write_text(json.dumps(ext, indent=1, default=float))
    # stability-harness include (loop_matrix.rs: include!("reve_extracted.rs"))
    lead = [ext['inductance_nh'][r]['high'] for r, _, _, _ in RANGES]
    P = VARIANT.upper()  # const prefix: REVE_ / REVE_R104_
    rs = [f'// GENERATED by ../layout-parasitics/assemble_reve.py (LP_VARIANT={VARIANT}) from extracted_{VARIANT}.json -- do not edit.',
          f'// Rev E board {geo_sha[:8]}...{geo_sha[-4:]}; FD {meta["fd_nominal"]}, thin {meta["fd_thin"]}.',
          '// RF-branch / C104-branch loop L: free-space (high) value incl. OPA2810 package, nH.',
          f'const {P}_LEAD: [f64; 3] = [{", ".join(f"{v:.2f}" for v in lead)}];',
          f'const {P}_CAPLEAD: f64 = {ext["inductance_nh"]["c104"]["high"]:.2f};']
    for c in ('nom', 'high'):
        rs.append(f'const {P}_BOARD_{c.upper()}: [&str; 3] = [')
        for rng, _, _, _ in RANGES:
            rs.append('    ' + json.dumps(ext['spice'][c][rng]) + ',')
        rs.append('];')
    out = HERE.parent / 'stability-full-chain' / f'{VARIANT}_extracted.rs'
    out.write_text('\n'.join(rs) + '\n')
    print(json.dumps(meta, indent=1, default=float)[:3000])
    for rng in ext['ranges']:
        for c in ('low', 'nom', 'high'):
            print(rng, c, ext['ranges'][rng][c])
    print(json.dumps(ext['inductance_nh'], indent=1))


if __name__ == '__main__':
    main()
