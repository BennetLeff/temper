"""Independent read-only examination of frozen PE component geometry."""
import json,hashlib,sys,math
from pathlib import Path
sys.path.insert(0,'zapote/power-stage-120v/prototype-closure/round3/packaging')
from build_proposal import read_parts,bounds,hits
root=Path('output/temper-prototype-closure/round5/orientation-cooling')
f=root/'cooling-replacements-pe-final.step'; p=read_parts(f)
r=json.loads((root/'checks-pe-final.json').read_text())
source=read_parts(Path(r['source']['path']))
P='BASE_BASE_R2_'
result={'step_sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'named_parts':len(p),'invalid_parts':[n for n,s in p.items() if not s.isValid()],'disconnected_parts':{n:len(s.Solids()) for n,s in p.items() if len(s.Solids())!=1},'sink_bounds':bounds(p[P+'CUSTOM_SINK']),'historical_sink_bounds':bounds(source[P+'CUSTOM_SINK']),'pe_contacts':[],'positive_pairs':[]}
for row in r['pe_terminal_contacts']:
 a,b=row['a'],row['b']; aa=p.get(a,source.get(a)); bb=p.get(b,source.get(b));result['pe_contacts'].append({'a':a,'b':b,'distance_mm':aa.distance(bb)})
for n in ['R5_PE_STRAIN_SUPPORT_FRONT','R5_PE_STRAIN_SUPPORT_REAR']:
 result['pe_contacts'].append({'a':n,'b':P+'SINK_CRADLE_CHASSIS_MOUNT','distance_mm':p[n].distance(p[P+'SINK_CRADLE_CHASSIS_MOUNT'])})
for i,(n,s) in enumerate(p.items()):
 for m,t in list(p.items())[i+1:]:
  b,c=bounds(s),bounds(t)
  if any(b[j]>=c[j+3]-1e-7 or c[j]>=b[j+3]-1e-7 for j in range(3)):continue
  vol=s.intersect(t).Volume()
  if vol>1e-5:result['positive_pairs'].append({'a':n,'b':m,'volume_mm3':vol})
recorded={frozenset((v['new'],v['context'])):v['volume_mm3'] for v in r['replacement_pair_hits']}
actual={frozenset((v['a'],v['b'])):v['volume_mm3'] for v in result['positive_pairs']}
result['pair_set_matches_receipt']=actual.keys()==recorded.keys()
result['max_pair_volume_difference_mm3']=max(abs(v-recorded.get(k,0)) for k,v in actual.items())
result['input_hashes']={k:{'path':r[k]['path'],'sha256':hashlib.sha256(Path(r[k]['path']).read_bytes()).hexdigest(),'matches_receipt':hashlib.sha256(Path(r[k]['path']).read_bytes()).hexdigest()==r[k]['sha256']} for k in ['source','native_source','validation_context_source']}
print(json.dumps(result,indent=2))
assert not result['invalid_parts'] and not result['disconnected_parts']
assert all(v['distance_mm']<1e-6 for v in result['pe_contacts'])
assert result['pair_set_matches_receipt'] and result['max_pair_volume_difference_mm3']<1e-4
assert all(v['matches_receipt'] for v in result['input_hashes'].values())
b,c=result['historical_sink_bounds'],result['sink_bounds'];assert max(abs(c[j]-b[j]-(36 if j in [0,3] else 0)) for j in range(6))<1e-6
