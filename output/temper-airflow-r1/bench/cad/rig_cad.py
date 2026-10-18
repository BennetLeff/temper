#!/usr/bin/env python3
"""Jet bench rig CAD: channel replica of the R45 jet box over native-21's strip, with a guarded heated plate.

    ../../.venv/bin/python rig_cad.py      # build123d 0.11.1 (recipe in ../README.md) -> rig-cad.json, STEP + STL

Frame: native-21 MODEL x/y (mm) as HANDOFF.md (x_w = x - 141, y_w = 236 - y), z above the board top = the test
plate's top face. Geometry is HANDOFF item 1/2 plus the s42 parts that bound the channel (cad/channel_parts.py):
  JET BOX   x 1..88, y 10.5..22.5, z 6..15; manifold 10.5 x 7 inside (side walls 0.75: HANDOFF's 1.0 mm walls round a
            10.5 mm manifold do not fit its own 12 mm Y envelope; the rig keeps the envelope, which is what bounds
            the channel); 1.0 floor with 8 x D3.0 jets at x 5.5 + 11k, y 14.0; closed at x 88; two 2 mm locating
            ribs bearing on the pressure-strip face (y 9.5), as HANDOFF's "1 mm locating rib".
  F3 FEED   leg B x -37..1, y 10.5..22.5, z 2..18 (1 mm walls) into the box; leg A x -37..-23, y -8.5..22.5 to the
            hood stand-in. Printed in two halves split at z 10.5 so the jet floor is drilled and deburred open.
  -Y WALL   TO-247 / BR1 package fronts at y 6.9 (z 0..9) under the FR-4 pressure strip face at y 9.5 (z 9..23), x -4..113
            (the FET/BR1 row; package gaps end on the AlN tile, dead ends, so the wall is continuous).
  FILM CAPS C38-C41 B32652 bodies 18 x 9 x 17.5 (footprint spec body_max), y 23.7..32.7, x 0.9..18.9, 22.7..40.7,
            44.5..62.5, 66.3..84.3 (pads from placement.json, body centred between the 15 mm pads).
  PLATE     6061, 90 x 16.5 x 3.0 = the strip, top z 0; 3 x D1.0 thermocouple holes from below, 2.0 deep, x 15/45/75.
  GUARD     6061 tray around and under the plate: 1.0 mm gap, 3 mm rim, 10 mm pocket; ears for the deck.
  DECK      printed 6 mm plate carrying the tray, walls and caps; HOOD a printed stand-in for the push hood.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from build123d import Align, Box, Compound, Cylinder, Pos, Vector, export_step, export_stl

HERE = Path(__file__).resolve().parent
MIN3 = (Align.MIN, Align.MIN, Align.MIN)
CYL = (Align.CENTER, Align.CENTER, Align.MIN)

STRIP = (0.0, 90.0, 7.0, 23.5)
JET_X, JET_Y, JET_D = [5.5 + 11.0 * k for k in range(8)], 14.0, 3.0
BOX = (1.0, 88.0, 10.5, 22.5, 6.0, 15.0)
MANIFOLD = (1.0, 87.0, 11.25, 21.75, 7.0, 14.0)
SPLIT_Z = 10.5
LEG_B = (-37.0, 1.0, 10.5, 22.5, 2.0, 18.0)
LEG_A = (-37.0, -23.0, -8.5, 22.5, 2.0, 18.0)
WALL_LO = (-4.0, 113.0, -8.0, 6.9, 0.0, 9.0)
WALL_HI = (-4.0, 113.0, -8.0, 9.5, 9.0, 23.0)
CAPS_X = [(0.9, 18.9), (22.7, 40.7), (44.5, 62.5), (66.3, 84.3)]
CAP_Y, CAP_H = (23.7, 32.7), 17.5
GAP, RIM, POCKET, FLOOR_T = 1.0, 3.0, 10.0, 2.0
PLATE_T = 3.0
TC_X, TC_Y = [15.0, 45.0, 75.0], 15.25
TAPS = {"p_mid": 44.0, "p_end": 86.0}
TC_AIR_X = 66.0


def abox(x0, x1, y0, y1, z0, z1):
    return Pos(x0, y0, z0) * Box(x1 - x0, y1 - y0, z1 - z0, align=MIN3)


def zcyl(x, y, z0, z1, d):
    return Pos(x, y, z0) * Cylinder(d / 2, z1 - z0, align=CYL)


def duct(ribs=True):
    """Jet box + F3 legs + elbow foot + end tab, one solid (split into two print halves by halves())."""
    s = abox(*BOX) + abox(*LEG_B) + abox(*LEG_A)
    s -= abox(LEG_B[0] + 1, LEG_B[1] - 1, LEG_B[2] + 1, LEG_B[3] - 1, LEG_B[4] + 1, LEG_B[5] - 1)   # leg B bore, 1 mm end wall
    s -= abox(LEG_A[0] + 1, LEG_A[1] - 1, LEG_A[2] - 1, LEG_A[3] - 1, LEG_A[4] + 1, LEG_A[5] - 1)    # leg A bore, open at -y
    s -= abox(MANIFOLD[0] - 1.5, *MANIFOLD[1:])                               # manifold, through leg B's end wall
    s += abox(-37.0, -23.0, 10.5, 22.5, 0.0, 2.0)                                                     # elbow foot (product base bracket)
    s += abox(88.0, 94.0, 12.0, 20.0, SPLIT_Z, 15.0)                                                  # end tab under the wall's hanger arm
    s -= zcyl(91.0, 16.0, SPLIT_Z - 1, 16.0, 2.2)
    for x0 in (-41.0,):                                                                                # dowel lugs for the two halves
        for yc in (-4.0, 16.0):
            s += abox(x0, -37.0, yc - 3, yc + 3, 6.0, 15.0)
            s -= zcyl(x0 + 2.0, yc, 5.0, 16.0, 2.0)
    s += abox(-36.0 - 6, -24.0 + 6, -8.5, -5.5, 0.0, 20.0) - abox(-36.0, -24.0, -9.0, -5.0, 3.0, 17.0)      # flange on the hood wall
    for xc in (-39.0, -21.0):
        s -= Pos(xc, -8.5, 10.0) * Cylinder(1.7, 8.0, rotation=(90, 0, 0))
    if ribs:
        for xc in (33.0, 66.0):
            s += abox(xc - 1.0, xc + 1.0, 9.5, 10.5, 9.0, 15.0)
    for xj in JET_X:
        s -= zcyl(xj, JET_Y, 5.0, 7.5, JET_D)
    for x in TAPS.values():                                                    # pressure-tap bosses on the lid
        s += zcyl(x, 16.5, 15.0, 21.0, 5.0)
        s -= zcyl(x, 16.5, 13.5, 21.5, 1.0)
        s -= zcyl(x, 16.5, 17.0, 21.5, 3.2)
    s += zcyl(TC_AIR_X, 16.5, 15.0, 19.0, 4.0)                                 # jet-air thermocouple port
    s -= zcyl(TC_AIR_X, 16.5, 13.5, 19.5, 1.2)
    return s


def halves(s):
    big = 400.0
    lower = s & abox(-big, big, -big, big, -big, SPLIT_Z)
    upper = s & abox(-big, big, -big, big, SPLIT_Z, big)
    return lower, upper


def wall():
    s = abox(*WALL_LO) + abox(*WALL_HI)
    s += abox(89.0, 95.0, 9.5, 20.0, 15.0, 18.0)                               # hanger arm over the duct's end tab
    s -= zcyl(91.0, 16.0, 14.0, 19.0, 2.2)
    for xc in (0.0, 54.0, 108.0):
        s += zcyl(xc, -4.0, -3.0, 0.0, 3.0)
    return s


def caps():
    out = []
    for x0, x1 in CAPS_X:
        c = abox(x0, x1, CAP_Y[0], CAP_Y[1], 0.0, CAP_H) + zcyl((x0 + x1) / 2, 30.5, -3.0, 0.0, 3.0)
        out.append(c)
    return out


def plate():
    s = abox(STRIP[0], STRIP[1], STRIP[2], STRIP[3], -PLATE_T, 0.0)
    for x in TC_X:
        s -= zcyl(x, TC_Y, -PLATE_T - 0.1, -PLATE_T + 2.0, 1.0)
    return s


def tray():
    x0, x1, y0, y1 = STRIP[0] - GAP - RIM, STRIP[1] + GAP + RIM, STRIP[2] - GAP - RIM, STRIP[3] + GAP + RIM
    zb = -POCKET - FLOOR_T
    s = abox(x0, x1, y0, y1, zb, 0.0)
    s -= abox(STRIP[0] - GAP, STRIP[1] + GAP, STRIP[2] - GAP, STRIP[3] + GAP, -POCKET, 0.1)
    s += abox(x0 - 8.0, x0, y0, y1, -3.0, 0.0) + abox(x1, x1 + 8.0, y0, y1, -3.0, 0.0)          # ears onto the deck
    for xe in (x0 - 4.0, x1 + 4.0):
        s -= zcyl(xe, (y0 + y1) / 2, -4.0, 1.0, 3.4)
    for x, y in ((8, 11), (8, 20), (82, 11), (82, 20)):                                          # M3 nylon set-screw supports
        s -= zcyl(x, y, zb - 0.1, -POCKET + 0.1, 2.5)
    for x, y, d in ((15, 19.5, 4.0), (45, 19.5, 4.0), (75, 19.5, 4.0), (40.5, 15.25, 5.0), (70.5, 15.25, 5.0)):
        s -= zcyl(x, y, zb - 0.1, -POCKET + 0.1, d)                                              # TC and heater-lead exits
    for x in (15.0, 75.0):                                                                       # guard thermocouples, rim (+y)
        s -= zcyl(x, (STRIP[3] + GAP + y1) / 2, zb - 0.1, -2.0, 1.0)
    return s


def deck(tr):
    s = abox(-45.0, 118.0, -8.0, 45.0, -6.0, 0.0)
    bb = tr.bounding_box()
    s -= abox(STRIP[0] - GAP - RIM - 0.3, STRIP[1] + GAP + RIM + 0.3, bb.min.Y - 0.3, bb.max.Y + 0.3, -7.0, 1.0)
    s -= abox(bb.min.X - 0.3, bb.max.X + 0.3, bb.min.Y - 0.3, bb.max.Y + 0.3, -3.0, 1.0)        # ear recesses
    for xe in (bb.min.X + 4.0, bb.max.X - 4.0):
        s -= zcyl(xe, (bb.min.Y + bb.max.Y) / 2, -7.0, 1.0, 2.8)
    for xc in (0.0, 54.0, 108.0):
        s -= zcyl(xc, -4.0, -3.5, 1.0, 3.2)
    for x0, x1 in CAPS_X:
        s -= zcyl((x0 + x1) / 2, 30.5, -3.5, 1.0, 3.2)
    return s


def hood():
    """Push-hood stand-in: open-top box (lid separate) the blower blows into; feed hole as R45-C-PUSH-HOOD."""
    s = abox(-70.0, 10.0, -66.0, -8.5, -56.0, 34.0) - abox(-67.5, 7.5, -63.5, -11.0, -53.5, 35.0)   # open top, 2.5 walls
    s -= abox(-36.0, -24.0, -11.5, -8.0, 3.0, 17.0)                            # feed hole 12 x 14 (x, z)
    for xc in (-39.0, -21.0):
        s -= Pos(xc, -8.5, 10.0) * Cylinder(1.7, 8.0, rotation=(90, 0, 0))
    s -= abox(-50.0, -10.0, -67.0, -63.0, -40.0, -10.0)                        # blower outlet opening 40 x 30 (gasket)
    s -= Pos(-70.0, -30.0, -20.0) * Cylinder(2.0, 8.0, rotation=(0, 90, 0))    # Pt100 port (hood air temperature)
    lid = abox(-70.0, 10.0, -66.0, -8.5, 34.0, 36.5)
    for i in range(5):
        lid -= zcyl(-60.0 + 10.0 * i, -50.0, 33.0, 37.0, 8.0)                  # bleed holes, trimmed with tape
    baffle = abox(-55.0, -5.0, -40.0, -38.0, -53.5, 25.0)                      # keeps the blower jet off the feed hole
    return s + baffle, lid


def main():
    d = duct()
    lower, upper = halves(d)
    wl, cs, pl, tr = wall(), caps(), plate(), tray()
    dk = deck(tr)
    hd, lid = hood()
    parts = {"duct_lower": lower, "duct_upper": upper, "wall_minus_y": wl, **{f"film_cap_{i + 1}": c for i, c in enumerate(cs)},
             "plate": pl, "guard_tray": tr, "deck": dk, "hood_box": hd, "hood_lid": lid}

    checks = {}
    floor_region = duct(ribs=False) & abox(2.0, 87.0, 9.0, 24.0, 0.0, 8.0)
    checks["jet_floor_to_plate_mm"] = round(floor_region.distance_to(pl), 3)
    box_only = duct(ribs=False) & abox(1.5, 88.0, 0.0, 30.0, 0.0, 15.0)
    checks["box_to_pressure_strip_face_mm"] = round(box_only.distance_to(wl), 3)
    checks["box_to_film_caps_mm"] = round(min(box_only.distance_to(c) for c in cs), 3)
    checks["plate_to_guard_mm"] = round(pl.distance_to(tr), 3)
    checks["jets_open"] = all(not d.is_inside(Vector(x, JET_Y, 6.5)) for x in JET_X)
    checks["jet_floor_solid_between_jets"] = all(d.is_inside(Vector(x + 5.5, JET_Y, 6.5)) for x in JET_X[:-1])
    checks["ribs_touch_strip_face_mm"] = round(d.distance_to(wl), 3)
    names = list(parts)
    over = []
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            v = (parts[a] & parts[b]).volume
            if v > 1e-3:
                over.append({"a": a, "b": b, "overlap_mm3": round(v, 3)})
    checks["overlaps"] = over
    checks["pass"] = (abs(checks["jet_floor_to_plate_mm"] - 6.0) < 1e-3 and abs(checks["box_to_pressure_strip_face_mm"] - 1.0) < 1e-3
                      and abs(checks["box_to_film_caps_mm"] - 1.2) < 1e-3 and abs(checks["plate_to_guard_mm"] - GAP) < 1e-3
                      and checks["jets_open"] and checks["jet_floor_solid_between_jets"] and checks["ribs_touch_strip_face_mm"] < 1e-3
                      and not over)

    out = {"scope": __doc__.strip(), "checks": checks, "parts": {}}
    make = {"plate": "JLCCNC 6061-T6, top face fine-milled (Ra <= 1.6 um), flat <= 0.05", "guard_tray": "JLCCNC 6061-T6"}
    for n, p in parts.items():
        bb = p.bounding_box()
        out["parts"][n] = {"bbox_mm": [round(v, 2) for v in (bb.min.X, bb.min.Y, bb.min.Z, bb.max.X, bb.max.Y, bb.max.Z)],
                           "volume_mm3": round(p.volume, 1), "make": make.get(n, "print PETG (or ASA), 0.4 nozzle, 100 % infill")}
        export_step(p, str(HERE / f"{n}.step"))
        if n not in make:
            export_stl(p, str(HERE / f"{n}.stl"))
    export_step(Compound(children=list(parts.values())), str(HERE / "rig-assembly.step"))
    out["plate_mass_g_6061"] = round(parts["plate"].volume * 2.70e-3, 2)
    out["tray_mass_g_6061"] = round(parts["guard_tray"].volume * 2.70e-3, 2)
    (HERE / "rig-cad.json").write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps(checks, indent=1))
    print({n: v["bbox_mm"] for n, v in out["parts"].items()})


if __name__ == "__main__":
    main()
