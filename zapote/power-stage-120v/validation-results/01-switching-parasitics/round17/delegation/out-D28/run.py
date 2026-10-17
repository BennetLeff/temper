"""D28 transport: pinned SPICE inputs, existing D22 convergence, Rust metrics.

No new engineering decision logic lives in this adapter. See physics.rs.
"""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor
import gzip
import hashlib
import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
import time
import numpy as np

HERE = Path(__file__).resolve().parent
D22 = HERE.parent / 'out-D22'
D19 = HERE.parent / 'out-D19'
D2 = HERE.parents[1] / 'd2'
ROOT = next(p for p in HERE.parents if (p / 'zapote').is_dir())
KIT = ROOT / 'zapote/power-stage-120v/validation-plan/sim-kit'
P = runpy.run_path(str(D22 / 'periodic.py'))
D = runpy.run_path(str(D2 / 'run_d2.py'))
VENDOR = HERE / 'vendor/IFX_CFD7_650V.lib'
NG = Path('/opt/homebrew/bin/ngspice')

def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def deck_text(original: bool) -> str:
    text = (D19 / 'periodic-sweep.cir').read_text().replace('../common/options.inc', 'options.inc')
    if not original:
        text = text.replace('XLA bus swa leg DIR=0', 'XLA bus swa leg DIR=0 SHIFT=0')
        text = text.replace('XLB bus swb leg DIR=1', 'XLB bus swb leg DIR=1 SHIFT={PHASE==180 ? 0 : (PHASE/360+0.5)/FREQ}')
        text = text.replace('.subckt leg bus sw params: DIR=0', '.subckt leg bus sw params: DIR=0 SHIFT=0')
        text = text.replace('TLS={T1+DIR*DT} THS={T1+(1-DIR)*DT}', 'TLS={T1+SHIFT+DIR*DT} THS={T1+SHIFT+(1-DIR)*DT}')
    save = ['i(ltank)']
    for leg in ('a', 'b'):
        for side in ('h', 'l'):
            for node in ('dd', 'g', 's', 'ldrd'):
                save.append(f'v(xl{leg}.xq{side}.{node})')
    text = text.replace('.meas tran sw_max', '.save ' + ' '.join(save) + '\n.meas tran sw_max')
    return text

def run_case(c: dict) -> dict:
    folder = HERE / 'runs' / c['label']
    folder.mkdir(parents=True, exist_ok=True)
    assert digest(VENDOR) == '02ac6634f47c25be04e8de3c6eec4ec8cf403b659001b7f176c8f98bb6e9ce3b'
    matrix = D2 / ('legA-h0-best.matrix.txt' if c.get('original') else 'legA-h0-best-n19.matrix.txt')
    params = D['matrix_params'](D['read_L'](str(matrix)))
    params.update(VBUS=str(c['bus']), RTANK=str(c['resistance']), FREQ=str(c['freq']), PHASE=str(c['phase']),
                  DT='443n', LESL='1.06n', TRMAX=f"{c['step']}n", CYCLES=str(c['cycles']))
    deck = deck_text(c.get('original', False))
    identity = {'config': c, 'params': params, 'matrix_sha256': digest(matrix), 'vendor_sha256': digest(VENDOR),
                'deck_sha256': hashlib.sha256(deck.encode()).hexdigest(),
                'common_options_sha256': digest(KIT/'common/options.inc'), 'simulator_sha256': digest(NG)}
    result = folder / 'result.json'
    if result.exists():
        row = json.loads(result.read_text())
        if row['identity'] != identity:
            raise ValueError(f"cache identity mismatch: {c['label']}")
        return row
    (folder/'source.cir').write_text(deck)
    (folder/'params.inc').write_text(''.join(f'.param {k}={v}\n' for k,v in params.items()))
    shutil.copyfile(KIT/'common/options.inc',folder/'options.inc')
    (folder/'.spiceinit').write_text('set ngbehavior=psa\nset filetype=binary\n')
    # Only the ignored directory contains licensed bytes; relative link is not committed.
    (folder/'IFX_CFD7_650V.lib').symlink_to('../../vendor/IFX_CFD7_650V.lib')
    row = {'identity': identity, 'status': 'indeterminate', 'label': c['label']}
    started = time.monotonic()
    result.write_text(json.dumps(row,indent=2)+'\n')
    with (folder/'run.log').open('w') as log:
        try:
            p = subprocess.run([str(NG), '-b', '-r', 'waves.raw', 'source.cir'], cwd=folder,
                               stdout=log, stderr=subprocess.STDOUT, timeout=c.get('timeout',1800),check=False)
            row['returncode'] = p.returncode
        except subprocess.TimeoutExpired:
            row['timeout'] = True
    raw = folder/'waves.raw'
    if raw.exists():
        payload=raw.read_bytes()
        with gzip.open(folder/'waves.raw.gz','wb') as out:
            out.write(payload)
        row['raw_sha256']=hashlib.sha256(payload).hexdigest()
        log=(folder/'run.log').read_text(errors='replace').lower()
        if row.get('returncode') == 0 and not any(x in log for x in ('timestep too small','simulation(s) aborted','fatal error')):
            try:
                waves=P['read_binary'](payload)
                row['periodic']=P['analyze'](waves,params,folder)
                columns=[waves['time'],waves['i(ltank)']]
                for leg in ('a','b'):
                    for side in ('h','l'):
                        q=f'xl{leg}.xq{side}'
                        columns.extend([waves[f'v({q}.dd)']-waves[f'v({q}.s)'],
                                        waves[f'v({q}.g)']-waves[f'v({q}.s)'],
                                        (waves[f'v({q}.ldrd)']-waves[f'v({q}.dd)'])/7.44e-5])
                np.savetxt(folder/'wave.csv',np.column_stack(columns),delimiter=',',header='time,tank,A_H_VDS,A_H_VGS,A_H_ID,A_L_VDS,A_L_VGS,A_L_ID,B_H_VDS,B_H_VGS,B_H_ID,B_L_VDS,B_L_VGS,B_L_ID',comments='')
                proc=subprocess.run([str(HERE/'physics'),'metrics',str(folder/'wave.csv'),str(c['bus']),str(c['freq']),str(c['phase']),str(c['cycles'])],capture_output=True,text=True,check=False)
                (folder/'metrics.log').write_text(proc.stdout+proc.stderr)
                if proc.returncode:
                    raise ValueError('Rust waveform analysis failed')
                row['switching']=json.loads(proc.stdout)
                # Complete transient is provisional until D22 spectral refinement qualifies it.
                row['status']='unqualified_complete'
            except (ValueError,KeyError) as error:
                row['analysis_error']=str(error)
        raw.unlink()
    row['elapsed_s']=time.monotonic()-started
    result.write_text(json.dumps(row,indent=2,allow_nan=False)+'\n')
    print(c['label'],row['status'],round(row['elapsed_s'],1),flush=True)
    return row

def main() -> None:
    parser=argparse.ArgumentParser()
    parser.add_argument('campaign',type=Path)
    parser.add_argument('--workers',type=int,default=4)
    args=parser.parse_args()
    cases=json.loads(args.campaign.read_text())
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        rows=list(pool.map(run_case,cases))
    (HERE/(args.campaign.stem+'-results.json')).write_text(json.dumps(rows,indent=2)+'\n')
if __name__=='__main__':
    main()
