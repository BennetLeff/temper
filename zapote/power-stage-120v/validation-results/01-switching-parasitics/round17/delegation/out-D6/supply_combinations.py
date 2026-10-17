#!/usr/bin/env python3
"""Compare capacitor plus negative bias without the split resistor complexity."""
import hashlib
import json
from pathlib import Path
import sys
import run
run.VARIANTS={'c1_neg2':(None,1,-2),'c1_neg4':(None,1,-4)}
HERE=Path(__file__).resolve().parent
(HERE/'supply-combinations-provenance.json').write_text(json.dumps({
 'sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
 'variants':run.VARIANTS,'argv':sys.argv},indent=2)+'\n')
run.main()
