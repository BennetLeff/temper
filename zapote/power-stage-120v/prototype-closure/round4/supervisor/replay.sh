#!/usr/bin/env bash
# Rebuild review artifacts; this never touches native19 or emits fabrication files.
set -euo pipefail
HERE=$(cd -- "$(dirname -- "$0")" && pwd)
ROOT=$(git -C "$HERE" rev-parse --show-toplevel)
OUT="$ROOT/output/temper-prototype-closure/round4/supervisor"
TMP_DIR=$(mktemp -d "${TMPDIR:-/tmp}/temper-supervisor.XXXXXX")
trap 'rm -rf "$TMP_DIR"' EXIT
mkdir -p "$OUT"
printf '%s\n' 'INCOMPLETE: replay in progress' > "$OUT/replay-status.txt"
(cd "$HERE" && shasum -a 256 circuit.rs render.py report.py replay.sh > "$TMP_DIR/inputs.sha256")
rustc --edition=2021 "$HERE/circuit.rs" -o "$TMP_DIR/circuit"
"$TMP_DIR/circuit" "$HERE/generated" | tee "$OUT/structural-audit.txt"
rustc --edition=2021 --test "$HERE/circuit.rs" -o "$TMP_DIR/tests"
"$TMP_DIR/tests" | tee "$OUT/tests.txt"
(cd "$HERE/generated" && "${ATO_BIN:-ato}" build --target netlist > "$HERE/atopile-build.log" 2>&1)
"${ATO_PYTHON:-python3}" "$ROOT/zapote/power-stage-120v/tools/circuit_export.py" "$HERE/generated" "$HERE/generated/resolved-components.json" --entry-file supervisor.ato --entry Supervisor > "$HERE/atopile-resolved.log" 2>&1
python3 "$HERE/render.py" verify-atopile | tee "$OUT/atopile-oracle.txt"
python3 "$HERE/render.py"
kicad-cli sch export netlist --format kicadxml -o "$OUT/kicad-netlist.xml" "$HERE/native/supervisor.kicad_sch" 2> "$OUT/kicad-stderr.txt"
python3 "$HERE/render.py" verify "$OUT/kicad-netlist.xml" | tee "$OUT/kicad-oracle.txt"
kicad-cli sch erc --format json -o "$OUT/erc.json" "$HERE/native/supervisor.kicad_sch" 2>> "$OUT/kicad-stderr.txt"
kicad-cli sch export pdf -o "$OUT/supervisor.pdf" "$HERE/native/supervisor.kicad_sch" 2>> "$OUT/kicad-stderr.txt"
(cd "$HERE" && shasum -a 256 -c "$TMP_DIR/inputs.sha256")
python3 "$HERE/report.py" "$OUT"
printf '%s\n' 'PASS source/compile/connectivity checks; DESIGN NOT RELEASED; see evidence.json and README.md' > "$OUT/replay-status.txt"
