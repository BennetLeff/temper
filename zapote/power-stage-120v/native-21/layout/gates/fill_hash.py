#!/usr/bin/env python3
"""Compare the filled pours of two or more builds (BUILDDIR/copper-dump.json) of the same copper.json (stage 17b).
    python3 fill_hash.py REF BUILD [BUILD ...]  -> JSON per build: symmetric-difference area against REF per
    (layer, net), total, and a hash of the per-(layer, net) filled areas rounded to 1 mm2.
Exit 1 when any (layer, net) differs by more than TOL_MM2 (0.1 mm2): KiCad's arc tessellation and thermal-relief
spokes differ by a few hundredths of a mm2 between identical rebuilds, a fill-order flip by whole mm2 (the stage-17
In1 n_ls / ocp_kelvin_p strip was 3.5 mm2; the B.Cu sw_b / res_a bank region 48 mm2)."""
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

from shapely.geometry import Polygon
from shapely.ops import unary_union

TOL_MM2 = 0.1


def fills(b):
    g = defaultdict(list)
    for z in json.loads((Path(b) / "copper-dump.json").read_text())["zones"]:
        if len(z["pts"]) > 2:
            g[(z["layer"], z["net"])].append(Polygon(z["pts"], [h for h in z.get("holes", []) if len(h) > 2]).buffer(0))
    return {k: unary_union(v) for k, v in g.items()}


ref = fills(sys.argv[1])
ok = True
for b in sys.argv[1:]:
    f = fills(b)
    diff = {f"{k[0]}|{k[1]}": round(ref.get(k, Polygon()).symmetric_difference(f.get(k, Polygon())).area, 4)
            for k in sorted(set(ref) | set(f))}
    worst = max(diff.values())
    ok &= worst <= TOL_MM2
    areas = "".join(f"{k}:{round(f[(k.split('|')[0], k.split('|')[1])].area if (k.split('|')[0], k.split('|')[1]) in f else 0)};"
                    for k in sorted(diff))
    print(json.dumps({"build": b, "area_hash": hashlib.sha256(areas.encode()).hexdigest()[:16],
                      "symdiff_total_mm2": round(sum(diff.values()), 4), "symdiff_worst_mm2": worst,
                      "worst": max(diff, key=diff.get)}))
sys.exit(0 if ok else 1)
