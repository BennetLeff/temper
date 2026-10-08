#!/usr/bin/env python3
"""Round 18, 4a: summary of history.tsv for the converged 12-rank 1e-8 board solves.

    python3 history_summary.py [../logs/history.tsv]

Per mesh class (fine 0.35 mm, coarse 1.0 mm): iterations (median, range), the
Krylov share of ElmerSolver's total time, median setup (mesh load + assembly +
AMS + Hypre setup) and post (field calc + VTU + teardown) seconds, the cost
constant c = Krylov s per iteration x ranks / Mtets, and memory per tet
(largest rank's max RSS x 12 / tets: an upper estimate of the total).
"""
import csv
import statistics as st
import sys
from pathlib import Path

p = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / "logs" / "history.tsv"
r = list(csv.DictReader(open(p), delimiter="\t"))
for name, key in (("fine 0.35 mm", "e0p35"), ("coarse 1.0 mm", "e1p0")):
    xs = [x for x in r if key in x["run"] and x["converged"] == "True" and x["np"] == "12" and x["tol"] == "1e-08"]
    its = [int(x["iterations"]) for x in xs]
    kr = [float(x["krylov_s"]) / float(x["total_s"]) for x in xs]
    setup = [sum(float(x[k]) for k in ("load_s", "assembly_s", "ams_setup_s", "hypre_setup_s")) for x in xs]
    post = [float(x["post_s"]) for x in xs]
    c = [float(x["s_per_it_per_Mtet_rank"]) for x in xs]
    kb = [float(x["rank_maxrss_GB"]) * 12 / int(x["tets"]) * 1e6 for x in xs]
    print(f"{name}: {len(xs)} solves; iterations median {st.median(its):.0f} (range {min(its)}-{max(its)}); "
          f"Krylov share {min(kr) * 100:.1f}-{max(kr) * 100:.1f} %; setup median {st.median(setup):.0f} s; "
          f"post median {st.median(post):.0f} s; c median {st.median(c):.2f} s*rank/(it*Mtet); "
          f"memory {min(kb):.2f}-{max(kb):.2f} kB/tet")
