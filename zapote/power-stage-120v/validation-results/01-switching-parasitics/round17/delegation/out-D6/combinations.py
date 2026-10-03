#!/usr/bin/env python3
"""Follow-up combinations: the capacitor mitigates S4 VDS but costs gate delay."""
import hashlib
import json
from pathlib import Path
import sys
import run

run.VARIANTS = {'off1_c1':(1,1,0),'off1_c1_neg2':(1,1,-2)}
HERE=Path(__file__).resolve().parent
(HERE/'combinations-provenance.json').write_text(json.dumps({
    'sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    'variants':run.VARIANTS,'argv':sys.argv},indent=2)+'\n')
run.main()
