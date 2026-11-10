"""Exposed pads: via count inside each EP, via tenting flags (front/back), paste apertures on the EP (coverage),
and any via touching an SMT land that is not an EP (fab note 4 promise). Output work/ep_vias_paste.txt"""
import sys; sys.path.insert(0,'work')
from lib_board import *
b=load(); P=pads(b); V=[t for t in tracks(b) if t['kind']=='via']
out=[]
def inside(p,pd):
    bb=pd['obj'].GetBoundingBox(); return mm(bb.GetLeft())<=p[0]<=mm(bb.GetRight()) and mm(bb.GetTop())<=p[1]<=mm(bb.GetBottom())
for pd in P:
    if pd['th']: continue
    vs=[v for v in V if inside(v['at'],pd)]
    if vs:
        o=vs[0]['obj']
        tent=''
        try:
            tent=f"front tented {o.IsTented(pcbnew.F_Mask)} back tented {o.IsTented(pcbnew.B_Mask)}"
        except Exception as e:
            try: tent=f"front/back tenting {o.Padstack().FrontOuterLayers().has_solder_mask} / {o.Padstack().BackOuterLayers().has_solder_mask}"
            except Exception as e2: tent=f"(tenting api n/a: {e2})"
        out.append(f"{pd['ref']}.{pd['num']} {pd['net']} size {pd['size']}: {len(vs)} vias; drill {vs[0]['drill']} dia {vs[0]['dia']}; {tent}")
# paste on EP pads: look at F.Paste shapes: pad's paste layer presence + any paste-only pads / zones
out.append("== paste on exposed pads (pad has F.Paste layer? plus separate paste-only pads / graphics inside it)")
for pd in P:
    if pd['size'][0]>=1.5 and pd['size'][1]>=1.5 and not pd['th'] and pd['ref'].startswith('U'):
        ls=[b.GetLayerName(l) for l in pd['obj'].GetLayerSet().Seq()]
        has='F.Paste' in ls
        ratio=pd['obj'].GetLocalSolderPasteRatio() if hasattr(pd['obj'],'GetLocalSolderPasteRatio') else None
        # other pads inside
        sub=[q for q in P if q is not pd and q['fp'] is pd['fp'] and inside(q['at'],pd)]
        gi=[g for g in pd['fp'].GraphicalItems() if b.GetLayerName(g.GetLayer())=='F.Paste']
        out.append(f"  {pd['ref']}.{pd['num']} {pd['size']} F.Paste on pad: {has}; paste ratio {ratio}; sub-pads inside {len(sub)}; F.Paste graphics in fp {len(gi)}")
# vias touching any SMT land that is not an EP
out.append("== vias touching SMT lands (not EP)")
for pd in P:
    if pd['th'] or (pd['ref'].startswith('U') and pd['size'][0]>=1.5 and pd['size'][1]>=1.5): continue
    for v in V:
        if 'F.Cu' in pd['layers'] and dist(v['at'],pd['at'])<(max(pd['size'])/2+v['dia']/2):
            sh=pd['obj'].GetEffectiveShape(pcbnew.F_Cu); vs=v['obj'].GetEffectiveShape(pcbnew.F_Cu)
            if sh.Collide(vs,0): out.append(f"  {pd['ref']}.{pd['num']} {pd['net']} <- via ({v['at'][0]:.2f},{v['at'][1]:.2f})")
open('work/ep_vias_paste.txt','w').write('\n'.join(out)+'\n'); print('\n'.join(out))
