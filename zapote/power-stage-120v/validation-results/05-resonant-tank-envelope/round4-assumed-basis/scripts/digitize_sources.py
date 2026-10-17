#!/usr/bin/env python3
"""Digitize the three published charts the assumed coil/pan/capacitor basis rests on.

ASSUMED / pre-measurement evidence. The charts are vendor plots, not tables; every
value written here is a chart reading with the stated pixel resolution.

Inputs (PDFs are NOT committed except 942C.pdf, which task 05 already carries;
sources/README.md gives URL and SHA-256 for each):
  --onsemi   onsemi AND9201/D "The Effect of Pan Material in an Induction Cooker",
             Rev. 0, January 2015, p. 7 Fig. 9 (series L) and Fig. 10 (series R)
  --infineon Infineon UG-2023-15 "EVAL-IHW25N140R5L user guide", Rev. 1.0,
             2023-08-04, p. 21 Fig. 16 (resonant load L and R with/without vessel)
  --cde      CDE Type 942C catalogue (942C.pdf), printed p. 4, 1200 Vdc panel,
             "RMS Voltage vs Frequency @ 25 C" (0.1 / 0.33 / 0.9 uF)

Renders each page with pdftoppm at 300 dpi, calibrates axes from the gridline pixel
positions recorded below (found by scanning for full-height gray/black lines), and
takes the median row of each curve's colour per pixel column. Writes
outputs/digitized-*.csv.

Usage: python3 digitize_sources.py --onsemi AND9201.pdf --infineon ug.pdf --cde 942C.pdf
"""
import argparse
import csv
import math
import os
import subprocess
import tempfile

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "outputs")

FREQS_KHZ = [20, 25, 30, 35, 40, 45, 50, 55, 60]


def render(pdf, page, tmp):
    stem = os.path.join(tmp, f"p{page}")
    subprocess.run(["pdftoppm", "-r", "300", "-f", str(page), "-l", str(page), "-png", pdf, stem],
                   check=True)
    name = [f for f in os.listdir(tmp) if f.startswith(f"p{page}") and f.endswith(".png")][0]
    return np.array(Image.open(os.path.join(tmp, name)).convert("RGB")).astype(int)


def color_mask(img, rgb, tol=38):
    d = np.sqrt(((img - np.array(rgb)) ** 2).sum(axis=2))
    return d < tol


def column_rows(mask, x, y0, y1, halfwidth=2):
    ys = []
    for xx in range(x - halfwidth, x + halfwidth + 1):
        ys.extend(list(np.nonzero(mask[y0:y1, xx])[0] + y0))
    return ys


def clusters(ys, gap=6):
    """Split sorted row indices into contiguous groups; return group medians."""
    if not ys:
        return []
    ys = sorted(ys)
    groups, cur = [], [ys[0]]
    for y in ys[1:]:
        if y - cur[-1] <= gap:
            cur.append(y)
        else:
            groups.append(cur)
            cur = [y]
    groups.append(cur)
    return [float(np.median(g)) for g in groups if len(g) >= 3]


def sample(fn_px, mask, xs_needed, y0, y1, pick, search=14):
    """For each target x, look outward up to `search` px for a column with the curve.

    Columns where the mask covers more than half the window are gridlines and skipped."""
    out = []
    for x in xs_needed:
        val = None
        for dx in [0] + [s * k for k in range(1, search + 1) for s in (1, -1)]:
            ys = column_rows(mask, x + dx, y0, y1, 0)
            if len(ys) > 0.5 * (y1 - y0):
                continue
            groups = clusters(ys)
            v = pick(groups)
            if v is not None:
                val = v
                break
        out.append(val)
    return out


def onsemi(pdf, tmp):
    img = render(pdf, 7, tmp)
    # Fig. 10 series R: x decades 1k/10k/100k/1M at px 711.5/1138.5/1565.5/1992.5,
    # y decades 100/10/1/0.1/0.01 ohm at 1390/1563/1736/1909/2082.
    rx = lambda f_khz: 711.5 + 427.0 * math.log10(f_khz)
    r_of_y = lambda y: 10 ** (2 - (y - 1390.0) / 173.0)
    # Fig. 9 series L: x decades at px 678/1117/1556/1995, y 0..160 uH at 1010..252.5.
    lx = lambda f_khz: 678.0 + 439.0 * math.log10(f_khz)
    l_of_y = lambda y: (1010.0 - y) / 4.7375
    # name: (rgb, R window ohm, L window uH). Windows keep each colour to the band its
    # curve occupies over 20-60 kHz (checked visually) and away from other legend text.
    colors = {
        "no_pan": ((65, 111, 166), (0.1, 0.45), (100, 120)),
        "aluminium": ((168, 66, 63), (0.15, 0.6), (45, 60)),
        "five_ply_430_clad": ((61, 150, 174), (1.0, 8.0), (55, 100)),
        "cast_iron": ((218, 129, 55), (1.0, 8.0), (55, 100)),
        "ss304_duxtop": ((134, 164, 74), (1.0, 8.0), (55, 100)),
        "ss430_midea": ((110, 84, 141), (1.0, 8.0), (55, 100)),
    }
    ry_of = lambda r: 1390.0 + 173.0 * (2 - math.log10(r))
    ly_of = lambda l: 1010.0 - 4.7375 * l
    # bottom-most group = the curve (legend labels sit above their curves)
    last = lambda g: g[-1] if g else None
    rows = []
    for name, (rgb, rwin, lwin) in colors.items():
        m = color_mask(img, rgb, 24)
        rs = sample(None, m, [int(round(rx(f))) for f in FREQS_KHZ],
                    int(ry_of(rwin[1])), int(ry_of(rwin[0])), last)
        ls = sample(None, m, [int(round(lx(f))) for f in FREQS_KHZ],
                    int(ly_of(lwin[1])), int(ly_of(lwin[0])), last)
        for f, ry, ly in zip(FREQS_KHZ, rs, ls):
            note = ""
            if name == "ss304_duxtop" and f > 25:
                # Above 25 kHz the green trace runs under the cast-iron/430 traces and the
                # pixels found are the "304 SS" legend text: discard (visual check).
                ly, note = None, "L above 25 kHz hidden under ferrous traces; R hidden"
            if name in ("ss304_duxtop", "ss430_midea") and ry is None:
                note = note or "R hidden under cast-iron trace (overlaps within line width)"
            if name == "five_ply_430_clad" and ly is None:
                note = "L hidden under cast-iron/430 traces (overlaps within line width)"
            rows.append({"source": "onsemi_AND9201_p7", "series": name, "f_khz": f,
                         "R_ohm": None if ry is None else round(r_of_y(ry), 4),
                         "L_uH": None if ly is None else round(l_of_y(ly), 2), "note": note})
    return rows


def infineon(pdf, tmp):
    img = render(pdf, 21, tmp)
    # x: 0..50 kHz at px 586..1869.5 (256.7 px per 10 kHz); y: 0 at 1807, top 875
    # = 4000 mOhm (left) = 120 uH (right).
    xf = lambda f_khz: 586.0 + 25.67 * f_khz
    r_of_y = lambda y: (1807.0 - y) / 0.2330 / 1000.0
    l_of_y = lambda y: (1807.0 - y) / 7.7667
    mr = color_mask(img, (146, 130, 133), 30)
    ml = color_mask(img, (171, 55, 122), 30)
    xs = [int(round(xf(f))) for f in FREQS_KHZ if f <= 50]
    fs = [f for f in FREQS_KHZ if f <= 50]
    # R: top group = with vessel, bottom group = without; L at >=15 kHz: top = without.
    r_ves = sample(None, mr, xs, 870, 1812, lambda g: g[0] if len(g) >= 2 else None)
    r_no = sample(None, mr, xs, 1500, 1812, lambda g: g[-1] if g else None)
    l_no = sample(None, ml, xs, 870, 1812, lambda g: g[0] if len(g) >= 2 else None)
    l_ves = sample(None, ml, xs, 870, 1812, lambda g: g[-1] if len(g) >= 2 else None)
    rows = []
    for f, a, b, c, d in zip(fs, r_no, r_ves, l_no, l_ves):
        rows.append({"source": "infineon_UG-2023-15_p21_fig16", "series": "no_vessel", "f_khz": f,
                     "R_ohm": None if a is None else round(r_of_y(a), 4),
                     "L_uH": None if c is None else round(l_of_y(c), 2)})
        rows.append({"source": "infineon_UG-2023-15_p21_fig16", "series": "with_vessel", "f_khz": f,
                     "R_ohm": None if b is None else round(r_of_y(b), 4),
                     "L_uH": None if d is None else round(l_of_y(d), 2)})
    return rows


def cde(pdf, tmp):
    img = render(pdf, 4, tmp)
    # 1200 Vdc panel: x decades 10 Hz..100 kHz at px 1405/1636/1867/2098/2329,
    # y 0..500 V at px 2012.5..1523 (0.98 px/V). Gridlines every 50 V.
    xf = lambda f_hz: 1405.0 + 231.0 * math.log10(f_hz / 10.0)
    v_of_y = lambda y: (2012.5 - y) / 0.98
    red = color_mask(img, (255, 0, 0), 60)
    # black curve: dark pixels that are not on a horizontal gridline row
    dark = img.sum(axis=2) < 200
    grid_rows = [int(round(2012.5 - 0.98 * v)) for v in range(0, 501, 50)]
    for gy in grid_rows:
        dark[gy - 3:gy + 4, :] = False
    freqs = [20000, 25000, 30000, 35000, 40000, 45000, 50000, 55000, 60000, 70000, 100000]
    xs = [int(round(xf(f))) for f in freqs]
    # In 20-100 kHz the 0.1 uF red trace is the upper red group, 0.9 uF the lower.
    v01 = sample(None, red, xs, 1530, 2010, lambda g: g[0] if g else None)
    v09 = sample(None, red, xs, 1530, 2010, lambda g: g[-1] if len(g) >= 2 else None)
    v033 = sample(None, dark, xs, 1530, 2005, lambda g: g[0] if g else None, search=8)
    rows = []
    for f, a, b, c in zip(freqs, v01, v033, v09):
        for cap, y in (("0.10uF", a), ("0.33uF", b), ("0.90uF", c)):
            v = None if y is None else round(v_of_y(y), 1)
            c_f = float(cap[:-2]) * 1e-6
            rows.append({"source": "CDE_942C_p4_1200Vdc_25C", "series": cap, "f_hz": f,
                         "Vrms_allow_25C": v,
                         "Irms_implied_25C": None if v is None else round(v * 2 * math.pi * f * c_f, 2)})
    return rows


def write(rows, name):
    path = os.path.join(OUT, name)
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print("wrote", os.path.relpath(path, os.path.join(HERE, "..")), len(rows), "rows")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--onsemi", required=True)
    ap.add_argument("--infineon", required=True)
    ap.add_argument("--cde", required=True)
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    with tempfile.TemporaryDirectory() as t1, tempfile.TemporaryDirectory() as t2, \
            tempfile.TemporaryDirectory() as t3:
        write(onsemi(a.onsemi, t1), "digitized-onsemi-and9201.csv")
        write(infineon(a.infineon, t2), "digitized-infineon-fig16.csv")
        write(cde(a.cde, t3), "digitized-cde-942c-1200vdc.csv")


if __name__ == "__main__":
    main()
