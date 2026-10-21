"""Combine FD, closed-form, header, inductance and proximity results into extracted.json.

Capacitance (pF):
  nom  = 3-D FD (JLC04161H-7628, finest whole-AFE grid) corrected to the
         finest zoom grid (ratio of the same quantity, zoom fine/zoom at the
         AFE spacing), + nominal component/package/header terms.
  low  = nominal FD terms x (1 - U_GRID) + low component terms, no solder-mask
         uplift.
  high = nominal FD terms x (1 + U_GRID); ground terms replaced by the
         thin-prepreg JLC04161H-1080 FD solve where larger; mutual terms
         +15 % solder-mask/copper-thickness uplift; + high component terms.
None of these is a mathematical bound; see README.

Per range: Maxwell matrix of [S=summing, T=TIA_OUT, H=DUT_HI, LB, HB, RF100,
RF5K, RF100K] with the selected RF net merged into T (its jumper is shunted)
and the two unselected RF nets floating (Kron-reduced).
"""
from __future__ import annotations

import json
import os

import numpy as np

from common import HERE, NOMINAL_STACKUP, THIN_STACKUP

FD = HERE / 'fd_results'
RANGES = {'100R': 'RF100', '5k': 'RF5K', '100k': 'RF100K'}
EXTRA = {  # component / package terms not in the board FD model (pF)
    'pkg_pin_pair': {'low': 0.02, 'nom': 0.04, 'high': 0.08},   # VSSOP adjacent leads in mould
    'res_body': {'low': 0.02, 'nom': 0.05, 'high': 0.10},       # 0603 thin-film parallel C
    'mask_uplift': {'low': 1.0, 'nom': 1.05, 'high': 1.15},     # on board mutual terms
    'header_er': {'low': 'er_ins=1.0', 'nom': 'er_ins=3.6', 'high': 'er_ins=4.2'},
}
ASSUMED = {
    'l_c104_branch_nh': 5.0, 'l_c104_branch_sensitivity_nh': 10.0, 'l_rf_branch_nh': 100.0,
    'c_dut_terminal_gnd_pf': [0.0, 100.0],
}


def load(name):
    p = FD / name
    return json.loads(p.read_text()) if p.exists() else None


def best_afe(stackup, variant=''):
    suf = f'_{variant}' if variant else ''
    for dx in ('0.05', '0.07', '0.1'):
        d = load(f'fd_afe_{stackup}_{dx}_neumann{suf}.json')
        if d:
            return d
    return None


def matrix(d, names):
    n = len(names)
    C = np.zeros((n, n))
    for i, a in enumerate(names):
        row = d['maxwell_pF'][a]
        for j, b in enumerate(names):
            C[i, j] = row.get(b, 0.0)
    # symmetrise (solver residual ~1e-7)
    return 0.5 * (C + C.T)


def zoom_factors(dx_afe):
    zs = sorted([json.loads(p.read_text()) for p in FD.glob(f'fd_zoom_{NOMINAL_STACKUP}_*_neumann.json')],
                key=lambda d: -d['dx_mm'])
    if not zs:
        return 1.0, 1.0, 1.0, 1.0, {}
    def q(d):
        r = d['maxwell_pF']['DUT_LO']
        return -r['__ground__'], -r['TIA_OUT']
    table = {d['dx_mm']: dict(zip(('DUT_LO_ground', 'DUT_LO_TIA_OUT'), q(d))) for d in zs}
    coarse = min(zs, key=lambda d: abs(d['dx_mm'] - dx_afe))
    fine = zs[-1]
    g0, m0 = q(coarse); g1, m1 = q(fine)
    f_g, f_m = g1 / g0, m1 / m0
    # first-order Richardson from the two finest grids
    if len(zs) >= 2:
        d2, d1 = zs[-2], zs[-1]
        h2, h1 = d2['dx_mm'], d1['dx_mm']
        (ga, ma), (gb, mb) = q(d2), q(d1)
        g_inf = gb + (gb - ga) * h1 / (h2 - h1)
        m_inf = mb + (mb - ma) * h1 / (h2 - h1)
        r_g, r_m = g_inf / g0, m_inf / m0
    else:
        r_g, r_m = f_g, f_m
    return f_g, f_m, max(r_g, f_g), max(r_m, f_m), table


def corrected(C, f_ground, f_mut):
    off = C - np.diag(np.diag(C))
    ground = C.sum(1)
    off2 = off * f_mut
    ground2 = ground * f_ground
    return off2 + np.diag(ground2 - off2.sum(1))


def add_cap(C, i, j, c):
    """Add capacitance c between nodes i and j (j=None: to ground)."""
    C = C.copy()
    C[i, i] += c
    if j is not None:
        C[j, j] += c; C[i, j] -= c; C[j, i] -= c
    return C


def kron(C, keep, merge=None):
    """merge: list of (into, from) node merges, then eliminate nodes not in keep."""
    C = C.copy()
    idx = list(range(C.shape[0]))
    for into, frm in (merge or []):
        C[into, :] += C[frm, :]; C[:, into] += C[:, frm]
        C[frm, :] = 0; C[:, frm] = 0
        idx.remove(frm)
    elim = [i for i in idx if i not in keep]
    a = np.ix_(keep, keep); b = np.ix_(keep, elim); f = np.ix_(elim, elim)
    if not elim:
        return C[a]
    return C[a] - C[b] @ np.linalg.solve(C[f], C[np.ix_(elim, keep)])


def headers(case):
    h = json.loads((HERE / 'headers.json').read_text())[EXTRA['header_er'][case]]
    return h['C_to_ground_each_pF'], h['Cm_pF']


U_GRID = 0.10  # FD discretisation uncertainty (see README: zoom series and fd_validate.json)


def corner_matrices(names, d7, d1):
    f_g, f_m, _, _, table = zoom_factors(d7['dx_mm'])
    C7 = matrix(d7, names)
    out = {'nom': corrected(C7, f_g, f_m),
           'low': corrected(C7, f_g * (1 - U_GRID), f_m * (1 - U_GRID))}
    hi = corrected(C7, f_g * (1 + U_GRID), f_m * (1 + U_GRID))
    if d1 is not None:
        f_g1 = zoom_factors(d1['dx_mm'])[0]
        C1 = corrected(matrix(d1, names), f_g1 * (1 + U_GRID), 1.0)
        # high: larger of thin-stackup and 7628 ground terms, 7628 mutual terms
        g = np.maximum(C1.sum(1), hi.sum(1))
        off = hi - np.diag(np.diag(hi))
        hi = off + np.diag(g - off.sum(1))
    out['high'] = hi
    meta = {'fd_nominal': f"{NOMINAL_STACKUP} dx={d7['dx_mm']}",
            'fd_thin': None if d1 is None else f"{THIN_STACKUP} dx={d1['dx_mm']}",
            'zoom_convergence_DUT_LO': table, 'factor_ground': f_g, 'factor_mutual': f_m,
            'grid_uncertainty': U_GRID}
    return out, meta


def base_matrices():
    names = ['DUT_LO', 'TIA_OUT', 'DUT_HI', 'LOW_BUF', 'HIGH_BUF', 'RF100', 'RF5K', 'RF100K']
    out, meta = corner_matrices(names, best_afe(NOMINAL_STACKUP), best_afe(THIN_STACKUP))
    return names, out, meta


def with_extras(C, case, names, sum_name='DUT_LO', j3_name='DUT_LO'):
    i = {n: k for k, n in enumerate(names)}
    up = EXTRA['mask_uplift'][case]
    off = C - np.diag(np.diag(C)); ground = C.sum(1)
    off = off * up
    C = off + np.diag(ground - off.sum(1))
    pp = EXTRA['pkg_pin_pair'][case]
    C = add_cap(C, i[sum_name], i['TIA_OUT'], pp)      # U7 pin2-pin1
    C = add_cap(C, i[sum_name], None, pp)              # U7 pin2-pin3 (GND)
    C = add_cap(C, i[j3_name], i['LOW_BUF'], pp)       # U7 pin5-pin6
    for rf in RANGES.values():
        C = add_cap(C, i[sum_name], i[rf], EXTRA['res_body'][case])
    cg, cm = headers(case)
    C = add_cap(C, i[j3_name], None, cg)               # J3 LO post
    C = add_cap(C, i['DUT_HI'], None, cg)              # J3 HI post
    C = add_cap(C, i[j3_name], i['DUT_HI'], cm)        # J3 post pair
    return C, cg, cm


def per_range(C, names, case, rng, sum_name='DUT_LO', j3_name='DUT_LO'):
    i = {n: k for k, n in enumerate(names)}
    _, cg, cm = with_extras(np.zeros_like(C), case, names, sum_name, j3_name)
    C, cg, cm = with_extras(C, case, names, sum_name, j3_name)
    sel = RANGES[rng]
    for r, rf in RANGES.items():
        if rf == sel:
            C = add_cap(C, i['TIA_OUT'], None, 2 * cg)          # both posts on TIA_OUT (shunt not incl.)
        else:
            C = add_cap(C, i['TIA_OUT'], None, cg)
            C = add_cap(C, i[rf], None, cg)
            C = add_cap(C, i['TIA_OUT'], i[rf], cm)              # open header pin pair
    keep_names = [n for n in names if n not in RANGES.values()]
    keep = [i[n] for n in keep_names]
    R = kron(C, keep, merge=[(i['TIA_OUT'], i[sel])])
    k = {n: m for m, n in enumerate(keep_names)}
    S, T, H, LB, HB = (k[sum_name], k['TIA_OUT'], k['DUT_HI'], k['LOW_BUF'], k['HIGH_BUF'])
    rows = R.sum(1)
    res = {
        'c_sum_gnd_pf': rows[S] - R[S, HB],                      # true ground + HIGH_BUF (driven)
        'c_sum_tiaout_pf': -R[S, T],
        'c_sum_lowbuf_pf': -R[S, LB],
        'c_hi_gnd_pf': rows[H] - R[H, LB],
        'c_hi_sum_pf': -R[H, S],
        'c_hi_tiaout_pf': -R[H, T],
        'c_hi_highbuf_pf': -R[H, HB],
        'c_tiaout_gnd_pf': rows[T] - R[T, LB] - R[T, HB],
    }
    if j3_name != sum_name:
        J = k[j3_name]
        res.update({
            'c_j3side_gnd_pf': rows[J] - R[J, HB],
            'c_sum_j3side_pf': -R[S, J],
            'c_j3side_lowbuf_pf': -R[J, LB],
            'c_hi_j3side_pf': -R[H, J],
        })
        res['c_hi_sum_pf'] = -R[H, S]
    return {a: float(b) for a, b in res.items()}


def verdict(assumed, lo, nom, hi):
    if hi <= assumed:
        return 'conservative (assumption >= extracted high)'
    if nom <= assumed:
        return 'roughly right (assumption between extracted nominal and high)'
    return 'optimistic (extracted nominal exceeds assumption)'


def main():
    names, mats, meta = base_matrices()
    ind = json.loads((HERE / 'inductance.json').read_text())
    prox = json.loads((HERE / 'proximity.json').read_text())
    ext = {'board_sha256': json.loads((HERE / 'fd_results' / f"fd_afe_{NOMINAL_STACKUP}_0.1_neumann.json").read_text())['board_sha256'],
           'units': 'pF, nH', 'definitions': {
               'c_sum_gnd_pf': 'summing node (DUT_LO net: U7A -IN, U7B +IN, C104.1, R43-45.1, J3.2 + post) to AC ground; board only, excludes fixture/cable and amplifier input capacitance; excludes the bootstrapped LOW_BUF coupling (c_sum_lowbuf_pf)',
               'c_sum_tiaout_pf': 'summing node to TIA_OUT, in parallel with C104 (adds to CF); includes selected RF net/header, unselected RF branches through their floating nodes, 0603 resistor body and U7 lead-to-lead estimate',
               'c_hi_gnd_pf': 'DUT_HI to AC ground (excluding HIGH_BUF follower coupling)',
               'c_hi_sum_pf': 'DUT_HI to summing node (parallel to the DUT), incl. J3 posts',
               'l_c104_branch_nh': 'loop U7.1 -> C104 -> U7.2 closed through the OPA2810 package (leads, bond wires, die)',
               'l_rf_branch_nh': 'loop U7.1 -> TIA_OUT copper -> JPx posts/shunt -> RF resistor -> summing copper -> U7.2, closed through the package'},
           'meta': meta, 'ranges': {}, 'assumed_in_simulation': ASSUMED}
    for rng in RANGES:
        ext['ranges'][rng] = {c: per_range(mats[c], names, c, rng) for c in ('low', 'nom', 'high')}
    # harness summary: worst case over ranges for each quantity and corner
    summ = {}
    keys = ext['ranges']['100R']['nom'].keys()
    for key in keys:
        summ[key] = {c: {r: round(ext['ranges'][r][c][key], 4) for r in RANGES} for c in ('low', 'nom', 'high')}
    ext['capacitance_by_range'] = summ
    harness = {}
    for key in ('c_sum_gnd_pf', 'c_sum_tiaout_pf', 'c_hi_gnd_pf', 'c_hi_sum_pf', 'c_sum_lowbuf_pf',
                'c_tiaout_gnd_pf', 'c_hi_tiaout_pf'):
        harness[key] = {c: round(min(summ[key][c].values()) if c == 'low' else max(summ[key][c].values()), 3)
                        for c in ('low', 'nom', 'high')}
        if key == 'c_sum_tiaout_pf':
            harness[key + '_by_range'] = {r: {c: summ[key][c][r] for c in ('low', 'nom', 'high')} for r in RANGES}
    L = ind['loops']
    harness['l_c104_branch_nh'] = {c: round(L['C104'][c]['with_package_nH'], 2) for c in ('low', 'nom', 'high')}
    harness['l_c104_branch_board_only_nh'] = {c: round(L['C104'][c]['board_and_part_only_nH'], 2) for c in ('low', 'nom', 'high')}
    harness['l_rf_branch_nh'] = {r: {c: round(L[f'RF_{r}'][c]['with_package_nH'], 2) for c in ('low', 'nom', 'high')} for r in RANGES}
    harness['l_rf_branch_board_only_nh'] = {r: {c: round(L[f'RF_{r}'][c]['board_and_part_only_nH'], 2) for c in ('low', 'nom', 'high')} for r in RANGES}
    harness['l_shared_package_and_pin_path_nh'] = {r: round(L[f'RF_{r}']['mutual_with_C104_loop_free_space_nH'], 2) for r in RANGES}
    noisy = {}
    for lab, g in prox['groups'].items():
        noisy[lab] = {'nets': g['nets'],
                      'min_distance_to_sum_mm': g['DUT_LO']['min_distance_mm'],
                      'c_to_sum_fF': {'nom': round(g['DUT_LO']['c_mutual_fF_nom'], 4), 'high': round(g['DUT_LO']['c_mutual_fF_high'], 4)},
                      'min_distance_to_tiaout_mm': g['TIA_OUT']['min_distance_mm'],
                      'c_to_tiaout_fF': {'nom': round(g['TIA_OUT']['c_mutual_fF_nom'], 4), 'high': round(g['TIA_OUT']['c_mutual_fF_high'], 4)},
                      'min_distance_to_hi_mm': g['DUT_HI']['min_distance_mm'],
                      'c_to_hi_fF': {'nom': round(g['DUT_HI']['c_mutual_fF_nom'], 4), 'high': round(g['DUT_HI']['c_mutual_fF_high'], 4)}}
    harness['noisy_copper_coupling'] = noisy
    # verdicts
    v = {}
    lc = harness['l_c104_branch_nh']
    v['l_c104_branch_nh'] = verdict(ASSUMED['l_c104_branch_nh'], lc['low'], lc['nom'], lc['high'])
    for r in RANGES:
        lr = harness['l_rf_branch_nh'][r]
        v[f'l_rf_branch_nh[{r}]'] = verdict(ASSUMED['l_rf_branch_nh'], lr['low'], lr['nom'], lr['high'])
    harness['verdict_vs_simulation'] = v
    ext['harness'] = harness
    # Rev D: 'riso' is the proposed placement synthesised on the Rev C board (riso_variant.py);
    # 'revd' is the as-built Rev D board (geometry_revd.json, run_revd.sh).
    for variant, key in (('riso', 'rev_d_riso_variant'), ('revd', 'rev_d_board')):
        dv = best_afe(NOMINAL_STACKUP, variant)
        if dv is None:
            continue
        vn = ['TIA_SUM', 'DUT_LO', 'TIA_OUT', 'DUT_HI', 'LOW_BUF', 'HIGH_BUF', 'RF100', 'RF5K', 'RF100K']
        mv, mmeta = corner_matrices(vn, dv, best_afe(THIN_STACKUP, variant))
        riso = {}
        for rng in RANGES:
            riso[rng] = {c: per_range(mv[c], vn, c, rng, sum_name='TIA_SUM', j3_name='DUT_LO') for c in ('low', 'nom', 'high')}
            for c in ('low', 'nom', 'high'):
                riso[rng][c]['c_sum_j3side_pf'] += EXTRA['res_body'][c]   # R_ISO body
        ext[key] = {'fd': mmeta['fd_nominal'], 'fd_thin': mmeta['fd_thin'], 'ranges': riso}
        if variant == 'revd':
            ext[key]['board_sha256'] = json.loads((HERE / 'geometry_revd.json').read_text())['board_sha256']
            ind = HERE / 'inductance_revd.json'
            if ind.exists():
                ext[key]['inductance_nh'] = {n: {c: round(v[c]['with_package_nH'], 2) for c in ('low', 'nom', 'high')}
                                             for n, v in json.loads(ind.read_text())['loops'].items()}
    (HERE / 'extracted.json').write_text(json.dumps(ext, indent=1, default=float))
    print(json.dumps(harness, indent=1, default=float)[:6000])
    for key in ('rev_d_riso_variant', 'rev_d_board'):
        for c in ('low', 'nom', 'high'):
            if key in ext:
                print(key, c, {k: round(x, 3) for k, x in ext[key]['ranges']['100R'][c].items()})


if __name__ == '__main__':
    main()
