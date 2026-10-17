#!/usr/bin/env python3
"""Extract the plotted line segments from pinned Infineon diagrams 11 and 15.

Requires pdfplumber. These are typical graph readings, not guaranteed limits.
Run from any directory; output stays beside this script.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
from itertools import pairwise
from pathlib import Path

import pdfplumber

HERE = Path(__file__).resolve().parent
PDF = HERE.parent / "03-loss-thermal-budget/round3/sources/ipw65r018cfd7.pdf"
X0, XSPAN = 80.8706, 216.0585
Y0, YSPAN = 715.4126, 240.7997


def check_voltage_axis(page, maximum):
    """Check numeric tick centers, independently of grid stroke edges."""
    ticks = []
    for word in page.extract_words():
        if not (720 < word["top"] < 721 and 70 < word["x0"] < 310):
            continue
        value = float(word["text"])
        center = (word["x0"] + word["x1"]) / 2
        expected = X0 + value / maximum * XSPAN
        assert abs(center - expected) < 0.001, (value, center, expected)
        ticks.append(value)
    assert ticks[0] == 0 and ticks[-1] == maximum
    assert len(ticks) == (6 if maximum == 500 else 10)


def segments(page):
    return [
        line["pts"]
        for line in page.lines
        if 80 <= line["x0"] < 297.5
        and 474 <= line["top"] < 716
        and line["width"] > 0.001
        and line["height"] > 0.001
        and line["linewidth"] == 1.2
    ]


def crossings(lines, position, axis):
    values = []
    for a, b in lines:
        if min(a[axis], b[axis]) <= position <= max(a[axis], b[axis]):
            other = 1 - axis
            value = a[other] + (position - a[axis]) / (b[axis] - a[axis]) * (b[other] - a[other])
            if not any(abs(value - existing) < 0.002 for existing in values):
                values.append(value)
    return sorted(values)


def write_csv(name, rows):
    with (HERE / name).open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    with pdfplumber.open(PDF) as document:
        check_voltage_axis(document.pages[8], 1.8)
        check_voltage_axis(document.pages[9], 500)
        diode, eoss = segments(document.pages[8]), segments(document.pages[9])
    # The plotted Eoss line begins at zero energy and approximately zero voltage.
    origin = min((point for segment in eoss for point in segment), key=lambda point: point[0])
    assert abs(origin[0] - X0) < 0.03 and abs(origin[1] - Y0) < 0.03
    assert len(diode) == 219 and len(eoss) == 582, "Pinned figure changed"
    currents = [
        0.1,
        0.2,
        0.5,
        1,
        2,
        3,
        5,
        8,
        10,
        12,
        16,
        20,
        24,
        30,
        37,
        40,
        42,
        50,
        58.2,
        60,
        80,
        100,
        125,
        150,
    ]
    diode_rows = []
    for current in currents:
        y = Y0 - (math.log10(current) + 1) / 4 * YSPAN
        xs = crossings(diode, y, 1)
        assert len(xs) == 2, (current, xs)
        # Visual labels in Diagram11: lower-Vf (left) curve125C, right25C.
        hot, cold = [(x - X0) / XSPAN * 1.8 for x in xs]
        assert 0 < hot < cold < 1.8
        diode_rows.append(
            {"current_a": current, "vf_25c_v": round(cold, 4), "vf_125c_v": round(hot, 4)}
        )
    volts = [k / 2 for k in range(2, 401)] + [250, 280, 300, 350, 400, 450, 490]
    eoss_rows = []
    for voltage in volts:
        x = X0 + voltage / 500 * XSPAN
        ys = crossings(eoss, x, 0)
        assert len(ys) == 1, (voltage, ys)
        energy_uj = (Y0 - ys[0]) / YSPAN * 40
        eoss_rows.append({"vds_v": voltage, "eoss_typ_uj": round(energy_uj, 4)})
    for key in ["vf_25c_v", "vf_125c_v"]:
        assert all(b[key] > a[key] for a, b in pairwise(diode_rows))
    assert all(b["eoss_typ_uj"] > a["eoss_typ_uj"] for a, b in pairwise(eoss_rows))
    vf_check = next(row["vf_25c_v"] for row in diode_rows if row["current_a"] == 58.2)
    eoss_check = next(row["eoss_typ_uj"] for row in eoss_rows if row["vds_v"] == 400)
    # Independent tabulated data: VSDtyp1.0V@58.2A and Co(er)=396pF@400V.
    assert abs(vf_check - 1.0) < 0.03
    assert abs(eoss_check / (0.5 * 396e-12 * 400**2 * 1e6) - 1) < 0.01
    write_csv("diode-vf-graph.csv", diode_rows)
    write_csv("eoss-graph.csv", eoss_rows)
    metadata = {
        "source": str(PDF.relative_to(HERE.parent)),
        "source_sha256": hashlib.sha256(PDF.read_bytes()).hexdigest(),
        "source_revision": "IPW65R018CFD7 Rev2.0,2021-04-19",
        "extractor_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "pdfplumber_version": pdfplumber.__version__,
        "evidence": "typical plotted graph; approximate reading, not guaranteed device limit",
        "method": "pdfplumber vector line intersections; voltage axes calibrated and checked against every numeric tick center; Eoss curve origin independently checked; vertical axes calibrated from grid rectangle and visually checked on rendered pages",
        "axes_pdf_points": {"x0": X0, "xspan": XSPAN, "y_bottom": Y0, "yspan": YSPAN},
        "diode": {
            "printed_page": 9,
            "diagram": 11,
            "x_domain_v": [0, 1.8],
            "y_log10_current_a": [-1, 3],
            "curve_identity": "left125C,right25C",
            "suggested_reading_uncertainty_v": 0.01,
            "interpolation": "linearVf versus log10(I); no extrapolation outside supplied0.1–150A",
        },
        "eoss": {
            "printed_page": 10,
            "diagram": 15,
            "x_domain_v": [0, 500],
            "y_domain_uj": [0, 40],
            "suggested_reading_uncertainty_uj": 0.2,
            "interpolation": "piecewise linear; dense knots preserve nonlinear knee; no extrapolation outside1–490V",
        },
        "table_crosschecks": {
            "vf_25c_at58p2a_v": vf_check,
            "vf_table_v": 1.0,
            "eoss_at400v_uj": eoss_check,
            "coer_table_energy_at400v_uj": 31.68,
        },
        "uncertainty_note": "Suggested graph-reading scales reflect1.2pt stroke width; they are not statistical or manufacturer tolerances. Extra decimals preserve extraction reproducibility only.",
        "zero_voltage_note": "Eoss(0)=0 follows stored-energy definition, but adding that point is a separately stated physical assumption; C1 classification below10V remains unavailable.",
    }
    (HERE / "loss-curve-provenance.json").write_text(json.dumps(metadata, indent=2) + "\n")
    print(f"Extracted {len(diode_rows)} diode and {len(eoss_rows)} Eoss points")


if __name__ == "__main__":
    main()
