#!/bin/sh
# Run from any directory. Regenerates the copper-free FR4 tip plate and lead
# bridge (geometry from tools/leads.rs) and their JLC fabrication files.
set -eu
cd "$(dirname "$0")/.."
rustc --edition 2021 tools/leads.rs -o /tmp/temper-probe-leads
/tmp/temper-probe-leads > /dev/null
for part in tip-plate lead-bridge; do
  src="mech/$part/$part.kicad_pcb"
  out="procurement/mech/$part"
  rm -rf "$out"
  mkdir -p "$out"
  kicad-cli pcb drc --format json -o "$out/drc.json" "$src" > /dev/null
  # Copper-free parts: footprint-library lookups do not apply to generated NPTH holes.
  jq -e '([.violations[] | select(.type != "lib_footprint_issues")] | length) == 0 and (.unconnected_items | length) == 0' "$out/drc.json" > /dev/null \
    || { echo "DRC violations in $src"; jq '.violations[] | select(.type != "lib_footprint_issues") | .description' "$out/drc.json"; exit 1; }
  kicad-cli pcb export gerbers --layers F.Cu,B.Cu,F.Mask,B.Mask,F.SilkS,Edge.Cuts --precision 6 -o "$out/" "$src" > /dev/null
  kicad-cli pcb export drill --format excellon --drill-origin absolute --excellon-units mm -o "$out/" "$src" > /dev/null
  kicad-cli pcb export dxf --layers Edge.Cuts --output-units mm --mode-single -o "$out/$part-outline.dxf" "$src" > /dev/null
done
python3 - <<'PY'
import hashlib
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

lines = []
for part in ('tip-plate', 'lead-bridge'):
    d = Path('procurement/mech') / part
    z = Path('procurement') / f'{part}-gerbers.zip'
    with ZipFile(z, 'w', compression=ZIP_DEFLATED) as archive:
        for path in sorted(d.iterdir()):
            if path.suffix in ('.gbr', '.gm1', '.drl', '.gbrjob') or path.name.endswith(('.gtl', '.gbl', '.gto', '.gts', '.gbs')):
                entry = ZipInfo(path.name, date_time=(2026, 10, 20, 0, 0, 0))
                entry.compress_type = ZIP_DEFLATED
                archive.writestr(entry, path.read_bytes())
    for path in [Path('mech') / part / f'{part}.kicad_pcb', *sorted(d.iterdir()), z]:
        if path.name == 'drc.json':
            continue
        lines.append(f'{hashlib.sha256(path.read_bytes()).hexdigest()}  {path}\n')
Path('procurement/mech/sha256.txt').write_text(''.join(lines))
print('Exported tip-plate and lead-bridge fabrication files.')
PY
