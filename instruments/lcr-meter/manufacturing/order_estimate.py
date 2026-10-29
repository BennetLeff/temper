"""Batch order estimate for N assembled Rev E boards at JLC (read-only).

Run with KiCad's bundled Python:  <kicad-python> manufacturing/order_estimate.py [N]
Writes manufacturing/order-estimate-<N>.json and prints a summary.

Inputs:
  - bom-complete.csv (lines, quantities, SMT vs hand fit) and cpl-jlcpcb.csv (machine placements);
  - prices/jlc-parts-2026-10-29.json: JLC assembly-library snapshot per LCSC code (price tiers,
    stock, library class, lossNumber, leastPatchNumber), written by prices/fetch_jlc_parts.py;
  - joint and leadless-package counts taken from cad/temper-lcr.kicad_pcb;
  - fee constants below, copied from https://jlcpcb.com/help/article/pcb-assembly-price
    (last updated 2026-09-09, read 2026-10-20), and the fabrication quote read from
    https://cart.jlcpcb.com/quote on 2026-10-20.

Part quantity per line is max(N * per-board + lossNumber, leastPatchNumber), our reading of
JLC's library fields (attrition pieces and minimum patch quantity). The uploaded BOM quote is
authoritative. Shipping, taxes and import duty are not included.
"""
import csv
import json
import re
import sys
from pathlib import Path

import pcbnew as k

ROOT = Path(__file__).resolve().parents[1]
N = int(sys.argv[1]) if len(sys.argv) > 1 else 5
MFG = ROOT / 'manufacturing'

# JLC fabrication quote, 2026-10-20: 4 layers, 140 x 100 mm, qty 5, 1.6 mm, 1 oz outer /
# 0.5 oz inner, ENIG 1 u", epoxy filled & capped vias, 3-4 days.  Rev E has only 0.3 mm vias
# (0.45 mm pad), JLC's standard via option: the $116.73 quote for 0.2 mm vias less its
# 'Min via hole 0.2 mm' and 4-wire Kelvin lines, which the 0.2 mm option forced, gives the $80.98
# the same page quoted for 0.3 mm vias.  TG155 is kept as quoted.  2026-10-29: POFV ($18.28) and the
# via plating line it forced ($3.48) are dropped: no via sits in a small land, the exposed-pad thermal
# vias are tented (cad/audit_dfm.py), and "Tented" is JLC's default via covering.  Re-quote at upload.
FAB_QUOTE = {
    'qty': 5,
    'lines': {
        'Engineering fee': 25.00, 'Surface finish (ENIG)': 18.20,
        'Material type (TG155)': 7.32, 'Board': 8.70,
    },
}
ECONOMIC = {'setup': 8.18, 'stencil': 1.53, 'extended_line': 3.07}
STANDARD = {'setup': 25.56, 'stencil': 8.21, 'extended_line': 3.07, 'basic_line': 1.53,
            'fixtures_1_29': 16.42}
SMT_JOINT = 0.0016            # 1-100,000 joints (Economic)
MANUAL_JOINT = 0.0164         # 1-10,000 joints
HAND_LABOR = 3.58             # per order, when any part is hand soldered
CONFIRM_PLACEMENT = 0.45
XRAY_TIERS = [(10, 1.64), (50, 0.82), (200, 0.49), (500, 0.33)]
LEADLESS = re.compile(r'QFN|DFN|SON|BGA|LGA')   # case-sensitive: 'Panasonic' is not a SON


def tier_price(tiers, qty):
    price = tiers[0][1]
    for start, value in tiers:
        if qty >= start:
            price = value
    return price


def board_counts():
    board = k.LoadBoard(str(ROOT / 'cad/temper-lcr.kicad_pcb'))
    placed = {row['Designator'] for row in csv.DictReader(open(MFG / 'cpl-jlcpcb.csv'))}
    smt_joints = tht_joints = 0
    leadless, tht_refs = [], []
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        # Unnumbered pads are paste windows on exposed pads, not joints.
        pads = [p for p in fp.Pads() if p.GetAttribute() != k.PAD_ATTRIB_NPTH and p.GetNumber()]
        if ref in placed:
            smt_joints += len(pads)
            if LEADLESS.search(fp.GetFPIDAsString()):
                leadless.append(ref)
        elif pads:
            tht_joints += len(pads)
            tht_refs.append(ref)
    return len(placed), smt_joints, sorted(leadless), tht_joints, sorted(tht_refs)


def main():
    snapshot = json.loads((MFG / 'prices/jlc-parts-2026-10-29.json').read_text())['parts']
    placements, smt_joints, leadless, tht_joints, tht_refs = board_counts()
    lines, findings = [], []
    for row in csv.DictReader(open(MFG / 'bom-complete.csv')):
        part = snapshot[row['LCSC']]
        need = N * int(row['Quantity'])
        qty = max(need + part['loss'], part['least'])
        unit = tier_price(part['tiers'], qty)
        if part['stock'] < qty:
            findings.append(f"{row['LCSC']} stock {part['stock']} < {qty}")
        lines.append({
            'lcsc': row['LCSC'], 'mpn': row['MPN'], 'assembly': row['Assembly'],
            'library': part['library'], 'preferred': part['preferred'], 'need': need,
            'buy': qty, 'unit': unit, 'cost': round(qty * unit, 4), 'stock': part['stock'],
        })
    smt = [l for l in lines if l['assembly'] == 'SMT']
    hand = [l for l in lines if l['assembly'] != 'SMT']
    extended = [l for l in smt if l['library'] == 'expand' and not l['preferred']]
    basic = [l for l in smt if l not in extended]
    xray_pcs = N * len(leadless)
    xray_unit = next(price for limit, price in XRAY_TIERS if xray_pcs <= limit)
    fab = sum(FAB_QUOTE['lines'].values())

    smt_parts = sum(l['cost'] for l in smt)
    hand_parts = sum(l['cost'] for l in hand)
    common = {
        'SMT parts': smt_parts,
        'SMT joints': N * smt_joints * SMT_JOINT,
        'X-ray': xray_pcs * xray_unit,
        'Confirm placement': CONFIRM_PLACEMENT,
        'PCB fabrication': fab,
    }
    economic = dict(common, **{
        'Setup': ECONOMIC['setup'], 'Stencil': ECONOMIC['stencil'],
        'Extended-part fee': len(extended) * ECONOMIC['extended_line'],
    })
    standard = dict(common, **{
        'Setup': STANDARD['setup'], 'Stencil': STANDARD['stencil'],
        'Feeder loading': len(extended) * STANDARD['extended_line'] + len(basic) * STANDARD['basic_line'],
        'Fixtures': STANDARD['fixtures_1_29'],
    })
    jlc_hand = {'Hand-fit parts via JLC': hand_parts,
                'Manual joints': N * tht_joints * MANUAL_JOINT, 'Hand-soldering labour': HAND_LABOR}
    result = {
        'boards': N,
        'board_counts': {'placements': placements, 'smt_joints': smt_joints, 'leadless': leadless,
                         'tht_joints': tht_joints, 'tht_refs': tht_refs},
        'extended_lines': len(extended), 'basic_or_preferred_lines': len(basic),
        'lines': lines, 'stock_findings': findings,
        'fab_quote': FAB_QUOTE,
        'economic': {k_: round(v, 2) for k_, v in economic.items()},
        'standard': {k_: round(v, 2) for k_, v in standard.items()},
        'jlc_hand_fit': {k_: round(v, 2) for k_, v in jlc_hand.items()},
        'totals': {
            'economic': round(sum(economic.values()), 2),
            'standard': round(sum(standard.values()), 2),
            'jlc_hand_fit': round(sum(jlc_hand.values()), 2),
        },
        'excluded': ['shipping', 'sales tax / VAT / import duty', 'coupons'],
    }
    (MFG / f'order-estimate-{N}.json').write_text(json.dumps(result, indent=1) + '\n')

    print(f'{N} boards: {placements} placements, {smt_joints} SMT joints/board, '
          f'leadless {leadless}, THT {tht_joints} joints/board {tht_refs}')
    print(f'{len(extended)} extended lines, {len(basic)} basic/preferred lines; stock findings: {findings or "none"}')
    print('\nTop lines:')
    for l in sorted(lines, key=lambda l: -l['cost'])[:14]:
        print(f"  {l['mpn']:22} {l['lcsc']:10} buy {l['buy']:>3} x ${l['unit']:.4f} = ${l['cost']:8.2f}")
    for name in ('economic', 'standard', 'jlc_hand_fit'):
        print(f'\n{name}:')
        for item, value in result[name].items():
            print(f'  {item:28} ${value:8.2f}')
        print(f"  {'TOTAL':28} ${result['totals'][name]:8.2f}")


main()
