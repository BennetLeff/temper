#!/usr/bin/env python3
"""Independently audit committed CSV recovery integrals and comparison ratios."""
import csv
import hashlib
import json
from pathlib import Path
import numpy as np
P=Path(__file__).resolve().parent
rows=json.loads((P/'summary.json').read_text())
output={}
for r in rows:
 with (P/'results'/r['tag']/'waves.csv').open() as f:
  data=list(csv.reader(f)); names=data.pop(0)
 w=dict(zip(names,np.array(data,dtype=float).T));t=w['time']
 if r['tag'].startswith('recovery'):
  a,b=r['zero_s'],r['end_s']; m=(t>a)&(t<b)
  tt=np.r_[a,t[m],b];ii=np.interp(tt,t,w['i(vprobe)'])
  q=float(np.trapezoid(ii,tt)*1e6)
  assert abs(q-r['Qrr_uC'])<1e-7
  output[r['tag']]={'Qrr_csv_uC':q,'die_VGS_max_recovery_V':float((w['v(xqd.g)']-w['v(xqd.s)'])[m].max()),'Qrr_vs_typ_percent':100*(q/2.3-1),'trr_vs_typ_percent':100*(r['trr_ns']/236-1),'Irrm_vs_typ_percent':100*(r['Irrm_A']/15-1)}
 else:
  output[r['tag']]={'max_terminal_current_A':float(w['i(vids)'].max())}
coarse,fine=rows[:2]
output['recovery_refinement_percent']={key:100*(fine[key]/coarse[key]-1) for key in ('Qrr_uC','trr_ns','Irrm_A')}
coarse,fine=rows[3],rows[5]
output['s4_refinement_percent']={key:100*(fine['meas'][key]/coarse['meas'][key]-1) for key in ('vds_ls_die_pk','vgs_ls_off_max')}
# Input provenance is content-hash authority; commit SHA identifies upstream source.
prov=json.loads((P/'provenance.json').read_text());power=P.parents[4]
for name,digest in prov['inputs'].items():
 assert hashlib.sha256((power/name).read_bytes()).hexdigest()==digest,name
output['input_hashes_verified']=True
(P/'audit.json').write_text(json.dumps(output,indent=2)+'\n')
print(json.dumps(output,indent=2))
