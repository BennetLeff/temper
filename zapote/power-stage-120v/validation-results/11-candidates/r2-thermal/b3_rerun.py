#!/usr/bin/env python3
"""RESOLUTION-PLAN F12 step 1 (and the baseline for every thermal proposal): rerun the converged B3 body-level model
(a COPY of ../../04-board-current-thermal/round5-native21/b3{,-convergence} in ./round5copy, originals untouched) with
edited heat inputs.

    python3 -I b3_rerun.py --scenario L1_15A_dc --op c28 --h 25 --pitch 0.25 [--window 'W07']

A scenario is a dict of {ref: watts} overrides applied to the c28 heat file (watts_nominal = watts_worst) plus optional
sens dict. Output: runs/<scenario>_<op>_h<h>_p<pitch>[_win].json
"""
import argparse, json, os, sys, time
from pathlib import Path
HERE = Path(__file__).resolve().parent
CP = HERE / "round5copy"
sys.path.insert(0, str(CP / "b3-convergence"))
sys.path.insert(0, str(CP / "b3"))
import body_runs as br      # noqa: E402
import thermal_body as tb   # noqa: E402
import numpy as np          # noqa: E402

CACHE = Path(os.environ.get("R2_CACHE", HERE / "cache"))
SCEN = json.loads((HERE / "scenarios.json").read_text())


def heat_file(name, op):
    base = CP / "b3-convergence/inputs/heat_der14.json" if op == "der14" else CP / "b3/inputs/native21-board-heat-sources-c28.json"
    d = json.loads(base.read_text())
    sc = SCEN[name]
    for p in d["parts"]:
        if p["ref"] in sc.get("watts", {}):
            p["watts_nominal"] = p["watts_worst"] = sc["watts"][p["ref"]]
        if p["ref"] in sc.get("scale", {}):
            p["watts_nominal"] *= sc["scale"][p["ref"]]; p["watts_worst"] *= sc["scale"][p["ref"]]
    out = HERE / "inputs" / f"heat_{name}_{op}.json"
    out.write_text(json.dumps(d))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", default="base")
    ap.add_argument("--op", default="c28")
    ap.add_argument("--h", type=float, default=25)
    ap.add_argument("--pitch", type=float, default=0.5)
    ap.add_argument("--bc-from", default=None, help="saved rise npz (cache) for a window run")
    ap.add_argument("--window", default=None, help="i0,i1,j0,j1 in cells of --pitch")
    ap.add_argument("--it", type=float, default=None, help="tank RMS A (scales tank rows and A4 copper like the der14 op)")
    ap.add_argument("--edit", default=None)
    ap.add_argument("--config", default="main")
    ap.add_argument("--save-rise", default=None)
    a = ap.parse_args()
    CACHE.mkdir(parents=True, exist_ok=True)
    brd = tb.Board(br.rs.GEOM, CACHE)
    if a.edit:
        edits = json.loads((HERE / "edits.json").read_text())[a.edit]
        for e in edits:
            if e["kind"] == "via":
                for L in e["layers"]:
                    brd.data["primitives"].append({"kind": "via", "layer": L, "centre": e["xy"], "diameter_mm": e["dia"],
                                                   "drill_mm": e["drill"], "net": e["net"]})
            elif e["kind"] == "zone":
                x0, y0, x1, y1 = e["box"]
                brd.data["primitives"].append({"kind": "zone", "layer": e["layer"], "net": e["net"],
                                               "shell": [[x0, y0], [x1, y0], [x1, y1], [x0, y1]], "holes": []})
        brd.data["board_sha256"] += "+" + a.edit
    brd.fine()
    hf = heat_file(a.scenario, "der14" if a.op == "der14" else "c28")
    sc = SCEN[a.scenario]
    if a.op == "der14":
        br.op_inputs("der14")      # writes the original-copy der14 json (identical) and registers the op
        br.rs.OPS["der14"]  # noqa
        # override the heat path used by op_inputs for der14
        orig = br.op_inputs
        def patched(op):
            c, _, m = orig(op)
            return c, hf, m
        br.op_inputs = patched
    else:
        br.rs.HEAT_C28 = hf
    if a.it:
        it = a.it
        br.rs.OPS["ik"] = {"I_t": it, "I_line": 11.1, "parts": "nominal", "heat": "c28"}
        d = json.loads(hf.read_text()); k = (it / 29.4) ** 2
        for p in d["parts"]:
            if p["ref"] in br.TANK_ROWS:
                p["watts_nominal"] *= k; p["watts_worst"] *= k
        hf2 = HERE / "inputs" / f"heat_{a.scenario}_it{it}.json"; hf2.write_text(json.dumps(d))
        case = br.rs.cases("ik")
        br.op_inputs = lambda op: (case, hf2, "nominal")
        a.op = "ik"
    window = bc = None
    if a.window:
        window = tuple(int(v) for v in a.window.split(","))
        z = np.load(CACHE / a.bc_from)
        pg = float(z["pitch"]); wg = z["window"]
        origin = (brd.xmin + int(wg[0]) * pg, brd.ymin + int(wg[2]) * pg)
        bc = br.bc_from_global(z["rise"], pg, origin, brd, a.pitch, *window)
    t0 = time.time()
    cop, src = {"main": ("fraction", "network"), "legacy": ("binary", "point")}[a.config]
    res, rise = br.run_case(brd, a.op, a.h, a.pitch, cop, src, sc.get("sens") or {}, window, bc,
                            label=a.scenario, return_rise=True)
    res["scenario"] = a.scenario
    res["runtime_s"] = round(time.time() - t0, 1)
    name = f"{a.scenario}{"+" + a.edit if a.edit else ""}{"_" + a.config if a.config != "main" else ""}{"_it" + str(a.it) if a.it else ""}_{a.op}_h{int(a.h)}_p{str(a.pitch).replace('.', 'p')}" + (f"_w{a.window.replace(',', '-')}" if a.window else "")
    (HERE / "runs" / f"{name}.json").write_text(json.dumps(res, indent=1, default=float) + "\n")
    if a.save_rise:
        np.savez_compressed(CACHE / a.save_rise, rise=rise, pitch=a.pitch, window=np.array(window if window else [0, 0, 0, 0]))
    print(name, "peak", res["peak"], "balance", res["balance"], "runtime", res["runtime_s"])


if __name__ == "__main__":
    main()
