"""Audit runs of the Rev G protection screen at the brief's cases (read-only use of the repo's models).
Writes only to this scratch directory."""
import sys, json, pathlib, concurrent.futures as cf
REPO = pathlib.Path('/Users/bennet/Desktop/temper/worktrees/lcr-rev-g/instruments/lcr-meter/validation')
sys.path.insert(0, str(REPO / 'rev-g-protection'))
import protection_screen as ps
cd = ps.cd

def one(case):
    name, scn, deck_power, sw, rng, c, v = case
    cfg = ps.CANDIDATES[name]
    prot = ps.network(cfg, 'powered' if sw == 'closed' else 'unpowered')
    gun = (scn[4:], v) if scn.startswith('gun_') else None
    text, t_end = cd.deck(scn, deck_power, rng, c, v, 0.0, cfg.get('esd_is', cd.ESD_IS), prot, gun=gun)
    col, opt = cd.spice(text, t_end)
    if col is None:
        return case, {'error': opt}
    r = {'case': [deck_power] + list(case), 'options': opt,
         **cd.metrics(col, col['time'], rng, 0.0, cd.RCP_JACK)}
    r['case'] = (scn, deck_power, rng, c, v, name)
    cls, lims, notes, unr = cd.judge(r)
    t = col['time']
    out = {'class': cls, 'limits': lims[:6]}
    st = {}
    for stage, j in prot['parts']:
        i = col[f'i(vam_{ {"tvs1": "t1", "tvs2": "t2", "sch2": "s2"}[stage] }_{j})']
        vj = col[f'v(jk_{j})' if stage == 'tvs1' else f'v(mid_{j})']
        p = [abs(a * b) for a, b in zip(i, vj)]
        ipk = max(map(abs, i))
        k = max(range(len(i)), key=lambda n: abs(i[n]))
        # pulse width at half peak current
        w = cd.t_above(t, i, ipk / 2)
        st[f'{stage}_{j}'] = {'i_pk': ipk, 'v_at_pk': vj[k], 'p_pk': max(p), 'e_uj': 1e6 * cd.integ(t, p), 'w50_us': 1e6 * w}
    for j in ps.JACKS:
        a = f'rl_{j}'
        b = f'mid_{j}' if j != 'lcur' else f'mid_{j}'
        rr = cfg['r'][j]
        dv = [x - y for x, y in zip(col[f'v({a})'], col[f'v({b})'])]
        st[f'r_{j}'] = {'v_pk': max(map(abs, dv)), 'p_pk': max(d * d / rr for d in dv), 'e_uj': 1e6 * cd.integ(t, [d * d / rr for d in dv])}
        dsw = [x - y for x, y in zip(col[f'v(jk_{j})'], col[f'v(rl_{j})'])]
        if sw == 'closed':
            st[f'iso_{j}'] = {'i_pk': max(abs(d) / cfg['iso']['ron'] for d in dsw)}
        else:
            st[f'iso_{j}'] = {'v_pk': max(map(abs, dsw))}
        st[f'jack_{j}'] = {'v_pk': max(map(abs, col[f'v(jk_{j})']))}
    out['stress'] = st
    out['res'] = {k: (round(x['v_pk'], 2), round(x['p_pk_w'], 3)) for k, x in r['res'].items() if k in ('R105', 'R106', 'R94')}
    out['opamp_in_ma'] = {n: round(o['in_ma'], 2) for n, o in r['opamp'].items()}
    out['opamp_vdiff'] = {n: round(o['vdiff'], 2) for n, o in r['opamp'].items()}
    return case, out

def cases():
    L = []
    for v in (50, -50):
        for scn in cd.SCENARIOS:
            for p, rg in cd.STATES:
                sw = 'closed' if p == 'powered' else 'open'
                L.append(('parts_jackside', scn, p, sw, rg, 1e-6, v))
                if p == 'powered':
                    L.append(('parts_jackside', scn, p, 'open', rg, 1e-6, v))   # brief case (a)
                else:
                    L.append(('jackside_coff2x', scn, p, 'open', rg, 1e-6, v))
            L.append(('parts_jackside', scn, 'unpowered', 'open', '100R', 10e-6, v))
            L.append(('parts_jackside', scn, 'powered', 'closed', '100R', 10e-6, v))
    for kv in (8, -8):
        for j in ps.JACKS:
            for p, rg in (('powered', '100R'), ('powered', '100k'), ('unpowered', '100R'), ('unpowered', '100k')):
                for sw in (('closed', 'open') if p == 'powered' else ('open',)):
                    L.append(('parts_jackside', 'gun_' + j, p, sw, rg, 0.0, kv))
    return L

if __name__ == '__main__':
    cs = cases()
    if len(sys.argv) > 1 and sys.argv[1] == 'count':
        print(len(cs)); sys.exit()
    res = {}
    with cf.ProcessPoolExecutor(int(sys.argv[1]) if len(sys.argv) > 1 else 6) as ex:
        for case, out in ex.map(one, cs):
            res[' '.join(map(str, case))] = out
    pathlib.Path(__file__).with_name('run50.json').write_text(json.dumps(res, indent=1))
    print('done', len(res))
