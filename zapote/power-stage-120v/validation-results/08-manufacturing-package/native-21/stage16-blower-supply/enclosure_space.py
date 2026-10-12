#!/usr/bin/env python3
"""Where can a 60 W blower supply go in the R39 enclosure?

    python3 enclosure_space.py [Z0] > out/enclosure-space.txt        (Z0 floor height, default 20)

Inputs (read-only): R39 catalog.json (output/temper-manufacturing-r39, CURRENT.json revision R39) and the
unit's enclosure-fit body boxes for native-21 stage 15b (native21-boxes.json from the stage-15b STEP,
commit d5b1e9995, + native21-envelopes.json heights, as board_in_enclosure.py does).

Frame: R39 assembly (x across, y from the front, z up). native-21 sits at world (-141 + x, 236 - y),
bottom z 26 (R39 electronics_native21_board bbox [-141, 46, 26, 149, 236, 27.5]; H1 board (285, 135) ->
world (144, 101) = electronics_native21_standoff_H1).

1. On-board IRM-60 on the SELV tongue (free_space.py's least-displacing spot, board (45, 145)): body
   87 x 52 x 29.5 over the board top (z 27.6), 1 mm gap -> which R39 solids it hits.
2. Chassis IRM-60-xxST (109 x 52 x 33.5, IRM-60-SPEC p.2 / p.4: AC terminals on one short end, DC on the
   other) + 2 mm all round + 10 mm wire dress at each terminal end, four orientations, 2.5 mm grid,
   z from Z0 up to whatever the catalog allows. Obstacles: every catalog solid except the outer shells
   (P1-P4, chassis, glass, fence: their AABBs span the interior; wrapper inner face |x| <= 182) and
   native-21's allocation envelope, which is replaced by its real bodies. Harness route AABBs are listed
   per candidate, not blocking (routes can be re-dressed).
"""
import itertools
import json
import sys
from pathlib import Path

import numpy as np

R39 = Path("/Users/bennet/Desktop/temper/output/temper-manufacturing-r39/catalog.json")
FIT = Path("/Users/bennet/Desktop/temper/worktrees/ps-integrate/zapote/power-stage-120v/validation-plan/enclosure-fit")
Z0 = float(sys.argv[1]) if len(sys.argv) > 1 else 20.0   # 20 = chassis bbox top; 10 = fit_gate.py ZF
cat = json.load(open(R39))
SHELL = ("enclosure_P1_", "enclosure_P2_", "enclosure_P3_", "enclosure_P4_", "enclosure_bottom_chassis",
         "enclosure_glass_350", "enclosure_glass_S96", "enclosure_fence_M3", "electronics_native21_components_ENVELOPE")
solid = [(x["name"], x["bbox"]) for x in cat if not x["name"].startswith(SHELL) and x["group"] != "harness"]
harn = [(x["name"], x["bbox"]) for x in cat if x["group"] == "harness"]
named = {x["name"]: x["bbox"] for x in cat}
boxes = json.load(open(FIT / "native21-boxes.json"))["boxes"]
boxes = [b for b in boxes if not (b[5] - b[2] < 2 and (b[3] - b[0]) * (b[4] - b[1]) > 30000)]   # board slab
crt = json.load(open(FIT / "native21-courtyards.json"))
for r, h in json.load(open(FIT / "native21-envelopes.json")).items():
    boxes.append([*crt[r][:2], 1.6, *crt[r][2:], 1.6 + h])
for b in boxes:
    solid.append(("native21_body", [-141 + b[0], 236 - b[4], 26 + b[2], -141 + b[3], 236 - b[1], 26 + b[5]]))
O = np.array([b for _, b in solid])


def hit_names(b):
    m = (b[0] < O[:, 3]) & (O[:, 0] < b[3]) & (b[1] < O[:, 4]) & (O[:, 1] < b[4]) & (b[2] < O[:, 5]) & (O[:, 2] < b[5])
    return sorted({solid[i][0] for i in np.nonzero(m)[0]})


def harness(b):
    return [n[8:] for n, o in harn if b[0] < o[3] and o[0] < b[3] and b[1] < o[4] and o[1] < b[4] and b[2] < o[5] and o[2] < b[5]]


# 1. tongue
bx, by = 45, 145
b = [-141 + bx - 44.5, 236 - by - 27, 27.6, -141 + bx + 44.5, 236 - by + 27, 27.6 + 29.5 + 1]
print("1. IRM-60 on the tongue at board (45,145): world", [round(v, 1) for v in b])
print("   hits:", [n for n in hit_names(b) if n != "native21_body"], "(+ native-21 bodies:", "native21_body" in hit_names(b), ")")
ui = named["controls_ui_board"]
print(f"   controls_ui_board bottom z {ui[2]} -> headroom over the board top (27.6) {ui[2] - 27.6:.1f} mm vs 30.5 needed")

# 2. chassis module
ferr = named["sensor_coil_ferrite_bars"]
L, W, H = 109.0, 52.0, 33.5
dims = {"flat, long x": (L + 24, W + 4, H + 4), "flat, long y": (W + 4, L + 24, H + 4),
        "on edge, long x": (L + 24, H + 4, W + 4), "on edge, long y": (H + 4, L + 24, W + 4)}
XW, Y0, Y1, ZMAX = 182.0, 3.0, 422.0, 105.0
out = []
for tag, (ex, ey, ez) in dims.items():
    for cx, cy, z0 in itertools.product(np.arange(-XW + ex / 2, XW - ex / 2 + 0.1, 2.5),
                                         np.arange(Y0 + ey / 2, Y1 - ey / 2 + 0.1, 2.5),
                                         np.arange(Z0, ZMAX - ez + 0.1, 2.5)):
        bb = [cx - ex / 2, cy - ey / 2, z0, cx + ex / 2, cy + ey / 2, z0 + ez]
        if not hit_names(bb):
            gap = max(ferr[1] - bb[4], bb[1] - ferr[4], ferr[0] - bb[3], bb[0] - ferr[3])
            out.append((tag, float(cx), float(cy), float(z0), round(float(gap), 1),
                        bool(bb[0] < 149 and -141 < bb[3] and bb[1] < 236 and 46 < bb[4]), harness(bb), bb))
print(f"\n2. IRM-60-xxST chassis envelope, floor z {Z0}: {len(out)} clear grid positions")
print("   (plan gap to the coil ferrite bars: negative = under the coil)")
seen = set()
for f in sorted(out, key=lambda f: -f[4]):
    k = (f[0], round(f[1] / 20), round(f[2] / 20))
    if k in seen:
        continue
    seen.add(k)
    print(f"   {f[0]:15s} centre ({f[1]:.1f}, {f[2]:.1f}) x {f[7][0]:.0f}..{f[7][3]:.0f} y {f[7][1]:.0f}..{f[7][4]:.0f}"
          f" z {f[3]:.1f}-{f[7][5]:.1f}  ferrite gap {f[4]:+.1f} mm{'  over native-21' if f[5] else ''}  harness AABBs: {f[6]}")
    if len(seen) >= 14:
        break
