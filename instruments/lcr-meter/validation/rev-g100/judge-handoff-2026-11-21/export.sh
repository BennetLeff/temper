#!/bin/sh
# Frozen export of the Rev G100 order package for an independent judge (BRIEF.md in this folder).
#   sh validation/rev-g100/judge-handoff-2026-11-21/export.sh [OUT_DIR]
# Run from instruments/lcr-meter in a checkout that has the commits. Writes OUT_DIR (default
# ~/Documents/temper-handoffs/lcr-g100-judge-2026-11-21) and OUT_DIR.zip:
#   BRIEF.md                    the brief (from this folder)
#   instruments/lcr-meter/      git archive of SHA (tracked files only)
#   instruments/boardkit/       the shared board tooling the scripts import
#   instruments/lcr-meter/manufacturing/temper-lcr-gerbers.zip   the gitignored upload file, hash-checked
#   history/                    commit logs and per-commit source/doc patches (the export has no .git)
#   MANIFEST.txt                commit, hashes, file count
set -eu
SHA=412a11f7a
ZIP_SHA=ac6f45a6a8af1b21a5cd7a72e03637d6f95ca536834a5cd39923aa9f26498504
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
LCR=$(CDPATH= cd -- "$HERE/../../.." && pwd)
REPO=$(git -C "$LCR" rev-parse --show-toplevel)
OUT=${1:-$HOME/Documents/temper-handoffs/lcr-g100-judge-2026-11-21}
[ -e "$OUT" ] && { echo "$OUT exists; choose another OUT_DIR" >&2; exit 1; }
mkdir -p "$OUT"
git -C "$REPO" archive "$SHA" instruments/lcr-meter instruments/boardkit | tar -x -C "$OUT"
# The upload zip is gitignored: take it from the working tree only if it is the reviewed one.
got=$(shasum -a 256 "$LCR/manufacturing/temper-lcr-gerbers.zip" | cut -d' ' -f1)
[ "$got" = "$ZIP_SHA" ] || { echo "manufacturing/temper-lcr-gerbers.zip is $got, not $ZIP_SHA" >&2; exit 1; }
cp "$LCR/manufacturing/temper-lcr-gerbers.zip" "$OUT/instruments/lcr-meter/manufacturing/"
cp "$HERE/BRIEF.md" "$OUT/BRIEF.md"
# History: the export has no .git, so add the commit logs and per-commit patches of source and doc files
# (generated Gerbers, images and binaries are left out; their commits' --stat lists them).
mkdir -p "$OUT/history"
git -C "$REPO" log --stat --reverse 286f4c05f~1.."$SHA" -- instruments/lcr-meter > "$OUT/history/log-stat-g100.txt"
git -C "$REPO" log --stat a8e3e3211~2..a8e3e3211 > "$OUT/history/log-stat-rev-g-carry.txt"
i=0
for c in $(git -C "$REPO" rev-list --reverse 286f4c05f~1.."$SHA" -- instruments/lcr-meter) a8e3e3211~1 a8e3e3211; do
  i=$((i + 1))
  git -C "$REPO" show --format=fuller "$c" -- 'instruments/lcr-meter/*.py' 'instruments/lcr-meter/*.c' \
    'instruments/lcr-meter/*.h' 'instruments/lcr-meter/*.rs' 'instruments/lcr-meter/*.sh' 'instruments/lcr-meter/*.md' \
    'instruments/lcr-meter/*.txt' 'instruments/lcr-meter/*.csv' ':!instruments/lcr-meter/**/netlist.txt' \
    > "$OUT/history/$(printf %02d $i)-$(git -C "$REPO" rev-parse --short "$c").patch"
done
{
  echo "Rev G100 judge export"
  echo "commit      $(git -C "$REPO" rev-parse "$SHA") (study/lcr-rev-g100)"
  echo "rev-g carry $(git -C "$REPO" rev-parse a8e3e3211) (study/lcr-rev-g; not in this export)"
  echo "board       $(shasum -a 256 "$OUT/instruments/lcr-meter/cad/temper-lcr.kicad_pcb" | cut -d' ' -f1)"
  echo "gerber zip  $ZIP_SHA"
  echo "files       $(find "$OUT/instruments" -type f | wc -l | tr -d ' ')"
  echo "exported    $(date -u +%Y-%m-%dT%H:%MZ)"
} > "$OUT/MANIFEST.txt"
(cd "$(dirname "$OUT")" && zip -qr "$(basename "$OUT").zip" "$(basename "$OUT")")
echo "$OUT"
echo "$OUT.zip"
