#!/bin/sh
# Reproduce every number in README.md (about 15 s). Needs Python 3 with numpy.
# Reuses ../rev-e-improvements (front-end model, draws, commercial specs) and ../virtual-instrument.
set -eu
cd "$(dirname "$0")"
mkdir -p results
python3 -W ignore accuracy_map.py > /dev/null
python3 -W ignore attribution.py
python3 -W ignore variants.py
python3 - <<'PY'
import json, platform, subprocess, numpy
from pathlib import Path
head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
Path("results/provenance.json").write_text(json.dumps(dict(python=platform.python_version(), numpy=numpy.__version__,
                                                           git_head=head), indent=1))
PY
echo "done: results/ in $(pwd)"
