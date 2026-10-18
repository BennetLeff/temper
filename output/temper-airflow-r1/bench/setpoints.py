#!/usr/bin/env python3
"""Jet bench set-points: which manifold pressure in the rig stands for which blower drive in the product.

    python3 setpoints.py           # seconds; imports ../delivery.py read-only -> setpoints.json

Why manifold pressure. The rig has no sink or coil branch and no bay vent, so blower volts do not map to jet flow.
What carries over is the jet box itself: the same holes in the same floor have the same discharge coefficient Cd,
so a jet's exit velocity follows the manifold-to-channel pressure, v = Cd sqrt(2 dp / rho), in rig and product
alike. Matching Reynolds number (properties at the film temperature) then gives the rig pressure for each product
drive with Cd cancelling:
    dp_rig = dp_prod x (rho_rig / rho_prod) x (nu_rig / nu_prod)^2
dp_prod is delivery.py's own jet-orifice drop at that drive, rho/2 (q / (Cd a_jets))^2 with its q and Cd 0.65. A
different real Cd changes dp_prod only weakly (the jets take ~80 % of the branch drop): the Cd 0.58 / 0.72 columns
rerun delivery's network to show by how much.

Product film temperature: jet air 50 C (D-18 hood air, delivery JET_AIR_C) and the strip at the FET-row maximum of
the c28 jet run at h 100 (runs/c28_jet_h100_bay59p5_p0p5.json). Rig: room-temperature jets, plate 25 K above them.
"""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import math
import sys
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
AIRFLOW = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(AIRFLOW))
from air import props  # noqa: E402

with contextlib.redirect_stdout(io.StringIO()):
    import delivery as dl  # noqa: E402  (read-only: functions and constants only; its main() is not run)

DRIVES = [round(dl.FLOOR, 3), 0.5, 0.55, 0.6, 0.7, 0.8, 1.0]
NAMED = {"floor": round(dl.FLOOR, 3), "drive_0.55": 0.55, "full": 1.0}
ROOM_C = [18.0, 21.0, 24.0, 27.0, 30.0]
DT_RIG = 25.0
RUN_C28 = AIRFLOW / "runs/c28_jet_h100_bay59p5_p0p5.json"


def a_jets(jet=dl.JET):
    return jet["N"] * math.pi / 4 * (jet["D_mm"] * 1e-3) ** 2


def jet_dp(q, cd, rho):
    return rho / 2 * (q / (cd * a_jets())) ** 2


def product_film_c():
    t_s = json.loads(RUN_C28.read_text())["fet_row_max_c"]
    return t_s, (t_s + dl.JET_AIR_C) / 2


def rig_dp_for(dp_prod, t_film_prod, t_room):
    pp, pr = props(t_film_prod), props(t_room + DT_RIG / 2)
    return dp_prod * (pr["rho"] / pp["rho"]) * (pr["nu"] / pp["nu"]) ** 2


def main():
    t_s, t_fp = product_film_c()
    pp = props(t_fp)
    d_m = dl.JET["D_mm"] * 1e-3
    rows = []
    for d in DRIVES:
        op = dl.op3(d)
        q = op["board_cfm"] * dl.CFM
        dp = jet_dp(q, dl.JET["Cd"], dl.RHO)
        sens = {}
        for cd in (0.58, 0.72):
            jet = dict(dl.JET, Cd=cd)
            o2 = dl.op3(d, jet=jet)
            q2 = o2["board_cfm"] * dl.CFM
            sens[f"Cd{cd}"] = {"board_cfm": o2["board_cfm"], "jet_dp_Pa": round(jet_dp(q2, cd, dl.RHO), 2)}
        v = dl.JET["Cd"] * math.sqrt(2 * dp / pp["rho"])
        rows.append({"drive": d, "volts_12V_basis": round(12 * d, 2), "board_cfm": op["board_cfm"],
                     "branch_dp_Pa": op["branch_dp_Pa"], "jet_dp_Pa": round(dp, 2),
                     "Re_film_prod_Cd0.65": round(v * d_m / pp["nu"]), "Re_delivery": op["jet"]["Re"],
                     "h_design_delivery": op["board_h_design"], "h_est_delivery": op["board_h_est"],
                     "Cd_sensitivity": sens,
                     "rig_dp_Pa_by_room_C": {f"{t:g}": round(rig_dp_for(dp, t_fp, t), 2) for t in ROOM_C}})
    out = {"scope": __doc__.strip(),
           "inputs_sha256": {str(p.relative_to(AIRFLOW.parents[1])): hashlib.sha256(p.read_bytes()).hexdigest()
                             for p in (AIRFLOW / "delivery.py", RUN_C28)},
           "product": {"jet_air_C": dl.JET_AIR_C, "strip_C": round(t_s, 1), "film_C": round(t_fp, 1),
                       "rho": round(pp["rho"], 4), "nu": pp["nu"], "k": round(pp["k"], 5)},
           "rig_plate_rise_K": DT_RIG, "jet": dl.JET, "a_jets_m2": a_jets(), "rows": rows,
           "named": {k: next(r for r in rows if r["drive"] == v) for k, v in NAMED.items()}}
    (HERE / "setpoints.json").write_text(json.dumps(out, indent=1) + "\n")
    print(f"product film {t_fp:.1f} C (strip {t_s:.1f}, jets {dl.JET_AIR_C}); rig plate +{DT_RIG} K over room")
    print("drive  V    cfm    jet_dp  Re   dp(Cd.58/.72)   rig dp at room 18/21/24/27/30 C")
    for r in rows:
        s = r["Cd_sensitivity"]
        print(f"{r['drive']:<5} {r['volts_12V_basis']:<5} {r['board_cfm']:<6} {r['jet_dp_Pa']:<6} {r['Re_film_prod_Cd0.65']:<4} "
              f"{s['Cd0.58']['jet_dp_Pa']}/{s['Cd0.72']['jet_dp_Pa']}   "
              + " ".join(f"{v:.1f}" for v in r["rig_dp_Pa_by_room_C"].values()))


if __name__ == "__main__":
    main()
