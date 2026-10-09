"""Read-only independent merged geometry checks; output only to stdout."""
from pathlib import Path
import sys,json,hashlib,math
sys.path.insert(0,'zapote/power-stage-120v/prototype-closure/round5/packaging-integration')
from build_integration import read_parts,bounds,cylinder
from check_power_orientation import check
import cadquery as cq
O=Path('output/temper-prototype-closure/round5/packaging-integration');C=O.parent/'orientation-cooling'
f=O/'r4-supported-routed-candidate.step';p=read_parts(f)
source=Path('output/temper-prototype-closure/round5/protection/catch-with-power-interposer-review.step');hist=read_parts(source)
native=read_parts(Path('output/temper-prototype-closure/pcb/temper-power-native19-candidate.step'));native={('SUBSTRATE' if n.startswith('=>') else n):v for n,v in native.items()}
r={'assembly_sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'orientation':check(native,p,'BASE_BASE_native19_')}
try:check(native,hist,'BASE_BASE_native19_')
except AssertionError as ex:r['historical_negative_control']=str(ex)
else:raise AssertionError('Historical mirror passed')
new=read_parts(C/'cooling-replacements-pe-final.step')
r['final_cooling_parts_missing']=[n for n in new if n not in p]
r['final_cooling_invalid_or_disconnected']={n:len(p[n].Solids()) for n in new if n in p and (not p[n].isValid() or len(p[n].Solids())!=1)}
cr=json.loads((C/'checks-pe-final.json').read_text());r['pe_final_contacts']=[{'a':v['a'],'b':v['b'],'distance_mm':p[v['a']].distance(p[v['b']])} for v in cr['pe_terminal_contacts']]
r['delegated_interfaces']=[]
interfaces=[v for v in cr['packaging_deferred_context_hits'] if 'PAIRED_POST_M3x60' not in v['context']]
posts=[n for n in p if n.startswith('PAIRED_POST_M3x60_CS_')]
assert len(posts)==2
interfaces += [{'new':'BASE_BASE_R2_CARRIER_RAIL_-122p5','context':n} for n in posts]
for v in interfaces:
 s=p[v['new']].intersect(p[v['context']]);vol=0 if s.wrapped.IsNull() else s.Volume();entry={'a':v['new'],'b':v['context'],'volume_mm3':vol}
 if 'PAIRED_POST_M3x60' in v['context']:
  entry['bounds_mm']=bounds(s);assert abs(vol-math.pi*(1.5**2-1.25**2)*6)<1e-5;assert abs(entry['bounds_mm'][2]-10)<1e-6 and abs(entry['bounds_mm'][5]-16)<1e-6
 else:assert abs(vol)<1e-6
 r['delegated_interfaces'].append(entry)
power=json.loads((O/'rigid-power-installation.json').read_text());support=json.loads((O/'support-patterns.json').read_text())['records'];harness=json.loads((O/'harness-probe.json').read_text())
rows=[[*v['center_xy'],v['diameter']] for v in power['new_cooling_floor_holes']]
for v in support:
 if 'floor_hole_d' in v:rows.append([*v['xy'],v['floor_hole_d']])
 rows.extend(v.get('floor_holes_xy_d',[]))
for v in harness['candidate_changes'].values():
 if 'floor_hole_xy_d_mm' in v:rows.append(v['floor_hole_xy_d_mm'])
assert len(rows)==26
# Reconstruct expected complete new floor from immutable historical shape;
# unlike masking changed areas, this also detects unfilled obsolete hole remnants.
name='BASE_BASE_R4_two_bend_bottom_and_sides';want=hist[name]
for x,y,d in power['obsolete_floor_holes_restored_xy_d_mm']:want=want.fuse(cylinder([x,y,8],[x,y,10],d/2))
for x,y,d in rows:want=want.cut(cylinder([x,y,7],[x,y,11],d/2))
actual=cq.importers.importStep(str(O/'candidate-drilled-floor.step')).val()
def vol(s):return 0 if s.wrapped.IsNull() else s.Volume()
r['floor']={'new_holes':len(rows),'obsolete_holes_restored':len(power['obsolete_floor_holes_restored_xy_d_mm']),'missing_material_vs_reconstructed_mm3':vol(want.cut(actual)),'excess_material_vs_reconstructed_mm3':vol(actual.cut(want)),'assembly_to_floor_export_missing_mm3':vol(actual.cut(p[name])),'assembly_to_floor_export_excess_mm3':vol(p[name].cut(actual))}
lower=p['PAIRED_WIRE_SADDLE_LOWER']
r['catch_retention']={'separate_base_present':'PAIRED_SADDLE_BASE' in p,'lower_integral_solids':len(lower.Solids()),'lower_integral_bounds_mm':bounds(lower),'post_to_integral_base':[],'mount_head_to_integral_base':[],'closure_head_to_upper':[],'closure_thread_volumes_mm3':[],'mount_driver_vs_guide_mm3':[]}
for y in [285,295]:
 post=p[f'PAIRED_SADDLE_PEEK_POST_{y}'];r['catch_retention']['post_to_integral_base'].append(post.distance(lower))
 r['catch_retention']['mount_head_to_integral_base'].append(p[f'PAIRED_POST_M3x60_CS_{y}'].distance(lower))
 driver=cylinder([135.5,y,70.01],[135.5,y,81],3.0)
 r['catch_retention']['mount_driver_vs_guide_mm3'].append(vol(driver.intersect(lower))+vol(driver.intersect(p['PAIRED_WIRE_SADDLE_UPPER'])))
for n in p:
 if n.startswith('PAIRED_CLOSURE_M2x8_'):
  r['catch_retention']['closure_head_to_upper'].append(p[n].distance(p['PAIRED_WIRE_SADDLE_UPPER']))
  overlap=vol(lower.intersect(p[n]));r['catch_retention']['closure_thread_volumes_mm3'].append(overlap);assert abs(overlap-math.pi*(1**2-.8**2)*2.5)<1e-5
assert not r['catch_retention']['separate_base_present'] and r['catch_retention']['lower_integral_solids']==1
assert all(v<1e-6 for v in r['catch_retention']['post_to_integral_base']+r['catch_retention']['mount_head_to_integral_base']+r['catch_retention']['closure_head_to_upper']+r['catch_retention']['mount_driver_vs_guide_mm3'])
r['sink_bounds']=bounds(p['BASE_BASE_R2_CUSTOM_SINK'])
print(json.dumps(r,indent=2))
assert not r['final_cooling_parts_missing'] and not r['final_cooling_invalid_or_disconnected']
assert all(v['distance_mm']<1e-6 for v in r['pe_final_contacts'])
assert all(abs(v)<1e-5 for k,v in r['floor'].items() if k.endswith('mm3'))
assert max(abs(a-b) for a,b in zip(r['sink_bounds'],[-76,93.9,12,124,161.9,72]))<1e-6
