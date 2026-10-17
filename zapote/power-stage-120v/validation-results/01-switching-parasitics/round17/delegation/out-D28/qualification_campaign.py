"""Invoke unchanged D-22 qualification for the declared adjacent-step pairs."""
from __future__ import annotations
import json
from pathlib import Path
import subprocess
import sys
HERE=Path(__file__).resolve().parent
pairs=[]
for row in json.loads((HERE/'refinement.json').read_text()):
    fine=row['label']
    pairs.append((fine.removesuffix('-s0.5')+'-s1',fine))
for manifest in ('quarter-step.json','candidate-refinement.json'):
    for row in json.loads((HERE/manifest).read_text()):
        fine=row['label']
        pairs.append((fine.removesuffix('-s0.25')+'-s0.5',fine))
for coarse,fine in pairs:
    subprocess.run([sys.executable,str(HERE/'qualify.py'),coarse,fine],check=True)
(HERE/'qualification-pairs.json').write_text(json.dumps(pairs,indent=2)+'\n')
