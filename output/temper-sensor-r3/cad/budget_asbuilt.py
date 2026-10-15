"""sensor-r3 C1 cartridge budget, AS MODELLED (copy of ../cartridge_budget.py with the CAD dimensions).

GEOM is read from cartridge_r3.DIM and the CAD solids (disc volume with its chamfer), not typed in. The budget's
own formulas are kept line for line so the numbers are comparable; three as-built additions are labelled:
  (a) C_cap by the budget method (1.1 x disc + bond) is the gated number; an effusivity estimate of the neck,
      inner-tube and fibre that touch the disc (C = e A sqrt(tau_ref), tau_ref = 1 s, the worst-contact time
      constant) is reported beside it as a sensitivity for the firmware's calibratable C_cap.
  (b) G4 cold leak, split as the HANDOFF asks: the as-modelled transfer conductance from thermal_axisym.leak_split()
      (2-D FV of the whole cartridge in the glass/eye; cold = eye air + winding sinks, hot = pan/glass/collar side,
      tracked by the rim NTC) is gated, nominal and with fibre k doubled. The budget's series hand-calc with the
      as-built lengths is printed beside it: it sends everything that enters the neck, inner tube, fibre and leads to
      the shoulder as if the shoulder were cold, so it is the unsplit total into the post (an upper bound on the
      cold part, not a split).
  (c) G6 disc stress over the as-drawn chip pocket = the integral inner support tube's bore (Ø3.4), Roark Table
      11.2 case 16 as in the budget, plus the 1 kg / 100 mm ball-drop stroke argument.
Run: python budget_asbuilt.py -> budget-asbuilt.json
"""
from __future__ import annotations

import json
import sys
from math import log, pi, sqrt
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import cartridge_r3 as C  # noqa: E402

D = C.DIM
SIGMA_SB = 5.670e-8


def disc_volume_mm3():
    return next(p for p in C.r3_cartridge(0.0) if p["name"].endswith("disc_Si3N4"))["shape"].volume


GEOM = dict(
    disc_d=2 * D["disc_r"] * 1e-3, disc_t=D["disc_t"] * 1e-3, contact_d=2 * (D["disc_r"] - D["disc_chamfer"]) * 1e-3,
    pocket_d=2 * D["inner_ri"] * 1e-3,                         # as drawn: the inner support tube's bore
    neck_od=2 * D["neck_ro"] * 1e-3, neck_wall=D["neck_wall"] * 1e-3,
    neck_len_cold=(D["disc_bot"] - D["neck_bot"]) * 1e-3,      # disc underside to the shoulder (first mass below)
    inner_ro=D["inner_ro"] * 1e-3, inner_ri=D["inner_ri"] * 1e-3,
    lead_d=0.08e-3, lead_len=(D["chip_bot_h2"] - D["foot_pot_z"][0]) * 1e-3, n_leads=4,
    capillary_od=2 * D["capillary_r"] * 1e-3, capillary_bore_d=0.18e-3, capillary_len=(D["capillary_z"][1] - D["capillary_z"][0]) * 1e-3,
    cavity_len=(D["disc_bot"] - D["neck_bot"]) * 1e-3, cavity_view_factor=0.3, cavity_fill=True, k_fill=0.04,
    bond_t=D["bond_t"] * 1e-3,
)
MAT = dict(
    si3n4=dict(k=85.0, rho_cp=3250 * 690, flex_MPa=700.0, nu=0.27),
    neck_pi=dict(k=0.35, rho_cp=1430 * 1130),   # Vespel SP-1 sheet: k 0.35, cp 1130, SG 1.43
    lead=dict(k=22.0),                          # manganin (PCB D: 22 W/mK)
    silica=dict(k=1.38),                        # fused silica
    fibre=dict(k=0.04, rho_cp=200 * 1000),      # alumina-silica paper/felt ~200 kg/m3 (ASSUMED density)
    air=dict(k=0.035),
    bond=dict(k=1.7),
)
CHIP = dict(w=1.8e-3, l=2.0e-3, t=0.65e-3, rho_cp=3970 * 880)
T_HOT = 250 + 273.15
GATES = dict(C_cap_max_mJ=45.0, G_cold_max_mW=0.80, tau63_max_s_at_h888=1.20, disc_SF_min_at_20N=2.0,
             contact_area_min_mm2=40.0)
TAU_REF = 1.0


def main():
    g, m = GEOM, MAT
    v_disc = disc_volume_mm3() * 1e-9
    c_disc = m["si3n4"]["rho_cp"] * v_disc
    c_bond = 2.0e6 * CHIP["w"] * CHIP["l"] * g["bond_t"]
    c_cap = 1.1 * c_disc + c_bond                                    # budget method (gated)
    a_neck = pi * (g["neck_od"] - g["neck_wall"]) * g["neck_wall"]
    a_inner = pi * (g["inner_ro"] ** 2 - g["inner_ri"] ** 2)
    e_pi = sqrt(m["neck_pi"]["k"] * m["neck_pi"]["rho_cp"])
    e_fib = sqrt(m["fibre"]["k"] * m["fibre"]["rho_cp"])
    a_fibre_touch = pi * ((g["neck_od"] / 2 - g["neck_wall"]) ** 2 - g["inner_ro"] ** 2) + pi * g["inner_ri"] ** 2 - CHIP["w"] * CHIP["l"]
    c_eff_pi = e_pi * (a_neck + a_inner) * sqrt(TAU_REF)
    c_eff_fib = e_fib * a_fibre_touch * sqrt(TAU_REF)
    c_cap_eff = c_disc + c_bond + c_eff_pi + c_eff_fib
    c_el = CHIP["rho_cp"] * CHIP["w"] * CHIP["l"] * CHIP["t"]
    g_bond = m["bond"]["k"] * CHIP["w"] * CHIP["l"] / g["bond_t"]
    # ---- G4 hand calc (budget series formulas, as-built geometry)
    g_neck = m["neck_pi"]["k"] * a_neck / g["neck_len_cold"]
    g_inner = m["neck_pi"]["k"] * a_inner / g["neck_len_cold"]
    g_leads = g["n_leads"] * m["lead"]["k"] * pi * (g["lead_d"] / 2) ** 2 / g["lead_len"]
    a_cap = pi * (g["capillary_od"] / 2) ** 2 - 4 * pi * (g["capillary_bore_d"] / 2) ** 2
    g_cap = m["silica"]["k"] * a_cap / g["capillary_len"]
    a_under = pi * ((g["neck_od"] - 2 * g["neck_wall"]) / 2) ** 2 - a_inner - pi * (g["capillary_od"] / 2) ** 2
    g_air = g["k_fill"] * a_under / g["cavity_len"]
    g_cold_hand = g_neck + g_inner + g_leads + g_cap + g_air
    # ---- G4 as modelled (2-D FV transfer conductance)
    import thermal_axisym as T
    fv = {}
    for eye in T.EYE:
        for h in (888.0, 21946.0):
            r = T.leak_split(D["proud"], eye, h)
            fv[f"{eye}|h_c {h:.0f}"] = {k: (float(v) if isinstance(v, (int, float)) else v) for k, v in r.items()
                                         if k in ("G_cold_mW_K", "G_hot_mW_K", "G_total_mW_K")}
    sens = T.leak_split(D["proud"], "fry_hold_12.7A", 888.0, {"fibre": 0.08, "ffkm": 0.30})
    fv["sensitivity fibre k 0.08, FFKM k 0.30"] = {k: float(sens[k]) for k in ("G_cold_mW_K", "G_hot_mW_K", "G_total_mW_K")}
    g_cold_fv = max(v["G_cold_mW_K"] for v in fv.values()) * 1e-3
    g_hot_fv = max(v["G_hot_mW_K"] for v in fv.values()) * 1e-3
    g_cold = g_cold_fv
    a_contact = pi * (g["contact_d"] / 2) ** 2
    tau = {f"{h:.0f}": round(c_cap / (h * a_contact + g_cold) + c_el / g_bond, 3) for h in (888.0, 1300.0, 21946.0)}
    tau_eff = {f"{h:.0f}": round(c_cap_eff / (h * a_contact + g_cold) + c_el / g_bond, 3) for h in (888.0, 1300.0, 21946.0)}
    # ---- G6: disc over the as-drawn pocket, Roark Table 11.2 case 16 (simply supported, load on r0)
    a, r0, nu, t = g["pocket_d"] / 2, 0.3e-3, m["si3n4"]["nu"], g["disc_t"]
    sig = {f"{W:g}N": round(3 * W / (2 * pi * t ** 2) * ((1 + nu) * log(a / r0) + 1) / 1e6, 1) for W in (1.8, 20.0)}
    sf20 = m["si3n4"]["flex_MPa"] / sig["20N"]
    a_unb = (D["neck_ro"] - D["neck_wall"]) * 1e-3                    # if the inner tube were absent (neck rim only)
    sig_unbacked = 3 * 20.0 / (2 * pi * t ** 2) * ((1 + nu) * log(a_unb / r0) + 1) / 1e6
    # ball drop: 1 kg steel ball (R from mass) must reach the glass at the bore edge before the post hits its stop
    r_ball = (3 * (1.0 / 7850) / (4 * pi)) ** (1 / 3) * 1e3
    sag = r_ball - sqrt(r_ball ** 2 - D["bore_r"] ** 2)
    stroke_needed = D["proud"] + 0.10 + sag
    stroke_min = D["stroke_hard"] - D["stroke_tol"]                 # hard-stop stack (checks.py G2 chain)
    res = {
        "C_cap_mJ_per_K": round(c_cap * 1e3, 2), "C_disc_mJ_per_K": round(c_disc * 1e3, 2),
        "C_cap_effusivity_estimate_mJ_per_K": {"total": round(c_cap_eff * 1e3, 2), "PI_neck_and_inner_tube": round(c_eff_pi * 1e3, 2),
                                                "fibre_under_disc": round(c_eff_fib * 1e3, 2), "tau_ref_s": TAU_REF},
        "C_el_mJ_per_K": round(c_el * 1e3, 3), "G_bond_W_per_K": round(g_bond, 4),
        "G_into_post_hand_upper_bound_mW_per_K": {"neck": round(g_neck * 1e3, 3), "inner_tube": round(g_inner * 1e3, 3),
                                 "leads_manganin": round(g_leads * 1e3, 3), "lead_capillary_silica": round(g_cap * 1e3, 3),
                                 "cavity_fibre": round(g_air * 1e3, 3), "total": round(g_cold_hand * 1e3, 3)},
        "G_leak_FV_mW_per_K": fv,
        "G_cold_gated_mW_per_K": round(g_cold * 1e3, 3),
        "G_hot_to_collar_and_pan_side_mW_per_K": round(g_hot_fv * 1e3, 3),
        "contact_area_mm2": round(a_contact * 1e6, 1), "tau63_s_by_h": tau, "tau63_s_by_h_with_C_eff": tau_eff,
        "disc_stress_MPa_over_pocket": sig, "disc_SF_at_20N": round(sf20, 2),
        "disc_stress_20N_if_unbacked_to_neck_MPa": round(sig_unbacked, 1),
        "ball_drop": {"ball_R_mm": round(r_ball, 2), "sag_at_bore_edge_mm": round(sag, 3),
                      "stroke_needed_mm": round(stroke_needed, 3), "stroke_to_hard_stop_min_mm": round(stroke_min, 3)},
    }
    gates = {
        "G3 C_cap (budget method)": res["C_cap_mJ_per_K"] <= GATES["C_cap_max_mJ"],
        "G4 cold leak (FV split, worst incl. sensitivity)": res["G_cold_gated_mW_per_K"] <= GATES["G_cold_max_mW"],
        "tau63 at worst modelled contact": tau["888"] <= GATES["tau63_max_s_at_h888"],
        "G6 disc strength over the pocket": sf20 >= GATES["disc_SF_min_at_20N"],
        "G6 ball drop ends on the glass": stroke_min >= stroke_needed,
        "contact area": res["contact_area_mm2"] >= GATES["contact_area_min_mm2"],
    }
    out = {"scope": __doc__.strip(), "geometry": GEOM, "materials": MAT, "gates": GATES, "results": res, "gate_pass": gates,
           "notes": ["C_cap effusivity estimate exceeds 45 mJ/K only if the whole neck/fibre contact participates at "
                     "tau_ref = 1 s; the firmware keeps C_cap calibratable (bench T3).",
                     "G_hot is to nodes the rim NTC tracks (collar/glass under the pan); it is reported for the firmware "
                     "G_leak constant, not gated (HANDOFF G4)."]}
    (HERE / "budget-asbuilt.json").write_text(json.dumps(out, indent=1, default=float) + "\n")
    print(json.dumps(res, indent=1, default=float))
    for k, v in gates.items():
        print(f"{'PASS' if v else 'FAIL'}  {k}")
    return out


if __name__ == "__main__":
    main()
