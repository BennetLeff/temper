"""Apply explicit candidate placement/net edits to the routed passive baseline.

No routing search or engineering verdict is implemented here. New copper is
specified by the agent in routes.json and checked by the native/Rust tools.
"""
from pathlib import Path
import json
import pcbnew as p
ROOT=Path(__file__).resolve().parents[1]
REPO=ROOT.parents[2]
io=p.PCB_IO_KICAD_SEXPR()
base=io.LoadBoard(str(ROOT.parent/'shunt-repair/candidate/section.kicad_pcb'),None)
fresh=io.LoadBoard(str(ROOT/'native-source-unrouted.kicad_pcb'),None)
# Source-derived identities, not a reconstructed circuit.
newfp={f.GetReference():f for f in fresh.GetFootprints()}
pin_net={(f.GetReference(),pad.GetNumber()):pad.GetNetname() for f in fresh.GetFootprints() for pad in f.Pads() if pad.GetNumber()}
rename={'plus':'RECTIFIER_POSITIVE','minus':'RECTIFIER_NEGATIVE','ac1':'RECTIFIER_L','ac2':'RECTIFIER_R'}
for n in fresh.GetNetInfo().NetsByNetcode().values():
 if n.GetNetname() and not base.FindNet(n.GetNetname()):base.Add(p.NETINFO_ITEM(base,n.GetNetname()))
# Remove obsolete bridge branches, and split only reviewed bank-positive copper.
remove={
'33cdb604-2e4a-49a4-bcca-80b829c3818c','6c5554bb-f497-487d-aeac-ad0ad80259bc',
'530155a0-5859-4387-be82-53e370fc79e5','c060f5f6-a3d7-4399-923b-4094c1d4c60e',
'8e49f7cf-5c7a-4b79-9cb4-c1cbe398fc62','bdc6f92e-74a7-4e0e-80df-743886e67f7b',
'2c143aeb-e5a9-4abb-9449-b76a8967f49a','6d45e4d9-945b-4e98-ae6f-85d60f0469aa',
'7fdb5978-8270-4f18-803d-d4cc0c691884','da3bcf49-d36b-4ce3-9d6f-3bd861c9f9e7','db31ea03-4a84-4ffb-a104-546559df82f3','fcbfb9cb-ae96-4261-8ec9-a57c3db7f95d',
'2d1e2fc8-943b-4320-baf2-429d438a2ef4','f98a1626-1fd2-40b6-a2d7-ac36935daa4a',
'6d2b41e7-43c2-4ff8-9319-787da2aa60f4','c45d59b8-60e9-487c-8932-56c32cb7c63e'}
diode={'954a68d8-8c29-4706-8ddb-251c8518a7a2','ff4fe944-8cd7-4b47-abb1-6eea457d35a0'}
for item in list(base.GetTracks()):
 uid=item.m_Uuid.AsString()
 if uid in remove:base.Remove(item);continue
 net='BOOST_DIODE_POSITIVE' if uid in diode else rename.get(item.GetNetname(),item.GetNetname())
 if net:item.SetNet(base.FindNet(net))
for z in base.Zones():
 net=rename.get(z.GetNetname(),z.GetNetname())
 if net:z.SetNet(base.FindNet(net))
poses=json.loads((ROOT/'poses.json').read_text())
manifest=json.loads((ROOT/'candidate/source-manifest.json').read_text())
paths={c['reference']:c['instance_path'] for c in manifest['bridge']['components']}
for f in list(base.GetFootprints()):
 if f.GetReference()=='U1':base.Remove(f)
for ref,nf in newfp.items():
 fs=[f for f in base.GetFootprints() if f.GetReference()==ref]
 if fs:f=fs[0]
 else:
  lib, stem=next(c['footprint'] for c in manifest['bridge']['components'] if c['reference']==ref).split(':',1)
  f=p.FootprintLoad(str(ROOT/'candidate/candidate-libs'/(lib+'.pretty')),stem)
  f.SetReference(ref);base.Add(f)
 x,y,a=poses[paths[ref]]
 f.SetPosition(p.VECTOR2I(p.FromMM(x),p.FromMM(y)));f.SetOrientationDegrees(a)
 attrs=manifest['source_attributes'][paths[ref]]
 f.SetField('SourceInstance',paths[ref]);f.SetField('MPN',attrs['mpn']);f.SetField('Datasheet',attrs.get('datasheet',''));f.SetValue(nf.GetValue());f.SetFPID(nf.GetFPID());f.SetPath(nf.GetPath())
 for pad in f.Pads():
  net=pin_net.get((ref,pad.GetNumber()),'')
  if ref=='U1' and pad.GetNumber() in ['4','9','11','15']:net=''
  pad.SetNet(base.FindNet(net) if net else base.FindNet(0))
# Extra construction area for the experimental line-frequency bridge.
for d in list(base.GetDrawings()):
 if d.GetLayer()==p.Edge_Cuts:base.Remove(d)
for a,b in [((-80,0),(230,0)),((230,0),(230,210)),((230,210),(-80,210)),((-80,210),(-80,0))]:
 d=p.PCB_SHAPE();d.SetShape(p.SHAPE_T_SEGMENT);d.SetLayer(p.Edge_Cuts);d.SetWidth(p.FromMM(.05));d.SetStart(p.VECTOR2I(*(p.FromMM(v) for v in a)));d.SetEnd(p.VECTOR2I(*(p.FromMM(v) for v in b)));base.Add(d)
# Existing power copper is retained at original UUIDs except the named edits.
base.BuildConnectivity()
io.SaveBoard(str(ROOT/'candidate/section.kicad_pcb'),base)
print('Applied explicit baseline net/placement edits; routing and validation pending')
