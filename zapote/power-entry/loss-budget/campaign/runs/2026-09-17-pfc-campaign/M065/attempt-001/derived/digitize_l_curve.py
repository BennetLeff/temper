#!/usr/bin/env python3
"""Digitize the 'Typical Inductance vs. Current' (left) chart from a WE-TORPFC
datasheet page 2, rendered at 600 dpi.

Chart anatomy (verified on all four sheets):
  * light-grey major gridlines, grey level ~137 (V in 120..170)
  * the traced curve is pure black (V < 60)
  * LEFT chart x gridlines = 0,20,...,120 A (7 lines), y gridlines = 0..YMAX
    every 50 or 100 uH depending on the part.

Calibration: detected gridline positions, first vertical -> 0 A, last -> 120 A;
first horizontal -> YMAX (printed top label), last -> 0 uH.
Cross-check: at the part's printed ISAT the curve should read ~0.70*nominal L
(|dL/L| < 30 % definition used by this family).

This is a GRAPH DIGITISER, not a tabulated datasheet value. Outputs are labelled
'typical, digitized from datasheet page-2 curve'. No smoothing/fitting; each
requested current uses traced columns within +/-0.6 A and their median.
"""
import json
import numpy as np
from PIL import Image


def clus(vals, gap=12):
    out, cur = [], [vals[0]]
    for v in vals[1:]:
        if v - cur[-1] <= gap:
            cur.append(v)
        else:
            out.append(int(round(sum(cur) / len(cur)))); cur = [v]
    out.append(int(round(sum(cur) / len(cur))))
    return out


def digitize(png, xmax, ymax, isat, currents):
    a = np.asarray(Image.open(png).convert("RGB")).astype(np.int16)
    V = a.max(axis=2)
    H, W = V.shape
    grey = V < 185          # gridlines AND frame ink (curve is separated by V<60)
    black = V < 60
    xlim = int(0.49 * W)                       # keep only the LEFT chart

    # pass 1: horizontal gridlines using an interior band of the left chart
    xb0, xb1 = int(0.14 * W), int(0.46 * W)
    rows = [r for r in range(1, H - 1)
            if grey[r, xb0:xb1].sum() > 0.55 * (xb1 - xb0)]
    hlines = clus(rows)
    rtop, rbot = hlines[0], hlines[-1]

    # pass 2: vertical gridlines spanning the plot height
    cols = [c for c in range(1, xlim)
            if grey[rtop:rbot, c].sum() > 0.55 * (rbot - rtop)]
    vlines = clus(cols)
    if len(vlines) < 2:
        raise SystemExit(f"{png}: vertical gridlines not found {vlines}")

    x0, x1 = vlines[0], vlines[-1]
    sx = xmax / (x1 - x0)
    sy = ymax / (rbot - rtop)

    m = 6
    pts = []
    for x in range(x0 + m, x1 - m + 1):
        col = np.where(black[rtop + m:rbot - m, x])[0]
        if len(col) == 0:
            continue
        # contiguous runs; the curve is the longest run
        runs, s, p = [], col[0], col[0]
        for v in col[1:]:
            if v - p <= 3:
                p = v
            else:
                runs.append((s, p)); s = p = v
        runs.append((s, p))
        runs.sort(key=lambda r: r[1] - r[0], reverse=True)
        s, p = runs[0]
        L = (rbot - ((s + p) / 2 + rtop + m)) * sy
        I = (x - x0) * sx
        if -3 <= L <= ymax * 1.03:
            pts.append((I, L))
    pts = np.array(sorted(pts))
    res = {}
    for cur in currents:
        near = pts[np.abs(pts[:, 0] - cur) <= 0.6]
        res[str(cur)] = None if len(near) == 0 else float(np.median(near[:, 1]))

    def at(cur):
        near = pts[np.abs(pts[:, 0] - cur) <= 0.6]
        return None if len(near) == 0 else float(np.median(near[:, 1]))

    return {
        "png": png, "xmax_A": xmax, "ymax_uH": ymax,
        "grid_vlines_px": vlines, "grid_hlines_px": hlines,
        "px_per_A": sx, "px_per_uH": sy,
        "L_at_currents_uH": res,
        "L_read_at_isat_uH": at(isat),
        "n_traced_points": len(pts),
        "L_at_0A_uH": at(0.0), "L_at_60A_uH": at(60.0),
    }


if __name__ == "__main__":
    SPEC = {  # part -> (xmax A, ymax uH, ISAT A, nominal uH)
        "760800301": (120.0, 250.0, 43.0, 180.0),
        "760801202": (120.0, 450.0, 37.0, 389.0),
        "760801403": (120.0, 400.0, 23.0, 355.0),
        "760801321": (160.0, 800.0, 38.0, 720.0),
    }
    currents = [0, 5, 10, 11.5, 12.3, 15, 17.2, 20, 23.2719, 25, 30, 35, 37, 40, 50, 60]
    out = {}
    for part, (xmax, ymax, isat, nom) in SPEC.items():
        r = digitize(f"derived/{part}-page2.png", xmax, ymax, isat, currents)
        r["isat_a"] = isat
        r["nominal_uH"] = nom
        r["isat_crosscheck_ratio"] = (None if r["L_read_at_isat_uH"] is None
                                      else r["L_read_at_isat_uH"] / nom)
        out[part] = r
    print(json.dumps(out, indent=2))
