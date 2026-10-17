import pcbnew,json,sys,hashlib
from pathlib import Path
p=Path(sys.argv[1]);b=pcbnew.LoadBoard(str(p));result={}
for net in ('leg_a-out_h','leg_a-out_l','leg_b-out_h','leg_b-out_l'):
 tracks=[t for t in b.GetTracks() if t.GetNetname()==net and t.GetClass()=='PCB_TRACK']
 result[net]={'authored_track_total_mm':sum(pcbnew.ToMM(t.GetLength()) for t in tracks),'segments':len(tracks),'layers':sorted({t.GetLayerName() for t in tracks})}
print(json.dumps({'board_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'method':'sum KiCad straight track lengths on each unbranched driver-output net, excludes resistor-to-gate net','results':result},indent=2))
