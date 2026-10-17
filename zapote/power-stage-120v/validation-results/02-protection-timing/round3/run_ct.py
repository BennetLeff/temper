#!/usr/bin/env python3
"""One-off CT analog solve with the kit's feed-forward delays applied offline.

The existing pure delay does not load or feed back into the analog network.
At VCC/2 the tanh comparator decision is exactly input difference = VOS.
Verify this decomposition against retained original-deck results before a grid.
No small-overdrive timing guarantee or physical protection verdict follows.
"""
from __future__ import annotations
import gzip
import hashlib
import itertools
import json
import math
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE=Path(__file__).resolve().parent
RESULT=HERE.parent
UNIT=RESULT.parents[1]
KIT=UNIT/'validation-plan/sim-kit'
sys.path.insert(0,str(KIT/'common'))
from run_ngspice import read_raw


def crossings(t:list[float], y:list[float], rising:bool=True) -> list[float]:
    out=[]
    for k in range(1,len(t)):
        a,b=y[k-1],y[k]
        if (a < 0 <= b) if rising else (a > 0 >= b):
            out.append(t[k-1]+(t[k]-t[k-1])*(-a)/(b-a))
    return out


def analog(freq:int,i0:int,slope:float,step:float=5e-9) -> dict:
    label=f'f{freq}-i{i0}-s{slope:g}-dt{step:g}'
    deck=(KIT/'02-chain/ct_frontend.cir').read_text()
    deck=deck.split('* ---- comparators:')[0]
    deck=deck.replace('../common/',str(KIT/'common')+'/')
    deck+=f'\n.tran {step:.12g} {{TSTOP}} 0 {step:.12g}\n'
    deck+='.save v(ipri) v(sense) v(ct_s2) v(ref_hi) v(ref_lo)\n.end\n'
    params=f'.param FREQ={freq} I0={i0} SLOPE={slope:.12g}\n'
    with tempfile.TemporaryDirectory(prefix='ps-ct-r3-') as tmp:
        work=Path(tmp)
        (work/'ct.cir').write_text(deck)
        (work/'params.inc').write_text(params)
        (work/'.spiceinit').write_text('set ngbehavior=psa\nset filetype=ascii\n')
        run=subprocess.run(['/opt/homebrew/bin/ngspice','-b','-r','waves.raw','ct.cir'],cwd=work,
                           capture_output=True,text=True,timeout=30,check=False)
        log=run.stdout+'\n'+run.stderr
        (HERE/'outputs'/f'{label}.log').write_text(log)
        if run.returncode or re.search('timestep too small|aborted|singular matrix|fatal error',log,re.I):
            raise ValueError(f'{label}: ngspice failed with exit {run.returncode}')
        waves=read_raw(work/'waves.raw')
        if waves['time'][-1]<199.999e-6 or any(not math.isfinite(x) for col in waves.values() for x in col):
            raise ValueError(f'{label}: incomplete/nonfinite waveform')
        # Full compressed waveforms for the three previously stalled parameter families.
        if (freq,i0,slope) in ((33000,37,1e7),(33000,10,1e6),(39000,37,1e6),(39000,10,1e6)):
            (HERE/'outputs'/f'{label}.raw.gz').write_bytes(gzip.compress((work/'waves.raw').read_bytes(),mtime=0))
    t=waves['time']
    ip=waves['v(ipri)']
    pos=crossings(t,[i-55.17 for i in ip])
    neg=crossings(t,[i+55.17 for i in ip],False)
    zeros=crossings(t,ip)
    if not pos or not neg:
        raise ValueError(f'{label}: primary threshold missing')
    rows=[]
    for vos,tpd in itertools.product((-.004,0.,.004),(45e-9,55e-9)):
        pos_dec=crossings(t,[s-r-vos for s,r in zip(waves['v(sense)'],waves['v(ref_hi)'])])
        neg_dec=crossings(t,[r-s-vos for s,r in zip(waves['v(sense)'],waves['v(ref_lo)'])])
        pos_20=crossings(t,[s-r-vos-.020 for s,r in zip(waves['v(sense)'],waves['v(ref_hi)'])])
        neg_20=crossings(t,[r-s-vos-.020 for s,r in zip(waves['v(sense)'],waves['v(ref_lo)'])])
        zc_dec=crossings(t,[s-b-vos for s,b in zip(waves['v(sense)'],waves['v(ct_s2)'])])
        if not pos_dec or not neg_dec or not zc_dec:
            raise ValueError(f'{label}: analog comparator threshold missing')
        first=min(pos[0],neg[0])
        tor=min(pos_dec[0],neg_dec[0])+tpd+4.5e-9
        t20=min((pos_20[0] if pos_20 else float('inf')),
                (neg_20[0] if neg_20 else float('inf')))
        if not math.isfinite(t20):
            raise ValueError(f'{label}: no 20 mV overdrive crossing')
        t20_plus55=t20+55e-9
        # Pair every ZC decision after one period with its nearest rising primary zero.
        zlags=[(z+tpd-min(zeros,key=lambda x:abs(x-z))) for z in zc_dec if z>1/freq and z<190e-6]
        primary=min(i0+slope*tor,150)*math.sin(6.283185307*freq*tor)
        rows.append({'params':{'FREQ':str(freq),'I0':str(i0),'SLOPE':str(slope),'VOS':str(vos),'TPD':str(tpd)},
                     't_ip_trip':pos[0],'t_in_trip':neg[0],'t_pos_trip':pos_dec[0]+tpd,'t_or':tor,
                     'detection_delay_ns':(tor-first)*1e9,'primary_at_detection_a':primary,
                     't_20mv_overdrive':t20,
                     't_20mv_plus_55ns':t20_plus55,
                     'conditional_20mv_delay_ns':(t20_plus55-first)*1e9,
                     'primary_at_conditional_20mv_a':min(i0+slope*t20_plus55,150)*math.sin(6.283185307*freq*t20_plus55),
                     'zc_lag_ns_min':min(zlags)*1e9,'zc_lag_ns_max':max(zlags)*1e9,
                     'raw_end_s':t[-1],'raw_points':len(t),'analog_run':label})
    return {'rows':rows,'params_inc':params,'derived_deck':deck.replace(str(KIT/'common')+'/', '../../../validation-plan/sim-kit/common/')}


def key(params:dict)->tuple:
    return tuple(float(params[k]) for k in ('FREQ','I0','SLOPE','VOS','TPD'))


def main()->int:
    out=HERE/'outputs'
    out.mkdir(exist_ok=True)
    previous=json.loads((RESULT/'outputs/frontend_sweep.json').read_text())
    print('prior keys',list(previous) if isinstance(previous,dict) else 'list',flush=True)
    retained=previous['ct']
    rows=[]
    comparisons=[]
    for freq,i0,slope in itertools.product((33000,39000,60000),(37,10),(1e6,3e6,1e7)):
        result=analog(freq,i0,slope)
        (HERE/'analog_frontend.cir').write_text(result['derived_deck'])
        rows.extend(result['rows'])
        bykey={key(row['params']):row for row in result['rows']}
        for old in retained:
            k=key(old['params'])
            if k not in bykey:
                continue
            new=bykey[k]
            deltas={n:(new[n]-old['meas'][n])*1e9 for n in ('t_ip_trip','t_in_trip','t_pos_trip','t_or')}
            relative={n:abs(new[n]-old['meas'][n])/abs(old['meas'][n])*100
                      for n in ('t_ip_trip','t_in_trip','t_pos_trip','t_or')}
            comparisons.append({'params':old['params'],'delta_ns':deltas,'relative_error_pct':relative})
            if max(abs(x) for x in deltas.values())>5.1:
                raise ValueError(f'reference decomposition mismatch >5.1 ns: {comparisons[-1]}')
            if max(relative.values())>1.0:
                raise ValueError(f'reference decomposition mismatch >1%: {comparisons[-1]}')
        record={'source_revision':subprocess.check_output(['git','rev-parse','HEAD'], cwd=UNIT, text=True).strip(),
                'board_sha256':hashlib.sha256((UNIT/'native-15/section.kicad_pcb').read_bytes()).hexdigest(),
                'original_deck_sha256':hashlib.sha256((KIT/'02-chain/ct_frontend.cir').read_bytes()).hexdigest(),
                'options_sha256':hashlib.sha256((KIT/'common/options.inc').read_bytes()).hexdigest(),
                'evidence_class':'simulation/model-based, constant-delay assumption',
                'rows':rows,'reference_comparisons':comparisons}
        (out/'ct_sweep.json').write_text(json.dumps(record,indent=2)+'\n')
        print(freq,i0,slope,'completed',len(rows),flush=True)
    return 0

if __name__=='__main__':
    raise SystemExit(main())
