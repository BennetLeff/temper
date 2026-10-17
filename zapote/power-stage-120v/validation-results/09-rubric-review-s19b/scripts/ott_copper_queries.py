"""OTT-EMC review: copper-dump queries. Usage: python3 -I ott_copper_queries.py native21s19b-all-copper.json.gz"""
import sys,gzip,json,math,heapq,collections
from shapely.geometry import Polygon,LineString,Point,box
from shapely.ops import unary_union
d=json.load(gzip.open(sys.argv[1])); P=d['primitives']
L=['F.Cu','In1.Cu','In2.Cu','B.Cu']
def shp(p):
    k=p['kind']
    if k=='zone': return Polygon(p['shell'],p.get('holes') or None).buffer(0)
    if k=='pad': return Polygon(p['shell']).buffer(0)
    if k=='track': return LineString([p['start'],p['end']]).buffer(p['width_mm']/2)
    return Point(p['centre']).buffer(p['diameter_mm']/2)
def gat(nets):
    o={l:[] for l in L}
    for p in P:
        if p.get('net') in nets:
            s=shp(p)
            for l in (L if p['kind']=='via' else [p['layer']]): o[l].append(s)
    return {l:unary_union(v) if v else Polygon() for l,v in o.items()}
e0=8.854e-12
# OTT-17 filter bypass
A=gat({'ac_l_in','ac_n_in','l_f'}); B=gat({'l_filt','n_filt','rect_p','rect_n','bus_p','sw_a','sw_b'})
print('OTT-17 same-layer min gap F.Cu %.2f B.Cu %.2f mm'%(A['F.Cu'].distance(B['F.Cu']),A['B.Cu'].distance(B['B.Cu'])))
ov=A['F.Cu'].intersection(B['B.Cu']).area
print('OTT-17 F.Cu line-side over B.Cu load-side overlap %.1f mm2; C~%.3f pF (er4.3,d1.493mm)'%(ov,e0*4.3*ov*1e-6/1.493e-3*1e12))
for w in(0.5,1.0): print('OTT-17 B.Cu load-side within %.1f mm of line-side: run ~%.1f mm'%(w,A['B.Cu'].buffer(w).intersection(B['B.Cu']).area/w))
# OTT-02/12 proximity
AG=gat({'sw_a','sw_b','res_a','coil_feed'})
for n in ['ct_s1','ct_s2','ct_sense_mon','ct_oc_pos','ct_oc_neg','ct_mon','ct_zc','ocp_kelvin_p','ocp_kelvin_n','vbus_p','vbus_n','pwm_ha','pwm_la','pwm_hb','pwm_lb','permit','bus_fault_hot']:
    V=gat({n}); g=min(V[l].distance(AG[l]) for l in L if not V[l].is_empty and not AG[l].is_empty)
    o=max((V[a].intersection(AG[b]).area for a in L for b in L if a!=b and not V[a].is_empty and not AG[b].is_empty),default=0)
    print('OTT-02 %-13s min same-layer gap to SW/RES_A/COIL_FEED %.2f mm; max cross-layer overlap %.2f mm2'%(n,g,o))
K=gat({'ocp_kelvin_p','ocp_kelvin_n'}); SA=gat({'sw_a'})
a=K['In1.Cu'].intersection(SA['F.Cu']).area
print('OTT-02 SW_A F.Cu over Kelvin In1 overlap %.2f mm2; C~%.2f pF; I at 170V/24ns %.1f mA'%(a,e0*4.29*a*1e-6/0.4355e-3*1e12,e0*4.29*a*1e-6/0.4355e-3*170/24e-9*1e3))
# net lengths
for n in ['ct_s1','ct_s2']:
    t=sum(math.dist(p['start'],p['end']) for p in P if p.get('net')==n and p['kind']=='track')
    print('OTT-08 %s track length %.1f mm, vias %d'%(n,t,sum(1 for p in P if p.get('net')==n and p['kind']=='via')))
# J4 window (OTT-05/09)
w=box(31,176,59,187)
for net,l in[('v3v3','In1.Cu'),('selv_gnd','In2.Cu')]:
    G=unary_union([shp(p) for p in P if p['kind']=='zone' and p['net']==net and p['layer']==l])
    print('OTT-05 J4 window %s %s copper %.1f of %.1f mm2'%(net,l,G.intersection(w).area,w.area))
# PE path (OTT-22)
tr=[p for p in P if p.get('net')=='pe' and p['kind']=='track']
k=lambda q:(round(q[0],2),round(q[1],2)); adj=collections.defaultdict(list)
for t in tr:
    a_,b_=k(t['start']),k(t['end']); w_=math.dist(a_,b_); adj[a_].append((b_,w_)); adj[b_].append((a_,w_))
def near(pt): return [n for n in adj if math.dist(n,pt)<=1.0]
def dij(s,t):
    D=set(near(t)); pq=[(0,n) for n in near(s)]; seen=set()
    while pq:
        dd,n=heapq.heappop(pq)
        if n in seen: continue
        seen.add(n)
        if n in D: return dd
        for m,w_ in adj[n]:
            if m not in seen: heapq.heappush(pq,(dd+w_,m))
print('OTT-22 pe net: %d tracks, total %.1f mm'%(len(tr),sum(math.dist(t['start'],t['end']) for t in tr)))
print('OTT-22 C3.2->J6.2 %.2f mm; C4.2->J6.2 %.2f mm'%(dij((215.0,102.8),(165.84,134.5)),dij((215.0,109.1),(165.84,134.5))))
