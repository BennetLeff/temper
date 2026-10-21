#!/usr/bin/env python3
"""Snapshot JLC's assembly-library entry for every LCSC code in manufacturing/bom-complete.csv.
Same schema as ../manufacturing/prices/jlc-parts-*.json (read by order_estimate.py).
Uses curl (macOS Python's certificate store fails on this host)."""
import csv
import datetime
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
URL = 'https://jlcpcb.com/api/overseas-pcb-order/v1/shoppingCart/smtGood/selectSmtComponentList'


def lookup(code):
    body = json.dumps({'keyword': code, 'currentPage': 1, 'pageSize': 25})
    raw = subprocess.run(['curl', '-s', '-X', 'POST', '-H', 'Content-Type: application/json',
                          '-A', 'Mozilla/5.0', '-d', body, URL], check=True, capture_output=True).stdout
    hits = [c for c in json.loads(raw)['data']['componentPageInfo']['list'] if c['componentCode'] == code]
    assert len(hits) == 1, (code, len(hits))
    c = hits[0]
    return {'model': c['componentModelEn'], 'brand': c.get('componentBrandEn'),
            'describe': c.get('describe'), 'library': c['componentLibraryType'],
            'preferred': bool(c['preferredComponentFlag']), 'stock': c['stockCount'],
            'least': c['leastPatchNumber'], 'loss': c['lossNumber'],
            'datasheet': c.get('dataManualUrl'),
            'tiers': [[p['startNumber'], p['productPrice']] for p in c['componentPrices']]}


codes = sorted({r['LCSC'] for r in csv.DictReader((ROOT / 'manufacturing/bom-complete.csv').open())})
today = datetime.date.today().isoformat()
out = {'source': f'POST {URL} {{"keyword": <LCSC>}}, exact componentCode match', 'fetched': today,
       'parts': {c: lookup(c) for c in codes}}
dest = ROOT / f'manufacturing/jlc-parts-{today}.json'
dest.write_text(json.dumps(out, indent=1, ensure_ascii=False) + '\n')
print(f'{len(codes)} parts -> {dest.name}')
