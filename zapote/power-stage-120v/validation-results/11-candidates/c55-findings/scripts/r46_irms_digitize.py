#!/usr/bin/env python3
"""Which trace of the KEMET R46 'Lead Spacing 22.5 mm' ripple graph is 1 uF, and what it reads at 35-90 kHz.

    python3 -I validation-results/11-candidates/c55-findings/scripts/r46_irms_digitize.py

The c54 ledger desk read the graph (KEMET F3095_R46_X2_310_110C, 2026-05-13, p.8) as "two upper traces about 1.5-1.6 A
and 1.9-2.0 A; the leader lines do not attribute the 1 uF trace unambiguously, so the lower is taken". The leader lines
are ambiguous, but the traces are not: below the knee every trace is the voltage limit I = 2 pi f C V at one test
voltage, so the five low-frequency asymptotes stand in the ratio of the five legend capacitances (0.15 / 0.33 / 0.47 /
0.68 / 1 uF). This script renders p.8 of the repo copy at 400 dpi (pdftoppm), calibrates the log axes on the panel's
major gridlines, digitises the five traces by colour (black, grey, blue dashed; the yellow dashed and the yellow dotted
share a colour and are split by height), fits V = I / (2 pi f C) per trace on 0.1-0.4 kHz for each candidate attribution,
and reads every trace at 35 / 50 / 70 / 90 kHz (the S31 band). Writes results/r46-irms.json and results/r46-irms.md.
"""
import itertools
import json
import math
import subprocess
import tempfile
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
UNIT = HERE.parents[3]
PDF = UNIT / "validation-results/07-conducted-emi/sources/KEM_F3095_R46_X2_310_110C.pdf"
OUT = HERE.parent / "results"
DPI = 400
PANEL = (200, 1760, 1600, 2855)        # the 22.5 mm panel on the 400 dpi page (3400 x 4400 px)
MAJOR = (102, 153, 204)                 # decade gridline colour
CAPS_UF = [0.15, 0.33, 0.47, 0.68, 1.0]  # legend
F_READ_KHZ = [35, 50, 70, 90]


def near(p, q, tol=30):
    return all(abs(a - b) <= tol for a, b in zip(p, q))


def classes(p):
    r, g, b = p
    if r < 40 and g < 40 and b < 40:
        return "black"
    if near(p, (127, 127, 127), 5):
        return "grey"
    if near(p, (51, 75, 157), 25):
        return "blue"
    if near(p, (240, 175, 0), 40):
        return "yellow"
    return None


def runs(flags):
    out, s = [], None
    for i, v in enumerate(flags):
        if v and s is None:
            s = i
        if not v and s is not None:
            out.append((s, i - 1))
            s = None
    if s is not None:
        out.append((s, len(flags) - 1))
    return out


def main():
    with tempfile.TemporaryDirectory() as td:
        subprocess.run(["pdftoppm", "-r", str(DPI), "-f", "8", "-l", "8", "-png", str(PDF), f"{td}/p"], check=True)
        page = Image.open(next(Path(td).glob("p*.png"))).convert("RGB")
    im = page.crop(PANEL)
    w, h = im.size
    px = im.load()
    # major gridlines: columns / rows where the decade colour runs most of the plot height / width
    xs = [x for x in range(w) if sum(near(px[x, y], MAJOR, 6) for y in range(h)) > 0.6 * h * 0.78]
    ys = [y for y in range(h) if sum(near(px[x, y], MAJOR, 6) for x in range(w)) > 0.6 * w * 0.74]
    xg = [(a + b) / 2 for a, b in runs([x in set(xs) for x in range(w)])]
    yg = [(a + b) / 2 for a, b in runs([y in set(ys) for y in range(h)])]
    assert len(xg) == 4 and len(yg) == 4, (xg, yg)   # 0.1 / 1 / 10 / 100 kHz; 10 / 1 / 0.1 / 0.01 A
    xdec = (xg[3] - xg[0]) / 3
    ydec = (yg[3] - yg[0]) / 3
    f_of = lambda x: 0.1 * 10 ** ((x - xg[0]) / xdec)          # kHz
    i_of = lambda y: 10 * 10 ** (-(y - yg[0]) / ydec)          # A
    x_of = lambda f: xg[0] + math.log10(f / 0.1) * xdec
    # legend box and leader lines sit at x 600-1090, y 400-750 of the panel: exclude them for black
    def legend(x, y):
        return 600 <= x <= 1090 and 400 <= y <= 750

    def trace_y(name, x):
        col = []
        for y in range(int(yg[0]) + 2, int(yg[3]) - 2):
            c = classes(px[x, y])
            if c == ("yellow" if name.startswith("yellow") else name) and not (name == "black" and legend(x, y)):
                col.append(y)
        rr = [r for r in runs([y in set(col) for y in range(h)]) if r[1] - r[0] >= 1]
        if not rr:
            return None
        if name.startswith("yellow"):
            # the dotted 1-uF-class trace and the dashed lowest trace share a colour: read a column only where both
            # show, split by height (the two are > 0.3 decade apart everywhere on the panel)
            if len(rr) < 2 or rr[-1][0] - rr[0][1] < 0.25 * ydec:
                return None
            a, b = rr[0] if name == "yellow_top" else rr[-1]
        else:
            a, b = rr[0]
        return (a + b) / 2

    def read(name, f, win=14):
        x0 = int(round(x_of(f)))
        vals = [trace_y(name, x) for x in range(x0 - win, x0 + win + 1)]
        vals = [(x, v) for x, v in zip(range(x0 - win, x0 + win + 1), vals) if v is not None]
        if not vals:
            return None
        # median over the sampled columns of the window (dashed / dotted traces have gaps)
        vals.sort(key=lambda t: t[1])
        x, y = vals[len(vals) // 2]
        return {"f_kHz_at": round(f_of(x), 2), "A": round(i_of(y), 3), "columns": len(vals)}

    names = ["yellow_low", "blue", "grey", "black", "yellow_top"]   # bottom to top at low frequency
    lowf = {}
    for n in names:
        pts = []
        for f in [0.10, 0.12, 0.15, 0.2, 0.25, 0.3, 0.4]:
            r = read(n, f, win=10)
            if r:
                pts.append((r["f_kHz_at"], r["A"]))
        # I = 2 pi f C V on a log-log line of slope 1: the trace's I/f is its 2 pi C V
        k = sum(a / ff for ff, a in pts) / len(pts)        # A per kHz
        lowf[n] = {"points": pts, "A_per_kHz": k}
    # every assignment of the five legend capacitances to the five traces: spread of the implied test voltage
    best = []
    for perm in itertools.permutations(CAPS_UF):
        v = [lowf[n]["A_per_kHz"] / (2 * math.pi * 1e3 * c * 1e-6) for n, c in zip(names, perm)]
        spread = (max(v) - min(v)) / (sum(v) / len(v))
        best.append((spread, perm, v))
    best.sort()
    spread, perm, volts = best[0]
    attrib = dict(zip(names, perm))
    hf = {n: [read(n, f) for f in F_READ_KHZ] for n in names}
    res = {
        "pdf": str(PDF.relative_to(UNIT)),
        "page": 8, "panel": "Lead Spacing 22.5 mm", "dpi": DPI,
        "axes_px": {"x_decades": xg, "y_decades": yg},
        "low_f_fit": lowf,
        "attribution": {n: attrib[n] for n in names},
        "implied_test_voltage_V": [round(x, 1) for x in volts],
        "voltage_spread": round(spread, 4),
        "runner_up_spread": round(best[1][0], 4), "runner_up": dict(zip(names, best[1][1])),
        "hf_reads": hf,
    }
    one = [n for n in names if attrib[n] == 1.0][0]
    res["one_uF_trace"] = one
    res["one_uF_A_min_35_90kHz"] = min(r["A"] for r in hf[one] if r)
    OUT.mkdir(exist_ok=True)
    (OUT / "r46-irms.json").write_text(json.dumps(res, indent=1) + "\n")
    lines = ["# r46-irms.md (generated by scripts/r46_irms_digitize.py; do not edit)", "",
             f"KEMET R46 p.8, Lead Spacing 22.5 mm, digitised at {DPI} dpi from `{res['pdf']}`.", "",
             "| Trace | Attributed C | I/f below the knee (A/kHz) | implied V | " + " | ".join(f"{f} kHz" for f in F_READ_KHZ) + " |",
             "|---|---|---|---|" + "---|" * len(F_READ_KHZ)]
    for n, v in zip(names, volts):
        lines.append(f"| {n} | {attrib[n]} uF | {lowf[n]['A_per_kHz']:.4f} | {v:.0f} V | "
                     + " | ".join(f"{r['A']:.2f} A" if r else "-" for r in hf[n]) + " |")
    lines += ["", f"Best attribution: implied-voltage spread {spread:.1%}; next best {best[1][0]:.1%} "
              f"({dict(zip(names, best[1][1]))}).",
              f"1 uF is the `{one}` trace: minimum {res['one_uF_A_min_35_90kHz']:.2f} A over 35-90 kHz (Th <= 70 C)."]
    (OUT / "r46-irms.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
