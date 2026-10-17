#!/bin/zsh
set -euo pipefail

# Changes only the private copied attempt-4 dependencies, never round-7.
BUILD=/tmp/ps-r8-palace-build4
OLD=/tmp/ps-r6-fem-build1
RECORD=${0:A:h}/raw/build-records
mkdir -p "$RECORD"

for name in libceed.dylib libxsmm.1.dylib libxsmmgen.1.dylib; do
  otool -L "$BUILD/lib/$name" > "$RECORD/$name.otool-before.txt"
  shasum -a 256 "$BUILD/lib/$name" > "$RECORD/$name.sha256-before.txt"
done

install_name_tool -id "$BUILD/lib/libxsmm.1.dylib" "$BUILD/lib/libxsmm.1.dylib"
install_name_tool -id "$BUILD/lib/libxsmmgen.1.dylib" "$BUILD/lib/libxsmmgen.1.dylib"
install_name_tool -change "$OLD/lib/libxsmm.1.dylib" \
  "$BUILD/lib/libxsmm.1.dylib" "$BUILD/lib/libceed.dylib"

for name in libceed.dylib libxsmm.1.dylib libxsmmgen.1.dylib; do
  otool -L "$BUILD/lib/$name" > "$RECORD/$name.otool-after.txt"
  shasum -a 256 "$BUILD/lib/$name" > "$RECORD/$name.sha256-after.txt"
  if rg -q "$OLD" "$RECORD/$name.otool-after.txt"; then
    print -u2 "Old build prefix remains in $name dependency closure"
    exit 1
  fi
done
