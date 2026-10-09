# Fit check of a 10x38 clip pair replacing F1 on native-21 stage 11 (read-only).
import pcbnew, sys, math, json
b=pcbnew.LoadBoard(sys.argv[1]); mm=pcbnew.ToMM
HOT_SKIP={'F1'}
def rect_dist(a,b_):
    ax0,ay0,ax1,ay1=a; bx0,by0,bx1,by1=b_
    dx=max(bx0-ax1, ax0-bx1, 0); dy=max(by0-ay1, ay0-by1, 0); return math.hypot(dx,dy)
def overlap(a,b_): return not (a[2]<=b_[0] or b_[2]<=a[0] or a[3]<=b_[1] or b_[3]<=a[1])
# collect other footprints' courtyards and pads
fps=[]; pads=[]
for fp in b.GetFootprints():
    ref=fp.GetReference()
    if ref in HOT_SKIP: continue
    cy=fp.GetCourtyard(pcbnew.F_CrtYd)
    if cy.OutlineCount():
        r=cy.BBox(); fps.append((ref,(mm(r.GetX()),mm(r.GetY()),mm(r.GetRight()),mm(r.GetBottom()))))
    for p in fp.Pads():
        bb=p.GetBoundingBox(); pads.append((ref,p.GetNumber(),p.GetNetname(),(mm(bb.GetX()),mm(bb.GetY()),mm(bb.GetRight()),mm(bb.GetBottom())), p.GetAttribute()==pcbnew.PAD_ATTRIB_PTH))
trks=[]
for t in b.GetTracks():
    bb=t.GetBoundingBox(); trks.append((t.GetNetname(), b.GetLayerName(t.GetLayer()) if t.GetClass()!="PCB_VIA" else "via",(mm(bb.GetX()),mm(bb.GetY()),mm(bb.GetRight()),mm(bb.GetBottom()))))
def candidate(name,cx,cy,pins,pad_ax,pad_tr,crt_half_ax,crt_half_tr,body):
    # pins: list of (dx, net)  along x; pads rectangles approx
    print(f"\n=== {name} centre ({cx},{cy})")
    newpads=[(net,(cx+dx-pad_ax/2,cy-pad_tr/2,cx+dx+pad_ax/2,cy+pad_tr/2)) for dx,net in pins]
    crt=(cx-crt_half_ax,cy-crt_half_tr,cx+crt_half_ax,cy+crt_half_tr)
    print(" courtyard", tuple(round(v,2) for v in crt), "board edge y=0 -> top gap", round(crt[1],2))
    for ref,r in fps:
        d=rect_dist(crt,r)
        if overlap(crt,r) or d<3: print(f"  crtyd vs {ref}: {'OVERLAP' if overlap(crt,r) else 'gap'} {d:.2f}  ({tuple(round(v,2) for v in r)})")
    worst=[]
    for net,pr in newpads:
        for ref,num,pn,r,pth in pads:
            if pn==net or pn=='' : continue
            d=rect_dist(pr,r)
            if d<6: worst.append((round(d,2),f"pad {net} vs {ref}.{num} {pn}"))
        for tn,lay,r in trks:
            if tn==net: continue
            d=rect_dist(pr,r)
            if d<6: worst.append((round(d,2),f"pad {net} vs track/via {tn} {lay}"))
    for net_body,bx in body:
        bxr=(cx+bx[0],cy+bx[1],cx+bx[2],cy+bx[3])
        for tn,lay,r in trks:
            if tn==net_body or lay not in("F.Cu",): continue
            d=rect_dist(bxr,r)
            if d<4: worst.append((round(d,2),f"clip-envelope {net_body} vs F.Cu track {tn}"))
    for w in sorted(set(worst))[:14]: print("  ",w)
    return newpads,crt
# Littelfuse 01250003H x2: slots 1.2x2.5 at +-10.08, +-20.88; pad 2.4 (ax) x 3.7 (tr); body 11.1 ax x 12.5 tr centred +-15.48
lf=[(-20.88,'l_f'),(-10.08,'l_f'),(10.08,'ac_l_in'),(20.88,'ac_l_in')]
for cx,cy in [(250.0,7.25),(250.0,6.85),(252.0,7.25),(247.5,7.25)]:
    candidate("LF 125 (01250003H x2)",cx,cy,lf,2.4,3.7,22.6,6.75,
      [('l_f',(-21.03,-6.25,-9.93,6.25)),('ac_l_in',(9.93,-6.25,21.03,6.25))])
# Schurter CSO THT x2: pins 2.35 at +-7.5,+-22.5 ; pad 4.0 ; body 12 ax x 13.8 tr at +-15
cso=[(-22.5,'l_f'),(-7.5,'l_f'),(7.5,'ac_l_in'),(22.5,'ac_l_in')]
candidate("Schurter CSO 0751.0507 x2",250.0,7.6,cso,4.0,4.0,25.0,7.4,
      [('l_f',(-21,-6.9,-9,6.9)),('ac_l_in',(9,-6.9,21,6.9))])
