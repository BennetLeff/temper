"""Where do the pads land if JLC puts the EasyEDA footprint ORIGIN (head x,y) at the CPL point with the CPL rotation?
Worst pad-to-pad distance per part (same pad number; LEDs C2286 matched by A/K swap). Run with KiCad python."""
import csv, json, math, os
import pcbnew
R = os.path.dirname(os.path.abspath(__file__))
b = pcbnew.LoadBoard('cad/temper-lcr.kicad_pcb')
org = b.GetDesignSettings().GetAuxOrigin()
cpl = {r['Designator']: r for r in csv.DictReader(open('manufacturing/cpl-jlcpcb.csv'))}
bom = {}
for row in csv.DictReader(open('manufacturing/bom-jlcpcb.csv')):
    for d in row['Designator'].split(','): bom[d] = row['LCSC Part #']
rows = []
for f in b.GetFootprints():
    ref = f.GetReference(); p = f'{R}/easyeda/{bom.get(ref)}.json'
    if ref not in cpl or not os.path.exists(p): continue
    d = json.load(open(p))['result']['packageDetail']['dataStr']
    ox, oy = float(d['head']['x']), float(d['head']['y'])
    ep = {}
    for s in d['shape']:
        t = s.split('~')
        if t[0] == 'PAD': ep.setdefault(t[8], []).append(((float(t[2]) - ox) * 0.254, -(float(t[3]) - oy) * 0.254))
    bp = {}
    for pad in f.Pads():
        if pad.GetNumber(): bp.setdefault(pad.GetNumber(), []).append((pcbnew.ToMM(pad.GetPosition().x - org.x), -pcbnew.ToMM(pad.GetPosition().y - org.y)))
    cx = float(cpl[ref]['Mid X'][:-2]); cy = float(cpl[ref]['Mid Y'][:-2]); a = math.radians(float(cpl[ref]['Rotation']))
    c, s_ = math.cos(a), math.sin(a)
    swap = {'1': '2', '2': '1'} if bom[ref] == 'C2286' else {}
    worst = 0
    for n, pts in ep.items():
        m = swap.get(n, n)
        if m not in bp: continue
        for x, y in pts:
            q = (cx + x * c - y * s_, cy + x * s_ + y * c)
            worst = max(worst, min(math.hypot(q[0] - w[0], q[1] - w[1]) for w in bp[m]))
    rows.append((worst, ref, bom[ref]))
for w, ref, code in sorted(rows, reverse=True)[:14]: print(f'{ref:5} {code:10} worst pad error {w:.2f} mm')
print('parts checked', len(rows), 'over 0.3 mm:', sum(1 for r in rows if r[0] > 0.3))
