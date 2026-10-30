"""Snapshot the JLC assembly-library entry of every LCSC code in bom-complete.csv (read-only search).

python3 manufacturing/prices/fetch_jlc_parts.py   ->  manufacturing/prices/jlc-parts-<today>.json

The fetch and the schema (which order_estimate.py reads) are temper_boardkit.jlc.parts.
"""
import csv
import sys
from pathlib import Path

MFG = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MFG.parent / 'cad' / 'tools'))
import boardkit_path  # noqa: E402,F401
from temper_boardkit.jlc import parts  # noqa: E402

snap = parts.snapshot(row['LCSC'] for row in csv.DictReader(open(MFG / 'bom-complete.csv')))
dest = MFG / f'prices/jlc-parts-{snap["fetched"]}.json'
parts.write(dest, snap)
print(f'{len(snap["parts"])} parts -> {dest}')
