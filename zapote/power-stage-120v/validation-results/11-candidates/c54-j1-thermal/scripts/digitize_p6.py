#!/usr/bin/env python3
"""Digitize the Phoenix Contact 1714971 (MKDS 5/ 2-9,5) derating diagram, PDF p.6, into results/phoenix_1714971_p6.json.

    python3 -I scripts/digitize_p6.py [PDF]

PDF: the Phoenix online-catalog PDF 'generated Oct 16, 2026' (sha256 36517cfd4b96d200..., the copy temp-ratings
2026-10-15 cites), default worktrees/runs-native21/s47/temp-ratings-dl/conn/phx1714971_b/phoenix-contact-1714971-en.pdf
(not in git; the JSON this writes is). The page is rendered at 200 dpi with pdftoppm into a temporary directory and read
as pixels: the grid lines give the axes (x 0..110 C in 10 C steps, y 0..64 A in 8 A steps), then each column's dark pixels
off the grid are the curve. The diagram has two traces: the solid line ('1 = 6 mm2', flat at 32 A to the knee, then
falling to 0 A near 105 C) and a dashed continuation above 32 A (the same curve without the 32 A nominal-current cap).
For each sampled ambient the curve's centre is the mean of its contiguous dark run (line width ~5 px = 0.7 A).
"""
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "results" / "phoenix_1714971_p6.json"
DEFAULT_PDF = Path("/Users/bennet/Desktop/temper/worktrees/runs-native21/s47/temp-ratings-dl/conn/phx1714971_b/"
                   "phoenix-contact-1714971-en.pdf")
SHA_PREFIX = "36517cfd4b96d200"
DPI = 200


def grid(d, axis, lo, hi, span, min_dark):
    """Indices (rows if axis == 0, else columns) whose dark-pixel count over span exceeds min_dark, merged into centres."""
    idx = [i for i in range(lo, hi) if (d[i, span[0]:span[1]] if axis == 0 else d[span[0]:span[1], i]).sum() > min_dark]
    out, run = [], []
    for i in idx:
        if run and i != run[-1] + 1:
            out.append(sum(run) / len(run)); run = []
        run.append(i)
    if run:
        out.append(sum(run) / len(run))
    return out, set(idx)


def runs_in(col_dark, rows, exclude):
    """Contiguous dark runs (start, end) of one column within rows, skipping grid rows."""
    out, cur = [], None
    for y in rows:
        if col_dark[y] and y not in exclude:
            if cur and y == cur[1] + 1:
                cur[1] = y
            else:
                if cur:
                    out.append(tuple(cur))
                cur = [y, y]
    if cur:
        out.append(tuple(cur))
    return out


def main():
    pdf = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PDF
    sha = hashlib.sha256(pdf.read_bytes()).hexdigest()
    if not sha.startswith(SHA_PREFIX):
        raise SystemExit(f"digitize_p6: {pdf} sha256 {sha[:16]} is not the cited copy {SHA_PREFIX}")
    with tempfile.TemporaryDirectory() as td:
        subprocess.run(["pdftoppm", "-r", str(DPI), "-f", "6", "-l", "6", "-png", str(pdf), f"{td}/p"], check=True)
        png = next(Path(td).glob("p-*6.png"))
        a = np.asarray(Image.open(png).convert("L"))
    d = a < 140
    # plot box: the diagram sits in the lower half of the page (rows ~1300-1900 at 200 dpi, columns ~380-1400)
    rows, grid_r = grid(d, 0, 1300, 1900, (400, 1380), 600)
    cols, grid_c = grid(d, 1, 380, 1400, (1350, 1820), 350)
    if len(cols) != 12:
        raise SystemExit(f"digitize_p6: expected 12 vertical grid lines (0..110 C), found {len(cols)}: {cols}")
    x0, x110 = cols[0], cols[-1]
    px_per_c = (x110 - x0) / 110.0
    y64, y0 = rows[0], rows[-1]
    px_per_a = (y0 - y64) / 64.0
    # the 32 A grid line carries the solid trace's flat part; exclude every grid row except when reading below it
    excl = set(grid_r)
    pts_solid, pts_dashed = [], []
    for t10 in range(200, 1080, 10):
        t = t10 / 10.0
        x = int(round(x0 + t * px_per_c))
        if x in grid_c:
            x += 2
        runs = runs_in(d[:, x], range(int(y64) - 2, int(y0) + 1), excl)
        for (ya, yb) in runs:
            # a near-horizontal trace crosses a column in ~5 px; the steep tail (> 99 C) in up to ~40 px; anything longer
            # is a label digit or the bottom axis
            if yb - ya > (40 if t >= 99.0 else 12) or yb >= y0 - 1:
                continue
            i_a = (y0 - (ya + yb) / 2.0) / px_per_a
            if t < 81.5 and i_a > 32.6:
                pts_dashed.append((t, round(i_a, 2)))
            elif t >= 81.5 and i_a < 31.5:
                pts_solid.append((t, round(i_a, 2)))
    # keep one point per ambient (the label '1' and its leader cross the solid trace near 88-95 C: drop columns with
    # more than one candidate below 32 A, and points that break monotonic decrease)
    def mono(pts, decreasing=True):
        by_t = {}
        for t, i in pts:
            by_t.setdefault(t, []).append(i)
        out, last = [], None
        for t in sorted(by_t):
            if len(by_t[t]) != 1:
                continue
            i = by_t[t][0]
            if last is None or (i <= last + 0.3 if decreasing else True):
                out.append((t, i)); last = i
        return out
    solid = mono(pts_solid)
    dashed = mono(pts_dashed)
    zero_c = None
    for t, i in solid:
        if i < 1.0:
            zero_c = t; break
    out = {
        "source": "Phoenix Contact online-catalog PDF 1714971 MKDS 5/ 2-9,5 (generated Oct 16, 2026), p.6 'Diagram', "
                  "trace '1 = 6 mm2', type MKDS 5/...-9,5",
        "pdf_sha256": sha,
        "dpi": DPI,
        "axes_px": {"x0_c": x0, "x110_c": x110, "y0_a": y0, "y64_a": y64, "px_per_c": px_per_c, "px_per_a": px_per_a},
        "reading_uncertainty": "+/-0.4 A (line half-width), +/-0.3 C (one column); ambient grid 10 C",
        "solid_falling_branch": solid,
        "dashed_branch_above_32A": dashed,
        "flat_A": 32.0,
        "first_ambient_below_1A_c": zero_c,
    }
    OUT.write_text(json.dumps(out, indent=1) + "\n")
    print(f"wrote {OUT.name}: {len(solid)} solid / {len(dashed)} dashed points; curve below 1 A at {zero_c} C")


if __name__ == "__main__":
    main()
