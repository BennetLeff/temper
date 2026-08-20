# provenance: commit=bc3a19b063a26eb0eabc880494d1133496f0cdfb dirty=false
# Branch agent/ripup-production-path, branched from bc3a19b06
# (origin/agent/per-pairing-placement-route). The A* core these scripts
# instrument is byte-identical to origin/main at that commit. See
# docs/evidence/2026-08-20-ripup-production-path.md.
# pcb/temper.kicad_pcb sha256
# 26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b verified
# unchanged before AND after; never opened for writing. Every board written by
# these scripts goes to a scratch path outside the repo.
"""Build reorder specs from an analyze.py --emit blob."""
import json
import sys
from pathlib import Path

an = json.loads(Path(sys.argv[1]).read_text())
outdir = Path(sys.argv[2])
stamped = an["stamped"]
victims = sorted(stamped, key=lambda n: stamped[n]["order"])

# 1. oracle-informed UPPER BOUND: every victim routes before anything else
(outdir / "reorder_promote.json").write_text(json.dumps({
    "mode": "promote_front", "nets": victims,
}, indent=2))

# 2. MINIMAL perturbation: each victim moves to just before its earliest blocker
pairs = []
for v in victims:
    cl = stamped[v]["claimers"]
    earliest = min(cl, key=lambda b: cl[b][1]) if cl else None
    if earliest is not None:
        pairs.append([v, earliest])
(outdir / "reorder_before.json").write_text(json.dumps({
    "mode": "before", "pairs": pairs,
}, indent=2))

print(f"victims ({len(victims)}): {victims}")
print(f"pairs   ({len(pairs)}): {pairs}")
