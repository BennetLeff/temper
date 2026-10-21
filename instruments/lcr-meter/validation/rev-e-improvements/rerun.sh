#!/bin/sh
# Reproduce every number in README.md (about 10 s). Needs Python 3 with numpy.
# Reuses ../virtual-instrument (vi_model.py replica of the host calibration, DUT library, targets) and
# ../rev-e-codec/results/noise_codec.json (cross-check only). No SPICE, no host build.
set -eu
cd "$(dirname "$0")"
mkdir -p results
python3 -W ignore validate.py
python3 -W ignore sensitivity.py
python3 -W ignore study.py
python3 -W ignore commercial.py
python3 - <<'EOF'
import json, platform, subprocess, numpy
from pathlib import Path
head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
Path("results/provenance.json").write_text(json.dumps(dict(python=platform.python_version(), numpy=numpy.__version__,
                                                           git_head=head), indent=1))
EOF
echo "done: results/ in $(pwd)"
