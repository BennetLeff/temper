#!/usr/bin/env python3
"""Digitise TDK B3267*D/G/J/T (6/26) p.25 'Permissible current IRMS versus frequency f at 70 C', B32676G/T* (37.5 mm),
numpy only.  python3 -I scripts/digitize_b32676_irms.py <MKP_B32674_678.pdf> OUT.json
Frame from the grid (x decades 1e2..1e5 Hz, y 0..34 A). At 10 kHz every curve is seeded from the p.10 table IRMS
(70 C, 10 kHz) of the part, snapped to the nearest dark run, then tracked column by column to 95 kHz.
Control: the snapped 10 kHz value must be within 0.6 A of the table value (else exit 1).
Result: I(f)/I(10 kHz) per part; since the curve is TDK's dT <= 20 K rule, ESR(f)/ESR(10 kHz) = (I10k/I(f))^2."""
import json, subprocess, sys, tempfile, math, hashlib
from pathlib import Path
import numpy as np
pdf = Path(sys.argv[1]); tmp = Path(tempfile.mkdtemp())
subprocess.run(["pdftoppm", "-gray", "-r", "300", "-f", "25", "-l", "25", str(pdf), str(tmp / "p")], check=True)
raw = next(tmp.glob("p*.pgm")).read_bytes(); h = raw.split(maxsplit=4); W, H = int(h[1]), int(h[2])
im = np.frombuffer(h[4][:W * H], np.uint8).reshape(H, W).astype(int)
dark = im < 150
# chart window: the long horizontal / vertical grid lines in the upper half of the page
rows = [y for y in range(H // 3, H // 2 + 300) if dark[y].sum() > 900]
cols_all = [x for x in range(W) if dark[H // 3: H // 2 + 300, x].sum() > 450]
def groups(v):
    g = []
    for a in v:
        if g and a - g[-1][-1] <= 2: g[-1].append(a)
        else: g.append([a])
    return [sum(x) / len(x) for x in g]
R, C = groups(rows), groups(cols_all)
ytop, ybot = R[0], R[-1]; xl, xr = C[0], C[-1]
A_per_px = 34.0 / (ybot - ytop)
def y2a(y): return (ybot - y) * A_per_px
def a2y(a): return ybot - a / A_per_px
def f2x(f): return xl + (math.log10(f) - 2) / 3 * (xr - xl)
TABLE = {"9uF/750V B32676G1905": 19.5, "10uF/750V B32676G1106": 20.5, "12uF/750V B32676G1126": 23.0,
         "7.5uF/875V B32676G8755": 19.0, "10uF/875V B32676G8106K000": 22.5}
FREQS = [10e3, 15e3, 20e3, 30e3, 40e3, 50e3, 60e3, 70e3, 80e3, 90e3, 95e3]
gridx = set(int(round(c)) for c in C)
def runs(x):
    col = dark[int(ytop) + 3: int(ybot) - 2, x]; ys = np.nonzero(col)[0] + int(ytop) + 3
    return groups(list(ys))
def col_ok(x): return all(abs(x - g) > 3 for g in gridx)
out = {"pdf_sha256_16": hashlib.sha256(pdf.read_bytes()).hexdigest()[:16], "page": 25,
       "frame_px": [xl, xr, ytop, ybot], "parts": {}}
ok = True
for name, i10 in TABLE.items():
    x = int(round(f2x(10e3))) + 6
    while not col_ok(x): x += 1
    rr = runs(x); y = min(rr, key=lambda r: abs(r - a2y(i10)))
    snap = y2a(y); ctl = abs(snap - i10) <= 0.6; ok &= ctl
    track = {}; xs = int(round(f2x(95e3)))
    for xx in range(x, xs + 1):
        if not col_ok(xx): continue
        rr = runs(xx)
        if rr:
            near = min(rr, key=lambda r: abs(r - y))
            if abs(near - y) <= 4: y = near
        for f in FREQS:
            if abs(xx - f2x(f)) < 1.0 or (f == 10e3 and xx == x): track.setdefault(f, y2a(y))
    for f in FREQS:            # frequencies that fell on a grid column: take the nearest tracked column
        if f not in track: track[f] = None
    vals = {f"{int(f/1e3)}k": (round(v, 2) if v is not None else None) for f, v in track.items()}
    ref = track[10e3]
    out["parts"][name] = {"table_10k_A": i10, "snapped_10k_A": round(snap, 2), "control_ok": bool(ctl), "I_A": vals,
                          "ratio_to_10k": {k: (round(v / ref, 4) if v is not None else None) for k, v in zip(vals, track.values())}}
json.dump(out, open(sys.argv[2], "w"), indent=1)
print(json.dumps(out, indent=1)); sys.exit(0 if ok else 1)
