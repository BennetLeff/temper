#!/usr/bin/env python3
"""Check half-step agreement for prior stalls and delay extremes."""
from __future__ import annotations
import json
from run_ct import HERE,analog,key


def main()->None:
    data=json.loads((HERE/'outputs/ct_sweep.json').read_text())
    rows=data['rows']
    cases={(33000,37,1e7),(33000,10,1e6),(39000,37,1e6)}
    for row in (min(rows,key=lambda r:r['detection_delay_ns']),max(rows,key=lambda r:r['detection_delay_ns'])):
        p=row['params']
        cases.add((int(p['FREQ']),int(p['I0']),float(p['SLOPE'])))
    bykey={key(r['params']):r for r in rows}
    checks=[]
    for freq,i0,slope in sorted(cases):
        fine=analog(freq,i0,slope,2.5e-9)
        for row in fine['rows']:
            old=bykey[key(row['params'])]
            delta={n:(row[n]-old[n])*1e9 for n in ('t_ip_trip','t_in_trip','t_pos_trip','t_or')}
            checks.append({'params':row['params'],'delta_ns':delta,'fine':row})
    passed=all(abs(x)<=5.1 for c in checks for x in c['delta_ns'].values())
    summary={'coarse_step_ns':5,'fine_step_ns':2.5,'checks':checks,'passed_within_coarse_step':passed,
             'maximum_crossing_change_ns':max(abs(x) for c in checks for x in c['delta_ns'].values())}
    (HERE/'outputs/timestep.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps({k:v for k,v in summary.items() if k!='checks'}))
    if not passed:
        raise SystemExit(1)

if __name__=='__main__':
    main()
