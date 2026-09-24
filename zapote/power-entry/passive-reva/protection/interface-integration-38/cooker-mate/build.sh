#!/usr/bin/env bash
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
stage="$(mktemp -d "${TMPDIR:-/tmp}/temper-cooker-mate.XXXXXX")"
rmdir "$stage"

python3 "$here/../tools/build_cooker_mate_source.py" "$stage"
echo "Built netlist: $stage/build/default.net"
echo "Built BOM: $stage/build/default.csv"
rustc --edition=2021 "$here/../audit.rs" -o "$stage/cooker-mate-audit"
"$stage/cooker-mate-audit" --cooker-mate "$stage/build/default.net" "$stage/build/default.csv"
