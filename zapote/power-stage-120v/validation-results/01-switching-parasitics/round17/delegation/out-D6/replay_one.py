#!/usr/bin/env python3
"""Independently replay one saved case into a temporary directory."""
import argparse
import json
import tempfile
from pathlib import Path
from run_study import HERE, run_d2, sha

ap=argparse.ArgumentParser()
ap.add_argument('--group',default='corrected')
ap.add_argument('--case',default='baseline_S4_v198_i-20_d0_dt348')
a=ap.parse_args()
folder=HERE/'results'/a.group
saved=json.loads((folder/a.case/'result.json').read_text())
assert not saved['aborted'], 'This case has no passing numerical replay target.'
identity=json.loads((folder/saved.get('execution_identity','identity.json')).read_text())
assert sha(run_d2.KIT/'models/vendor/IFX_CFD7_650V.lib')==identity['vendor']
deck=HERE/'decks'/f"{saved['variant']}.cir"
assert sha(deck)==saved['deck_sha256']
with tempfile.TemporaryDirectory(prefix='d6-replay-') as temp:
    result=run_d2.run(deck,saved['params'],keep=Path(temp))
    assert not result['aborted']
    delta={k:result['meas'][k]-v for k,v in saved['meas'].items()}
    assert all(abs(v)<=1e-8 for v in delta.values()),delta
    print(json.dumps({'case':a.case,'all_measurements_equal':True,'measurements':result['meas']},indent=2))
