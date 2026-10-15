#!/usr/bin/env python3
"""Compute the B3 ratings-gate basis solves on the current board and write margins.json for scorecard.py.

    python3 run_basis.py [--workers 4]     # about 6 min (two 0.25 mm and two 0.5 mm body-level solves)
        -> runs/<case>_p0p25.json, runs/<case>_p0p5.json (gitignored), margins.json, exit = gate exit
    python3 run_basis.py --bay-c 61 --runs DIR --out FILE   # another bay (candidate 39: the bay-61 ceiling); the FET
        tab tie is absolute (fet_case), so a bay is solved, not shifted

Uses the committed body-level model in place (../b3-convergence/thermal_body.py + body_runs.py, fill-fraction copper and
datasheet package networks) on run_study.GEOM (the chain's current copper) and the committed c28 heat file.
c22 = the 22 A default ceiling at its 1.05 x trip (23.1 A) with the tank-current rows of the c28 heat file scaled by
(23.1 / 29.4)^2, the same construction as body_runs.op_inputs('der14').
FET drain-lead path (thermal-refine 2026-10-15): each TO-247's drain pad is tied to its tab at the fet_case.t_case()
central case temperature through thermal_body.drain_lead_conductance() (IPW65R018CFD7 p.12 drawing, mid values). The tie
temperature is relative to the bay air, so the solves are for BAY_C and the gate is run at BAY_C.
Note: b3-convergence/inputs/part-bodies.json is the stage-19b extraction; it carries to the s32 board unchanged in
footprint and position (checked 2026-10-15 against fab/positions-kicad.csv) - re-run extract_bodies.py if parts move.
"""
import argparse
import json
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
CONV = HERE.parent / "b3-convergence"
sys.path.insert(0, str(CONV))
import body_runs as br  # noqa: E402
import fet_case  # noqa: E402
import thermal_body as tb  # noqa: E402

RUNS = HERE / "runs"
CASES = {"c22_h10": ("c22", 10), "c28_h10": ("c28", 10)}
CEIL = {"c22": 22.0, "c28": 28.0}
BAY_C = 55.0                                       # enclosure R33 study 14 expected bay air (the gate's default)
LEAD_G = tb.drain_lead_conductance()


def op_c22(runs):
    rs = br.rs
    rs.OPS["c22"] = {"I_t": 1.05 * 22.0, "I_line": 11.1, "parts": "nominal", "heat": "c28"}
    heat = json.loads(rs.HEAT_C28.read_text())
    k = (1.05 * 22.0 / 29.4) ** 2
    for p in heat["parts"]:
        if p["ref"] in br.TANK_ROWS:
            p["watts_nominal"] *= k
            p["watts_worst"] *= k
    path = runs / "heat_c22.json"
    path.write_text(json.dumps(heat))
    return rs.cases("c22"), path, "nominal"


def one(job):
    name, op, h, pitch, runs, bay = job
    runs = Path(runs)
    if op == "c22":
        c = op_c22(runs)
        br.op_inputs = lambda _op, _c=c: _c
    brd = tb.Board(br.rs.GEOM, RUNS / "cache")
    leads = {"pad": "2", "g": LEAD_G, "t_rise": {r: t - bay for r, t in fet_case.t_case(CEIL[op]).items()}}
    res = br.run_case(brd, op, h, pitch, "fraction", "network", {}, None, None, True, True, label=name, leads=leads)
    res["board_sha256"] = brd.data["board_sha256"]
    (runs / f"{name}.json").write_text(json.dumps(res, indent=1) + "\n")
    return name


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--bay-c", type=float, default=BAY_C)
    ap.add_argument("--runs", default=str(RUNS))
    ap.add_argument("--out", default=str(HERE / "margins.json"))
    a = ap.parse_args()
    runs = Path(a.runs)
    # the task-04 heat fields are gitignored: after a merge they can belong to another board (DECISIONS 51)
    sys.path.insert(0, str(HERE.parent))
    import a4_fields
    if not a4_fields.check():
        raise SystemExit(2)
    RUNS.mkdir(exist_ok=True)
    runs.mkdir(parents=True, exist_ok=True)
    tb.Board(br.rs.GEOM, RUNS / "cache").fine()
    jobs = [(f"{c}_p{str(p).replace('.', 'p')}", op, h, p, str(runs), a.bay_c) for c, (op, h) in CASES.items()
            for p in (0.25, 0.5)]
    with ProcessPoolExecutor(max_workers=min(a.workers, 4)) as ex:
        for n in ex.map(one, jobs):
            print("  solved", n, flush=True)
    r = subprocess.run([sys.executable, str(HERE / "b3_ratings_gate.py"), "--runs", str(runs),
                        "--out", a.out, "--bay-c", str(a.bay_c)])
    raise SystemExit(r.returncode)


if __name__ == "__main__":
    main()
