"""Independent, read-only audit of frozen assembly geometry. Writes only stdout."""
import hashlib,json,sys
from pathlib import Path
sys.path.insert(0,'zapote/power-stage-120v/prototype-closure/round3/packaging')
from build_proposal import read_parts,bounds
final=Path(sys.argv[1]); native_path=Path('output/temper-prototype-closure/pcb/temper-power-native19-candidate.step')
p=read_parts(final); native=read_parts(native_path)
native={('SUBSTRATE' if k.startswith('=>') else k):v for k,v in native.items()}
result={'assembly':str(final),'sha256':hashlib.sha256(final.read_bytes()).hexdigest(),'source_sha256':hashlib.sha256(native_path.read_bytes()).hexdigest(),'named_parts':len(p),'native_parts':len(native),'native_mismatches':[],'contacts':[]}
for n,s in native.items():
 key='BASE_BASE_native19_'+n
 if key not in p:
  result['native_mismatches'].append({'name':n,'error':'missing'});continue
 b=bounds(s); want=[129.5-b[3],162-b[4],30.387+b[2],129.5-b[0],162-b[1],30.387+b[5]]; actual=bounds(p[key])
 error=max(abs(x-y) for x,y in zip(want,actual));volume_error=abs(s.Volume()-p[key].Volume())
 if error>1e-5 or volume_error>1e-3:result['native_mismatches'].append({'name':n,'bbox_error_mm':error,'volume_error_mm3':volume_error})
for ref in ['Q2','Q3','Q5','Q6','BR1']:
 source=p['BASE_BASE_native19_'+ref]
 proxy=p['R5_'+ref+'_CAD_CONTACT_PROXY_NOT_SHIM_ORDER']
 ceramic=p['BASE_BASE_R2_ALN_'+('BR1' if ref=='BR1' else 'Q3_Q2' if ref in ['Q2','Q3'] else 'Q5_Q6')]
 sink=p['BASE_BASE_R2_CUSTOM_SINK']
 row={'ref':ref,'proxy_device_mm':proxy.distance(source),'proxy_device_overlap_mm3':proxy.intersect(source).Volume(),'proxy_ceramic_mm':proxy.distance(ceramic),'ceramic_sink_mm':ceramic.distance(sink),'rear_slice_area_mm2':proxy.translate((0,.001,0)).intersect(source).Volume()/.001}
 result['contacts'].append(row)
for n in sorted(p):
 if 'PEEK_PRESSURE_PAD' in n:
  ref='BR1' if '_BR_' in n else n.split('_')[1]
  result['contacts'].append({'pad':n,'device':ref,'distance_mm':p[n].distance(p['BASE_BASE_native19_'+ref]),'overlap_mm3':p[n].intersect(p['BASE_BASE_native19_'+ref]).Volume()})
print(json.dumps(result,indent=2))
assert not result['native_mismatches']
