#!/usr/bin/env python3
"""Bench heatsink r1: dimensioned drawing (DXF R12 + SVG) and the drill / cut tables, all from bench_params.py.

    python3 -I scripts/bench_cad.py              (from bench-sink-r1/)
      -> results/bench-sink-r1.dxf, results/bench-sink-r1.svg, results/drill-table.md

Views (mm, board frame of bench_params.py): A front (x-z, looking at the sink face from the board), B section at Q3
(y-z), C plan (x-y), D sink front-face drilling, E clamp-bar drilling, F strip / shim / pad cut sizes.
Stdlib only: the DXF is written by hand (LINE, CIRCLE, TEXT; layers OUTLINE, HIDDEN, INSUL, DIM, NOTE).
Positions marked 'match' are drilled on assembly from the part itself (bracket bolts through the outer fins). The BR1 hole
is drilled at machining from a loose part's measured seat height (GBJ S = hole centre above the body bottom).
Owner decisions 2026-10-18: JLC solders the TO-247s (per-device shims under the strip, bench_tolerance.py); BR1 is fitted
later by the owner (bar access slot, window extension for the bottom preheater).
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
STUDY = HERE.parent
sys.path.insert(0, str(HERE))
import bench_params as P  # noqa: E402
import bench_mech as M  # noqa: E402

ENT = []          # (kind, layer, data)
COLORS = {"OUTLINE": "#222", "HIDDEN": "#888", "INSUL": "#c06000", "DIM": "#0060c0", "NOTE": "#444", "PE": "#108040"}


def line(x1, y1, x2, y2, layer="OUTLINE"):
    ENT.append(("LINE", layer, (x1, y1, x2, y2)))


def rect(x1, y1, x2, y2, layer="OUTLINE"):
    line(x1, y1, x2, y1, layer); line(x2, y1, x2, y2, layer); line(x2, y2, x1, y2, layer); line(x1, y2, x1, y1, layer)


def circle(x, y, r, layer="OUTLINE"):
    ENT.append(("CIRCLE", layer, (x, y, r)))


def text(x, y, s, h=2.0, layer="NOTE"):
    ENT.append(("TEXT", layer, (x, y, h, s)))


def dim_h(x1, x2, y, label=None, layer="DIM"):
    line(x1, y, x2, y, layer); line(x1, y - 1, x1, y + 1, layer); line(x2, y - 1, x2, y + 1, layer)
    text((x1 + x2) / 2 - 3, y + 0.8, label or f"{abs(x2 - x1):.2f}", 1.6, layer)


def dim_v(x, y1, y2, label=None, layer="DIM"):
    line(x, y1, x, y2, layer); line(x - 1, y1, x + 1, y1, layer); line(x - 1, y2, x + 1, y2, layer)
    text(x + 0.8, (y1 + y2) / 2, label or f"{abs(y2 - y1):.2f}", 1.6, layer)


# ------------------------------------------------------------------------------------------------ derived geometry
T = P.TO247
NOM = {k: sum(v) / 2 for k, v in T.items()}
t_pad = P.PADS[P.PAD_CHOICE]["t"]
Y_FACE = P.Y_TAB - t_pad
Y_BAR = Y_FACE + P.SPACER_L
SINK_X = (P.SINK_X0, P.SINK_X0 + P.SINK_WIDTH)
SINK_Z = (P.Z_SINK_BOTTOM, P.Z_SINK_BOTTOM + P.SINK_LEN)
STRIP_Z = (P.Z_SINK_BOTTOM - P.STRIP_OVERHANG, P.STRIP_TOP_Z)
BODY_Z = (NOM["L1"], NOM["L1"] + NOM["D"])
METAL_TOP = NOM["L1"] + NOM["D"] - NOM["D2"]
METAL_BOT = METAL_TOP - NOM["D1"]
BR1_Z = (P.BR1_SEAT_Z_EST + P.BR1_LIFT, P.BR1_SEAT_Z_EST + P.BR1_LIFT + sum(P.GBJ["B"]) / 2)   # EST: measure the seat
SHIM_X = (P.BR1_X - P.SHIM_SIZE[0] / 2, P.BR1_X + P.SHIM_SIZE[0] / 2)
SHIM_Z = (P.Z_SINK_BOTTOM + 0.5, P.Z_SINK_BOTTOM + 0.5 + P.SHIM_SIZE[1])
BR1_HOLE_EST = (P.BR1_X, P.BR1_HOLE_Z)
SHIM_FET = {r: (x - P.SHIM_FET_SIZE[0] / 2, x + P.SHIM_FET_SIZE[0] / 2) for r, x in P.FET_X.items()}
SHIM_FET_Z = (P.SHIM_FET_Z0, P.SHIM_FET_Z0 + P.SHIM_FET_SIZE[1])


def view_front(ox, oy):
    o = lambda x, z: (ox + x, oy + z)
    text(*o(-12, 88), "A  FRONT: sink face seen from the board (x right, z up from board top)", 2.5)
    line(*o(0, 0), *o(125, 0)); text(*o(126, 0), "board top", 1.6)
    line(*o(0, 0), *o(0, -1.6)); line(*o(0, -1.6), *o(125, -1.6))
    rect(*o(SINK_X[0], SINK_Z[0]), *o(SINK_X[1], SINK_Z[1]), "PE")
    text(*o(SINK_X[0] + 2, SINK_Z[1] - 4), f"{P.SINK_PN} (PE), face y {Y_FACE:.3f} nominal; floats {M.sink_face_range()[0]:.2f}..{M.sink_face_range()[2]:.2f} onto the soldered row", 1.8, "PE")
    rect(*o(P.STRIP_X[0], STRIP_Z[0]), *o(P.STRIP_X[1], STRIP_Z[1]), "INSUL")
    text(*o(P.STRIP_X[0] + 1, STRIP_Z[1] + 1), f"{P.PAD_CHOICE} strip {P.STRIP_X[1] - P.STRIP_X[0]:.1f} x {STRIP_Z[1] - STRIP_Z[0]:.1f}", 1.6, "INSUL")
    for ref, xc in P.FET_X.items():
        rect(*o(xc - NOM["E"] / 2, BODY_Z[0]), *o(xc + NOM["E"] / 2, BODY_Z[1]))
        rect(*o(xc - NOM["E1"] / 2, METAL_BOT), *o(xc + NOM["E1"] / 2, METAL_TOP), "HIDDEN")
        for dx in (-5.45, 0, 5.45):
            line(*o(xc + dx, BODY_Z[0]), *o(xc + dx, -1.6))
        circle(*o(xc, P.SPRING_Z), P.SPRING["OD"] / 2, "HIDDEN")
        rect(*o(xc - P.FR4_PAD[0] / 2, P.SPRING_Z - P.FR4_PAD[1] / 2), *o(xc + P.FR4_PAD[0] / 2, P.SPRING_Z + P.FR4_PAD[1] / 2), "INSUL")
        text(*o(xc - 3, BODY_Z[1] + 1), f"{ref} {P.TAB_NET[ref]}", 1.6)
        rect(*o(SHIM_FET[ref][0], SHIM_FET_Z[0]), *o(SHIM_FET[ref][1], SHIM_FET_Z[1]), "PE")
    rect(*o(P.BR1_X_SPAN[0], BR1_Z[0]), *o(P.BR1_X_SPAN[1], BR1_Z[1]))
    rect(*o(SHIM_X[0], SHIM_Z[0]), *o(SHIM_X[1], SHIM_Z[1]), "PE")
    circle(*o(*BR1_HOLE_EST), 1.7, "PE")
    text(*o(P.BR1_X_SPAN[0] + 1, BR1_Z[1] + 1), "BR1 (owner-fitted; case = basic), selected shim behind strip", 1.6)
    text(*o(P.STRIP_X[0] + 30, STRIP_Z[0] - 9.5), "green under each FET: selected shim (0-2.0 mm) under the strip", 1.4, "PE")
    for dx in (0, 10, 17.5, 25):
        line(*o(81.7 + dx, BR1_Z[0]), *o(81.7 + dx, -1.6))
    rect(*o(P.BAR["x"][0], P.BAR["z"][0]), *o(P.BAR["x"][1], P.BAR["z"][1]), "HIDDEN")
    text(*o(P.BAR["x"][0] + 1, P.BAR["z"][0] + 0.8), "clamp bar 3/8 x 1 in 6061 (in front of the packages)", 1.4, "HIDDEN")
    for x in P.BAR_SCREW_X:
        circle(*o(x, P.BAR_SCREW_Z), 2.0, "PE"); circle(*o(x, P.BAR_SCREW_Z), 3.0, "PE")
    sl = P.BAR_SLOT
    rect(*o(sl["x"] - sl["w"] / 2, sl["z"][0]), *o(sl["x"] + sl["w"] / 2, sl["z"][1]), "HIDDEN")
    circle(*o(*P.NTC_XZ), 1.5, "PE"); text(*o(P.NTC_XZ[0] - 6, P.NTC_XZ[1] + 3), "NTC M3", 1.6)
    rect(*o(P.TCO_XZ[0] - 5.5, P.TCO_XZ[1] - 2), *o(P.TCO_XZ[0] + 5.5, P.TCO_XZ[1] + 2), "INSUL")
    circle(*o(*P.TCO_CLAMP_SCREW_XZ), 1.5, "PE"); text(*o(P.TCO_XZ[0] + 7, P.TCO_XZ[1]), "TCO DF110S, 2x Kapton, loop clamp", 1.6)
    circle(*o(*P.BOND_XZ), 2.0, "PE"); text(*o(P.BOND_XZ[0] - 22, P.BOND_XZ[1] + 3), "PE bond M4", 1.6)
    dim_h(*[ox + SINK_X[0], ox + SINK_X[1]], oy - 8, f"{P.SINK_WIDTH} sink")
    dim_v(ox + SINK_X[1] + 4, oy + 0, oy + SINK_Z[0], f"{P.Z_SINK_BOTTOM} +/- {P.Z_SINK_TOL}")
    dim_v(ox + P.STRIP_X[0] - 4, oy + STRIP_Z[0], oy + SINK_Z[0], f"overhang {P.STRIP_OVERHANG}")
    dim_h(ox + 0, ox + P.STRIP_X[0], oy - 4, f"{P.STRIP_X[0]}")


def view_section(ox, oy):
    o = lambda y, z: (ox + y, oy + z)
    text(*o(-62, 88), "B  SECTION at Q3 (y into the board, z up)", 2.5)
    rect(*o(0, -1.6), *o(40, 0))
    text(*o(30, -4), "board", 1.6)
    rect(*o(Y_FACE - P.SINK_BASE_T, SINK_Z[0]), *o(Y_FACE, SINK_Z[1]), "PE")
    for z in range(int(SINK_Z[0]) + 4, int(SINK_Z[1]), 9):
        line(*o(Y_FACE - P.SINK_BASE_T, z), *o(Y_FACE - P.SINK_HEIGHT, z), "PE")
    text(*o(Y_FACE - P.SINK_HEIGHT, SINK_Z[1] + 2), "fins (vertical, along z)", 1.6, "PE")
    rect(*o(Y_FACE, STRIP_Z[0]), *o(P.Y_TAB, STRIP_Z[1]), "INSUL")
    rect(*o(P.Y_TAB, BODY_Z[0]), *o(P.Y_TAB + NOM["A"], BODY_Z[1]))
    rect(*o(P.Y_TAB, METAL_BOT), *o(P.Y_TAB + NOM["A2"], METAL_TOP), "HIDDEN")
    line(*o(P.Y_FET_LEAD, BODY_Z[0]), *o(P.Y_FET_LEAD, -1.6))
    y_pf = P.Y_TAB + NOM["A"]
    y_pp = y_pf + 1.6
    rect(*o(y_pf, P.SPRING_Z - P.FR4_PAD[1] / 2), *o(y_pp, P.SPRING_Z + P.FR4_PAD[1] / 2), "INSUL")
    rp = P.SPRING["OD"] / 2
    rect(*o(y_pp, P.SPRING_Z - rp), *o(Y_BAR + P.POCKET_DEPTH, P.SPRING_Z + rp), "HIDDEN")
    for k in range(6):
        y = y_pp + k * (Y_BAR + P.POCKET_DEPTH - y_pp) / 6
        line(*o(y, P.SPRING_Z - rp), *o(y + (Y_BAR + P.POCKET_DEPTH - y_pp) / 12, P.SPRING_Z + rp), "HIDDEN")
    rect(*o(Y_BAR, P.BAR["z"][0]), *o(Y_BAR + P.BAR["t"], P.BAR["z"][1]), "PE")
    text(*o(Y_BAR, P.BAR["z"][1] + 1.5), "bar", 1.6, "PE")
    rect(*o(P.Y_FILM_COURTYARD_FRONT, 0), *o(P.Y_FILM_COURTYARD_FRONT + 9.59, 17), "HIDDEN")
    text(*o(P.Y_FILM_COURTYARD_FRONT, 18), "C38-C41 courtyard", 1.4, "HIDDEN")
    dim_h(ox + Y_FACE, ox + P.Y_TAB, oy + 36, f"strip {t_pad}")
    dim_h(ox + Y_FACE, ox + Y_BAR, oy + 40, f"spacer {P.SPACER_L}")
    dim_h(ox + 0, ox + Y_FACE, oy - 7, f"face {Y_FACE:.3f} inside edge")
    dim_v(ox + Y_FACE - P.SINK_HEIGHT - 3, oy + 0, oy + SINK_Z[0], f"{P.Z_SINK_BOTTOM}")
    dim_v(ox + Y_FACE + 0.6, oy + STRIP_Z[0], oy + SINK_Z[0], "2.5")
    text(*o(-60, -10), f"spring {P.SPRING['pn']} in a {P.SPRING['hole']} pocket {P.POCKET_DEPTH} deep; FR-4 pad {P.FR4_PAD[0]} x {P.FR4_PAD[1]} x 1.6 on the package front", 1.5)


def view_plan(ox, oy):
    o = lambda x, y: (ox + x, oy - y)          # y into the board drawn downward
    text(*o(-30, 72), "C  PLAN (x right, y into the board drawn down; baseplate window for bottom-side soldering)", 2.5)
    line(*o(0, 0), *o(140, 0)); line(*o(0, 0), *o(0, 60)); text(*o(141, 0), "board rear edge y=0", 1.6)
    rect(*o(SINK_X[0], Y_FACE - P.SINK_HEIGHT), *o(SINK_X[1], Y_FACE), "PE")
    for ref, xc in P.FET_X.items():
        rect(*o(xc - NOM["E"] / 2, P.Y_TAB), *o(xc + NOM["E"] / 2, P.Y_TAB + NOM["A"]))
    rect(*o(P.BR1_X_SPAN[0], P.Y_BR1_BACK), *o(P.BR1_X_SPAN[1], P.Y_BR1_BACK + 4.6))
    rect(*o(P.BAR["x"][0], Y_BAR), *o(P.BAR["x"][1], Y_BAR + P.BAR["t"]), "PE")
    for x in P.BAR_SCREW_X:
        rect(*o(x - 3, Y_FACE), *o(x + 3, Y_BAR), "PE")
    a = P.BRACKET["angle"]
    rect(*o(SINK_X[0] - a[2], -45), *o(SINK_X[0], -5), "PE")
    rect(*o(SINK_X[1], -45), *o(SINK_X[1] + a[2], -5), "PE")
    text(*o(SINK_X[0] - 30, -25), "bracket", 1.6, "PE"); text(*o(SINK_X[1] + 5, -25), "bracket", 1.6, "PE")
    rect(*o(P.WINDOW["x"][0], P.WINDOW["y"][0]), *o(P.WINDOW["x"][1], P.WINDOW["y"][1]), "DIM")
    rect(*o(P.WINDOW_BR1["x"][0], P.WINDOW_BR1["y"][0]), *o(P.WINDOW_BR1["x"][1], P.WINDOW_BR1["y"][1]), "DIM")
    text(*o(P.WINDOW_BR1["x"][0] + 1, P.WINDOW_BR1["y"][1] - 2), "extension: bottom preheater for BR1", 1.4, "DIM")
    text(*o(P.WINDOW["x"][0] + 1, P.WINDOW["y"][1] + 3), "baseplate window (solder / rework access)", 1.6, "DIM")
    fy = Y_FACE - P.SINK_HEIGHT - P.FAN["gap_to_fins"]
    xc = (SINK_X[0] + SINK_X[1]) / 2
    rect(*o(xc - P.FAN["size"] / 2, fy - P.FAN["depth"]), *o(xc + P.FAN["size"] / 2, fy), "HIDDEN")
    text(*o(xc - 20, fy - P.FAN["depth"] - 4), f"fan {P.FAN['pn']} blowing at the fins", 1.6, "HIDDEN")
    hx, hy, _ = P.MOUNT_HOLES["H9"]
    circle(*o(hx, hy), 1.6, "DIM"); text(*o(hx + 2, hy + 1), "H9 EMPTY", 1.6, "DIM")
    hx, hy, _ = P.MOUNT_HOLES["H5"]
    circle(*o(hx, hy), 1.6); text(*o(hx + 2, hy + 1), "H5 nylon", 1.6)


def view_sink_drill(ox, oy, holes):
    text(ox, oy + P.SINK_LEN + 6, "D  SINK FRONT FACE drilling (u from the left edge, v from the bottom edge, face toward you)", 2.5)
    rect(ox, oy, ox + P.SINK_WIDTH, oy + P.SINK_LEN, "PE")
    for name, u, v, d, how in holes:
        circle(ox + u, oy + v, d / 2, "PE")
        text(ox + u + d / 2 + 0.5, oy + v + 0.5, name, 1.4)
    rect(ox + P.STRIP_X[0] - SINK_X[0], oy - P.STRIP_OVERHANG, ox + P.STRIP_X[1] - SINK_X[0], oy + P.STRIP_TOP_Z - P.Z_SINK_BOTTOM, "INSUL")


def view_bar(ox, oy, bar_holes):
    L = P.BAR["x"][1] - P.BAR["x"][0]
    text(ox, oy + P.BAR["h"] + 5, f"E  CLAMP BAR {L:.1f} x 25.4 x 9.525 (sink-facing face toward you)", 2.5)
    rect(ox, oy, ox + L, oy + P.BAR["h"], "PE")
    for name, u, v, d, how in bar_holes:
        circle(ox + u, oy + v, d / 2, "PE")
        text(ox + u - 3, oy + v + d / 2 + 0.8, name, 1.4)


def view_cuts(ox, oy):
    text(ox, oy + 40, "F  CUT PARTS", 2.5)
    w, h = P.STRIP_X[1] - P.STRIP_X[0], STRIP_Z[1] - STRIP_Z[0]
    rect(ox, oy, ox + w, oy + h, "INSUL")
    circle(ox + BR1_HOLE_EST[0] - P.STRIP_X[0], oy + BR1_HOLE_EST[1] - STRIP_Z[0], 2.0, "INSUL")
    text(ox + 2, oy + h - 4, f"strip {w:.1f} x {h:.1f}, {P.PAD_CHOICE}; scribe a line {P.STRIP_OVERHANG} mm above the bottom edge (sink edge); BR1 hole punched on assembly", 1.5)
    rect(ox + w + 10, oy, ox + w + 10 + P.SHIM_SIZE[0], oy + P.SHIM_SIZE[1], "PE")
    text(ox + w + 10, oy + P.SHIM_SIZE[1] + 2, f"shim {P.SHIM_SIZE[0]} x {P.SHIM_SIZE[1]} x {P.SHIM_T}", 1.5)
    rect(ox + w + 45, oy, ox + w + 45 + P.FR4_PAD[0], oy + P.FR4_PAD[1], "INSUL")
    text(ox + w + 45, oy + P.FR4_PAD[1] + 2, f"FR-4 pad {P.FR4_PAD[0]} x {P.FR4_PAD[1]} x 1.6 or 0.8", 1.5)
    rect(ox + w + 65, oy, ox + w + 65 + P.SHIM_FET_SIZE[0], oy + P.SHIM_FET_SIZE[1], "PE")
    text(ox + w + 65, oy + P.SHIM_FET_SIZE[1] + 2, f"FET shim {P.SHIM_FET_SIZE[0]} x {P.SHIM_FET_SIZE[1]} x selected", 1.5)


def write_dxf(path):
    out = ["0", "SECTION", "2", "ENTITIES"]
    for kind, layer, d in ENT:
        if kind == "LINE":
            out += ["0", "LINE", "8", layer, "10", f"{d[0]:.4f}", "20", f"{d[1]:.4f}", "30", "0", "11", f"{d[2]:.4f}", "21", f"{d[3]:.4f}", "31", "0"]
        elif kind == "CIRCLE":
            out += ["0", "CIRCLE", "8", layer, "10", f"{d[0]:.4f}", "20", f"{d[1]:.4f}", "30", "0", "40", f"{d[2]:.4f}"]
        else:
            out += ["0", "TEXT", "8", layer, "10", f"{d[0]:.4f}", "20", f"{d[1]:.4f}", "30", "0", "40", f"{d[2]:.3f}", "1", d[3]]
    out += ["0", "ENDSEC", "0", "EOF"]
    path.write_text("\n".join(out) + "\n")


def write_svg(path):
    xs, ys = [], []
    for kind, _, d in ENT:
        if kind == "LINE":
            xs += [d[0], d[2]]; ys += [d[1], d[3]]
        else:
            xs.append(d[0]); ys.append(d[1])
    x0, x1, y0, y1 = min(xs) - 10, max(xs) + 60, min(ys) - 10, max(ys) + 10
    s = 4.0
    W, H = (x1 - x0) * s, (y1 - y0) * s
    X = lambda x: (x - x0) * s
    Y = lambda y: (y1 - y) * s
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W:.0f}" height="{H:.0f}" viewBox="0 0 {W:.0f} {H:.0f}">',
         f'<rect width="{W:.0f}" height="{H:.0f}" fill="#fff"/>']
    for kind, layer, d in ENT:
        c = COLORS.get(layer, "#000")
        dash = ' stroke-dasharray="6,4"' if layer == "HIDDEN" else ""
        if kind == "LINE":
            o.append(f'<line x1="{X(d[0]):.1f}" y1="{Y(d[1]):.1f}" x2="{X(d[2]):.1f}" y2="{Y(d[3]):.1f}" stroke="{c}" stroke-width="1"{dash}/>')
        elif kind == "CIRCLE":
            o.append(f'<circle cx="{X(d[0]):.1f}" cy="{Y(d[1]):.1f}" r="{d[2] * s:.1f}" fill="none" stroke="{c}" stroke-width="1"{dash}/>')
        else:
            t_ = d[3].replace("&", "&amp;").replace("<", "&lt;")
            o.append(f'<text x="{X(d[0]):.1f}" y="{Y(d[1]):.1f}" font-family="sans-serif" font-size="{d[2] * s:.1f}" fill="{c}">{t_}</text>')
    o.append("</svg>")
    path.write_text("\n".join(o) + "\n")


def main():
    u = lambda x: x - SINK_X[0]
    v = lambda z: z - SINK_Z[0]
    base_txt = f"through the {P.SINK_BASE_T} mm base"   # the base is the only metal the hole can thread into
    holes = [("bar screw L, M4 tapped through the base", u(P.BAR_SCREW_X[0]), v(P.BAR_SCREW_Z), 4.0, f"drill 3.3 {base_txt}, tap M4 through ({P.SINK_BASE_T} mm engagement); confirm first that it lands between fin grooves"),
             ("bar screw R, M4 tapped through the base", u(P.BAR_SCREW_X[1]), v(P.BAR_SCREW_Z), 4.0, f"drill 3.3 {base_txt}, tap M4 through ({P.SINK_BASE_T} mm engagement); confirm first that it lands between fin grooves"),
             ("NTC lug, M3", u(P.NTC_XZ[0]), v(P.NTC_XZ[1]), 3.0, f"drill 2.5 {base_txt}, tap M3 through ({P.SINK_BASE_T} mm engagement); confirm first that it lands between fin grooves"),
             ("TCO loop-clamp tab, M3", u(P.TCO_CLAMP_SCREW_XZ[0]), v(P.TCO_CLAMP_SCREW_XZ[1]), 3.0, f"drill 2.5 {base_txt}, tap M3 through ({P.SINK_BASE_T} mm engagement); confirm first that it lands between fin grooves"),
             ("PE bond, M4", u(P.BOND_XZ[0]), v(P.BOND_XZ[1]), 4.0, f"drill 3.3 {base_txt}, tap M4 through ({P.SINK_BASE_T} mm engagement); confirm first that it lands between fin grooves"),
             ("BR1 screw, M3", u(BR1_HOLE_EST[0]), v(BR1_HOLE_EST[1]), 3.0,
              f"v = (measured seat height of a loose BR1 + {sum(P.GBJ['S']) / 2:.1f} + {P.BR1_LIFT}) - {P.Z_SINK_BOTTOM}; shown at the EST seat {P.BR1_SEAT_Z_EST}. Drill 2.5 {base_txt}, tap M3 through ({P.SINK_BASE_T} mm engagement)")]
    xb0 = P.BAR["x"][0]
    bar_holes = [(f"pocket {r}", P.FET_X[r] - xb0, P.SPRING_Z - P.BAR["z"][0], P.SPRING["hole"],
                  f"3/8 in flat-bottom, {P.POCKET_DEPTH} deep (twist drill + 3/8 in counterbore, or end mill)") for r in P.FET_X]
    bar_holes += [(f"end hole {i}", x - xb0, P.BAR_SCREW_Z - P.BAR["z"][0], P.BAR_HOLE_D, f"through {P.BAR_HOLE_D} (M4 clearance)")
                  for i, x in enumerate(P.BAR_SCREW_X, 1)]
    sl = P.BAR_SLOT
    bar_holes += [("BR1 driver slot", sl["x"] - xb0, sum(sl["z"]) / 2 - P.BAR["z"][0], sl["w"],
                   f"through slot {sl['w']} wide, v {sl['z'][0] - P.BAR['z'][0]:.1f}..{sl['z'][1] - P.BAR['z'][0]:.1f} (two {sl['w']} holes + file)")]
    view_front(0, 0)
    view_section(220, 0)
    view_plan(0, -160)
    view_sink_drill(0, 120, holes)
    view_bar(160, 120, bar_holes)
    view_cuts(0, 230)
    (STUDY / "results").mkdir(exist_ok=True)
    write_dxf(STUDY / "results" / "bench-sink-r1.dxf")
    write_svg(STUDY / "results" / "bench-sink-r1.svg")
    md = ["# Bench sink r1: drill and cut tables (generated by scripts/bench_cad.py; do not edit)", "",
          f"Sink {P.SINK_PN}: front face {P.SINK_WIDTH} (u) x {P.SINK_LEN} (v), u from the face's left edge (board x {SINK_X[0]}), "
          f"v from its lower edge (board z {SINK_Z[0]}, set {P.Z_SINK_BOTTOM} +/- {P.Z_SINK_TOL} above the board top). Board x = u {SINK_X[0]:+}; z = v + {SINK_Z[0]}.", "",
          "| hole | u mm | v mm | size | how |", "|---|---|---|---|---|"]
    md += [f"| {n} | {a:.2f} | {b:.2f} | {d} | {how} |" for n, a, b, d, how in holes]
    md += ["", "Bracket bolts (2 per end, M4 through the outermost fin, nut in the first fin channel): MATCH-drill with the sink "
           "set on its gauges; brackets stay >= 5 mm behind the board edge (y <= -5).", "",
           f"Clamp bar: 6061 3/8 x 1 in, cut {P.BAR['x'][1] - P.BAR['x'][0]:.1f} mm; u from the bar's left end (board x {xb0}), v from its lower edge (board z {P.BAR['z'][0]}).", "",
           "| hole | u mm | v mm | size | how |", "|---|---|---|---|---|"]
    md += [f"| {n} | {a:.2f} | {b:.2f} | {d} | {how} |" for n, a, b, d, how in bar_holes]
    md += ["", "| cut part | size mm | from |", "|---|---|---|",
           f"| insulator strip | {P.STRIP_X[1] - P.STRIP_X[0]:.1f} x {STRIP_Z[1] - STRIP_Z[0]:.1f} | {P.PADS[P.PAD_CHOICE]['pn']} |",
           f"| BR1 shim (selected at the BR1 dry fit, Ø3.5 hole at the screw) | {P.SHIM_SIZE[0]} x {P.SHIM_SIZE[1]} x 0-{P.SHIM_MAX_DESIGN} | shim stock, <= {P.SHIM_LAYERS_MAX} layers |",
           f"| FET shims (selected by shim_select.py) | {P.SHIM_FET_SIZE[0]} x {P.SHIM_FET_SIZE[1]} x 0-{P.SHIM_MAX_DESIGN}, lower edge at v {P.SHIM_FET_Z0 - P.Z_SINK_BOTTOM:.1f} | shim stock, <= {P.SHIM_LAYERS_MAX} layers, deburred |",
           f"| FR-4 pressure pads x 4 (+ spares) | {P.FR4_PAD[0]} x {P.FR4_PAD[1]} x 1.6, or x 0.8 per shim_select.py | 1/16 and 1/32 in G-10/FR-4 sheet |",
           f"| spacers x 2 | {P.SPACER_L} long, OD 6, ID 4.3 | RAF M0539-4-AL |", "",
           f"Strip placement on the sink face: left end at u {P.STRIP_X[0] - SINK_X[0]:.1f}, lower edge {P.STRIP_OVERHANG} below the sink's lower edge, "
           f"top at v {P.STRIP_TOP_Z - SINK_Z[0]:.1f}. Shim centred at u {P.BR1_X - SINK_X[0]:.1f}, v {SHIM_Z[0] - SINK_Z[0]:.1f}..{SHIM_Z[1] - SINK_Z[0]:.1f}, under the strip.",
           "", f"BR1 seated height is an estimate (body z {BR1_Z[0]:.1f}.., hole z {BR1_HOLE_EST[1]:.1f}): the GBJ drawing does not place "
           "the lead feature it seats on, so measure a loose part before drilling. Brackets: M4 pivot through the outer fin in a "
           "Ø8 hole with a fender washer (y and z float), second M4 in a Ø8 hole to lock the tilt."]
    (STUDY / "results" / "drill-table.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))
    print(f"\n{len(ENT)} entities -> results/bench-sink-r1.dxf, .svg")


if __name__ == "__main__":
    main()
