"""AN139-19: copper changed inside the FEM leg boxes. usage: an139_fem_box_diff.py BASE_DUMP S19B_DUMP"""
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

bs,bg=load(sys.argv[1]); ns,ng=load(sys.argv[2])
print("base board",bs["board_sha256"]); print("new board ",ns["board_sha256"])
legs={"A21":(37.865,4.215,89.58,46.125),"B21":(2.4,4.215,42.58,46.125)}  # round17/scripts/mesh25d_hybrid.py:71-72
for m in (10,20):
    for leg,b in legs.items():
        bx=box(b[0]-m,b[1]-m,b[2]+m,b[3]+m); tot=0; per={}
        for L in LAY:
            A=unary_union([s for (n,l),s in bg.items() if l==L]).intersection(bx)
            B=unary_union([s for (n,l),s in ng.items() if l==L]).intersection(bx)
            per[L]=round(A.symmetric_difference(B).area,1); tot+=per[L]
        print(f"margin {m} mm leg {leg}: symmetric-difference copper {tot:.1f} mm2 {per}")
bx=lambda b:box(b[0]-10,b[1]-10,b[2]+10,b[3]+10)
for leg,b in legs.items():
    rows=[]
    for n in {k[0] for k in bg}|{k[0] for k in ng}:
        for L in LAY:
            A=bg.get((n,L)); B=ng.get((n,L)); x=bx(b)
            a=A.intersection(x) if A is not None else Polygon(); c=B.intersection(x) if B is not None else Polygon()
            d=a.symmetric_difference(c).area
            if d>40: rows.append((round(d),n,L))
    print(leg,"largest contributors (margin 10, >40 mm2):",sorted(rows,reverse=True))
