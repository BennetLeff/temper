#!/usr/bin/env python3
"""Halve timestep for the candidate's short-dead-time/high-bus and S2/S4 corners."""
import hashlib
import json
from pathlib import Path
import sys
import run
run.VARIANTS={'baseline':(None,0,0),'off1_c1_neg2':(1,1,-2)}
run.CASES=[c for c in run.CASES if c[0]!='S1' or c[1]==280]
HERE=Path(__file__).resolve().parent
(HERE/'refine-provenance.json').write_text(json.dumps({
 'sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
 'variants':run.VARIANTS,'cases':run.CASES,'argv':sys.argv},indent=2)+'\n')
run.main()
