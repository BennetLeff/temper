"""Cross-check named assembly occurrences against individually exported saved parts."""
from pathlib import Path
import hashlib
import json
from cadgen import read_scene
from build123d import import_step

ROOT=Path(__file__).resolve().parents[1]
scene=read_scene(ROOT/'STEP/assembly.step')
occurrences={o.label:o.ref for o in scene.leaves()}
catalog=json.loads((ROOT/'catalog.json').read_text())
rows=[]
for p in catalog:
    if p['name'].startswith('pcb_export_'):continue
    a=scene.resolve(occurrences[p['name']]).shape()
    # Bounds/volume checks need a B-rep import, not tessellation and cache compilation.
    b=import_step(ROOT/p['file'])
    aa=a.bounding_box();bb=b.bounding_box()
    diffs=[abs(getattr(getattr(aa,end),axis)-getattr(getattr(bb,end),axis)) for end in ('min','max') for axis in ('X','Y','Z')]
    v=abs(a.volume-b.volume)
    rows.append({'name':p['name'],'volume_difference_mm3':v,'max_bound_difference_mm':max(diffs),
                 'matches':v<1e-4 and max(diffs)<1e-5 and len(a.solids())==len(b.solids())})
result={'assembly_sha256':hashlib.sha256((ROOT/'STEP/assembly.step').read_bytes()).hexdigest(),
        'method':'Independent cadgen saved-scene name resolution; compare volume, bounds and solid count to individual STEP.',
        'scope':'Correspondence screen, not full topological equivalence or physical proof.',
        'checked':len(rows),'all_match':all(r['matches'] for r in rows),'parts':rows}
(ROOT/'evidence/assembly-correspondence.json').write_text(json.dumps(result,indent=2))
print(json.dumps({k:v for k,v in result.items() if k!='parts'}))
assert result['all_match']
