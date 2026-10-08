#!/usr/bin/env python3
"""Round 18, hypothesis 3: iterations a looser stopping tolerance would save.

    python3 tol_savings.py RUN_DIR... > tol_savings.tsv

For each converged Hypre GMRES run (solver.log with Hypre's per-iteration
print), the first iteration whose relative residual is <= 1e-5, 1e-6, 1e-7,
and the final count (to the run's own tolerance), plus the fraction of the
Krylov time each looser tolerance would save (iterations are uniform in cost
within a run, so the fraction of iterations is the fraction of Krylov time).
"""
import re
import sys
from pathlib import Path

LINE = re.compile(r"^\s*(\d+)\s+([0-9.e+-]+)\s+[0-9.]+\s+([0-9.e+-]+)\s*$", re.M)
print("run\tfinal_its\tfinal_res\tit_1e-5\tit_1e-6\tit_1e-7\tsave_1e-7\tsave_1e-6\tsave_1e-5")
for d in sys.argv[1:]:
    log = Path(d) / "solver.log"
    try:
        t = log.read_text(errors="replace")
    except OSError:
        continue
    m = re.search(r"SolveHypre: Required iterations (\d+) \(method 802\) to norm (\S+)", t)
    if not m:
        continue
    hist = [(int(a), float(c)) for a, _, c in LINE.findall(t)]
    n = int(m[1])
    first = {tol: next((i for i, r in hist if r <= tol), None) for tol in (1e-5, 1e-6, 1e-7)}
    sv = {tol: (1 - first[tol] / n) if first[tol] else None for tol in first}
    f = lambda x: "" if x is None else (f"{x:.3f}" if isinstance(x, float) else str(x))
    print("\t".join([d, str(n), m[2], f(first[1e-5]), f(first[1e-6]), f(first[1e-7]),
                     f(sv[1e-7]), f(sv[1e-6]), f(sv[1e-5])]))
