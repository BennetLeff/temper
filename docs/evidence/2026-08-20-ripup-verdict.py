# provenance: commit=bc3a19b063a26eb0eabc880494d1133496f0cdfb dirty=false
# Branch agent/ripup-production-path, branched from bc3a19b06
# (origin/agent/per-pairing-placement-route). The A* core these scripts
# instrument is byte-identical to origin/main at that commit. See
# docs/evidence/2026-08-20-ripup-production-path.md.
# pcb/temper.kicad_pcb sha256
# 26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b verified
# unchanged before AND after; never opened for writing. Every board written by
# these scripts goes to a scratch path outside the repo.
"""Verdict for named nets, same rule as analyze.py."""
import json
import sys
from collections import Counter
from pathlib import Path

T = json.loads(Path(sys.argv[1]).read_text())
names = sys.argv[2:]
S = T["run_summaries"][-1]
unb = T.get("pad_cells_after_unblock", {})
stm = T.get("pad_cells_after_stamp", {})
id2 = {v: k for k, v in S["net_ids"].items()}


def own(pl, gl):
    return pl == gl or pl in ("All", "all") or "*.Cu" in str(pl) or "Through" in str(pl)


for n in names:
    a = unb.get(n) or []
    b = {(r[0], r[1], r[3]): r[4] for r in (stm.get(n) or [])}
    nb, who = Counter(), Counter()
    for px, py, pl, gl, v0 in a:
        if not own(pl, gl):
            continue
        v1 = b.get((px, py, gl))
        if v0 == 0 and v1 == 0:
            nb["free"] += 1
        elif v0 == 0 and v1 not in (0, None):
            nb["HALO"] += 1
            who[f"halo:{id2.get(v1, v1)}"] += 1
        elif v0 == -1:
            nb["static"] += 1
        elif v0 is not None and v0 > 0:
            nb["STAMP"] += 1
            who[id2.get(v0, f"id{v0}")] += 1
        else:
            nb["?"] += 1
    v = ("HALO" if nb["HALO"] else "STAMP" if nb["STAMP"]
         else "static" if nb["static"] else "free/search-lost")
    print(f"{n:34s} {v:16s} cells={dict(nb)} reason={S['failure_reasons'].get(n)}")
    if who:
        print(f"       by: {dict(who)}")
