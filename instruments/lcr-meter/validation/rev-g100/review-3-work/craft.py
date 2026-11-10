"""Craft rules: (1) T-junctions: a track end that lands on the interior of another same-net, same-layer track
(not at its end) and not inside a pad; (2) bends: angle between joined segments not a multiple of 45 deg;
(3) pad entry: a track leaving an SMD pad must be along the pad's axis through the centre (its first segment passes
through the pad centre and is parallel to a pad axis). Compares against routing.json craft_exceptions.
Output work/craft.txt"""
import sys, json; sys.path.insert(0,'work')
from lib_board import *
b=load(); T=[t for t in tracks(b) if t['kind']=='track']; V=[t for t in tracks(b) if t['kind']=='via']; P=pads(b)
exc=json.load(open('cad/routing.json'))['craft_exceptions']
exc_pts={(round(e['at'][0],2),round(e['at'][1],2)):e for e in exc}
def inpad(p, layer):
    for pd in P:
        if layer in pd['layers'] or pd['th']:
            bb=pd['obj'].GetBoundingBox()
            if mm(bb.GetLeft())-0.01<=p[0]<=mm(bb.GetRight())+0.01 and mm(bb.GetTop())-0.01<=p[1]<=mm(bb.GetBottom())+0.01: return pd
    return None
out=[]; tj=[]
from collections import defaultdict
byln=defaultdict(list)
for t in T: byln[(t['layer'],t['net'])].append(t)
for (l,n),ts in byln.items():
    for t in ts:
        for end in (t['a'],t['b']):
            for u in ts:
                if u is t: continue
                if dist(end,u['a'])<0.01 or dist(end,u['b'])<0.01: continue
                if seg_dist(end,u['a'],u['b'])<0.01:
                    if inpad(end,l): continue
                    if any(dist(end,v['at'])<0.01 for v in V): continue
                    tj.append((n,l,end))
out.append(f"T-junctions: {len(tj)}")
for n,l,e in sorted(set((n,l,(round(e[0],2),round(e[1],2))) for n,l,e in tj)): out.append(f"   {n:14s} {l:7s} ({e[0]:.2f},{e[1]:.2f})")
# bends
bends=[]
for (l,n),ts in byln.items():
    ends=defaultdict(list)
    for t in ts:
        ends[(round(t['a'][0],3),round(t['a'][1],3))].append((t,t['b']))
        ends[(round(t['b'][0],3),round(t['b'][1],3))].append((t,t['a']))
    for k,lst in ends.items():
        if len(lst)!=2: continue
        (t1,o1),(t2,o2)=lst
        a1=math.degrees(math.atan2(o1[1]-k[1],o1[0]-k[0])); a2=math.degrees(math.atan2(o2[1]-k[1],o2[0]-k[0]))
        d=abs((a1-a2+180)%360-180)
        if dist(o1,k)<0.3 or dist(o2,k)<0.3: continue
        if inpad(k,l): continue
        r=d%45
        if min(r,45-r)>1.0:
            bends.append((n,l,k,d))
        elif abs(d-90)<1.0 and (round(k[0],2),round(k[1],2)) not in exc_pts:
            bends.append((n,l,k,d))
out.append(f"non-45-multiple or 90-deg bends not in craft_exceptions: {len(bends)}")
for n,l,k,d in bends: out.append(f"   {n:14s} {l:7s} ({k[0]:.2f},{k[1]:.2f}) angle {d:.1f}")
# pad entry
pe=[]
for pd in P:
    if pd['th'] or pd['ref'].startswith('TP') or pd['ref'].startswith('FID'): continue
    bb=pd['obj'].GetBoundingBox(); x1,y1,x2,y2=mm(bb.GetLeft()),mm(bb.GetTop()),mm(bb.GetRight()),mm(bb.GetBottom())
    for t in T:
        if t['net']!=pd['net'] or t['layer'] not in pd['layers']: continue
        for e,o in ((t['a'],t['b']),(t['b'],t['a'])):
            if x1-0.005<=e[0]<=x2+0.005 and y1-0.005<=e[1]<=y2+0.005 and not (x1-0.005<=o[0]<=x2+0.005 and y1-0.005<=o[1]<=y2+0.005):
                # entering segment: direction
                dx,dy=o[0]-e[0],o[1]-e[1]; L=math.hypot(dx,dy)
                if L<0.02: continue
                ang=math.degrees(math.atan2(dy,dx))%180
                rot=pd['rot']%180
                axis=abs((ang-rot+90)%180-90)
                axis=min(axis, abs(axis-90))
                # offset of the line from the pad centre
                c=pd['at']; off=abs((c[0]-e[0])*dy-(c[1]-e[1])*dx)/L
                if axis>1.0 or off>0.03:
                    key=(round(e[0],2),round(e[1],2))
                    if key in exc_pts or any(dist(e,(ex['at'][0],ex['at'][1]))<0.05 for ex in exc if ex.get('land')==f"{pd['ref']}.{pd['num']}"): continue
                    pe.append((pd['ref'],pd['num'],pd['net'],t['layer'],e,axis,off))
out.append(f"pad entries off-axis or off-centre (not in craft_exceptions): {len(pe)}")
for r,nn,n,l,e,ax,off in pe: out.append(f"   {r}.{nn} {n:14s} {l:7s} at ({e[0]:.2f},{e[1]:.2f}) axis-dev {ax:.0f} deg, centre offset {off:.2f} mm")
open('work/craft.txt','w').write('\n'.join(out)+'\n'); print('\n'.join(out))
