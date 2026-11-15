"""BOM <-> CPL <-> board consistency (read-only). Run with KiCad python from instruments/lcr-meter."""
import csv, sys, collections
import pcbnew
b = pcbnew.LoadBoard('cad/temper-lcr.kicad_pcb')
ds = b.GetDesignSettings()
org = ds.GetAuxOrigin()
print('aux origin mm', pcbnew.ToMM(org.x), pcbnew.ToMM(org.y))
bb = b.GetBoardEdgesBoundingBox()
print('edge bbox mm', pcbnew.ToMM(bb.GetX()), pcbnew.ToMM(bb.GetY()), pcbnew.ToMM(bb.GetWidth()), pcbnew.ToMM(bb.GetHeight()))
fps = {}
for f in b.GetFootprints():
    ref = f.GetReference()
    flds = {fl.GetName(): fl.GetText() for fl in f.GetFields()}
    fps[ref] = dict(x=pcbnew.ToMM(f.GetPosition().x - org.x), y=-pcbnew.ToMM(f.GetPosition().y - org.y),
                    rot=f.GetOrientationDegrees() % 360, side='top' if f.GetLayer() == pcbnew.F_Cu else 'bottom',
                    dnp=f.IsDNP(), exbom=bool(f.GetAttributes() & pcbnew.FP_EXCLUDE_FROM_BOM),
                    expos=bool(f.GetAttributes() & pcbnew.FP_EXCLUDE_FROM_POS_FILES),
                    smd=bool(f.GetAttributes() & pcbnew.FP_SMD), tht=bool(f.GetAttributes() & pcbnew.FP_THROUGH_HOLE),
                    val=f.GetValue(), fp=str(f.GetFPID().GetLibItemName()), flds=flds, npads=f.GetPadCount())
print('footprints', len(fps), 'sides', collections.Counter(v['side'] for v in fps.values()))
kinds = collections.Counter()
for r, v in fps.items():
    kinds[(v['dnp'], v['exbom'], v['expos'], v['smd'], v['tht'])] += 1
print('(dnp,exbom,expos,smd,tht):', dict(kinds))
print('field names seen:', collections.Counter(k for v in fps.values() for k in v['flds']))
cpl = {r['Designator']: r for r in csv.DictReader(open('manufacturing/cpl-jlcpcb.csv'))}
bom = {}
for row in csv.DictReader(open('manufacturing/bom-jlcpcb.csv')):
    for d in row['Designator'].split(','):
        assert d not in bom, d
        bom[d] = row
print('CPL rows', len(cpl), 'BOM designators', len(bom), 'BOM lines', len(set(r['LCSC Part #'] for r in bom.values())))
print('BOM-CPL', sorted(set(bom) - set(cpl)), 'CPL-BOM', sorted(set(cpl) - set(bom)))
real = {r for r, v in fps.items() if not v['exbom']}
print('board(not exbom) - BOM:', sorted(real - set(bom)))
print('BOM - board:', sorted(set(bom) - set(fps)))
print('non-BOM footprints:', sorted(r for r, v in fps.items() if v['exbom']))
print('DNP:', sorted(r for r, v in fps.items() if v['dnp']))
bad = 0
for d, row in cpl.items():
    f = fps[d]
    x = float(row['Mid X'].replace('mm', '')); y = float(row['Mid Y'].replace('mm', ''))
    if abs(x - f['x']) > 0.001 or abs(y - f['y']) > 0.001 or row['Layer'] != f['side']:
        bad += 1; print('POS MISMATCH', d, row, f['x'], f['y'])
print('CPL position mismatches (footprint anchor):', bad)
# LCSC field vs BOM
lk = [k for k in ('LCSC', 'LCSC Part #', 'LCSC Part', 'JLCPCB') if any(k in v['flds'] for v in fps.values())]
print('lcsc field keys', lk)
mm = 0
for d, row in bom.items():
    f = fps[d]
    code = next((f['flds'][k] for k in lk if k in f['flds']), None)
    if code != row['LCSC Part #']:
        mm += 1; print('LCSC MISMATCH', d, code, row['LCSC Part #'])
    if row['Footprint'] != f['fp']:
        mm += 1; print('FP MISMATCH', d, row['Footprint'], f['fp'])
print('LCSC/footprint mismatches:', mm)
# audit native vs board orientation
oa = {r['Designator']: r for r in csv.DictReader(open('manufacturing/orientation-audit.csv'))}
n = 0
for d, r in oa.items():
    f = fps[d]
    nat = float(r['Native angle deg']) % 360; off = float(r['Library offset deg']); c = float(r['CPL angle deg'])
    if abs(nat - f['rot']) > 0.01 or abs((nat + off) % 360 - c) > 0.01 or abs(float(cpl[d]['Rotation']) - c) > 0.01:
        n += 1; print('ROT MISMATCH', d, r['Native angle deg'], off, c, f['rot'], cpl[d]['Rotation'])
print('orientation-audit rows', len(oa), 'rotation mismatches', n)
