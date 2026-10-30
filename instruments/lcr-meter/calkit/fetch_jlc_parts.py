#!/usr/bin/env python3
"""Snapshot JLC's assembly-library entry for every LCSC code in manufacturing/bom-complete.csv.
Same schema as ../manufacturing/prices/jlc-parts-*.json (read by order_estimate.py), plus brand,
description and datasheet URL; the fetch is temper_boardkit.jlc.parts."""
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / 'cad' / 'tools'))
import boardkit_path  # noqa: E402,F401
from temper_boardkit.jlc import parts  # noqa: E402

snap = parts.snapshot((r['LCSC'] for r in csv.DictReader((ROOT / 'manufacturing/bom-complete.csv').open())), extra=True)
dest = ROOT / f'manufacturing/jlc-parts-{snap["fetched"]}.json'
parts.write(dest, snap)
print(f'{len(snap["parts"])} parts -> {dest.name}')
