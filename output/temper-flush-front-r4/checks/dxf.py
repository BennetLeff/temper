"""Run the CAD skill's serialized-DXF checks and check the strip pilot-hole size."""
from pathlib import Path
import json
import hashlib
import ezdxf
from cadgen.drawing_checks import validate_dxf_file

ROOT=Path(__file__).resolve().parents[1]
records=[]
for path in sorted((ROOT/'DXF').glob('*.dxf')):
    findings=[f.render() for f in validate_dxf_file(path)]
    doc=ezdxf.readfile(path)
    records.append({'file':str(path.relative_to(ROOT)),'units':doc.header.get('$INSUNITS'),
                    'findings':findings,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
doc=ezdxf.readfile(ROOT/'DXF/hatch-tapped-strip-pre-tap-PROVISIONAL.dxf')
pilots=[e.dxf.radius for e in doc.modelspace().query('CIRCLE') if abs(e.dxf.center.x)<1e-6 and abs(e.dxf.center.y)<1e-6]
result={'files':records,'tap_pilot_radii_mm':pilots,'pilot_matches_2p5mm':pilots==[1.25],
        'scope':'Skill serialized-DXF syntax, closure, duplicates, units and degeneracy checks; no kerf, bend unfolding, laminate cutting suitability or tooling approval.'}
(ROOT/'evidence/dxf-checks.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result,indent=2))
assert not any(r['findings'] for r in records)
assert all(r['units']==4 for r in records)
assert result['pilot_matches_2p5mm']
