#!/usr/bin/env python3
"""Rerun D3 evidence sequentially; only local output changes, no native builds."""
from __future__ import annotations
import contextlib
import hashlib
import importlib.util
import io
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
R17 = HERE.parents[1]
POWER = R17.parents[2]
KIT = POWER / 'validation-plan/sim-kit'
sys.path.insert(0, str(KIT / 'common'))
from run_ngspice import run, read_raw
spec = importlib.util.spec_from_file_location('d2_original', R17 / 'd2/run_d2.py')
d2 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(d2)


def crossing(t: np.ndarray, y: np.ndarray, level: float, start: int, rising: bool) -> tuple[float, int]:
    candidates = np.where((y[start:-1] < level) & (y[start+1:] >= level) if rising else
                          (y[start:-1] > level) & (y[start+1:] <= level))[0]
    if not len(candidates):
        raise ValueError(f'missing crossing: {level}')
    k = start + int(candidates[0])
    return float(t[k] + (level-y[k])*(t[k+1]-t[k])/(y[k+1]-y[k])), k+1


def metrics(w: dict) -> dict:
    t = np.array(w['time']); current = np.array(w['i(vprobe)'])
    start = int(np.searchsorted(t, 2e-6))
    zero, k = crossing(t, current, 0, start, True)
    p = k + int(np.argmax(current[k:]))
    end, e = crossing(t, current, current[p]*.1, p, False)
    ta = t[p]-zero; tb=end-t[p]
    tt=np.r_[zero,t[k:e],end]; ii=np.r_[0,current[k:e],current[p]*.1]
    slope_mask=(t>zero-20e-9)&(t<zero+20e-9)
    internal=np.array(w['i(v.xqd.x1.v_sense2)'])
    return dict(zero_s=zero, peak_s=float(t[p]), end_s=end, Irrm_A=float(current[p]),
                Qrr_uC=float(np.trapezoid(ii,tt)*1e6), trr_ns=(end-zero)*1e9,
                ta_ns=ta*1e9,tb10_ns=tb*1e9,softness_tb10_over_ta=tb/ta,
                slew_A_per_us=float(np.polyfit(t[slope_mask]-zero,current[slope_mask],1)[0]/1e6),
                forward_A=float(-np.interp(1.9e-6,t,current)),
                terminal_v_final=float(w['v(sw)'][-1]),
                body_branch_peak_A=float(internal[k:e].max()),
                body_branch_Q_same_window_uC=float(np.trapezoid(np.interp(tt,t,internal),tt)*1e6),
                gate_node_peak_V=float(np.array(w['v(xqd.g)'])[k:e].max()),
                final_time_s=float(t[-1]))


def execute(tag: str, deck: Path, params: dict[str,str], recovery: bool) -> dict:
    dest=HERE/'results'/tag; dest.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='d3-') as tmp:
        result=run(deck,params,keep=Path(tmp),raw=True)
        for name in ('run.log','raw_run.log','params.inc','.spiceinit'):
            shutil.copy(Path(tmp)/name,dest/name)
        if result['aborted'] or result['failed']:
            raise RuntimeError(result)
        w=read_raw(Path(tmp)/'waves.raw')
    t=np.array(w['time'])
    expected=12e-6 if recovery else 3.148e-6
    if t[-1] < expected-1e-12:
        raise RuntimeError('incomplete waveform')
    row={'tag':tag,'params':params,'meas':result['meas'],'aborted':result['aborted'],
         'returncode':result['returncode'],'raw_returncode':result['raw_returncode'],
         'final_time_s':float(t[-1])}
    fig,axes=plt.subplots(3,1,figsize=(9,8),sharex=True)
    if recovery:
        row.update(metrics(w)); z=row['zero_s']; mask=(t>z-.3e-6)&(t<row['end_s']+.3e-6)
        axes[0].plot((t[mask]-z)*1e9,np.array(w['i(vprobe)'])[mask],label='terminal reverse current')
        axes[0].plot((t[mask]-z)*1e9,np.array(w['i(v.xqd.x1.v_sense2)'])[mask],label='internal body branch')
        axes[0].set_ylabel('Current (A)');axes[0].legend()
        axes[1].plot((t[mask]-z)*1e9,np.array(w['v(sw)'])[mask]);axes[1].set_ylabel('Terminal VDS (V)')
        axes[2].plot((t[mask]-z)*1e9,np.array(w['v(xqd.g)'])[mask]-np.array(w['v(xqd.s)'])[mask]);axes[2].set_ylabel('Die VGS (V)')
        axes[2].set_xlabel('Time from current zero (ns)')
    else:
        mask=t>2e-6
        for side in ('l','h'):
            vd=np.array(w[f'v(xq{side}.dd)'])-np.array(w[f'v(xq{side}.s)'])
            vg=np.array(w[f'v(xq{side}.g)'])-np.array(w[f'v(xq{side}.s)'])
            axes[0].plot(t[mask]*1e6,vd[mask],label=side+' VDS');axes[1].plot(t[mask]*1e6,vg[mask],label=side+' VGS')
        axes[0].legend();axes[1].legend();axes[0].set_ylabel('Die VDS (V)');axes[1].set_ylabel('Die VGS (V)')
        axes[2].plot(t[mask]*1e6,np.array(w['i(vids)'])[mask]);axes[2].set_ylabel('LS current (A)');axes[2].set_xlabel('Time (µs)')
        row['ls_current_peak_A']=float(np.array(w['i(vids)'])[mask].max())
    # Full-resolution transition CSV; full-window logs + explicit final-time check above.
    names=list(w)
    np.savetxt(dest/'waves.csv',np.column_stack([np.array(w[n])[mask] for n in names]),delimiter=',',header=','.join(names),comments='',fmt='%.12g')
    for ax in axes: ax.grid(alpha=.3)
    fig.suptitle(tag);fig.tight_layout();fig.savefig(dest/'waves.png',dpi=140);plt.close(fig)
    (dest/'result.json').write_text(json.dumps(row,indent=2)+'\n')
    return row


def main() -> None:
    vendor=KIT/'models/vendor/IFX_CFD7_650V.lib'
    expected='02ac6634f47c25be04e8de3c6eec4ec8cf403b659001b7f176c8f98bb6e9ce3b'
    if hashlib.sha256(vendor.read_bytes()).hexdigest()!=expected:
        raise RuntimeError('vendor hash mismatch; run fetch_models.sh')
    rows=[]
    for temp,step in ((25,'0.2n'),(25,'0.1n'),(27,'0.2n')):
        rows.append(execute(f'recovery-{temp}C-{step}',HERE/'recovery.cir',{'RG':'730','TJ':str(temp),'STEP':step},True))
    matrix=R17/'d2/legA-h0-lin12.matrix.txt'
    base=d2.matrix_params(d2.read_L(str(matrix)))
    base.update(VBUS='170',IL='-20',DIR='0',LESL='10n',LSHUNT='2n',DT='348n')
    for temp,step in ((27,'0.2n'),(25,'0.2n'),(27,'0.1n')):
        p=base|{'TJ':str(temp),'TRMAX':step}
        rows.append(execute(f's4-{temp}C-{step}',HERE/'s4.cir',p,False))
    # Exercise original runner entry point, redirecting only its output destination.
    with tempfile.TemporaryDirectory(prefix='d3-original-') as tmp:
        d2.HERE=Path(tmp); d2.DECK=R17/'d2/leg_matrix.cir'
        sys.argv=['run_d2.py','--matrix',str(matrix),'--vbus','170','--il','-20','--dir','0','--dt','348','--esl','10','--tag','S4']
        output=io.StringIO()
        with contextlib.redirect_stdout(output): d2.main()
        (HERE/'original-runner.log').write_text(output.getvalue())
        original=json.loads(output.getvalue().split('RESULT ')[1])
        if original['aborted']: raise RuntimeError(original)
        for key,value in original['meas'].items():
            if value != rows[3]['meas'][key]: raise RuntimeError(f'copied S4 mismatch {key}')
    (HERE/'summary.json').write_text(json.dumps(rows,indent=2)+'\n')
    inputs=[vendor,matrix,R17/'d2/run_d2.py',R17/'d2/leg_matrix.cir',KIT/'common/options.inc',KIT/'common/run_ngspice.py',HERE/'run.py',HERE/'recovery.cir',HERE/'s4.cir']
    provenance={'source_revision':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),'model':'GPT-6 Astra','python':sys.version,'ngspice':subprocess.check_output(['ngspice','--version'],text=True),'inputs':{str(f.relative_to(POWER)):hashlib.sha256(f.read_bytes()).hexdigest() for f in inputs}}
    (HERE/'provenance.json').write_text(json.dumps(provenance,indent=2)+'\n')
    print(json.dumps(rows,indent=2))

if __name__=='__main__': main()
