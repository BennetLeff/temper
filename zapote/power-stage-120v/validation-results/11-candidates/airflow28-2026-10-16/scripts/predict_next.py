#!/usr/bin/env python3
"""Next bracketing points for the ladder series by shape transfer from the solved c28 series (fewer solves than the
plain 1/h secant on a shared, loaded machine).

    python3 -I predict_next.py [--mode uniform] [--series c26@61,...]   -> prints CASE@BAY list (comma separated)

Shape: f(h) = the h-dependent worst gated margin of the reference series (c28@61, uniform), linear in 1/h between its
solved points. A series with solved points (h_i, m_i) is fitted as m(h) = A + B f(h) (least squares; exact with two
points), its zero h* solved, and the candidates ceil(h*), ceil(h*) - 1 returned inside the series' current bracket
(skipping solved h). Series already bracketed to hi - lo <= 1 (or passing at h 10) return nothing.
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import airflow_search as af  # noqa: E402


def margin(e):
    return e["hdep"] if e["worst"] >= 0 else min(e["worst"], e["hdep"])


def shape(ref):
    hs = sorted(ref)

    def f(h):
        x = 1 / h
        xs = [1 / v for v in hs]
        if x >= xs[0]:
            a, b = 0, 1
        elif x <= xs[-1]:
            a, b = len(hs) - 2, len(hs) - 1
        else:
            a = max(i for i in range(len(hs)) if xs[i] >= x)
            b = a + 1
        return ref[hs[a]] + (ref[hs[b]] - ref[hs[a]]) * (x - xs[a]) / (xs[b] - xs[a])
    return f


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="uniform")
    ap.add_argument("--series", default="c26@61,c26@55,c24@61,c24@55,c22@61,c22@55,c20@61,c20@55,c18@61,c18@55")
    ap.add_argument("--ref", default="c28@61")
    a = ap.parse_args()
    rc, rb = af.parse_series(a.ref)[0]
    ref = {h: margin(e) for h, e in af.series_state(rc, rb, "uniform").items()}
    f = shape(ref)
    out = []
    for ceil, bay in af.parse_series(a.series):
        st = af.series_state(ceil, bay, a.mode)
        pts = {h: margin(e) for h, e in st.items()}
        if not pts:
            continue
        ok = [h for h in pts if pts[h] >= 0]
        fail = [h for h in pts if pts[h] < 0]
        if ok and min(ok) <= 10:
            print(f"# c{ceil:g}@{bay:g}: passes at h 10", file=sys.stderr)
            continue
        lo = max(fail) if fail else 10
        hi = min(ok) if ok else 400
        if ok and fail and hi - lo <= 1:
            print(f"# c{ceil:g}@{bay:g}: bracketed {lo}/{hi}", file=sys.stderr)
            continue
        hs = sorted(pts)
        if len(hs) == 1:
            B = 1.0
            A = pts[hs[0]] - f(hs[0])
        else:
            fs = [f(h) for h in hs]
            ms = [pts[h] for h in hs]
            n = len(hs)
            fm, mm = sum(fs) / n, sum(ms) / n
            B = sum((x - fm) * (y - mm) for x, y in zip(fs, ms)) / sum((x - fm) ** 2 for x in fs)
            A = mm - B * fm
        lo_s, hi_s = 10.0, 400.0                       # zero of A + B f(h) by bisection in h
        g = lambda h: A + B * f(h)
        if g(hi_s) < 0:
            hstar = hi_s
        else:
            for _ in range(60):
                mid = 0.5 * (lo_s + hi_s)
                lo_s, hi_s = (mid, hi_s) if g(mid) < 0 else (lo_s, mid)
            hstar = hi_s
        c = math.ceil(hstar)
        cand = [h for h in sorted({c - 1, c}) if lo < h < hi and h not in pts]
        print(f"# c{ceil:g}@{bay:g}: pts {sorted(pts.items())} -> h* {hstar:.1f}, bracket ({lo}, {hi}) -> {cand}",
              file=sys.stderr)
        out += [f"{af.case_name(ceil, h, a.mode)}@{bay:g}" for h in cand]
    print(",".join(out))


if __name__ == "__main__":
    main()
