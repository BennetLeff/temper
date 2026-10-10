#!/usr/bin/env python3
"""Digitize TDK B3265*A data sheet (6/26) p.57, right-hand chart 'B32654/1600 V DC': permissible I_RMS vs f,
sinusoidal, T_A <= 85 C, self-heating dT <= 20 K, lead spacing 27.5 mm. Four curves, top to bottom
220 / 150 / 100 / 47 nF.

Usage: digitize_tdk_p57.py <MKP_B32651_658.pdf>
  (https://www.tdk-electronics.tdk.com/inf/20/20/db/fc_2009/MKP_B32651_658.pdf; not committed)
Renders p.57 at 130 dpi with pdftoppm, finds the log grid from its gridlines, traces the four curves column by
column (dark-pixel clusters, gridline columns skipped), and checks the 100 kHz end against the p.22 table
(4.6 / 7.3 / 9.5 / 12.0 A). Writes outputs/tdk-p57-1600v.csv and .json.
"""
import csv
import hashlib
import json
import math
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
pdf = Path(sys.argv[1])
tmp = Path(tempfile.mkdtemp())
subprocess.run(["pdftoppm", "-f", "57", "-l", "57", "-r", "130", "-png", str(pdf), str(tmp / "p")], check=True)
png = next(tmp.glob("p*.png"))
im = np.array(Image.open(png).convert("L")).astype(int)
# chart box (right chart): find gridlines inside x 600..965, y 330..775
sub = im[330:775, 600:965]
gcols = [i + 600 for i, c in enumerate((sub < 140).sum(0)) if c > 250]
grows = [i + 330 for i, c in enumerate((sub < 140).sum(1)) if c > 250]
x100, x1e5 = min(gcols), max(gcols)               # 10^2 and 10^5 Hz border lines
y100, y001 = min(grows), max(grows)               # 100 A and 0.01 A border lines
dx, dy = (x1e5 - x100) / 3, (y001 - y100) / 4


def trace(f):
    x = round(x100 + dx * (math.log10(f) - 2))
    for xx in (x, x - 1, x + 1, x - 2, x + 2):
        if all(abs(xx - g) > 1 for g in gcols):
            break
    col = im[400:575, xx]
    dark = [i + 400 for i, v in enumerate(col) if v < 110]
    cl = []
    for y in dark:
        if cl and y - cl[-1][-1] <= 1:
            cl[-1].append(y)
        else:
            cl.append([y])
    vals = [10 ** (2 - (sum(c) / len(c) - y100) / dy) for c in cl if len(c) >= 2]
    return vals


freqs = [10e3, 15e3, 20e3, 25e3, 30e3, 35e3, 40e3, 45e3, 50e3, 55e3, 60e3, 70e3, 80e3, 90e3, 99e3]
rows = []
for f in freqs:
    v = trace(f)
    assert len(v) == 4, (f, v)
    rows.append({"f_hz": f, "I_220nF": round(v[0], 2), "I_150nF": round(v[1], 2), "I_100nF": round(v[2], 2),
                 "I_47nF": round(v[3], 2)})
table100k = {"I_220nF": 12.0, "I_150nF": 9.5, "I_100nF": 7.3, "I_47nF": 4.6}
check = {k: round(rows[-1][k] / v, 3) for k, v in table100k.items()}
with open(ROOT / "outputs" / "tdk-p57-1600v.csv", "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0]))
    w.writeheader()
    w.writerows(rows)
meta = {"source": "TDK B3265*A/G/J/T data sheet 6/26, p.57 right chart (1600 V DC / 500 V AC), T_A <= 85 C, dT <= 20 K",
        "pdf_sha256": hashlib.sha256(pdf.read_bytes()).hexdigest(), "render": "pdftoppm -r 130",
        "grid_px": {"x_1e2": x100, "x_1e5": x1e5, "y_100A": y100, "y_0.01A": y001},
        "check_99kHz_over_p22_table_100kHz": check,
        "resolution": "about +/-3 % in current (1 px = 2.1 % at 110 px/decade); curve line width ~3 px"}
(ROOT / "outputs" / "tdk-p57-1600v.json").write_text(json.dumps(meta, indent=1) + "\n")
print(json.dumps(meta, indent=1))
for r in rows:
    print(r)
