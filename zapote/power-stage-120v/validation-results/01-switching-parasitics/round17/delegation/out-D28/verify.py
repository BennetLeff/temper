"""Audit evidence identities and coverage without rerunning device simulations."""
from __future__ import annotations
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import numpy as np
HERE=Path(__file__).resolve().parent
ROOT=next(p for p in HERE.parents if (p/'zapote').is_dir())

def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main() -> None:
    attempts=[]
    for result in sorted((HERE/'runs').glob('*/result.json')):
        row=json.loads(result.read_text())
        identity=row['identity']
        folder=result.parent
        assert row.get('returncode') is not None or row.get('timeout') or row.get('interrupted'), f'nonterminal: {folder.name}'
        matrix=HERE.parents[1]/'d2'/('legA-h0-best.matrix.txt' if identity['config'].get('original') else 'legA-h0-best-n19.matrix.txt')
        assert digest(matrix)==identity['matrix_sha256']
        assert identity['vendor_sha256']=='02ac6634f47c25be04e8de3c6eec4ec8cf403b659001b7f176c8f98bb6e9ce3b'
        assert digest(folder/'source.cir')==identity['deck_sha256']
        assert digest(folder/'options.inc')==identity['common_options_sha256']
        params=''.join(f'.param {k}={v}\n' for k,v in identity['params'].items())
        assert (folder/'params.inc').read_text()==params
        if 'raw_sha256' in row:
            raw=gzip.decompress((folder/'waves.raw.gz').read_bytes())
            assert hashlib.sha256(raw).hexdigest()==row['raw_sha256']
        if row['status']=='unqualified_complete':
            replay=json.loads((folder/'replay/analysis.json').read_text())
            assert replay['raw_sha256']==row['raw_sha256']
            assert replay['physics_source_sha256']==digest(HERE/'physics.rs')
            assert replay['physics_binary_sha256']==digest(HERE/'physics')
            for name in ('fft.npz','prior-fft.npz'):
                with np.load(folder/name) as original, np.load(folder/'replay'/name) as final:
                    assert original.files==final.files
                    assert all(np.array_equal(original[k],final[k]) for k in original.files)
        raw_path=folder/'waves.raw.gz'
        closure_raw_hash=hashlib.sha256(gzip.decompress(raw_path.read_bytes())).hexdigest() if raw_path.exists() else None
        attempts.append({'label':folder.name,'terminal':True,'identity_valid':True,
                         'raw_sha256_at_closure':closure_raw_hash,
                         'raw_hash_recorded_during_run':'raw_sha256' in row})
    coverage={}
    for name in ('complementary','refinement','quarter-step','boundary','upper-boundary','candidate-refinement'):
        declared=json.loads((HERE/(name+'.json')).read_text())
        missing=[r['label'] for r in declared if not (HERE/'runs'/r['label']/'result.json').exists()]
        assert not missing, (name,missing)
        coverage[name]=len(declared)
    anchor=json.loads((HERE/'anchor-reproduction.json').read_text())
    with np.load(HERE/anchor['new']/'fft.npz') as ours, np.load(ROOT/anchor['reference']/'fft.npz') as prior:
        assert ours.files==prior.files
        assert all(np.array_equal(ours[k],prior[k]) for k in ours.files)
    subprocess.run([str(HERE/'physics-tests')],check=True,capture_output=True)
    oracle=subprocess.run([str(HERE/'physics'),'oracle',str(HERE/'ideal-oracle-v2.csv')],check=True,capture_output=True,text=True)
    result={'status':'PASS','attempts':attempts,'campaign_coverage':coverage,
            'anchor_fft_exact':True,'oracle':oracle.stdout.strip(),
            'physics_source_sha256':digest(HERE/'physics.rs')}
    (HERE/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
    print(f"PASS: {len(attempts)} terminal, hash-checked attempts; exact anchor and ideal oracle verified")
if __name__=='__main__':
    main()
