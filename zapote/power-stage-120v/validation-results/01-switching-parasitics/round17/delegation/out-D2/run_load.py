#!/usr/bin/env python3
"""Characterize surrogate into TI's stated capacitive load; use existing runner."""
from pathlib import Path
import json
import sys
from run_cases import VARIANTS, HERE

KIT = HERE.parents[4] / 'validation-plan/sim-kit'
sys.path.insert(0, str(KIT/'common'))
from run_ngspice import run

rows = {}
for variant, params in VARIANTS.items():
    folder = HERE/'load-runs'/variant
    result = run(HERE/'driver_load.cir', params, keep=folder)
    (folder/'IFX_CFD7_650V.lib').unlink(missing_ok=True)
    (folder/'driver_load.cir').unlink(missing_ok=True)
    assert not result['aborted'] and not result['failed']
    assert all(k in result['meas'] for k in ('rise_20_80', 'fall_90_10'))
    rows[variant] = result['meas']
(HERE/'load-results.json').write_text(json.dumps(rows, indent=2)+'\n')
print(json.dumps(rows, indent=2))
