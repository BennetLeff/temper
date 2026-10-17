import json,sys
import pcbnew as p
src,dst=sys.argv[1:3]
b=p.LoadBoard(src);out=[];mm=p.ToMM
for z in b.Zones():
 if z.GetIsRuleArea():continue
 for lid in (p.F_Cu,p.In1_Cu,p.In2_Cu,p.B_Cu):
  if not z.IsOnLayer(lid):continue
  q=z.GetFilledPolysList(lid)
  for i in range(q.OutlineCount()):
   o=q.Outline(i)
   shell=[[mm(o.CPoint(k).x),mm(o.CPoint(k).y)] for k in range(o.PointCount())]
   holes=[]
   for h in range(q.HoleCount(i)):
    ho=q.Hole(i,h)
    holes.append([[mm(ho.CPoint(k).x),mm(ho.CPoint(k).y)] for k in range(ho.PointCount())])
   out.append(dict(net=z.GetNetname(),layer=b.GetLayerName(lid),shell=shell,holes=holes))
json.dump(out,open(dst,'w'))
print(len(out),sum(len(p['holes']) for p in out))
