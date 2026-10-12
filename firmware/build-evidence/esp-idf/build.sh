#!/usr/bin/env bash
# Reproduce the ESP-IDF build of the Temper firmware (evidence for build-evidence/esp-idf/README.md).
# Requires ESP-IDF v5.3.6 at $IDF_DIR with `./install.sh esp32s3` already run.
# Needs `python3 -m pip install jinja2` for the generators, or they fall back to the committed headers.
#   Step 1 STRICT : the real build. Pass = exit 0.
#   Step 1b PROOF : on a strict pass, platform-symbols-nm.txt (nm proof that the 26 platform symbols
#                   are defined, which object defines them, no diag stub in the map) and bin-size.txt.
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
if [ "$STRICT_RC" -eq 0 ]; then
  # Strict image: prove each of the 26 platform symbols that failed to link at 4168c046a
  # (undefined-symbols.txt) is now defined in the ELF, by which object, and that no diag stub is in it.
  ELF="$BUILD/induction_cooker.elf"
  NM=xtensa-esp32s3-elf-nm
  {
    echo "# $NM over the strict image (induction_cooker.elf) and libmain.a; input: undefined-symbols.txt"
    echo "# columns: status | ELF address type symbol | defining object"
    while read -r s; do
      [ -z "$s" ] && continue
      line=$("$NM" "$ELF" | awk -v s="$s" '$3==s {print $1, $2, $3}')
      obj=$("$NM" -A --defined-only "$BUILD/esp-idf/main/libmain.a" 2>/dev/null | awk -v s="$s" '$NF==s {split($1,a,":"); print a[2]}' | head -1)
      case "$line" in
        *" T "*|*" t "*) echo "DEFINED | $line | ${obj:-?}" ;;
        *) echo "MISSING | $s | -" ;;
      esac
    done < "$HERE/undefined-symbols.txt"
    echo "# diag_stubs references in the link map: $(grep -c diag_stubs "$BUILD/induction_cooker.map" || true)"
  } > "$HERE/platform-symbols-nm.txt"
  if grep -q '^MISSING' "$HERE/platform-symbols-nm.txt" || ! grep -q 'diag_stubs references in the link map: 0$' "$HERE/platform-symbols-nm.txt"; then
    echo "STRICT image is missing a platform symbol or contains a diag stub"; STRICT_RC=3
  fi
  ls -l "$BUILD/induction_cooker.bin" | awk '{print "induction_cooker.bin", $5, "bytes"}' > "$HERE/bin-size.txt"
fi
"${IDF[@]}" size > "$HERE/size.txt" 2>&1
"${IDF[@]}" size-components > "$HERE/size-components.txt" 2>&1
# Trimmed logs (drop per-file "Building C object" lines and the repeated relocation noise)
trim() { grep -vE "Building (C|ASM|CXX) object|Built target|Generating|dangerous relocation|^-- (Found|Check|Detecting|Performing|Looking|Configuring|Adding|Component)" "$1" | sed "s|$BUILD|<BUILD>|g; s|$FW/||g" | cut -c1-240; }
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
