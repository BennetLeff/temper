"""sensor-r3 C1 cartridge budget: the numbers the CAD agent must hold (HANDOFF section A gates).

Edit GEOM from the CAD model and rerun; every gate prints PASS/FAIL and the JSON
records the inputs. Formulas are hand-calc screens (stated per line), not FEA.

Run: python cartridge_budget.py -> cartridge-budget.json
"""
from __future__ import annotations

import json
from math import log, pi
from pathlib import Path

SIGMA_SB = 5.670e-8

# ---- geometry (CAD agent: replace with as-modelled values) ------------------
GEOM = dict(
    disc_d=8.0e-3, disc_t=0.32e-3, contact_d=7.6e-3,          # 0.2 mm edge chamfer
    pocket_d=3.2e-3,                                          # unbacked pocket under the disc for the chip
    neck_od=8.0e-3, neck_wall=0.25e-3, neck_len_cold=6.0e-3,  # neck length from disc to the first COLD sink
    lead_d=0.08e-3, lead_len=20e-3, n_leads=4,                # 4-wire, low-k alloy (constantan-class) first 20 mm
    cavity_len=10e-3, cavity_view_factor=0.3,                 # disc underside to cold cavity end
    cavity_fill=True, k_fill=0.04,                            # alumina-silica fibre / aerogel plug: blocks radiation
    bond_t=0.10e-3,
)
MAT = dict(
    si3n4=dict(k=85.0, rho_cp=3250 * 690, flex_MPa=700.0, nu=0.27),
    neck_pi=dict(k=0.35),          # polyimide (Vespel SP-1 class); PEEK k 0.25 if RTI allows
    lead=dict(k=21.0),             # constantan
    air=dict(k=0.035),
    bond=dict(k=1.7),              # EPO-TEK 930-4 class
)
CHIP = dict(w=1.8e-3, l=2.0e-3, t=0.65e-3, rho_cp=3970 * 880)  # IST P0K1.202
T_HOT = 250 + 273.15
GATES = dict(C_cap_max_mJ=45.0, G_cold_max_mW=0.80, tau63_max_s_at_h888=1.20,
             disc_SF_min_at_20N=2.0, contact_area_min_mm2=40.0)


def main():
    g, m = GEOM, MAT
    c_disc = m["si3n4"]["rho_cp"] * pi * (g["disc_d"] / 2) ** 2 * g["disc_t"]
    c_bond = 2.0e6 * CHIP["w"] * CHIP["l"] * g["bond_t"]
    c_cap = 1.1 * c_disc + c_bond                       # +10 % for the neck rim bonded to the disc
    c_el = CHIP["rho_cp"] * CHIP["w"] * CHIP["l"] * CHIP["t"]
    g_bond = m["bond"]["k"] * CHIP["w"] * CHIP["l"] / g["bond_t"]
    a_neck = pi * (g["neck_od"] - g["neck_wall"]) * g["neck_wall"]
    g_neck = m["neck_pi"]["k"] * a_neck / g["neck_len_cold"]
    g_leads = g["n_leads"] * m["lead"]["k"] * pi * (g["lead_d"] / 2) ** 2 / g["lead_len"]
    a_under = pi * ((g["neck_od"] - 2 * g["neck_wall"]) / 2) ** 2
    if g["cavity_fill"]:
        g_air, g_rad = g["k_fill"] * a_under / g["cavity_len"], 0.0
    else:
        g_air = m["air"]["k"] * a_under / g["cavity_len"]
        g_rad = 4 * 0.9 * SIGMA_SB * T_HOT ** 3 * a_under * g["cavity_view_factor"]
    g_cold = g_neck + g_leads + g_air + g_rad
    a_contact = pi * (g["contact_d"] / 2) ** 2
    tau = {f"{h:.0f}": round(c_cap / (h * a_contact + g_cold) + c_el / g_bond, 3) for h in (888.0, 1300.0, 21946.0)}
    # Disc over the unbacked chip pocket: simply supported circular plate, central load on r0 = 0.3 mm
    # (Roark Table 11.2 case 16): sigma = 3W/(2 pi t^2) [(1+nu) ln(a/r0) + 1].
    a, r0, nu, t = g["pocket_d"] / 2, 0.3e-3, m["si3n4"]["nu"], g["disc_t"]
    sig = {f"{W:g}N": round(3 * W / (2 * pi * t ** 2) * ((1 + nu) * log(a / r0) + 1) / 1e6, 1) for W in (1.8, 20.0)}
    sf20 = m["si3n4"]["flex_MPa"] / sig["20N"]
    res = {
        "C_cap_mJ_per_K": round(c_cap * 1e3, 2), "C_el_mJ_per_K": round(c_el * 1e3, 3), "G_bond_W_per_K": round(g_bond, 4),
        "G_cold_mW_per_K": {"neck": round(g_neck * 1e3, 3), "leads": round(g_leads * 1e3, 3), "cavity_air": round(g_air * 1e3, 3),
                            "cavity_radiation": round(g_rad * 1e3, 3), "total": round(g_cold * 1e3, 3)},
        "contact_area_mm2": round(a_contact * 1e6, 1), "tau63_s_by_h": tau,
        "disc_stress_MPa_over_pocket": sig, "disc_SF_at_20N": round(sf20, 2),
    }
    gates = {
        "G3 C_cap": res["C_cap_mJ_per_K"] <= GATES["C_cap_max_mJ"],
        "G4 cold leak": res["G_cold_mW_per_K"]["total"] <= GATES["G_cold_max_mW"],
        "tau63 at worst modelled contact": tau["888"] <= GATES["tau63_max_s_at_h888"],
        "G6 disc strength": sf20 >= GATES["disc_SF_min_at_20N"],
        "contact area": res["contact_area_mm2"] >= GATES["contact_area_min_mm2"],
    }
    out = {"scope": __doc__.strip(), "geometry": GEOM, "materials": MAT, "gates": GATES, "results": res,
           "gate_pass": gates}
    Path(__file__).with_name("cartridge-budget.json").write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps(res, indent=1))
    for k, v in gates.items():
        print(f"{'PASS' if v else 'FAIL'}  {k}")


if __name__ == "__main__":
    main()
