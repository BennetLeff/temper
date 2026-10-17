"""Independent DC and peak-current fixtures; report differences, no fitting."""
from __future__ import annotations
import numpy as np
from run import HERE, control, dump, execute
rows=[]
for mode in ['dc','peak']:
    inputs='Va a 0 3.3\nVb b 0 0' if mode=='dc' else 'Va a 0 PULSE(0 3.3 1u 1n 1n 1u 1m)\nVb b 0 0'
    load='Ioh oa 0 0.05\nIol 0 ob 0.05' if mode=='dc' else 'Ca oa 0 220n\nCb ob 0 1f'
    text=f'''* Output-stage {mode}; CVDD10u, VDD12V
.include ucc21550_parametric.lib
Vcc vc 0 3.3
Vdd vd 0 12
Cdd vd 0 10u
{inputs}
XU a b 0 vc 0 vd 0 oa vd 0 ob UCC21550 DTEN=0
{load}
.tran 0.1n 3u
'''+control('v(oa) v(ob)')
    status,w=execute('output-'+mode,text,3e-6)
    row=dict(status,fixture=mode)
    if w is not None and status['status']=='COMPLETED':
        t,a,b=w.T
        if mode=='dc':
            row['ROH_ohm']=(12-float(a[-1]))/0.05
            row['ROL_ohm']=float(b[-1])/0.05
        else:
            current=np.diff(a)/np.diff(t)*220e-9
            row['source_peak_A']=float(current.max())
            row['sink_peak_A']=float(-current.min())
            row['source_typical_A']=4
            row['sink_typical_A']=6
    rows.append(row)
    print(row,flush=True)
dump(HERE/'output-fixtures.json',rows)
