#!/usr/bin/env python3
"""G02/G03 power-path scenarios on the stage-19c copper dump (what-if edits, necks, DC R, plane L).

    python3 -I scenarios.py            # writes ../results/scenarios.json and prints the tables

Scenarios (all geometry is spelled out in PROPOSALS.md; coordinates are board mm, y down):
  BASE   stage 19c as dumped.
  S1     keep the J7-J10 straps; clear the x 77-84 corridor and fix the other necks (copper only):
           S1a  move the two n_ha F.Cu/B.Cu ties off the corridor ((74.8,30.7) and (77.86,30.85) -> (73.88,44.3)
                and (77.83,42.4)), extend the B.Cu n_ha tab to x 78.2 at y 41-44;
           S1b  leg_a-out_l In1 run (y 34.7, x 56-82) moved to In2 (x 56 south to y 46.6, east to x 83.17), TP1 via to (83.17,47.3)
           S1c  R5.4 via field: analytic, see r5_via_field.py;
           (S1d, moving the In1 leg_ret/hv_ret split for leg A's source neck, was tried and dropped: the neck
            just becomes the Q3.3 pad tongue, 2,080 -> 2,130 A2s; edit_s1d is kept for the record.)
  P2     direct BR1 feed: rect_p -> bus_p, rect_n -> hv_ret, J7-J10 removed (no strap), In1/In2 re-poured
         in x 60-128, y 0-27 under the board's own clearance rules (S1c analytic).
Every edit is checked with whatif_lib.check_clear (DRC-style clearance against the dump). The neck calculator is
the unmodified F1 one. Nothing here is a layout: it is the proof that a layout with this geometry reaches the numbers.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np

from dcnet import NetGrid
from plane_l import trunk_table
from pp_common import RESULTS, load_copper
from whatif_lib import (check_clear, clip_zone, drop, f1c, make_track, make_via, necks, outline_poly, polys,
                        rename_net, repour, zone_prim)
from shapely.geometry import box

I_DC = 15.0           # A, the task-04 DC experiment current (round5-native21); R scales, loss scales as I^2
TARGET = 3420.0       # A^2 s: 2 x F1 clearing (DECISIONS 22)
F1_CLEAR = 1710.0

SEG_ALL = None        # filled from f1_containment.SEGMENTS


def near(p, xy, tol=0.02):
    c = p.get("centre")
    return c is not None and abs(c[0] - xy[0]) < tol and abs(c[1] - xy[1]) < tol


def trk(p, a, b, layer=None):
    return (p["kind"] == "track" and (layer is None or p["layer"] == layer) and
            ((np.allclose(p["start"], a, atol=0.02) and np.allclose(p["end"], b, atol=0.02)) or
             (np.allclose(p["start"], b, atol=0.02) and np.allclose(p["end"], a, atol=0.02))))


def edit_s1a(P, notes):
    """n_ha ties out of the corridor."""
    P = drop(P, lambda p: p["net"] == "n_ha" and p["kind"] == "via" and (near(p, (74.8, 30.7)) or near(p, (77.86, 30.85))))
    P = drop(P, lambda p: p["net"] == "n_ha" and (trk(p, (74.8, 30.7), (72.375, 39.6), "F.Cu") or trk(p, (77.83, 31.2), (77.86, 30.85), "F.Cu")))
    P = drop(P, lambda p: p["net"] == "n_ha" and trk(p, (77.83, 44.735), (77.83, 31.2), "F.Cu"))
    new = make_track("n_ha", "F.Cu", [(77.83, 44.735), (77.83, 42.4)], 0.25)
    vias = make_via("n_ha", (73.88, 44.3)) + make_via("n_ha", (77.83, 42.4))
    tab = zone_prim("n_ha", "B.Cu", box(75.0, 41.0, 78.2, 44.0))
    bad = check_clear(P, new + vias + [tab])
    notes.append(("S1a", "DRC violations on new n_ha items: %s" % (bad or "none")))
    return P + new + vias + [tab]


def edit_s1b(P, notes, remove_only=False):
    """leg_a-out_l (U1.10 -> gate resistor R12/R54) leaves In1: its 26 mm run x 56-82 at y 34.7 is a wall across the
    hv_ret plane (it separates the north plane from the y 35-39 ribbon for x 56-82).  New route: the existing via at
    (56,31) drops to In2, runs south along x = 56 and east along y = 46.6 (south of the bus_p corridor) to x = 83.17,
    where a new via at (83.17,47.3) reaches U1.10's F.Cu pad (short F.Cu stub).  The old TP1 via (82,37) and the
    F.Cu track (82,37)-(83.17,39.9)-(83.175,46.125) go away; TP1 moves to the new via."""
    P = drop(P, lambda p: p["net"] == "leg_a-out_l" and ((p["kind"] == "via" and near(p, (82.0, 37.0))) or
                                                         (p["kind"] == "track" and p["layer"] == "In1.Cu" and
                                                          (trk(p, (82.0, 34.7), (82.0, 37.0)) or trk(p, (56.0, 31.0), (56.0, 34.7)) or trk(p, (56.0, 34.7), (82.0, 34.7)))) or
                                                         (p["kind"] == "track" and p["layer"] == "F.Cu" and
                                                          (trk(p, (82.0, 37.0), (83.17, 39.9)) or trk(p, (83.17, 39.9), (83.175, 46.125))))))
    if remove_only:
        notes.append(("S1b_ub", "leg_a-out_l In1 run and test-point via removed outright (upper bound, no re-route)"))
        return P
    new = make_track("leg_a-out_l", "In2.Cu", [(56.0, 31.0), (56.0, 46.6), (83.17, 46.6), (83.17, 47.3)], 0.5)
    new += make_track("leg_a-out_l", "F.Cu", [(83.175, 46.125), (83.17, 47.3)], 0.3)
    new += make_via("leg_a-out_l", (83.17, 47.3), 0.85, 0.3)
    bad = check_clear(P, new, zones=False)
    zc = [b for b in check_clear(P, new, zones=True) if b not in bad]
    notes.append(("S1b", "non-zone DRC violations of the new leg_a-out_l route: %s; plane-void conflicts (resolved by re-pour): %d" % (bad or "none", len(zc))))
    return P + new


R5_VIAS = [(36.8, 17.0), (38.0, 17.0), (39.2, 17.0), (40.4, 17.0), (36.8, 18.4), (38.0, 18.4), (39.2, 18.4), (40.4, 18.4)]


def edit_s1c(P, notes):
    """R5.4 via field: handled analytically (r5_via_field.py); geometry would need In2/B.Cu void re-pour."""
    return P


def edit_s1d(P, notes):
    """leg_ret/hv_ret split on In1 from y 12.65 to y 14.0 for x 42.8-53."""
    P = clip_zone(P, "hv_ret", "In1.Cu", (42.8, 4.0, 53.0, 14.0))
    P = repour(P, "leg_ret", "In1.Cu", (42.8, 8.0, 53.0, 14.0), None)
    P = repour(P, "hv_ret", "In1.Cu", (42.8, 14.0, 53.0, 30.0), None)
    return P


def edit_s1_repour(P, d):
    O = outline_poly(d)
    P = repour(P, "hv_ret", "In1.Cu", (50, 22, 100, 50), O)
    P = repour(P, "bus_p", "In2.Cu", (50, 25.5, 100, 50), O)
    return P


def is_stud(p):
    return p.get("ref", "").split(".")[0] in ("J7", "J8", "J9", "J10")


def edit_p2(P, d):
    O = outline_poly(d)
    P = [p for p in P if not (p["kind"] == "zone" and p["net"] in ("rect_p", "rect_n") and p["layer"] in ("In1.Cu", "In2.Cu"))]
    P = drop(P, is_stud)
    P = rename_net(P, "rect_p", "bus_p")
    P = rename_net(P, "rect_n", "hv_ret")
    P = repour(P, "bus_p", "In2.Cu", (60, 0, 128, 30), O)
    P = repour(P, "hv_ret", "In1.Cu", (60, 0, 128, 30), O)
    return P


def seg_set(kind):
    m = f1c()
    base = list(m.SEGMENTS)
    if kind == "BASE":
        return base
    if kind in ("S1",):
        return base
    if kind == "P2":
        out = []
        for s in base:
            if s[3].startswith("BR1 +") or s[3].startswith("BR1 -"):
                continue
            if s[3] == "J8 -> Q2 drain (leg A)":
                s = ("bus_p", "BR1.1", "Q2.2", "BR1+ -> Q2 drain (leg A)")
            elif s[3] == "J8 -> Q5 drain (leg B)":
                s = ("bus_p", "BR1.1", "Q5.2", "BR1+ -> Q5 drain (leg B)")
            elif s[3] == "shunt R5 -> J10":
                s = ("hv_ret", "R5.4", "BR1.4", "shunt R5 -> BR1 -")
            out.append(s)
        return out


def run_necks(d, P, kind):
    res = necks(d, P, seg_set(kind))
    rows = []
    for r in res:
        rows.append({"segment": r["segment"], "net": r["net"], "neck_mm": r["neck_width_mm"], "at": r["neck_location_xy_mm"],
                     "layer": r["neck_layer"], "I2t_cons": round(r["I2t_conservative"]), "I2t_par": round(r["I2t_parallel"]),
                     "class": r["classification"].split(" (")[0]})
    return rows


def dc_paths(P, kind):
    out = {}
    if kind in ("BASE", "S1"):
        cases = [("rect_p", "BR1.1", ["J7.1"], (0, 0, 150, 60), "BR1+ -> J7"),
                 ("bus_p", "J8.1", ["Q2.2", "Q5.2"], (0, 0, 150, 60), "J8 -> Q2||Q5"),
                 ("hv_ret", "R5.4", ["J10.1"], (0, 0, 200, 60), "R5.4 -> J10"),
                 ("rect_n", "J9.1", ["BR1.4"], (0, 0, 150, 60), "J9 -> BR1-")]
    else:
        cases = [("bus_p", "BR1.1", ["Q2.2", "Q5.2"], (0, 0, 150, 60), "BR1+ -> Q2||Q5"),
                 ("hv_ret", "R5.4", ["BR1.4"], (0, 0, 200, 60), "R5.4 -> BR1-")]
    tot = 0.0
    for net, a, b, win, lab in cases:
        g = NetGrid(P, net, win, pitch=0.25)
        try:
            r = g.resistance([a], b) * 1e3
        except RuntimeError as e:
            out[lab] = {"error": str(e)}
            continue
        out[lab] = {"R_mOhm": round(r, 3), "loss_W_at_%gA" % I_DC: round(r * 1e-3 * I_DC ** 2, 3)}
        tot += r
    out["TOTAL"] = {"R_mOhm": round(tot, 3), "loss_W_at_%gA" % I_DC: round(tot * 1e-3 * I_DC ** 2, 3)}
    return out


def main():
    d = load_copper()
    P0 = d["primitives"]
    notes = []
    sc = {}
    sc["BASE"] = P0
    # S1 = a + b + c + d + repour
    P = edit_s1a(P0, notes)
    P = edit_s1b(P, notes)
    P = edit_s1c(P, notes)
    P = edit_s1_repour(P, d)
    sc["S1"] = P
    Pu = edit_s1a(P0, notes)
    Pu = edit_s1b(Pu, notes, remove_only=True)
    Pu = edit_s1c(Pu, notes)
    Pu = edit_s1_repour(Pu, d)
    sc["S1_ub"] = Pu
    P2 = edit_p2(P0, d)
    sc["P2"] = P2
    out = {"notes": notes, "I_DC_A": I_DC, "target_I2t": TARGET, "scenarios": {}}
    for k, PP in sc.items():
        kind = "BASE" if k == "BASE" else ("P2" if k == "P2" else "S1")
        rows = run_necks(d, PP, kind)
        mn = min(r["I2t_cons"] for r in rows)
        mn_wo_g01 = min(r["I2t_cons"] for r in rows if r["net"] in ("bus_p", "hv_ret", "leg_ret"))
        dc = dc_paths(PP, kind)
        L = trunk_table(PP)
        out["scenarios"][k] = {"necks": rows, "min_I2t_all": mn, "ratio_all": round(mn / F1_CLEAR, 3),
                               "min_I2t_G02_G03_nets": mn_wo_g01, "ratio_G02_G03": round(mn_wo_g01 / F1_CLEAR, 3),
                               "dc": dc, "plane_L": L}
        print("=" * 100)
        print(k, "min I2t all %d (x%.2f F1) | G02/G03 nets only %d (x%.2f)" % (mn, mn / F1_CLEAR, mn_wo_g01, mn_wo_g01 / F1_CLEAR))
        for r in rows:
            if r["net"] in ("bus_p", "hv_ret", "leg_ret", "rect_p", "rect_n"):
                print("  %-34s %-8s %6.2f mm @%-16s %-9s cons %6d par %6d  %s" % (r["segment"], r["net"], r["neck_mm"], r["at"], r["layer"], r["I2t_cons"], r["I2t_par"], r["class"]))
        for lab, v in dc.items():
            print("  DC %-18s %s" % (lab, v))
        for lab, v in L.items():
            print("  L  %-28s squares %s  L %s nH" % (lab, "%.2f" % v["squares"] if np.isfinite(v["squares"]) else "inf", "%.2f" % v["L_nH"] if v["L_nH"] is not None else "n/a"))
    for n in notes:
        print("NOTE", n)
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "scenarios.json").write_text(json.dumps(out, indent=1, default=float) + "\n")


if __name__ == "__main__":
    main()
