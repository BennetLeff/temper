"""J2/J5 coil-lead termination for R1: the chosen ring lug formed upturned on the Wurth 7466004R terminal, the lead sleeve,
and the bend rule. One source for the fit scripts (r1_parts, screen, lug_board, bench_leads).

Sources (read 2026-10-21; URLs and quotes in fit/README.md, section "Sources"):
  Wurth 7466004R datasheet rev 001.003 (2023-07-03): M4 thread through the part, body Ø7.0 x 5.0 above the PCB, 6.0
    overall with a Ø5.0 x 1.0 spigot in a Ø5.2 NPTH, tightening torque 1.2 N m, 50 A max at 20 C, -55..+150 C. No
    lug-width, washer or screw-head limit is stated in it or in the REDCUBE SMD design guide.
  Panduit P14-8RHT6-C (Pan-Term high-temperature, non-insulated): 18-14 AWG, #8 stud, ring OD 7.9, tongue 0.8, barrel
    ID 2.3, brazed seam, copper nickel-plated, 343 C max, overall length 18, strip length 7.1, cULus.
  TE 1577639-1 (PIDG STRATO-THERM, PEEK, 0-260 C): 14-12 AWG, Ø4.34 hole, ring 8.71, tongue 0.80, length 22.99 max,
    insulation sleeve Ø6.05 max, insulation support 2.30-3.18. Modelled as the alternative (LUGS["TE_1577639-1"]).
  Alpha Wire FIT-350 (PVDF, UL 224 150 C / 600 V, -55..175 C, 2:1): 3/16 in supplied >= 4.75 mm, recovered <= 2.36 mm,
    wall 0.25 mm; 1/4 in supplied 6.35, recovered 3.18, wall 0.30.
  Varflex Varglas Silicone Rubber (200 C, Grade C-1 2500 V min avg / 1500 V min individual): size No. 9 ID 0.114-0.124 in
    (2.90-3.15 mm), Grade C wall >= 0.008 in (0.20 mm).
  NASA-STD-8739.4A w/ Change 4, Table 7-1: installed harness of AWG 10 or smaller, minimum bend 3 x OD (optimum 10 x).
  New England Wire glossary: 5 x OD for static installations (generic guideline).
ASSUMED (not published in what was read; check on the first lug at W9): barrel wall 0.5 mm (barrel OD 3.3) for the
Panduit part; tongue formed 90 deg up with a 1.0 mm inner radius starting 0.5 mm past the ring edge, bent AWAY from the
barrel side so the barrel stands outboard (bend the other way and the barrel stands over the screw head); PEEK lug barrel
OD 4.0.
"""
from __future__ import annotations

import math

from build123d import Align, Box, Cylinder, Plane, Pos, Rot, Solid

BOARD_TOP_Z = 26.0 + 1.6                 # world; board_in_r43 pose (board-local 1.6 for envelopes)
TERMINAL = dict(part="Wurth 7466004R (WP-SMBU REDCUBE SMT, M4 through thread)", body_d=7.0, body_h=5.0, thread="M4",
                thread_len=6.0, torque_Nm=1.2)
SEAT_Z = BOARD_TOP_Z + TERMINAL["body_h"]   # 32.6: lug seat (R43 modelled the THR part's 31.3)
STUDS = {"J2": (-9.0, 150.5), "J5": (-9.0, 165.5)}          # world, after R31's mirror; 15.0 mm centres
AWAY = {"J2": -1.0, "J5": +1.0}                               # barrel offset direction along Y (away from the other stud)
SCREW = dict(part="ISO 7045 M4 x 8 A2 pan head + DIN 125-A M4 washer (Ø9 x 0.8) + DIN 127-B M4 spring washer",
             head_d=8.0, head_h=3.1, washer_d=9.0, washer_t=0.8, spring_t=0.9, length=8.0)
HEATSHRINK = dict(part="Alpha Wire FIT-350 PVDF: 3/16 in inner layer over barrel + 10 mm of sleeve; 1/4 in outer layer from "
                       "the sleeve over barrel and bend to the ring edge", walls_mm=(0.25, 0.30), over_sleeve_mm=10.0)
SLEEVE = dict(part="Varflex Varglas Silicone Rubber, Grade C-1, size No. 9 (200 C; 2500 V min avg)", id_mm=3.15, wall_mm=0.20,
              id_nominal_mm=3.0)
LUGS = {
    "Panduit_P14-8RHT6-C": dict(ring_od=7.9, hole=4.3, t=0.8, neck_w=4.8, barrel_id=2.3, barrel_od=3.3, barrel_len=7.1,
                                neck_len=3.0, insul_od=None, insul_len=0.0, temp_C=343, insulated=False),
    "TE_1577639-1": dict(ring_od=8.71, hole=4.34, t=0.80, neck_w=4.8, barrel_id=None, barrel_od=4.0, barrel_len=18.57 - 1.5,
                         neck_len=1.5, insul_od=6.05, insul_len=18.57 - 1.5, temp_C=260, insulated=True),
}
CHOICE = "Panduit_P14-8RHT6-C"
BEND_START, BEND_RI = 0.5, 1.0
LEAD_OD = SLEEVE["id_mm"] + 2 * SLEEVE["wall_mm"]
BEND_RULE_MM = 3.0 * LEAD_OD
BEND_RULE = (f"minimum bend radius 3 x the sleeved lead's OD ({LEAD_OD:.2f} mm -> {BEND_RULE_MM:.2f} mm): NASA-STD-8739.4A "
             "w/ Change 4 Table 7-1, installed harness of AWG 10 or smaller (minimum; optimum 10 x). Also reported: 5 x the "
             "bare bundle (11.45 mm), New England Wire's generic static guideline")
SUMMARY = (f"{CHOICE} formed 90 deg up (barrel outboard), FIT-350 PVDF two layers over barrel and bend to the ring; on "
           f"{TERMINAL['part']} at Z{SEAT_Z:.1f}; {SCREW['part']}")


def zcyl(x, y, z0, h, r):
    return Pos(x, y, z0) * Cylinder(r, h, align=(Align.CENTER, Align.CENTER, Align.MIN))


def geometry(name, which=CHOICE):
    L = LUGS[which]
    sx, sy = STUDS[name]
    sgn = AWAY[name]
    x_b = L["ring_od"] / 2 + BEND_START                      # bend start from the stud axis
    face_out = x_b + BEND_RI + L["t"]                        # outboard face of the vertical strip
    axis = face_out + L["barrel_od"] / 2                     # barrel (and lead) axis offset from the stud axis
    z_v0 = SEAT_Z + L["t"] + BEND_RI                         # where the strip is vertical
    vertical_neck = max(0.0, L["neck_len"] - BEND_START - math.pi / 2 * (BEND_RI + L["t"] / 2))
    z_b0 = z_v0 + vertical_neck
    z_b1 = z_b0 + L["barrel_len"]
    shrink_top = z_b1 + HEATSHRINK["over_sleeve_mm"]
    env_r = (L["insul_od"] / 2 if L["insul_od"] else L["barrel_od"] / 2) + sum(HEATSHRINK["walls_mm"])
    return dict(stud=(sx, sy), sgn=sgn, x_b=x_b, axis_offset=axis, drop=(sx, sy + sgn * axis), z_vertical=z_v0,
                barrel=(z_b0, z_b1), barrel_top=z_b1, shrink_top=shrink_top, envelope_r=env_r, lug=which, **L)


def lug_geometry(which=CHOICE):
    out = {}
    for n in STUDS:
        g = geometry(n, which)
        # board-frame drop (KiCad x right, y down): world = (x - 141, 236 - y)
        g["drop_board"] = (g["drop"][0] + 141.0, 236.0 - g["drop"][1])
        out[n] = g
    return out


def lug_solid(name, which=CHOICE):
    """Lug as fitted: ring + flat neck + the 90 deg bend + vertical neck/barrel, with the heat-shrink envelope over the
    barrel, the bend and up the sleeved lead (the insulated surface the fit must clear)."""
    g = geometry(name, which)
    sx, sy, s = *g["stud"], g["sgn"]
    t, w = g["t"], g["neck_w"]
    ring = zcyl(sx, sy, SEAT_Z, t, g["ring_od"] / 2) - zcyl(sx, sy, SEAT_Z - 1, 3, g["hole"] / 2)
    y0, y1 = sorted((sy, sy + s * g["x_b"]))
    neck = Pos(sx, (y0 + y1) / 2, SEAT_Z) * Box(w, y1 - y0, t, align=(Align.CENTER, Align.CENTER, Align.MIN))
    # bend: quarter torus section approximated by a box over the bend envelope (inner radius BEND_RI, thickness t)
    yb0, yb1 = sorted((sy + s * g["x_b"], sy + s * (g["x_b"] + BEND_RI + t)))
    bend = Pos(sx, (yb0 + yb1) / 2, SEAT_Z) * Box(w, yb1 - yb0, t + BEND_RI + 0.01, align=(Align.CENTER, Align.CENTER, Align.MIN))
    yv0, yv1 = sorted((sy + s * (g["x_b"] + BEND_RI), sy + s * (g["x_b"] + BEND_RI + t)))
    vneck = Pos(sx, (yv0 + yv1) / 2, g["z_vertical"]) * Box(w, yv1 - yv0, g["barrel"][0] - g["z_vertical"] + 0.5,
                                                             align=(Align.CENTER, Align.CENTER, Align.MIN))
    dx, dy = g["drop"]
    barrel = zcyl(dx, dy, g["barrel"][0], g["barrel"][1] - g["barrel"][0], g["barrel_od"] / 2)
    if g["insul_od"]:
        barrel = barrel + zcyl(dx, dy, g["barrel"][0], g["insul_len"], g["insul_od"] / 2)
    # heat-shrink envelope: from the ring edge (bend zone) up over the barrel and 10 mm of the sleeved lead
    shrink = zcyl(dx, dy, g["z_vertical"], g["shrink_top"] - g["z_vertical"], g["envelope_r"])
    ys0, ys1 = sorted((sy + s * g["x_b"], sy + s * (g["x_b"] + BEND_RI + t + sum(HEATSHRINK["walls_mm"]))))
    shrink_bend = Pos(sx, (ys0 + ys1) / 2, SEAT_Z - 0.0) * Box(w + 2 * sum(HEATSHRINK["walls_mm"]), ys1 - ys0,
                                                               g["z_vertical"] - SEAT_Z + 1.0 + sum(HEATSHRINK["walls_mm"]),
                                                               align=(Align.CENTER, Align.CENTER, Align.MIN))
    return ring + neck + bend + vneck + barrel + shrink + shrink_bend


def hardware_solid(name):
    """Washer, spring washer and pan-head screw on the ring (exposed metal; not part of the lug part)."""
    sx, sy = STUDS[name]
    t = LUGS[CHOICE]["t"]
    z = SEAT_Z + t
    w = zcyl(sx, sy, z, SCREW["washer_t"], SCREW["washer_d"] / 2)
    sp = zcyl(sx, sy, z + SCREW["washer_t"], SCREW["spring_t"], 3.7)
    head = zcyl(sx, sy, z + SCREW["washer_t"] + SCREW["spring_t"], SCREW["head_h"], SCREW["head_d"] / 2)
    return w + sp + head


def screw_stack():
    t = LUGS[CHOICE]["t"]
    S = t + SCREW["washer_t"] + SCREW["spring_t"]
    engaged = min(TERMINAL["thread_len"], SCREW["length"] - S)
    tip_below_board_top = SCREW["length"] - S - TERMINAL["body_h"]
    board_t = 1.633
    return dict(stack_mm=S, thread_engaged_mm=engaged, tip_below_board_top_mm=tip_below_board_top,
                tip_inside_board_mm=board_t - tip_below_board_top, board_thickness_nominal_mm=board_t,
                head_top_z=SEAT_Z + S + SCREW["head_h"])
