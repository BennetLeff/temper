#!/usr/bin/env python3
"""Candidate 33 step 1: commutation-loop and switch-node estimates for the six-layer plane plans (screen only).

    python3 loop_screen.py COPPER_DUMP.json PADS_BOARD.json OUT.json [--dump6 COPPER_DUMP6.json]

The cheapest estimator in the repo is task 01 round 1's (`01-switching-parasitics/scripts/loop_inductance.py`):
the plane-pair term L = mu0 * d * length / overlap_width along each straight pad-to-pad power path, only where both
pours overlap, and the through-via term mu0 * h / (2 pi) * (ln(4 h / drill) + 1). Its own status was
PARTIAL_BLOCKED: it does not give the loop total, and the FEM matrices (round 17: native-21 leg A 37.6 nH, leg B
24.5 nH parallel commutation loop at the coarse reference, FINDINGS M11) are the numbers of record. This script uses
the same formulas, on the stage-32 fills (the plan view does not change in phase A), to compare plans:

  * plane-pair term of each power path for the bus_p / hv_ret (leg_ret) pair, at the pair's dielectric gap in each
    plan: 4L 0.5 mm core; plan A In1 / In2 0.30 mm core; plan B In1 / In4 0.953 mm (core + In2 + prepreg + In3 + core);
  * one power via's term from F.Cu to each plane of the pair (the film caps and the TO-247 pins reach the planes
    through pins and vias);
  * switch-node capacitance: outer-layer sw_a / sw_b pours over the nearest inner pour of another net
    (C = eps0 * eps_r * A / d, plan-view overlap of the fills).
With --dump6, the six-layer board's own dump is used for its plan-A rows (the as-routed fills) instead of the
stage-32 fills.

Everything here is a screen [ESTIMATE]: the plane-pair and via terms are a fraction of the FEM loop (package, film
cap ESL, pin and spreading terms are not modelled), so the FEM figure is restated only as "the modelled terms change
by X nH"; a new FEM extraction on the six-layer copper is the verification.
"""
import json
import math
import sys
from collections import defaultdict

from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union

MU0_NH_PER_MM = 4 * math.pi * 1e-7 * 1e6        # nH per mm (mu0 in nH/mm)
EPS0_PF_PER_MM = 8.854e-3                       # pF per mm
POWER_PATHS = {   # loop_inductance.py round 1 (C38-C41 film row, Q2 / Q5 drains, Q3 / Q6 sources, R5 shunt)
    "A_C38_bus_to_Q2": ("C38.1", "Q2.2", "bus_p", "hv_ret"),
    "A_C39_bus_to_Q2": ("C39.1", "Q2.2", "bus_p", "hv_ret"),
    "A_Q3_source_to_R5": ("Q3.3", "R5.1", "leg_ret", "bus_p"),
    "A_R5_to_C38_return": ("R5.4", "C38.2", "hv_ret", "bus_p"),
    "A_R5_to_C39_return": ("R5.4", "C39.2", "hv_ret", "bus_p"),
    "B_C40_bus_to_Q5": ("C40.1", "Q5.2", "bus_p", "hv_ret"),
    "B_C41_bus_to_Q5": ("C41.1", "Q5.2", "bus_p", "hv_ret"),
    "B_Q6_source_to_R5": ("Q6.3", "R5.1", "leg_ret", "bus_p"),
    "B_R5_to_C40_return": ("R5.4", "C40.2", "hv_ret", "bus_p"),
    "B_R5_to_C41_return": ("R5.4", "C41.2", "hv_ret", "bus_p"),
}
# plan -> (layer of bus_p, layer of hv_ret / leg_ret, gap between them mm, F.Cu-to-plane gaps mm, eps_r of the pair gap)
PLANS = {
    "4L-s32": {"bus": "In2.Cu", "ret": "In1.Cu", "gap": 0.5, "f_to": {"In1.Cu": 0.4355, "In2.Cu": 0.4355 + 0.061 + 0.5},
               "outer_gap": {"F.Cu": [("In1.Cu", 0.4355, 4.29), ("In2.Cu", 0.9965, 4.37)],
                             "B.Cu": [("In2.Cu", 0.4355, 4.29), ("In1.Cu", 0.9965, 4.37)]}},
    "6L-A": {"bus": "In2.Cu", "ret": "In1.Cu", "gap": 0.30, "f_to": {"In1.Cu": 0.2215, "In2.Cu": 0.2215 + 0.061 + 0.30},
             "outer_gap": {"F.Cu": [("In1.Cu", 0.2215, 3.91), ("In2.Cu", 0.5825, 4.2)],
                           "B.Cu": [("In4.Cu", 0.2215, 3.91), ("In3.Cu", 0.5825, 4.2), ("In2.Cu", 0.8745, 4.15)]}},
    "6L-B": {"bus": "In4.Cu", "ret": "In1.Cu", "gap": 0.30 + 0.061 + 0.231 + 0.061 + 0.30,
             "f_to": {"In1.Cu": 0.2215, "In4.Cu": 0.2215 + 0.061 + 0.30 + 0.061 + 0.231 + 0.061 + 0.30},
             "outer_gap": {"F.Cu": [("In1.Cu", 0.2215, 3.91), ("In2.Cu", 0.5825, 4.2)],
                           "B.Cu": [("In4.Cu", 0.2215, 3.91), ("In3.Cu", 0.5825, 4.2)]}},
}
VIA_DRILL = 0.3          # the standard 0.6 / 0.3 via (stage 32)


def zones(d, remap=None):
    out = defaultdict(list)
    for z in d["zones"]:
        if len(z["pts"]) > 2:
            p = Polygon(z["pts"], [h for h in z["holes"] if len(h) > 2]).buffer(0)
            lay = (remap or {}).get(z["layer"], z["layer"])
            out[(z["net"], lay)].append(p)
    return {k: unary_union(v) for k, v in out.items()}


def width(poly, p, normal):
    if not poly.covers(Point(p)):
        return 0.0
    line = LineString([(p[0] - 100 * normal[0], p[1] - 100 * normal[1]), (p[0] + 100 * normal[0], p[1] + 100 * normal[1])])
    cut = poly.intersection(line)
    parts = [cut] if cut.geom_type == "LineString" else list(getattr(cut, "geoms", []))
    return max((q.length for q in parts if q.distance(Point(p)) < 1e-6), default=0.0)


def path_term(a, b, overlap, gap):
    length = math.dist(a, b)
    u = ((b[0] - a[0]) / length, (b[1] - a[1]) / length)
    n = (-u[1], u[0])
    count = math.ceil(length / 0.5)
    step = length / count
    ws = [width(overlap, (a[0] + (i + 0.5) * step * u[0], a[1] + (i + 0.5) * step * u[1]), n) for i in range(count)]
    cov = [w for w in ws if w > 0]
    return {"length_mm": round(length, 2), "covered_mm": round(len(cov) * step, 2),
            "covered_nH": round(sum(MU0_NH_PER_MM * gap * step / w for w in cov), 4) if cov else 0.0}


def via_nh(h):
    return MU0_NH_PER_MM * h / (2 * math.pi) * (math.log(4 * h / VIA_DRILL) + 1)


def main():
    dump, pads_path, out = sys.argv[1:4]
    dump6 = sys.argv[sys.argv.index("--dump6") + 1] if "--dump6" in sys.argv else None
    d4 = json.load(open(dump))
    pads = {f"{p['ref']}.{p['pad']}": (p["x"], p["y"]) for p in json.load(open(pads_path))}
    res = {"inputs": {"dump": dump, "pads": pads_path, "dump6": dump6}, "method": __doc__.split("\n\n")[1], "plans": {}}
    for name, pl in PLANS.items():
        if name == "6L-B":
            z = zones(d4, {"In2.Cu": "In4.Cu"})
        elif name == "6L-A" and dump6:
            z = zones(json.load(open(dump6)))
        else:
            z = zones(d4)
        bus = z.get(("bus_p", pl["bus"]))
        pair = {r: bus.intersection(z[(r, pl["ret"])]) for r in ("hv_ret", "leg_ret") if (r, pl["ret"]) in z}
        paths, tot = {}, defaultdict(float)
        for k, (a, b, n1, n2) in POWER_PATHS.items():
            if a not in pads or b not in pads:
                paths[k] = {"missing_pad": [x for x in (a, b) if x not in pads]}
                continue
            ret = n2 if n1 == "bus_p" else n1
            paths[k] = path_term(pads[a], pads[b], pair[ret], pl["gap"])
            tot[k[0]] += paths[k]["covered_nH"]
        # switch-node overlap with the nearest inner pour of another net (fills, plan view)
        cap = {}
        for outer, stack in pl["outer_gap"].items():
            for sw in ("sw_a", "sw_b"):
                s = z.get((sw, outer))
                if s is None:
                    continue
                left = s                       # the part of the pour not yet over a nearer plane
                for inner, gap, er in stack:
                    for (net, lay), g in sorted(z.items()):
                        if lay == inner and net != sw:
                            ov = left.intersection(g)
                            if ov.area > 0.01:
                                cap[f"{sw} {outer} / {net} {inner}"] = {"mm2": round(ov.area, 1), "gap_mm": gap,
                                                                        "pF": round(EPS0_PF_PER_MM * er * ov.area / gap, 2)}
                    covered = unary_union([g for (net, lay), g in z.items() if lay == inner])
                    left = left.difference(covered)
        res["plans"][name] = {"pair_gap_mm": round(pl["gap"], 4), "paths": paths,
                              "plane_pair_term_nH_by_leg": {k: round(v, 3) for k, v in tot.items()},
                              "via_term_nH": {lay: round(via_nh(h), 4) for lay, h in pl["f_to"].items()},
                              "switch_node_overlap": cap,
                              "switch_node_pF_total": {sw: round(sum(v["pF"] for k, v in cap.items() if k.startswith(sw)), 2)
                                                       for sw in ("sw_a", "sw_b")}}
    base = res["plans"]["4L-s32"]
    for name, r in res["plans"].items():
        r["delta_vs_4L_nH"] = {leg: round(r["plane_pair_term_nH_by_leg"].get(leg, 0) - base["plane_pair_term_nH_by_leg"].get(leg, 0), 3)
                               for leg in ("A", "B")}
        print(name, "pair gap", r["pair_gap_mm"], "plane-pair term (nH) A/B", r["plane_pair_term_nH_by_leg"],
              "delta", r["delta_vs_4L_nH"], "via F->planes", r["via_term_nH"], "sw pF", r["switch_node_pF_total"])
    json.dump(res, open(out, "w"), indent=1)


if __name__ == "__main__":
    main()
