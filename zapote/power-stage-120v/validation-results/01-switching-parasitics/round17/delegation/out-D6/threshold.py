#!/usr/bin/env python3
"""Reproduce D6 model-only hot threshold; dVth is NOT a volt-for-volt shift."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import sys
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parents[1]/'d2'))
import run_d2
rows=[]
for temp in (25,150):
    for dv in (0,-.5):
        path=HERE/'raw'/f'threshold_t{temp}_dv{dv}'
        r=run_d2.run(HERE/'threshold.cir',{'TJ':str(temp),'DV':str(dv)},keep=path)
        (path/'IFX_CFD7_650V.lib').unlink(missing_ok=True)
        (path/'threshold.cir').unlink(missing_ok=True)
        assert not r['aborted'] and r['returncode']==0 and 'vth' in r['meas']
        r['deck']='threshold.cir'
        r['run_dir']=str(path.relative_to(HERE))
        rows.append({'temp_C':temp,'dVth_V':dv,**r})
(HERE/'threshold.json').write_text(json.dumps(rows,indent=2)+'\n')
nom={r['temp_C']:r['meas']['vth'] for r in rows if r['dVth_V']==0}
derived={'model_vth_25C_V':nom[25],'model_vth_150C_V':nom[150],
         'model_drift_25_to_150_V':nom[150]-nom[25],
         'model_average_tempco_mV_C':1000*(nom[150]-nom[25])/125,
         'screen_unrounded_V':3.5+nom[150]-nom[25]-.5,
         'recommended_screen_V':1.9,
         'qualification':'Engineering screen only, not guaranteed hot minimum or limit.',
         'sha256':{f:hashlib.sha256((HERE/f).read_bytes()).hexdigest() for f in ('threshold.py','threshold.cir')}}
(HERE/'criterion.json').write_text(json.dumps(derived,indent=2)+'\n')
print(json.dumps(derived,indent=2))
