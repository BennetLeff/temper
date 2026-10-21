#!/bin/sh
# Reproduce every number in README.md.
#   ./rerun.sh            analysis only (uses committed data/transfer_*.npz), ~25 min
#   ./rerun.sh --spice    also re-extract the SPICE transfer models first (ngspice 45.2 + KLU), ~5 min more
# Needs: Rust (cargo/rustc), Python 3 with numpy, git, and for --spice ngspice with KLU and the
# vendor models in ../../sources/ti/models (gitignored; hashes in data/provenance.json).
set -eu
cd "$(dirname "$0")"
HERE=$(pwd)
REPO=$(git rev-parse --show-toplevel)
mkdir -p work/bin results data

# Host CLI from the COMMITTED snapshot (not the working tree), dedicated target dir.
# Pinned: synth.py writes protocol-1 records; host commits from e4e41c31a on speak protocol 2.
COMMIT=${HOST_COMMIT:-ff1ffb45b}
rm -rf work/host-src && mkdir -p work/host-src
git -C "$REPO" archive "$COMMIT" instruments/lcr-meter/host | tar -x -C work/host-src
TARGET=${VI_CARGO_TARGET_DIR:-${TMPDIR:-/tmp}/vi-host-target}
(cd work/host-src/instruments/lcr-meter/host && CARGO_TARGET_DIR="$TARGET" cargo build --locked --release)
cp "$TARGET/release/temper-lcr" work/bin/
echo "$COMMIT" > data/host-commit.txt

# strict-order / true-OP helper (reuses ../solver-resolution-rev-c-final/strict_order.rs)
rustc --edition 2021 -O -o work/op_guard op_guard.rs

python3 - <<'EOF'
import hashlib, json, platform, subprocess, numpy
from pathlib import Path
m = Path("../../sources/ti/models")
prov = dict(python=platform.python_version(), numpy=numpy.__version__,
            ngspice=subprocess.run(["ngspice", "--version"], capture_output=True, text=True).stdout.split("\n")[1].strip(),
            models={p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(m.glob("*.lib"))} if m.exists() else {},
            host_commit=Path("data/host-commit.txt").read_text().strip())
Path("data/provenance.json").write_text(json.dumps(prov, indent=1))
print(prov)
EOF

if [ "${1:-}" = "--spice" ]; then
  for c in base r33 gain2 again4 r5k riso22 riso22_c100 riso22_c200 base_c100 base_c200 riso22_lo100; do
    python3 chain_spice.py "$c"
  done
  for c in base_c80 base_c120 base_c160 base_c240 riso22_c80 riso22_c120 riso22_c160 riso22_c240; do
    python3 chain_spice.py "$c" --signal-only
  done
  for i in 1 2 3 4 5 6; do python3 chain_spice.py base --instance "$i"; done
  python3 validate_transfer.py
fi

python3 noise_budget.py
python3 spur_alias.py
python3 mc.py baseline
python3 mc.py corner
python3 mc.py whatif
python3 mc.py leadmove
python3 summarize.py
echo "done: results/ in $HERE"
