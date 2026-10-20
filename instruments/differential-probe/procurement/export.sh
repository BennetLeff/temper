#!/bin/sh
# Run from any directory. Regenerates only the draft procurement package.
set -eu
cd "$(dirname "$0")/.."
mkdir -p procurement/gerbers procurement/validation
kicad-cli version > procurement/validation/kicad-version.txt
kicad-cli sch erc --exit-code-violations cad/differential-probe.kicad_sch -o procurement/validation/erc.rpt
kicad-cli pcb drc --exit-code-violations --all-track-errors --format json -o procurement/validation/pcb-drc.json cad/differential-probe.kicad_pcb
kicad-cli pcb export gerbers --layers F.Cu,In1.Cu,In2.Cu,B.Cu,F.Mask,B.Mask,F.SilkS,B.SilkS,F.Paste,B.Paste,Edge.Cuts --subtract-soldermask --precision 6 -o procurement/gerbers/ cad/differential-probe.kicad_pcb
kicad-cli pcb export drill --format excellon --drill-origin absolute --excellon-units mm -o procurement/gerbers/ cad/differential-probe.kicad_pcb
kicad-cli pcb export pos --format csv --units mm --side both --exclude-dnp -o procurement/positions-raw.csv cad/differential-probe.kicad_pcb
kicad-cli sch export bom --fields Reference,Value,Footprint,MPN,Manufacturer,LCSC,QUANTITY,EXCLUDE_FROM_BOARD --labels Reference,Value,Footprint,MPN,Manufacturer,LCSC,Qty,Offboard --exclude-dnp --ref-range-delimiter '' -o procurement/components-raw.csv cad/differential-probe.kicad_sch

# Formatting only: schematic remains the part-selection authority; native KiCad
# positions remain the geometry authority. Reject any missing assembly position.
python3 - <<'PY'
import csv
import hashlib
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

out = Path('procurement')
with (out / 'components-raw.csv').open(newline='') as stream:
    components = list(csv.DictReader(stream))
onboard = [row for row in components if not row['Offboard'].strip()]
with (out / 'bom-jlc.csv').open('w', newline='') as stream:
    writer = csv.writer(stream)
    writer.writerow(['Comment', 'Designator', 'Footprint', 'LCSC Part #', 'MPN', 'Manufacturer'])
    for row in onboard:
        writer.writerow([row['Value'], row['Reference'], row['Footprint'], row['LCSC'].strip(), row['MPN'], row['Manufacturer']])
with (out / 'positions-raw.csv').open(newline='') as stream:
    positions = list(csv.DictReader(stream))
wanted = {row['Reference'] for row in onboard}
selected = [row for row in positions if row['Ref'] in wanted]
if len(selected) != len(wanted) or {row['Ref'] for row in selected} != wanted:
    raise SystemExit('BOM/position reference mismatch')
with (out / 'cpl-jlc.csv').open('w', newline='') as stream:
    writer = csv.writer(stream)
    writer.writerow(['Designator', 'Mid X', 'Mid Y', 'Layer', 'Rotation'])
    for row in selected:
        writer.writerow([row['Ref'], row['PosX'], row['PosY'], {'top': 'T', 'bottom': 'B'}[row['Side']], row['Rot']])
(out / 'validation' / 'assembly-parity.json').write_text(json.dumps({
    'onboard_references': len(wanted), 'position_references': len(selected),
    'excluded_positions': [row['Ref'] for row in positions if row['Ref'] not in wanted],
    'offboard_components': [row['Reference'] for row in components if row['Offboard'].strip()],
    'rotation_status': 'native KiCad; vendor placement preview review still required',
    'parts_status': 'exact MPN; blank LCSC fields require vendor sourcing, not substitution'
}, indent=2) + '\n')
with ZipFile(out / 'revb-gerbers.zip', 'w', compression=ZIP_DEFLATED) as archive:
    for path in sorted((out / 'gerbers').iterdir()):
        if path.is_file():
            entry = ZipInfo(path.name, date_time=(2026, 10, 20, 0, 0, 0))
            entry.compress_type = ZIP_DEFLATED
            archive.writestr(entry, path.read_bytes())
project_snapshot = out / 'validation' / 'source-project.json'
project_snapshot.write_bytes(Path('cad/differential-probe.kicad_pro').read_bytes())
inputs = [Path('cad/differential-probe' + suffix) for suffix in ('.kicad_pcb', '.kicad_sch', '.kicad_dru')] + [project_snapshot]
outputs = sorted((out / 'gerbers').iterdir()) + [out / name for name in ('bom-jlc.csv', 'cpl-jlc.csv', 'revb-gerbers.zip')]
(out / 'validation' / 'sha256.txt').write_text(''.join(
    f'{hashlib.sha256(path.read_bytes()).hexdigest()}  {path}\n' for path in inputs + outputs
))
print(f'Exported {len(wanted)} assembly references; no PCB or schematic edits.')
PY
