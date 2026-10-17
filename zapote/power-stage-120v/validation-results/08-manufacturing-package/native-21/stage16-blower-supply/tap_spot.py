#!/usr/bin/env python3
"""Spot for the PS3 mains tap (fuse F2 in clips + 2-post header J11) on native-21 stage 15b.

    python3 -B tap_spot.py board/dump.json > out/tap-spot.txt

Block = J11, a JST B2P3-VH(LF)(SN) at rotation 0 (J3's measured courtyard turned: 12.9 x 9.6 mm; VH
7.92 mm, middle post omitted) stacked 0.6 mm over F2, two Littelfuse 01000056Z 5 x 20 clips (KiCad
Fuse:Fuseholder_Clip-5x20mm_Littelfuse_100_Inline_P20.50x4.60mm courtyard 23.3 x 6.44 mm) holding a
0215 3.15 A ceramic time-lag fuse: block 23.3 x 16.64 mm. A legal spot must:
  - collide with no courtyard (0.6 mm gap) and sit inside the outline (0.5 mm);
  - be >= 8.0 mm plan view from SELV/PE copper and from H1's earthed 7 mm head (D5, rules21);
  - be >= 3.2 mm from HOT/SW copper and from other MAINS-group copper (D5 functional) with nothing
    foreign under it (no pour clip).
Ranked by distance to the l_filt / n_filt copper it taps (PS1's AC feed). Copper distances use pour
OUTLINES (dump_board.py): lower bounds on the filled board.
"""
import sys

from shapely.geometry import box
from shapely.ops import unary_union

from common import EDGE, copper_by_net, courtyards, domain, h1_disc, load

d = load(sys.argv[1])
edge = EDGE.buffer(-0.5, join_style=2)
crt = [g for _, g, _ in courtyards(d, 0.6)]
geo = copper_by_net(d)
selv = unary_union([g for n, g in geo.items() if domain(n) in ("SELV", "PE")] + [h1_disc(d)])
hot = unary_union([g for n, g in geo.items() if domain(n) in ("HOT", "SW_A", "SW_B")])
other_mains = unary_union([g for n, g in geo.items() if domain(n) == "MAINS" and n not in ("l_filt", "n_filt")])
filt = unary_union([geo["l_filt"], geo["n_filt"]])
# block override: tap_spot.py dump.json BW BH  (e.g. 12.9 14.2 = J11 over a Schurter UMT 250 SMD fuse,
# 10.1 x 3.1 body, courtyard taken as 11.5 x 4.0)
BW, BH = (float(sys.argv[2]), float(sys.argv[3])) if len(sys.argv) > 3 else (23.3, 9.6 + 0.6 + 6.44)
print(f"block {BW} x {BH} mm")
res = []
for orient, (w, h) in (("stack-y (clips along x)", (BW, BH)), ("stack-x (clips along y)", (BH, BW))):
    for yi in range(0, 381):
        for xi in range(0, 581):
            x, y = xi / 2, yi / 2
            b = box(x - w / 2, y - h / 2, x + w / 2, y + h / 2)
            if not edge.contains(b) or any(c.intersects(b) for c in crt):
                continue
            ds, dh, dm = b.distance(selv), b.distance(hot), b.distance(other_mains)
            if ds >= 8.0 and dh >= 3.2 and dm >= 3.2:
                res.append((round(b.distance(filt), 1), round(ds, 1), round(dh, 1), round(dm, 1), orient, x, y,
                            round(b.intersection(filt).area)))
res.sort(key=lambda r: (r[0], -r[1]))
print(f"{len(res)} legal spots (no courtyard, >= 8 mm SELV/PE/H1, >= 3.2 mm HOT and other MAINS groups)")
print("dist_to_filt  dist_SELV/PE/H1  dist_HOT  dist_other_MAINS  orient  cx  cy  filt_cu_under_mm2")
seen = set()
for r in res:
    k = (r[4], round(r[5] / 6), round(r[6] / 6))
    if k in seen:
        continue
    seen.add(k)
    print("  ", r)
    if len(seen) >= 12:
        break
