"""Re-read captured bytes and forward their measurements to the final Rust analyzer."""
from __future__ import annotations
import gzip
import hashlib
import json
from pathlib import Path
import runpy
import subprocess
import numpy as np
HERE=Path(__file__).resolve().parent
P=runpy.run_path(str(HERE.parent/'out-D22/periodic.py'))

def replay(folder: Path) -> dict:
    original=json.loads((folder/'result.json').read_text())
    if original.get('status')!='unqualified_complete':
        return {'status':'indeterminate','reason':'no complete transient','label':folder.name}
    raw=gzip.decompress((folder/'waves.raw.gz').read_bytes())
    if hashlib.sha256(raw).hexdigest()!=original['raw_sha256']:
        raise ValueError(f'raw identity mismatch: {folder}')
    waves=P['read_binary'](raw)
    target=folder/'replay'
    target.mkdir(exist_ok=True)
    periodic=P['analyze'](waves,original['identity']['params'],target)
    columns=[waves['time'],waves['i(ltank)']]
    # Existing D15 die-voltage/drain-resistor coordinate conversion, unchanged.
    for leg in ('a','b'):
        for side in ('h','l'):
            q=f'xl{leg}.xq{side}'
            columns.extend([waves[f'v({q}.dd)']-waves[f'v({q}.s)'],
                            waves[f'v({q}.g)']-waves[f'v({q}.s)'],
                            (waves[f'v({q}.ldrd)']-waves[f'v({q}.dd)'])/7.44e-5])
    csv=target/'wave.csv'
    np.savetxt(csv,np.column_stack(columns),delimiter=',',header='D28 canonical measurement columns',comments='')
    c=original['identity']['config']
    command=[str(HERE/'physics'),'metrics',str(csv),str(c['bus']),str(c['freq']),str(c['phase']),str(c['cycles']),str(c['resistance'])]
    proc=subprocess.run(command,capture_output=True,text=True,check=False)
    (target/'metrics.txt').write_text(proc.stdout+proc.stderr)
    if proc.returncode:
        raise ValueError(f'metrics failed: {folder}')
    result={'label':folder.name,'periodic':periodic,'switching':json.loads(proc.stdout),
            'raw_sha256':original['raw_sha256'],
            'physics_source_sha256':hashlib.sha256((HERE/'physics.rs').read_bytes()).hexdigest(),
            'physics_binary_sha256':hashlib.sha256((HERE/'physics').read_bytes()).hexdigest()}
    (target/'analysis.json').write_text(json.dumps(result,indent=2)+'\n')
    csv.unlink()
    return result
if __name__=='__main__':
    results=[replay(folder) for folder in sorted((HERE/'runs').iterdir()) if (folder/'result.json').exists()]
    (HERE/'replay-results.json').write_text(json.dumps(results,indent=2)+'\n')
