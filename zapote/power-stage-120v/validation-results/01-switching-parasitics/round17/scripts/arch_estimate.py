#!/usr/bin/env python3
"""Hand estimate of the closure arches' inductance vs arch height h (round 17).

Each closure is a strip (width w: 0.4 mm port sheet, 0.6 mm bridge bar) of
length l between its legs, at height H above a return plane, plus two
vertical 0.6 mm square legs of length equal to the strip's height above
the top copper. The return plane is assumed d below the top copper
surface (d is unknown per closure; it is bracketed).

Strip over plane, per unit length (microstrip in air, Wheeler/Hammerstad):
    u = w/H <= 1:  L' = mu0/(2 pi) * ln(8/u + u/4)
    u >  1:        L' = mu0 / (u + 1.393 + 0.667 ln(u + 1.444))
Leg standing on the plane (with its collinear image): a wire of length 2t
halved:  L_leg = mu0 t/(2 pi) * (ln(4t/r) - 1), r = 0.4473 * 0.6 mm (GMD of
a square). Legs are omitted when t = 0.

The quantity that matters for the extrapolation is the arch part relative
to a flat strip lying on the top copper (h = 0):
    dL(h) = L(h) - L(0).
For each loop this prints dL at h = 1, 2, 3 and what a straight line
(through 1, 2 mm) and a parabola (through 1, 2, 3 mm) would extrapolate to
at h = 0, i.e. the extrapolation error if this model held. Level-1 closures
(gate-source bridges) sit at 2h; the column "left at h=0" must be zero
(it was 2-3 nH when they sat at h + 1 mm, before the round-17 fix).

Mutual coupling between arches (e.g. Q2_GS directly above Q2_DS) is not
modelled; it enters the off-diagonal terms.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

MU0 = 4e-7 * math.pi
LEG_W = 0.6
R_LEG = 0.4473 * LEG_W
LOOPS = {
    "P1_C38": ["P1_C38", "Q2_DS", "Q3_DS", "R5_1_4"],
    "P2_C39": ["P2_C39", "Q2_DS", "Q3_DS", "R5_1_4"],
    "P3_gate_high": ["P3_gate_high", "R10", "Q2_GS"],
    "P4_gate_low": ["P4_gate_low", "R12", "Q3_GS"],
}


def strip_per_mm(w: float, H: float) -> float:
    """nH per mm of a thin strip of width w at height H over a plane."""
    u = w / H
    if u <= 1:
        lp = MU0 / (2 * math.pi) * math.log(8 / u + u / 4)
    else:
        lp = MU0 / (u + 1.393 + 0.667 * math.log(u + 1.444))
    return lp * 1e9 * 1e-3


def leg(t: float) -> float:
    """nH of one vertical leg of length t (mm) standing on the plane."""
    if t <= 0:
        return 0.0
    return MU0 * t * 1e-3 / (2 * math.pi) * (math.log(4 * t / R_LEG) - 1) * 1e9


def arch(cl: dict, h: float, d: float) -> float:
    (ax, ay), (bx, by) = cl["a"], cl["b"]
    span = math.hypot(bx - ax, by - ay) - LEG_W
    w = 0.4 if cl["kind"] == "port" else 0.6
    t = h * (1 + cl.get("level", 0))              # level-1 bridges sit at 2h (round 17 fix)
    return strip_per_mm(w, t + d) * span + 2 * leg(t)


def main() -> None:
    closures = {c["name"]: c for c in json.load(open(Path(__file__).resolve().parent.parent / "closures-legA.json"))}
    out = {}
    for d in (0.5, 1.07):
        print(f"\nreturn plane d = {d} mm below the top copper")
        print(f"{'loop':14s} {'dL(1)':>7s} {'dL(2)':>7s} {'dL(3)':>7s}  {'lin(1,2)->0':>11s} {'quad->0':>8s}  {'left at h=0 (level-1)':>21s}")
        out[str(d)] = {}
        for loop, names in LOOPS.items():
            L = {h: sum(arch(closures[n], h, d) for n in names) for h in (0, 1, 2, 3)}
            dL = {h: L[h] - L[0] for h in (1, 2, 3)}
            lin0 = 2 * dL[1] - dL[2]                 # straight line through h=1,2 evaluated at 0
            quad0 = 3 * dL[1] - 3 * dL[2] + dL[3]    # parabola through 1,2,3 evaluated at 0
            lvl1 = [n for n in names if closures[n].get("level", 0) == 1]
            left = sum(arch(closures[n], 0, d) - closures_flat(closures[n], d) for n in lvl1)
            out[str(d)][loop] = {"dL_nH": {h: round(v, 3) for h, v in dL.items()},
                                 "linear_extrapolation_error_nH": round(lin0, 3),
                                 "quadratic_extrapolation_error_nH": round(quad0, 3),
                                 "level1_arch_left_at_h0_nH": round(left, 3)}
            print(f"{loop:14s} {dL[1]:7.2f} {dL[2]:7.2f} {dL[3]:7.2f}  {lin0:11.2f} {quad0:8.2f}  {left:21.2f}")
    print("RESULT " + json.dumps(out))


def closures_flat(cl: dict, d: float) -> float:
    """The same strip lying flat on the top copper (no legs)."""
    (ax, ay), (bx, by) = cl["a"], cl["b"]
    span = math.hypot(bx - ax, by - ay) - LEG_W
    w = 0.4 if cl["kind"] == "port" else 0.6
    return strip_per_mm(w, d) * span


if __name__ == "__main__":
    main()
