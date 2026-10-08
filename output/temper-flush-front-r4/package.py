"""Package the R4 exploration with visible failures and a content manifest."""
from pathlib import Path
from collections import Counter
import csv
import hashlib
import html
import json
import zipfile

ROOT=Path(__file__).resolve().parent

def main():
    catalog=json.loads((ROOT/'catalog.json').read_text())
    current={p['file'] for p in catalog}
    # This output directory was copied from R2.1; remove superseded individual exports only.
    for path in (ROOT/'STEP/parts').glob('*.step'):
        if str(path.relative_to(ROOT)) not in current:path.unlink()
    checks=json.loads((ROOT/'evidence/front-panel-validation.json').read_text())['checks']
    inherited=json.loads((ROOT/'evidence/validation.json').read_text())['checks']
    counts=Counter(c['status'] for c in checks)
    with (ROOT/'make-buy-review.csv').open('w',newline='') as f:
        w=csv.writer(f);w.writerow(['part','group','status','definition','STEP'])
        for p in catalog:
            if p['name'].startswith('pcb_export_'):continue
            w.writerow([p['name'],p['group'],'ALLOCATION / UNSELECTED' if p['envelope'] else 'PROTOTYPE PROCESS REVIEW',p['evidence'],p['file']])
    rows=''.join('<tr><td>'+html.escape(c['id'])+'</td><td>'+html.escape(c['status'])+'</td></tr>' for c in checks)
    body='''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Temper R4 / Flush front</title><style>body{margin:0;background:#f5f2e9;color:#263f35;font:16px/1.6 -apple-system,sans-serif}main{max-width:1080px;margin:auto;padding:40px 28px}h1{font-size:46px;font-weight:500;line-height:1.1}h2{font-size:26px;font-weight:500;margin-top:40px}a{color:#326147}nav{display:flex;gap:24px;flex-wrap:wrap;margin:25px 0}img{width:100%}.grid{display:grid;grid-template-columns:1fr 1fr;gap:24px}.note{padding:18px;border-left:3px solid #a6744a;background:#ece5d8}td,th{border-bottom:1px solid #cad1c4;padding:10px;text-align:left}table{border-collapse:collapse;width:100%;font-size:14px}.small{font-size:13px;color:#69776a}@media(max-width:720px){.grid{grid-template-columns:1fr}}</style><main><p class="small">TEMPER / R4 / FLUSH FRONT EXPLORATION</p><h1>One continuous aluminum face.</h1><p>The exterior cassette outline is gone. The glass and three button tops share the aluminum front's nominal surface plane; a hidden carrier holds the display and button electronics.</p><nav><a href="index.html">Interactive CAD</a><a href="STEP/assembly.step">Integrated STEP</a><a href="STEP/front_panel_exploded.step">Hidden assembly STEP</a><a href="temper-flush-front-r4.zip">Complete R4 package</a></nav><img src="renders/assembly.png" alt="Continuous bent aluminum front with flush glass and three buttons"><div class="grid"><section><h2>Flush lens, hidden support</h2><p>A 108 × 38 × 2 mm glass lens sits in a 108.8 × 38.8 mm window. The 0.4 mm perimeter joint is allocated for a flush-filled flexible seal. A flat rear support ring bonds to both glass and sheet through a nominal 0.3 mm bondline.</p><p>The ring supports inward loads. Outward retention depends on a qualified adhesive joint; there is no overlapping front lip. An exterior datum jig must establish flushness during cure.</p></section><section><h2>Service the electronics from inside</h2><p>Six concealed bonded stud pads hold the carrier with spacers, washers and nuts. The electronics can be removed while the lens stays bonded to the enclosure. The three button holes share one membrane behind the face.</p><p>Back, Select/Start and Stop remain. Button tops are nominally flush. Compound, actuation force, overtravel, bond strength, locking and service tool access require prototype tests.</p></section></div><img src="renders/front_panel_exploded.png" alt="Hidden carrier, lens support ring and membrane behind cropped front sheet"><p class="small">The aluminum in this detail is a cropped excerpt of the actual continuous formed cover—not a separate faceplate. Exploded offsets illustrate the stack; they do not demonstrate a disassembly procedure.</p><h2>Measured geometry and remaining limits</h2><p>COUNTS. Nominal flushness, sheet bridge, joint gap, support stack, screw clearances and saved solids are checked. Allocation solids participate in interference checks.</p><div class="note">The shallow folded front roof clears the former front carrier/chamber clash in nominal saved geometry and keeps the historical PCB covered. Current full-bridge board and cooling fit, physical barrier construction and tool access remain unqualified. No hot-oil, ingress, thermal, bond-life or electrical qualification is claimed.</div><table><thead><tr><th>Check</th><th>Result</th></tr></thead><tbody>ROWS</tbody></table><nav><a href="evidence/front-panel-validation.json">Measurements and failures</a><a href="evidence/assembly-correspondence.json">Saved assembly correspondence</a><a href="evidence/dxf-checks.json">DXF checks</a><a href="evidence/validation.json">Inherited mechanism checks</a></nav><h2>Manufacturing and qualification</h2><p>The large body remains bent 2 mm sheet. The new rear lens ring is a flat 1.2 mm part with a provisional cutting DXF. The carrier is a prototype polymer-machining or cold-print candidate; the membrane needs a material and process trial. No large cosmetic CNC faceplate remains.</p><p>Bonded glass and mounting pads need aged pull/peel and creep tests after heat, cooking oil and cleaning exposure. The edge seal and membrane need leak and cleaning tests. The closed electronics housing still needs a measured thermal budget. The candidate display's published 85°C operating limit is not a hot-oil rating.</p><nav><a href="front-panel-engineering-plan.md">Assembly, DFM and test plan</a><a href="README.md">Build instructions</a><a href="catalog.json">Current part catalog</a><a href="make-buy-review.csv">Make/buy review</a><a href="sha256-manifest.json">Manifest</a></nav><p class="small">R3 preserved. Firmware, PCB, knob and pan-sensor mechanisms unchanged. Inherited PDFs concern earlier revisions; use current R4 STEP/source for this front. Five STL files are cold shape/fit mockups, including nonfunctional glass/elastomer shapes. Display source: <a href="evidence/Newhaven-NHD-3.12-25664UCW2-rev7.pdf">Newhaven rev7 drawing</a>.</p></main></html>'''
    body=body.replace('COUNTS',', '.join(f'{v} {k}' for k,v in sorted(counts.items()))).replace('ROWS',rows)
    (ROOT/'review.html').write_text(body)
    (ROOT/'CURRENT.json').write_text(json.dumps(dict(revision='R4',status='PROTOTYPE_NOMINAL_FIT_ONLY',units='mm',build='src/assembly.py',assembly='STEP/assembly.step',panel='STEP/front_panel.step',catalog='catalog.json',review='review.html',baseline='../temper-front-panel-r3',drawings_status='R2 PDFs inherited; front chamber roof and front panel unqualified, no released cassette drawing'),indent=2))
    paths=[p for p in sorted(ROOT.rglob('*')) if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ('.zip','.log','.pyc') and p.name!='sha256-manifest.json']
    manifest={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    (ROOT/'sha256-manifest.json').write_text(json.dumps(manifest,indent=2))
    paths.append(ROOT/'sha256-manifest.json')
    output=ROOT/'temper-flush-front-r4.zip'
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as z:
        for p in paths:z.write(p,Path(ROOT.name)/p.relative_to(ROOT))
    with zipfile.ZipFile(output) as z:assert z.testzip() is None
    print(json.dumps(dict(files=len(paths),new_checks=dict(counts),inherited_checks=dict(Counter(c['status'] for c in inherited)),zip_bytes=output.stat().st_size),indent=2))

if __name__=='__main__':main()
