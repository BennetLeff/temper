#!/usr/bin/env python3
"""Converter-local capacitor distances on a built native-21 board (stage 19, review PI1 / PI2).

    KiCad-python pi_distances19.py BOARD.kicad_pcb [--json OUT.json] [--control]

Straight-line pad-centre distances (the stage-18 review's metric, "at their power pads"), from the converter's
power pins to the capacitor's pad on the same net:

  PI1  RECOM R24C2T25/R U41 / U42: VOUT+ pins 28 / 29 -> the p pad of the module's 10 uF (HsSplit cout1, C104 /
       C108) and 100 nF (chf, C75 / C82); VOUT- pins 19-27, 30, 31, 35, 36 -> their n pads.
  PI2  TI TPS7A4700 U26: OUT 1 / 20 (SENSE 3 excluded, as the review did) -> C99's v15_ls pad; IN 15 / 16 (not EN 13) ->
       C98's v24_raw pad; NR 14 -> C64's ldo_nr pad; GND 4 / 5 / 7-10 and the thermal pad -> the caps' n_ls pads.

Target (asserted, DECISIONS item 19): every supply-side distance (module VOUT+ / LDO OUT, IN, NR to the cap) is
<= 3.0 mm, and the 100 nF's VOUT- side too. The return sides of the 1210s and of C98 are reported: they join
the IC's ground by the F.Cu pour around it (and vias to the plane), which a centre distance does not describe.
--control asserts the review's stage-18 figures reproduce instead (U41-C104 25.57, U42-C108 26.53, C98 14.03,
C99 15.39, C64 23.06 mm, +-0.05).
"""
import argparse
import json
import math
import sys

import pcbnew

VOUT_N = [str(n) for n in list(range(19, 28)) + [30, 31, 35, 36]]
ROWS = [  # (check, ic, ic supply pins, ic return pins, cap, supply-side asserted, return-side asserted)
    ("PI1 U41 10 uF", "U41", ["28", "29"], VOUT_N, "C104", True, False),
    ("PI1 U41 100 nF", "U41", ["28", "29"], VOUT_N, "C75", True, True),
    ("PI1 U42 10 uF", "U42", ["28", "29"], VOUT_N, "C108", True, False),
    ("PI1 U42 100 nF", "U42", ["28", "29"], VOUT_N, "C82", True, True),
    ("PI2 U26 OUT", "U26", ["1", "20"], ["4", "5", "7", "8", "9", "10", "21"], "C99", True, False),
    ("PI2 U26 IN", "U26", ["15", "16"], ["4", "5", "7", "8", "9", "10", "21"], "C98", True, False),
    ("PI2 U26 NR", "U26", ["14"], ["4", "5", "7", "8", "9", "10", "21"], "C64", True, False),
]
CONTROL = {"PI1 U41 10 uF": 25.57, "PI1 U42 10 uF": 26.53, "PI2 U26 IN": 14.03, "PI2 U26 OUT": 15.39,
           "PI2 U26 NR": 23.06}
LIMIT = 3.0


def xy(p):
    c = p.GetPosition()
    return (pcbnew.ToMM(c.x), pcbnew.ToMM(c.y))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("board")
    ap.add_argument("--json")
    ap.add_argument("--control", action="store_true")
    a = ap.parse_args()
    b = pcbnew.LoadBoard(a.board)
    fps = {f.GetReference(): f for f in b.GetFootprints()}
    out, fails = [], []
    for name, ic, sup, ret, cap, a_sup, a_ret in ROWS:
        ipads = list(fps[ic].Pads())
        cpads = list(fps[cap].Pads())
        snet = next(p.GetNetname() for p in ipads if p.GetNumber() == sup[0])
        rnet = next(p.GetNetname() for p in ipads if p.GetNumber() in ret and p.GetNetname())
        cs = next(p for p in cpads if p.GetNetname() == snet)
        cr = next(p for p in cpads if p.GetNetname() == rnet)
        ds = min((math.dist(xy(p), xy(cs)), p.GetNumber()) for p in ipads if p.GetNumber() in sup)
        dr = min((math.dist(xy(p), xy(cr)), p.GetNumber() or "EP") for p in ipads
                 if p.GetNumber() in ret and p.GetNetname() == rnet)
        row = {"check": name, "ic": ic, "cap": cap, "supply_net": snet, "return_net": rnet,
               "supply_mm": round(ds[0], 2), "supply_pin": ds[1], "return_mm": round(dr[0], 2), "return_pin": dr[1],
               "cap_at": [round(v, 3) for v in xy(fps[cap])], "supply_asserted": a_sup, "return_asserted": a_ret}
        out.append(row)
        print(f"{name}: {ic}.{ds[1]} -> {cap} {snet} {ds[0]:.2f} mm; {ic}.{dr[1]} -> {cap} {rnet} {dr[0]:.2f} mm")
        if a.control:
            if name in CONTROL and abs(ds[0] - CONTROL[name]) > 0.05:
                fails.append(f"control {name}: {ds[0]:.2f} mm, review {CONTROL[name]}")
        else:
            if a_sup and ds[0] > LIMIT:
                fails.append(f"{name}: supply {ds[0]:.2f} mm > {LIMIT}")
            if a_ret and dr[0] > LIMIT:
                fails.append(f"{name}: return {dr[0]:.2f} mm > {LIMIT}")
    res = {"board": a.board, "mode": "control" if a.control else "gate", "limit_mm": LIMIT, "rows": out,
           "failures": fails, "pass": not fails}
    if a.json:
        json.dump(res, open(a.json, "w"), indent=1)
    print(("PASS" if not fails else "FAIL: " + "; ".join(fails)) + (" (control)" if a.control else ""))
    sys.exit(0 if not fails else 1)


main()
