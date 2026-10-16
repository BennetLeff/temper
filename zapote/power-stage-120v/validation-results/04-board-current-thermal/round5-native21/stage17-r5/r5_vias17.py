#!/usr/bin/env python3
"""Stage 17b: R5 current-via check against the project's via criterion.

    python3 r5_vias17.py [--tag native21s17] [--copper-tcr A] [--out r5_vias17.json]   -> r5_vias17.json

Copper temperature (OPEN-ITEMS S17): the B3 solve is hot copper by default (thermal.py --copper-tcr, ALPHA_CU), and the
barrel loss uses rho(T) = RHO_CU (1 + alpha (T - 20 C)) at the via's mid-wall temperature (fixed point of cell max +
mid-wall rise, three passes; RHO_CU is the 20 C value). --copper-tcr 0 reproduces the 20 C copper record.

Criterion (validation-plan/04-board-current-thermal.md:114): "Report the maximum per-via current and the via
temperature rise. Flag any via > 3 A (a flag, not a fail; there's no rated limit)". Round 5 accepted the stage-6
R5 arrays at 7.27 A worst (34 A coherent, about 7.7 A per mm of barrel circumference; native-17 5.5 A/mm;
round5-native21/README.md:37-47). There is no rated per-via limit in DECISIONS or task 04.

For every via of LEG_RET / HV_RET within R5's box this script reports:
  * the A4 hop currents (outputs/via_currents.json; hv_mixed_a / hv_mixed_b = the coherent 34 A return,
    hv_dc 15 A, leg_a_34 / leg_a_18p7), the A per mm of barrel circumference and the > 3 A flag;
  * the c28 current: the coherent 34 A value scaled to the 29.4 A trip RMS (linear, conservative: the B3 c28 case
    weights the two mixed cases 0.5 each);
  * the barrel self-heating: Joule heat of each current-carrying hop (18 um plating tube, hop length from the B3
    stackup) and its mid-wall rise over the two planes it joins, dT = P R_th / 8 (uniform generation, both ends
    held: conservative, the epoxy fill and the cap are ignored);
  * the B3 c28 / 0.25 mm / h 25 temperature of the board cells at the via (all copper levels; A4 barrel heat is
    already in that solve) and the via-wall estimate = cell max + barrel rise.
The wall estimate is then compared with G6's terminal bound (148.39 C for 20 % CSS2H margin): an in-pad via
must not lift the R5 terminal above it.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
R5N = HERE.parent
UNIT = R5N.parents[2]
BOX = (33.0, 5.0, 44.0, 19.0)
RHO_CU, K_CU, PLATING_M = 1.72e-8, 390.0, 18e-6
I_COH, I_TRIP = 34.0, 29.4
COH = ("hv_mixed_a-p00625-pl18", "hv_mixed_b-p00625-pl18", "leg_a_34-p00625-pl18")   # the coherent 34 A cases
CASES = ("hv_mixed_a-p00625-pl18", "hv_mixed_b-p00625-pl18", "hv_dc-p00625-pl18", "leg_a_34-p00625-pl18", "leg_a_18p7-p00625-pl18")


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="native21s17b")
    ap.add_argument("--copper-tcr", type=float, help="copper TCR 1/K (default thermal.ALPHA_CU, hot copper; 0 = 20 C)")
    ap.add_argument("--out", default=str(HERE / "r5_vias17.json"))
    a = ap.parse_args()
    th = load("thermal", R5N / "b3/thermal.py")
    alpha = th.ALPHA_CU if a.copper_tcr is None else a.copper_tcr
    rs = load("run_study", R5N / "b3/run_study.py")
    zmid = np.cumsum(th.THICK_MM) - th.THICK_MM / 2
    vc = json.loads((R5N / "outputs/via_currents.json").read_text())
    vias = {}
    for case in CASES:
        for r in vc[case]:
            x, y = r["xy_mm"]
            if r["kind"] != "via" or not (BOX[0] <= x <= BOX[2] and BOX[1] <= y <= BOX[3]):
                continue
            v = vias.setdefault((round(x, 3), round(y, 3)), {"xy_mm": [x, y], "drill_mm": r["drill_mm"], "cases": {}})
            v["cases"][case] = {"hop_layers": r["hop_layers"], "hop_amps": [round(h, 3) if h is not None else None for h in r["hop_amps"]]}

    # B3 c28 solve, 0.25 mm (same command as g6_r5_derating.py), keep the temperature field
    geom = UNIT / f"native-21/verification/{a.tag}-all-copper.json.gz"
    heat = R5N / "b3/inputs/native21-board-heat-sources-c28.json"
    out = Path(tempfile.mkdtemp()) / "b3_p0p25.json"
    subprocess.run([sys.executable, str(R5N / "b3/thermal.py"), "--geometry", str(geom), "--case", rs.cases("c28"),
                    "--pitch-mm", "0.25", "--h", "25", "--a6-heat", str(heat), "--a6-mode", "nominal", "--output", str(out),
                    "--copper-tcr", repr(alpha)], check=True, stdout=subprocess.DEVNULL)
    sol = json.loads(out.read_text())
    f = np.load(out.with_suffix(".npz"))
    xs, ys, rise = f["x_mm"], f["y_mm"], f["rise_k"]
    r5 = next(q for q in sol["a6_parts_applied"] if q["ref"] == "R5")

    rows = []
    for v in vias.values():
        x, y = v["xy_mm"]
        d = v["drill_mm"]
        circ = math.pi * d
        amax = {c: max((abs(h) for h in r["hop_amps"] if h is not None), default=0.0) for c, r in v["cases"].items()}
        coh_case = max((c for c in COH if c in v["cases"]), key=lambda c: amax[c])
        coh = amax[coh_case]
        worst = max(amax.values())
        ix = np.flatnonzero(abs(xs - x) <= d / 2 + 0.125)
        iy = np.flatnonzero(abs(ys - y) <= d / 2 + 0.125)
        cell = th.TAMB_C + float(rise[:, ix][:, :, iy].max())
        # c28 barrel heat: every hop of the via's worst coherent 34 A case scaled to the trip RMS, plating resistivity
        # at the mid-wall temperature (cell max + rise; fixed point, three passes)
        case = v["cases"][coh_case]
        dt_k = 0.0
        for _ in range(3):
            rho = RHO_CU * (1 + alpha * (cell + dt_k - 20.0))
            p_w, dt_new = 0.0, 0.0
            for (la, lb), h in zip(case["hop_layers"], case["hop_amps"]):
                if h is None:
                    continue
                length = abs(zmid[th.CU_INDEX[lb]] - zmid[th.CU_INDEX[la]]) * 1e-3
                area = math.pi * d * 1e-3 * PLATING_M
                i = abs(h) * I_TRIP / I_COH
                p = i * i * rho * length / area
                p_w += p
                dt_new = max(dt_new, p * (length / (K_CU * area)) / 8)
            dt_k = dt_new
        rows.append({"xy_mm": [x, y], "case_max_a": {c: round(q, 2) for c, q in amax.items()}, "coherent_case": coh_case,
                     "worst_a": round(worst, 2), "coherent_34a_a": round(coh, 2),
                     "a_per_mm_circumference": round(worst / circ, 2), "over_3a_flag": worst > 3.0,
                     "c28_rms_a": round(coh * I_TRIP / I_COH, 2), "c28_barrel_w": round(p_w, 4),
                     "c28_barrel_mid_rise_k": round(dt_k, 2), "b3_c28_cell_max_c": round(cell, 2),
                     "barrel_rho_ohm_m": float(f"{rho:.4g}"),
                     "via_wall_estimate_c": round(cell + dt_k, 2)})
    rows.sort(key=lambda r: -r["worst_a"])
    g6_bound = 148.39
    worst = rows[0]
    res = {"criterion": {"source": "validation-plan/04-board-current-thermal.md:114",
                         "text": "Report the maximum per-via current and the via temperature rise. Flag any via > 3 A (a flag, not a fail; there's no rated limit)",
                         "round5_reference": "round5-native21/README.md:37-47: stage 6 accepted 7.27 A worst (34 A coherent), ~7.7 A/mm of barrel circumference; native-17 5.5 A/mm"},
           "geometry": str(geom.relative_to(UNIT)), "board_sha256": sol["board_sha256"],
           "copper_temp_model": {**(sol.get("copper_temp_model") or {"model": "cold-20C", "alpha_per_k": 0.0}),
                                 "barrel_rho": f"RHO_CU {RHO_CU} x (1 + {alpha} (T_mid_wall - 20 C))"},
           "r5_pad_cell_max_c": round(r5["conditional_pad_cell_max_c"], 2), "g6_terminal_bound_c": g6_bound,
           "vias": rows, "n_vias": len(rows), "n_over_3a": sum(r["over_3a_flag"] for r in rows),
           "worst": {k: worst[k] for k in ("xy_mm", "worst_a", "a_per_mm_circumference", "c28_rms_a", "c28_barrel_w",
                                           "c28_barrel_mid_rise_k", "b3_c28_cell_max_c", "via_wall_estimate_c")},
           "max_via_wall_estimate_c": max(r["via_wall_estimate_c"] for r in rows),
           "verdict": None}
    res["verdict"] = ("REPORTED (flag only, no rated limit); every via wall estimate <= the G6 terminal bound"
                      if res["max_via_wall_estimate_c"] <= g6_bound else "via wall estimate above the G6 terminal bound")
    Path(a.out).write_text(json.dumps(res, indent=1) + "\n")
    print(json.dumps({k: res[k] for k in ("n_vias", "n_over_3a", "worst", "max_via_wall_estimate_c", "r5_pad_cell_max_c", "verdict")}, indent=1))


if __name__ == "__main__":
    main()
