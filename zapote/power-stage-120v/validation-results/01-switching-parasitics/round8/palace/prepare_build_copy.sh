#!/bin/zsh
set -euo pipefail

OLD=/tmp/ps-r6-fem-build1
BUILD=/tmp/ps-r8-palace-build4
if test -e "$BUILD"; then
  print -u2 "Private attempt-4 build already exists: $BUILD"
  exit 1
fi
cp -cR "$OLD" "$BUILD"
python3 - "$OLD" "$BUILD" <<'PY'
from pathlib import Path
import subprocess
import sys

old, new = (value.encode() for value in sys.argv[1:])
paths = subprocess.check_output(
    ['rg', '-l', '-0', '-F', old.decode(), new.decode()]
).split(b'\0')
count = 0
for raw in paths:
    if not raw:
        continue
    path = Path(raw.decode())
    original = path.read_bytes()
    updated = original.replace(old, new)
    if updated != original:
        path.write_bytes(updated)
        count += 1
print(f'Relocated {count} generated text files')
PY
