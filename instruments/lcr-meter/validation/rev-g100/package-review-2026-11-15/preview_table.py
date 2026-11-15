"""Pin-1 position of every keyed part as it appears in JLC's placement preview (BNC edge up, USB-C edge left).
Run with KiCad python.  Output: preview-checklist.csv"""
import csv, pcbnew, os
R = os.path.dirname(os.path.abspath(__file__))
b = pcbnew.LoadBoard('cad/temper-lcr.kicad_pcb')
cpl = {r['Designator']: r for r in csv.DictReader(open('manufacturing/cpl-jlcpcb.csv'))}
kill = {'U1','U2','U3','U5','U6','U7','U11','U12','U13','U14','U15','U16','U17','U18','U19','U20','U21','D1','D2','D3','D29','C117','K1','K2','K3','K4','Y1','J1','Q2','Q3','Q4','Q5','Q6','Q7','D5','D6','D7','D8','D9','D28'}
rows = []
for f in b.GetFootprints():
    ref = f.GetReference()
    if ref not in cpl or not (ref[0] in 'DUQKYJ' or ref == 'C117'): continue
    pads = [p for p in f.Pads() if p.GetNumber()]
    xs = [p.GetPosition().x for p in pads]; ys = [p.GetPosition().y for p in pads]
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    p1 = next((p for p in pads if p.GetNumber() in ('1', 'A1')), None)
    if p1 is None: continue
    dx, dy = pcbnew.ToMM(p1.GetPosition().x - cx), pcbnew.ToMM(p1.GetPosition().y - cy)
    where = ('up' if dy < -0.2 else 'down' if dy > 0.2 else '') + ('-' if abs(dy) > 0.2 and abs(dx) > 0.2 else '') + ('left' if dx < -0.2 else 'right' if dx > 0.2 else '')
    rows.append((ref, f.GetValue(), cpl[ref]['Rotation'], where or 'centre', p1.GetNetname(), p1.GetPinFunction(), 'dead board if wrong' if ref in kill else ''))
rows.sort(key=lambda r: (r[6] == '', r[0][0], int(''.join(c for c in r[0] if c.isdigit()))))
with open(f'{R}/preview-checklist.csv', 'w', newline='') as fh:
    w = csv.writer(fh); w.writerow(['Ref', 'Value', 'CPL rotation', 'Pad 1 is at (BNC edge up, USB-C left)', 'Pad 1 net', 'Pad 1 function', 'Severity']); w.writerows(rows)
print(len(rows), sum(1 for r in rows if r[6]))
for r in rows[:42]: print(*r, sep=' | ')
