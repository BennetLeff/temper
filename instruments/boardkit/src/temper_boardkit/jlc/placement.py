"""JLC placement-preview simulation (from RB1 dfm_checks.py section 2; pure Python).

JLC places each part from its CPL row: the EasyEDA footprint of the LCSC part, origin at its head point,
turned by Rotation (degrees CCW, y up, the Gerber frame) and moved to Mid X / Mid Y.  simulate() does the
same with the cached records (easyeda.pads_about_head) and measures each vendor pad against the board pad of
the same number, read from the Gerber X2 attributes (gerber.Copper.pads).  A wrong CPL rotation moves pads
by a pitch or more; land-pattern differences are tenths of a millimetre.

pin_map {LCSC: {vendor pin: KiCad pad}} renumbers parts whose vendor numbering differs.
"""

from __future__ import annotations

import csv
import math

PLACE_TOL = 0.15  # mm: under a third of a 0.5 mm pitch


def read_cpl(path):
    """JLC CPL csv -> [{ref, x, y, rot, layer}] (mm suffixes stripped)."""
    with open(path) as f:
        return [
            {
                "ref": r["Designator"],
                "x": float(r["Mid X"].removesuffix("mm")),
                "y": float(r["Mid Y"].removesuffix("mm")),
                "rot": float(r["Rotation"]),
                "layer": r.get("Layer", "Top"),
            }
            for r in csv.DictReader(f)
        ]


def simulate(cpl, lcsc_of, vendor_pads, board_pads, pin_map=None, tol=PLACE_TOL):
    """cpl: read_cpl rows; lcsc_of {ref: LCSC}; vendor_pads {LCSC: pads_about_head(...)};
    board_pads {'REF.PIN': (layer, x, y, ...)} in the Gerber frame.
    -> (result {pass, tolerance_mm, worst_mm, worst_pad, max_error_by_ref}, outlines [(points, is_pin1)])"""
    pin_map = pin_map or {}
    place_err, worst, outlines = {}, (0.0, ""), []
    for row in cpl:
        ref, lcsc = row["ref"], lcsc_of[row["ref"]]
        mx, my = row["x"], row["y"]
        th = math.radians(row["rot"])
        c, s = math.cos(th), math.sin(th)
        errs = []
        for epin, ((u, v), poly) in vendor_pads[lcsc].items():
            pin = pin_map.get(lcsc, {}).get(epin, epin)
            px, py = mx + u * c - v * s, my + u * s + v * c
            g = board_pads.get(f"{ref}.{pin}")
            e = math.hypot(px - g[1], py - g[2]) if g else float("inf")
            errs.append(e)
            if e > worst[0]:
                worst = (e, f"{ref}.{pin}")
            if poly:
                outlines.append(
                    ([(mx + a * c - b * s, my + a * s + b * c) for a, b in poly], pin == "1")
                )
        place_err[ref] = round(max(errs), 4)
    return (
        {
            "pass": all(e <= tol for e in place_err.values()),
            "tolerance_mm": tol,
            "worst_mm": round(worst[0], 4),
            "worst_pad": worst[1],
            "max_error_by_ref": place_err,
        },
        outlines,
    )


def overlay_svg(bounds, board_pad_polys, outlines, scale=20.0):
    """Our pads (grey) under the vendor pads placed from the CPL (blue outline; pin 1 red)."""
    minx, miny, maxx, maxy = bounds

    def path(pts):
        return (
            "M"
            + "L".join(f"{(x - minx) * scale:.2f},{(maxy - y) * scale:.2f}" for x, y in pts)
            + "Z"
        )

    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{(maxx - minx) * scale:.0f}" '
        f'height="{(maxy - miny) * scale:.0f}">',
        '<rect width="100%" height="100%" fill="#14301f"/>',
    ]
    svg += [f'<path d="{path(p)}" fill="#c8c8c8"/>' for p in board_pad_polys]
    svg += [
        f'<path d="{path(p)}" fill="none" stroke="{"#ff3030" if one else "#3a8bff"}" stroke-width="1.5"/>'
        for p, one in outlines
    ]
    svg.append("</svg>")
    return "\n".join(svg) + "\n"
