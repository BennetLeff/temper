#!/usr/bin/env python3
"""C34: digitize TDK B3265*A/G/J/T (6/26) permissible-current charts that round 6 did not, numpy only.

    python3 -I scripts/digitize_tdk.py <MKP_B32651_658.pdf>    -> results/tdk_curves_c34.json  (exit 1 on a failed control)

The PDF is not in the repo (TDK: https://www.tdk-electronics.tdk.com/inf/20/20/db/fc_2009/MKP_B32651_658.pdf,
sha256 c32e3754787fa19b2e256e007c98a24755ae18eb52830cce430ffd6b177afdd3). Pages are rendered with
`pdftoppm -gray -r 130` (PGM, read with numpy). For each chart the frame is found from its long grid lines inside a
crop window, log axes are mapped from the frame to the decades printed on the chart, and each curve is traced column
by column as dark-pixel clusters (>= 2 px, rows that are grid lines excluded), top to bottom = largest C first.
Charts (all 'T_A <= 85 C, self-heating dT <= 20 K'):
  p57R  p.57 right, B32654 1600 V DC / 500 V AC (27.5 mm): 220/150/100/47 nF  -> CONTROL against round 6's CSV
  p57B  p.57 bottom-left, B32654 2000 V DC / 700 V AC (27.5 mm): 100/68/47/22 nF
  (p.55 right, B32653 1600 V / 22.5 mm, was tried and dropped: the legend leader lines cross its 35-50 kHz columns.
   B32653 parts are covered by tdk_family_bound.py and do not fit the column.)
Controls: p57R within 3 % of round 6 at 30-99 kHz; p57B 100 kHz end within 6 % of the p.23 table (100/68/47 nF).
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

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "results"
R6 = HERE.parents[2] / "05-resonant-tank-envelope/round6-full-power/outputs/tdk-p57-1600v.csv"
pdf = Path(sys.argv[1])
FREQS = [10e3, 15e3, 20e3, 25e3, 30e3, 35e3, 40e3, 45e3, 50e3, 55e3, 60e3, 70e3, 80e3, 90e3, 99e3]
CHARTS = {
    # page, crop (x0, y0, x1, y1) px at 130 dpi, x decades (left, right), y decades (top, bottom), labels top->bottom
    "p57R": (57, (600, 330, 965, 780), (2, 5), (2, -2), ["220nF", "150nF", "100nF", "47nF"]),
    "p57B": (57, (125, 890, 490, 1345), (2, 5), (2, -2), ["100nF", "68nF", "47nF", "22nF"]),
}
TABLE100K = {"p57B": {"100nF": 10.0, "68nF": 7.8, "47nF": 6.4}}    # p.23 2000 V rows (22 nF: table 4.6 A, chart ~3.6 A; not used)
fails = []
tmp = Path(tempfile.mkdtemp())


def page(n):
    subprocess.run(["pdftoppm", "-gray", "-r", "130", "-f", str(n), "-l", str(n), str(pdf), str(tmp / f"p{n}")], check=True)
    f = next(tmp.glob(f"p{n}*.pgm"))
    raw = f.read_bytes()
    hdr = raw.split(maxsplit=4)
    w, h = int(hdr[1]), int(hdr[2])
    return np.frombuffer(hdr[4][:w * h], np.uint8).reshape(h, w).astype(int)


def digitize(im, crop, xd, yd, labels):
    x0, y0, x1, y1 = crop
    sub = im[y0:y1, x0:x1]
    gcols = [i + x0 for i, c in enumerate((sub < 140).sum(0)) if c > 0.55 * (y1 - y0)]
    grows = [i + y0 for i, c in enumerate((sub < 140).sum(1)) if c > 0.55 * (x1 - x0)]
    xl, xr, yt, yb = min(gcols), max(gcols), min(grows), max(grows)
    dx = (xr - xl) / (xd[1] - xd[0])
    dy = (yb - yt) / (yd[0] - yd[1])
    gr = set(grows)

    def trace(xx):
        col = im[yt + 2:yb - 2, xx]
        dark = [i + yt + 2 for i, v in enumerate(col) if v < 110 and (i + yt + 2) not in gr]
        cl = []
        for y in dark:                      # bridge the 1 px holes left by removed grid rows
            if cl and y - cl[-1][-1] <= 2:
                cl[-1].append(y)
            else:
                cl.append([y])
        cl = [c for c in cl if c[-1] - c[0] >= 1]
        if len(cl) > len(labels):           # leader lines to the legend: drop the thinnest clusters
            cl = sorted(sorted(cl, key=lambda c: c[-1] - c[0], reverse=True)[:len(labels)])
        return [10 ** (yd[0] - ((c[0] + c[-1]) / 2 - yt) / dy) for c in cl]

    out = {}
    for f in FREQS:
        x = round(xl + dx * (math.log10(f) - xd[0]))
        if all(abs(x - g) > 1 for g in gcols):
            out[f] = trace(x)
        else:                               # on a grid column: geometric mean of the two columns 2 px either side
            a_, b_ = trace(x - 2), trace(x + 2)
            out[f] = [math.sqrt(u * v) for u, v in zip(a_, b_)] if len(a_) == len(b_) == len(labels) else a_
    return {"frame_px": [xl, xr, yt, yb], "raw": out}


res = {"pdf_sha256": hashlib.sha256(pdf.read_bytes()).hexdigest(), "render": "pdftoppm -gray -r 130", "charts": {}}
cache = {}
for name, (pg, crop, xd, yd, labels) in CHARTS.items():
    im = cache.setdefault(pg, page(pg))
    d = digitize(im, crop, xd, yd, labels)
    rows = []
    for f, vals in d["raw"].items():
        if len(vals) != len(labels) or (f >= 30e3 and sorted(vals, reverse=True)[len(labels) - 2] < 1.0):
            # leader lines to the legend cross some columns: keep the frequencies where all curves separate
            continue
        rows.append({"f_hz": f, **{f"I_{l}": round(v, 3) for l, v in zip(labels, sorted(vals, reverse=True))}})
    res["charts"][name] = {"page": pg, "frame_px": d["frame_px"], "labels": labels, "rows": rows,
                           "missing_f": [f for f, v in d["raw"].items() if len(v) != len(labels)]}
# controls
r6 = {float(r["f_hz"]): r for r in csv.DictReader(open(R6))}
dev = []
for row in [r for r in res["charts"]["p57R"]["rows"] if r["f_hz"] >= 30e3]:
    for l in ("220nF", "150nF", "100nF", "47nF"):
        a, b = row[f"I_{l}"], float(r6[row["f_hz"]][f"I_{l}"])
        dev.append(abs(a / b - 1))
res["control_p57R_vs_round6_max_dev"] = round(max(dev), 4) if dev else None
if not dev or max(dev) > 0.03:
    fails.append(f"p57R vs round 6: {res['control_p57R_vs_round6_max_dev']}")
for name, tab in TABLE100K.items():
    rows = res["charts"][name]["rows"]
    end = [r for r in rows if r["f_hz"] == 99e3]
    if not end:
        fails.append(f"{name}: no 99 kHz column")
        continue
    chk = {l: round(end[0][f"I_{l}"] / v, 3) for l, v in tab.items()}
    res["charts"][name]["check_99k_over_table_100k"] = chk
    if any(abs(c - 1) > 0.06 for c in chk.values()):
        fails.append(f"{name} 99 kHz vs table {chk}")
    for f in (35e3, 40e3, 45e3, 50e3):
        if not any(r["f_hz"] == f for r in rows):
            fails.append(f"{name} has no column at {f}")
res["resolution"] = "about +/-3 % in current (1 px = 2.1 % at ~110 px/decade); curve line ~3 px"
res["controls"] = {"failed": fails, "passed": not fails}
OUT.mkdir(exist_ok=True)
(OUT / "tdk_curves_c34.json").write_text(json.dumps(res, indent=1) + "\n")
for name, c in res["charts"].items():
    print(name, c["frame_px"], "missing", c["missing_f"], c.get("check_99k_over_table_100k"))
    for r in c["rows"]:
        if r["f_hz"] in (35e3, 40e3, 45e3, 50e3, 99e3):
            print("  ", r)
print("control p57R max dev", res["control_p57R_vs_round6_max_dev"], "fails", fails)
sys.exit(1 if fails else 0)
