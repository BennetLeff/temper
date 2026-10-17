"""Most-unfavourable-position check (IEC 60335-1 29.1/29.2: parts that can be tightened in different
positions are placed in the most unfavourable position) for two M4 ring lugs on studs at pitch P.
Bare lug: Wurth 5580406 envelope from terminal_envelopes.json (10 mm wide, 5 mm behind, 16 mm ahead).
Insulated lug: only the ring (diameter = width) is exposed metal; barrel and neck are sleeved."""
import math
from shapely.geometry import Point, box
from shapely import affinity
W, BEH, AHEAD = 10.0, 5.0, 16.0
def bare(cx, cy, ang):
    g = box(0, -W/2, AHEAD, W/2).union(Point(0, 0).buffer(W/2))  # ring (radius W/2) + tongue/barrel to 16 mm
    return affinity.translate(affinity.rotate(g, ang, origin=(0, 0)), cx, cy)
def ring(cx, cy): return Point(cx, cy).buffer(W/2)
for P in (15.0, 20.0, 30.0, 37.0, 40.0):
    worst = min((bare(0, 0, a).distance(bare(0, P, b)), a, b) for a in range(0, 360, 5) for b in range(0, 360, 5))
    para = bare(0, 0, 0).distance(bare(0, P, 0))
    print(f"pitch {P:4.0f} mm: bare lugs parallel (+x) {para:5.2f} mm; worst over rotation {worst[0]:5.2f} mm "
          f"(angles {worst[1]},{worst[2]}); insulated (ring only) {ring(0,0).distance(ring(0,P)):5.2f} mm")
