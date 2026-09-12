"""Replay the reviewed poses-pfc-02 coordinates and compiled metadata in native KiCad.
Run from the repository root; no placement search or engineering verdict.
"""
from pathlib import Path
import pcbnew,json,hashlib
p=Path('zapote/power-entry/candidate/section.kicad_pcb');before=hashlib.sha256(p.read_bytes()).hexdigest();b=pcbnew.LoadBoard(str(p));
if list(b.GetTracks()) or list(b.Zones()): raise ValueError('placement replay requires an unrouted candidate')
poses=json.loads(Path('zapote/power-entry/poses-pfc-02.json').read_text());m=json.loads(Path('zapote/power-entry/candidate/source-manifest.json').read_text());ids={c['reference']:c['instance_path'] for c in m['components']}
for f in b.GetFootprints():
 c=next(c for c in m['components'] if c['reference']==f.GetReference())
 for name,value in [('SourceInstance',c['instance_path']),('MPN',c['mpn']),('SourceValue',c.get('value') or '')]: f.SetField(name,str(value))
 for q in f.GetFields():
  if q.GetName() not in ['Reference','Value']: q.SetVisible(False)
 x,y,a=poses[ids[f.GetReference()]];f.SetOrientationDegrees(a);f.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(x),pcbnew.FromMM(y)))
 # Move reference labels with the package and keep a readable native reference.
 f.Reference().SetVisible(True);f.Reference().SetTextSize(pcbnew.VECTOR2I(pcbnew.FromMM(1),pcbnew.FromMM(1)));f.Reference().SetTextThickness(pcbnew.FromMM(.15))
pcbnew.SaveBoard(str(p),b)
Path('zapote/power-entry/evidence/placement-02.json').write_text(json.dumps({'input_sha256':before,'output_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'poses_sha256':hashlib.sha256(Path('zapote/power-entry/poses-pfc-02.json').read_bytes()).hexdigest(),'status':'explicit native placement, unrouted; DRC and mechanical review required'},indent=2)+'\n')
