#!/usr/bin/env python3
"""Board-face h -> enclosure terms, on the jet lane's own correlation (temper-8d airflow-r1 delivery.py,
'parallel_flow_alternative'; air properties of R43 coil_thermal.py).

    python3 -I enclosure.py            -> ../results/enclosure.json, prints the tables

Parallel flow over a face, from its leading edge, over the flow length L (average Nu):
  laminar          Nu_L = 0.664 Re_L^0.5 Pr^1/3      (smooth plate; an upper bound on the velocity needed)
  fully turbulent  Nu_L = 0.037 Re_L^0.8 Pr^1/3      (boundary layer tripped from the leading edge - a component-
                                                      populated board; delivery.py's headline figure)
h_forced = the B3 h (no natural-convection or radiation credit on top, as delivery.py: h_top = max(10, h)).
Flow = v x (width across the flow) x (free height over the face). Bulk air rise along the board = Q_air / (rho cp Vdot),
Q_air = the solve's convection + body-to-air heat (run-file balance).
Jets (for comparison with airflow-r1): Martin (1977) round-nozzle array x 0.6 design factor - not re-derived here; the
jet lane's delivery.json numbers are quoted in results.md.
"""
from __future__ import annotations

import json
from pathlib import Path

K_AIR, NU, PR, RHO, CP, CFM = 0.0285, 1.8e-5, 0.71, 1.09, 1005.0, 4.719e-4


def v_for_h(h, L):
    pr3 = PR ** (1 / 3)
    re_l = (h * L / (0.664 * K_AIR * pr3)) ** 2
    re_t = (h * L / (0.037 * K_AIR * pr3)) ** 1.25
    return re_l * NU / L, re_t * NU / L


# flow paths: (name, L along the flow [m], width across the flow [m], faces)
PATHS = {
    "hot corner, along x (enter at the x 0 edge), 125 mm run, 90 mm wide": (0.125, 0.090),
    "hot corner, along y, 90 mm run, 125 mm wide": (0.090, 0.125),
    "corner + tank path along x, 195 mm run, 120 mm wide": (0.195, 0.120),
    "whole board along x, 290 mm run, 190 mm wide": (0.290, 0.190),
    "whole board along y, 190 mm run, 290 mm wide": (0.190, 0.290),
}
GAPS_MM = (10.0, 25.0)       # free height over a face: 10 mm (a duct floor close over the SMD field) .. 25 mm (over PS2's 24 mm body)


def table(h, q_air_w, faces):
    out = {}
    for name, (L, W) in PATHS.items():
        vl, vt = v_for_h(h, L)
        row = {"L_mm": L * 1e3, "width_mm": W * 1e3, "faces": faces, "v_turbulent_m_s": round(vt, 2),
               "v_laminar_m_s": round(vl, 2)}
        for g in GAPS_MM:
            q = vt * W * g * 1e-3 * faces
            row[f"flow_cfm_turb_gap{int(g)}"] = round(q / CFM, 1)
            row[f"bulk_rise_K_gap{int(g)}"] = round(q_air_w / (RHO * CP * q), 1)
        out[name] = row
    return out


def main():
    here = Path(__file__).resolve().parent
    an = json.loads((here.parent / "results/analysis.json").read_text())
    res = {}
    for mode, faces in (("uniform", 2), ("top", 1), ("zone", 1)):
        for key, t in an["modes"].get(mode, {}).items():
            h = t["all"]["h_pass"]
            if h is None:
                continue
            q = t["points"][f"{h:g}"]["balance"]
            q_air = q["convection_w"] + q["body_air_w"]
            res[f"{mode}:{key}"] = {"h": h, "h_x1.2": round(1.2 * h, 1), "q_air_w": round(q_air, 2),
                                    "at_h": table(h, q_air, faces), "at_1.2h": table(1.2 * h, q_air, faces)}
    # base face flow under the airflow-r1 jet strip (jetmix cases): both faces, h 12-20
    res["jetmix_base"] = {f"h{h}": table(h, 29.9, 2) for h in (12, 15, 16, 17, 18, 20, 24)}
    (here.parent / "results/enclosure.json").write_text(json.dumps(res, indent=1) + "\n")
    for k, r in res["jetmix_base"].items():
        print(f"jetmix base {k}: " + "; ".join(f"{nm[:24]} v_t {row['v_turbulent_m_s']} v_l {row['v_laminar_m_s']} "
                                              f"CFM10 {row['flow_cfm_turb_gap10']}" for nm, row in r.items()))
    for k, r in res.items():
        if "c28" not in k or k == "jetmix_base":
            continue
        print(f"\n{k}: h {r['h']} (x1.2 {r['h_x1.2']}), Q_air {r['q_air_w']} W")
        for nm, row in r["at_h"].items():
            r2 = r["at_1.2h"][nm]
            print(f"  {nm[:58]:58} v_t {row['v_turbulent_m_s']:5.2f} ({r2['v_turbulent_m_s']:5.2f}) v_l {row['v_laminar_m_s']:5.2f} | "
                  f"CFM gap10 {row['flow_cfm_turb_gap10']:5.1f} gap25 {row['flow_cfm_turb_gap25']:5.1f} | "
                  f"rise {row['bulk_rise_K_gap10']}/{row['bulk_rise_K_gap25']} K")


if __name__ == "__main__":
    main()
