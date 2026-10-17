"""Reconstruct report from retained solver evidence; do not invent missing runs."""
from __future__ import annotations
import ast
import gzip
import hashlib
import io
import json
import subprocess
from pathlib import Path
import numpy as np
from run import HERE, D2, KIT, LIB, SHA, build_deck, cross, ns_delta, dump


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def wave(tag: str) -> np.ndarray:
    return np.loadtxt(io.BytesIO(gzip.decompress((HERE/'runs'/tag/'wave.txt.gz').read_bytes())),skiprows=1)


def fmt(value: object) -> str:
    return '—' if value is None else f'{value:.3f}' if isinstance(value,float) else str(value)


def extra_fixture_outcome(r: dict) -> tuple[str, str]:
    targets={
        'dis':{-1:(27,27),0:(48,48),1:(80,80)},
        'vcc':{-1:(500,18000),0:(1200,42000),1:(7000,80000)},
        'vdd':{-1:(100,10000),0:(500,10000),1:(2000,10000)},
    }
    if r['status']!='COMPLETED':
        outcome='INDETERMINATE'
        target='parameter ledger'
    elif r['what']=='overlap':
        outcome='PASS' if r.get('other_output_peak_V') is not None and abs(r['other_output_peak_V'])<0.01 and r.get('disable_ns') is not None else 'FAIL'
        target='both-high: B remains low; A falls'
    else:
        off,on=targets[r['what']][r['corner']]
        target=f'{off} /{on}ns'
        values=(r.get('disable_ns'),r.get('reenable_ns'))
        outcome='PASS' if all(v is not None and abs(v-e)<=.2 for v,e in zip(values,(off,on))) else 'FAIL'
    return outcome, target


def main() -> None:
    groups={m:json.loads((HERE/f'{m}.json').read_text()) for m in ['baseline','model','stress']}
    checks={}
    postrun=[]
    audited=[]
    for mode,rows in groups.items():
        for r in rows:
            work=HERE/'runs'/r['tag']
            params='\n'.join(f'.param {k}={v}' for k,v in r['params'].items())
            rendered=build_deck(mode!='baseline').replace('.include params.inc',params)
            rendered=rendered.replace('.include IFX_CFD7_650V.lib',f'.include "{LIB}"')
            rendered=rendered.replace('.include ../common/options.inc',f'.include "{KIT/"common/options.inc"}"')
            rendered=rendered.replace('.include ucc21550_parametric.lib',f'.include "{HERE/"ucc21550_parametric.lib"}"')
            identical=rendered==(work/'deck.cir').read_text()
            postrun.append({'tag':r['tag'],'saved_deck_sha256':sha(work/'deck.cir'),'final_renderer_matches_saved_deck':identical,
                            'model_sha256':sha(HERE/'ucc21550_parametric.lib'),'vendor_sha256':sha(LIB),
                            'identity_capture':'post-run reconstructed; execution-time runner hash unavailable for this first campaign'})
            log=(work/'run.log').read_text()
            if r['status']!='COMPLETED':
                r['failure_kind']='TIMEOUT' if 'PROCESS TIMEOUT' in log else 'NUMERICAL_ABORT' if 'Timestep too small' in log or 'simulation(s) aborted' in log else 'INCOMPLETE'
                continue
            w=wave(r['tag']);t,gl,gh,dl,dh,ol,oh=w.T
            outgoing,incoming=(gl,gh) if r['direction']==0 else (gh,gl)
            vo,vi=(ol,oh) if r['direction']==0 else (oh,ol)
            on=cross(t,vi,1.5,True,2e-6)
            window=(t>=2e-6)
            offmask=t>=on
            audit={'tag':r['tag'],'full_tail_vds_V':float(max(dl[window].max(),dh[window].max())),
                   'full_tail_off_gate_V':float(outgoing[offmask].max()),'crossings':{}}
            for threshold in [1.9,3.,7.5]:
                count=lambda y:int(np.count_nonzero((t[:-1]>=2e-6)&((y[:-1]-threshold)*(y[1:]-threshold)<0)))
                audit['crossings'][str(threshold)]={'incoming':count(incoming),'outgoing':count(outgoing)}
            audit['tail_additional_vds_V']=audit['full_tail_vds_V']-r['vds_peak_V']
            audit['tail_additional_off_gate_V']=audit['full_tail_off_gate_V']-r['off_gate_peak_V']
            audited.append(audit)
    checks['baseline_count']=len(groups['baseline'])
    checks['baseline_reproduced']=sum(r.get('baseline_reproduced',False) for r in groups['baseline'])
    checks['required_model_attempts']=len(groups['model'])
    checks['model_completed']=sum(r['status']=='COMPLETED' for r in groups['model'])
    checks['saved_decks_equal_final_renderer']=all(r['final_renderer_matches_saved_deck'] for r in postrun)
    checks['vendor_hash_matches']=sha(LIB)==SHA
    checks['no_higher_tail_peaks']=all(r['tail_additional_vds_V']<1e-6 and r['tail_additional_off_gate_V']<1e-6 for r in audited)
    checks['all_python_syntax_valid']=True
    for f in HERE.glob('*.py'): ast.parse(f.read_text(),filename=str(f))
    # --no-index respects the final output-directory overrides; return1 means
    # no ignored path matched, return0 is a verification failure.
    samples=[HERE/'runs'/groups['baseline'][0]['tag']/'run.log',HERE/'runs'/groups['baseline'][0]['tag']/'wave.txt.gz']
    ignored=subprocess.run(['git','check-ignore','--no-index',*[str(p) for p in samples]],cwd=HERE,capture_output=True,text=True)
    checks['logs_and_waves_not_ignored']=ignored.returncode==1
    checks['base_commit']=subprocess.check_output(['git','rev-parse','HEAD'],cwd=HERE,text=True).strip()
    checks['completed']=checks['baseline_count']==36 and checks['baseline_reproduced']==36 and checks['required_model_attempts']==36 and checks['vendor_hash_matches'] and checks['logs_and_waves_not_ignored'] and checks['saved_decks_equal_final_renderer'] and checks['no_higher_tail_peaks'] and checks['all_python_syntax_valid']
    dump(HERE/'verification.json',checks)
    dump(HERE/'waveform-audit.json',audited)
    dump(HERE/'provenance.json',{'identity_capture':'post-run; see README limitations','base':checks['base_commit'],
        'runtime':subprocess.check_output(['/opt/homebrew/bin/ngspice','--version'],text=True),
        'source_hashes':{p.name:sha(p) for p in HERE.iterdir() if p.suffix in ['.py','.lib']},
        'matrix':sha(D2/'legA-h0-best-n19.matrix.txt'),'original_deck':sha(D2/'leg_matrix.cir'),
        'options':sha(KIT/'common/options.inc'),'runs':postrun})
    lines=['# Decision-case results','', 'Completed rows are conditional simulations with an unqualified output-stage surrogate. Gate timing columns use first die-VGS crossings; `waveform-audit.json` retains full-tail crossing counts. Numerical aborts are not passes.', '', '| Campaign / case | State | Driver DT ns | Gate DT1.9 /3 /7.5V ns | Off gate V | Die VDS V | ZVS | 3V /1.9V /520V screens |','|---|---|---:|---|---:|---:|---|---|']
    for mode,rows in groups.items():
        for r in rows:
            state=r['status'] if r['status']=='COMPLETED' else r.get('failure_kind','INDETERMINATE')
            timing=' / '.join(fmt(r.get(f'gate_dt_{k}_ns')) for k in ['1.9','3.0','7.5'])
            screens=' / '.join('PASS' if r.get(k) else 'FAIL' for k in ['pass_3V','pass_1p9V','pass_520V']) if state=='COMPLETED' else '—'
            lines.append(f"| {r['tag']} | {state} | {fmt(r.get('driver_dt_ns'))} | {timing} | {fmt(r.get('off_gate_peak_V'))} | {fmt(r.get('vds_peak_V'))} | {r.get('zvs','—')} | {screens} |")
    (HERE/'CASES.md').write_text('\n'.join(lines)+'\n')
    summary=['# Numerical summary','',f"Baseline: **{checks['baseline_reproduced']}/36 reproduced** selected native19-carryover rows (≤1% relative with1V floor). Required driver cases: **{checks['model_completed']}/{len(groups['model'])} completed**; all others indeterminate. Optional stress: {sum(r['status']=='COMPLETED' for r in groups['stress'])}/{len(groups['stress'])} completed attempted samples.", '', '| Required case | Completed /12 | Off gate range V | Die VDS range V | 3V threshold deadtime ns | ZVS passes | Hot/VDS screen passes |','|---|---:|---|---|---|---:|---:|']
    for case in ['S1','S2','S4']:
        rows=[r for r in groups['model'] if r['case']==case and r['status']=='COMPLETED']
        span=lambda k:'—' if not rows else f"{min(r[k] for r in rows):.3f}…{max(r[k] for r in rows):.3f}"
        summary.append(f"| {case} | {len(rows)}/12 | {span('off_gate_peak_V')} | {span('vds_peak_V')} | {span('gate_dt_3.0_ns')} | {sum(r['zvs'] for r in rows)} | {sum(r['pass_1p9V'] and r['pass_520V'] for r in rows)} |")
    delta={k:max(abs(r['baseline_delta'][k]) for r in groups['baseline']) for k in ['vds_pk','vgs_off_max','vds_incoming_at_on']}
    summary += ['',f"Maximum absolute baseline discrepancies: VDS peak{delta['vds_pk']:.6g}V; off-gate{delta['vgs_off_max']:.6g}V; incoming command-time VDS{delta['vds_incoming_at_on']:.6g}V.", '', f"Full-tail audit to3.5µs: no higher peaks beyond3.193µs = **{checks['no_higher_tail_peaks']}**.", '', 'These ranges cover completed samples only and are not bounds. See CASES.md for every aborted combination. No circuit decision is changed on this evidence.']
    (HERE/'SUMMARY.md').write_text('\n'.join(summary)+'\n')
    fixtures=json.loads((HERE/'fixtures.json').read_text())
    fs=['# Fixture comparison','', 'Timing tolerance:±0.2ns propagation/DIS,±0.5ns DT; loaded-edge/current tolerance:±20% of typical. These are model comparison tolerances, not TI production guarantees.', '', '| Fixture | Measured | Target | Outcome |','|---|---|---|---|']
    measured=[]
    for r in fixtures:
        if r['status']!='COMPLETED': fs.append(f"|{r['tag']}|INDETERMINATE|—|FAIL|");continue
        w=wave(r['tag']);t,a,b,d,oa,ob=w.T
        if 'prop' in r['tag']:
            if r['cap_nF']==0:
                target={-1:26,0:33,1:45}[r['corner']]
                for channel,inp,out in [('A',a,oa),('B',b,ob)]:
                    up=ns_delta(cross(t,out,1.2,True),cross(t,inp,2,True));down=ns_delta(cross(t,out,10.8,False),cross(t,inp,1,False))
                    ok=up is not None and down is not None and max(abs(up-target),abs(down-target))<=.2
                    fs.append(f"|{r['tag']} channel{channel} rise/fall|{fmt(up)} /{fmt(down)}ns|{target}ns|{'PASS' if ok else 'FAIL'}|")
                    measured.append({'tag':r['tag'],'channel':channel,'rise_ns':up,'fall_ns':down,'pass':ok})
            else:
                ok=max(abs(r['rise_ns']-8),abs(r['fall_ns']-8))<=1.6
                fs.append(f"|{r['tag']} loaded rise/fall|{r['rise_ns']:.3f} /{r['fall_ns']:.3f}ns|8 /8ns typical|{'PASS' if ok else 'FAIL'}|")
        elif 'dt-' in r['tag']:
            table={20000:{-1:167,0:185,1:203},50000:{-1:399,0:443,1:487}}
            target=max(r['gap_ns'],table[r['rdt_ohm']][r['corner']]);value=r['dt_ns']
            fs.append(f"|{r['tag']}|{value:.3f}ns|{target}ns|{'PASS' if abs(value-target)<.5 else 'FAIL'}|")
        elif 'pulse' in r['tag']:
            width=ns_delta(cross(t,a,1,False),cross(t,a,2,True))
            fs.append(f"|{r['tag']} (threshold width{width:.3f}ns)|{'passed' if r['pulse_passed'] else 'rejected'}|12ns typical filter|characterization|")
    for r in json.loads((HERE/'extra-fixtures.json').read_text()):
        outcome,target=extra_fixture_outcome(r)
        fs.append(f"|{r['tag']} off/on response|{fmt(r.get('disable_ns'))} /{fmt(r.get('reenable_ns'))}ns|{target}|{outcome}|")
    for r in json.loads((HERE/'output-fixtures.json').read_text()):
        if r['status']!='COMPLETED':
            fs.append(f"|{r['tag']}|INDETERMINATE|parameter ledger|INDETERMINATE|")
        elif r['fixture']=='dc':
            passed=abs(r['ROH_ohm']/5-1)<=.2 and abs(r['ROL_ohm']/.55-1)<=.2
            fs.append(f"|DC source/sink R|{r['ROH_ohm']:.3f} /{r['ROL_ohm']:.3f}Ω|5 /0.55Ω typical|{'PASS' if passed else 'FAIL'}|")
        else:
            passed=abs(r['source_peak_A']/4-1)<=.2 and abs(r['sink_peak_A']/6-1)<=.2
            fs.append(f"|0.22µF peak source/sink current|{r['source_peak_A']:.3f} /{r['sink_peak_A']:.3f}A|4 /6A typical|{'PASS' if passed else 'FAIL'}|")
    fs += ['', 'VDD-UVLO off/on crossings use output divided by the contemporaneous supply, preventing a falling supply itself from masquerading as UVLO shutdown. Threshold/pull-resistance corners, rail-unpowered active pull-down and nonlinear output current are not independently qualified. The output-stage fixture failures block using this surrogate as a physical gate-timing bound.']
    (HERE/'FIXTURES.md').write_text('\n'.join(fs)+'\n')
    dump(HERE/'channel-fixtures.json',measured)
    print(json.dumps(checks,indent=2))

if __name__=='__main__': main()
