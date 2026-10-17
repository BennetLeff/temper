#!/bin/zsh
set -euo pipefail

link=${1:?pass generated link command file}
test -s "$link"
python3 - "$link" <<'PY'
from pathlib import Path
import shlex
import sys

line = Path(sys.argv[1]).read_text()
if '/opt/homebrew/lib/libgs' in line:
    raise SystemExit('Ghostscript libgs selected; refusing Palace link')
mfem = [
    token
    for token in shlex.split(line)
    if token == '-lmfem' or Path(token).name.startswith('libmfem.')
]
approved = '/tmp/ps-r8-palace-build4/lib/libmfem.a'
if mfem != [approved]:
    raise SystemExit(f'Expected exactly one approved MFEM archive, got {mfem}')
PY
print 'Palace link preflight passed'
