#!/usr/bin/env python3
"""Digitize KEMET R75 (F3106_R75, 2026-10-06) 'Maximum Current (Irms) vs. Frequency (Sinusoidal Waveform / Th <= 85 C)',
2000 Vdc / 700 Vac chart (PDF p.11, right column, lower chart), curve '0.1 uF p = 27.5' (grey dashed).

    python3 -I scripts/digitize_r75.py   -> results/r75_curves.json (exit 1 on a failed control)

Render: pdftoppm -r 200 -f 11 -l 11 (1700 x 2200 px); crop x 850-1700, y 660-1452 (render/r75_11_2000.png).
Frame in the crop (read off the axis labels): x 0.1 / 1 / 10 / 100 / 1000 kHz at 108 / 257 / 405 / 553 / 702 px
(148.5 px per decade); y 100 / 10 / 1 / 0.1 / 0.01 A at 293 / 400 / 507 / 614 / 721 px (107 px per decade).
Legend order bottom-up and colours: 3300 pF orange dashed, 0.047 uF blue dashed, 0.1 uF p27.5 GREY dashed, 0.15 uF black
dashed, 0.27 uF orange dotted, 0.47 uF blue dotted. Value = median over columns +-12 px of the grey pixel runs
(R = G = B within 12, 95..175) between 2 and 20 A.
Control: the 100 kHz chart value against the p.24 table (R75UR3100(1)30: 7.56 A; R75UR3100(1)L3 low-profile 24 x 15: 8.13 A).
The chart sits at the low-profile value, so the 11 x 20 x 32 part (R75UR31004030J) is scaled by 7.56 / chart(100 kHz).
"""
import json
import math
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
PDF = ROOT / "dl/KEM_F3106_R75/KEM_F3106_R75.pdf"
tmp = Path(tempfile.mkdtemp())
subprocess.run(["pdftoppm", "-r", "200", "-png", "-f", "11", "-l", "11", str(PDF), str(tmp / "p")], check=True)
full = Image.open(next(tmp.glob("p*.png"))).convert("RGB")
crop = full.crop((850, 660, 1700, 1452))
crop.save(ROOT / "render/r75_11_2000.png")
im = np.asarray(crop).astype(int)
R, G, B = im[..., 0], im[..., 1], im[..., 2]
grey = (abs(R - G) < 12) & (abs(G - B) < 12) & (R > 95) & (R < 175)
X = lambda f: 405 + 148.5 * math.log10(f / 10e3)
Y = lambda a: 400 - 107 * math.log10(a / 10.0)
A = lambda y: 10 * 10 ** (-(y - 400) / 107.0)
vals = {}
for f in (20e3, 30e3, 35e3, 40e3, 50e3, 70e3, 100e3):
    xs = []
    for xx in range(int(X(f)) - 12, int(X(f)) + 13):
        ys = [y for y in range(int(Y(20)), int(Y(2))) if grey[y, xx]]
        if ys:
            xs.append(A(float(np.median(ys))))
    vals[f"{f / 1e3:g}k"] = round(float(np.median(xs)), 3) if xs else None
scale = 7.56 / vals["100k"]
res = {"pdf": str(PDF.relative_to(ROOT)), "chart_0.1uF_p27.5_A": vals, "table_100k_A": {"R75UR3100(1)30 11x20x32": 7.56,
       "R75UR3100(1)L3 24x15x32": 8.13}, "scale_to_4030J": round(scale, 4),
       "R75UR31004030J_I_allow_A": {k: round(v * scale, 3) for k, v in vals.items()},
       "basis": "Th <= 85 C; table note (*) 'Irms value that leads to a dT of ~20 C in the hot spot' (p.24); dT_lim vs Th "
                "p.7: 20 K to Th 85 C, linear to 0 K at Th 105 C; Th = the higher of the air around the part and the hottest "
                "contact point (tracks) (p.7)"}
fails = []
if not 0.97 <= vals["100k"] / 8.13 <= 1.06:
    fails.append(f"chart 100 kHz {vals['100k']} not near the 8.13 A table row")
res["control_failed"] = fails
(ROOT / "results").mkdir(exist_ok=True)
(ROOT / "results/r75_curves.json").write_text(json.dumps(res, indent=1) + "\n")
print(json.dumps(res, indent=1))
sys.exit(1 if fails else 0)
