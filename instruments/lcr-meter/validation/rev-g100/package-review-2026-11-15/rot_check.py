"""Independent CPL rotation check. For each placed part that is not a non-polar 2-pin passive, take the EasyEDA/JLCEDA
official-library footprint of its LCSC code (lceda.cn mirror, cached in easyeda/), rotate it CCW by 0/90/180/270 about the
pad-bbox centre, and find which angle puts every numbered pad on the board's pad of the same number. Compare with the CPL.
Source of the footprints: JLCEDA/EasyEDA Official Library (https://lceda.cn/, https://easyeda.com).
Run with KiCad python from instruments/lcr-meter."""
import csv, json, math, os, sys, subprocess, collections
import pcbnew
R = os.path.dirname(os.path.abspath(__file__))
b = pcbnew.LoadBoard('cad/temper-lcr.kicad_pcb')
cpl = {r['Designator']: r for r in csv.DictReader(open('manufacturing/cpl-jlcpcb.csv'))}
bom = {}
for row in csv.DictReader(open('manufacturing/bom-jlcpcb.csv')):
    for d in row['Designator'].split(','): bom[d] = row['LCSC Part #']

def easyeda(code):
    p = f'{R}/easyeda/{code}.json'
    if not os.path.exists(p) or os.path.getsize(p) < 500:
        subprocess.run(['curl', '-s', '-m', '40', '-A', 'Mozilla/5.0', '-o', p,
                        f'https://lceda.cn/api/products/{code}/components?version=6.4.19.5'])
    d = json.load(open(p))['result']
    pads = {}
    for s in d['packageDetail']['dataStr']['shape']:
        f = s.split('~')
        if f[0] == 'PAD':
            num = f[8]
            pads.setdefault(num, []).append((float(f[2]) * 0.254, -float(f[3]) * 0.254))   # 10 mil units -> mm, y up
    pins = {}
    for s in d['dataStr']['shape']:
        if s.startswith('P~'):
            segs = s.split('^^')
            try:
                num = s.split('~')[3]; name = segs[3].split('~')[4]
                pins[num] = name
            except Exception: pass
    return pads, pins, d['packageDetail']['title']

def centre(pts):
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    return ((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2)

out = []
for f in sorted(b.GetFootprints(), key=lambda f: f.GetReference()):
    ref = f.GetReference()
    if ref not in cpl: continue
    polar = ref[0] in 'DUQKYJS' or ref == 'C117' or ref.startswith('SW')
    if not polar: continue
    bp = {}
    fn = {}
    for p in f.Pads():
        n = p.GetNumber()
        if not n: continue
        bp.setdefault(n, []).append((pcbnew.ToMM(p.GetPosition().x), -pcbnew.ToMM(p.GetPosition().y)))
        fn[n] = (p.GetPinFunction(), p.GetNetname())
    try:
        ep, pins, title = easyeda(bom[ref])
    except Exception as e:
        out.append((ref, bom[ref], 'NO EASYEDA RECORD', str(e)[:60])); continue
    common = sorted(set(bp) & set(ep))
    if len(common) < 2:
        out.append((ref, bom[ref], 'PAD NUMBERS DIFFER', f'board {sorted(bp)} easyeda {sorted(ep)}')); continue
    ec = centre([q for v in ep.values() for q in v]); bc = centre([q for v in bp.values() for q in v])
    errs = {}
    for ang in (0, 90, 180, 270):
        c, s = math.cos(math.radians(ang)), math.sin(math.radians(ang))
        worst = 0
        for n in common:
            for (x, y) in ep[n]:
                x, y = x - ec[0], y - ec[1]
                rx, ry = x * c - y * s + bc[0], x * s + y * c + bc[1]
                worst = max(worst, min(math.hypot(rx - q[0], ry - q[1]) for q in bp[n]))
        errs[ang] = worst
    best = min(errs, key=errs.get)
    second = sorted(errs.values())[1]
    cang = float(cpl[ref]['Rotation']) % 360
    ok = 'OK' if abs(best - cang) < 0.01 else 'MISMATCH'
    if errs[best] > 0.35: ok += ' POORFIT'
    if second - errs[best] < 0.2: ok += ' AMBIGUOUS(symmetric)'
    # anchor vs pad centre offset (JLC places the library centre at the CPL point)
    off = math.hypot(pcbnew.ToMM(f.GetPosition().x) - bc[0], -pcbnew.ToMM(f.GetPosition().y) - bc[1])
    extra = ''
    if len(bp) <= 3:
        extra = ' | board ' + ' '.join(f'{n}:{fn[n][0] or "-"}/{fn[n][1]}' for n in sorted(fn)) + ' | easyeda ' + ' '.join(f'{n}:{pins.get(n, "?")}' for n in sorted(ep))
    out.append((ref, bom[ref], ok, f'cpl {cang:g} best {best} err {errs[best]:.2f} next {second:.2f} anchor-to-padcentre {off:.2f} mm [{title}]{extra}'))
for o in out: print(*o)
print(collections.Counter(o[2] for o in out))
