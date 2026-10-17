#!/usr/bin/env python3
"""Repeat the hard-turn-on boosted cases with half the maximum timestep."""
import importlib.util
import json
from run_cases import D2, HERE, MATRICES, VARIANTS

spec = importlib.util.spec_from_file_location('round17_d2', D2/'run_d2.py')
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
rows = []
for matrix, path in MATRICES.items():
    params = mod.matrix_params(mod.read_L(str(path)))
    params.update(VBUS='170', IL='-20', DIR='0', DT='348n', TRMAX='0.1n', LESL='10n', LSHUNT='2n', **VARIANTS['boost'])
    folder = HERE/'refined-runs'/matrix
    result = mod.run(HERE/'leg_matrix.cir', params, keep=folder)
    (folder/'IFX_CFD7_650V.lib').unlink(missing_ok=True)
    (folder/'leg_matrix.cir').unlink(missing_ok=True)
    assert not result['aborted'] and not result['failed']
    assert all(k in result['meas'] for k in (*mod.MEAS, 'window_end'))
    assert abs(result['meas']['window_end']-3.098e-6)<1e-12
    rows.append({'matrix': matrix, 'params': params, 'meas': result['meas']})
(HERE/'refinement.json').write_text(json.dumps(rows, indent=2)+'\n')
print(json.dumps(rows, indent=2))
