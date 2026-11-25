#!/usr/bin/env python3
"""Shrink options for the native-21 power board: area, indicative outline and a lumped thermal check.

    python3 power_shrink_options.py   (after power_board_area.py) -> results/power_shrink_options.json

ESTIMATES, NOT LAYOUTS. Every option is an area budget built from measured s53 numbers
(results/power_area.json) plus explicit assumptions written into ASSUME below and into each option's
record. No option was placed, routed or solved in B3.

Area model per option:
  cut-only   = s53 area - territory of every part that leaves + territory of every part that is added.
               (territory = the part's courtyard plus the board nearest to it; power_board_area.py)
  repacked   = cut-only - RECOVER x (empty, copper-free, non-moat area left in kept territories).
  width140   = repacked / 140 mm (the depth the D-36 band allows, RELAYOUT-REQUIREMENTS L11), an
               indicative rectangle only.

Thermal model (first-order, lumped, NOT B3):
  The s53 release solve (c17.5_h10, bay 61 C, h 10) convects Q = 13.32 W from both faces of the board.
  Each kept territory's share of that duty is apportioned by its parts' pad-copper rise in the same solve
  (probe pad_mean - 50 C model base) x area; the apportionment overshoots the solve's total by about 11 %
  and is used for shares only. If an option removes convective duty share c (fraction) and board heat q
  (W), the remaining area must carry (Q - q) with (1 - c) of the capacity, so its rise scales by
     F = ((Q - q) / Q) / (1 - c)      at the same h.
  Release-row hit, two estimates (neither is a bound):
     low  = (F - 1) x 14.75 K   the board-mean rise Q / (2 h A) at s53
     high = (F - 1) x 27.7 K    R10's far-field heat terms (s43 heat attribution: 47.0 K heat - 19.3 K R_on)
  against the +1.3 K release margin (margins.json, binding row R10). h needed to restore F = 1 is
  h_req = 10 x F (W/m2K), to be compared with DECISIONS 66's h >= 16 for 28 A.
"""
from __future__ import annotations

import json
from pathlib import Path

import power_board_area as pba

HERE = Path(__file__).resolve().parent
RES = HERE.parent / "results"
UNIT = pba.UNIT
B3 = UNIT / "validation-results/04-board-current-thermal/round5-native21/b3-ratings"
RUN = B3 / "runs/c17.5_h10_p0p25.json"
MARGINS = B3 / "margins.json"
CTRL_PCB = Path("/Users/bennet/Desktop/temper/worktrees/ctrl-j13/zapote/controller/pcb/controller-routed.kicad_pcb")

ASSUME = {
    "RECOVER": 0.5,          # share of the empty (no copper, no courtyard, non-moat) area a re-layout recovers
    "RECOVER_RANGE": (0.3, 0.7),
    "DEPTH_MM": 140.0,       # D-36 band depth (RELAYOUT-REQUIREMENTS L11)
    "TAMB_MODEL_C": 50.0,    # B3 run files are solved on a 50 C base (b3_ratings_gate.py TAMB_MODEL_C)
    "R10_FAR_K": 47.0 - 19.3,  # s43 heat attribution README section 3, R10 terminal row: heat 47.0 K, R_on 19.3 K
    "TERRITORY_PER_COURTYARD_ADDED": 2.0,  # an added connector costs ~2x its courtyard (s53 J1/J3/J4: 1.9-6.5x)
    "QDPAK_COURTYARD_MM": (15.10 + 2.0, 21.06 + 2.0),  # PG-HDSOP-22 E max x H max + 1 mm courtyard each side
    "CTRL_PACKING": (0.30, 0.45),  # courtyard / area for the controller block once merged (its own board: 0.26)
}


def main():
    A = json.loads((RES / "power_area.json").read_text())
    run = json.loads(RUN.read_text())
    margins = json.loads(MARGINS.read_text())
    assert run["board_sha256"] == A["board_sha256"], "B3 run is not on the s53 board"
    parts = {p["ref"]: p for p in A["parts"]}
    A0 = A["board_area_mm2"]
    Q = run["balance"]["convection_w"]
    h0 = run["h"]
    dT_mean = Q / (2 * h0 * A0 * 1e-6)
    rel = [r for r in margins["cases"]["c17.5_h10"] if r.get("gated")]
    rel.sort(key=lambda r: r["margin_k"])
    margin0 = rel[0]["margin_k"]

    # board heat per part: watts into the model minus what leaves through the body to air
    heat = {p["ref"]: p["watts_into_model"] - p.get("body_air_w", 0.0) for p in run["parts"]}
    # convective duty share per part territory (apportionment)
    pr = run["probes"]
    duty = {}
    for ref, p in parts.items():
        if p["territory_mm2"] > 0 and ref in pr:
            duty[ref] = 2 * h0 * p["territory_mm2"] * 1e-6 * (pr[ref]["pad_mean_c"] - ASSUME["TAMB_MODEL_C"])
    duty_tot = sum(duty.values())
    moat_mm2 = A["moat_territory_mm2"]

    def kept_empty(removed):
        return sum(p["territory_empty_mm2"] for r, p in parts.items() if r not in removed)

    def thermal(removed, extra_heat_w=0.0):
        q = sum(heat.get(r, 0.0) for r in removed) - extra_heat_w
        c = sum(duty.get(r, 0.0) for r in removed) / duty_tot
        F = ((Q - q) / Q) / (1 - c)
        return {"board_heat_removed_w": round(q, 3), "duty_share_removed": round(c, 4), "F": round(F, 4),
                "release_margin_low_est_k": round(margin0 - (F - 1) * dT_mean, 2),
                "release_margin_high_est_k": round(margin0 - (F - 1) * ASSUME["R10_FAR_K"], 2),
                "h_to_restore_w_m2k": round(h0 * F, 1),
                "h_for_28A_lumped_w_m2k": round(16.0 * F, 1)}  # s53 needs h >= 16 at 28 A (review-packet-s53 README:113)

    def option(name, removed, added_mm2=0.0, extra_heat_w=0.0, note="", also_remove_area=0.0, relocated=()):
        removed = set(removed)
        missing = removed - set(parts)
        assert not missing, missing
        terr = sum(parts[r]["territory_mm2"] for r in removed)
        cut = A0 - terr - also_remove_area + added_mm2
        empty = kept_empty(removed | set(relocated))
        rep = cut - ASSUME["RECOVER"] * empty
        rng = [round(cut - k * empty, 1) for k in ASSUME["RECOVER_RANGE"][::-1]]
        return {"name": name, "removed_refs": sorted(removed), "removed_territory_mm2": round(terr, 1),
                "also_removed_area_mm2": round(also_remove_area, 1), "added_mm2": round(added_mm2, 1),
                "cut_only_mm2": round(cut, 1), "repacked_mm2": round(rep, 1), "repacked_range_mm2": rng,
                "kept_empty_mm2": round(empty, 1),
                "repacked_pct_of_s53": round(100 * rep / A0, 1),
                "width_at_140_mm": round(rep / ASSUME["DEPTH_MM"], 1),
                "thermal_lumped": thermal(removed, extra_heat_w), "note": note}

    opts = []
    # O0: baseline, re-layout of the same circuit only (recover empty area)
    opts.append(option("O0 same circuit, re-laid (recover empty area only)", []))

    # O1: drop the SELV tongue (x 0-91, y 140-190); J4 and its 6 small parts move into the main body's SELV island
    tongue = [r for r, p in parts.items() if p["y"] > 140 and p["block"] != "mech_test"]
    tongue_area = 91.0 * 50.0
    tongue_terr = sum(parts[r]["territory_mm2"] for r in tongue)
    # the tongue parts are re-added inside the main body at 2x their courtyard
    readd = ASSUME["TERRITORY_PER_COURTYARD_ADDED"] * sum(parts[r]["courtyard_mm2"] for r in tongue)
    o1 = option("O1 drop the SELV tongue (290 x 140 rectangle)", [], added_mm2=readd, also_remove_area=tongue_area,
                relocated=tongue,
                note="tongue parts " + ", ".join(sorted(tongue)) + f" (territory {tongue_terr:.0f} mm2) move into the main body")
    o1["thermal_lumped"] = thermal(tongue)  # same parts, same heat; their duty share leaves with the tongue
    opts.append(o1)

    # O2: inlet module: mains entry, EMI filter, fuse, MOV, PE branch, blower AC tap, PS2 and its TCO loop leave the board
    inlet = ["J1", "F1", "RV1", "C1", "C2", "L1", "C3", "C4", "R1", "R2", "J6", "F2", "R130", "J11", "PS2", "J3"]
    # what comes back: a 2-pole L_FILT / N_FILT input terminal (J1 class) and a 2-pin V24_RAW / N_LS input (J3 class)
    add2 = ASSUME["TERRITORY_PER_COURTYARD_ADDED"] * (parts["J1"]["courtyard_mm2"] + parts["J3"]["courtyard_mm2"])
    opts.append(option("O2 inlet module: EMI + fuse + MOV + PS2 + blower tap off-board", inlet, added_mm2=add2,
                       note="adds back one J1-class 2-pole terminal and one J3-class 2-pin gate-supply input"))

    # O1 + O2
    o12 = option("O1+O2 tongue dropped and inlet module", inlet + tongue, added_mm2=add2 + readd,
                 also_remove_area=tongue_area - tongue_terr)
    o12["thermal_lumped"] = thermal(inlet + tongue)
    o12["note"] = "tongue parts re-added in the main body at 2x courtyard; inlet parts as O2"
    opts.append(o12)

    # O3: controller merge (from the power-board side)
    cfps = [pba.parse_fp(f) for f in pba.split_footprints(CTRL_PCB.read_text())]
    c_cy = sum(pba.poly_area(p) for f in cfps for _, p in f["polys"])
    c_j4 = sum(pba.poly_area(p) for f in cfps if f["ref"] == "J4" for _, p in f["polys"])
    c_body = c_cy - c_j4
    lo, hi = (round(c_body / ASSUME["CTRL_PACKING"][1], 1), round(c_body / ASSUME["CTRL_PACKING"][0], 1))
    j4_terr = parts["J4"]["territory_mm2"]
    o3 = {"name": "O3 merge the controller into the SELV zone", "controller_pcb": str(CTRL_PCB),
          "controller_footprints": len(cfps), "controller_courtyard_mm2": round(c_cy, 1),
          "controller_J4_courtyard_mm2": round(c_j4, 1),
          "controller_board_mm2": 206 * 76, "controller_own_packing": round(c_cy / (206 * 76), 3),
          "added_mm2_range": [lo, hi], "power_J4_territory_mm2": j4_terr,
          "merged_mm2_range": [round(A0 - j4_terr + lo, 1), round(A0 - j4_terr + hi, 1)],
          "merged_on_O1O2_mm2_range": [round(o12["repacked_mm2"] + lo, 1), round(o12["repacked_mm2"] + hi, 1)],
          "two_boards_today_mm2": A0 + 206 * 76,
          "note": "power board grows; the system loses one board, two J4 headers and the harness"}
    opts.append(o3)

    # O4: QDPAK top-side-cooled FETs (IPDQ65R017CFD7A), footprint delta only
    qx, qy = ASSUME["QDPAK_COURTYARD_MM"]
    fets = ["Q2", "Q3", "Q5", "Q6"]
    d_cy = 4 * qx * qy - sum(parts[r]["courtyard_mm2"] for r in fets)
    opts.append({"name": "O4 QDPAK top-side-cooled FETs", "qdpak_courtyard_each_mm2": round(qx * qy, 1),
                 "to247_courtyard_each_mm2": parts["Q2"]["courtyard_mm2"], "courtyard_delta_mm2": round(d_cy, 1),
                 "courtyard_delta_pct_of_s53": round(100 * d_cy / A0, 2),
                 "note": "area roughly neutral (+courtyard); value is freedom from the rear-edge row (L13) and the edge sink keep-out (L14)"})

    # O5: resonant bank: what the bank occupies today
    bank = ["C21", "C22", "C23", "C151", "C152"]
    opts.append({"name": "O5 denser resonant bank", "bank_courtyard_mm2": round(sum(parts[r]["courtyard_mm2"] for r in bank), 1),
                 "bank_territory_mm2": round(sum(parts[r]["territory_mm2"] for r in bank), 1),
                 "bank_pct_of_s53": round(100 * sum(parts[r]["territory_mm2"] for r in bank) / A0, 1),
                 "note": "upper bound on the gain: the whole bank territory; a realistic 2-3 larger caps saves a fraction of it"})

    # O6: the binding row's own lever. Gate formula (b3_ratings_gate.py line 404): limit = 155 - 85 P / (0.8 P_rated);
    # R10 is the UniRoyal 25121WF, 1 W at 70 C (gate lines 108-112). A 2 W-rated part at the same P, or two 1 W parts
    # sharing it, moves the limit; then the next release rows bind.
    p_on = 0.217
    lim1 = 155.0 - 85.0 * p_on / (0.8 * 1.0)
    lim2 = 155.0 - 85.0 * p_on / (0.8 * 2.0)
    nxt = [r for r in rel if not r["item"].startswith(("R10", "R12", "R18", "R20"))][:3]
    f12 = o12["thermal_lumped"]["F"]
    opts.append({"name": "O6 R_on 2 W class (or 2 x 1 W in parallel)", "limit_1w_c": round(lim1, 1), "limit_2w_c": round(lim2, 1),
                 "r10_margin_gain_k_from_limit_only": round(lim2 - lim1, 1),
                 "release_rows_by_margin": [{"item": r["item"][:80], "margin_k": r["margin_k"]} for r in rel[:6]],
                 "next_binding_rows_without_r_on": [{"item": r["item"][:80], "margin_k": r["margin_k"]} for r in nxt],
                 "on_O1O2_next_row_low_high_k": [round(nxt[0]["margin_k"] - (f12 - 1) * dT_mean, 2),
                                                 round(nxt[0]["margin_k"] - (f12 - 1) * ASSUME["R10_FAR_K"], 2)],
                 "note": "limit change only; the part's own temperature also falls with 2 x 1 W (half the heat each), not credited"})

    out = {"assumptions": ASSUME, "board_sha256": A["board_sha256"], "s53_area_mm2": A0,
           "b3_run": str(RUN), "b3_convection_w": round(Q, 3), "h": h0,
           "board_mean_rise_k": round(dT_mean, 2), "release_margin_k": margin0, "release_binding_row": rel[0]["item"],
           "duty_apportionment_w_sum": round(duty_tot, 2), "duty_overshoot_pct": round(100 * (duty_tot / Q - 1), 1),
           "duty_share_by_block": {b: round(sum(v for r, v in duty.items() if parts[r]["block"] == b) / duty_tot, 3)
                                   for b in sorted({p["block"] for p in parts.values()})},
           "moat_territory_mm2": moat_mm2, "empty_not_moat_mm2": A["empty_not_moat_mm2"],
           "options": opts}
    (RES / "power_shrink_options.json").write_text(json.dumps(out, indent=1))
    print(json.dumps({k: v for k, v in out.items() if k != "options"}, indent=1))
    for o in opts:
        print(json.dumps({k: v for k, v in o.items() if k != "removed_refs"}))


if __name__ == "__main__":
    main()
