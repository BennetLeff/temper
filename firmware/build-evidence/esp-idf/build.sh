#!/usr/bin/env bash
# Reproduce the ESP-IDF build of the Temper firmware (evidence for build-evidence/esp-idf/README.md).
# Requires ESP-IDF v5.3.6 at $IDF_DIR with `./install.sh esp32s3` already run.
# Needs `python3 -m pip install jinja2` for the generators, or they fall back to the committed headers.
#   Step 1 STRICT : the real build. Pass = exit 0.
#   Step 2 DIAG   : only if step 1 fails at LINK. Re-links with diag_stubs/ (abort() stubs for the unresolved symbols) so
#                   size/map data exist. The DIAG image is NOT flashable (26 functions have no
#                   production implementation); it is never a pass.
set -uo pipefail
IDF_DIR="${IDF_DIR:-$HOME/esp/esp-idf-v5.3.6}"
HERE="$(cd "$(dirname "$0")" && pwd)"
FW="$(cd "$HERE/../.." && pwd)"
BUILD="${BUILD_DIR:-$FW/build}"            # firmware/build/ is gitignored; never commit it
# shellcheck disable=SC1091
. "$IDF_DIR/export.sh" >/dev/null
cd "$FW"
# sdkconfig.evidence turns on CONFIG_TEMPER_POWER_HW_BINDING so the opt-in n21_hw_esp32.c compiles.
export SDKCONFIG_DEFAULTS="sdkconfig.defaults;build-evidence/esp-idf/sdkconfig.evidence"
IDF=(idf.py -B "$BUILD" -DSDKCONFIG="$BUILD/sdkconfig")
rm -rf "${BUILD:?}"
mkdir -p "$BUILD"
LOGS="$BUILD/evidence-logs"; mkdir -p "$LOGS"   # raw logs stay in the (gitignored) build dir
"${IDF[@]}" set-target esp32s3 > "$LOGS/set-target.log" 2>&1
"${IDF[@]}" build > "$LOGS/build-strict.log" 2>&1; STRICT_RC=$?
echo "STRICT build exit code: $STRICT_RC"
if [ "$STRICT_RC" -ne 0 ]; then
  grep -o "undefined reference to \`[A-Za-z_0-9]*'" "$LOGS/build-strict.log" | sed "s/.*\`//;s/'//" | sort -u > "$HERE/undefined-symbols.txt"
  "${IDF[@]}" -DEXTRA_COMPONENT_DIRS="$HERE/diag_stubs" reconfigure > "$LOGS/build-diag-link.log" 2>&1
  "${IDF[@]}" build >> "$LOGS/build-diag-link.log" 2>&1; DIAG_RC=$?
  echo "DIAG (non-flashable) link exit code: $DIAG_RC"
fi
"${IDF[@]}" size > "$HERE/size.txt" 2>&1
"${IDF[@]}" size-components > "$HERE/size-components.txt" 2>&1
# Trimmed logs (drop per-file "Building C object" lines and the repeated relocation noise)
trim() { grep -vE "Building (C|ASM|CXX) object|Built target|Generating|dangerous relocation|^-- (Found|Check|Detecting|Performing|Looking|Configuring|Adding|Component)" "$1" | sed "s|$FW/||g" | cut -c1-240; }
trim "$LOGS/build-strict.log" > "$HERE/build-strict.trimmed.log"
[ -f "$LOGS/build-diag-link.log" ] && trim "$LOGS/build-diag-link.log" > "$HERE/build-diag-link.trimmed.log"
# Which glue objects made it into the final ELF (per the linker map)
python3 "$HERE/mapsum.py" "$BUILD/induction_cooker.map" > "$HERE/linked-glue-objects.txt"
# Proof that every esp32 glue file was compiled
python3 - "$BUILD" "$FW" > "$HERE/compiled-glue-files.txt" <<'PY'
import json, sys, re
build, fw = sys.argv[1], sys.argv[2]
cc = json.load(open(f"{build}/compile_commands.json"))
for e in sorted(cc, key=lambda e: e["file"]):
    f = e["file"]
    if f.startswith(fw + "/") and re.search(r"(components/[^/]+/esp32/|/main/|n21_hw_esp32\.c)", f):
        out = re.search(r"-o (\S+)", e["command"]).group(1)
        print(f[len(fw)+1:], "->", out)
PY
exit "$STRICT_RC"
