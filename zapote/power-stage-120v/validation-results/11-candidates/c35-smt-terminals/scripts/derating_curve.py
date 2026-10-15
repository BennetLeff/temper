#!/usr/bin/env python3
"""Digitize the grey 'THR 7x7mm / SMD D7mm' derating curve of Wuerth's REDCUBE SMD Terminals Design Guide (p.11).

    python3 -I scripts/derating_curve.py GUIDE.pdf [--json OUT.json]

GUIDE.pdf: https://www.we-online.com/components/media/o153698v410%20BCF_REDCUBESMDDesignGuide_EN.pdf
(16 pages, sha256 1d9eb5ae2bdfbb18..., fetched 2026-10-14; not committed). The chart's legend puts the REDCUBE THR
7x7 mm (the 74650074 family) and the SMD D7 mm (7466004R) on ONE curve; the footnote: "tested with 4-layers 105 um Cu
PCB", text above it: "measured with 6 mm2 and a 2 x 70 um circuit board".

Method: render p.11 at 300 dpi (pdftoppm), crop the plot, find the light-grey gridlines (x 20..150 C every 10 C,
y 0..100 A every 10 A) and, in each pixel column, the curve's mid-grey pixels (r = g = b, 140-175; gridlines are
>= 180, text < 120). The current at each temperature is the mean row of those pixels; reading error is about one
line width (~0.5 A). Prints the curve every 5 C and the ambient at which it crosses given currents.
"""
import argparse
import json
import subprocess
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

ap = argparse.ArgumentParser()
ap.add_argument("pdf")
ap.add_argument("--json")
ap.add_argument("--at", default="29.4,28.0,22.0", help="currents (A) whose crossing ambient is reported")
a = ap.parse_args()
with tempfile.TemporaryDirectory() as td:
    subprocess.run(["pdftoppm", "-f", "11", "-l", "11", "-r", "300", "-png", a.pdf, f"{td}/p"], check=True)
    page = Image.open(next(Path(td).glob("p*.png"))).convert("RGB")
w, h = page.size
im = np.asarray(page.crop((int(w * 0.11), int(h * 0.37), int(w * 0.88), int(h * 0.71)))).astype(int)
r, g, b = im[..., 0], im[..., 1], im[..., 2]
neutral = (abs(r - g) < 10) & (abs(g - b) < 10)
light = neutral & (r > 180) & (r < 235)
H, W = r.shape


def groups(idx):
    out = []
    for v in idx:
        if out and v - out[-1][-1] <= 2:
            out[-1].append(v)
        else:
            out.append([v])
    return [sum(x) / len(x) for x in out]


cols = groups(np.where(light.sum(0) > 0.3 * H)[0])
rows = groups(np.where(light.sum(1) > 0.25 * W)[0])
# x gridlines 20..150 C (14 lines), y gridlines 100..0 A (11 lines, top first)
xs = [c for c in cols if c > 100][:14]
ys = rows[:11]
assert len(xs) == 14 and len(ys) == 11, (xs, ys)
x0, dx = xs[0], (xs[-1] - xs[0]) / 130.0          # px per C
y0, dy = ys[-1], (ys[-1] - ys[0]) / 100.0          # row of 0 A, px per A
curve = neutral & (r >= 140) & (r <= 175)
pts = []
for c in range(int(xs[0]) + 3, int(xs[-1]) - 3):
    hit = np.where(curve[int(ys[0]) + 2:int(y0) - 2, c])[0]
    if len(hit) == 0:
        continue
    # several neutral runs can fall in one column (gridline antialiasing, labels): take the longest run
    best = max(([v for v in hit if abs(v - m) <= 3] for m in groups(hit)), key=len)
    row = np.mean(best) + int(ys[0]) + 2
    pts.append(((c - x0) / dx + 20.0, (y0 - row) / dy))
pts = np.array(pts)
grid = {}
for t in range(20, 150, 5):
    sel = pts[abs(pts[:, 0] - t) < 1.0]
    if len(sel):
        grid[t] = round(float(np.median(sel[:, 1])), 1)
cross = {}            # linear interpolation on the 5 C grid (the curve falls monotonically)
ts = sorted(grid)
for amp in (float(v) for v in a.at.split(",")):
    cross[amp] = next((round(t0 + (grid[t0] - amp) / (grid[t0] - grid[t1]) * (t1 - t0), 1)
                       for t0, t1 in zip(ts, ts[1:]) if grid[t0] >= amp > grid[t1]), None)
print("ambient C -> A:", grid)
print("ambient where the curve falls to the current:", cross)
if a.json:
    Path(a.json).write_text(json.dumps({"source": "Wuerth REDCUBE SMD Terminals Design Guide p.11, grey curve "
                                        "'THR 7x7mm / SMD D7mm' (one curve for both terminals)",
                                        "pdf_sha256_prefix16": "1d9eb5ae2bdfbb18",
                                        "test_basis": "6 mm2 cable; 4-layer 105 um Cu PCB (footnote) / 2 x 70 um (text)",
                                        "curve_A_by_ambient_C": grid, "ambient_C_at_current_A": cross,
                                        "reading_error_A": 0.5}, indent=1) + "\n")
