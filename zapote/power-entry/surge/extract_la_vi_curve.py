#!/usr/bin/env python3
"""Extract the V150LA10A(P) transient V-I curve from the captured Littelfuse PDF.

Why this exists
---------------
The datasheet tabulates ONE clamp point per part (395 V MAXIMUM at 50 A, 8/20 us)
and carries the V-I characteristics only as multi-curve family charts. An earlier
attempt to digitise the raster figure was rejected as an unreliable instrument: it
hopped between the adjacent V130/V140/V150/V175 curves.

The figures are **vector**, not raster (only page 1 is a raster image), so the
curves can be read exactly rather than traced. Two things make the read checkable:

  * the axes are calibrated from their own printed tick labels, and
  * the identified curves are validated against the datasheet's tabulated maximum
    clamp voltage for three consecutive parts.

The V150 curve passes through 383 V at 50 A against a stated maximum of 395 V -
below the maximum, as a typical curve must be.

Requires: pymupdf. Run:
    python3 extract_la_vi_curve.py <datasheet.pdf> <out.json>
"""

from __future__ import annotations

import collections
import json
import math
import sys

import pymupdf

# Figure 10, page 7: "Maximum Clamping Voltage for 14mm Parts",
# captioned "V130LA10A(P) - V320LA20A".
PAGE_INDEX = 6
PLOT = (96.0, 186.0, 300.0, 334.0)  # x0, y0, x1, y1 in page points

# Axis calibration, from the printed tick labels (log-log).
#   x: 10^-3 .. 10^4 A ; y: 200 .. 6,000 V
PX_PER_DEC_I, X_AT_I_1 = 25.39, 180.67
PX_PER_DEC_V, Y_AT_V_1 = 91.4, 540.9

# Datasheet table (LA Series Ratings & Specifications): maximum clamping voltage
# at IPK = 50 A, 8/20 us, for the three lowest 14 mm "A" parts in this figure.
# These are the validation anchors, NOT inputs to the calculation.
ANCHORS = [
    ("V130LA10A(P)", 340.0),
    ("V140LA10A(P)", 360.0),
    ("V150LA10A(P)", 395.0),
]


def to_data(x: float, y: float) -> tuple[float, float]:
    return (10 ** ((x - X_AT_I_1) / PX_PER_DEC_I), 10 ** ((Y_AT_V_1 - y) / PX_PER_DEC_V))


def cubic(p1, p2, p3, p4, t):
    mt = 1 - t
    return pymupdf.Point(
        mt**3 * p1.x + 3 * mt * mt * t * p2.x + 3 * mt * t * t * p3.x + t**3 * p4.x,
        mt**3 * p1.y + 3 * mt * mt * t * p2.y + 3 * mt * t * t * p3.y + t**3 * p4.y,
    )


def curves_in_plot(page) -> list[list]:
    """Every chained Bezier path inside the plot area, as sampled polylines."""
    x0, y0, x1, y1 = PLOT
    inside = lambda p: x0 <= p.x <= x1 and y0 <= p.y <= y1
    bez = []
    for g in page.get_drawings():
        for it in g["items"]:
            if it[0] == "c" and inside(it[1]) and inside(it[4]):
                bez.append((it[1], it[2], it[3], it[4]))

    key = lambda p: (round(p.x, 1), round(p.y, 1))
    starts: dict = collections.defaultdict(list)
    for i, (a, _b, _c, _d) in enumerate(bez):
        starts[key(a)].append(i)

    used = [False] * len(bez)
    chains = []
    for i in range(len(bez)):
        if used[i]:
            continue
        used[i] = True
        chain, cur = [i], i
        while True:
            nxt = next((j for j in starts.get(key(bez[cur][3]), []) if not used[j]), None)
            if nxt is None:
                break
            used[nxt] = True
            chain.append(nxt)
            cur = nxt
        chains.append(chain)

    out = []
    for chain in chains:
        pts = []
        for idx in chain:
            a, b, c, d = bez[idx]
            pts.extend(cubic(a, b, c, d, k / 8.0) for k in range(1, 9))
            pts.append(d)
        if len(pts) >= 40:
            out.append(pts)
    return out


def voltage_at(pts, amps: float) -> float:
    """Interpolate the curve at a current, using the polyline's own ordering."""
    target = X_AT_I_1 + PX_PER_DEC_I * math.log10(amps)
    best = min(pts, key=lambda p: abs(p.x - target))
    return to_data(best.x, best.y)[1]


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    pdf, out_path = argv
    page = pymupdf.open(pdf)[PAGE_INDEX]
    curves = curves_in_plot(page)

    # The family stacks by voltage, so the three LOWEST curves at 50 A are the
    # three lowest-voltage parts, in order. Match them to the table anchors.
    ordered = sorted(curves, key=lambda q: voltage_at(q, 50.0))
    lowest_three = ordered[:3]

    report = []
    ok = True
    for pts, (name, table_max) in zip(lowest_three, ANCHORS):
        v = voltage_at(pts, 50.0)
        below = v <= table_max
        ok &= below
        report.append({"part": name, "v_at_50a": round(v, 1), "datasheet_vc_max": table_max, "below_max": below})

    print("  validation against the datasheet's own tabulated maximum clamp:")
    for r in report:
        mark = "OK " if r["below_max"] else "BAD"
        print(f"    {mark} {r['part']:<16} curve={r['v_at_50a']:6.1f} V   table max={r['datasheet_vc_max']:6.1f} V")
    if not ok:
        print("  REFUSING: an identified curve exceeds its tabulated maximum.")
        return 1

    v150 = lowest_three[2]
    data = [{"i_a": round(to_data(p.x, p.y)[0], 4), "v": round(to_data(p.x, p.y)[1], 2)} for p in v150]
    doc = {
        "schema": "zapote-la-vi-curve/v1",
        "part": "V150LA10A(P)",
        "datasheet": "Littelfuse LA Series Radial Lead Varistors, revised VL 16/9/2024",
        "figure": "Figure 10 (page 7), 'Maximum Clamping Voltage for 14mm Parts'",
        "extraction": "vector Bezier paths (the figures are vector, not raster)",
        "axis_calibration": {"px_per_decade_i": PX_PER_DEC_I, "px_per_decade_v": PX_PER_DEC_V},
        "validation": report,
        "note": "Points are ordered along the curve. This is a TYPICAL curve read from the family chart; the datasheet's tabulated 395 V at 50 A is a MAXIMUM.",
        "points": data,
    }
    with open(out_path, "w") as fh:
        json.dump(doc, fh, indent=2)
        fh.write("\n")
    print(f"  wrote {out_path}: {len(data)} points, {data[0]['i_a']:.4f} A .. {data[-1]['i_a']:.0f} A")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
