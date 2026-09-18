"""Serialize only agent-authored polylines; no route search or acceptance logic."""
from pathlib import Path
import json, hashlib
import pcbnew as p
ROOT=Path(__file__).resolve().parents[1]
board_path=ROOT/'candidate/section.kicad_pcb'
io=p.PCB_IO_KICAD_SEXPR()
b=io.LoadBoard(str(board_path),None)
raw=(ROOT/'routes.json').read_bytes()
instructions=json.loads(raw)
pads={}
for f in b.GetFootprints():
 for pad in f.Pads():
  key=f.GetReference()+'.'+pad.GetNumber()
  pads[key]=None if key in pads else pad

def point(value,net):
 if isinstance(value,str):
  pad=pads[value]
  if pad is None:raise ValueError('Ambiguous duplicate pad '+value)
  if pad.GetNetname()!=net:raise ValueError('Net mismatch '+value)
  return pad.GetPosition()
 return p.VECTOR2I(*(p.FromMM(v) for v in value))

before=hashlib.sha256(board_path.read_bytes()).hexdigest()
for route in instructions['paths']:
 net=b.FindNet(route['net'])
 if not net:raise ValueError('Unknown net '+route['net'])
 points=[point(v,route['net']) for v in route['points']]
 for start,end in zip(points,points[1:]):
  t=p.PCB_TRACK(b);t.SetStart(start);t.SetEnd(end);t.SetWidth(p.FromMM(route['width_mm']));t.SetLayer(b.GetLayerID(route['layer']));t.SetNet(net);b.Add(t)
for v in instructions['vias']:
 t=p.PCB_VIA(b);t.SetPosition(point(v['at'],v['net']));t.SetWidth(p.FromMM(v['diameter_mm']));t.SetDrill(p.FromMM(v['drill_mm']));t.SetViaType(p.VIATYPE_THROUGH);t.SetLayerPair(p.F_Cu,p.B_Cu);t.SetNet(b.FindNet(v['net']));b.Add(t)
b.BuildConnectivity()
for z in b.Zones():z.UnFill()

io.SaveBoard(str(board_path),b)
(ROOT/'evidence/routes-receipt.json').write_text(json.dumps({'input_board_sha256':before,'routes_sha256':hashlib.sha256(raw).hexdigest(),'output_board_sha256':hashlib.sha256(board_path.read_bytes()).hexdigest(),'paths':len(instructions['paths']),'status':'applied-validation-pending'},indent=2)+'\n')
