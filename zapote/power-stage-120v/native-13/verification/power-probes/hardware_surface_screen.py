import json,sys
from pathlib import Path
from shapely.geometry import box
u=Path('/Users/bennet/Desktop/temper/worktrees/ps-build/zapote/power-stage-120v')
sys.path.insert(0,str(u/'tools'))
import importlib.util
spec=importlib.util.spec_from_file_location("pinned_geometry_oracle",u/"tests/_barrier_check_py_oracle.py")
oracle=importlib.util.module_from_spec(spec);spec.loader.exec_module(oracle)
geometry=oracle.geometry
from write_rules import HOT_GROUPS,PE,TANK,audit_selv_nets,SELV_NC
items=json.load(open(sys.argv[1]))['items']
metrics=json.load(open(sys.argv[2]))
config=json.load(open(u/'terminal_envelopes.json'))
selv=audit_selv_nets(u/'audit.rs')|SELV_NC|PE
studnets={i['ref'].split('.')[0]:i['net'] for i in items if i['kind']=='pad' and i['ref'].split('.')[0] in ['J2','J5','J7','J8','J9','J10']}
out={}
for name,cfg in config['configurations'].items():
 hits=[]
 for hw in cfg['items']:
  b=box(*metrics['terminal_hardware'][name]['items'][hw['id']]); nets={studnets[s] for s in hw['studs']}
  for i in items:
   if i['net'] in nets or 'F.Cu' not in i['layers']:continue
   need=8 if i['net'] in selv else (5 if (nets&TANK or i['net'] in TANK) else 3.2)
   gap=b.distance(geometry(i))
   if gap<need-1e-5:hits.append({'hardware':hw['id'],'net':i['net'],'kind':i['kind'],'layers':i['layers'],'gap_mm':round(gap,4),'required_mm':need,'geometry':i})
 out[name]=hits
print(json.dumps(out,indent=1))
