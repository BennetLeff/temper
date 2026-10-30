"""JLC assembly fee model and part-quantity rule (pure; Python 3.9+).

Fee constants from https://jlcpcb.com/help/article/pcb-assembly-price (last updated 2026-09-09, read
2026-10-20).  Part quantity per BOM line is max(N * per-board + lossNumber, leastPatchNumber), our reading of
JLC's library fields (attrition pieces and minimum patch quantity); the uploaded BOM quote is authoritative.
A line is an extended-part line when the library class is 'expand' and it is not preferred.  Shipping,
taxes and import duty are not modelled.
"""
from __future__ import annotations

import re

ECONOMIC = {'setup': 8.18, 'stencil': 1.53, 'extended_line': 3.07}
STANDARD = {'setup': 25.56, 'stencil': 8.21, 'extended_line': 3.07, 'basic_line': 1.53,
            'fixtures_1_29': 16.42}
SMT_JOINT = 0.0016            # 1-100,000 joints (Economic)
MANUAL_JOINT = 0.0164         # 1-10,000 joints
HAND_LABOR = 3.58             # per order, when any part is hand soldered
CONFIRM_PLACEMENT = 0.45
XRAY_TIERS = [(10, 1.64), (50, 0.82), (200, 0.49), (500, 0.33)]     # (pieces up to, $ each)
LEADLESS = re.compile(r'QFN|DFN|SON|BGA|LGA')   # case-sensitive: 'Panasonic' is not a SON
EXCLUDED = ['shipping', 'sales tax / VAT / import duty', 'coupons']


def tier_price(tiers, qty):
    """tiers [(start qty, unit price)] ascending -> the unit price at qty."""
    price = tiers[0][1]
    for start, value in tiers:
        if qty >= start:
            price = value
    return price


def buy_qty(need, loss, least):
    return max(need + loss, least)


def is_extended(library, preferred):
    return library == 'expand' and not preferred


def xray_unit(pieces):
    return next(price for limit, price in XRAY_TIERS if pieces <= limit)


def fees(n, smt_parts, hand_parts, smt_joints, tht_joints, leadless, extended_lines, basic_lines, fab):
    """Per-order cost breakdowns (unrounded) for N boards: Economic and Standard PCBA, and JLC hand fit.
    smt_joints / tht_joints / leadless are per board; smt_parts / hand_parts and fab are order totals."""
    xray_pcs = n * leadless
    common = {
        'SMT parts': smt_parts,
        'SMT joints': n * smt_joints * SMT_JOINT,
        'X-ray': xray_pcs * xray_unit(xray_pcs),
        'Confirm placement': CONFIRM_PLACEMENT,
        'PCB fabrication': fab,
    }
    economic = dict(common, **{
        'Setup': ECONOMIC['setup'], 'Stencil': ECONOMIC['stencil'],
        'Extended-part fee': extended_lines * ECONOMIC['extended_line'],
    })
    standard = dict(common, **{
        'Setup': STANDARD['setup'], 'Stencil': STANDARD['stencil'],
        'Feeder loading': extended_lines * STANDARD['extended_line'] + basic_lines * STANDARD['basic_line'],
        'Fixtures': STANDARD['fixtures_1_29'],
    })
    jlc_hand = {'Hand-fit parts via JLC': hand_parts,
                'Manual joints': n * tht_joints * MANUAL_JOINT, 'Hand-soldering labour': HAND_LABOR}
    return {'economic': economic, 'standard': standard, 'jlc_hand_fit': jlc_hand}


def rounded(breakdowns):
    """-> (breakdowns rounded to cents, totals rounded to cents)."""
    out = {name: {k: round(v, 2) for k, v in b.items()} for name, b in breakdowns.items()}
    return out, {name: round(sum(b.values()), 2) for name, b in breakdowns.items()}
