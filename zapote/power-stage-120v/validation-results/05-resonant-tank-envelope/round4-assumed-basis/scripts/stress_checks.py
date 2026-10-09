#!/usr/bin/env python3
"""Fixed-frequency stress/fault probes and the timestep check for round 4 (ASSUMED basis).

1. Floor probe: every main-class corner, the synthetic offset pan and the two fault
   loads (no pan; aluminium / non-magnetic stainless) driven at the 35 kHz firmware floor
   and at 60 kHz with NO current regulation, 108 and 140 V. This is what a control fault
   or a start-up sweep at the window edge would impose; compared with the tank-CT static
   trip band (50.56-60.01 A) and the DC-return shunt band (47.52-97.98 A).
2. Timestep check: the grid cases with the largest tank peak and the largest capacitor
   peak re-run at 25 ns maximum step (deck default 50 ns); runbook threshold 2 %.
Writes outputs/floor-probe.csv and outputs/timestep-check.json.
"""
import csv
import json
import shutil
import sys
import tempfile
from multiprocessing import Pool
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import run_grid as G  # noqa: E402
import basis as B  # noqa: E402

CT_BAND = (50.558, 60.014)
SHUNT_BAND = (47.52, 97.98)


def probe(job):
    name, which, p, V, f = job
    m = G.sim(p, 0.54e-6, V, f)
    L, R = G.lr(p, f)
    return {"load": name, "corner": which, "line_vrms": V, "freq_hz": f,
            "f_res_hz": round(G.f_res(p, 0.54e-6), 1), "i_tank_rms_a": round(m["i_rms"], 2),
            "i_tank_pk_a": round(m["i_pk"], 2), "vc_pk_v": round(m["vc_pk"], 1), "p_tank_w": round(m["p_avg"], 1),
            "i_edge_crest_a": round(m["i_edge"], 2),
            "above_ct_trip_min": m["i_pk"] >= CT_BAND[0], "above_ct_trip_max": m["i_pk"] >= CT_BAND[1],
            "above_shunt_trip_min": m["i_pk"] >= SHUNT_BAND[0], "above_shunt_trip_max": m["i_pk"] >= SHUNT_BAND[1]}


def halfstep(row):
    p = {k[len("param_"):]: float(v) for k, v in row.items() if k.startswith("param_")}
    tmp = Path(tempfile.mkdtemp(prefix="t05r4-hs-"))
    try:
        deck = tmp / "tank_basis_25n.cir"
        deck.write_text((HERE / "tank_basis.cir").read_text().replace(".tran 50n 8.3333m 0 50n",
                                                                        ".tran 25n 8.3333m 0 25n"))
        base = G.DECK
        G.DECK = deck
        m25 = G.sim(p, float(row["C_bank_uF"]) * 1e-6, float(row["line_vrms"]), float(row["freq_hz"]))
        G.DECK = base
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    out = {"case": row["case"]}
    for key, col in (("i_pk", "i_tank_pk_a"), ("vc_pk", "vc_pk_v"), ("i_rms", "i_tank_rms_a"), ("p_avg", "p_tank_w")):
        a, b = float(row[col]), m25[key]
        out[key] = {"50ns": a, "25ns": round(b, 4), "change_pct": round(100 * (b - a) / a, 4)}
    return out


def main():
    jobs = []
    loads = {**{k: v for k, v in B.PANS.items()}, **B.SUPPLEMENTAL}
    for name, pan in loads.items():
        for which in ("low", "nom", "high"):
            p = G.corner_params(pan, which, 70.0)
            for V in (108.0, 140.0):
                for f in (35e3, 60e3):
                    jobs.append((name, which, p, V, f))
    for name, fl in B.FAULT_LOADS.items():
        p = {"L0U": 70.0, "KL40": fl["kl40"], "BETA": B.COIL["beta_kl"][0], "Q40": B.COIL["q40_ohm_per_uH"][1],
             "GAMMA": B.COIL["gamma_coil"][0], "R40": fl["r40"], "ALPHA": fl["alpha"]}
        for V in (108.0, 140.0):
            for f in (35e3, 45e3, 60e3):
                jobs.append((name + "_FAULT", "q_min", p, V, f))
    with Pool(8) as pool:
        rows = pool.map(probe, jobs)
    with open(ROOT / "outputs" / "floor-probe.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    grid = list(csv.DictReader(open(ROOT / "outputs" / "grid-cases.csv")))
    picks = {max(grid, key=lambda r: float(r["i_tank_pk_a"]))["case"]: None,
             max(grid, key=lambda r: float(r["vc_pk_v"]))["case"]: None,
             max(grid, key=lambda r: float(r["i_tank_rms_a"]))["case"]: None}
    sel = [r for r in grid if r["case"] in picks]
    with Pool(min(8, len(sel))) as pool:
        hs = pool.map(halfstep, sel)
    worst = max(abs(v["change_pct"]) for h in hs for k, v in h.items() if k != "case")
    json.dump({"threshold_pct": 2.0, "max_abs_change_pct": worst, "pass": worst < 2.0, "cases": hs},
              open(ROOT / "outputs" / "timestep-check.json", "w"), indent=1)
    print(f"floor probe {len(rows)} runs; timestep max change {worst:.4f} %")


if __name__ == "__main__":
    main()
