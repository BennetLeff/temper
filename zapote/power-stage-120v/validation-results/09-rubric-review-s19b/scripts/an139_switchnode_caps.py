"""AN139-04/05: switch-node areas, parallel-plate C, plane coverage, quiet-net distances. usage: an139_switchnode_caps.py DUMP"""
import gzip,json,sys,collections,math
from shapely.geometry import LineString,Polygon,Point,box
from shapely.ops import unary_union
def opn(p): return gzip.open(p,"rt") if p.endswith(".gz") else open(p)
def load(path):
    d=json.load(opn(path)); g=collections.defaultdict(list)
    for p in d["primitives"]:
        k=p["kind"]; n=p.get("net") or "pad:"+p.get("ref",""); l=p["layer"]
        try:
            if k=="track": s=LineString([p["start"],p["end"]]).buffer(p["width_mm"]/2)
            elif k=="via": s=Point(p["centre"]).buffer(p["diameter_mm"]/2)
            else: s=Polygon(p["shell"],p.get("holes") or []).buffer(0)
        except Exception: continue
        if k=="via":
            for L in ("F.Cu","In1.Cu","In2.Cu","B.Cu"): g[(n,L)].append(s)
        else: g[(n,l)].append(s)
    return d,{k:unary_union(v) for k,v in g.items()}
LAY=("F.Cu","In1.Cu","In2.Cu","B.Cu")

d,G=load(sys.argv[1]); print("board",d["board_sha256"])
e0=8.854e-12; er=4.29; dd=0.4355e-3   # stackup.json:12-31 dielectric 1 / 3
print("sw_a F.Cu area mm2",round(G[("sw_a","F.Cu")].area,1)); print("sw_b B.Cu area mm2",round(G[("sw_b","B.Cu")].area,1))
for tag,sw,pl in (("sw_a F.Cu over hv_ret In1",("sw_a","F.Cu"),("hv_ret","In1.Cu")),("sw_b B.Cu over bus_p In2",("sw_b","B.Cu"),("bus_p","In2.Cu"))):
    a=G[sw].intersection(G[pl]).area
    print(f"{tag}: overlap {a:.0f} mm2, C = {e0*er*a*1e-6/dd*1e12:.1f} pF")
U=lambda ns: unary_union([G[(n,l)] for n in ns for l in LAY if (n,l) in G])
quiet=U(["ac_l_in","ac_n_in","l_f"])
for n in ("sw_a","sw_b","bus_p","hv_ret","rect_p","rect_n"):
    print(f"quiet-side (ac_l_in,ac_n_in,l_f) to {n}: {quiet.distance(U([n])):.2f} mm")
print("l_filt/quiet cross-layer overlap mm2",round(quiet.intersection(U(["l_filt"])).area,1))
for nm,bx in (("leg A x38-75,y4-30",box(38,4,75,30)),("leg B x2-35,y4-30",box(2,4,35,30))):
    print(nm,"area",bx.area,"In1 hv_ret",round(G[("hv_ret","In1.Cu")].intersection(bx).area),"In2 bus_p",round(G[("bus_p","In2.Cu")].intersection(bx).area))
H=G[("hv_ret","In1.Cu")]
for x in (40,45,50,55,60,65,70,74):
    y=next((i/10 for i in range(300) if H.contains(Point(x,i/10))),None); print("x",x,"first y with hv_ret on In1:",y)
a,b=(61,28.2),(68.05,4.215); n=int(math.dist(a,b)/0.5); no_in1=0
In1=unary_union([s for (nn,l),s in G.items() if l=="In1.Cu" and not nn.startswith("pad:")])
for i in range(n+1):
    t=i/n; p=Point(a[0]+(b[0]-a[0])*t,a[1]+(b[1]-a[1])*t)
    if not In1.contains(p): no_in1+=0.5
hv=sum(0.5 for i in range(n+1) if H.contains(Point(a[0]+(b[0]-a[0])*i/n,a[1]+(b[1]-a[1])*i/n)))
print(f"C38+ -> Q2.D line {math.dist(a,b):.1f} mm: hv_ret on In1 under {hv:.1f} mm, no In1 copper under {no_in1:.1f} mm")
swb=G[("sw_b","B.Cu")]
for nn,l in (("ocp_kelvin_p","In1.Cu"),("ocp_kelvin_n","In1.Cu"),("leg_a-gate_l","F.Cu"),("leg_a-gate_h","F.Cu")):
    i=swb.intersection(G[(nn,l)])
    if i.area>0.5: print(nn,l,"under sw_b B.Cu overlap",round(i.area,1),"mm2; frac with hv_ret In1",round(i.intersection(H).area/i.area,2),"bus_p In2",round(i.intersection(G[("bus_p","In2.Cu")]).area/i.area,2))
