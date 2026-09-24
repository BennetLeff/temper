#!/usr/bin/env bash
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo="$(cd "$here/../../../../../.." && pwd)"
stage="$(mktemp -d "${TMPDIR:-/tmp}/temper-cooker-mate.XXXXXX")"
ato_bin="${ATO_BIN:-ato}"

# Atopile 0.2.69's netlist exporter requires every imported source to live
# beneath its project directory. Stage the unmodified cooker source together
# with this derivative, preserving their repository-relative paths.
mkdir -p "$stage/elec" "$stage/zapote/power-entry/passive-reva/protection/interface-integration-38/cooker-mate/elec"
cp -R "$repo/elec/src" "$stage/elec/"
cp -R "$here/elec/src" "$stage/zapote/power-entry/passive-reva/protection/interface-integration-38/cooker-mate/elec/"
cat > "$stage/ato.yaml" <<'EOF'
ato-version: 0.2.69
builds:
  cooker_mate:
    entry: zapote/power-entry/passive-reva/protection/interface-integration-38/cooker-mate/elec/src/cooker_mate.ato:CookerMate38
EOF

echo "Staged Atopile project: $stage"
if ! (cd "$stage" && "$ato_bin" --non-interactive build > build.log 2>&1); then
    tail -60 "$stage/build.log" >&2
    exit 1
fi
echo "Built netlist: $stage/build/cooker_mate.net"
echo "Built BOM: $stage/build/cooker_mate.csv"
