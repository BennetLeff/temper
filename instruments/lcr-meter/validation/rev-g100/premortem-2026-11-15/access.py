"""Probe access per net, from board.json (dump_board.py). A pad is 'probeable' when its smaller side is >= 0.6 mm
and the part is not a QFN/VSSOP/SOT-23-5/6 lead; 'fine' otherwise. Lists nets whose only pads are fine-pitch."""
import json, collections, math, sys
b = json.load(open(sys.argv[1]))
FINE = ('QFN', 'VQFN', 'VSSOP', 'HVSSOP', 'USB_C', 'SOT-23-5', 'SOT-23-6', 'Toshiba_11-4M1S')
nets = collections.defaultdict(lambda: {'easy': [], 'fine': []})
for f in b['fps']:
    fine_fp = any(k in f['fp'] for k in FINE)
    for num, net, x, y, sx, sy in f['pads']:
        if not net: continue
        easy = (not fine_fp) and min(sx, sy) >= 0.6
        nets[net]['easy' if easy else 'fine'].append(f"{f['ref']}.{num}@{x},{y}")
print('## nets with NO easy pad (only fine-pitch / small pads)')
for n, v in sorted(nets.items()):
    if not v['easy']:
        print(n, v['fine'])
print('## unconnected pads on ICs (no net)')
for f in b['fps']:
    nn = [p[0] for p in f['pads'] if not p[1]]
    if nn and f['ref'][0] in 'UK': print(f['ref'], f['fp'], nn)
print('## test pads: nearest other footprints (centre distance, mm)')
for t in b['tps']:
    near = sorted(((math.hypot(f['x'] - t['x'], f['y'] - t['y']), f['ref'], f['fp']) for f in b['fps'] if f['ref'] != t['ref']))[:3]
    print(t['ref'], t['value'], t['x'], t['y'], [(round(d, 1), r, fp[:28]) for d, r, fp in near])
for r in ('J4', 'SW1', 'SW2', 'C117', 'U1', 'U14', 'U13', 'L1', 'L2', 'K1', 'K2', 'K3', 'K4', 'J1', 'Y1', 'U2', 'C14', 'R9', 'R119', 'R120', 'R134', 'R101', 'C60', 'C62', 'C8'):
    f = next(f for f in b['fps'] if f['ref'] == r)
    print(r, f['fp'][:40], f['x'], f['y'], f['rot'])
