#!/usr/bin/env python3
"""Layer 3, coupling that is on no net: heat, coil field, return-path references, switch-node dv/dt, creepage.

    python3 -I validation-results/13-coupling/scripts/physics.py      (after assign32.py)

No new physics: each term reads an existing model's input or output for the stage-32 board.
* Thermal (B3, 04-board-current-thermal/round5-native21/b3, run c28_h25_p1p0 on board 2fb346dc): the solver's own
  deposited-heat map heat_w (1 mm cells) is attributed to groups - cells under a heat-source part's courtyard to that
  part's group, the rest to the nets of the case's Joule-heated copper (sw_a / sw_b / res_a / coil_feed / leg / bus /
  ac nets) by which copper occupies the cell. Screen: heat of group i deposited within 5 mm and 15 mm of group j's
  courtyards (W), and each group's hottest part from the solved rise map. This is proximity on B3's own heat, not a
  new solve.
* Coil field (02-protection-timing/coil-pickup): OCP Kelvin / comparator pickup on this board (s21b/result-s32.json,
  the scorecard's ocp_pickup_stack_pan60_A) against its 6.5 A gate; CT and LINE_ZC verdicts from PICKUP.md.
* Return-path references (return-path.json of the stage-32 chain): which groups' planes and transfer capacitors each
  fast or slow signal's layer changes lean on; the open changes (> 3 mm or no cap) per group pair.
* dv/dt: copper area of the switching domains (SW_A, SW_B nets) overlapping other domains' copper on the adjacent
  layer (plane-to-plane capacitance proxy, mm2) and same-layer copper within 1 mm, by group.
* Creepage: RES_A (G04) to SELV / PE pairs from the stage-32 res-a-creepage.json, margin over the 12.6 mm floor.
Controls: attributed heat + unattributed = B3's total source watts (balance); the pickup row equals the s32 scorecard;
the return-path open-change count equals the scorecard's 18.
"""
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from scipy import ndimage

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402

B3 = C.VR / "04-board-current-thermal/round5-native21/b3"
SW_DOMAINS = ("SW_A", "SW_B")
STATIC_POWER = {"bus_p", "hv_ret", "leg_ret"}     # DC rails, not dv/dt aggressors or victims of interest


def main():
    ctl = C.Controls()
    sg, so = C.shapely()
    import shapely
    asg = C.load("assignment.json")["assignment"]
    cy = C.courtyards()
    d = C.dump()
    dom, R = C.domains()
    card = json.loads((C.VR / "10-benchmark/scorecard-native21s32.json").read_text())
    pad_refs = defaultdict(set)
    for x in d["primitives"]:
        if x["kind"] == "pad" and x.get("net"):
            r = x["ref"].split(".")[0]
            if r in asg:
                pad_refs[x["net"]].add(r)
    net_groups = {n: sorted({asg[r] for r in rs}) for n, rs in pad_refs.items()}

    # ---------------------------------------------------------------- thermal
    run = json.loads((B3 / "outputs/c28_h25_p1p0.json").read_text())
    ctl.check("B3 c28_h25 run is on the stage-32 board", run["board_sha256"] == C.BOARD_SHA)
    z = np.load(B3 / "outputs/c28_h25_p1p0.npz")
    xs, ys, heat, rise = z["x_mm"], z["y_mm"], z["heat_w"].sum(axis=0), z["rise_k"]
    XX, YY = np.meshgrid(xs, ys, indexing="ij")
    src = json.loads((B3 / "inputs/native21-board-heat-sources-c28.json").read_text())["parts"]
    owner = np.full(heat.shape, -1, int)
    gidx = {g: i for i, g in enumerate(C.GIDS)}
    part_cells = {}
    for p in src:
        r = p["ref"]
        if r not in cy:
            continue
        x0, y0, x1, y1 = cy[r]
        m = (XX >= x0 - 0.5) & (XX <= x1 + 0.5) & (YY >= y0 - 0.5) & (YY <= y1 + 0.5)
        part_cells[r] = m
        owner[m & (owner < 0)] = gidx[asg[r]]
    case_nets = sorted({c.split("-")[0] for c in run["case"].split(",")})
    jnet = {"sw_a": "sw_a", "sw_a_low": "sw_a", "sw_b_high": "sw_b", "sw_b_low": "sw_b", "res_a": "res_a",
            "coil_feed": "coil_feed", "leg_a_18p7": "leg_ret", "leg_b_18p7": "leg_ret", "hv_mixed_a": "hv_ret",
            "hv_mixed_b": "hv_ret", "bus_mixed_q2": "bus_p", "bus_mixed_q5": "bus_p", "ac_n_main": "ac_n_in", "ac_l_main": "ac_l_in"}
    nets_j = sorted({jnet[c] for c in case_nets if c in jnet})
    cu = C.copper_geoms(d, sg, so, nets=set(nets_j))
    netcell = {}
    for n in nets_j:
        g = so.unary_union([v for (nn, L), v in cu.items() if nn == n])
        netcell[n] = shapely.contains_xy(g, XX, YY) | shapely.contains_xy(g.buffer(0.5), XX, YY)
    att = np.zeros((len(C.GIDS),) + heat.shape)
    unatt = 0.0
    for i in range(heat.shape[0]):
        for j in range(heat.shape[1]):
            w = heat[i, j]
            if w <= 0:
                continue
            if owner[i, j] >= 0:
                att[owner[i, j], i, j] += w
                continue
            ns = [n for n in nets_j if netcell[n][i, j]]
            gs = Counter()
            for n in ns:
                for g in net_groups.get(n, []):
                    gs[g] += 1.0 / (len(ns) * len(net_groups[n]))
            if gs:
                for g, f in gs.items():
                    att[gidx[g], i, j] += w * f
            else:
                unatt += w
    tot_att = float(att.sum())
    ctl.check("thermal: attributed + unattributed heat = B3 source watts", abs(tot_att + unatt - run["balance"]["source_w"]) < 1e-3,
              f"{tot_att:.3f} + {unatt:.3f} vs {run['balance']['source_w']:.3f} W")
    heat_by_group = {g: float(att[gidx[g]].sum()) for g in C.GIDS}
    therm = {}
    for R_ in (5.0, 15.0):
        T = {i: {j: 0.0 for j in C.GIDS} for i in C.GIDS}
        for j in C.GIDS:
            m = np.zeros(heat.shape, bool)
            for r in asg:
                if asg[r] == j:
                    x0, y0, x1, y1 = cy[r]
                    m |= (XX >= x0) & (XX <= x1) & (YY >= y0) & (YY <= y1)
            dist = ndimage.distance_transform_edt(~m) * float(xs[1] - xs[0])
            near = dist <= R_
            for i in C.GIDS:
                if i != j:
                    T[i][j] = float(att[gidx[i]][near].sum())
        therm[f"heat_within_{int(R_)}mm_W"] = T
    peak_rise = rise.max(axis=0)
    hottest = {}
    for g in C.GIDS:
        best = None
        for r in asg:
            if asg[r] != g:
                continue
            x0, y0, x1, y1 = cy[r]
            m = (XX >= x0) & (XX <= x1) & (YY >= y0) & (YY <= y1)
            if not m.any():
                continue
            t = float(peak_rise[m].max()) + run["ambient_c"]
            if best is None or t > best[1]:
                best = (r, t)
        hottest[g] = {"ref": best[0], "local_peak_C": best[1]} if best else None

    # ---------------------------------------------------------------- coil field
    pk = json.loads((C.VR / "02-protection-timing/coil-pickup/s21b/result-s32.json").read_text())
    row = pk["rows"]["f60|pan_bars_31kHz_45Apk|base_A|cluster_drawn"]
    ocp = round(row["stack_any_phase_x1p5_A"], 2)
    ctl.check("coil field: OCP pickup row equals the s32 scorecard", ocp == card["performance"]["ocp_pickup_stack_pan60_A"],
              f"{ocp} A")
    field = {
        "source": "coil current (tank, G04 via J2 / J5; coil off board)",
        "victims": {
            "G08": {"loop": "OCP Kelvin + comparator node / threshold loops (R5, R33, R35, C30, C31, U6)",
                    "value_A": ocp, "gate_A": 6.5, "utilisation": round(ocp / 6.5, 3),
                    "parts_A": row["parts_A"], "source_file": "02-protection-timing/coil-pickup/s21b/result-s32.json"},
            "G09": {"loop": "CT comparator loops and LINE_ZC string", "value": "negligible (<= 0.35 A tank-current equivalent, <= 0.6 deg ZC shift; LINE_ZC nA / ns)",
                    "utilisation": 0.0, "source_file": "02-protection-timing/coil-pickup/PICKUP.md lines 9-10 (13b copper; not rerun per stage)"},
        },
        "layout_dependence": "the OCP loop area is set by G08's Kelvin routing and by the In1 ocp_kelvin_p pour, which "
                             "contests In1 with G06's n_ls LS block (patches21.ZONE_WINNERS); stage 28's router re-laid "
                             "ocp_node / ocp_thresh when G10 changed, and the pickup went 4.17 -> 4.78 A (DECISIONS 30)",
    }

    # ---------------------------------------------------------------- return-path references
    rp = json.loads((C.S32_BUILD / "return-path.json").read_text())
    cap_group = {c: asg.get(c) for c in rp["signals"]["transfer_caps"]}
    RP = {i: {j: 0 for j in C.GIDS} for i in C.GIDS}
    RPopen = {i: {j: 0 for j in C.GIDS} for i in C.GIDS}
    rows = []
    n_open = 0
    for n, s in sorted(rp["signals"].items()):
        if not isinstance(s, dict) or "reference_changes" not in s:
            continue
        sg_ = net_groups.get(n, [])
        for c in s["reference_changes"]:
            cg = asg.get(c.get("cap")) if c.get("cap") else None
            pgs = sorted({g for pn in c.get("nets", []) for g in net_groups.get(pn, [])})
            is_open = c.get("mm") is None or c["mm"] > 3.0
            n_open += is_open
            targets = ({cg} if cg else set()) | set()
            for a in sg_:
                for b in targets:
                    if a != b:
                        RP[a][b] += 1
                        if is_open:
                            RPopen[a][b] += 1
            rows.append({"signal": n, "signal_groups": sg_, "at": c.get("at"), "cap": c.get("cap"), "cap_group": cg,
                         "mm": c.get("mm"), "open": is_open, "plane_groups": pgs})
        for t in s.get("plane_crossings", []):
            pass
    ctl.check("return path: open changes equal the s32 scorecard", n_open == card["performance"]["return_path_open_changes"],
              f"{n_open}")
    exp_ret = {n: s["expected_return"] for n, s in rp["signals"].items() if isinstance(s, dict) and "expected_return" in s}
    plane_dep = {}
    for n, e in sorted(exp_ret.items()):
        plane_dep[n] = {"signal_groups": net_groups.get(n, []), "expected_return": e,
                        "return_groups": sorted({g for pn in e for g in net_groups.get(pn, [])})}

    # ---------------------------------------------------------------- dv/dt neighbours
    allg = C.copper_geoms(d, sg, so)
    adjL = {"F.Cu": ["In1.Cu"], "In1.Cu": ["F.Cu", "In2.Cu"], "In2.Cu": ["In1.Cu", "B.Cu"], "B.Cu": ["In2.Cu"]}
    DV = {i: {j: 0.0 for j in C.GIDS} for i in C.GIDS}
    DVsame = {i: {j: 0.0 for j in C.GIDS} for i in C.GIDS}
    victims = defaultdict(float)
    aggr = [(n, L, g) for (n, L), g in sorted(allg.items()) if dom(n) in SW_DOMAINS and n in net_groups]
    vict = [(n, L, g) for (n, L), g in sorted(allg.items()) if dom(n) not in SW_DOMAINS and n in net_groups and n not in STATIC_POWER]
    for na, La, ga in aggr:
        for nv, Lv, gv in vict:
            if Lv in adjL[La]:
                a = ga.intersection(gv).area if ga.bounds[0] <= gv.bounds[2] and gv.bounds[0] <= ga.bounds[2] and ga.bounds[1] <= gv.bounds[3] and gv.bounds[1] <= ga.bounds[3] else 0.0
                s_ = 0.0
            elif Lv == La:
                a = 0.0
                s_ = ga.buffer(3.5).intersection(gv).area if ga.distance(gv) < 3.5 else 0.0
            else:
                continue
            if a <= 0 and s_ <= 0:
                continue
            victims[f"{nv}|{dom(nv)}"] += a
            w = 1.0 / (len(net_groups[na]) * len(net_groups[nv]))
            for i in net_groups[na]:
                for j in net_groups[nv]:
                    if i != j:
                        DV[i][j] += a * w
                        DVsame[i][j] += s_ * w
    top_victims = sorted(victims.items(), key=lambda t: -t[1])[:20]

    # ---------------------------------------------------------------- creepage
    ra = json.loads((C.S32_BUILD / "res-a-creepage.json").read_text())
    cre = []
    CR = {j: 0.0 for j in C.GIDS}
    for p in ra["pairs_under_25mm"]:
        if not isinstance(p, dict):
            continue
        gs = net_groups.get(p["barrier_net"], [])
        cre.append({"layer": p["layer"], "hv_net": p["hv_net"], "hv_groups": net_groups.get(p["hv_net"], []),
                    "barrier_net": p["barrier_net"], "groups": gs, "mm": p["mm"],
                    "floor_mm": p["floor_mm"], "margin_mm": round(p["mm"] - p["floor_mm"], 3), "gated": p.get("gated")})
        for g in gs:
            if p.get("gated") and p["hv_net"] == "res_a":       # the 12.6 mm RES_A outer-layer rows (res_a is G04's own net)
                CR[g] = max(CR[g], 1.0 / max(p["mm"] - p["floor_mm"], 0.1))
    ctl.check("creepage: RES_A outer minimum equals the s32 scorecard",
              abs(min(c["mm"] for c in cre if c["gated"] and c["hv_net"] == "res_a") - card["performance"]["res_a_outer_min_mm"]) < 1e-6)

    out = {
        "board_sha256": C.BOARD_SHA, "method": __doc__.split("Controls:")[0].strip(),
        "thermal": {"b3_run": "c28_h25_p1p0", "source_w": run["balance"]["source_w"], "attributed_w": tot_att, "unattributed_w": unatt,
                    "heat_by_group_W": heat_by_group, **therm, "hottest_part_by_group": hottest, "joule_nets": nets_j},
        "coil_field": field,
        "return_path": {"reference_changes": rows, "pair_changes": RP, "pair_open_changes": RPopen, "open_total": n_open,
                        "transfer_cap_groups": cap_group, "expected_return_planes": plane_dep},
        "dvdt": {"adjacent_layer_overlap_mm2": DV, "same_layer_within_3p5mm_mm2": DVsame,
                 "top_victim_nets_overlap_mm2": top_victims},
        "creepage_res_a": {"pairs": cre, "inverse_margin_by_group": CR},
        "controls": ctl.rows,
    }
    h = C.write("physics.json", out)
    print("physics.json", h[:12])
    ctl.finish()


if __name__ == "__main__":
    main()
