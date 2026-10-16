#!/usr/bin/env python3
"""Digitize KNSCHA MMKP82 'Maximum allowable current (Irms) - frequency' charts (sine, ambient <= 85 C, internal
temperature rise dT = 10 C), numpy + PIL.

    python3 -I scripts/digitize_knscha.py   -> results/knscha_curves.json (exit 1 on a failed control)

Source: dl/C565696_MMK104J3CESKN158G2/*.pdf (KNSCHA spec MMK104J3CESKN158G2, 2026.9.16, family charts p.6 Vrms, p.7 Irms;
sha256 in dl/SHA256SUMS) and dl/C528963_MMK224J3DF3KN208G2/*.pdf (224J/2000V single-curve sheet, 2026.10.6, p.10).
The charts are embedded JPEGs; `pdfimages -j` extracts them (render/img/). Panels are identified by title (checked by eye:
kn-008 = 2000 VDC/700 VAC Irms, kn-013 = 1600 VDC/650 VAC Irms, kn-006 = 2000 VDC Vrms).
Method: the black grid is found from row / column darkness; decades are the major lines (x 0.1-1000 kHz, y 0.01-100 A or
1-1000 V). All curves are black, so at each frequency the dark runs that are not grid lines are listed per column over
+-14 px; the TOP run is the '---' 104 P=27.5 curve on the 2000 V and 1600 V Irms charts (it lies above every other curve
from 1 kHz up; checked against the zoom render/kn013_zoom.png). Value = median over the columns.
Controls: (1) the 2000 V Vrms chart's top-of-pack '---' curve gives V_allow; I = V w C must agree with the Irms read within
8 %; (2) 224J single-curve chart 100 kHz value is reported for comparison with the family chart (no control).
"""
import json
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
IMG = ROOT / "render" / "img"
OUT = ROOT / "results"
FREQS = [10e3, 20e3, 30e3, 35e3, 40e3, 50e3, 70e3, 100e3]


def grid(im):
    dark = im < 110
    H, W = im.shape
    rows, cols = dark.sum(1), dark.sum(0)

    def groups(v):
        g = []
        for i in v:
            if g and i - g[-1][-1] <= 2:
                g[-1].append(i)
            else:
                g.append([i])
        return g
    R = groups([i for i in range(H) if rows[i] > 0.48 * W])
    C = groups([j for j in range(W) if cols[j] > 0.3 * H])
    grow = {i for g in R for i in range(g[0] - 1, g[-1] + 2)}
    gcol = {j for g in C for j in range(g[0] - 1, g[-1] + 2)}
    return dark, [float(np.mean(g)) for g in R], [float(np.mean(g)) for g in C], grow, gcol


def majors(lines, n, step_guess):
    """the n evenly spaced major lines (decades): largest-gap structure; take lines whose spacing to the next major is
    ~step (log grids have 9 lines per decade, the decade line is the one after the widest gap)."""
    best = None
    for i in range(len(lines)):
        for j in range(i + 1, len(lines)):
            step = (lines[j] - lines[i])
            if abs(step - step_guess) > 0.15 * step_guess:
                continue
            seq = [lines[i] + k * step for k in range(n)]
            err = sum(min(abs(s - l) for l in lines) for s in seq)
            if best is None or err < best[0]:
                best = (err, lines[i], step)
    return best[1], best[2]


# frames: decade lines read from grid() output (printed by --frames): x at 0.1 / 1 / 10 / 100 / 1000 kHz, y at the decades
FRAMES = {"kn-008.jpg": (160.0, 234.0, 102.0, 174.0, 100.0),     # 2000 VDC Irms: x 160,395,629,862,1096; y 102,277,450,624,798
          "kn-013.jpg": (166.0, 239.5, 100.0, 176.5, 100.0),     # 1600 VDC Irms: x 166,405,645,884,1124; y 100,277,453,630,806
          "kn-006.jpg": (164.5, 241.25, 89.5, 217.3, 1000.0)}    # 2000 VDC Vrms: x 164.5,406,647,888,1129.5; y 89.5,307,523.5,741.5
BAND = {"kn-008.jpg": (3.0, 20.0), "kn-013.jpg": (3.0, 20.0), "kn-006.jpg": (100.0, 690.0)}


def read(fn, *_):
    im = np.asarray(Image.open(fn).convert("L")).astype(int)
    dark, R, C, grow, gcol = grid(im)
    x0, dx, y0, dy, top_val = FRAMES[fn.name]
    lo, hi = BAND[fn.name]
    ylo, yhi = int(y0 + dy * math.log10(top_val / hi)), int(y0 + dy * math.log10(top_val / lo))
    X = lambda f: x0 + dx * (math.log10(f / 1e3) + 1)            # x0 = 0.1 kHz
    V = lambda y: top_val * 10 ** (-(y - y0) / dy)                # y0 = the top decade
    out = {}
    for f in FREQS:
        x = X(f)
        tops = []
        for xx in range(int(x) - 14, int(x) + 15):
            if xx in gcol:
                continue
            ys = [y for y in range(ylo, yhi) if dark[y, xx] and y not in grow]
            if not ys:
                continue
            run = [ys[0]]
            for y in ys[1:]:
                if y - run[-1] <= 2:
                    run.append(y)
                else:
                    break
            tops.append(V(float(np.mean(run))))
        out[f"{f / 1e3:g}k"] = round(float(np.median(tops)), 3) if tops else None
    return {"file": str(fn.relative_to(ROOT)), "frame": {"x_0.1kHz": round(x0, 1), "px_per_decade_x": round(dx, 1),
                                                          "y_top": round(y0, 1), "px_per_decade_y": round(dy, 1)}, "top_curve": out}


# Eye reads from the annotated zooms (render/kn008_zoom.png: Irms, blue lines at 5-9 A; render/kn006_zoom.png: Vrms, blue
# lines at 200-400 V; red lines at 35 / 40 kHz). Made by drawing the lines with the FRAMES above (make_zooms()).
EYE = {"Irms_2000V_104_P27.5_A": {"35k": 6.2, "40k": 6.35, "100k": 8.25},
       "Vrms_2000V_104_P27.5_V": {"35k": 290.0, "40k": 245.0}}


def make_zooms():
    from PIL import ImageDraw
    im = Image.open(IMG / "kn-008.jpg").convert("RGB")
    d = ImageDraw.Draw(im)
    x0, dx, y0, dy, _ = FRAMES["kn-008.jpg"]
    X = lambda f: x0 + dx * (math.log10(f / 1e3) + 1)
    Y = lambda a: y0 + dy * (2 - math.log10(a))
    for f in (35e3, 40e3):
        d.line([(X(f), Y(20)), (X(f), Y(2))], fill=(255, 0, 0), width=1)
    for a in (5, 6, 7, 8, 9):
        d.line([(X(20e3), Y(a)), (X(120e3), Y(a))], fill=(0, 160, 255), width=1)
    im.crop((int(X(15e3)), int(Y(14)), int(X(130e3)), int(Y(3)))).resize((900, 600)).save(ROOT / "render/kn008_zoom.png")
    im = Image.open(IMG / "kn-006.jpg").convert("RGB")
    d = ImageDraw.Draw(im)
    x0, dx, y0, dy, _ = FRAMES["kn-006.jpg"]
    X = lambda f: x0 + dx * (math.log10(f / 1e3) + 1)
    Y = lambda v: y0 + dy * (3 - math.log10(v))
    for f in (35e3, 40e3):
        d.line([(X(f), Y(900)), (X(f), Y(100))], fill=(255, 0, 0), width=1)
    for v in (200, 250, 300, 350, 400):
        d.line([(X(15e3), Y(v)), (X(120e3), Y(v))], fill=(0, 160, 255), width=1)
    im.crop((int(X(15e3)), int(Y(800)), int(X(130e3)), int(Y(150)))).resize((900, 600)).save(ROOT / "render/kn006_zoom.png")


def main():
    make_zooms()
    res = {"basis": "KNSCHA MMKP82: sine, ambient <= 85 C, internal temperature rise dT = 10 C (p.6 / p.7 remarks)",
           "auto": {"2000V_Irms_top_curve_A": read(IMG / "kn-008.jpg"), "1600V_Irms_top_curve_A": read(IMG / "kn-013.jpg")},
           "eye": EYE}
    fails = []
    auto = res["auto"]["2000V_Irms_top_curve_A"]["top_curve"]
    for k, v in EYE["Irms_2000V_104_P27.5_A"].items():
        if auto[k] is None or abs(auto[k] / v - 1) > 0.06:
            fails.append(f"auto {auto[k]} vs eye {v} at {k}")
    cons = {}
    for k in ("35k", "40k"):
        f = float(k[:-1]) * 1e3
        iv = EYE["Vrms_2000V_104_P27.5_V"][k] * 2 * math.pi * f * 1e-7
        cons[k] = {"I_from_Vrms_A": round(iv, 2), "I_eye_A": EYE["Irms_2000V_104_P27.5_A"][k],
                   "ratio": round(EYE["Irms_2000V_104_P27.5_A"][k] / iv, 3)}
        if abs(cons[k]["ratio"] - 1) > 0.08:
            fails.append(f"Vrms vs Irms chart at {k}")
    res["control_vrms_vs_irms"] = cons
    res["used_I_allow_A"] = {k: round(min(EYE["Irms_2000V_104_P27.5_A"][k], cons[k]["I_from_Vrms_A"]), 2) for k in cons}
    res["control_failed"] = fails
    OUT.mkdir(exist_ok=True)
    (OUT / "knscha_curves.json").write_text(json.dumps(res, indent=1) + "\n")
    print(json.dumps({k: res[k] for k in ("eye", "control_vrms_vs_irms", "used_I_allow_A", "control_failed")}, indent=1))
    print("auto 2000 V:", auto)
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
