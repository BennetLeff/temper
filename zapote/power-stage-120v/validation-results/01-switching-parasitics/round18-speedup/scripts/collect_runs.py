#!/usr/bin/env python3
"""Round 18: one TSV row per experiment run (remote ~/temper-fem/speedup/runs).

    python3 collect_runs.py ~/temper-fem/speedup/runs > runs.tsv

Columns: run, mesh, np, solver lines, Hypre method, iterations, final residual,
Krylov seconds, s per iteration, energy-derived L (nH), peak memory per rank (GB),
residual at iterations 250/500/1000/2000 (Hypre's relative residual print).
Runs marked "skipped" in their .out are listed as such.
"""
import json
import re
import sys
from pathlib import Path

LINE = re.compile(r"^\s*(\d+)\s+([0-9.e+-]+)\s+[0-9.]+\s+([0-9.e+-]+)\s*$", re.M)
root = Path(sys.argv[1]).expanduser()
print("run\tmesh\tnp\tsolver_lines\tmethod\titerations\tfinal_res\tkrylov_s\ts_per_it\tL_nH\tpeak_GB_rank\tres250\tres500\tres1000\tres2000")
for out in sorted(root.glob("*.out")):
    name = out.stem
    js = [l for l in out.read_text(errors="replace").splitlines() if l.startswith("{")]
    r = json.loads(js[-1]) if js else {}
    if r.get("skipped"):
        print(f"{name}\tskipped: {r['skipped']}")
        continue
    log = root / name / "solver.log"
    t = log.read_text(errors="replace") if log.exists() else ""
    m = re.search(r"Required iterations (\d+) \(method (\d+)\) to norm (\S+)", t)
    k = re.search(r"Solution time \(method \d+\): (\S+)", t)
    e = re.findall(r"Magnetic Field Energy:\s+(\S+)", t)
    hist = {int(a): c for a, _, c in LINE.findall(t)}
    its = int(m[1]) if m else None
    ks = float(k[1]) if k else None
    L = 2e9 * float(e[-1]) if e else None
    cols = [name, Path(r.get("mesh", "")).name, r.get("np", ""), ";".join(r.get("solver_lines") or []),
            m[2] if m else "", its, m[3] if m else "", ks, f"{ks / its:.4f}" if its and ks else "",
            f"{L:.5f}" if L else "", r.get("peak_memory_GB", "")] + [hist.get(i, "") for i in (250, 500, 1000, 2000)]
    print("\t".join("" if c is None else str(c) for c in cols))
