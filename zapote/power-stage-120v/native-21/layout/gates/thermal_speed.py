#!/usr/bin/env python3
"""B3 ratings speed harness (round-3 agents, the box): time run_basis.py and require the same results.

    python3 thermal_speed.py baseline REPO REF [--cpus 0-5,12-17]   # once, on the untouched copy
    python3 thermal_speed.py check REPO REF [--cpus LIST] [--tol 0.01]

REPO is a copy of the temper tree holding zapote/power-stage-120v/validation-results/04-board-current-thermal/
round5-native21. Each run is `run_basis.py --workers 4` there (its own cap; keep it: the gain must come from the
algorithm, not from more cores), timed end to end with a cold runs/ (its cache too, as on a new board), pinned to
--cpus (taskset; one 6-core CCD of the box, so two agents do not disturb each other) and with every BLAS / OpenMP pool
at --threads (default 1; the reference was taken the same way, so thread tuning is not what is measured). check
passes only when
  - margins.json (the gate's output: rows rounded to 0.1 K, verdicts, ratchet) is identical to REF's, and
  - every runs/*.json matches REF's field by field: same keys, same strings / booleans / list lengths, numbers within
    --tol (absolute, default 0.01: temperatures in K, watts, mm), skipping keys that are timing or solver diagnostics
    (IGNORED below: they may change with a faster solver), and
  - every solve's balance.relative_residual (the true ||Mx - b|| / ||b||) is <= RESID_MAX: the solver tolerance (CG
    rtol 1e-10) is part of the model, not a speed knob.
A faster solver is expected to differ in the last digits, not in any reported temperature at 0.01 K.
"""
import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

PY = sys.executable
SUB = Path("zapote/power-stage-120v/validation-results/04-board-current-thermal/round5-native21/b3-ratings")
IGNORED = {"runtime_s", "cg_iterations", "relative_residual", "picard_steps", "max_dT_k"}
RESID_MAX = 1.05e-10
THREAD_VARS = ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS")


def run(repo, cpus, threads):
    d = Path(repo) / SUB
    shutil.rmtree(d / "runs", ignore_errors=True)
    env = dict(os.environ, **{v: str(threads) for v in THREAD_VARS})
    cmd = [PY, "run_basis.py", "--workers", "4"]
    if cpus:
        cmd = ["taskset", "-c", cpus] + cmd
    t = time.perf_counter()
    r = subprocess.run(cmd, cwd=d, capture_output=True, text=True, env=env)
    dt = time.perf_counter() - t
    if not (d / "margins.json").exists() or not list((d / "runs").glob("*.json")):
        sys.exit(f"thermal_check: run_basis.py produced no results (exit {r.returncode}):\n{r.stdout[-3000:]}\n"
                 f"{r.stderr[-3000:]}")
    return dt, r.returncode, d


def diff(a, b, path, tol, out):
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if k in IGNORED:
                continue
            if k not in a or k not in b:
                out.append(f"{path}.{k}: only in {'reference' if k in a else 'candidate'}")
            else:
                diff(a[k], b[k], f"{path}.{k}", tol, out)
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            out.append(f"{path}: length {len(a)} -> {len(b)}")
        for i, (x, y) in enumerate(zip(a, b)):
            diff(x, y, f"{path}[{i}]", tol, out)
    elif isinstance(a, bool) or isinstance(b, bool) or not (isinstance(a, (int, float)) and isinstance(b, (int, float))):
        if a != b:
            out.append(f"{path}: {a!r} -> {b!r}")
    elif not (math.isclose(a, b, abs_tol=tol) or (math.isnan(a) and math.isnan(b))):
        out.append(f"{path}: {a} -> {b} (|d| {abs(a - b):.3g})")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", choices=("baseline", "check"))
    ap.add_argument("repo")
    ap.add_argument("ref")
    ap.add_argument("--tol", type=float, default=0.01)
    ap.add_argument("--cpus", default="", help="taskset CPU list (default: no pinning)")
    ap.add_argument("--threads", type=int, default=1)
    a = ap.parse_args()
    ref = Path(a.ref).resolve()
    dt, rc, d = run(a.repo, a.cpus, a.threads)
    if a.mode == "baseline":
        shutil.rmtree(ref, ignore_errors=True)
        (ref / "runs").mkdir(parents=True)
        for f in (d / "runs").glob("*.json"):
            shutil.copyfile(f, ref / "runs" / f.name)
        shutil.copyfile(d / "margins.json", ref / "margins.json")
        per = {f.stem: json.loads(f.read_text()).get("runtime_s") for f in sorted((ref / "runs").glob("*.json"))}
        (ref / "time.json").write_text(json.dumps({"seconds": round(dt, 1), "exit": rc, "cpus": a.cpus,
                                                   "threads": a.threads, "runtime_s": per}, indent=1) + "\n")
        print(f"baseline {dt:.1f} s (run_basis exit {rc}), {len(list((ref / 'runs').glob('*.json')))} run files -> {ref}")
        return
    base = json.loads((ref / "time.json").read_text())
    problems = []
    if rc != base["exit"]:
        problems.append(f"run_basis exit {base['exit']} -> {rc}")
    if (d / "margins.json").read_bytes() != (ref / "margins.json").read_bytes():
        problems.append("margins.json differs:")
        diff(json.loads((ref / "margins.json").read_text()), json.loads((d / "margins.json").read_text()),
             "margins", 0.0, problems)
    names = sorted(f.name for f in (ref / "runs").glob("*.json"))
    got = sorted(f.name for f in (d / "runs").glob("*.json"))
    if names != got:
        problems.append(f"run files {names} -> {got}")
    per = {}
    for n in names:
        if (d / "runs" / n).exists():
            c = json.loads((d / "runs" / n).read_text())
            diff(json.loads((ref / "runs" / n).read_text()), c, n, a.tol, problems)
            if "balance" not in c:
                continue                                   # heat_*.json: inputs, compared above
            per[n[:-5]] = c.get("runtime_s")
            rr = c["balance"].get("relative_residual")
            if rr is None or not rr <= RESID_MAX:
                problems.append(f"{n}: balance.relative_residual {rr} > {RESID_MAX}")
    print(f"time {dt:.1f} s against {base['seconds']} s (x{base['seconds'] / dt:.2f}); "
          + ("SAME RESULTS" if not problems else f"FAIL: {len(problems)} difference(s)"))
    print("  per run (s): " + ", ".join(f"{k} {v} (ref {base['runtime_s'].get(k)})" for k, v in per.items()))
    for p in problems[:40]:
        print("  " + p)
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
