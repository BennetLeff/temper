"""Serialize recorded outcomes; Rust owns acceptance of the measured screens."""
from __future__ import annotations
import csv
import json
from pathlib import Path
import subprocess
HERE=Path(__file__).resolve().parent

def flags(rows: list[dict], field: str) -> str:
    return ';'.join(str(r[field]).lower() for r in rows)

def main() -> None:
    captures=[]
    events=[]
    inputs=[]
    for path in sorted((HERE/'runs').glob('*/result.json')):
        r=json.loads(path.read_text())
        replay=path.parent/'replay/analysis.json'
        measured=json.loads(replay.read_text()) if replay.exists() else r
        qpath=HERE/(path.parent.name+'-qualification.json')
        q=json.loads(qpath.read_text()) if qpath.exists() else {}
        periodic=measured.get('periodic',{})
        switching=measured.get('switching',{})
        c=r['identity']['config']
        point={'label':path.parent.name,'bus_V':c['bus'],'R_ohm':c['resistance'],
               'phase_deg':c['phase'],'frequency_Hz':c['freq'],'step_ns':c['step'],
               'cycles':c['cycles'],'transient':r['status'],
               'periodic':periodic.get('status','missing'),
               'input_power_estimate_W':periodic.get('input_power_estimate_W'),
               'tank_power_W':switching.get('tank_power_W'),
               'bridge_overlap_proxy_W':switching.get('bridge_overlap_proxy_W'),
               'elapsed_s':r.get('elapsed_s'),'interrupted':r.get('interrupted',False),
               'source':str(path.relative_to(HERE))}
        captures.append(point)
        for e in switching.get('events',[]):
            events.append({'label':path.parent.name,**e})
        inputs.append([path.parent.name,r['status'],periodic.get('status','missing'),q.get('status','missing'),
                       flags(q.get('cycle',[]),'passes_0p2dB_target'),flags(q.get('step',[]),'passes_0p2dB_target'),
                       *[flags(switching.get('events',[]),f) for f in ('zvs','screen3','screen1p9','screen520')]])
    with (HERE/'verdict-input.tsv').open('w') as stream:
        writer=csv.writer(stream,delimiter='\t',lineterminator='\n')
        writer.writerow(['label','transient','periodic','comparison','cycle_flags','step_flags','zvs','off3','off1p9','vds520'])
        writer.writerows(inputs)
    result=subprocess.run([str(HERE/'physics'),'classify',str(HERE/'verdict-input.tsv')],capture_output=True,text=True,check=True)
    (HERE/'verdicts.csv').write_text(result.stdout)
    for name,rows in [('captures',captures),('events',events)]:
        with (HERE/(name+'.csv')).open('w') as stream:
            writer=csv.DictWriter(stream,fieldnames=list(rows[0]),lineterminator='\n')
            writer.writeheader();writer.writerows(rows)
    (HERE/'summary.json').write_text(json.dumps({'captures':captures,'events':events},indent=2)+'\n')
if __name__=='__main__':
    main()
