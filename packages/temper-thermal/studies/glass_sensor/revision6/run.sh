#!/bin/sh
set -eu
cd "$(dirname "$0")"
# A provenance snapshot only describes the last wholly successful run.
rm -f source-provenance.json
./contact/run.sh
./contact/check_runner.sh
./observer/run.sh
./observer/check_fault_mutations.sh
./optical/run.sh
./seal/run.sh
# Normalize captured terminal logs without changing their recorded messages.
python3 - <<'PYLOG'
from pathlib import Path
for path in Path('.').rglob('*.txt'):
    path.write_text(path.read_text().rstrip() + '\n')
PYLOG
python3 build_report.py
python3 provenance.py
