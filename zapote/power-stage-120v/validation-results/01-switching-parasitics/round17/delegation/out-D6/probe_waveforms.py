#!/usr/bin/env python3
"""Bounded waveform evidence and numerical integration/timestep cross-check."""
from __future__ import annotations
import csv
import gzip
import json
from run_study import HERE, D2, run_d2, sha
from run_ngspice import read_raw, MEAS

def integral(t: list[float], p: list[float], a: float, b: float) -> float:
    total=0.0
    for t0,t1,p0,p1 in zip(t,t[1:],p,p[1:]):
        lo,hi=max(t0,a),min(t1,b)
        if hi<=lo: continue
        pl=p0+(p1-p0)*(lo-t0)/(t1-t0)
        ph=p0+(p1-p0)*(hi-t0)/(t1-t0)
        total+=(hi-lo)*(pl+ph)/2
    return total

def main() -> None:
    out=HERE/'waveforms'
    out.mkdir(exist_ok=True)
    matrix=D2/'legA-h0-lin12-m20corr.matrix.txt'
    rows=[]
    for variant in ('baseline','roff1_cgs2p2n'):
        source=HERE/'decks'/f'{variant}.cir'
        for label,v,i,dt in (('S1',170,37,307),('S4',198,-20,348)):
            for step in ('0.2n','0.1n'):
                tag=f'{variant}_{label}_d0_{step}'
                deck=out/f'{tag}.cir'
                deck.write_text(source.read_text().replace('.end','.save v(xql.ldrd) v(xqh.ldrd)\n.end'))
                params=run_d2.matrix_params(run_d2.read_L(str(matrix)))
                params.update(VBUS=str(v),IL=str(i),DIR='0',LESL='10n',LSHUNT='2n',DT=f'{dt}n',TRMAX=step)
                work=out/tag
                if (work/'result.json').exists():
                    previous=json.loads((work/'result.json').read_text())
                    assert previous['params']==params and previous['deck_sha256']==sha(deck)
                    rows.append(previous)
                    print('REUSE '+tag,flush=True)
                    continue
                if (work/'waves.raw').exists():
                    # Resume analysis of already completed raw run; no solver rerun.
                    measured={}
                    for line in (work/'run.log').read_text().splitlines():
                        match=MEAS.match(line)
                        if match: measured[match.group(1).lower()]=float(match.group(2))
                    assert 'aborted' not in (work/'raw_run.log').read_text().lower()
                    r={'meas':measured,'aborted':False}
                else:
                    r=run_d2.run(deck,params,keep=work,raw=True)
                (work/'IFX_CFD7_650V.lib').unlink(missing_ok=True)
                if r['aborted']: raise RuntimeError(r)
                if step=='0.2n':
                    frozen=json.loads((HERE/'results/corrected'/f'{variant}_{label}_v{v}_i{i}_d0_dt{dt}'/'result.json').read_text())
                    for name in ('vgs_ls_off_max','vds_ls_die_pk','vds_hs_die_pk'):
                        assert r['meas'][name]==frozen['meas'][name], (name,r['meas'][name],frozen['meas'][name])
                w=read_raw(work/'waves.raw')
                t=w['time']
                assert t[-1]>=2e-6+dt*1e-9+0.8e-6-1e-14
                signals={}
                for q in ('l','h'):
                    signals[f'vds_{q}']=[d-s for d,s in zip(w[f'v(xq{q}.dd)'],w[f'v(xq{q}.s)'])]
                    signals[f'vgs_{q}']=[g-s for g,s in zip(w[f'v(xq{q}.g)'],w[f'v(xq{q}.s)'])]
                    signals[f'id_{q}']=[(a-b)/7.44e-5 for a,b in zip(w[f'v(xq{q}.ldrd)'],w[f'v(xq{q}.dd)'])]
                audits={}
                for q in ('l','h'):
                    power=[v*i for v,i in zip(signals[f'vds_{q}'],signals[f'id_{q}'])]
                    for window,a,b in (('off',2e-6,2e-6+dt*1e-9),('on',2e-6+dt*1e-9,2e-6+dt*1e-9+0.75e-6)):
                        for kind,values in (('signed',power),('positive',[max(0,p) for p in power])):
                            name=f'e_{q}_{window}_{kind}'
                            measured=r['meas'][name]
                            replay=integral(t,values,a,b)
                            absolute=integral(t,[abs(p) for p in power],a,b)
                            scale=absolute if kind=='signed' else abs(measured)
                            audits[name]={'meas_J':measured,'csv_integral_J':replay,'delta_J':replay-measured,
                                          'absolute_integral_J':absolute,'relative_to_audit_scale':abs(replay-measured)/max(scale,1e-12)}
                            assert abs(replay-measured)<max(scale*1e-3,1e-9),(name,measured,replay,scale)
                with gzip.open(work/'transition.csv.gz','wt') as f:
                    writer=csv.writer(f)
                    writer.writerow(['time_s',*signals])
                    for k,time in enumerate(t):
                        if time>=2e-6: writer.writerow([f'{time:.12g}',*[f'{values[k]:.12g}' for values in signals.values()]])
                (work/'waves.raw').unlink()
                (work/deck.name).unlink()
                (work/'.spiceinit').unlink()
                row={'tag':tag,'params':params,'meas':r['meas'],'aborted':r['aborted'],
                     'deck_sha256':sha(deck),'waveform_sha256':sha(work/'transition.csv.gz'),
                     'script_sha256':sha(__import__('pathlib').Path(__file__)),
                     'ls_terminal_vs_die_current_max_delta_A':max(abs(a-b) for a,b in zip(w['i(vids)'],signals['id_l'])),
                     'integration_audit':audits}
                (work/'result.json').write_text(json.dumps(row,indent=2)+'\n')
                rows.append(row)
                print(tag,r['meas']['vgs_ls_off_max'],r['meas']['vds_ls_die_pk'],flush=True)
    refinements=[]
    for a,b in zip(rows[::2],rows[1::2]):
        changes={k:(b['meas'][k]-a['meas'][k]) for k in ('vgs_ls_off_max','vds_ls_die_pk','vds_hs_die_pk')}
        refinements.append({'tag':a['tag'],'fine_minus_coarse':changes})
    (out/'audit.json').write_text(json.dumps(refinements,indent=2)+'\n')

if __name__=='__main__':main()
