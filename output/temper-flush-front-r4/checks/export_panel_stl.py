"""Cold-fit STL exports only. Material, mechanism and whole-cooker fit unqualified."""
from pathlib import Path
import struct
import json
import cadquery as cq
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
NAMES=['lens_rear_support_ring','carrier_and_closed_sidewalls','flush_lens_108x38x2','rear_lid','three_button_continuous_membrane_INSTALLED']
(ROOT/'STL').mkdir(exist_ok=True)
records=[]
for name in NAMES:
    shape=cq.importers.importStep(str(ROOT/'STEP/parts'/('front_'+name+'.step'))).val()
    path=ROOT/'STL'/('front_'+name+'-WORLD-mm.stl')
    cq.exporters.export(shape,str(path),tolerance=.03,angularTolerance=.1)
    raw=path.read_bytes();count=struct.unpack('<I',raw[80:84])[0]
    dtype=np.dtype([('normal','<f4',(3,)),('vertices','<f4',(3,3)),('attr','<u2')])
    triangles=np.frombuffer(raw, dtype=dtype,offset=84,count=count)
    v=triangles['vertices'];areas=np.linalg.norm(np.cross(v[:,1]-v[:,0],v[:,2]-v[:,0]),axis=1)
    kept=triangles[areas>0]
    path.write_bytes(raw[:80]+struct.pack('<I',len(kept))+kept.tobytes())
    records.append(dict(file=str(path.relative_to(ROOT)),triangles=len(kept),exact_zero_area_removed=int(count-len(kept)),finite=bool(np.isfinite(v).all()),units='mm',coordinates='whole cooker',purpose='Cold visual/fit mock; not material or manufacturing specification'))
    assert records[-1]['finite'] and len(kept)>0
(ROOT/'evidence/panel-stl-checks.json').write_text(json.dumps(records,indent=2))
(ROOT/'STL/README.txt').write_text('R4 cold-fit geometry only. Units mm, whole-cooker coordinates; orient in slicer. The lens and installed membrane solids are shape mockups, not printable functional glass or qualified seals. The complete cassette still conflicts with the PCB compartment allocations. STEP remains authoritative. Binary STL checks remove exact zero-area triangles and verify finite coordinates; no manifold/strength/process certification.\n')
print(json.dumps(records,indent=2))
