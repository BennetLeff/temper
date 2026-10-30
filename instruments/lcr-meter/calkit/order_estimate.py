#!/usr/bin/env python3
"""Order estimate for N assembled cal-kit cards at JLC (read-only; nothing is uploaded).

    python3 order_estimate.py [N]   ->  manufacturing/order-estimate-<N>.json

Same method as ../manufacturing/order_estimate.py, with the fee constants, tier price, quantity and
extended-line rules of temper_boardkit.jlc.order:  part quantity per line is
max(N * per-board + lossNumber, leastPatchNumber); assembly fees from
https://jlcpcb.com/help/article/pcb-assembly-price (last updated 2026-09-09).
Fabrication: JLC instant quote read on 2026-10-21 at https://cart.jlcpcb.com/quote for
2 layers, 38 x 193 mm, qty 5, FR-4 TG135, 1.6 mm, green, ENIG 1 u", 1 oz, tented vias, 3 days.
The card outline is read from calkit.kicad_pcb; a different size is reported as a finding.
Shipping, taxes and import duty are excluded.  The uploaded BOM quote is authoritative.
"""
import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MFG = ROOT / 'manufacturing'
sys.path.insert(0, str(ROOT.parent / 'cad' / 'tools'))
import boardkit_path  # noqa: E402,F401
from temper_boardkit.jlc import order  # noqa: E402
from temper_boardkit.jlc.order import CONFIRM_PLACEMENT, ECONOMIC, SMT_JOINT, tier_price  # noqa: E402
N = int(sys.argv[1]) if len(sys.argv) > 1 else 5

FAB_QUOTE = {'qty': 5, 'date': '2026-10-21', 'size_mm': [38.0, 193.0],
             'lines': {'Engineering fee': 4.00, 'Surface finish (ENIG 1u")': 17.40, 'Board': 3.60}}


def outline_mm():
    """Bounding box of the Edge.Cuts lines in calkit.kicad_pcb, [width, height] in mm."""
    text = (ROOT / 'calkit.kicad_pcb').read_text()
    xs, ys = [], []
    for m in re.finditer(r'\(gr_line\s+\(start ([-\d.]+) ([-\d.]+)\)\s+\(end ([-\d.]+) ([-\d.]+)\)'
                         r'(?:(?!\(gr_line).)*?\(layer "Edge\.Cuts"\)', text, re.S):
        xs += [float(m[1]), float(m[3])]
        ys += [float(m[2]), float(m[4])]
    return [round(max(xs) - min(xs), 3), round(max(ys) - min(ys), 3)]


snap = sorted(MFG.glob('jlc-parts-*.json'))[-1]
parts = json.loads(snap.read_text())['parts']
placements = list(csv.DictReader((MFG / 'cpl-jlcpcb.csv').open()))
lines, findings = [], []
for row in csv.DictReader((MFG / 'bom-complete.csv').open()):
    p = parts[row['LCSC']]
    need = N * int(row['Quantity'])
    buy = order.buy_qty(need, p['loss'], p['least'])
    unit = tier_price(p['tiers'], buy)
    if p['stock'] < buy:
        findings.append(f"{row['LCSC']} stock {p['stock']} < {buy}")
    lines.append({'lcsc': row['LCSC'], 'mpn': row['MPN'], 'refs': row['Designators'],
                  'library': p['library'], 'preferred': p['preferred'], 'need': need, 'buy': buy,
                  'unit': unit, 'cost': round(buy * unit, 4), 'stock': p['stock']})
extended = [l for l in lines if order.is_extended(l['library'], l['preferred'])]
joints = 2 * len(placements)          # every placed part is a 2-terminal SMD
outline = outline_mm()
if outline != FAB_QUOTE['size_mm']:
    findings.append(f'fabrication quote is for {FAB_QUOTE["size_mm"][0]:g} x {FAB_QUOTE["size_mm"][1]:g} mm, '
                    f'the card is {outline[0]:g} x {outline[1]:g} mm: re-quote')
if FAB_QUOTE['qty'] != N:
    findings.append(f'fabrication quote is for {FAB_QUOTE["qty"]} boards, not {N}: re-quote')
cost = {
    'PCB fabrication (quote)': sum(FAB_QUOTE['lines'].values()),
    'SMT parts': sum(l['cost'] for l in lines),
    'Setup (Economic)': ECONOMIC['setup'],
    'Stencil': ECONOMIC['stencil'],
    'Extended-part fee': len(extended) * ECONOMIC['extended_line'],
    'SMT joints': N * joints * SMT_JOINT,
    'Confirm placement': CONFIRM_PLACEMENT,
}
result = {'boards': N, 'outline_mm': outline, 'parts_snapshot': snap.name, 'placements_per_board': len(placements),
          'smt_joints_per_board': joints, 'extended_lines': len(extended), 'lines': lines,
          'stock_findings': findings, 'fab_quote': FAB_QUOTE,
          'economic': {k: round(v, 2) for k, v in cost.items()},
          'total_usd': round(sum(cost.values()), 2),
          'per_card_usd': round(sum(cost.values()) / N, 2),
          'excluded': ['shipping', 'sales tax / VAT / import duty', 'coupons', 'Kelvin clip leads']}
(MFG / f'order-estimate-{N}.json').write_text(json.dumps(result, indent=1) + '\n')
print(f'{N} cards: {len(placements)} placements, {len(extended)} extended lines; '
      f'stock findings: {findings or "none"}')
for l in lines:
    print(f"  {l['mpn']:22} {l['lcsc']:10} buy {l['buy']:>3} x ${l['unit']:.4f} = ${l['cost']:6.2f}")
for k, v in result['economic'].items():
    print(f'  {k:26} ${v:7.2f}')
print(f"  {'TOTAL':26} ${result['total_usd']:7.2f}  (${result['per_card_usd']:.2f}/card)")
