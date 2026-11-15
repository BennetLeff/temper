"""Read-only dump of test pads, DNP parts and net access on cad/temper-lcr.kicad_pcb."""
import sys, json, collections
import pcbnew
b = pcbnew.LoadBoard(sys.argv[1])
out = {'tps': [], 'fps': []}
for f in b.GetFootprints():
    ref = f.GetReference()
    p = f.GetPosition()
    pads = [(pd.GetNumber(), pd.GetNetname(), round(pcbnew.ToMM(pd.GetPosition().x), 3), round(pcbnew.ToMM(pd.GetPosition().y), 3),
             round(pcbnew.ToMM(pd.GetSize().x), 2), round(pcbnew.ToMM(pd.GetSize().y), 2)) for pd in f.Pads()]
    rec = {'ref': ref, 'value': f.GetValue(), 'fp': str(f.GetFPID().GetLibItemName()), 'x': round(pcbnew.ToMM(p.x), 3), 'y': round(pcbnew.ToMM(p.y), 3),
           'rot': f.GetOrientationDegrees(), 'layer': f.GetLayerName(), 'dnp': f.IsDNP(), 'exclude_bom': f.IsExcludedFromBOM(), 'pads': pads}
    out['fps'].append(rec)
    if ref.startswith('TP'):
        out['tps'].append(rec)
json.dump(out, open(sys.argv[2], 'w'), indent=1)
for t in sorted(out['tps'], key=lambda r: int(r['ref'][2:])):
    print(t['ref'], t['value'], t['fp'], t['x'], t['y'], [(p[1], p[4], p[5]) for p in t['pads']])
print('n fps', len(out['fps']))
print('DNP', [r['ref'] for r in out['fps'] if r['dnp']])
print('others not in design', sorted(r['ref'] for r in out['fps'] if r['ref'][0] in 'HMF' or r['ref'].startswith('TP') is False and r['exclude_bom']))
