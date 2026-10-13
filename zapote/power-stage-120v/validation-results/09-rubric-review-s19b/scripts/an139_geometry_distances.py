"""AN139-13/14/15/18: pad distances, L1 to coil axis, RES_A distances. usage: an139_geometry_distances.py DUMP"""
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
pad={}
for p in d["primitives"]:
    if p["kind"]=="pad" and "." in p.get("ref",""): pad.setdefault(p["ref"],p["centre"])
D=lambda a,b: math.dist(pad[a],pad[b])
for a,b in (("L1.4","C2.1"),("L1.3","C2.2"),("L1.4","C3.1"),("L1.3","C4.1"),("L1.4","BR1.2"),("C38.1","Q2.2")):
    print(f"{a} {pad.get(a)} -> {b} {pad.get(b)}: {D(a,b):.1f} mm")
ax=(141,-25)  # coil axis in board frame, coil-pickup/PICKUP.md:17
print("L1.1 pad",pad["L1.1"],"; L1.1 pad (= L1 footprint origin) distance to coil axis",round(math.dist(pad["L1.1"],ax),1),"mm")
S=("v3v3","selv_gnd","pe","v15_selv")
for L in LAY:
    a=G.get(("res_a",L)); r=sorted((round(a.distance(G[(n,L)]),3),n) for n in S if (n,L) in G)
    print(L,"RES_A to SELV/PE same-layer min",r[:2])
ra=unary_union([s for (n,l),s in G.items() if n=="res_a"]); sv=unary_union([s for (n,l),s in G.items() if n in S])
print("RES_A to SELV/PE plan view all layers",round(ra.distance(sv),3))
