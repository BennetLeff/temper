"""Bounded D26 fixtures and native-19 comparisons; all writes stay HERE.

No vendor model is copied to tracked runs. Raw solver stdout and compressed
full-precision wrdata output are retained for independent remeasurement.
"""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor, as_completed
import argparse
import gzip
import hashlib
import itertools
import json
import re
import subprocess
import sys
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
R17 = HERE.parents[1]
D2 = R17 / 'd2'
KIT = HERE.parents[4] / 'validation-plan/sim-kit'
sys.path.insert(0, str(D2))
sys.path.insert(0, str(KIT / 'common'))
import run_d2

NG = '/opt/homebrew/bin/ngspice'
LIB = HERE / 'vendor/IFX_CFD7_650V.lib'
SHA = '02ac6634f47c25be04e8de3c6eec4ec8cf403b659001b7f176c8f98bb6e9ce3b'


def dump(path: Path, obj: object) -> None:
    path.write_text(json.dumps(obj, indent=2, allow_nan=False) + '\n')


def execute(tag: str, text: str, stop: float) -> tuple[dict, np.ndarray | None]:
    work = HERE / 'runs' / tag
    work.mkdir(parents=True, exist_ok=True)
    text = text.replace('.include IFX_CFD7_650V.lib', f'.include "{LIB}"')
    text = text.replace('.include ../common/options.inc', f'.include "{KIT / "common/options.inc"}"')
    text = text.replace('.include ucc21550_parametric.lib', f'.include "{HERE / "ucc21550_parametric.lib"}"')
    (work / 'deck.cir').write_text(text)
    (work / '.spiceinit').write_text('set ngbehavior=psa\n')
    status = {'tag': tag, 'status': 'INDETERMINATE', 'timeout_s': 90}
    try:
        p = subprocess.run([NG, '-b', 'deck.cir'], cwd=work, capture_output=True, text=True, timeout=90)
        log = p.stdout + p.stderr
        status['returncode'] = p.returncode
    except subprocess.TimeoutExpired as exc:
        log = (exc.stdout or b'').decode() + (exc.stderr or b'').decode() + '\nPROCESS TIMEOUT\n'
        status['returncode'] = None
    (work / 'run.log').write_text(log)
    data = None
    if (work / 'wave.txt').exists():
        raw = (work / 'wave.txt').read_bytes()
        try:
            data = np.loadtxt(work / 'wave.txt', skiprows=1)
            status['last_time_s'] = float(data[-1, 0])
            if status['returncode'] == 0 and data[-1, 0] >= stop * (1-1e-7) and np.isfinite(data).all() and not re.search(r'Timestep too small|simulation\(s\) aborted|fatal error', log, re.I):
                status['status'] = 'COMPLETED'
        except (ValueError, IndexError):
            status['wave_error'] = 'Malformed or missing finite waveform'
        (work / 'wave.txt.gz').write_bytes(gzip.compress(raw, mtime=0))
        (work / 'wave.txt').unlink()
    dump(work / 'status.json', status)
    return status, data


def cross(t: np.ndarray, y: np.ndarray, level: float, rising: bool, after: float=0) -> float | None:
    mask = (y[:-1] < level) & (y[1:] >= level) if rising else (y[:-1] > level) & (y[1:] <= level)
    idx = np.flatnonzero(mask & (t[:-1] >= after))
    if not len(idx):
        return None
    i = idx[0]
    return float(t[i] + (level-y[i])*(t[i+1]-t[i])/(y[i+1]-y[i]))


def ns_delta(a: float | None, b: float | None) -> float | None:
    return None if a is None or b is None else (a-b)*1e9


def control(vectors: str) -> str:
    return f'.control\nset numdgt=15\nset wr_singlescale\nset wr_vecnames\nrun\nwrdata wave.txt {vectors}\nquit\n.endc\n.end\n'


def fixture() -> None:
    rows = []
    # Loaded/unloaded, both channels and edges; input period is 2us and
    # pulse 100ns for propagation. DT disabled for this characterization.
    specs = []
    for c, cap in itertools.product([-1, 0, 1], [0, 1.8]):
        specs.append((f'prop-c{c}-cl{cap}', c, cap, 50000, 0, 200, 100, 0))
    for c, r, gap in itertools.product([-1,0,1], [20000,50000], [0,200,600]):
        specs.append((f'dt-c{c}-r{r}-gap{gap}', c, 0, r, 1, gap, 500, 0))
    specs += [(f'pulse-{w}',0,0,50000,0,200,w,0) for w in [3,6,11,13,31]]
    specs += [('disable',0,0,50000,0,200,2000,1)]
    for tag,c,cap,r,dten,gap,pw,dis in specs:
        # A falls at 1us+1ns+PW; B rises GAP after A falling threshold
        text = f'''* {tag}: datasheet SLUSE89C fixture
.include ucc21550_parametric.lib
Vcc vc 0 3.3
Vdd vd 0 12
Va a 0 PULSE(0 3.3 1u 1n 1n {pw}n 2u)
Vb b 0 PULSE(0 3.3 {1001+pw+gap}n 1n 1n {100 if tag.startswith('prop') else 500}n {2 if tag.startswith('prop') else 4}u)
Vdis dis 0 PULSE(0 {3.3*dis} 1.7u 1n 1n 2u 5u)
XU a b dis vc 0 vd 0 oa vd 0 ob UCC21550 CORNER={c} RDT={r} RTOL=0 DTEN={dten}
Ca oa 0 {max(cap,0.000001)}n
Cb ob 0 {max(cap,0.000001)}n
.tran 0.1n 2.8u
'''+control('v(a) v(b) v(dis) v(oa) v(ob)')
        status,w = execute('fixture-'+tag,text,2.8e-6)
        row = dict(status, corner=c, cap_nF=cap, rdt_ohm=r, gap_ns=gap, pulse_ns=pw)
        if status['status']=='COMPLETED' and w is not None:
            t,a,b,d,oa,ob = w.T
            row.update(tpd_lh_ns=ns_delta(cross(t,oa,1.2,True),cross(t,a,2,True)),
                       tpd_hl_ns=ns_delta(cross(t,oa,10.8,False),cross(t,a,1,False)),
                       rise_ns=ns_delta(cross(t,oa,9.6,True),cross(t,oa,2.4,True)),
                       fall_ns=ns_delta(cross(t,oa,1.2,False),cross(t,oa,10.8,False)),
                       dt_ns=ns_delta(cross(t,ob,1.2,True),cross(t,oa,10.8,False)),
                       dis_ns=ns_delta(cross(t,oa,10.8,False,1.7e-6),cross(t,d,2,True)),
                       pulse_passed=bool(oa.max()>6))
        rows.append(row)
        print(tag, row.get('tpd_lh_ns'), row.get('dt_ns'), flush=True)
    dump(HERE/'fixtures.json', rows)


def build_deck(model: bool) -> str:
    text = (D2/'leg_matrix.cir').read_text()
    if model:
        text=text.replace('.param GL0=', '.include ucc21550_parametric.lib\n.param CORNER=0 SK=0 PWDS=0 PDOV=0 PWOV=0\n.param GL0=',1)
        # params must precede defaults? move extra defaults before params.inc
        text=text.replace('.param CORNER=0 SK=0 PWDS=0 PDOV=0 PWOV=0\n','')
        text=text.replace('.include params.inc','.param CORNER=0 SK=0 PWDS=0 PDOV=0 PWOV=0\n.include params.inc')
        start=text.index('Vgl_cmd')
        end=text.index('* ---- FEM couplings')
        text=text[:start]+'''Vcc vc 0 3.3
Vh vdh sw {VDRV}
Vl vdl s_ls {VDRV}
Vina ina 0 PULSE({3.3*DIR} {3.3*(1-DIR)} {T1+(1-DIR)*200n} 1n 1n 10u 20u)
Vinb inb 0 PULSE({3.3*(1-DIR)} {3.3*DIR} {T1+DIR*200n} 1n 1n 10u 20u)
XU ina inb 0 vc 0 vdh sw gdh vdl s_ls gdl UCC21550 CORNER={CORNER} SKEW={SK} PWD={PWDS} PDOV={PDOV} PWOV={PWOV}
Rgl gdl gdl3 {RG}
L_P4 g_ls gdl3 {LP4}
Rholdl g_ls s_ls 10k
Rgh gdh gdh3 {RG}
L_P3 g_hs gdh3 {LP3}
Rholdh g_hs sw 10k
'''+text[end:]
    text=text[:text.index('.tran')]
    return text+ '.tran {TRMAX} 3.5u 0 {TRMAX}\n'+control('v(xql.g,xql.s) v(xqh.g,xqh.s) v(xql.dd,xql.s) v(xqh.dd,xqh.s) v(gdl,s_ls) v(gdh,sw)')


def decision(mode: str) -> None:
    if hashlib.sha256(LIB.read_bytes()).hexdigest()!=SHA:
        raise ValueError('Licensed MOSFET model hash mismatch')
    base = run_d2.matrix_params(run_d2.read_L(str(D2/'legA-h0-best-n19.matrix.txt')))
    rows=[]
    result_path=HERE/f'{mode}.json'
    cached={r['tag']:r for r in json.loads(result_path.read_text())} if result_path.exists() else {}
    # Three decision points, both directions, both ESL values. Their exact
    # native19-carryover rows are the baseline comparison authority.
    cases=[('S1',170,37),('S2',280,71),('S4',198,-20)]
    variants = [('base'+str(dt),None,dt,0,0) for dt in [391,443,498]] if mode=='baseline' else [(name,c,443,sk,pwd) for name,c,sk,pwd in [('min',-1,0,0),('typ',0,0,0),('max',1,0,0)]]
    if mode=='stress':
        # Independent cold skew ±6.5ns and PWD ±5ns, center35.5ns.
        # Four channel/edge delays stay26.5..44.5ns. DT independently min/max.
        # Pulse filter remains12ns: its process correlation is unspecified.
        variants=[(f'dtc{c}-sk{sk}-pwd{pwd}',c,443,sk,pwd) for c,sk,pwd in itertools.product([-1,1],[-6.5,6.5],[-5,5])]
    jobs=list(itertools.product(cases,[0,1],[1.06,10],variants))
    def work(job):
        (s,v,i),direction,esl,variant=job
        name,c,dt,sk,pwd=variant
        tag=f'{mode}-{s}-v{v}-i{i}-d{direction}-e{esl}-{name}'
        p=dict(base,VBUS=str(v),IL=str(i),DIR=str(direction),DT=f'{dt}n',LESL=f'{esl}n',TRMAX='0.2n')
        if c is not None:
            p.update(CORNER=str(c),SK=f'{sk}n',PWDS=f'{pwd}n')
            if mode=='stress':
                p.update(PDOV='35.5n',PWOV='12n')
        text=build_deck(c is not None).replace('.include params.inc','\n'.join(f'.param {k}={val}' for k,val in p.items()))
        identity = {
            'rendered_deck_sha256': hashlib.sha256(text.encode()).hexdigest(),
            'model_sha256': hashlib.sha256((HERE/'ucc21550_parametric.lib').read_bytes()).hexdigest(),
            'vendor_sha256': hashlib.sha256(LIB.read_bytes()).hexdigest(),
            'matrix_sha256': hashlib.sha256((D2/'legA-h0-best-n19.matrix.txt').read_bytes()).hexdigest(),
            'runner_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'options_sha256': hashlib.sha256((KIT/'common/options.inc').read_bytes()).hexdigest(),
            'ngspice_binary_sha256': hashlib.sha256(Path(NG).resolve().read_bytes()).hexdigest(),
        }
        if tag in cached and cached[tag].get('execution_identity') == identity:
            return cached[tag]
        if (HERE/'runs'/tag/'status.json').exists():
            prior=HERE/'runs'/tag
            suffix=hashlib.sha256((prior/'deck.cir').read_bytes()).hexdigest()[:12]
            archive=prior.with_name('previous-'+tag+'-'+suffix)
            if archive.exists():
                raise RuntimeError(f'Archive collision; preserve both before rerunning {tag}')
            prior.rename(archive)
        status,w=execute(tag,text,3.5e-6)
        row=dict(status,case=s,vbus=v,il=i,direction=direction,esl_nH=esl,variant=name,params=p,execution_identity=identity)
        if status['status']=='COMPLETED' and w is not None:
            t,gl,gh,dl,dh,ol,oh=w.T
            outgoing,incoming=(gl,gh) if direction==0 else (gh,gl)
            vo,vi=(ol,oh) if direction==0 else (oh,ol)
            vd=dh if direction==0 else dl
            on=cross(t,vi,1.5,True,2e-6)
            off=cross(t,vo,13.5,False,2e-6)
            row['driver_dt_ns']=ns_delta(on,off)
            for threshold in [1.9,3.0,7.5]:
                rise=cross(t,incoming,threshold,True,2e-6)
                fall=cross(t,outgoing,threshold,False,2e-6)
                row[f'gate_dt_{threshold}_ns']=ns_delta(rise,fall)
                mask=(t[:-1]>=2e-6)&(t[:-1]<=3.193e-6)
                count=lambda y: int(np.count_nonzero(mask & ((y[:-1]-threshold)*(y[1:]-threshold)<0)))
                row[f'crossing_counts_{threshold}']={'incoming':count(incoming),'outgoing':count(outgoing)}
                if rise is not None and fall is not None:
                    gapmask=(t>=fall)&(t<=rise)
                    row[f'gap_overlap_{threshold}']=bool(np.any((outgoing[gapmask]>=threshold)&(incoming[gapmask]>=threshold)))
            if on is not None:
                window=(t>=on)&(t<=3.193e-6)
                row['off_gate_peak_V']=float(outgoing[window].max())
                row['vds_at_driver_on_V']=float(np.interp(on,t,vd))
                row['zvs']=row['vds_at_driver_on_V']<=0.05*v
            window=(t>=2e-6)&(t<=3.193e-6)
            row['vds_peak_V']=float(max(dl[window].max(),dh[window].max()))
            row['pass_3V']=row['off_gate_peak_V']<3
            row['pass_1p9V']=row['off_gate_peak_V']<1.9
            row['pass_520V']=row['vds_peak_V']<=520
            if mode=='baseline':
                ref=json.loads((D2/f'results/native19-carryover/cases/{s}_v{v}_i{i}_d{direction}_dt{dt}_esl{esl}.json').read_text())
                window=(t>=2e-6)&(t<=2e-6+dt*1e-9+0.75e-6)
                offwindow=(t>=2e-6+dt*1e-9)&(t<=2e-6+dt*1e-9+0.75e-6)
                observed={'vds_pk':float(max(dl[window].max(),dh[window].max())), 'vgs_off_max':float(outgoing[offwindow].max()),'vds_incoming_at_on':float(np.interp(2e-6+dt*1e-9,t,vd))}
                row['reference']=ref
                row['baseline_observed']=observed
                row['baseline_delta']={k:observed[k]-ref[k] for k in observed}
                row['baseline_reproduced']=all(abs(observed[k]-ref[k])<=0.01*max(1,abs(ref[k])) for k in observed)
        return row
    with ThreadPoolExecutor(max_workers=4 if mode=='model' else 2) as pool:
        for future in as_completed([pool.submit(work,job) for job in jobs]):
            row=future.result()
            rows.append(row)
            rows.sort(key=lambda r:r['tag'])
            dump(result_path,rows)
            print(row['tag'],row['status'],row.get('gate_dt_3.0_ns'),row.get('off_gate_peak_V'),flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser()
    ap.add_argument('mode', choices=['fixtures','baseline','model','stress'])
    args=ap.parse_args()
    if args.mode=='fixtures': fixture()
    else: decision(args.mode)
