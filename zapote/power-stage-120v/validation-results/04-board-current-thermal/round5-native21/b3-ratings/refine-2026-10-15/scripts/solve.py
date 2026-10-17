#!/usr/bin/env python3
"""Body-level B3 solves for the thermal-refine study: one job = one global solve -> runs/<config>/<case>_p0pNN.json.

A job (dict):
  config      folder name under runs/
  case        "c22_h10" etc. (file stem; the gate reads <case>_p0p25.json / _p0p5.json)
  ceil        commissioned ceiling in A: 28 -> run_study OPS "c28" exactly (I_t 29.4 A); other -> I_t = 1.05 x ceil,
              inlet 11.1 A, tank rows of the heat file scaled by (I_t / 29.4)^2 (b3-ratings/run_basis.py op_c22)
  pitch       0.25 | 0.5
  model       "repo" (committed modules, in place) | "mod" (model/b3-convergence with the lead path)
  heat        path of the c28-basis heat file (committed: round5-native21/b3/inputs/native21-board-heat-sources-c28.json)
  tank_factor scales the A4 copper rows that carry tank current (every run_study.cases() row but ac_n/ac_l)
  part_scale  {ref: factor} on the heat-file rows (after the ceiling scaling)
  leads       None | {"g": W/K or {ref: W/K}, "t_case_c": {ref: C}, "bay_c": C}  (mod only; t_rise = T_case - bay)
  save_field  optional: also write the rise field (all sheets) to <case>_p0pNN.npz, for superposition.py
Solves are cached: a job whose JSON exists with the same job spec is skipped.

    python3 solve.py jobs.json [--workers 4]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import multiprocessing as mp
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import BOARD_SHA, CACHE, FROZEN, HEAT_DIR, MOD_CONV, REPO_CONV, RUNS  # noqa: E402

TANK_A4_SKIP = ("ac_n_main", "ac_l_main")      # line-current rows (run_study.cases); every other row scales with I_t


def job_key(job):
    return hashlib.sha256(json.dumps(job, sort_keys=True).encode()).hexdigest()[:16]


def out_path(job):
    return RUNS / job["config"] / f"{job['case']}_p{str(job['pitch']).replace('.', 'p')}.json"


def build_inputs(br, job):
    """(case string, heat path) for the job; the same construction as b3-ratings/run_basis.py for c22."""
    rs = br.rs
    heat = json.loads(Path(job["heat"]).read_text())
    ceil = float(job["ceil"])
    if ceil == 28.0:
        case = rs.cases("c28")
    else:
        op = f"c{ceil:g}".replace(".", "p")
        rs.OPS[op] = {"I_t": 1.05 * ceil, "I_line": 11.1, "parts": "nominal", "heat": "c28"}
        case = rs.cases(op)
        k = (1.05 * ceil / 29.4) ** 2
        for p in heat["parts"]:
            if p["ref"] in br.TANK_ROWS:
                p["watts_nominal"] *= k
                p["watts_worst"] *= k
    f = float(job.get("tank_factor", 1.0))
    if f != 1.0:
        rows = []
        for it in case.split(","):
            c, _, s = it.partition(":")
            rows.append(f"{c}:{float(s) * (1.0 if c.startswith(TANK_A4_SKIP) else f):.6g}")
        case = ",".join(rows)
    for ref, fac in (job.get("part_scale") or {}).items():
        hit = [p for p in heat["parts"] if p["ref"] == ref]
        if not hit:
            raise KeyError(ref)
        for p in hit:
            p["watts_nominal"] *= fac
            p["watts_worst"] *= fac
    HEAT_DIR.mkdir(parents=True, exist_ok=True)
    path = HEAT_DIR / f"heat_{job_key(job)}.json"
    path.write_text(json.dumps(heat))
    return case, path


def run_one(job):
    sys.dont_write_bytecode = True
    out = out_path(job)
    key = job_key(job)
    if out.exists():
        try:
            if json.loads(out.read_text()).get("job_key") == key:
                return f"cached {out.parent.name}/{out.name}"
        except json.JSONDecodeError:
            pass
    sys.path.insert(0, str(REPO_CONV if job["model"] == "repo" else MOD_CONV))
    import body_runs as br  # noqa: E402
    import thermal_body as tb  # noqa: E402
    assert Path(tb.__file__).resolve().parent == (REPO_CONV if job["model"] == "repo" else MOD_CONV).resolve(), tb.__file__
    # every input comes from the frozen pinned tree (freeze.py), never the live worktree
    assert FROZEN.resolve() in Path(br.rs.__file__).resolve().parents, br.rs.__file__
    assert FROZEN.resolve() in Path(br.rs.GEOM).resolve().parents, br.rs.GEOM
    case, heat_path = build_inputs(br, job)
    br.op_inputs = lambda _op, _c=(case, heat_path, "nominal"): _c
    brd = tb.Board(br.rs.GEOM, CACHE)
    kw = {}
    if job.get("leads") is not None:
        assert job["model"] == "mod"
        L = job["leads"]
        kw["leads"] = {"pad": "2", "g": L["g"], "t_rise": {r: t - L["bay_c"] for r, t in L["t_case_c"].items()}}
    t0 = time.time()
    res = br.run_case(brd, job["case"].split("_")[0], 10, job["pitch"], "fraction", "network", {}, None, None, True, True,
                      label=f"{job['config']}/{job['case']}", return_rise=bool(job.get("save_field")), **kw)
    if job.get("save_field"):
        res, rise = res
        import numpy as np  # noqa: E402
        out.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(out.with_suffix(".npz"), rise=rise, job_key=np.array(key))
    res["board_sha256"] = brd.data["board_sha256"]
    assert res["board_sha256"] == BOARD_SHA, res["board_sha256"]
    res["job"] = job
    res["job_key"] = key
    res["a4_case"] = case
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, indent=1) + "\n")
    return f"solved {out.parent.name}/{out.name} in {time.time() - t0:.0f} s"


def run_jobs(jobs, workers=4):
    todo = []
    for j in jobs:
        o = out_path(j)
        if o.exists():
            try:
                if json.loads(o.read_text()).get("job_key") == job_key(j):
                    continue
            except json.JSONDecodeError:
                pass
        todo.append(j)
    todo.sort(key=lambda j: j["pitch"])            # 0.25 mm first: the long ones start early
    if not todo:
        return
    print(f"solve: {len(todo)} of {len(jobs)} jobs to run ({min(workers, 4)} workers)", flush=True)
    ctx = mp.get_context("spawn")
    from concurrent.futures import as_completed
    with ProcessPoolExecutor(max_workers=min(workers, 4), mp_context=ctx, max_tasks_per_child=1) as ex:
        futs = {ex.submit(run_one, j): j for j in todo}
        failed = []
        for fut in as_completed(futs):
            try:
                print("  " + fut.result(), flush=True)
            except Exception as e:  # report at once; keep the other solves running
                failed.append(futs[fut])
                print(f"  FAILED {futs[fut]['config']}/{futs[fut]['case']} p{futs[fut]['pitch']}: {e!r}", flush=True)
    if failed:
        raise SystemExit(f"solve: {len(failed)} job(s) failed")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("jobs")
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    run_jobs(json.loads(Path(a.jobs).read_text()), a.workers)


if __name__ == "__main__":
    main()
