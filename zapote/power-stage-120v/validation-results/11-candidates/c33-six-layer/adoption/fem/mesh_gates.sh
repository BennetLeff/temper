#!/bin/bash
# Mesh-only readiness check for chain_c33.sh (no solve): round 17's coarse reference mesh (campaign.py's exact
# mesher arguments for --cases 1:1.0) and its two gates (pec_columns: no inner far-field triangles; port_loops:
# every port a closed loop, every closure end on the main body; plus the mesher's own zero port leakage).
#   bash mesh_gates.sh BOARD LEG EXPORT SCRATCH      (BOARD s32 | s33; LEG A21 | B21)
# Gate logs land in mesh-gates/ next to this script; the .msh stays in SCRATCH (not committed).
set -euo pipefail
b=$1 leg=$2 export=$3 scratch=$4
here=$(cd "$(dirname "$0")" && pwd)
S=$(cd "$here/../../../../01-switching-parasitics/round17/scripts" && pwd)
py="python3 -B"
export PYTHONPATH=/opt/homebrew/lib
if [ "$b" = s33 ]; then export MESH_STACKUP=$(cd "$here/../../../../../native-21" && pwd)/stackup-6L.json; else unset MESH_STACKUP; fi
tag=leg$leg-h1-e1p0-$b
mkdir -p "$scratch" "$here/mesh-gates"
msh=$scratch/$tag.msh
$py "$S/mesh25d_hybrid.py" "$export" "$msh" --leg "$leg" --closures "$here/closures-leg${leg:0:1}-$b.json" \
  --arch-h 1 --h-edge 1.0 --h-far 4 --dz-max 0.45 --simplify 0.05 --margin 10 --air 10 > "$here/mesh-gates/$tag.log" 2>&1
$py "$S/pec_columns.py" "$msh" > "$here/mesh-gates/$tag.columns.txt" 2>&1
(cd "$S" && $py port_loops.py "$msh" "$here/mesh-gates/$tag.log" --closures "$here/closures-leg${leg:0:1}-$b.json") \
  > "$here/mesh-gates/$tag.loops.txt" 2>&1
shasum -a 256 "$msh" | awk '{print $1}' > "$here/mesh-gates/$tag.msh.sha256"
$py - "$here/mesh-gates/$tag" <<'EOF'
import json, sys
t = sys.argv[1]
res = lambda p: json.loads([l for l in open(p) if l.startswith("RESULT ")][-1][7:])
info, col, loops = res(t + ".log"), res(t + ".columns.txt"), res(t + ".loops.txt")
ok = (col["inner_farfield_triangles"] == 0 and all(p["leak_A"] <= 1e-9 for p in info["port_leak_A"])
      and all(p["closed_loop"] for p in loops["ports"]))
ends = {c["closure"]: (c["a_body"], c["b_body"]) for c in loops["closure_ends"]}
main_body = all(a == [0] and b == [0] for a, b in ends.values())
print(("GATES" if ok else "FAIL"), t.split("/")[-1], info["tets"], "tets; closure ends on main body:", main_body,
      {k: v for k, v in ends.items() if v != ([0], [0])})
EOF
