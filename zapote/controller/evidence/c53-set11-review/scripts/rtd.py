from lib import *
from shapely.strtree import STRtree
an=[n for n in N['nets'] if n.startswith('rtd') or n in('refin_n','vbias','HS_SENSE','COIL_SENSE','RIM_SENSE','vbus_p','vbus_n','ct_mon','rms_in','m12_node','bay_node','p1') or 'bias' in n.lower() or 'refin' in n]
an=[n for n in an if n not in('bias_good_j4','BIAS_GOOD')]
tr=B['tracks']; geoms=[LineString([(t['x1'],t['y1']),(t['x2'],t['y2'])]) for t in tr]; tree=STRtree(geoms)
in1=unary_union([p for _,_,p in zonepolys('selv_gnd','In1.Cu')])
in4=unary_union([p for _,_,p in zonepolys('selv_gnd','In4.Cu')])
for n in sorted(an):
    L=collections.defaultdict(float); par=collections.defaultdict(float); cross=collections.defaultdict(int); offplane=0.0
    for i,t in enumerate(tr):
        if t['net']!=n: continue
        g=geoms[i]; l=g.length; L[t['layer']]+=l
        ref=in1 if t['layer'] in('F.Cu','In2.Cu') else in4
        offplane+=l-g.intersection(ref).length
        for j in tree.query(g.buffer(0.45)):
            j=int(j); o=tr[j]
            if o['net']==n or o['net'] in('selv_gnd',): continue
            if o['layer']==t['layer']:
                # parallel length: part of other within 0.45 of this
                pl=geoms[j].intersection(g.buffer(0.45)).length
                if pl>0.3: par[o['net']]+=pl
            elif g.crosses(geoms[j]) and {t['layer'],o['layer']} in ({'F.Cu','In2.Cu'},{'In2.Cu','In3.Cu'},{'In3.Cu','B.Cu'}): cross[o['net']+'@'+o['layer']]+=1
    if not L: continue
    print(n,{k:round(v,1) for k,v in L.items()},'vias',sum(v['net']==n for v in B['vias']),'| len not over ref plane copper %.1f'%offplane,'| same-layer neighbours within 0.3mm gap (mm run):',{k:round(v,1) for k,v in sorted(par.items(),key=lambda x:-x[1])[:5] if v>3},'| direct crossings w/o plane between:',dict(cross))
