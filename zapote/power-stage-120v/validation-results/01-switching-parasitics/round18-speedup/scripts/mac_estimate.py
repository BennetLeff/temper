#!/usr/bin/env python3
"""Round 18: could the Mac take coarse cases off the remote box? (ESTIMATES)

    python3 mac_estimate.py [../logs/history.tsv]

Evidence: the only board solves run on the Mac are round 17's leg-A h1 e0.7
case (camp2/legA-h1-e0p7-P*, 3,468,764 tets, 10 ranks, BSD time: max RSS of
the largest rank). From them: the Mac's cost constant c = Krylov s per
iteration x ranks / Mtet, and memory per tet (largest rank x ranks / tets).
The remote's c is the median of the coarse 12-rank solves in history.tsv.
Mac budget (memory note "Mac MPI core budget"): 8 ranks, 32 GB RAM of which
~26 GB usable for a solve, ~28 GB free disk (field files deleted per case).

Per case: Mac wall / remote wall = (c_mac / 8) / (c_remote / 12) at the
same iteration count (iteration counts depend on the solver, not the machine).
"""
import csv
import statistics as st
import sys
from pathlib import Path

p = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / "logs" / "history.tsv"
r = list(csv.DictReader(open(p), delimiter="\t"))
mac = [x for x in r if "legA-h1-e0p7-P" in x["run"] and x["converged"] == "True"]
rem = [x for x in r if "e1p0" in x["run"] and x["converged"] == "True" and x["np"] == "12" and x["tol"] == "1e-08"]
c_mac = sorted(float(x["s_per_it_per_Mtet_rank"]) for x in mac)
kb_mac = [float(x["rank_maxrss_GB"]) * int(x["np"]) / int(x["tets"]) * 1e6 for x in mac]
c_rem = st.median(float(x["s_per_it_per_Mtet_rank"]) for x in rem)
print(f"Mac (10 ranks, 4 solves): c = {', '.join(f'{c:.2f}' for c in c_mac)}; memory {min(kb_mac):.1f}-{max(kb_mac):.1f} kB/tet")
print(f"remote coarse (12 ranks): c median {c_rem:.2f}")
for label, c in (("best 3 of 4", st.median(c_mac[:3])), ("worst", c_mac[-1])):
    ratio = (c / 8) / (c_rem / 12)
    print(f"  Mac wall / remote wall at 8 ranks ({label}): {ratio:.2f}")
USABLE_GB, KB = 26.0, 6.1          # conservative: remote's 6.1 kB/tet, not the Mac's lower figure
cases = {  # tets (M), from chain_estimate.py (measured h1 meshes, n19 ladder for the rest)
    "B21 h0p5": 2.42, "B21 h2": 3.10, "B21 h3": 3.48, "B21 m20": 3.59,
    "A21 h0p5": 3.01, "A21 h2": 3.85, "A21 h3": 4.32, "A21 m20": 4.46}
print(f"\nfits in {USABLE_GB:.0f} GB at {KB} kB/tet (field files ~0.87 kB/tet/port: 4 ports kept until the matrix):")
for k, t in cases.items():
    mem, disk = t * KB, t * 0.87 * 4
    print(f"  {k:9s} {t:4.2f} M tets  {mem:5.1f} GB  disk {disk:4.1f} GB  {'fits' if mem <= USABLE_GB else 'NO'}")
