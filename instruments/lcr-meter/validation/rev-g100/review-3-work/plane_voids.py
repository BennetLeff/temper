"""In1 plane integrity and return paths.
1. Fill the zones (in memory only), take In1's filled polygon, list every hole larger than a via antipad.
2. For every track on F.Cu / In2.Cu / B.Cu, find segments that cross a hole in In1 (no return under them), and
   the In1 keep-out rectangles. Output work/plane_voids.txt"""
import sys; sys.path.insert(0,'work')
from lib_board import *
b=load()
filler=pcbnew.ZONE_FILLER(b); filler.Fill(b.Zones())
T=tracks(b)
res=[]
for z in b.Zones():
    if z.GetNetname()!='GND': continue
    for l in z.GetLayerSet().Seq():
        ln=b.GetLayerName(l)
        if ln not in ('In1.Cu','In2.Cu','B.Cu'): continue
        poly=pcbnew.SHAPE_POLY_SET(z.GetFilledPolysList(l)); poly.Unfracture()
        res.append(f"== {ln} GND zone: {poly.OutlineCount()} outlines")
        for i in range(poly.OutlineCount()):
            o=poly.Outline(i)
            bb=o.BBox()
            res.append(f"  outline {i}: bbox {mm(bb.GetLeft()):.1f},{mm(bb.GetTop()):.1f} - {mm(bb.GetRight()):.1f},{mm(bb.GetBottom()):.1f} area {abs(o.Area())/1e12:.1f} mm2 holes {poly.HoleCount(i)}")
            holes=[]
            for h in range(poly.HoleCount(i)):
                hp=poly.Hole(i,h); hb=hp.BBox(); area=abs(hp.Area())/1e12
                holes.append((area, mm(hb.GetLeft()),mm(hb.GetTop()),mm(hb.GetRight()),mm(hb.GetBottom())))
            holes.sort(reverse=True)
            for area,x1,y1,x2,y2 in holes:
                if area>1.5: res.append(f"    hole {area:6.1f} mm2  bbox {x1:.2f},{y1:.2f} - {x2:.2f},{y2:.2f}  ({x2-x1:.2f} x {y2-y1:.2f})")
            if ln=='In1.Cu':
                big=[(a,x1,y1,x2,y2) for a,x1,y1,x2,y2 in holes if a>1.5]
                # tracks on other layers crossing these holes
                res.append("  -- tracks on other layers over In1 holes > 1.5 mm2 (segment clipped length > 0.3 mm):")
                for t in T:
                    if t['kind']!='track' or t['layer']=='In1.Cu': continue
                    for a,x1,y1,x2,y2 in big:
                        # clip segment to rect (Liang-Barsky)
                        (ax,ay),(bx,by)=t['a'],t['b']
                        dx,dy=bx-ax,by-ay; t0,t1=0.0,1.0; ok=True
                        for p,q in ((-dx,ax-x1),(dx,x2-ax),(-dy,ay-y1),(dy,y2-ay)):
                            if p==0:
                                if q<0: ok=False;break
                            else:
                                r=q/p
                                if p<0: t0=max(t0,r)
                                else: t1=min(t1,r)
                        if ok and t0<t1:
                            L=math.hypot(dx,dy)*(t1-t0)
                            if L>0.3:
                                res.append(f"     {t['net']:14s} {t['layer']:7s} ({ax:.2f},{ay:.2f})-({bx:.2f},{by:.2f}) over hole {x1:.1f},{y1:.1f}-{x2:.1f},{y2:.1f}: {L:.2f} mm")
open('work/plane_voids.txt','w').write('\n'.join(res)+'\n'); print('\n'.join(res))
