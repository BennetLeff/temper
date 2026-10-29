"""Batch order estimate for N assembled boards (Rev F, 100 x 100 mm) at JLC (read-only).

Run with KiCad's bundled Python:  <kicad-python> manufacturing/order_estimate.py [N]
Writes manufacturing/order-estimate-<N>.json and prints a summary.

Inputs:
  - bom-complete.csv (lines, quantities, SMT vs hand fit) and cpl-jlcpcb.csv (machine placements);
  - prices/jlc-parts-2026-10-29.json: JLC assembly-library snapshot per LCSC code (price tiers,
    stock, library class, lossNumber, leastPatchNumber), written by prices/fetch_jlc_parts.py;
  - joint and leadless-package counts taken from cad/temper-lcr.kicad_pcb;
  - fee constants below, copied from https://jlcpcb.com/help/article/pcb-assembly-price
    (last updated 2026-09-09, read 2026-10-20), and the fabrication quote in fab-quote.json
    (read from https://cart.jlcpcb.com/quote on 2026-10-29).

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
# LCR_MFG_DIR names another folder holding the BOM/CPL and receiving the estimate (Rev E's archived
# package: LCR_MFG_DIR=manufacturing/rev-e LCR_FAB_QUOTE=manufacturing/rev-e/fab-quote.json); LCR_FAB_QUOTE
# a JSON quote file replacing manufacturing/fab-quote.json. The price snapshot stays in manufacturing/prices/.
import os
PKG = ROOT / os.environ['LCR_MFG_DIR'] if os.environ.get('LCR_MFG_DIR') else MFG

# JLC fabrication quote, read 2026-10-29 (fab-quote.json): 4 layers, 100 x 100 mm, qty 5, 1.6 mm,
# FR4 TG 135-140, JLC04161H-7628, 1 oz outer / 0.5 oz inner, ENIG 1 u", 0.3 mm vias, no POFV.  At
# 100 x 100 mm the page shows no engineering-fee line; Rev E's 140 x 105 mm read the same day $52.40
# with a $25 engineering fee (manufacturing/rev-e/fab-quote.json).  Re-quote with the Gerbers at upload.
FAB_QUOTE = json.loads((ROOT / os.environ.get('LCR_FAB_QUOTE', 'manufacturing/fab-quote.json')).read_text())
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
    placed = {row['Designator'] for row in csv.DictReader(open(PKG / 'cpl-jlcpcb.csv'))}
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
        elif pads and not fp.IsDNP():
            tht_joints += len(pads)
            tht_refs.append(ref)
    return len(placed), smt_joints, sorted(leadless), tht_joints, sorted(tht_refs)


def main():
    snapshot = json.loads((MFG / 'prices/jlc-parts-2026-10-29.json').read_text())['parts']
    placements, smt_joints, leadless, tht_joints, tht_refs = board_counts()
    lines, findings = [], []
    for row in csv.DictReader(open(PKG / 'bom-complete.csv')):
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
    hand = [l for l in lines if l['assembly'] not in ('SMT', 'DNP')]
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
    (PKG / f'order-estimate-{N}.json').write_text(json.dumps(result, indent=1) + '\n')

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
