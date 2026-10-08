"""Live KiCad transport regression; explicit fixture geometry, no routing search."""
import hashlib
import json
from pathlib import Path
import sys
import pcbnew

REPO = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(REPO / 'harness-lab'), str(REPO / 'zapote/rtd')]
import block_native
import buck_native
import apply_routes

out = Path(sys.argv[1]).resolve()
out.mkdir(parents=True, exist_ok=True)
path = out / 'adapter.kicad_pcb'
board = pcbnew.BOARD()
net = pcbnew.NETINFO_ITEM(board, 'gnd')
board.Add(net)
fp = pcbnew.FOOTPRINT(board)
fp.SetReference('J1')
fp.SetPosition(buck_native.position(5, 5))
pad = pcbnew.PAD(fp)
pad.SetNumber('1')
pad.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
pad.SetSize(buck_native.position(1.5, 1.5))
pad.SetDrillSize(buck_native.position(0.8, 0.8))
pad.SetLayerSet(pcbnew.LSET.AllCuMask())
pad.SetPosition(buck_native.position(5, 5))
pad.SetNet(net)
fp.Add(pad)
board.Add(fp)
for a,b in [((0,0),(10,0)),((10,0),(10,10)),((10,10),(0,10)),((0,10),(0,0))]:
 edge=pcbnew.PCB_SHAPE(board)
 edge.SetShape(pcbnew.SHAPE_T_SEGMENT)
 edge.SetStart(buck_native.position(*a));edge.SetEnd(buck_native.position(*b))
 edge.SetLayer(pcbnew.Edge_Cuts);edge.SetWidth(pcbnew.FromMM(.05));board.Add(edge)
buck_native.save(board,path)
zone = {'layer':'B.Cu','outline_mm':[[1,1],[9,1],[9,9],[1,9]],'clearance_mm':.22,'priority':2}
block_native.replace_copper(path,'gnd',[],[],[zone])
first = buck_native.load(path)
old = first.Zones()[0].m_Uuid.AsString()
# Regression: deleting an existing native zone and constructing a new one.
zone['outline_mm']=[[2,2],[8,2],[8,8],[2,8]]
block_native.replace_copper(path,'gnd',[],[],[zone])
second=buck_native.load(path)
assert len(list(second.Zones())) == 1
z=second.Zones()[0]
assert z.m_Uuid.AsString()!=old
assert z.GetAssignedPriority()==2
assert abs(pcbnew.ToMM(z.GetLocalClearance())-.22)<1e-6
outline=pcbnew.Cast_to_SHAPE_POLY_SET(z.Outline())
assert outline.TotalVertices()==4
# Fail after a valid first operation: the destination bytes must stay intact.
instruction=out/'intentional-failure.json'
instruction.write_text(json.dumps({'nets':[
 {'net':'gnd','paths':[{'points':[[5,5],[6,5]],'layer':'B.Cu','width_mm':.3}]},
 {'net':'gnd','paths':[{'points':['MISSING.1',[7,5]],'layer':'B.Cu','width_mm':.3}]}]}))
before=path.read_bytes()
try:
 apply_routes.run(path,instruction,out/'should-not-exist.json')
except KeyError:
 pass
else:
 raise AssertionError('missing native pad accepted')
assert path.read_bytes()==before
assert not (out/'should-not-exist.json').exists()
receipt={'status':'PASS','kicad_version':pcbnew.Version(),'checks':['existing zone deletion/new zone/native save reload','zone priority and clearance survive serialization','late operation failure leaves destination bytes unchanged'], 'board_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'inputs':{str(p.relative_to(REPO)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__),REPO/'harness-lab/block_native.py',REPO/'harness-lab/buck_native.py',REPO/'zapote/rtd/apply_routes.py']},'native_refill':'PENDING'}
(out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps(receipt,indent=2))
