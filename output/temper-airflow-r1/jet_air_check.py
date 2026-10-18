#!/usr/bin/env python3
"""Board margins at the chosen jet operating points with the jet air at its own temperature (estimate, step 1b).

    python3 jet_air_check.py [--workers 4]     # about 15 min -> runs/*_jet*.json, jet-air-check.json

board_h_sweep.py takes the jet air at bay-air temperature, which is conservative: the jets carry push-hood air
(D-18 basis 50 C at a 40 C kitchen), and their through-flow also ventilates the bay. Here, for each chosen point
(ceiling, h_top from delivery.json at the minimum drive, bay):
  * the bay air is study 14's lumped bay with the jet through-flow (delivery.bay_air),
  * the region's top-face convection is referenced to the jet air: h_top (T - T_jet) = h_top (rise - dT), with
    dT = T_jet - T_bay < 0 entered as a heat sink on those cells (rhs), and the FET tab ties relative to that bay.
Same model, same wrappers and the same gate as board_h_sweep.py (imported from it).
"""
from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import board_h_sweep as hs  # noqa: E402  (installs the region-h wrappers)
import delivery as dv  # noqa: E402

tb = hs.tb
_solve = tb.solve_system


def solve_system(board, k, thk_m, heat, h, pitch_m, links, parts=(), **kw):
    m, dT = hs._CTX.get("mask"), hs._CTX.get("dT", 0.0)
    if m is not None and dT:
        heat = heat.copy()
        heat[0][m & board] += hs._CTX["h_top"] * pitch_m * pitch_m * dT
    return _solve(board, k, thk_m, heat, h, pitch_m, links, parts, **kw)


tb.solve_system = solve_system
JET_C = dv.JET_AIR_C


class Ctx(dict):
    """board_h_sweep.one() clears and fills its _CTX; this one adds the jet-air offset on every fill."""
    dT = 0.0

    def update(self, *a, **kw):
        super().update(*a, **kw)
        super().update(dT=self.dT)


def one(job):
    ceil, h_top, bay, t_jet, pitch, label = job
    assert not (float(int(h_top)) in hs.H_TOPS and float(int(bay)) in hs.BAYS), "would overwrite a sweep solve"
    ctx = Ctx()
    ctx.dT = t_jet - bay
    hs._CTX = ctx                                  # the wrappers read the module global at call time
    tag, bal, rt = hs.one((ceil, "channel", h_top, bay, pitch))
    src = hs.RUNS / f"{tag}.json"
    dst = hs.RUNS / f"{label}_p{str(pitch).replace('.', 'p')}.json"
    d = json.loads(src.read_text())
    d["airflow"]["jet_air_c"], d["airflow"]["dT_jet_minus_bay"] = t_jet, t_jet - bay
    dst.write_text(json.dumps(d, indent=1) + "\n")
    src.unlink()
    return dst.name, bal, rt


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    dl = json.loads((HERE / "delivery.json").read_text())
    jobs, meta = [], {}
    for case, row in dl["board_min_drive"].items():
        r = row["at_min_board_h_design"]
        if r is None:
            continue
        ceil = float(case.split("_")[0][1:])
        bay0 = float(case.split("bay")[1])
        q_bay = {55: 20.2, 61: 27.9}[int(bay0)]
        bay = round(dv.bay_air(q_bay, r["board_cfm"]), 1)
        h = round(r["board_h_design"], 1)
        label = f"c{int(ceil)}_jet_h{int(h)}_bay{str(bay).replace('.', 'p')}"
        meta[case] = {"label": label, "ceil": ceil, "drive": r["drive"], "board_cfm": r["board_cfm"], "h_top": h,
                      "bay_still_air_c": bay0, "bay_with_jets_c": bay, "jet_air_c": JET_C}
        jobs += [(ceil, h, bay, JET_C, p, label) for p in (0.25, 0.5)]
    jobs.sort(key=lambda j: j[4])
    jobs = [j for j in jobs if not (hs.RUNS / f"{j[5]}_p{str(j[4]).replace('.', 'p')}.json").exists()]   # resume
    with ProcessPoolExecutor(max_workers=a.workers) as ex:
        for name, bal, rt in ex.map(one, jobs):
            print(f"  solved {name}  balance_rel {bal:.1e}  {rt} s", flush=True)
    out = {"scope": __doc__.strip(), "points": {}}
    for case, m in meta.items():
        rows = hs.gate.run(hs.RUNS, [m["label"]], m["bay_with_jets_c"])["cases"][m["label"]]
        g = hs.gated(rows)
        m["worst_gated"] = min(g, key=lambda r: r["margin_k"])
        m["rows_under_25K"] = {r["item"]: r["margin_k"] for r in g if r["margin_k"] < 25}
        out["points"][case] = m
    (HERE / "jet-air-check.json").write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps({k: (v["drive"], v["h_top"], v["bay_with_jets_c"], v["worst_gated"]) for k, v in out["points"].items()},
                     indent=1))


if __name__ == "__main__":
    main()
