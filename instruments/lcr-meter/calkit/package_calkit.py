#!/usr/bin/env python3
"""JLC BOM/CPL from the generator's placement record, cross-checked against KiCad's own
position export (build/positions.csv, kicad-cli, drill/place origin = lower-left corner)."""
import csv
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
rec = json.loads((ROOT / 'build/placement.json').read_text())
parts = rec['parts']
native = {r['Ref']: r for r in csv.DictReader((ROOT / 'build/positions.csv').open())}
assert set(native) == set(parts), (sorted(native), sorted(parts))
for ref, p in parts.items():
    r = native[ref]
    assert abs(float(r['PosX']) - p['x_mm']) < 1e-4 and abs(float(r['PosY']) - p['y_up_mm']) < 1e-4, ref
    assert (float(r['Rot']) - p['rot_deg']) % 360 == 0 and r['Side'] == 'top', ref

out = ROOT / 'manufacturing'
out.mkdir(exist_ok=True)


def write(name, header, rows):
    with (out / name).open('w', newline='') as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


groups = defaultdict(list)
for ref, p in parts.items():
    groups[p['lcsc']].append(ref)


def refkey(r):  # C2 < C10
    return (r[0], int(r[1:]))


bom, full = [], []
for lcsc, refs in sorted(groups.items(), key=lambda g: refkey(min(g[1], key=refkey))):
    refs.sort(key=refkey)
    p = parts[refs[0]]
    ascii_value = p['value'].replace(' ', '').replace('kΩ', 'k').replace('Ω', 'R').replace('µ', 'u')
    bom.append([f"{ascii_value} {p['mpn']}", ','.join(refs), p['footprint'].split(':')[1], lcsc])
    full.append([','.join(refs), len(refs), p['value'], p['manufacturer'], p['mpn'], lcsc,
                 p['footprint'], p['spec'], 'SMT'])
write('bom-jlcpcb.csv', ['Comment', 'Designator', 'Footprint', 'LCSC Part #'], bom)
write('bom-complete.csv', ['Designators', 'Quantity', 'Value', 'Manufacturer', 'MPN', 'LCSC',
                           'Footprint', 'Spec', 'Assembly'], full)
write('cpl-jlcpcb.csv', ['Designator', 'Mid X', 'Mid Y', 'Layer', 'Rotation'],
      [[ref, f"{p['x_mm']:.4f}mm", f"{p['y_up_mm']:.4f}mm", 'top', p['rot_deg'] % 360]
       for ref, p in sorted(parts.items(), key=lambda kv: refkey(kv[0]))])
print(f'{len(parts)} placements, {len(bom)} BOM lines; native position parity PASS')
