#!/usr/bin/env python3
"""Run the project's B3 body-level model (b3-ratings basis, unchanged code) on a proxy board from proxy.py, then gate it.

    python3 run_b3.py --board s53 --cases c17.5_h10@61 --check-s53     # control: must reproduce the committed s53 runs
    python3 run_b3.py --board s53 [--workers 3]                         # the h sweep below
    python3 run_b3.py --board native22_218 [--workers 3]

Default cases (both boards, identical settings, bay 61 C, line 13.5 A, hot copper, FET drain-lead path, probes):
  17.5 A release basis, still-air form: c17.5_h{10,12,16,19,25}       (h on both faces)
  28 A on the declared airflow route:   c28_h{10,12,16,19,25}_jet100  (jets on run_basis.JET_REGION + base h; S24)
Each case is solved at 0.25 and 0.5 mm, as run_basis.py does. What is reused verbatim: body_runs.run_case,
run_basis.inputs / region_for / LEAD_G, fet_case.t_case, b3_ratings_gate.evaluate / probe_rows / module_rows / est.
What the proxy swaps: the geometry (pads, vias, outline + copper masks), the A4 heat fields (sparse files, deposited
exactly as thermal.remap_a4 does), the heat-row file and the part bodies.

Gating: every gated row of b3_ratings_gate at the case's bay; the case margin is the worst gated row. A sensitivity
re-rates the four R_on 2512 resistors (R10/R12/R18/R20) as a 2 W-class part (element 155 C, derating to 0 W at 155 C,
the gate's own line with rated 2 W) - [EST]: no part is chosen.
Writes work/<board>/runs/*.json and results/b3_<board>.json.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

import common as C

sys.dont_write_bytecode = True
sys.path.insert(0, str(C.B3 / "b3-convergence"))
sys.path.insert(0, str(C.B3 / "b3-ratings"))
sys.path.insert(0, str(C.B3 / "b3"))

DEFAULT_CASES = [f"c17.5_h{h}@61" for h in (10, 12, 16, 19, 25)] + [f"c28_h{h}_jet100@61" for h in (10, 12, 16, 19, 25)]
RON = ("R10", "R12", "R18", "R20")
RON_2W = 2.0


def setup(board):
    """Point the B3 modules at a proxy board (call in every worker)."""
    import body_runs as br
    import run_basis
    import thermal as T
    d = C.WORK / board
    a4 = d / "a4"

    def remap_sparse(case, x, y, brd_mask, heat, scale=1.0):
        """thermal.remap_a4 on the proxy's sparse heat cells: the same floor binning, barrel rule and energy check."""
        meta = json.loads((a4 / f"{case}.json").read_text())
        z = np.load(a4 / f"{case}.npz")
        before = float(heat.sum())
        pitch = x[1] - x[0]
        xmin, ymin = x[0] - pitch / 2, y[0] - pitch / 2
        for layer, zi in T.CU_INDEX.items():
            if f"{layer}|w" not in z.files:
                continue
            xs, ys, ws = z[f"{layer}|x"], z[f"{layer}|y"], z[f"{layer}|w"]
            tx = np.floor((xs - xmin) / pitch).astype(int)
            ty = np.floor((ys - ymin) / pitch).astype(int)
            if np.any(tx < 0) or np.any(tx >= len(x)) or np.any(ty < 0) or np.any(ty >= len(y)):
                raise ValueError("A4 heat outside thermal grid")
            np.add.at(heat[zi], (tx, ty), scale * ws)
        for item in meta["barrel_heat_by_layer"]:
            px, py = item["xy_mm"]
            ix, iy = int(math.floor((px - xmin) / pitch)), int(math.floor((py - ymin) / pitch))
            if not brd_mask[ix, iy]:
                raise ValueError("A4 barrel heat outside board")
            for layer, watts in item["layer_joule_w"].items():
                heat[T.CU_INDEX[layer], ix, iy] += scale * watts
        found = float(heat.sum()) - before
        if abs(found - scale * meta["loss_w"]) > 1e-8 * max(1.0, scale):
            raise AssertionError(f"A4 energy map {found} differs from {meta['loss_w']}")
        return meta, {"remapped_w": found, "a4_loss_w": meta["loss_w"], "scale_i2": scale, "proxy_a4": str(a4)}

    T.remap_a4 = remap_sparse
    br.rs.HEAT_C28 = d / "heat_c28.json"
    br.PART_BODIES = json.loads((d / "part_bodies.json").read_text())["parts"]
    return br, run_basis, Path((d / "geom_path.txt").read_text().strip()), d / "cache"


def one(job):
    board, name, case, bay, pitch = job
    br, rb, geom, cache = setup(board)
    import thermal_body as tb
    import fet_case
    import b3_ratings_gate as gate
    ceil, h = gate.case_ceiling_h(case)
    op = case.split("_")[0]
    runs = C.WORK / board / "runs"
    c = rb.inputs(op, ceil, runs)
    br.op_inputs = lambda _op, _c=c: _c
    brd = tb.Board(geom, cache)
    leads = {"pad": "2", "g": rb.LEAD_G, "t_rise": {r: t - bay for r, t in fet_case.t_case(ceil, i_line=rb.I_LINE_A).items()}}
    region = rb.region_for(case, bay)
    t0 = time.time()
    res = br.run_case(brd, op, h, pitch, "fraction", "network", {}, None, None, True, True, label=name, leads=leads,
                      region=region, copper_tcr={"alpha": tb.ALPHA_CU, "air_c": bay}, probes=True)
    res["board_sha256"] = brd.data["board_sha256"]
    res.update(bay_c=bay, i_line_a=rb.I_LINE_A, i_t_a=rb.i_trip(ceil), ceiling_a=ceil, proxy_board=board,
               wall_s=round(time.time() - t0, 1))
    if region is not None:
        res["region"]["air_c"] = bay + region.t_air_rise
    (runs / f"{name}.json").write_text(json.dumps(res, indent=1) + "\n")
    return name


def gate_case(board, case, bay):
    import b3_ratings_gate as gate
    runs = C.WORK / board / "runs"
    r25 = json.loads((runs / f"{case}_p0p25.json").read_text())
    r05 = json.loads((runs / f"{case}_p0p5.json").read_text())
    rows = gate.evaluate(r25, r05, bay) + gate.probe_rows(case, r25, r05, bay)
    have_ps2 = any(p["ref"] == "PS2" for p in r25["parts"])
    if have_ps2:
        rows += gate.module_rows(case, r25, r05, bay)
    for r in rows:
        r.setdefault("margin_k", round(r["limit_c"] - r["est_c"], 1))
    gated = sorted([r for r in rows if r["gated"]], key=lambda r: r["margin_k"])
    # 2 W-class R_on sensitivity: the terminal-derating limit at rated 2 W, everything else unchanged
    alt = []
    p25 = {p["ref"]: p for p in r25["parts"]}
    for r in gated:
        q = dict(r)
        ref = r["item"].split(":")[0]
        if ref in RON and "terminal derating" in r["item"]:
            w = p25[ref]["watts_into_model"]
            q["limit_c"] = round(155.0 - 85.0 * w / (0.8 * RON_2W), 1)
            q["margin_k"] = round(q["limit_c"] - q["est_c"], 1)
            q["item"] = r["item"].replace("2512 terminal", "2 W-class [EST] terminal")
        alt.append(q)
    alt.sort(key=lambda r: r["margin_k"])
    bal = r25["balance"]
    area = r25["board_cells"] * 0.25 ** 2 * 1e-6
    return {"case": case, "bay_c": bay, "h": r25["h"], "i_t_a": r25["i_t_a"], "jet": r25.get("region") is not None,
            "worst_margin_k": gated[0]["margin_k"], "binding": gated[0]["item"],
            "next": [(r["item"], r["margin_k"]) for r in gated[1:6]],
            "worst_margin_k_ron2w": alt[0]["margin_k"], "binding_ron2w": alt[0]["item"],
            # board rows only: the PS2 local-air row leaves with PS2 (inlet module), so the like-for-like board metric
            # excludes it on both boards
            "worst_board_margin_k": next(r["margin_k"] for r in gated if not r["item"].startswith("PS2:")),
            "binding_board": next(r["item"] for r in gated if not r["item"].startswith("PS2:")),
            "worst_board_margin_k_ron2w": next(r["margin_k"] for r in alt if not r["item"].startswith("PS2:")),
            "binding_board_ron2w": next(r["item"] for r in alt if not r["item"].startswith("PS2:")),
            "laminate_1mm_block_c": next(r["est_c"] for r in rows if r["item"].startswith("laminate: 1 mm")),
            "source_w": round(bal["source_w"], 3), "face_convection_w": round(bal["convection_w"], 3),
            "body_air_w": round(bal["body_air_w"], 3), "lead_sink_w": round(bal["lead_sink_w"], 3),
            "board_area_m2": round(area, 6),
            "mean_face_rise_k": round(bal["convection_w"] / (2 * r25["h"] * area), 2) if not r25.get("region") else None,
            "copper_loss_hot_w": round(bal["tcr"]["q_hot_w"], 3), "copper_loss_20c_w": round(bal["tcr"]["q20_w"], 3),
            "advisory": [r for r in rows if not r["gated"] and r["item"].split(":")[0] in ("C5", "C6", "C21", "C22", "C23", "C151", "C152")],
            "rows": gated}


def check_s53():
    """The control: the s53 board through this runner must give the committed s53 release solve."""
    ref = C.B3 / "b3-ratings/runs"
    out = {}
    for p in ("0p25", "0p5"):
        a = json.loads((C.WORK / "s53/runs" / f"c17.5_h10_p{p}.json").read_text())
        b = json.loads((ref / f"c17.5_h10_p{p}.json").read_text())
        pa, pb = {x["ref"]: x for x in a["parts"]}, {x["ref"]: x for x in b["parts"]}
        dmax = max(abs(pa[r]["pad_max_cell_c"] - pb[r]["pad_max_cell_c"]) for r in pb)
        out[p] = {"source_w": [a["balance"]["source_w"], b["balance"]["source_w"]],
                  "peak_1mm_block_c": [a["peak_1mm_block"]["temperature_c"], b["peak_1mm_block"]["temperature_c"]],
                  "max_abs_part_pad_diff_k": dmax, "committed_board": b["board_sha256"][:12]}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", required=True)
    ap.add_argument("--cases", default=",".join(DEFAULT_CASES))
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--check-s53", action="store_true")
    ap.add_argument("--gate-only", action="store_true")
    a = ap.parse_args()
    cases = []
    for it in a.cases.split(","):
        c, _, b = it.partition("@")
        cases.append((c, float(b or 61)))
    (C.WORK / a.board / "runs").mkdir(parents=True, exist_ok=True)
    if not a.gate_only:
        jobs = []
        for c, bay in cases:
            for p in (0.25, 0.5):
                name = f"{c}_p{str(p).replace('.', 'p')}"
                if (C.WORK / a.board / "runs" / f"{name}.json").exists():
                    continue
                jobs.append((a.board, name, c, bay, p))
        jobs.sort(key=lambda j: -1 if j[4] == 0.25 else 0)          # long solves first
        with ProcessPoolExecutor(max_workers=max(1, min(a.workers, 4))) as ex:
            for n in ex.map(one, jobs):
                print("  solved", n, flush=True)
    setup(a.board)
    res = {"board": a.board, "cases": {}}
    for c, bay in cases:
        res["cases"][c] = gate_case(a.board, c, bay)
        g = res["cases"][c]
        print(f"  {c}: worst {g['worst_margin_k']:+.1f} K ({g['binding'][:60]}); 2 W R_on {g['worst_margin_k_ron2w']:+.1f} K")
    if a.check_s53:
        res["s53_control"] = check_s53()
        print(json.dumps(res["s53_control"], indent=1))
    old = C.RESULTS / f"b3_{a.board}.json"
    if old.exists():
        prev = json.loads(old.read_text())
        prev.get("cases", {}).update(res["cases"])
        res["cases"] = prev["cases"]
        res.setdefault("s53_control", prev.get("s53_control"))
    C.dump(old, res)


if __name__ == "__main__":
    main()
