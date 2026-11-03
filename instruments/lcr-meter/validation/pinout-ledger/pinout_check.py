"""Pinout / land-pattern / JLC-package check of every multi-pin and polarized part (read-only).

Run with KiCad's bundled Python (it needs pcbnew):
  /Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3 \
      validation/pinout-ledger/pinout_check.py
Writes validation/pinout-ledger/pinout-check.json; exits 1 if any part has a FINDING or a part is not in the ledger.
`--ledger PATH` checks another ledger (used to prove the checks fire on seeded errors) and writes PATH.check.json.

ledger.json holds what the manufacturer datasheets say (pin table, land pattern, package) and what each
datasheet function should connect to on this board. This script compares that ledger with:
  - cad/design.json: MPN, LCSC, pin-name table (`pinouts`) and the net on every pad;
  - cad/temper-lcr.kicad_pcb (pcbnew): pad count, pitch, row span, pad size, exposed pad, pin-1 position,
    pad-numbering direction, and absolute pad positions where the ledger gives them;
  - manufacturing/bom-jlcpcb.csv and cpl-jlcpcb.csv: the LCSC number JLC receives, and the CPL rotation;
  - sources/placement-library/<LCSC>-product.json (JLC/EasyEDA record of the LCSC part): its MPN and package
    title, and whether its pads, turned by the CPL rotation, land on the board pads of the same function.
independent_check.py already proves design.json pins == board pads == schematic netlist; this script does not
repeat that. It checks the datasheet side.
"""
import csv
import hashlib
import json
import math
import re
import sys
from pathlib import Path

import pcbnew as k

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
MM = 1e-6
LEDGER = Path(sys.argv[sys.argv.index('--ledger') + 1]) if '--ledger' in sys.argv else HERE / 'ledger.json'
OUT = HERE / 'pinout-check.json' if LEDGER == HERE / 'ledger.json' else LEDGER.with_suffix('.check.json')
ledger = json.loads(LEDGER.read_text())
design = json.loads((ROOT / 'cad/design.json').read_text())
pcb_path = ROOT / 'cad/temper-lcr.kicad_pcb'
board = k.LoadBoard(str(pcb_path))
parts = {p['ref']: p for p in design['parts']}
fps = {f.GetReference(): f for f in board.GetFootprints()}
bom = {}
for row in csv.DictReader(open(ROOT / 'manufacturing/bom-jlcpcb.csv')):
    for ref in row['Designator'].split(','):
        bom[ref.strip()] = row['LCSC Part #']
cpl = {r['Designator']: float(r['Rotation']) for r in csv.DictReader(open(ROOT / 'manufacturing/cpl-jlcpcb.csv'))}
nets = {}
for p in design['parts']:
    for num, net in p['pins'].items():
        if net:
            nets.setdefault(net, []).append(p['ref'])


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def norm(name):
    return re.sub(r'[^A-Z0-9+\-]', '', name.upper().replace('–', '-').replace('#', '').replace('/', ''))


def board_pads(ref):
    """Numbered copper pads of a footprint in its own (unrotated) frame, mm, KiCad y down."""
    out = {}
    for p in fps[ref].Pads():
        if not p.GetNumber():
            continue
        q = p.GetFPRelativePosition()
        try:
            s = p.GetSize()
        except TypeError:            # KiCad 9+: size is per copper layer
            s = p.GetSize(k.F_Cu)
        out.setdefault(p.GetNumber(), []).append({
            'x': q.x * MM, 'y': q.y * MM, 'w': s.x * MM, 'h': s.y * MM, 'drill': p.GetDrillSize().x * MM,
            'pth': p.GetAttribute() == k.PAD_ATTRIB_PTH})
    return out


def easyeda_pads(lcsc):
    p = ROOT / f'sources/placement-library/{lcsc}-product.json'
    if not p.exists():
        return None, None
    r = json.loads(p.read_text())['result']
    pads = {}
    for s in r['packageDetail']['dataStr']['shape']:
        if s.startswith('PAD~'):
            t = s.split('~')
            pads[t[8]] = (float(t[2]) * 0.254, float(t[3]) * 0.254)
    return r['dataStr']['head']['c_para'], pads


def rot(x, y, deg):
    """Counter-clockwise as seen from the top, in KiCad's y-down frame (same convention as placement-rev-c.json)."""
    a = math.radians(deg)
    return x * math.cos(a) + y * math.sin(a), -x * math.sin(a) + y * math.cos(a)


def check_entry(e):
    res = {'id': e['id'], 'refs': e['refs'], 'mpn': e['mpn'], 'lcsc': e.get('lcsc'), 'checks': [],
           'findings': [], 'attention': list(e.get('attention', [])), 'notes': list(e.get('notes', []))}

    def ok(name, detail=''):
        res['checks'].append({'check': name, 'pass': True, 'detail': detail})

    def bad(name, detail):
        res['checks'].append({'check': name, 'pass': False, 'detail': detail})
        res['findings'].append(f'{name}: {detail}')

    pins = e['pins']
    # 1. Identity: design MPN/LCSC, BOM LCSC, JLC/EasyEDA record.
    for ref in e['refs']:
        p = parts[ref]
        if p.get('mpn') != e['mpn'] or p.get('lcsc') != e.get('lcsc'):
            bad('identity', f"{ref}: design {p.get('mpn')}/{p.get('lcsc')}, ledger {e['mpn']}/{e.get('lcsc')}")
        if e.get('jlc_assembled', True) and bom.get(ref) != e.get('lcsc'):
            bad('bom', f'{ref}: JLC BOM LCSC {bom.get(ref)!r}, ledger {e.get("lcsc")!r}')
    if not any(c['check'] in ('identity', 'bom') for c in res['checks']):
        ok('identity', f"design.json and JLC BOM carry {e['mpn']} / {e.get('lcsc')}")
    head, epads = easyeda_pads(e.get('lcsc') or '')
    if head is not None:
        pkg, mpn = head.get('package', ''), head.get('Manufacturer Part', '')
        want = e.get('lcsc_package')
        if mpn != e['mpn'] or (want and want not in pkg):
            bad('jlc_record', f'LCSC record says {mpn!r} in {pkg!r}; ledger wants {e["mpn"]!r} in {want!r}')
        else:
            ok('jlc_record', f'LCSC record: {mpn} in {pkg}')

    # 2. Datasheet pin table vs design.json pins and pin names.
    kind = parts[e['refs'][0]]['kind']
    names = design['pinouts'].get(kind, {})
    alias = {norm(a): norm(b) for a, b in e.get('design_alias', {}).items()}
    for ref in e['refs']:
        dp = parts[ref]['pins']
        if set(dp) != set(pins):
            bad('pin_set', f'{ref}: design pads {sorted(dp)} vs datasheet pins {sorted(pins)}')
    if names and not e.get('skip_names'):
        wrong = []
        for num, ds in pins.items():
            dn = norm(names.get(num, ['?'])[0])
            if alias.get(dn, dn) != norm(ds):
                wrong.append(f'{num}: design {names.get(num, ["?"])[0]!r} vs datasheet {ds!r}')
        if wrong:
            bad('pin_names', '; '.join(wrong))
        else:
            ok('pin_names', f'design.json pinouts[{kind!r}] matches the datasheet table on {len(pins)} pins')

    # 3. Nets: each pad's net is the one the datasheet function needs.
    for ref, want in e.get('nets', {}).items():
        dp = parts[ref]['pins']
        diff = [f'{n} ({pins[n]}): design {dp.get(n)!r}, expected {w!r}' for n, w in want.items() if dp.get(n) != w]
        missing = sorted(set(pins) - set(want))
        if diff:
            bad('nets', f'{ref}: ' + '; '.join(diff))
        elif missing:
            bad('nets', f'{ref}: ledger has no expected net for pads {missing}')
        else:
            ok('nets', f'{ref}: all {len(want)} pads on the expected nets')
    for num in e.get('nc_pads', []):
        allowed = [None] + e.get('nc_allowed', {}).get(num, [])
        for ref in e['refs']:
            if parts[ref]['pins'].get(num) not in allowed:
                bad('nc', f'{ref}.{num} ({pins[num]}) is datasheet NC/DNC but on {parts[ref]["pins"][num]!r}')
    for net, refs in e.get('net_has', {}).items():
        have = nets.get(net, [])
        lack = [r for r in refs if r not in have]
        if lack:
            bad('support', f'net {net} lacks {lack} (has {have})')
        else:
            ok('support', f'net {net} has {refs}')

    # 4. Land pattern on the board vs the datasheet.
    land = e.get('land')
    fpids = {fps[r].GetFPIDAsString() for r in e['refs']}
    if len(fpids) != 1:
        bad('footprint', f'refs use different footprints {sorted(fpids)}')
    bp = board_pads(e['refs'][0])
    if set(bp) != set(pins):
        bad('pad_numbers', f'board pads {sorted(bp)} vs datasheet pins {sorted(pins)}')
    if land:
        tol = land.get('tol', 0.15)

        def centre(n):
            return bp[n][0]['x'], bp[n][0]['y']

        def dist(a, b):
            (x1, y1), (x2, y2) = centre(a), centre(b)
            return math.hypot(x1 - x2, y1 - y2)
        if 'pads' in land:
            n = sum(len(v) for v in bp.values())
            (ok if n == land['pads'] else bad)('pad_count', f'{n} numbered copper pads on the board, datasheet {land["pads"]}')
        for key in ('pitch', 'span'):
            if key in land:
                a, b, v = land[key]
                d = dist(a, b)
                t = land.get(f'tol_{key}', 0.03 if key == 'pitch' else 0.5)
                (ok if abs(d - v) <= t else bad)(key, f'pads {a}-{b} {d:.3f} mm, datasheet {v} mm (tol {t})')
        if 'pad1' in land:
            p1 = bp[land.get('pad1_ref', '1')][0]
            got = sorted((p1['w'], p1['h']))
            want = sorted(land['pad1'])
            lo, hi = land.get('pad_ratio', [0.6, 2.0])
            r = [g / w for g, w in zip(got, want)]
            (ok if all(lo <= x <= hi for x in r) else bad)(
                'pad_size', f'{got[0]:.2f} x {got[1]:.2f} mm, datasheet {want[0]} x {want[1]} mm (ratio {r[0]:.2f}, {r[1]:.2f})')
        if 'ep' in land:
            ep = bp[land['ep_pad']][0]
            got = sorted((ep['w'], ep['h']))
            want = sorted(land['ep'])
            (ok if all(abs(g - w) <= 0.06 for g, w in zip(got, want)) else bad)(
                'exposed_pad', f'{got[0]:.2f} x {got[1]:.2f} mm, datasheet {want[0]} x {want[1]} mm')
        if 'positions' in land:
            off = [(abs(bp[n][0]['x'] - x) if x is not None else 0) + (abs(bp[n][0]['y'] - y) if y is not None else 0)
                   for n, (x, y) in land['positions'].items()]
            worst = max(off)
            (ok if worst <= tol else bad)('positions', f'{len(off)} pad centres within {worst:.3f} mm of the datasheet')
        if 'drills' in land:
            out = [f'{n}: {bp[n][0]["drill"]:.2f} vs {d}' for n, d in land['drills'].items()
                   if abs(bp[n][0]['drill'] - d) > land.get('tol_drill', 0.05)]
            (bad if out else ok)('drills', '; '.join(out) or 'drills match')
        if 'pin1' in land:
            x, y = centre('1')
            sx, sy = land['pin1']
            good = (sx == '0' or (x < 0) == (sx == '-')) and (sy == '0' or (y < 0) == (sy == '-'))
            (ok if good else bad)('pin1', f'pad 1 at ({x:+.3f}, {y:+.3f}) in the footprint frame, expected {sx}x {sy}y')
        if 'ring' in land:
            ring = land['ring']
            ang = [math.atan2(-centre(n)[1], centre(n)[0]) for n in ring]
            steps = [(b - a) % (2 * math.pi) for a, b in zip(ang, ang[1:])]
            good = all(0 < s < math.pi for s in steps)
            (ok if good else bad)('numbering', f'pads {ring[0]}..{ring[-1]} run counter-clockwise seen from the top'
                                  if good else f'pad order is not counter-clockwise: steps {[round(math.degrees(s)) for s in steps]}')

    # 5. JLC placement: the LCSC part's pads, turned by the CPL rotation, on the board pads of the same function.
    jlc = e.get('jlc')
    if jlc is not None and epads:
        mp = jlc.get('map', {})
        for ref in e['refs']:
            if ref not in cpl:
                bad('cpl', f'{ref} missing from the CPL')
                continue
            off = (cpl[ref] - fps[ref].GetOrientationDegrees()) % 360
            bpr = board_pads(ref)
            pairs = []
            for en, xy in epads.items():
                bn = mp.get(en, en)
                if bn is None or bn not in bpr:
                    continue
                pairs.append((rot(*xy, off), (bpr[bn][0]['x'], bpr[bn][0]['y']), en, bn))
            if len(pairs) < 2:
                bad('jlc_orientation', f'{ref}: only {len(pairs)} EasyEDA pads map to board pads')
                continue
            cx = sum(a[0] for a, _, _, _ in pairs) / len(pairs) - sum(b[0] for _, b, _, _ in pairs) / len(pairs)
            cy = sum(a[1] for a, _, _, _ in pairs) / len(pairs) - sum(b[1] for _, b, _, _ in pairs) / len(pairs)
            err = max(math.hypot(a[0] - cx - b[0], a[1] - cy - b[1]) for a, b, _, _ in pairs)
            t = jlc.get('tol', 0.4)
            (ok if err <= t else bad)('jlc_orientation',
                                      f'{ref}: CPL {cpl[ref]:g} deg (board {fps[ref].GetOrientationDegrees():g} + {off:g}); '
                                      f'{len(pairs)} EasyEDA pads land on same-function board pads, worst {err:.3f} mm (tol {t})')

    # 6. Reviewer findings recorded in the ledger (datasheet facts the script cannot compute).
    for f in e.get('findings', []):
        res['findings'].append(f"{f['severity']}: {f['text']}")
    res['result'] = 'FINDING' if res['findings'] else ('NOTE' if res['attention'] else 'PASS')
    return res


results = [check_entry(e) for e in ledger['parts']]

# Coverage: every part that is not a two-terminal non-polar passive is in the ledger.
covered = {r for e in ledger['parts'] for r in e['refs']}
skip = re.compile(r'^(R|C)\d+$')
uncovered = sorted(p['ref'] for p in design['parts']
                   if p['ref'] not in covered and not (skip.match(p['ref']) and p['ref'] not in ledger['polarized_extra']))
coverage = {'parts_in_ledger': len(covered), 'uncovered': uncovered}

pcb_sha = sha(pcb_path)
out = {
    'method': __doc__.strip().split('\n')[0],
    'board_sha256': pcb_sha, 'board_sha256_ledger': ledger['board_sha256'],
    'design_sha256': sha(ROOT / 'cad/design.json'), 'ledger_sha256': sha(LEDGER),
    'kicad_version': k.GetBuildVersion(),
    'coverage': coverage,
    'summary': {r: sum(1 for x in results if x['result'] == r) for r in ('PASS', 'NOTE', 'FINDING')},
    'parts': results,
    'limits': ledger['limits'],
}
if pcb_sha != ledger['board_sha256']:
    out['board_changed'] = 'board differs from the one the ledger was written against; re-review the land rows'
OUT.write_text(json.dumps(out, indent=1, ensure_ascii=False) + '\n')
for r in results:
    print(f"{r['result']:8} {r['id']:22} {','.join(r['refs'])}")
    for f in r['findings'] + r['attention']:
        print('         ', f[:160])
print(f"summary {out['summary']}; uncovered {uncovered}")
fail = any(r['result'] == 'FINDING' for r in results) or bool(uncovered)
sys.exit(1 if fail else 0)
