#!/usr/bin/env python3
"""C34: digitize KEMET R76 (F3034_R76, 3/21/2025) p.8 'Maximum Current (Irms) Versus Frequency (Sinusoidal
Waveform / Th <= 85 C)', 1,600 VDC/650 VAC and 2,000 VDC/700 VAC charts, numpy only.

    python3 -I scripts/digitize_kemet_r76.py <KEM_F3034_R76.pdf>   -> results/kemet_r76_curves.json (exit 1 on a failed control)

PDF not in the repo (https://content.kemet.com/datasheets/KEM_F3034_R76.pdf; sha256 c45e4c7f...26804b9).
Rendered with `pdftoppm -r 200` (colour PPM). The charts are log-log with blue grid lines; frames are found from the
grid (x decades 0.1-1000 kHz, y decades 0.01-100 A). The curves are dotted / dashed and coloured, so each value is a
straight-line fit (pixel y against x) to the curve's colour mask over +-10 px columns around the target frequency.
Curves read (legend order and colours on the page; identities checked against the p.19 / p.22 tables at 100 kHz):
  2,000 V chart: orange dotted = 0.1 uF p=27.5 (R76UR3100, table 8.3 A); black dashed = 0.047 uF p=27.5 (R76UR2470, 6.1 A)
  1,600 V chart: black dashed = 0.22 uF p=27.5 (R76TR3220 18x33, 9.0 A); orange dotted = 0.33 uF p=27.5 (R76TR3330, 11.0 A)
Controls: each curve's 100 kHz value within 6 % of its table value (R76TR3330 informational: the printed curve
ends at ~10.3 A against the 11.0 A table, a datasheet inconsistency; it is not used for any bank).
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
subprocess.run(["pdftoppm", "-r", "200", "-f", "8", "-l", "8", str(pdf), str(tmp / "p")], check=True)
raw = next(tmp.glob("p*.ppm")).read_bytes()
hdr = raw.split(maxsplit=4)
W, H = int(hdr[1]), int(hdr[2])
im = np.frombuffer(hdr[4][:W * H * 3], np.uint8).reshape(H, W, 3).astype(int)
R, G, B = im[:, :, 0], im[:, :, 1], im[:, :, 2]
blue = (B - R > 40) & (B > 150)
MASK = {"orange": (R > 200) & (G > 130) & (G < 215) & (B < 110),
        "black": (R < 80) & (G < 80) & (B < 80)}
CHARTS = {"2000V": (940, 1600), "1600V": (160, 820)}            # x ranges of the third-row charts on p.8
CURVES = {"2000V": {"orange": ("R76UR3100", 0.1, 8.3), "black": ("R76UR2470", 0.047, 6.1)},
          "1600V": {"black": ("R76TR3220", 0.22, 9.0), "orange": ("R76TR3330", 0.33, 11.0)}}
FREQS = [30e3, 35e3, 40e3, 45e3, 50e3, 60e3, 80e3, 100e3]
fails = []
res = {"pdf_sha256": hashlib.sha256(pdf.read_bytes()).hexdigest(), "render": "pdftoppm -r 200", "charts": {}}
for ch, (xa, xb) in CHARTS.items():
    rows_b = blue[:, xa:xb].sum(1)
    grow = [i for i in range(1500, 2040) if rows_b[i] > 0.6 * (xb - xa)]   # third chart row (footer rule at ~2062 excluded)
    yt, yb = min(grow), max(grow)                                # 100 A and 0.01 A lines
    cols_b = blue[yt:yb + 1, :].sum(0)
    gcol = [i for i in range(xa, xb) if cols_b[i] > 0.7 * (yb - yt)]
    xl, xr = min(gcol), max(gcol)                                # 0.1 kHz and 1000 kHz lines
    dx, dy = (xr - xl) / 4.0, (yb - yt) / 4.0
    out = {"frame_px": [xl, xr, yt, yb], "curves": {}}
    for col, (pn, c_uf, tab) in CURVES[ch].items():
        m = MASK[col]
        vals = {}
        for f in FREQS:
            x = xl + dx * (math.log10(f / 1e3) + 1)
            xs, ys = [], []
            for xx in range(int(x) - 10, int(x) + 11):
                # the curve sits between 2 A and 20 A here: rows for 20 A .. 2 A
                y20 = yt + dy * (2 - math.log10(20))
                y2 = yt + dy * (2 - math.log10(2))
                hit = np.nonzero(m[int(y20):int(y2), xx])[0]
                for h in hit:
                    xs.append(xx)
                    ys.append(h + int(y20))
            if len(xs) < 4:
                vals[f] = None
                continue
            k, b0 = np.polyfit(np.array(xs, float), np.array(ys, float), 1)
            y = k * x + b0
            vals[f] = round(10 ** (2 - (y - yt) / dy), 3)
        chk = vals[100e3] / tab if vals.get(100e3) else None
        if pn == "R76TR3330":               # informational: the printed curve ends ~7 % under its table value
            pass
        elif chk is None or abs(chk - 1) > 0.06:
            fails.append(f"{ch} {pn}: 100 kHz {vals.get(100e3)} vs table {tab}")
        out["curves"][pn] = {"C_uF": c_uf, "colour": col, "table_100k_A": tab, "I_A": {str(int(f)): v for f, v in vals.items()},
                             "check_100k_over_table": round(chk, 3) if chk else None}
    res["charts"][ch] = out
res["resolution"] = "about +/-4 % (dotted / dashed lines fitted over +-10 px; 1 px = 1.6 % at ~146 px per decade)"
res["controls"] = {"failed": fails, "passed": not fails}
OUT.mkdir(exist_ok=True)
(OUT / "kemet_r76_curves.json").write_text(json.dumps(res, indent=1) + "\n")
for ch, c in res["charts"].items():
    print(ch, c["frame_px"])
    for pn, d in c["curves"].items():
        print("  ", pn, d["I_A"], d["check_100k_over_table"])
print("fails", fails)
sys.exit(1 if fails else 0)
