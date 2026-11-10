"""Mechanical / DFM: copper near M3 holes (all layers), parts near holes, parts over the outline, silk text heights,
courtyard overlaps between parts, parts within 1 mm of the edge, tall parts. Output work/mech.txt"""
import sys; sys.path.insert(0,'work')
from lib_board import *
b=load(); P=pads(b); T=tracks(b)
out=[]
holes=[(54,54),(146,54),(54,141),(146,141)]
out.append("== copper within 3.5 mm of M3 hole centres (standoff keep-out), per layer")
for h in holes:
    for t in T:
        if t['kind']=='track':
            d=seg_dist(h,t['a'],t['b'])-t['w']/2
            if d<3.5: out.append(f"  hole {h}: track {t['net']} {t['layer']} ({t['a'][0]:.2f},{t['a'][1]:.2f})-({t['b'][0]:.2f},{t['b'][1]:.2f}) w{t['w']} edge at {d:.2f} mm")
        else:
            d=dist(h,t['at'])-t['dia']/2
            if d<3.5: out.append(f"  hole {h}: via {t['net']} at {t['at']} edge at {d:.2f} mm")
    for p in P:
        if p['ref'].startswith('H'): continue
        bb=p['obj'].GetBoundingBox(); 
        dx=max(mm(bb.GetLeft())-h[0], 0, h[0]-mm(bb.GetRight())); dy=max(mm(bb.GetTop())-h[1],0,h[1]-mm(bb.GetBottom()))
        d=math.hypot(dx,dy)
        if d<3.5: out.append(f"  hole {h}: pad {p['ref']}.{p['num']} {p['net']} {p['layers']} edge at {d:.2f} mm")
# zones: filled copper near holes
filler=pcbnew.ZONE_FILLER(b); filler.Fill(b.Zones())
for z in b.Zones():
    if z.GetIsRuleArea() or z.GetNetname()!='GND': continue
    for l in z.GetLayerSet().Seq():
        poly=z.GetFilledPolysList(l)
        for h in holes:
            d=None
            for i in range(poly.OutlineCount()):
                o=poly.Outline(i)
                for k in range(o.PointCount()):
                    a=o.CPoint(k); c=o.CPoint((k+1)%o.PointCount())
                    dd=seg_dist(h,(mm(a.x),mm(a.y)),(mm(c.x),mm(c.y)))
                    d=dd if d is None or dd<d else d
            out.append(f"  hole {h}: {b.GetLayerName(l)} GND pour edge nearest {d:.2f} mm from centre (ring void radius)")
out.append("== footprint courtyard / bbox outside the outline (50..150 x 45..145)")
for fp in b.GetFootprints():
    bb=fp.GetBoundingBox(False,False)
    x1,y1,x2,y2=mm(bb.GetLeft()),mm(bb.GetTop()),mm(bb.GetRight()),mm(bb.GetBottom())
    if x1<50 or y1<45 or x2>150 or y2>145: out.append(f"  {fp.GetReference()} bbox {x1:.2f},{y1:.2f}-{x2:.2f},{y2:.2f}")
out.append("== silk text height < 1.0 mm or thickness < 0.15 (JLC) on F.Silkscreen")
n=0
for d in b.GetDrawings():
    if d.GetClass() in ('PCB_TEXT','PCB_FIELD') and b.GetLayerName(d.GetLayer())=='F.Silkscreen':
        h=mm(d.GetTextHeight()); th=mm(d.GetTextThickness())
        if h<1.0 or th<0.15: out.append(f"  text '{d.GetText()[:30]}' h {h} th {th} at {pt(d.GetPosition())}"); n+=1
for fp in b.GetFootprints():
    for it in list(fp.GraphicalItems())+[fp.Reference(), fp.Value()]:
        if it.GetClass() in ('PCB_TEXT','PCB_FIELD') and b.GetLayerName(it.GetLayer())=='F.Silkscreen' and it.IsVisible():
            h=mm(it.GetTextHeight()); th=mm(it.GetTextThickness())
            if h<1.0 or th<0.15: out.append(f"  {fp.GetReference()} text '{it.GetText()[:20]}' h {h} th {th}"); n+=1
        if it.GetClass()=='PCB_SHAPE' and b.GetLayerName(it.GetLayer())=='F.Silkscreen' and mm(it.GetWidth())<0.15:
            out.append(f"  {fp.GetReference()} silk line width {mm(it.GetWidth())}"); n+=1
out.append(f"  ({n} items)")
out.append("== B.Silkscreen items (fab note says bottom silk intentionally empty)")
nb=0
for fp in b.GetFootprints():
    for it in list(fp.GraphicalItems())+[fp.Reference(), fp.Value()]:
        if b.GetLayerName(it.GetLayer())=='B.Silkscreen' and (not hasattr(it,'IsVisible') or it.IsVisible()): nb+=1
for d in b.GetDrawings():
    if b.GetLayerName(d.GetLayer())=='B.Silkscreen': nb+=1
out.append(f"  {nb} items")
out.append("== reference designators not on F.Silkscreen (visible) / not on F.Fab")
for fp in b.GetFootprints():
    r=fp.Reference()
    if not r.IsVisible() or b.GetLayerName(r.GetLayer())!='F.Silkscreen':
        # is there a silk text with the ref elsewhere?
        found=any(d.GetClass() in('PCB_TEXT',) and d.GetText()==fp.GetReference() and b.GetLayerName(d.GetLayer())=='F.Silkscreen' for d in b.GetDrawings())
        fab=any(it.GetClass() in('PCB_TEXT','PCB_FIELD') and it.GetText()==fp.GetReference() and b.GetLayerName(it.GetLayer())=='F.Fab' for it in list(fp.GraphicalItems())+[fp.Reference()]) or any(d.GetClass()=='PCB_TEXT' and d.GetText()==fp.GetReference() and b.GetLayerName(d.GetLayer())=='F.Fab' for d in b.GetDrawings())
        if not found: out.append(f"  {fp.GetReference()}: ref not on silk (fab drawing: {'yes' if fab else 'NO'})")
out.append("== part-to-part bbox gap < 0.25 mm (SMT, JLC assembly)")
fps=[(fp.GetReference(), fp.GetBoundingBox(False,False)) for fp in b.GetFootprints() if not fp.GetReference().startswith(('H','FID','TP'))]
for i in range(len(fps)):
    for j in range(i+1,len(fps)):
        r1,b1=fps[i]; r2,b2=fps[j]
        gx=max(mm(b2.GetLeft())-mm(b1.GetRight()), mm(b1.GetLeft())-mm(b2.GetRight()))
        gy=max(mm(b2.GetTop())-mm(b1.GetBottom()), mm(b1.GetTop())-mm(b2.GetBottom()))
        g=max(gx,gy)
        if g<0.25: out.append(f"  {r1}-{r2}: gap {g:.2f} mm")
out.append("== tallest parts / overhang notes: J1, BNCs, C117 (8 mm dia, 6.9 tall), L1/L2 (5x5x4), relays")
open('work/mech.txt','w').write('\n'.join(out)+'\n'); print('\n'.join(out))
