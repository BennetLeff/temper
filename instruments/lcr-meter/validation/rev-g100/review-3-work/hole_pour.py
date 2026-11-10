"""GND pour edge distance from the four M3 hole centres on B.Cu / In1 / In2 (output work/hole_pour.txt)."""
import sys; sys.path.insert(0,'work')
from lib_board import *
b=load(); filler=pcbnew.ZONE_FILLER(b); filler.Fill(b.Zones())
holes=[(54,54),(146,54),(54,141),(146,141)]
for z in b.Zones():
    if z.GetIsRuleArea() or z.GetNetname()!='GND': continue
    for l in z.GetLayerSet().Seq():
        ln=b.GetLayerName(l)
        if ln not in('B.Cu','In2.Cu','In1.Cu'): continue
        poly=pcbnew.SHAPE_POLY_SET(z.GetFilledPolysList(l)); poly.Unfracture()
        if poly.OutlineCount()==0: continue
        for h in holes:
            best=None
            for i in range(poly.OutlineCount()):
                for hh in range(-1, poly.HoleCount(i)):
                    o=poly.Outline(i) if hh<0 else poly.Hole(i,hh)
                    for k in range(o.PointCount()):
                        a=o.CPoint(k); c=o.CPoint((k+1)%o.PointCount())
                        d=seg_dist(h,(mm(a.x),mm(a.y)),(mm(c.x),mm(c.y)))
                        if best is None or d<best: best=d
            inside=poly.Contains(pcbnew.VECTOR2I(int((h[0]+2.5)*1e6),int(h[1]*1e6)))
            print(f"{ln} GND pour: hole {h}: nearest pour edge {best:.2f} mm from centre (hole edge at 1.60); copper present 2.5 mm east of centre: {inside}")
