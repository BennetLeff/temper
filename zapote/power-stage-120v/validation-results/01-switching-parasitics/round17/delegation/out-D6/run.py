#!/usr/bin/env python3
"""D6 evidence: ngspice-only variants; no production sources modified."""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
D2 = HERE.parents[1] / 'd2'
sys.path.insert(0, str(D2))
import run_d2

VARIANTS = {'baseline': (None, 0, 0), 'off1': (1, 0, 0), 'off2': (2, 0, 0),
            'c1': (None, 1, 0), 'c2p2': (None, 2.2, 0), 'c4p7': (None, 4.7, 0),
            'neg2': (None, 0, -2), 'neg4': (None, 0, -4),
            'off1_neg2': (1, 0, -2), 'off1_neg4': (1, 0, -4)}
MATRICES = {'lin': 'legA-h0-lin12-m20corr.matrix.txt',
            'quad': 'legA-h0-quad05-m20corr.matrix.txt',
            'v2': 'legA-h0-lin12.matrix.txt'}
CASES = [(s, v, il, d, dt) for s, v, il, dt in
         [('S1', v, 37, dt) for v in (170,198,280) for dt in (307,348)] +
         [('S2',280,71,348),('S4',198,-20,348)] for d in (0,1)]


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def deck(name: str) -> Path:
    off, cap, neg = VARIANTS[name]
    text = (D2 / 'leg_matrix.cir').read_text()
    extra = [f'* D6 {name}: generic proposed remedy; no layout added.']
    if off:
        # Preserve original Rg_on. Parallel discharge-only branch is selected
        # so Rg || Rbranch tends to target Roff at high current. Finite diode
        # drop means effective resistance is higher at low gate current.
        rb = 1 / (1 / off - 1 / 3.9)
        extra += ['.model D6D D(Is=1u N=1 Rs=0.05 Cjo=20p Tt=0)']
        for side in ('l','h'):
            extra += [f'Doff{side} gd{side}3 off{side} D6D', f'Roff{side} off{side} gd{side} {rb:.12g}']
    if cap:
        extra += [f'Cgsl g_ls s_ls {cap}n', f'Cgsh g_hs sw {cap}n']
    if neg:
        for side, ref in [('l','s_ls'),('h','sw')]:
            old = f'v(gd{side},{ref})*(1-v(g{side}_cmd,{ref})/VDRV)/ROL'
            new = f'(v(gd{side},{ref})-({neg}))*(1-v(g{side}_cmd,{ref})/VDRV)/ROL'
            assert old in text
            text = text.replace(old,new)
    # Positive die VDS*drain-current overlap; internal drain R carries die
    # terminal current (channel + Coss + diode), not isolated channel heat.
    for side in ('l','h'):
        q = f'xq{side}'
        power = f'max(0,(v({q}.dd)-v({q}.s))*(v({q}.ldrd)-v({q}.dd))/7.44e-5)'
        for label, lo, hi in [('pre','T1','T1+DT'),('post','T1+DT','T1+DT+0.75u')]:
            extra += [f".meas tran e_{side}_{label} INTEG par('{power}') from={{{lo}}} to={{{hi}}}"]
    text = text.replace('.end\n','\n'.join(extra)+'\n.end\n')
    p = HERE / 'decks' / f'{name}.cir'
    p.parent.mkdir(exist_ok=True)
    p.write_text(text)
    return p


def one(job: tuple) -> dict:
    matrix, name, case, step = job
    s,v,il,d,dt = case
    tag = f'{matrix}_{name}_{s}_v{v}_i{il}_d{d}_dt{dt}_step{step}'
    output = HERE / 'raw' / tag
    p = run_d2.matrix_params(run_d2.read_L(str(D2 / MATRICES[matrix])))
    p.update(VBUS=str(v),IL=str(il),DIR=str(d),DT=f'{dt}n',LESL='10n',LSHUNT='2n',TRMAX=f'{step}n')
    r = run_d2.run(HERE / 'decks' / f'{name}.cir',p,keep=output)
    # Licensed model copies from unchanged kit runner are never retained.
    (output / 'IFX_CFD7_650V.lib').unlink(missing_ok=True)
    (output / f'{name}.cir').unlink(missing_ok=True)  # canonical committed deck above
    m = r['meas']
    off, inc = ('ls','hs') if d == 0 else ('hs','ls')
    required = [f'vgs_{off}_off_max', 'vds_ls_die_pk', 'vds_hs_die_pk', f'vds_{inc}_at_on'] + [f'e_{side}_{part}' for side in ('l','h') for part in ('pre','post')]
    if r['aborted'] or r['failed'] or r['returncode'] != 0 or not all(k in m for k in required):
        row = {'matrix':matrix,'variant':name,'case':s,'vbus':v,'il':il,'dir':d,'dt':dt,'step_ns':step,
               'aborted':True,'returncode':r['returncode'],'params':p,'meas':m,'failed':r['failed'],
               'log_tail':r['log_tail']}
        (output/'result.json').write_text(json.dumps(row,indent=2)+'\n')
        print(f'{tag}: FAILED (retained; no verdict)',flush=True)
        return row
    row = {'matrix':matrix,'variant':name,'case':s,'vbus':v,'il':il,'dir':d,'dt':dt,'step_ns':step,
           'off_V':m[f'vgs_{off}_off_max'],'vds_V':max(m['vds_ls_die_pk'],m['vds_hs_die_pk']),
           'incoming_V':m[f'vds_{inc}_at_on'],'zvs':m[f'vds_{inc}_at_on'] <= .05*v,
           'off_uJ':m[f'e_{off[0]}_pre']*1e6,'on_uJ':m[f'e_{inc[0]}_post']*1e6,
           'total_uJ':sum(m[f'e_{side}_{part}'] for side in ('l','h') for part in ('pre','post'))*1e6,
           'meas':m,'params':p,'aborted':r['aborted'],'returncode':r['returncode']}
    (output/'result.json').write_text(json.dumps(row,indent=2)+'\n')
    print(f'{tag}: off={row["off_V"]:.4f} V vds={row["vds_V"]:.2f} V E={row["total_uJ"]:.3f} uJ',flush=True)
    return row


def main() -> None:
    ap=argparse.ArgumentParser()
    ap.add_argument('--variants',default=','.join(VARIANTS))
    ap.add_argument('--matrices',default='lin,quad')
    ap.add_argument('--workers',type=int,default=4)
    ap.add_argument('--limit',type=int)
    ap.add_argument('--step',type=float,default=.2)
    args=ap.parse_args()
    for name in args.variants.split(','): deck(name)
    jobs=[(mat,n,c,args.step) for mat in args.matrices.split(',') for n in args.variants.split(',') for c in CASES]
    if args.limit: jobs=jobs[:args.limit]
    inputs=[Path(__file__), D2/'leg_matrix.cir',D2/'run_d2.py',run_d2.KIT/'common/run_ngspice.py',run_d2.KIT/'common/options.inc',run_d2.KIT/'models/vendor/IFX_CFD7_650V.lib']+[D2/f for f in MATRICES.values()]
    provenance={'source_revision':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
                'python':sys.version,'ngspice':subprocess.check_output(['ngspice','--version'],text=True),
                'inputs':{str(p.relative_to(HERE.parents[7])) if p.is_relative_to(HERE.parents[7]) else str(p):sha(p) for p in inputs},
                'decks':{n:sha(HERE/'decks'/f'{n}.cir') for n in args.variants.split(',')},'argv':sys.argv}
    key='_'.join(args.matrices.split(','))+'_'+ '_'.join(args.variants.split(','))+f'_step{args.step}'
    (HERE/f'provenance-{key}.json').write_text(json.dumps(provenance,indent=2)+'\n')
    with ThreadPoolExecutor(args.workers) as pool: rows=list(pool.map(one,jobs))
    (HERE/f'results-{key}.json').write_text(json.dumps(rows,indent=2)+'\n')

if __name__ == '__main__': main()
