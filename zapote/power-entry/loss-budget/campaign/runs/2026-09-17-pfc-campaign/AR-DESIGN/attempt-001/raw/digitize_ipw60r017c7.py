#!/usr/bin/env python3
"""Digitize two IPW60R017C7 figures from the captured PDF render.

Evidence class: manufacturer_datasheet_figure_digitized.  NOT a guaranteed
limit; these are typical/labelled-percentile curves.  Calibration is taken
from the manufacturer's own labelled gridlines, hard-coded below and printed
as anchors so a reviewer can verify the mapping rather than trust a number.

Diagram 8 (p.8 right): RDS(on)=f(Tj); ID=58.2A; VGS=10V  -> k_T(Tj), typ & 98%
Diagram 7 (p.8 left) : RDS(on)=f(ID); Tj=125C; VGS family -> VGS ratio

Curves are separated from gridlines by stroke width: at 400 dpi the plotted
curves are ~7-12 px thick, the gridlines ~3-4 px.
"""
import json
import numpy as np
from PIL import Image

P8 = "fig_p8-08.png"

# ---- Diagram 8 calibration (rows are pixel rows inside the p.8 lower-right crop)
D8_Y = ((484, 0.040), 191.0 / 0.005)      # (row, value) then px per ohm
D8_X = ((292, -50), 150.0 / 25.0)         # (col, value) then px per degC


def d8_R(row):
    return D8_Y[0][1] - (row - D8_Y[0][0]) / D8_Y[1]


def d8_T(col):
    return D8_X[0][1] + (col - D8_X[0][0]) / D8_X[1]


# ---- Diagram 7 calibration
D7_Y = ((485, 0.070), 334.5 / 0.010)      # px per ohm
D7_X = ((449, 0.0), 2.4)                  # px per amp


def d7_R(row):
    return D7_Y[0][1] - (row - D7_Y[0][0]) / D7_Y[1]


def d7_ID(col):
    return D7_X[0][1] + (col - D7_X[0][0]) / D7_X[1]


def dark(im):
    return np.asarray(im.convert("L")).astype(np.int16) < 130


def runs(mask, c, r0, r1, min_w):
    col = mask[r0:r1 + 1, c]
    out, i, n = [], 0, len(col)
    while i < n:
        if col[i]:
            j = i
            while j < n and col[j]:
                j += 1
            if j - i >= min_w:
                out.append((r0 + (i + j - 1) / 2.0, j - i))
            i = j
        else:
            i += 1
    return out


def main():
    im = Image.open(P8)
    W, H = im.size
    p8lo = im.crop((W // 2, int(0.46 * H), W, int(0.90 * H)))   # D8
    p8ll = im.crop((0, int(0.46 * H), W // 2, int(0.90 * H)))   # D7
    m8, m7 = dark(p8lo), dark(p8ll)

    # ---------------- Diagram 8 ----------------
    d8_typ, d8_p98 = {}, {}
    for T in range(-45, 151, 5):
        c = int(round(D8_X[0][0] + (T - D8_X[0][1]) * D8_X[1])) + 12
        rr = [r for r, w in runs(m8, c, 490, 1820, 6) if d8_R(r) < 0.045]
        if len(rr) >= 2:
            d8_p98[T] = round(d8_R(min(rr)), 5)   # higher R
            d8_typ[T] = round(d8_R(max(rr)), 5)   # lower R
    # ---------------- Diagram 7 ----------------
    d7 = {}
    for ID in (15, 21, 30, 45, 60, 90, 120):
        c = int(round(D7_X[0][0] + ID * D7_X[1])) + 13
        rr = sorted([(d7_R(r), w) for r, w in runs(m7, c, 490, 1820, 6)
                     if 0.030 < d7_R(r) < 0.062], reverse=True)
        d7[ID] = [round(v, 5) for v, w in rr]

    out = {
        "source": "Infineon IPW60R017C7 Final Data Sheet Rev 2.0 2016-03-01, page 8",
        "evidence_class": "manufacturer_datasheet_figure_digitized",
        "explicit_table_rows": {
            "RDS(on) VGS=10V ID=58.2A Tj=25C": "typ 0.015, max 0.017 ohm (p.5)",
            "RDS(on) VGS=10V ID=58.2A Tj=150C": "typ 0.033 ohm (p.5)",
            "calibration_check_25C_typ_ohm": 0.015,
            "calibration_check_150C_typ_ohm": 0.033,
        },
        "diagram_8_typ_ohm_vs_Tj": {str(k): v for k, v in sorted(d8_typ.items())},
        "diagram_8_p98_ohm_vs_Tj": {str(k): v for k, v in sorted(d8_p98.items())},
        "diagram_7_rds_family_vs_ID_at_125C_ohm": {
            str(k): v for k, v in sorted(d7.items())
        },
        "diagram_7_note": "list is descending R; VGS order 5.5,6,6.5,7,10,20 V",
        "calibration_anchors": {
            "d8_y_major_rows_values": [[484, 0.040], [1822, 0.005]],
            "d8_x_major_cols_values": [[292, -50], [1492, 150]],
            "d7_y_major_rows_values": [[485, 0.070], [1823, 0.030]],
            "d7_x_major_cols_values": [[449, 0.0], [1648, 500.0]],
        },
    }
    print(json.dumps(out, indent=2))
    with open("digitized_ipw60r017c7.json", "w") as f:
        json.dump(out, f, indent=2)


if __name__ == "__main__":
    main()
