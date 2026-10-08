#!/bin/zsh
set -euo pipefail

HERE=${0:A:h}
LINK=/tmp/ps-r8-palace-build4/palace-build/CMakeFiles/palace.dir/link.txt
RECORD=$HERE/raw/build-records
mkdir -p "$RECORD"
zsh "$HERE/check_prelink.sh" "$LINK" > "$RECORD/prelink-positive.log" 2>&1
cp "$LINK" "$RECORD/prelink-negative-link.txt"
print ' /opt/homebrew/lib/libgs.dylib' >> "$RECORD/prelink-negative-link.txt"
if zsh "$HERE/check_prelink.sh" "$RECORD/prelink-negative-link.txt" \
  > "$RECORD/prelink-negative.log" 2>&1; then
  print -u2 'Negative control unexpectedly passed'
  exit 1
fi
rg -q 'Ghostscript libgs selected' "$RECORD/prelink-negative.log"
cp "$LINK" "$RECORD/prelink-extra-mfem-link.txt"
print ' /opt/homebrew/lib/libmfem.dylib' >> "$RECORD/prelink-extra-mfem-link.txt"
if zsh "$HERE/check_prelink.sh" "$RECORD/prelink-extra-mfem-link.txt" \
  > "$RECORD/prelink-extra-mfem.log" 2>&1; then
  print -u2 'Extra MFEM negative control unexpectedly passed'
  exit 1
fi
rg -q 'Expected exactly one approved MFEM archive' "$RECORD/prelink-extra-mfem.log"
cp "$LINK" "$RECORD/prelink-old-mfem-link.txt"
print ' /tmp/ps-r6-fem-build1/lib/libmfem.a' >> "$RECORD/prelink-old-mfem-link.txt"
if zsh "$HERE/check_prelink.sh" "$RECORD/prelink-old-mfem-link.txt" \
  > "$RECORD/prelink-old-mfem.log" 2>&1; then
  print -u2 'Historical MFEM negative control unexpectedly passed'
  exit 1
fi
rg -q 'Expected exactly one approved MFEM archive' "$RECORD/prelink-old-mfem.log"
print 'Prelink positive and negative controls passed'
