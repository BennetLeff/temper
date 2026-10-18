#!/usr/bin/env python3
"""Assemble the jet-bench web demo: page.html + rig-mesh.json + numbers from the bench kit -> jet-bench-demo.html.

    ../../.venv/bin/python export_mesh.py   # once, or after cad/rig_cad.py changes (build123d 0.11.1)
    python3 build_demo.py                   # seconds, stdlib only

Every number the page shows is read here from a file the kit's scripts write; none is typed into page.html.
"""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
BENCH = HERE.parent
AIRFLOW = BENCH.parent


def load(p: Path):
    return json.loads(p.read_text())


def main():
    sp = load(BENCH / "setpoints.json")
    pd = load(BENCH / "plate-design.json")
    st = load(BENCH / "selftest.json")["scenarios"]
    cad = load(BENCH / "cad" / "rig-cad.json")
    sweep = load(AIRFLOW / "board-h-sweep.json")
    bench = load(BENCH / "bench.example.json")
    bom = load(BENCH / "bom.json")

    def band(s):
        med, (lo, hi), true = s["h_med_0.55"], s["h95_0.55"], s["h_true_0.55"]
        return {"bias": round(med / true, 4), "lo": round(lo / med, 4), "hi": round(hi / med, 4)}

    data = {
        "drives": [{"drive": r["drive"], "volts": r["volts_12V_basis"], "jet_dp_Pa": r["jet_dp_Pa"],
                    "rig_dp_Pa_24C": r["rig_dp_Pa_by_room_C"]["24"], "Re": r["Re_film_prod_Cd0.65"],
                    "h_design": r["h_design_delivery"], "h_martin": r["h_est_delivery"]} for r in sp["rows"]],
        "product": sp["product"],
        "jet": sp["jet"],
        "cases": {k: v["h_top_required"] for k, v in sweep["required_h_top"].items()},
        "plate": {"area_m2": pd["area_m2"], "C_J_K": pd["D_E_sizing_dynamics"]["plate_heat_capacity_J_K"]["total"],
                  "tau_s": pd["D_E_sizing_dynamics"]["tau_s"], "G_gap_W_K": bench["G_gap_W_K"], "eps": bench["eps_plate"],
                  "R_heater_ohm": pd["D_E_sizing_dynamics"]["heater"]["R_ohm"]},
        "selftest": {"meter": band(st["near_h100"]), "no_meter": band(st["near_h100_no_flowmeter"]),
                     "b_true": st["near_h100"]["b_true"],
                     "rows": [{"name": k, "true": v["h_true_0.55"], "med": v["h_med_0.55"], "lo": v["h95_0.55"][0],
                               "hi": v["h95_0.55"][1], "verdict": v["c28_bay61_at_0.55"]} for k, v in st.items()]},
        "cad_checks": cad["checks"],
        "parts": {k: {"bbox_mm": v["bbox_mm"], "make": v["make"]} for k, v in cad["parts"].items()},
        "plate_mass_g": cad["plate_mass_g_6061"],
        "bom_must_buy_usd": bom["must_buy_est_usd"],
    }
    mesh = (HERE / "rig-mesh.json").read_text()
    page = (HERE / "page.html").read_text()
    out = page.replace("__MESH__", mesh).replace("__DATA__", json.dumps(data))
    (HERE / "jet-bench-demo.html").write_text(out)
    print("jet-bench-demo.html", len(out), "bytes; must-buy", data["bom_must_buy_usd"])


if __name__ == "__main__":
    main()
