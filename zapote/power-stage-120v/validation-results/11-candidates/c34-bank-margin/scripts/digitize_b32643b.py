#!/usr/bin/env python3
"""C34: digitize TDK B3264*B 'High frequency' (6/26) p.24, B32643B 2000 V DC / 500 V AC, lead spacing 22.5 mm:
'Permissible current I_RMS versus frequency f (sinusoidal, T_A <= 85 C, dT <= 15 C)', numpy only.

    python3 -I scripts/digitize_b32643b.py <MMKP_B32641B_B32643B.pdf>  -> results/b32643b_curves.json (exit 1 on a failed control)

PDF not in the repo (TDK MMKP_B32641B_B32643B.pdf, 'B3264*B', June 2026; sha256 ab9fdca0...4a58ab77).
Rendered `pdftoppm -gray -r 200` (PGM). Frame from the grid: x decades 10^3-10^6 Hz, y decades 0.1-10 A. Above the
knee (>= ~30 kHz for 68-120 nF) the 14 curves are parallel plateaus; at each frequency column the dark clusters are
taken top-down as 120, 100, 82, 68, 56, 47 nF (the six largest, p.11 table order of I_RMS).
Controls: the 99 kHz values within 3 % of the p.11 table (100 kHz, 85 C): 9.1 / 8.3 / 7.5 / 6.8 / 6.2 / 5.7 A; and the
six clusters strictly ordered at every frequency used.
"""
import hashlib
import json
import math
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "results"
pdf = Path(sys.argv[1])
tmp = Path(tempfile.mkdtemp())
subprocess.run(["pdftoppm", "-gray", "-r", "200", "-f", "24", "-l", "24", str(pdf), str(tmp / "p")], check=True)
raw = next(tmp.glob("p*.pgm")).read_bytes()
hdr = raw.split(maxsplit=4)
W, H = int(hdr[1]), int(hdr[2])
im = np.frombuffer(hdr[4][:W * H], np.uint8).reshape(H, W).astype(int)
LAB = ["120nF", "100nF", "82nF", "68nF", "56nF", "47nF"]
TAB = {"120nF": 9.1, "100nF": 8.3, "82nF": 7.5, "68nF": 6.8, "56nF": 6.2, "47nF": 5.7}
FREQS = [30e3, 35e3, 40e3, 45e3, 50e3, 60e3, 70e3, 80e3, 99e3]
x0, y0, x1, y1 = 230, 550, 770, 1230                      # chart window at 200 dpi
sub = im[y0:y1, x0:x1]
gcol = [i + x0 for i, c in enumerate((sub < 140).sum(0)) if c > 0.55 * (y1 - y0)]
grow = [i + y0 for i, c in enumerate((sub < 140).sum(1)) if c > 0.55 * (x1 - x0)]
x3 = min(gcol) + 0.5                                       # 10^3 Hz (a 2 px line)
yt, yb = min(grow), max(grow)                              # 10 A and 0.1 A
x2k = min(g for g in gcol if g > x3 + 5)                    # 2 kHz minor line (first line after the 10^3 frame)
dx = (x2k - x3) / math.log10(2)                             # px per decade
x4 = x3 + dx
dy = (yb - yt) / 2.0
gr = set(grow)
fails = []
rows = []
for f in FREQS:
    x = round(x3 + dx * (math.log10(f) - 3))
    for xx in (x, x - 2, x + 2, x - 3, x + 3):
        if all(abs(xx - g) > 1 for g in gcol):
            break
    col = im[yt + 2:yb, xx]
    dark = [i + yt + 2 for i, v in enumerate(col) if v < 110 and (i + yt + 2) not in gr]
    cl = []
    for y in dark:
        if cl and y - cl[-1][-1] <= 2:
            cl[-1].append(y)
        else:
            cl.append([y])
    cl = [c for c in cl if c[-1] - c[0] >= 1][:len(LAB)]
    vals = [10 ** (1 - ((c[0] + c[-1]) / 2 - yt) / dy) for c in cl]
    if len(vals) < len(LAB) or any(b >= a for a, b in zip(vals, vals[1:])):
        fails.append(f"{f}: clusters {len(vals)} not ordered")
        continue
    rows.append({"f_hz": f, "col_px": xx, **{f"I_{l}": round(v, 3) for l, v in zip(LAB, vals)}})
end = [r for r in rows if r["f_hz"] == 99e3]
chk = {l: round(end[0][f"I_{l}"] / t, 3) for l, t in TAB.items()} if end else {}
if not chk or any(abs(c - 1) > 0.03 for c in chk.values()):
    fails.append(f"99 kHz vs p.11 table {chk}")
res = {"pdf_sha256": hashlib.sha256(pdf.read_bytes()).hexdigest(), "page": 24, "render": "pdftoppm -gray -r 200",
       "frame_px": {"x_1e3": x3, "x_1e4": x4, "y_10A": yt, "y_0.1A": yb}, "labels_top_down": LAB, "rows": rows,
       "check_99k_over_table_100k": chk,
       "resolution": "about +/-2 % (1 px = 0.73 % at ~318 px per decade); plateau lines ~3 px",
       "controls": {"failed": fails, "passed": not fails}}
OUT.mkdir(exist_ok=True)
(OUT / "b32643b_curves.json").write_text(json.dumps(res, indent=1) + "\n")
for r in rows:
    print(r)
print("check", chk, "fails", fails)
sys.exit(1 if fails else 0)
