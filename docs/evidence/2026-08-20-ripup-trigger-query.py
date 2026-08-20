# provenance: commit=bc3a19b063a26eb0eabc880494d1133496f0cdfb dirty=false
# Branch agent/ripup-production-path, branched from bc3a19b06
# (origin/agent/per-pairing-placement-route). The A* core these scripts
# instrument is byte-identical to origin/main at that commit. See
# docs/evidence/2026-08-20-ripup-production-path.md.
# pcb/temper.kicad_pcb sha256
# 26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b verified
# unchanged before AND after; never opened for writing. Every board written by
# these scripts goes to a scratch path outside the repo.
"""What the rip-up trigger computed, and what happened to it."""
import json
import sys
from collections import Counter
from pathlib import Path

T = json.loads(Path(sys.argv[1]).read_text())
S = T["run_summaries"][-1]
ids = S["net_ids"]
id2 = {v: k for k, v in ids.items()}
routed = set(S["routed_paths"])

rets = T["identify_blocking_returns"]
nonempty = [(n, b) for n, b in rets if b]
print(f"_identify_blocking_nets calls          : {len(rets)}")
print(f"  ... returning a NON-EMPTY blocker set: {len(nonempty)}")
print("  ... i.e. that many non-empty ripped_ids lists were built and dropped")
print(f"_unmark_route_blocked calls            : {T['unmark_calls']}")
# Per-victim attribution comes from the failure reports, not from this probe:
# _identify_blocking_nets is called AFTER _astar_route_nlayer returns, so the
# probe's "current net" marker is already cleared by then.
print(f"nets whose failure report names blockers: {len(S['blocking_nets'])}")
print()
allb = Counter()
for _n, b in nonempty:
    for i in b:
        allb[id2.get(i, f"id{i}")] += 1
print(f"distinct nets nominated for rip-up     : {len(allb)}")
print("top nominees (net, times nominated, currently routed):")
for nm, c in allb.most_common(12):
    print(f"   {nm:32s} {c:4d}  routed={nm in routed}")
print()
print("victims (net that asked for a rip-up) and how many blockers it named:")
per = {}
for n, b in nonempty:
    per.setdefault(n, set()).update(b)
for n in sorted(per, key=lambda x: -len(per[x]))[:15]:
    print(f"   {str(n):32s} named {len(per[n]):3d} blockers   routed={n in routed}")
print()
print(f"blocking_nets recorded in failure reports (diagnostic only): "
      f"{len(S['blocking_nets'])} nets")
print(f"attempted_ripups values in those same reports: "
      f"{sorted(set(S['attempted_ripups'].values()))}")
