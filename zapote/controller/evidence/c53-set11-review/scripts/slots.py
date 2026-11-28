# m8: openings >= 3 mm in the In1 / In4 ground planes (excluding the six 8 mm keep-outs)
from lib import *
for pl in ('In1.Cu','In4.Cu'):
    main=max((p for _,_,p in zonepolys('selv_gnd',pl)),key=lambda p:p.area)
    s=[]
    for h in main.interiors:
        hp=Polygon(h); b=hp.bounds; e=max(b[2]-b[0],b[3]-b[1])
        if e>=3.0 and hp.area<45: s.append((round(e,1),tuple(round(v,1) for v in b)))
    s.sort(reverse=True); print(pl,len(s),'openings >= 3 mm; largest:',s[:5])
