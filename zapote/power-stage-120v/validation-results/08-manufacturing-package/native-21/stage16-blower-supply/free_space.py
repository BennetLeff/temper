#!/usr/bin/env python3
"""Is there room on native-21 (stage 15b) for a third AC-DC module?  Also option (c): IRM-60 in PS1's corner.

    python3 -B free_space.py board/dump.json > out/free-space.txt

1. For each body (courtyard = body + 1 mm), both orientations, a 1 mm grid inside the L outline (0.5 mm
   edge clearance): positions colliding with no courtyard (0.6 mm pack gap, place.py GAP); otherwise the
   positions displacing the fewest parts, named, with the copper (D5 domain, plan view) underneath; and
   the best spot on the main body (off the SELV tongue).
2. Option (c): an 88 x 53 courtyard replacing PS1 in its corner (x >= 150, bottom edge band): fewest parts
   displaced besides PS1.
Bodies: IRM-60 / IRM-45 87 x 52 x 29.5 (IRM-60-SPEC / IRM-45-SPEC 2025-11-21 p.2 DIMENSION);
IRM-30 69.5 x 39 x 24 (IRM-30-SPEC p.2); IRM-20 52.4 x 27.2 x 24 (IRM-20-SPEC p.2), for scale.
"""
import sys

from shapely.geometry import box
from shapely.strtree import STRtree

from common import EDGE, by_domain, copper_by_net, courtyards, load

d = load(sys.argv[1])
edge = EDGE.buffer(-0.5, join_style=2)
crt = courtyards(d)
tree = STRtree([g for _, g, _ in crt])
cu = by_domain(copper_by_net(d))


def hits(b):
    return [crt[i] for i in tree.query(b) if crt[i][1].intersects(b)]


for name, (w, h) in {"IRM-60/45 (87 x 52)": (87.0, 52.0), "IRM-30 (69.5 x 39)": (69.5, 39.0),
                     "IRM-20 (52.4 x 27.2)": (52.4, 27.2)}.items():
    res = []
    for ang, (bw, bh) in (("long-x", (w + 1, h + 1)), ("long-y", (h + 1, w + 1))):
        for yi in range(int(bh / 2) + 1, int(190 - bh / 2)):
            for xi in range(int(bw / 2) + 1, int(290 - bw / 2)):
                b = box(xi - bw / 2, yi - bh / 2, xi + bw / 2, yi + bh / 2)
                if edge.contains(b):
                    hh = hits(b)
                    res.append((len(hh), round(sum(box(*f["crtyd"]).area for _, _, f in hh)), ang, xi, yi,
                                sorted(r for r, _, _ in hh), b))
    free = [q for q in res if q[0] == 0]
    print(f"== {name}: {len(res)} in-outline positions, {len(free)} collide with no courtyard"
          + (f" (all on the SELV tongue: centres x {min(q[3] for q in free)}-{max(q[3] for q in free)},"
             f" y {min(q[4] for q in free)}-{max(q[4] for q in free)})" if free else ""))
    res.sort(key=lambda q: (q[1], q[0]))
    seen = set()
    for q in res:
        if tuple(q[5]) in seen:
            continue
        seen.add(tuple(q[5]))
        under = {k: round(v.intersection(q[6]).area) for k, v in cu.items() if v.intersection(q[6]).area > 1}
        print(f"  displaced {q[1]:5d} mm2 / {q[0]:2d} parts, {q[2]} centre ({q[3]},{q[4]}): "
              f"{' '.join(q[5][:12])}{' ...' if len(q[5]) > 12 else ''}; copper under (mm2): {under}")
        if len(seen) >= 3:
            break
    main = [q for q in res if q[6].bounds[3] <= 140]
    q = min(main, key=lambda q: (q[1], q[0]))
    print(f"  best main-body spot (off the tongue): {q[0]} parts / {q[1]} mm2 at ({q[3]},{q[4]}) {q[2]}: {' '.join(q[5])}")

print("== option (c): 88 x 53 courtyard in PS1's corner (x >= 150, touching the y 139.5 edge band)")
best = {}
for w, h, tag in ((88, 53, "long-x"), (53, 88, "long-y")):
    x0 = 150.0
    while x0 + w <= 289.5:
        for j in range(21):
            y0 = 139.5 - h - 0.5 * j
            b = box(x0, y0, x0 + w, y0 + h)
            if edge.contains(b):
                hh = sorted(r for r, _, _ in hits(b) if r != "PS1")
                if tag not in best or len(hh) < len(best[tag][0]):
                    best[tag] = (hh, x0 + w / 2, y0 + h / 2)
        x0 += 0.5
for tag, (hh, cx, cy) in best.items():
    print(f"  {tag} centre ({cx:.1f},{cy:.1f}): displaces {len(hh)} parts besides PS1: {' '.join(hh)}")
