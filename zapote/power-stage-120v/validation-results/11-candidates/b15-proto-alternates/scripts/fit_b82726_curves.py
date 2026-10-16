#!/usr/bin/env python3
"""Digitise TDK B82726S22*3A020 (May 2026) p.5 impedance curves from the PDF's vector paths and fit the
round-3 parallel R||L||C choke model (07-conducted-emi/round3/scripts/fit_choke.py) to both parts.

Usage: python3 -I fit_b82726_curves.py <p5.svg> <out.json>
  p5.svg = `pdftocairo -f 5 -l 5 -svg b82726s22x3.pdf p5.svg` (PDF sha256 e8002bfe4af13edf..., the ledger copy).

The curves are exact vector strokes (no pixel tracing), so the only digitisation error is the stroke centre-line.
Control: the B82726S2203A020 fit is compared with round 3's bitmap fit (11.078 pF / 12.691 kOhm per winding).
"""
from __future__ import annotations

import json
import re
import sys

import numpy as np
from scipy.optimize import least_squares

# plot frame of the left chart (page points, from the 0.282-pt frame path: x 86.30..266.38, y 418.39..187.78)
X0, X1 = 86.300824, 86.300824 + 0.998991 * 180.267806      # 1e4 .. 1e7 Hz
Y0, Y1 = 418.394343, 418.394343 - 0.998442 * 230.969129     # 1e1 .. 1e6 ohm

PARTS = {  # TDK p.4 ordering table
    "B82726S2203A020": dict(L=1.6e-3, Lstray=18e-6, R=4.5e-3, line=None),
    "B82726S2243A020": dict(L=0.75e-3, Lstray=8e-6, R=3.2e-3, line=None),
}


def bez(p0, p1, p2, p3, n=40):
    t = np.linspace(0, 1, n)[:, None]
    return ((1 - t) ** 3) * p0 + 3 * ((1 - t) ** 2) * t * p1 + 3 * (1 - t) * t * t * p2 + t ** 3 * p3


def path_points(d, tf):
    a, b, c, dd, e, f = tf
    toks = re.findall(r"[MLC]|-?\d+\.?\d*(?:e-?\d+)?", d)
    pts, cur, i = [], None, 0
    while i < len(toks):
        cmd = toks[i]; i += 1
        if cmd in "ML":
            cur = np.array([float(toks[i]), float(toks[i + 1])]); i += 2
            pts.append(cur[None, :])
        elif cmd == "C":
            p = [np.array([float(toks[i + 2 * k]), float(toks[i + 2 * k + 1])]) for k in range(3)]; i += 6
            pts.append(bez(cur, p[0], p[1], p[2])[1:])
            cur = p[2]
    P = np.vstack(pts)
    x = a * P[:, 0] + c * P[:, 1] + e
    y = b * P[:, 0] + dd * P[:, 1] + f
    return x, y


def to_fz(x, y):
    fr = 10 ** (4 + 3 * (x - X0) / (X1 - X0))
    z = 10 ** (1 + 5 * (Y0 - y) / (Y0 - Y1))
    return fr, z


def fit(fr, z, L, Lstray, Rdc):
    Lp = L * (1 + (1 - Lstray / (2 * L))) / 2       # windings in parallel (round-3 convention)
    Rp = Rdc / 2

    def zmod(f, R, C):
        w = 2 * np.pi * f
        y = 1 / (Rp + 1j * w * Lp) + 1 / R + 1j * w * C
        return np.abs(1 / y)

    # fit below 3 MHz (TDK: model accuracy is below the first resonance; keep the round-3 band 10 kHz..~7 MHz too)
    res = {}
    for name, sel in (("10k_10M", fr <= 1e7), ("10k_3M", fr <= 3e6)):
        r = least_squares(lambda p: np.log10(zmod(fr[sel], p[0], p[1] * 1e-12) / z[sel]),
                          x0=[6000, 30], bounds=([100, 1], [1e6, 1000]))
        R, Cpf = r.x
        err = 20 * np.log10(zmod(fr[sel], R, Cpf * 1e-12) / z[sel])
        res[name] = {"parallel_R_ohm": float(R), "parallel_C_pF": float(Cpf),
                     "per_winding_R_ohm": float(2 * R), "per_winding_C_pF": float(Cpf / 2),
                     "self_res_hz": float(1 / (2 * np.pi * np.sqrt(Lp * Cpf * 1e-12))),
                     "rmse_dB": float(np.sqrt(np.mean(err ** 2))), "max_abs_err_dB": float(np.max(np.abs(err))),
                     "n_points": int(sel.sum())}
    # inductance check: |Z| at 10 kHz vs w*Lp (the low-frequency asymptote)
    i10 = np.argmin(np.abs(fr - 1e4 * 1.05))
    i100 = np.argmin(np.abs(fr - 1e5))
    lf = {"Z_at_%.0fHz" % fr[i10]: float(z[i10]), "wLp_ohm": float(2 * np.pi * fr[i10] * Lp),
          "Z_at_%.0fHz" % fr[i100]: float(z[i100]), "wLp_100k_ohm": float(2 * np.pi * fr[i100] * Lp),
          "L_par_from_curve_10k_H": float(z[i10] / (2 * np.pi * fr[i10])),
          "L_par_from_curve_100k_H": float(z[i100] / (2 * np.pi * fr[i100])), "L_par_model_H": Lp}
    return res, lf


def main():
    svg, out = sys.argv[1], sys.argv[2]
    txt = open(svg).read()
    paths = re.findall(r'<path[^>]*stroke-width="1.69"[^>]*d="([^"]+)"[^>]*transform="matrix\(([^)]+)\)"', txt)
    curves = []
    for d, tf in paths:
        tfv = [float(v) for v in tf.replace(",", " ").split()]
        x, y = path_points(d, tfv)
        if x.min() < X0 - 1 or x.max() > X1 + 1:   # the derating chart (right) is out of frame
            continue
        fr, z = to_fz(x, y)
        o = np.argsort(fr)
        curves.append((fr[o], z[o]))
    assert len(curves) == 2, len(curves)
    # higher peak = 2203 (TDK legend order; 2203 has the higher 10 kHz impedance, 1.6 mH vs 0.75 mH)
    curves.sort(key=lambda c: -c[1][0])
    result = {"source": "TDK B82726S22*3A020 data sheet May 2026 p.5, plot IND0783-T, vector paths (stroke 1.69 pt)",
              "frame_pt": {"x_1e4": X0, "x_1e7": X1, "y_1e1": Y0, "y_1e6": Y1}, "parts": {}}
    for (fr, z), (mpn, p) in zip(curves, PARTS.items()):
        res, lf = fit(fr, z, p["L"], p["Lstray"], p["R"])
        ipk = int(np.argmax(z))
        result["parts"][mpn] = {"datasheet": {k: v for k, v in p.items() if k != "line"}, "fit": res, "low_freq": lf,
                                "curve_peak": {"f_hz": float(fr[ipk]), "Z_ohm": float(z[ipk])},
                                "curve": [[float(a), float(b)] for a, b in zip(fr[::4], z[::4])]}
    c = result["parts"]["B82726S2203A020"]["fit"]["10k_10M"]
    result["control_vs_round3_bitmap_fit"] = {
        "round3_per_winding_C_pF": 11.078, "round3_per_winding_R_ohm": 12691.0,
        "vector_per_winding_C_pF": c["per_winding_C_pF"], "vector_per_winding_R_ohm": c["per_winding_R_ohm"],
        "round3_digitisation_range_parallel_C_pF": [19.73, 24.88]}
    open(out, "w").write(json.dumps(result, indent=1) + "\n")
    for mpn, v in result["parts"].items():
        print(mpn, json.dumps(v["fit"]), json.dumps(v["low_freq"]), v["curve_peak"])
    print(json.dumps(result["control_vs_round3_bitmap_fit"]))


if __name__ == "__main__":
    main()
